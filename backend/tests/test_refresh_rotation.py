"""
Refresh token delivery, rotation, and replay detection.

Two things are under test here:

1. The token is delivered as an httpOnly cookie and never in a response body,
   so page JavaScript -- and therefore any XSS payload -- cannot read it.
2. Every use burns the token, and reusing a spent one is treated as proof of
   compromise and kills the whole chain.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.main import app
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.security.cookies import COOKIE_PATH

PASSWORD = "TestPass123"
EMAIL = "rotate@example.com"
COOKIE = "refresh_token"


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
def session(client):
    """Register, leaving the refresh cookie in the client's jar."""
    response = client.post(
        "/auth/register", json={"email": EMAIL, "password": PASSWORD}
    )
    assert response.status_code == 201, response.text
    return response


def cookie_token(client) -> str:
    """The refresh token the browser currently holds."""
    return client.cookies.get(COOKIE)


def refresh_via_cookie(client):
    """How a browser refreshes: the cookie rides along automatically."""
    return client.post("/auth/refresh")


def refresh_with_token(client, token):
    """
    Present a specific token in the body, as a client with no cookie jar would.

    The jar is cleared first because read_refresh_token() prefers the cookie --
    correctly, since the browser is the primary client. Leaving a live cookie
    in place would mean the body token was silently ignored and the test would
    pass for the wrong reason. This also matches the threat model: a replayed
    token is being used from somewhere else, not from the victim's browser.
    """
    client.cookies.clear()
    return client.post("/auth/refresh", json={"refresh_token": token})


class TestCookieDelivery:
    def test_refresh_token_is_not_in_the_response_body(self, client, session):
        """The crux: no JavaScript on the page ever sees this token."""
        assert "refresh_token" not in session.json()
        assert session.json()["access_token"]

    def test_refresh_token_arrives_as_a_cookie(self, client, session):
        assert cookie_token(client)

    def test_cookie_is_httponly(self, client, session):
        header = session.headers["set-cookie"].lower()
        assert "httponly" in header, "document.cookie could read the token"

    def test_cookie_is_samesite_and_path_scoped(self, client, session):
        header = session.headers["set-cookie"].lower()
        assert "samesite=lax" in header
        # Scoped so the browser does not attach it to ordinary API calls.
        assert f"path={COOKIE_PATH}".lower() in header

    def test_login_also_sets_the_cookie(self, client, session):
        response = client.post(
            "/auth/login", json={"email": EMAIL, "password": PASSWORD}
        )
        assert response.status_code == 200
        assert "refresh_token" not in response.json()
        assert "set-cookie" in response.headers


class TestIssuing:
    def test_registration_records_the_token(self, client, session, db_session):
        assert db_session.query(RefreshToken).count() == 1

    def test_only_the_id_is_stored_never_the_token(self, client, session, db_session):
        """A database dump must not hand over usable credentials."""
        record = db_session.query(RefreshToken).one()
        assert record.jti not in cookie_token(client)
        assert len(record.jti) == 36  # a uuid4, not the token

    def test_login_issues_a_separate_token(self, client, session, db_session):
        client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
        assert db_session.query(RefreshToken).count() == 2


class TestRotation:
    def test_refresh_replaces_the_cookie(self, client, session):
        before = cookie_token(client)
        response = refresh_via_cookie(client)
        assert response.status_code == 200, response.text
        assert cookie_token(client) != before

    def test_the_used_token_is_revoked(self, client, session, db_session):
        refresh_via_cookie(client)
        used = db_session.query(RefreshToken).order_by(RefreshToken.id).first()
        assert used.revoked_at is not None

    def test_rotation_links_old_to_new(self, client, session, db_session):
        refresh_via_cookie(client)
        records = db_session.query(RefreshToken).order_by(RefreshToken.id).all()
        assert len(records) == 2
        assert records[0].replaced_by_jti == records[1].jti

    def test_a_chain_of_refreshes_keeps_working(self, client, session):
        for _ in range(5):
            assert refresh_via_cookie(client).status_code == 200


class TestReplayDetection:
    def test_reusing_a_spent_token_is_rejected(self, client, session):
        stolen = cookie_token(client)
        refresh_via_cookie(client)
        assert refresh_with_token(client, stolen).status_code == 401

    def test_replay_revokes_the_whole_chain(self, client, session, db_session):
        """
        An attacker steals the token and refreshes. The real user then refreshes
        with the copy they still hold, which is now spent. We cannot tell which
        party is which, so BOTH are logged out.
        """
        stolen = cookie_token(client)
        refresh_via_cookie(client)  # attacker rotates
        attacker_token = cookie_token(client)

        assert refresh_with_token(client, stolen).status_code == 401
        assert refresh_with_token(client, attacker_token).status_code == 401

        live = (
            db_session.query(RefreshToken)
            .filter(RefreshToken.revoked_at.is_(None))
            .count()
        )
        assert live == 0, "a token survived the reuse response"

    def test_replay_does_not_affect_other_users(self, client, session, db_session):
        stolen = cookie_token(client)
        refresh_via_cookie(client)
        refresh_with_token(client, stolen)  # trigger the reuse response

        # A different account must be untouched.
        other = TestClient(app)
        other.post(
            "/auth/register",
            json={"email": "bystander@example.com", "password": PASSWORD},
        )
        assert other.post("/auth/refresh").status_code == 200


class TestLogout:
    def test_logout_revokes_every_token(self, client, session, db_session):
        access = session.json()["access_token"]
        client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})

        response = client.post(
            "/auth/logout", headers={"Authorization": f"Bearer {access}"}
        )
        assert response.status_code == 204, response.text

        live = (
            db_session.query(RefreshToken)
            .filter(RefreshToken.revoked_at.is_(None))
            .count()
        )
        assert live == 0

    def test_logout_clears_the_cookie(self, client, session):
        access = session.json()["access_token"]
        response = client.post(
            "/auth/logout", headers={"Authorization": f"Bearer {access}"}
        )
        assert "set-cookie" in response.headers
        assert not client.cookies.get(COOKIE)

    def test_refresh_fails_after_logout(self, client, session):
        access = session.json()["access_token"]
        stolen = cookie_token(client)
        client.post("/auth/logout", headers={"Authorization": f"Bearer {access}"})
        assert refresh_with_token(client, stolen).status_code == 401

    def test_logout_requires_authentication(self, client):
        assert client.post("/auth/logout").status_code == 401


class TestForgedTokens:
    def test_a_signed_token_with_no_record_is_rejected(self, client, session, db_session):
        """
        Correct signature, unknown jti. Either the secret leaked and tokens are
        being forged, or the record was purged -- neither should be honoured.
        """
        db_session.query(RefreshToken).delete()
        db_session.commit()
        assert refresh_via_cookie(client).status_code == 401

    def test_an_access_token_cannot_be_used_to_refresh(self, client, session):
        access = session.json()["access_token"]
        assert refresh_with_token(client, access).status_code == 401

    def test_garbage_is_rejected(self, client):
        assert refresh_with_token(client, "not.a.token").status_code == 401

    def test_no_token_at_all_is_rejected(self, client):
        assert client.post("/auth/refresh").status_code == 401


class TestDeletedUser:
    def test_tokens_die_with_the_account(self, client, session, db_session):
        user = db_session.query(User).filter_by(email=EMAIL).one()
        db_session.delete(user)
        db_session.commit()

        assert db_session.query(RefreshToken).count() == 0, "cascade did not fire"
        assert refresh_via_cookie(client).status_code == 401
