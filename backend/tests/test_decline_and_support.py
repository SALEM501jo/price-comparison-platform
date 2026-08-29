"""
Declining a merchant claim, and reading the contact form.

Both close a gap where the data existed and nothing could act on it: a claim
could be approved or ignored but never refused, and support messages were
written to a table nobody ever read back.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.store import Store
from app.models.support import SupportMessage
from app.models.user import User, UserRole
from app.security.password import hash_password

PASSWORD = "AdminPass123"


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session, monkeypatch):
    async def no_limit(*args, **kwargs):
        return None

    monkeypatch.setattr("app.security.rate_limiter._enforce", no_limit)
    monkeypatch.setattr(Base.metadata, "create_all", lambda *a, **k: None)
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def admin_token(client, db_session):
    db_session.add(
        User(
            email="admin@example.com",
            password_hash=hash_password(PASSWORD),
            role=UserRole.admin,
        )
    )
    db_session.commit()
    response = client.post(
        "/auth/login", json={"email": "admin@example.com", "password": PASSWORD}
    )
    return response.json()["access_token"]


@pytest.fixture
def pending_store(db_session):
    owner = User(
        email="shop@example.com",
        password_hash=hash_password(PASSWORD),
        role=UserRole.merchant,
    )
    db_session.add(owner)
    db_session.commit()
    store = Store(name="Dubious Shop", owner_user_id=owner.id, is_verified=False)
    db_session.add(store)
    db_session.commit()
    db_session.refresh(store)
    return store


def auth(token):
    return {"Authorization": f"Bearer {token}"}


class TestDeclining:
    def test_a_claim_can_be_refused(self, client, db_session, admin_token, pending_store):
        response = client.post(
            f"/admin/stores/{pending_store.id}/decline", headers=auth(admin_token)
        )

        assert response.status_code == 200
        assert response.json()["review_status"] == "declined"
        db_session.refresh(pending_store)
        assert pending_store.rejected_at is not None
        assert pending_store.is_verified is False

    def test_a_declined_claim_leaves_the_pending_queue(
        self, client, admin_token, pending_store
    ):
        """
        The whole point. Before this, a refused claim stayed in the queue
        looking exactly like one nobody had reviewed, so the queue could never
        be cleared and the same bad claim was re-read on every visit.
        """
        before = client.get(
            "/admin/stores?pending_only=true", headers=auth(admin_token)
        ).json()
        assert any(row["id"] == pending_store.id for row in before)

        client.post(
            f"/admin/stores/{pending_store.id}/decline", headers=auth(admin_token)
        )

        after = client.get(
            "/admin/stores?pending_only=true", headers=auth(admin_token)
        ).json()
        assert not any(row["id"] == pending_store.id for row in after)

    def test_declining_does_not_delete_the_shop(
        self, client, db_session, admin_token, pending_store
    ):
        """
        The store, its listings and its history stay. Deleting would destroy a
        real shop's data on a judgement that might be wrong, and would let the
        same claim be re-registered with no record it had been refused.
        """
        client.post(
            f"/admin/stores/{pending_store.id}/decline", headers=auth(admin_token)
        )
        assert db_session.query(Store).filter_by(id=pending_store.id).first()

    def test_approving_afterwards_clears_the_decline(
        self, client, db_session, admin_token, pending_store
    ):
        """A shop that sends proof after being turned down must not be stuck."""
        client.post(
            f"/admin/stores/{pending_store.id}/decline", headers=auth(admin_token)
        )
        client.post(
            f"/admin/stores/{pending_store.id}/verify", headers=auth(admin_token)
        )

        db_session.refresh(pending_store)
        assert pending_store.is_verified is True
        assert pending_store.rejected_at is None
        assert pending_store.review_status == "verified"

    def test_a_scraped_store_has_no_claim_to_decline(
        self, client, db_session, admin_token
    ):
        scraped = Store(name="SmartBuy", is_verified=True)
        db_session.add(scraped)
        db_session.commit()

        response = client.post(
            f"/admin/stores/{scraped.id}/decline", headers=auth(admin_token)
        )
        assert response.status_code == 400

    def test_only_an_admin_may_decline(self, client, db_session, pending_store):
        """
        Two different refusals, and the distinction is deliberate: no token at
        all is 401 (the bearer scheme rejects it before any handler runs), a
        valid token without the role is 403.
        """
        path = f"/admin/stores/{pending_store.id}/decline"
        assert client.post(path).status_code == 401

        db_session.add(
            User(
                email="shopper@example.com",
                password_hash=hash_password(PASSWORD),
                role=UserRole.user,
            )
        )
        db_session.commit()
        token = client.post(
            "/auth/login",
            json={"email": "shopper@example.com", "password": PASSWORD},
        ).json()["access_token"]

        assert client.post(path, headers=auth(token)).status_code == 403


class TestReadingSupportMessages:
    def test_a_message_sent_through_the_form_is_readable(
        self, client, db_session, admin_token
    ):
        """
        The gap this closes: the contact form always stored its messages, but
        nothing read them back. With the console mail backend in development
        and SUPPORT_EMAIL optional in production, a support request went into
        the database and was never seen by a human.
        """
        sent = client.post(
            "/support/contact",
            json={
                "email": "shopper@example.com",
                "subject": "Wrong price",
                "body": "The iPhone 15 price at SmartBuy looks out of date.",
            },
        )
        assert sent.status_code == 202

        response = client.get("/admin/support-messages", headers=auth(admin_token))

        assert response.status_code == 200
        body = response.json()
        assert body["unhandled"] == 1
        assert body["messages"][0]["email"] == "shopper@example.com"
        assert "out of date" in body["messages"][0]["body"]

    def test_it_can_be_marked_handled_and_reopened(
        self, client, db_session, admin_token
    ):
        record = SupportMessage(email="a@example.com", body="x" * 20)
        db_session.add(record)
        db_session.commit()

        client.post(
            f"/admin/support-messages/{record.id}/handled?handled=true",
            headers=auth(admin_token),
        )
        db_session.refresh(record)
        assert record.handled is True

        # Reversible: "handled" is a note to the next admin, not an archive.
        client.post(
            f"/admin/support-messages/{record.id}/handled?handled=false",
            headers=auth(admin_token),
        )
        db_session.refresh(record)
        assert record.handled is False

    def test_unhandled_filter_hides_what_is_done(
        self, client, db_session, admin_token
    ):
        db_session.add_all(
            [
                SupportMessage(email="a@example.com", body="x" * 20, handled=True),
                SupportMessage(email="b@example.com", body="y" * 20, handled=False),
            ]
        )
        db_session.commit()

        response = client.get(
            "/admin/support-messages?handled=false", headers=auth(admin_token)
        )
        emails = [m["email"] for m in response.json()["messages"]]
        assert emails == ["b@example.com"]

    def test_only_an_admin_may_read_them(self, client, db_session):
        """
        These are other people's private messages -- often from someone locked
        out, so frequently carrying an address they have not proved they own.
        """
        db_session.add(SupportMessage(email="a@example.com", body="x" * 20))
        db_session.add(
            User(
                email="nosy@example.com",
                password_hash=hash_password(PASSWORD),
                role=UserRole.merchant,
            )
        )
        db_session.commit()

        assert client.get("/admin/support-messages").status_code == 401

        token = client.post(
            "/auth/login",
            json={"email": "nosy@example.com", "password": PASSWORD},
        ).json()["access_token"]
        assert client.get(
            "/admin/support-messages", headers=auth(token)
        ).status_code == 403


class TestInstagram:
    def test_a_shop_can_publish_an_instagram_profile(self, client, db_session):
        user = User(
            email="newshop@example.com",
            password_hash=hash_password(PASSWORD),
            role=UserRole.user,
        )
        db_session.add(user)
        db_session.commit()
        token = client.post(
            "/auth/login",
            json={"email": "newshop@example.com", "password": PASSWORD},
        ).json()["access_token"]

        response = client.post(
            "/merchant/store",
            json={
                "name": "Insta Shop",
                "phone": "0791234567",
                "instagram_url": "https://instagram.com/instashop",
            },
            headers=auth(token),
        )

        assert response.status_code == 201, response.text
        assert response.json()["instagram_url"] == "https://instagram.com/instashop"

    @pytest.mark.parametrize(
        "url",
        [
            "http://instagram.com/x",          # not https
            "https://evil.com/instagram.com/x",  # host is not instagram
            "https://instagram.com/a/b/c",     # not a single handle
            "javascript:alert(1)",
        ],
    )
    def test_only_a_real_instagram_profile_is_accepted(
        self, client, db_session, url
    ):
        """
        Same reasoning as the Facebook validator: an unchecked URL here becomes
        an open redirect advertised to every shopper on the product page.
        """
        user = User(
            email=f"shop-{abs(hash(url))}@example.com",
            password_hash=hash_password(PASSWORD),
            role=UserRole.user,
        )
        db_session.add(user)
        db_session.commit()
        token = client.post(
            "/auth/login",
            json={"email": user.email, "password": PASSWORD},
        ).json()["access_token"]

        response = client.post(
            "/merchant/store",
            json={"name": f"Shop {abs(hash(url))}", "instagram_url": url},
            headers=auth(token),
        )
        assert response.status_code == 422
