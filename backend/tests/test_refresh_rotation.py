"""
Refresh token rotation and replay detection.

These cover the claim the original docstring made but the code did not honour:
that a refresh token can be revoked. The headline case is replay -- a stolen
token being used alongside the real user's, which rotation is specifically
designed to expose.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.refresh_token import RefreshToken
from app.models.user import User

PASSWORD = "TestPass123"
EMAIL = "rotate@example.com"


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
def tokens(client):
    response = client.post(
        "/auth/register", json={"email": EMAIL, "password": PASSWORD}
    )
    assert response.status_code == 201, response.text
    return response.json()


def refresh(client, token):
    return client.post("/auth/refresh", json={"refresh_token": token})


class TestIssuing:
    def test_registration_records_the_refresh_token(self, client, tokens, db_session):
        assert db_session.query(RefreshToken).count() == 1

    def test_only_the_id_is_stored_never_the_token(self, client, tokens, db_session):
        """A database dump must not hand over usable credentials."""
        record = db_session.query(RefreshToken).one()
        assert record.jti not in tokens["refresh_token"]
        assert len(record.jti) == 36  # a uuid4, not the token

    def test_login_issues_a_separate_token(self, client, tokens, db_session):
        client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
        assert db_session.query(RefreshToken).count() == 2


class TestRotation:
    def test_refresh_returns_a_new_refresh_token(self, client, tokens):
        response = refresh(client, tokens["refresh_token"])
        assert response.status_code == 200, response.text
        assert response.json()["refresh_token"] != tokens["refresh_token"]

    def test_the_used_token_is_revoked(self, client, tokens, db_session):
        refresh(client, tokens["refresh_token"])
        used = db_session.query(RefreshToken).order_by(RefreshToken.id).first()
        assert used.revoked_at is not None

    def test_rotation_links_old_to_new(self, client, tokens, db_session):
        refresh(client, tokens["refresh_token"])
        records = db_session.query(RefreshToken).order_by(RefreshToken.id).all()
        assert len(records) == 2
        assert records[0].replaced_by_jti == records[1].jti

    def test_the_new_token_works(self, client, tokens):
        rotated = refresh(client, tokens["refresh_token"]).json()["refresh_token"]
        assert refresh(client, rotated).status_code == 200

    def test_a_chain_of_refreshes_keeps_working(self, client, tokens):
        token = tokens["refresh_token"]
        for _ in range(5):
            response = refresh(client, token)
            assert response.status_code == 200, response.text
            token = response.json()["refresh_token"]


class TestReplayDetection:
    def test_reusing_a_spent_token_is_rejected(self, client, tokens):
        refresh(client, tokens["refresh_token"])
        replay = refresh(client, tokens["refresh_token"])
        assert replay.status_code == 401

    def test_replay_revokes_the_whole_chain(self, client, tokens, db_session):
        """
        The scenario: an attacker steals the token and refreshes. The real user
        then refreshes with the token they still hold, which is now spent. We
        cannot tell which party is which, so BOTH are logged out.
        """
        stolen = tokens["refresh_token"]
        attacker = refresh(client, stolen).json()["refresh_token"]

        # The real user presents the original -- already used.
        assert refresh(client, stolen).status_code == 401

        # The attacker's freshly rotated token must die with the chain.
        assert refresh(client, attacker).status_code == 401

        live = (
            db_session.query(RefreshToken)
            .filter(RefreshToken.revoked_at.is_(None))
            .count()
        )
        assert live == 0, "a token survived the reuse response"

    def test_replay_does_not_affect_other_users(self, client, tokens, db_session):
        other = client.post(
            "/auth/register", json={"email": "bystander@example.com", "password": PASSWORD}
        ).json()

        refresh(client, tokens["refresh_token"])
        refresh(client, tokens["refresh_token"])  # trigger the reuse response

        assert refresh(client, other["refresh_token"]).status_code == 200


class TestLogout:
    def test_logout_revokes_every_token(self, client, tokens, db_session):
        client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})

        response = client.post(
            "/auth/logout",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert response.status_code == 204, response.text

        live = (
            db_session.query(RefreshToken)
            .filter(RefreshToken.revoked_at.is_(None))
            .count()
        )
        assert live == 0

    def test_refresh_fails_after_logout(self, client, tokens):
        client.post(
            "/auth/logout",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert refresh(client, tokens["refresh_token"]).status_code == 401

    def test_logout_requires_authentication(self, client):
        assert client.post("/auth/logout").status_code == 401


class TestForgedTokens:
    def test_a_signed_token_with_no_record_is_rejected(self, client, tokens, db_session):
        """
        Correct signature, unknown jti. Either the secret leaked and tokens are
        being forged, or the record was purged -- neither should be honoured.
        """
        db_session.query(RefreshToken).delete()
        db_session.commit()
        assert refresh(client, tokens["refresh_token"]).status_code == 401

    def test_an_access_token_cannot_be_used_to_refresh(self, client, tokens):
        assert refresh(client, tokens["access_token"]).status_code == 401

    def test_garbage_is_rejected(self, client):
        assert refresh(client, "not.a.token").status_code == 401


class TestDeletedUser:
    def test_tokens_die_with_the_account(self, client, tokens, db_session):
        user = db_session.query(User).filter_by(email=EMAIL).one()
        db_session.delete(user)
        db_session.commit()

        assert db_session.query(RefreshToken).count() == 0, "cascade did not fire"
        assert refresh(client, tokens["refresh_token"]).status_code == 401
