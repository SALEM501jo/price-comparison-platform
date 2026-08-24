"""
Email verification and price alert notifications.

The interesting tests here are the negative ones. Verification endpoints are
unauthenticated and take an email address, which makes them the easiest
account-enumeration oracle in the application and a convenient way to mail a
stranger using someone else's infrastructure.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.alias import ProductAlias
from app.models.email_token import EmailToken
from app.models.price import Price, PriceAlert
from app.models.product import Product
from app.models.store import Store
from app.models.user import User
from app.services import verification
from app.services.email.base import NullSender

PASSWORD = "TestPass123"
EMAIL = "verify@example.com"


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def mail(monkeypatch):
    """Capture outgoing mail so no test can send anything."""
    sender = NullSender()
    monkeypatch.setattr("app.services.email.get_sender", lambda: sender)
    return sender


@pytest.fixture
def client(db_session, mail, monkeypatch):
    async def no_limit(*args, **kwargs):
        return None

    monkeypatch.setattr("app.security.rate_limiter._enforce", no_limit)
    monkeypatch.setattr(Base.metadata, "create_all", lambda *a, **k: None)

    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def register(client, email=EMAIL):
    response = client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    return response.json()


def link_token(mail) -> str:
    """Pull the token out of the most recent email, as a user would."""
    body = mail.sent[-1].text
    return body.split("token=")[1].split()[0]


class TestRegistrationSendsAVerificationEmail:
    def test_an_email_goes_out(self, client, mail):
        register(client)
        assert len(mail.sent) == 1
        assert mail.sent[0].to == EMAIL

    def test_the_link_points_at_the_frontend_not_the_api(self, client, mail):
        """
        Built from configuration, never from the request Host header -- a
        header is client-supplied, and a link assembled from one is a phishing
        link the application sends under its own name.
        """
        register(client)
        assert "http://localhost:5173/verify-email?token=" in mail.sent[0].text

    def test_only_the_hash_is_stored(self, client, mail, db_session):
        """A database dump must not contain working links."""
        register(client)
        token = link_token(mail)
        record = db_session.query(EmailToken).one()
        assert record.token_hash != token
        assert token not in record.token_hash
        assert len(record.token_hash) == 64  # sha256 hex

    def test_a_new_account_starts_unverified(self, client, mail, db_session):
        register(client)
        assert db_session.query(User).one().email_verified_at is None

    def test_registration_still_succeeds_when_mail_fails(
        self, client, db_session, monkeypatch
    ):
        """A mail outage must not leave signup broken."""

        class Broken(NullSender):
            def send(self, message):
                raise RuntimeError("smtp is down")

        monkeypatch.setattr("app.services.email.get_sender", lambda: Broken())
        assert (
            client.post(
                "/auth/register", json={"email": "x@example.com", "password": PASSWORD}
            ).status_code
            == 201
        )


class TestRedeemingALink:
    def test_a_valid_token_verifies_the_account(self, client, mail, db_session):
        register(client)
        response = client.post("/auth/verify-email", json={"token": link_token(mail)})
        assert response.status_code == 200, response.text
        assert db_session.query(User).one().email_verified_at is not None

    def test_the_response_reports_verification(self, client, mail):
        register(client)
        body = client.post("/auth/verify-email", json={"token": link_token(mail)}).json()
        assert body["email_verified_at"] is not None

    def test_a_token_works_only_once(self, client, mail):
        register(client)
        token = link_token(mail)
        assert client.post("/auth/verify-email", json={"token": token}).status_code == 200
        assert client.post("/auth/verify-email", json={"token": token}).status_code == 401

    def test_an_expired_token_is_refused(self, client, mail, db_session):
        register(client)
        token = link_token(mail)
        record = db_session.query(EmailToken).one()
        record.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db_session.commit()

        assert client.post("/auth/verify-email", json={"token": token}).status_code == 401

    def test_requesting_a_second_link_retires_the_first(self, client, mail, db_session):
        register(client)
        first = link_token(mail)

        user = db_session.query(User).one()
        verification.send_verification(db_session, user)
        second = link_token(mail)

        assert client.post("/auth/verify-email", json={"token": first}).status_code == 401
        assert client.post("/auth/verify-email", json={"token": second}).status_code == 200

    @pytest.mark.parametrize("token", ["", "nonsense", "a" * 64])
    def test_garbage_tokens_are_refused(self, client, token):
        assert client.post("/auth/verify-email", json={"token": token}).status_code == 401

    def test_every_failure_gives_the_same_message(self, client, mail):
        """
        Distinguishing "expired" from "already used" from "never existed" tells
        an attacker holding a stale link which it is, and helps a real user not
        at all beyond "request another".
        """
        register(client)
        token = link_token(mail)
        client.post("/auth/verify-email", json={"token": token})

        used = client.post("/auth/verify-email", json={"token": token})
        unknown = client.post("/auth/verify-email", json={"token": "never-existed"})
        assert used.json() == unknown.json()


class TestResendDoesNotLeakWhoHasAnAccount:
    def test_unknown_address_returns_the_same_as_a_known_one(self, client, mail):
        register(client)
        known = client.post("/auth/resend-verification", json={"email": EMAIL})
        unknown = client.post(
            "/auth/resend-verification", json={"email": "nobody@example.com"}
        )
        assert known.status_code == unknown.status_code == 202
        assert known.json() == unknown.json()

    def test_no_mail_is_sent_to_an_unknown_address(self, client, mail):
        client.post("/auth/resend-verification", json={"email": "nobody@example.com"})
        assert mail.sent == []

    def test_an_already_verified_account_gets_no_new_link(self, client, mail, db_session):
        register(client)
        client.post("/auth/verify-email", json={"token": link_token(mail)})
        before = len(mail.sent)

        response = client.post("/auth/resend-verification", json={"email": EMAIL})
        assert response.status_code == 202
        assert len(mail.sent) == before

    def test_resending_is_throttled_per_account(self, client, mail, db_session):
        """
        Per account, not only per IP: an IP limit alone still lets someone
        rotate addresses and bury a stranger's inbox using our sending
        reputation.
        """
        register(client)
        before = len(mail.sent)

        for _ in range(5):
            client.post("/auth/resend-verification", json={"email": EMAIL})

        assert len(mail.sent) == before, "cooldown did not hold"

    def test_a_link_is_sent_once_the_cooldown_passes(self, client, mail, db_session):
        register(client)
        before = len(mail.sent)

        record = db_session.query(EmailToken).order_by(EmailToken.id.desc()).first()
        record.created_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db_session.commit()

        client.post("/auth/resend-verification", json={"email": EMAIL})
        assert len(mail.sent) == before + 1


class TestAlertNotifications:
    def _catalogue(self, db, price, target, verified=True):
        user = User(
            email="alerts@example.com",
            password_hash="x",
            email_verified_at=datetime.now(timezone.utc) if verified else None,
        )
        store = Store(name="SmartBuy")
        product = Product(canonical_name="iPhone 15 128GB Black", match_category="phones")
        db.add_all([user, store, product])
        db.commit()

        alias = ProductAlias(
            product_id=product.id,
            store_id=store.id,
            store_product_name="iPhone 15",
            store_product_id="X1",
        )
        db.add(alias)
        db.commit()
        db.add(
            Price(
                alias_id=alias.id,
                price=Decimal(str(price)),
                delivery_cost=Decimal("0"),
                availability=True,
            )
        )
        db.add(
            PriceAlert(
                user_id=user.id, product_id=product.id, target_price=Decimal(str(target))
            )
        )
        db.commit()
        return user, product

    def test_a_met_target_sends_one_email(self, db_session, mail):
        from app.services.notifications import process_alerts

        self._catalogue(db_session, price="800.000", target="850.000")
        result = process_alerts(db_session)

        assert result["notified"] == 1
        assert "Price drop" in mail.sent[0].subject

    def test_an_unmet_target_sends_nothing(self, db_session, mail):
        from app.services.notifications import process_alerts

        self._catalogue(db_session, price="900.000", target="850.000")
        assert process_alerts(db_session)["notified"] == 0
        assert mail.sent == []

    def test_exactly_at_target_counts_as_met(self, db_session, mail):
        """The boundary floats get wrong."""
        from app.services.notifications import process_alerts

        self._catalogue(db_session, price="850.000", target="850.000")
        assert process_alerts(db_session)["notified"] == 1

    def test_it_does_not_notify_twice_for_one_drop(self, db_session, mail):
        from app.services.notifications import process_alerts

        self._catalogue(db_session, price="800.000", target="850.000")
        process_alerts(db_session)
        assert process_alerts(db_session)["notified"] == 0
        assert len(mail.sent) == 1

    def test_a_recovered_price_arms_the_alert_again(self, db_session, mail):
        from app.services.notifications import process_alerts

        self._catalogue(db_session, price="800.000", target="850.000")
        process_alerts(db_session)

        price = db_session.query(Price).one()
        price.price = Decimal("900.000")
        db_session.commit()
        assert process_alerts(db_session)["reset"] == 1

        price.price = Decimal("800.000")
        db_session.commit()
        assert process_alerts(db_session)["notified"] == 1
        assert len(mail.sent) == 2

    def test_unverified_users_are_never_emailed(self, db_session, mail):
        """
        Anyone can type a stranger's address at signup. Notifying an
        unconfirmed account is exactly how this feature becomes a way to mail
        someone who never asked.
        """
        from app.services.notifications import process_alerts

        self._catalogue(db_session, price="800.000", target="850.000", verified=False)
        result = process_alerts(db_session)

        assert result["notified"] == 0
        assert result["skipped_unverified"] == 1
        assert mail.sent == []
