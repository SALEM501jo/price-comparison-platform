"""
Forgotten passwords, and the contact form.

Both endpoints are unauthenticated and take an email address, which makes them
the two easiest account-enumeration oracles in the application and the two
easiest ways to send mail to a stranger using our infrastructure. Most of what
follows tests that they refuse to be either.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.email_token import EmailToken
from app.models.refresh_token import RefreshToken
from app.models.support import SupportMessage
from app.models.user import User
from app.services import password_reset, verification

PASSWORD = "TestPass123"
NEW_PASSWORD = "BrandNew456"


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
def sent(monkeypatch):
    """Capture outbound mail instead of sending it."""
    outbox = []

    def fake_send(message):
        outbox.append(message)
        return True

    monkeypatch.setattr("app.services.email.send", fake_send)
    monkeypatch.setattr("app.services.password_reset.email_service.send", fake_send)
    monkeypatch.setattr("app.routers.support.email_service.send", fake_send)
    return outbox


def signup(client, email="user@example.com"):
    response = client.post(
        "/auth/register", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def request_reset(client, email="user@example.com"):
    return client.post("/auth/forgot-password", json={"email": email})


def token_for(db_session, email="user@example.com"):
    """The plaintext token is only returned once, so re-issue one directly."""
    user = db_session.query(User).filter(User.email == email).first()
    return verification.issue(db_session, user, purpose=password_reset.PURPOSE_RESET)


# --- Requesting a reset -----------------------------------------------------


class TestForgotPassword:
    def test_a_real_address_gets_a_link(self, client, db_session, sent):
        signup(client)
        assert request_reset(client).status_code == 202
        assert len(sent) >= 1
        body = sent[-1].text
        assert "/reset-password?token=" in body

    def test_the_email_never_contains_a_password(self, client, db_session, sent):
        """
        The whole reason this is a link. A password mailed in plaintext sits
        in an inbox forever and would mean the server had generated it.
        """
        signup(client)
        sent.clear()
        request_reset(client)
        message = sent[-1]
        haystack = f"{message.subject} {message.text} {message.html or ''}"
        assert PASSWORD not in haystack
        assert "password:" not in haystack.lower()
        assert "your new password" not in haystack.lower()

    def test_an_unknown_address_looks_identical(self, client, sent):
        """
        A 404 here would turn the endpoint into a membership check anyone
        could run against a list of email addresses.
        """
        signup(client, "real@example.com")
        known = request_reset(client, "real@example.com")
        unknown = request_reset(client, "nobody@example.com")
        assert known.status_code == unknown.status_code == 202
        assert known.json() == unknown.json()

    def test_no_mail_is_sent_to_a_stranger(self, client, sent):
        signup(client, "real@example.com")
        sent.clear()
        request_reset(client, "stranger@example.com")
        assert sent == []

    def test_requests_are_throttled_per_account(self, client, db_session, sent):
        """
        Per ACCOUNT, not only per IP: an IP limit alone still lets someone
        rotate addresses and bury one person's inbox using our sender.
        """
        signup(client)
        sent.clear()
        for _ in range(4):
            request_reset(client)
        assert len(sent) == 1

    def test_a_new_request_retires_the_previous_link(self, client, db_session, sent):
        signup(client)
        first = token_for(db_session, "user@example.com")
        second = token_for(db_session, "user@example.com")

        assert (
            client.post(
                "/auth/reset-password",
                json={"token": first, "password": NEW_PASSWORD},
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/auth/reset-password",
                json={"token": second, "password": NEW_PASSWORD},
            ).status_code
            == 200
        )


# --- Spending the link ------------------------------------------------------


class TestResetPassword:
    def test_the_new_password_works_and_the_old_one_does_not(
        self, client, db_session, sent
    ):
        signup(client)
        token = token_for(db_session)

        assert (
            client.post(
                "/auth/reset-password",
                json={"token": token, "password": NEW_PASSWORD},
            ).status_code
            == 200
        )

        old = client.post(
            "/auth/login", json={"email": "user@example.com", "password": PASSWORD}
        )
        new = client.post(
            "/auth/login",
            json={"email": "user@example.com", "password": NEW_PASSWORD},
        )
        assert old.status_code == 401
        assert new.status_code == 200

    def test_every_existing_session_is_revoked(self, client, db_session, sent):
        """
        The point of a reset. Somebody else holding a live session is the most
        likely reason a person is resetting, and leaving it working would make
        the whole exercise theatre.
        """
        signup(client)
        live = (
            db_session.query(RefreshToken)
            .filter(RefreshToken.revoked_at.is_(None))
            .count()
        )
        assert live >= 1

        token = token_for(db_session)
        client.post(
            "/auth/reset-password", json={"token": token, "password": NEW_PASSWORD}
        )

        db_session.expire_all()
        still_live = (
            db_session.query(RefreshToken)
            .filter(RefreshToken.revoked_at.is_(None))
            .count()
        )
        assert still_live == 0

    def test_a_link_works_only_once(self, client, db_session, sent):
        signup(client)
        token = token_for(db_session)
        first = client.post(
            "/auth/reset-password", json={"token": token, "password": NEW_PASSWORD}
        )
        second = client.post(
            "/auth/reset-password",
            json={"token": token, "password": "SomethingElse7"},
        )
        assert first.status_code == 200
        assert second.status_code == 401

    def test_an_expired_link_is_refused(self, client, db_session, sent):
        from datetime import datetime, timedelta, timezone

        signup(client)
        token = token_for(db_session)
        record = db_session.query(EmailToken).order_by(EmailToken.id.desc()).first()
        record.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db_session.commit()

        assert (
            client.post(
                "/auth/reset-password",
                json={"token": token, "password": NEW_PASSWORD},
            ).status_code
            == 401
        )

    @pytest.mark.parametrize("bogus", ["", "not-a-token", "x" * 60])
    def test_a_bogus_token_is_refused(self, client, bogus):
        response = client.post(
            "/auth/reset-password", json={"token": bogus, "password": NEW_PASSWORD}
        )
        assert response.status_code in (401, 422)

    def test_a_verification_token_cannot_reset_a_password(
        self, client, db_session, sent
    ):
        """
        Purposes are not interchangeable. A verification link is handed out on
        signup and sits in inboxes; if it doubled as a reset link, anyone who
        ever saw one could take the account.
        """
        signup(client)
        user = db_session.query(User).filter(User.email == "user@example.com").first()
        wrong = verification.issue(db_session, user, purpose=verification.PURPOSE_VERIFY)

        assert (
            client.post(
                "/auth/reset-password",
                json={"token": wrong, "password": NEW_PASSWORD},
            ).status_code
            == 401
        )

    @pytest.mark.parametrize("weak", ["short1A", "nouppercase123", "NoDigitsHere"])
    def test_the_password_policy_still_applies(self, client, db_session, sent, weak):
        """A reset accepting a weaker password than signup is the easy way past."""
        signup(client)
        token = token_for(db_session)
        assert (
            client.post(
                "/auth/reset-password", json={"token": token, "password": weak}
            ).status_code
            == 422
        )

    def test_resetting_does_not_hand_back_a_session(self, client, db_session, sent):
        """
        Deliberate: a reset link opened on a shared machine must not leave
        somebody signed in behind it.
        """
        signup(client)
        token = token_for(db_session)
        body = client.post(
            "/auth/reset-password", json={"token": token, "password": NEW_PASSWORD}
        ).json()
        assert "access_token" not in body

    def test_the_address_is_marked_verified(self, client, db_session, sent):
        """Redeeming the link proves control of the mailbox, which is the point."""
        signup(client)
        token = token_for(db_session)
        client.post(
            "/auth/reset-password", json={"token": token, "password": NEW_PASSWORD}
        )
        db_session.expire_all()
        user = db_session.query(User).filter(User.email == "user@example.com").first()
        assert user.email_verified_at is not None


# --- Contact form -----------------------------------------------------------


class TestContactForm:
    def test_anyone_can_write_in_without_signing_in(self, client, db_session, sent):
        """The people who most need support are the ones who cannot get in."""
        response = client.post(
            "/support/contact",
            json={
                "email": "stuck@example.com",
                "subject": "Cannot sign in",
                "body": "My password reset link never arrived, can you help?",
            },
        )
        assert response.status_code == 202, response.text
        assert db_session.query(SupportMessage).count() == 1

    def test_the_message_is_stored_even_when_mail_fails(
        self, client, db_session, monkeypatch
    ):
        """
        The row is the record; the email is a notification about it. A support
        request that vanishes is worse than one never sent, because its author
        is waiting for an answer.
        """
        def explode(_message):
            raise RuntimeError("smtp down")

        monkeypatch.setattr("app.routers.support.email_service.send", explode)

        response = client.post(
            "/support/contact",
            json={"email": "stuck@example.com", "body": "Something is broken here."},
        )
        # Either the mail is skipped (no support address configured) or it
        # raised and was swallowed -- the message must exist regardless.
        assert response.status_code == 202
        assert db_session.query(SupportMessage).count() == 1

    def test_a_signed_in_sender_is_linked_to_their_account(
        self, client, db_session, sent
    ):
        headers = signup(client, "member@example.com")
        client.post(
            "/support/contact",
            json={"email": "member@example.com", "body": "A question about alerts."},
            headers=headers,
        )
        record = db_session.query(SupportMessage).first()
        assert record.user_id is not None

    def test_an_anonymous_message_has_no_account(self, client, db_session, sent):
        client.post(
            "/support/contact",
            json={"email": "nobody@example.com", "body": "Just browsing, a question."},
        )
        assert db_session.query(SupportMessage).first().user_id is None

    @pytest.mark.parametrize(
        "payload",
        [
            {"email": "not-an-email", "body": "A long enough message here."},
            {"email": "a@b.com", "body": "short"},
            {"email": "a@b.com", "body": "x" * 5000},
            {"body": "No address at all in this message."},
        ],
    )
    def test_malformed_messages_are_refused(self, client, payload):
        assert client.post("/support/contact", json=payload).status_code == 422

    def test_the_form_does_not_reveal_who_has_an_account(
        self, client, db_session, sent
    ):
        signup(client, "member@example.com")
        known = client.post(
            "/support/contact",
            json={"email": "member@example.com", "body": "A question from a member."},
        )
        unknown = client.post(
            "/support/contact",
            json={"email": "stranger@example.com", "body": "A question from nobody."},
        )
        assert known.status_code == unknown.status_code == 202
        assert set(known.json()) == set(unknown.json())
