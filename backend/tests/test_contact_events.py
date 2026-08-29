"""
Contact taps: the only evidence this platform produces.

There is no checkout, so a shopper tapping Call or WhatsApp is the last thing
visible before the conversation moves to the phone. A merchant asked to pay a
monthly fee will ask what they got for it, and this is the answer.

These tests hold two lines in particular:
  - the number is honest (taps, per shop, scoped to the owner)
  - the endpoint cannot be used to learn which shops exist
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.contact_event import CONTACT_CHANNELS, ContactEvent
from app.models.product import Product
from app.models.store import Store
from app.models.user import User, UserRole
from app.security.password import hash_password
from app.services import contact_stats

PASSWORD = "TapPass123"


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
def shop(db_session):
    """A verified merchant store with an owner who can sign in."""
    owner = User(
        email="shop@example.com",
        password_hash=hash_password(PASSWORD),
        role=UserRole.merchant,
    )
    db_session.add(owner)
    db_session.commit()

    store = Store(
        name="Jado Mobile",
        owner_user_id=owner.id,
        is_verified=True,
        is_active=1,
        phone="0791234567",
    )
    product = Product(canonical_name="iPhone 15 128GB Black", match_category="phones")
    db_session.add_all([store, product])
    db_session.commit()
    db_session.refresh(store)
    db_session.refresh(product)
    return store, product, owner


def token_for(client, email):
    response = client.post(
        "/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


class TestRecordingATap:
    def test_a_tap_is_stored(self, client, db_session, shop):
        store, product, _ = shop

        response = client.post(
            "/products/contact-event",
            json={
                "store_id": store.id,
                "product_id": product.id,
                "channel": "whatsapp",
            },
        )

        assert response.status_code == 202
        event = db_session.query(ContactEvent).one()
        assert event.store_id == store.id
        assert event.channel == "whatsapp"

    def test_it_needs_no_account(self, client, shop):
        """
        Shoppers are not required to sign in. Requiring an account here would
        measure only the minority who have one, which is not the number a
        merchant is being sold.
        """
        store, _, _ = shop
        response = client.post(
            "/products/contact-event",
            json={"store_id": store.id, "channel": "call"},
        )
        assert response.status_code == 202

    def test_an_unknown_channel_is_rejected_at_the_edge(self, client, shop):
        store, _, _ = shop
        response = client.post(
            "/products/contact-event",
            json={"store_id": store.id, "channel": "carrier_pigeon"},
        )
        assert response.status_code == 422

    def test_no_personal_data_is_stored(self, client, db_session, shop):
        """
        A row is (shop, product, channel, when). Anything that could identify
        the shopper -- an IP, a user id, a session key -- would turn this into
        a record of what an individual browsed, which is what Jordan's PDPL
        covers and what this feature does not need.
        """
        store, _, _ = shop
        client.post(
            "/products/contact-event",
            json={"store_id": store.id, "channel": "call"},
        )
        columns = {c.name for c in ContactEvent.__table__.columns}
        assert columns == {"id", "store_id", "product_id", "channel", "created_at"}


class TestItIsNotAStoreOracle:
    """
    The endpoint takes a store id from an anonymous caller. A 404 for unknown
    ids would make it a way to enumerate which shops exist, and which are
    still unverified -- the same reasoning as /auth/forgot-password.
    """

    def test_an_unknown_store_still_returns_202(self, client, db_session, shop):
        response = client.post(
            "/products/contact-event",
            json={"store_id": 9999, "channel": "call"},
        )
        assert response.status_code == 202
        assert db_session.query(ContactEvent).count() == 0

    def test_an_unverified_store_still_returns_202_and_records_nothing(
        self, client, db_session
    ):
        owner = User(
            email="pending@example.com",
            password_hash=hash_password(PASSWORD),
            role=UserRole.merchant,
        )
        db_session.add(owner)
        db_session.commit()
        hidden = Store(name="Pending Shop", owner_user_id=owner.id, is_verified=False)
        db_session.add(hidden)
        db_session.commit()

        response = client.post(
            "/products/contact-event",
            json={"store_id": hidden.id, "channel": "call"},
        )
        assert response.status_code == 202
        assert db_session.query(ContactEvent).count() == 0

    def test_an_unknown_product_does_not_lose_the_tap(
        self, client, db_session, shop
    ):
        """
        The shop was still contacted. Dropping the row because the product id
        was stale would quietly reduce a number the merchant is billed on.
        """
        store, _, _ = shop
        response = client.post(
            "/products/contact-event",
            json={"store_id": store.id, "product_id": 4242, "channel": "call"},
        )
        assert response.status_code == 202
        event = db_session.query(ContactEvent).one()
        assert event.product_id is None


class TestMerchantSeesOnlyTheirOwn:
    def test_the_dashboard_reports_the_taps(self, client, db_session, shop):
        store, product, owner = shop
        for channel in ("call", "call", "whatsapp"):
            db_session.add(
                ContactEvent(
                    store_id=store.id, product_id=product.id, channel=channel
                )
            )
        db_session.commit()

        response = client.get(
            "/merchant/stats",
            headers={"Authorization": f"Bearer {token_for(client, owner.email)}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 3
        assert body["by_channel"]["call"] == 2
        assert body["by_channel"]["whatsapp"] == 1
        assert body["top_products"][0]["product_name"] == product.canonical_name
        assert body["top_products"][0]["taps"] == 3

    def test_every_channel_is_reported_even_at_zero(self, client, shop):
        """
        "Nobody used WhatsApp" and "WhatsApp is not set up" need different
        actions from the shop owner, and a dashboard that hides empty
        channels makes them look identical.
        """
        _, _, owner = shop
        response = client.get(
            "/merchant/stats",
            headers={"Authorization": f"Bearer {token_for(client, owner.email)}"},
        )
        # Derived from the model rather than listed here: this assertion was
        # written with three channels and broke the moment Instagram was added,
        # which is the test going stale rather than the code going wrong.
        assert set(response.json()["by_channel"]) == set(CONTACT_CHANNELS)

    def test_another_shops_taps_are_invisible(self, client, db_session, shop):
        """
        The access-control shape of this module: the store is resolved from
        the signed-in user, so there is no id to tamper with. A rival's
        traffic is commercially sensitive and must not leak.
        """
        store, _, owner = shop
        rival_owner = User(
            email="rival@example.com",
            password_hash=hash_password(PASSWORD),
            role=UserRole.merchant,
        )
        db_session.add(rival_owner)
        db_session.commit()
        rival = Store(name="Rival Shop", owner_user_id=rival_owner.id, is_verified=True)
        db_session.add(rival)
        db_session.commit()
        for _ in range(5):
            db_session.add(ContactEvent(store_id=rival.id, channel="call"))
        db_session.commit()

        response = client.get(
            "/merchant/stats",
            headers={"Authorization": f"Bearer {token_for(client, owner.email)}"},
        )
        assert response.json()["total"] == 0


class TestTheWindow:
    def test_taps_outside_the_window_are_not_counted(self, db_session, shop):
        """
        Thirty days because that is the period a monthly fee covers, so the
        number shown is the number being charged against.
        """
        store, _, _ = shop
        old = ContactEvent(store_id=store.id, channel="call")
        old.created_at = datetime.now(timezone.utc) - timedelta(days=45)
        recent = ContactEvent(store_id=store.id, channel="call")
        recent.created_at = datetime.now(timezone.utc) - timedelta(days=3)
        db_session.add_all([old, recent])
        db_session.commit()

        assert contact_stats.totals_for_store(db_session, store.id)["total"] == 1

    def test_many_stores_are_counted_in_one_query(self, db_session, shop):
        """
        The admin screen lists every store. A per-row lookup would be the same
        N+1 shape this codebase already removed from price_summary().
        """
        store, _, _ = shop
        db_session.add(ContactEvent(store_id=store.id, channel="call"))
        db_session.commit()

        summary = contact_stats.totals_for_stores(db_session, [store.id, 999])
        assert summary[store.id]["total"] == 1
        # A store with no taps is still present, with zeroes rather than absent.
        assert summary[999]["total"] == 0


class TestAdminSeesEveryShop:
    def test_the_store_list_carries_tap_counts(self, client, db_session, shop):
        store, _, _ = shop
        db_session.add(ContactEvent(store_id=store.id, channel="whatsapp"))
        db_session.commit()

        admin = User(
            email="admin@example.com",
            password_hash=hash_password(PASSWORD),
            role=UserRole.admin,
        )
        db_session.add(admin)
        db_session.commit()

        response = client.get(
            "/admin/stores",
            headers={"Authorization": f"Bearer {token_for(client, admin.email)}"},
        )

        assert response.status_code == 200
        row = next(r for r in response.json() if r["id"] == store.id)
        assert row["contact_taps"] == 1
        assert row["contact_taps_by_channel"]["whatsapp"] == 1
