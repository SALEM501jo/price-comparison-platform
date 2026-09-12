"""
"Continue with Google" and "Sign in with Apple", end to end.

WHAT THESE TESTS ARE ACTUALLY GUARDING. Social sign-in is the one place where
an unauthenticated HTTP request is meant to end in a session, so every control
between the two is load-bearing:

  - the state token, which is the only proof a callback belongs to a sign-in
    this browser started (test class: state is single use, and Redis being
    down refuses rather than allows)
  - the linking rules, which decide whose account a provider identity opens
    (four branches, one of which is a documented account-takeover path)
  - the redirect, which must not carry a token and must not leave the site

No network is touched: the provider exchange and the id token verifier are
replaced at the point the router uses them, and the state store runs against
fakeredis. The verifier's own behaviour -- signatures, audience, nonce,
expiry -- is tested against real RS256 keys in test_oauth_tokens.py.
"""

from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient

from app.models.oauth_identity import OAuthIdentity
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.routers import oauth as oauth_router
from app.services import oauth_state
from app.services.oauth import ProviderIdentity
from app.services.oauth import providers as provider_registry
from app.services.oauth.flow import IdTokenInvalid, TokenExchangeFailed
from app.security.password import hash_password

APP_URL = "https://app.example.test"
API_URL = "https://api.example.test"
PASSWORD = "TestPass123"
GOOGLE_SUBJECT = "109384756102938475610"


@pytest.fixture
def state_store(monkeypatch):
    """
    The state store, against a real Redis protocol implementation.

    fakeredis rather than a stub, because GETDEL is the thing being relied on
    for single use: a dict-shaped fake would happily let a read-then-delete
    bug pass.

    TWO HANDLES ON ONE SERVER, and the split is the point. The application is
    async, so it gets the async client. The tests are synchronous -- they
    drive a TestClient -- so a test that wants to manipulate the store cannot
    await anything, and calling an async method without awaiting it silently
    produces a coroutine that never runs. That failure is invisible: the test
    reads as though it emptied the store, the store is untouched, and the
    assertion that follows is testing nothing. The sync handle shares the same
    FakeServer, so what it changes the application sees.
    """
    server = fakeredis.FakeServer()
    fake = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)

    async def get_fake():
        return fake

    monkeypatch.setattr(oauth_state, "get_cache", get_fake)
    return fakeredis.FakeRedis(server=server, decode_responses=True)


@pytest.fixture
def google(monkeypatch):
    settings = provider_registry.settings
    monkeypatch.setattr(settings, "google_client_id", "client-123.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "google_client_secret", "a-google-secret")
    monkeypatch.setattr(settings, "api_base_url", API_URL)
    monkeypatch.setattr(settings, "app_base_url", APP_URL)


@pytest.fixture
def apple(monkeypatch, google):
    settings = provider_registry.settings
    monkeypatch.setattr(settings, "apple_client_id", "com.example.web")
    monkeypatch.setattr(settings, "apple_team_id", "TEAM123456")
    monkeypatch.setattr(settings, "apple_key_id", "KEY7890123")
    monkeypatch.setattr(settings, "apple_private_key", "-----BEGIN PRIVATE KEY-----\\nx\\n-----END PRIVATE KEY-----")


def stub_provider(
    monkeypatch,
    *,
    subject: str = GOOGLE_SUBJECT,
    email: str | None = "shopper@example.com",
    email_verified: bool = True,
    exchange_error: Exception | None = None,
    verify_error: Exception | None = None,
) -> dict:
    """
    Replace the two calls that would leave the machine. Returns what they saw.

    Patched on the ROUTER module, which is where the names are bound -- the
    same discipline the mail tests use, and the reason patching httpx globally
    would be the wrong tool.
    """
    seen: dict = {}

    async def fake_exchange(provider, code, code_verifier):
        seen["code"] = code
        seen["code_verifier"] = code_verifier
        if exchange_error:
            raise exchange_error
        return "an.id.token"

    async def fake_verify(provider, id_token, nonce):
        seen["nonce"] = nonce
        if verify_error:
            raise verify_error
        return ProviderIdentity(
            provider=provider.id,
            subject=subject,
            email=email,
            email_verified=email_verified,
        )

    monkeypatch.setattr(oauth_router, "exchange_code", fake_exchange)
    monkeypatch.setattr(oauth_router, "verify_id_token", fake_verify)
    return seen


def begin(client, provider_id="google", **params):
    """Start a sign-in; return (state, nonce) as sent to the provider."""
    response = client.get(
        f"/auth/oauth/{provider_id}/start", params=params, follow_redirects=False
    )
    assert response.status_code == 302, response.text
    query = parse_qs(urlparse(response.headers["location"]).query)
    return query["state"][0], query["nonce"][0]


def finish(client, state, provider_id="google", code="an-auth-code"):
    return client.get(
        f"/auth/oauth/{provider_id}/callback",
        params={"code": code, "state": state},
        follow_redirects=False,
    )


def landing(response) -> dict:
    """The query the browser is sent back to the SPA with."""
    assert response.status_code == 303, response.text
    location = urlparse(response.headers["location"])
    assert f"{location.scheme}://{location.netloc}" == APP_URL
    assert location.path == "/oauth/callback"
    return {k: v[0] for k, v in parse_qs(location.query).items()}


# --- Which providers exist --------------------------------------------------


class TestTheProviderListIsHonest:
    """
    A button for a provider with no credentials leads to a 404 with nothing on
    screen to explain it. Apple in particular needs a paid developer account,
    so the site has to ship with Google alone.
    """

    def test_a_configured_provider_is_advertised(self, client, google):
        body = client.get("/auth/providers").json()
        assert body["providers"] == [
            {"id": "google", "start_url": "/auth/oauth/google/start"}
        ]

    def test_an_unconfigured_provider_is_not(self, client, google):
        ids = [p["id"] for p in client.get("/auth/providers").json()["providers"]]
        assert "apple" not in ids

    def test_both_appear_when_both_are_configured(self, client, apple):
        ids = [p["id"] for p in client.get("/auth/providers").json()["providers"]]
        assert ids == ["google", "apple"]

    def test_nothing_is_advertised_on_a_deployment_with_no_credentials(self, client):
        assert client.get("/auth/providers").json()["providers"] == []

    def test_starting_a_disabled_provider_is_a_404(self, client, google):
        assert client.get("/auth/oauth/apple/start").status_code == 404

    def test_calling_back_to_a_disabled_provider_is_a_404(self, client, google):
        response = client.get(
            "/auth/oauth/apple/callback", params={"code": "x", "state": "y"}
        )
        assert response.status_code == 404

    def test_an_invented_provider_is_a_404(self, client, google):
        assert client.get("/auth/oauth/facebook/start").status_code == 404


# --- Handing the browser to the provider ------------------------------------


class TestStartingASignIn:
    def test_the_browser_is_sent_to_google_with_everything_google_needs(
        self, client, google, state_store
    ):
        response = client.get("/auth/oauth/google/start", follow_redirects=False)
        assert response.status_code == 302
        url = urlparse(response.headers["location"])
        assert f"{url.scheme}://{url.netloc}{url.path}" == (
            "https://accounts.google.com/o/oauth2/v2/auth"
        )
        query = parse_qs(url.query)
        assert query["client_id"] == ["client-123.apps.googleusercontent.com"]
        assert query["redirect_uri"] == [f"{API_URL}/auth/oauth/google/callback"]
        assert query["response_type"] == ["code"]
        assert query["scope"] == ["openid email"]
        assert query["state"] and query["nonce"]

    def test_pkce_is_used_and_the_verifier_never_leaves_the_server(
        self, client, google, state_store
    ):
        """
        The challenge is what the provider sees; the verifier stays in Redis
        until the exchange, so a stolen authorization code cannot be redeemed
        by whoever stole it.
        """
        response = client.get("/auth/oauth/google/start", follow_redirects=False)
        query = parse_qs(urlparse(response.headers["location"]).query)
        assert query["code_challenge_method"] == ["S256"]
        challenge = query["code_challenge"][0]
        assert "code_verifier" not in query
        assert challenge and "=" not in challenge

    def test_the_verifier_reaches_the_exchange(
        self, client, google, state_store, monkeypatch
    ):
        seen = stub_provider(monkeypatch)
        state, _ = begin(client)
        finish(client, state)
        assert seen["code_verifier"]

    def test_the_nonce_sent_to_google_is_the_one_the_token_is_checked_against(
        self, client, google, state_store, monkeypatch
    ):
        seen = stub_provider(monkeypatch)
        state, nonce = begin(client)
        finish(client, state)
        assert seen["nonce"] == nonce


# --- The open redirect ------------------------------------------------------


class TestThePostLoginPathCannotLeaveTheSite:
    """
    `next` is supplied by whoever builds the sign-in link, so it is
    attacker-controlled. Reflected unchecked it is an open redirect on an
    authentication endpoint -- the most valuable kind, because the URL really
    does start on our domain and the victim really does sign in before landing
    on the attacker's "your session expired" page.
    """

    @pytest.mark.parametrize(
        "payload",
        [
            "//evil.com",
            "///evil.com",
            "/\\evil.com",
            "\\\\evil.com",
            "https://evil.com",
            "http://evil.com/path",
            "evil.com",
            "javascript:alert(1)",
            "/ok\nLocation: https://evil.com",
        ],
    )
    def test_a_hostile_next_becomes_the_home_page(
        self, client, google, state_store, monkeypatch, payload
    ):
        stub_provider(monkeypatch)
        state, _ = begin(client, next=payload)
        assert landing(finish(client, state))["next"] == "/"

    def test_an_ordinary_relative_path_survives(
        self, client, google, state_store, monkeypatch
    ):
        stub_provider(monkeypatch)
        state, _ = begin(client, next="/wishlist?sort=price")
        assert landing(finish(client, state))["next"] == "/wishlist?sort=price"

    def test_the_landing_page_is_always_on_our_own_origin(
        self, client, google, state_store, monkeypatch
    ):
        stub_provider(monkeypatch)
        state, _ = begin(client, next="//evil.com")
        response = finish(client, state)
        assert response.headers["location"].startswith(APP_URL + "/oauth/callback")


# --- The session ------------------------------------------------------------


class TestASuccessfulCallbackEstablishesASession:
    def test_the_refresh_cookie_is_set_on_the_redirect_itself(
        self, client, google, state_store, monkeypatch
    ):
        """
        THE REGRESSION THIS NAMES: a cookie written to FastAPI's injected
        Response object is only merged when the handler returns a body model.
        Set it there and return a RedirectResponse and the cookie silently
        vanishes -- the redirect works, the SPA's boot-time refresh 401s, and
        the user lands back on the login screen with nothing logged anywhere.
        """
        stub_provider(monkeypatch)
        state, _ = begin(client)
        response = finish(client, state)
        landing(response)
        assert "refresh_token" in response.cookies

    def test_the_cookie_is_httponly_and_scoped_to_auth(
        self, client, google, state_store, monkeypatch
    ):
        stub_provider(monkeypatch)
        state, _ = begin(client)
        header = finish(client, state).headers["set-cookie"]
        assert "HttpOnly" in header
        assert "Path=/auth" in header

    def test_no_token_is_put_in_the_url(
        self, client, google, state_store, monkeypatch
    ):
        """
        A URL is the leakiest place a credential can sit: access logs, browser
        history, and the Referer of the next request the page makes. The whole
        codebase keeps the access token out of storage; a token in a query
        string here would quietly undo that.
        """
        stub_provider(monkeypatch)
        state, _ = begin(client)
        response = finish(client, state)
        location = response.headers["location"]
        assert response.cookies["refresh_token"] not in location
        assert set(landing(response)) == {"next"}
        assert "token" not in location.lower()

    def test_the_cookie_actually_buys_an_access_token(
        self, client, google, state_store, monkeypatch
    ):
        """The proof that the sign-in is complete: /auth/refresh accepts it."""
        stub_provider(monkeypatch)
        state, _ = begin(client)
        finish(client, state)
        refreshed = client.post("/auth/refresh")
        assert refreshed.status_code == 200
        assert refreshed.json()["access_token"]

    def test_a_user_who_cancels_lands_on_the_error_page_not_a_stack_trace(
        self, client, google, state_store, monkeypatch
    ):
        stub_provider(monkeypatch)
        state, _ = begin(client)
        response = client.get(
            "/auth/oauth/google/callback",
            params={"error": "access_denied", "state": state},
            follow_redirects=False,
        )
        assert landing(response)["error"] == "provider_error"


# --- The four linking branches ----------------------------------------------


class TestLinkingAProviderToALocalAccount:
    def test_a_new_visitor_gets_an_account_with_no_password(
        self, client, db_session, google, state_store, monkeypatch
    ):
        stub_provider(monkeypatch, email="newcomer@example.com")
        state, _ = begin(client)
        landing(finish(client, state))

        user = db_session.query(User).filter(User.email == "newcomer@example.com").one()
        assert user.password_hash is None
        # Provider-asserted, so no verification mail is sent: that would be
        # noise reading as phishing to someone who just proved control of the
        # mailbox through Google.
        assert user.email_verified_at is not None
        identity = db_session.query(OAuthIdentity).one()
        assert identity.provider == "google"
        assert identity.provider_subject == GOOGLE_SUBJECT
        assert identity.user_id == user.id

    def test_an_existing_verified_account_is_linked_and_keeps_its_password(
        self, client, db_session, google, state_store, monkeypatch
    ):
        """Both parties independently proved control of the same mailbox."""
        original = hash_password(PASSWORD)
        user = User(
            email="regular@example.com",
            password_hash=original,
            # A real datetime, not the string that looks like one: the column
            # is DateTime(timezone=True) and SQLite's driver rejects a string
            # outright rather than coercing it.
            email_verified_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        db_session.add(user)
        db_session.commit()

        stub_provider(monkeypatch, email="regular@example.com")
        state, _ = begin(client)
        landing(finish(client, state))

        db_session.refresh(user)
        assert user.password_hash == original
        assert db_session.query(OAuthIdentity).one().user_id == user.id
        assert db_session.query(User).count() == 1

    def test_linking_to_an_unverified_account_evicts_whoever_set_its_password(
        self, client, db_session, google, state_store, monkeypatch
    ):
        """
        THE ACCOUNT TAKEOVER THIS PREVENTS. An attacker registers
        victim@gmail.com with a password of their choosing and waits. They
        never had to open that mailbox, so the account sits unverified. When
        the real owner later clicks "Continue with Google", a naive link would
        join their identity to the attacker's row -- and the attacker's
        password would still open it, with the victim seeing nothing.

        So the password is cleared and every existing session is revoked:
        Google has just proved who owns the mailbox, and the person who typed
        a password into it has proved nothing.
        """
        registered = client.post(
            "/auth/register",
            json={"email": "victim@example.com", "password": PASSWORD},
        )
        assert registered.status_code == 201
        user = db_session.query(User).filter(User.email == "victim@example.com").one()
        assert user.email_verified_at is None
        attacker_jtis = [
            record.jti
            for record in db_session.query(RefreshToken).filter_by(user_id=user.id)
        ]
        assert attacker_jtis

        stub_provider(monkeypatch, email="victim@example.com")
        state, _ = begin(client)
        landing(finish(client, state))

        db_session.expire_all()
        user = db_session.query(User).filter(User.email == "victim@example.com").one()
        assert user.password_hash is None
        assert user.email_verified_at is not None
        for jti in attacker_jtis:
            record = db_session.query(RefreshToken).filter_by(jti=jti).one()
            assert record.revoked_at is not None, "the attacker's session survived"

        # And the password they chose no longer opens the account.
        rejected = client.post(
            "/auth/login",
            json={"email": "victim@example.com", "password": PASSWORD},
        )
        assert rejected.status_code == 401

    def test_an_unverified_provider_email_creates_and_links_nothing(
        self, client, db_session, google, state_store, monkeypatch
    ):
        """
        Without the provider vouching for the mailbox, the address is just a
        string somebody typed -- and typing "alice@gmail.com" is not evidence
        of owning it.
        """
        stub_provider(
            monkeypatch, email="unverified@example.com", email_verified=False
        )
        state, _ = begin(client)
        response = finish(client, state)

        assert landing(response)["error"] == "email_unverified"
        assert "refresh_token" not in response.cookies
        assert db_session.query(User).count() == 0
        assert db_session.query(OAuthIdentity).count() == 0

    def test_a_provider_that_sends_no_email_at_all_creates_nothing(
        self, client, db_session, google, state_store, monkeypatch
    ):
        stub_provider(monkeypatch, email=None, email_verified=True)
        state, _ = begin(client)
        assert landing(finish(client, state))["error"] == "email_unverified"
        assert db_session.query(User).count() == 0


class TestTheSubjectIsTheIdentityNotTheAddress:
    def test_a_second_sign_in_reuses_the_account_even_if_the_address_changed(
        self, client, db_session, google, state_store, monkeypatch
    ):
        """
        Apple's private relay changes when a user unlinks and relinks, and a
        corporate address outlives its owner. Matching on the address the
        second time would either fork the account or hand it to a stranger.
        """
        stub_provider(monkeypatch, email="first@example.com")
        state, _ = begin(client)
        landing(finish(client, state))
        first = db_session.query(User).one()

        stub_provider(monkeypatch, email="relay-changed@privaterelay.appleid.com")
        state, _ = begin(client)
        landing(finish(client, state))

        assert db_session.query(User).count() == 1
        assert db_session.query(User).one().id == first.id
        assert db_session.query(OAuthIdentity).count() == 1


# --- The state token --------------------------------------------------------


class TestTheStateTokenIsTheOnlyProofTheCallbackIsOurs:
    def test_a_callback_with_no_state_is_refused(
        self, client, db_session, google, state_store, monkeypatch
    ):
        stub_provider(monkeypatch)
        response = client.get(
            "/auth/oauth/google/callback",
            params={"code": "an-auth-code"},
            follow_redirects=False,
        )
        assert landing(response)["error"] == "state_invalid"
        assert db_session.query(User).count() == 0

    def test_a_state_we_never_minted_is_refused(
        self, client, db_session, google, state_store, monkeypatch
    ):
        stub_provider(monkeypatch)
        response = finish(client, "Zm9yZ2VkLXN0YXRlLXZhbHVlLTAwMDAwMDAw")
        assert landing(response)["error"] == "state_invalid"
        assert db_session.query(User).count() == 0

    def test_the_same_state_cannot_be_used_twice(
        self, client, google, state_store, monkeypatch
    ):
        """
        Without GETDEL the state would stay valid for its whole TTL and the
        same callback URL would keep working -- which is exactly the URL an
        attacker hands to a victim.
        """
        stub_provider(monkeypatch)
        state, _ = begin(client)
        assert "error" not in landing(finish(client, state))

        replayed = finish(client, state)
        assert landing(replayed)["error"] == "state_invalid"
        assert "refresh_token" not in replayed.cookies

    def test_a_state_minted_for_google_is_refused_at_apples_callback(
        self, client, apple, state_store, monkeypatch
    ):
        stub_provider(monkeypatch)
        state, _ = begin(client, "google")
        response = client.post(
            "/auth/oauth/apple/callback",
            data={"code": "an-auth-code", "state": state},
            follow_redirects=False,
        )
        assert landing(response)["error"] == "state_invalid"

    def test_an_expired_state_is_refused(
        self, client, google, state_store, monkeypatch
    ):
        stub_provider(monkeypatch)
        state, _ = begin(client)
        state_store.flushall()  # what expiry looks like from here
        assert landing(finish(client, state))["error"] == "state_invalid"


class TestAnUnreachableRedisRefusesTheSignInRatherThanAllowingIt:
    """
    THE VULNERABILITY THIS NAMES: login CSRF. Both neighbouring Redis users --
    app/services/cache.py and the rate limiter -- deliberately carry on when
    Redis is down, so "keep working during an outage" is the habit an
    implementer would copy here. Copying it means accepting a callback nobody
    can prove we started: the attacker completes a Google authorization
    themselves and sends the resulting callback URL to a victim, who is then
    silently signed in as the ATTACKER. Every search, wishlist entry, price
    alert and contact message they make afterwards lands in the attacker's
    account, and nothing on screen shows it.

    Password login is untouched by a Redis outage, so failing closed here is a
    partial outage, not a total one.
    """

    @pytest.fixture
    def redis_down(self, monkeypatch):
        async def refuse():
            raise ConnectionError("Connection refused")

        monkeypatch.setattr(oauth_state, "get_cache", refuse)

    def test_the_callback_is_refused_not_accepted(
        self, client, db_session, google, redis_down, monkeypatch
    ):
        stub_provider(monkeypatch)
        response = finish(client, "c3RhdGUtdGhhdC1sb29rcy1yaWdodC0wMDAw")
        assert landing(response)["error"] == "unavailable"
        assert "refresh_token" not in response.cookies
        assert db_session.query(User).count() == 0
        assert db_session.query(RefreshToken).count() == 0

    def test_starting_a_sign_in_is_refused_too(self, client, google, redis_down):
        """
        Nothing to start: without a stored state there would be no way to
        recognise the callback, so the button has to fail visibly rather than
        producing a sign-in that cannot be checked.
        """
        response = client.get("/auth/oauth/google/start", follow_redirects=False)
        assert landing(response)["error"] == "unavailable"


# --- What the provider says -------------------------------------------------


class TestAProviderResponseThatFailsVerification:
    def test_a_refused_code_exchange_creates_no_account(
        self, client, db_session, google, state_store, monkeypatch
    ):
        stub_provider(monkeypatch, exchange_error=TokenExchangeFailed("nope"))
        state, _ = begin(client)
        response = finish(client, state)
        assert landing(response)["error"] == "provider_error"
        assert db_session.query(User).count() == 0

    def test_an_unverifiable_id_token_creates_no_account(
        self, client, db_session, google, state_store, monkeypatch
    ):
        stub_provider(monkeypatch, verify_error=IdTokenInvalid("bad signature"))
        state, _ = begin(client)
        response = finish(client, state)
        assert landing(response)["error"] == "provider_error"
        assert "refresh_token" not in response.cookies
        assert db_session.query(User).count() == 0


# --- Apple's cross-site POST ------------------------------------------------


class TestApplePostsItsCallbackAsAForm:
    """
    Apple mandates response_mode=form_post the moment any scope is requested,
    so the parameters arrive as form fields on a CROSS-SITE POST. No
    SameSite=Lax cookie is sent with that request, which is precisely why the
    state token lives in Redis instead of in a cookie: a cookie-based state
    would work for Google and fail for Apple, and only for Apple.
    """

    def test_the_authorization_url_asks_for_form_post(
        self, client, apple, state_store
    ):
        response = client.get("/auth/oauth/apple/start", follow_redirects=False)
        query = parse_qs(urlparse(response.headers["location"]).query)
        assert query["response_mode"] == ["form_post"]
        # Apple rejects code_challenge outright, so PKCE is not attempted.
        assert "code_challenge" not in query

    def test_a_posted_callback_signs_the_user_in(
        self, client, db_session, apple, state_store, monkeypatch
    ):
        stub_provider(monkeypatch, subject="001234.abc.5678", email="ios@example.com")
        state, _ = begin(client, "apple")
        response = client.post(
            "/auth/oauth/apple/callback",
            data={"code": "an-auth-code", "state": state},
            follow_redirects=False,
        )
        # 303 specifically: only 303 guarantees the browser follows a POST
        # with a GET rather than re-posting the form to the SPA.
        assert response.status_code == 303
        assert "refresh_token" in response.cookies
        assert db_session.query(OAuthIdentity).one().provider == "apple"


# --- The account with no password -------------------------------------------


class TestLoginAgainstAnAccountThatHasNoPassword:
    """
    Making password_hash nullable put a None where bcrypt expects a string.
    Measured before the guard existed: password.py raised AttributeError, the
    global handler turned it into HTTP 500, and it came back in ~0ms against
    ~240ms for a genuine wrong password. Status code and timing both announced
    "this address exists and signs in with Google" -- which is worse than
    plain account enumeration, because it names the provider to phish.
    """

    @pytest.fixture
    def oauth_only_user(self, db_session):
        user = User(email="google-only@example.com", password_hash=None)
        db_session.add(user)
        db_session.commit()
        return user

    def test_it_is_a_401_and_not_a_500(self, client, oauth_only_user):
        response = client.post(
            "/auth/login",
            json={"email": "google-only@example.com", "password": PASSWORD},
        )
        assert response.status_code == 401

    def test_it_is_indistinguishable_from_an_address_nobody_registered(
        self, client, oauth_only_user
    ):
        no_such_account = client.post(
            "/auth/login",
            json={"email": "nobody@example.com", "password": PASSWORD},
        )
        no_password = client.post(
            "/auth/login",
            json={"email": "google-only@example.com", "password": PASSWORD},
        )
        assert no_such_account.status_code == no_password.status_code == 401
        assert no_such_account.json() == no_password.json()

    def test_an_ordinary_login_still_works(self, client, db_session):
        client.post(
            "/auth/register", json={"email": "normal@example.com", "password": PASSWORD}
        )
        response = client.post(
            "/auth/login", json={"email": "normal@example.com", "password": PASSWORD}
        )
        assert response.status_code == 200


class TestTheCallbackMustComeFromTheBrowserThatStartedIt:
    """
    LOGIN CSRF, the attack a state token ALONE does not stop.

    The state is a server-side value, so any browser holding a live one
    satisfies it. That is enough to prove the sign-in is ours; it proves
    nothing about WHOSE it is. The gap is executable against a perfectly
    healthy Redis:

        the attacker calls /start in their own browser, consents as their OWN
        Google account, and captures the callback URL WITHOUT following it.
        They send it to a victim. Everything downstream then verifies
        honestly -- the code redeems, the id token's signature and nonce are
        genuine -- and the victim's browser is handed a refresh cookie for the
        ATTACKER's user. The victim is silently signed in as someone else,
        including when they were already signed in as themselves, and every
        search, wishlist entry, price alert and merchant contact they make
        afterwards lands in an account the attacker reads at will.

    WHY THE STATE TESTS ABOVE DO NOT CATCH IT, and this is the whole reason
    this class exists separately: every one of them drives begin() and
    finish() on the SAME TestClient, so they would pass byte-identically if
    the two halves came from two different browsers. A one-client test cannot
    see this bug. These use two.
    """

    def _second_browser(self, client):
        """A client with its own cookie jar, sharing the app and the database."""
        return TestClient(client.app)

    def test_a_callback_replayed_into_another_browser_is_refused(
        self, client, db_session, google, state_store, monkeypatch
    ):
        """The attack itself, start to finish."""
        stub_provider(monkeypatch)
        state, _ = begin(client)  # the attacker's browser holds the binding

        victim = self._second_browser(client)
        response = victim.get(
            "/auth/oauth/google/callback",
            params={"code": "an-auth-code", "state": state},
            follow_redirects=False,
        )

        assert landing(response)["error"] == "state_invalid"
        # No session was created for anybody, in either browser.
        assert "refresh_token" not in response.cookies
        assert db_session.query(User).count() == 0
        assert db_session.query(RefreshToken).count() == 0

    def test_the_refusal_is_indistinguishable_from_an_unknown_state(
        self, client, google, state_store, monkeypatch
    ):
        """
        A prober must not learn WHICH half they got wrong. Two different
        answers here would tell an attacker that their captured state is still
        live and only the cookie is missing -- exactly the hint that makes it
        worth hunting for a way to plant one.
        """
        stub_provider(monkeypatch)
        state, _ = begin(client)

        wrong_browser = landing(
            self._second_browser(client).get(
                "/auth/oauth/google/callback",
                params={"code": "an-auth-code", "state": state},
                follow_redirects=False,
            )
        )
        never_minted = landing(finish(client, "c3RhdGUtdGhhdC1sb29rcy1yaWdodC0wMDAw"))
        assert wrong_browser == never_minted

    def test_a_stale_binding_does_not_match_a_newer_sign_in(
        self, client, db_session, google, state_store, monkeypatch
    ):
        """
        Starting a second sign-in replaces the binding, so the FIRST state can
        no longer be completed.

        A DELIBERATE TRADE-OFF, recorded here so it is not later mistaken for a
        bug: one cookie means one attempt in flight per browser, so someone who
        opens the Google button in two tabs can only finish the newer one. The
        alternative -- a set of live bindings per browser -- widens the very
        window this control exists to close, for a case that costs the user one
        click to retry.
        """
        stub_provider(monkeypatch)
        first_state, _ = begin(client)
        begin(client)  # a second attempt, overwriting the binding

        assert landing(finish(client, first_state))["error"] == "state_invalid"
        assert db_session.query(User).count() == 0

    def test_the_same_browser_still_signs_in(
        self, client, db_session, google, state_store, monkeypatch
    ):
        """The control must not cost the ordinary case anything."""
        stub_provider(monkeypatch)
        state, _ = begin(client)
        response = finish(client, state)

        assert "next" in landing(response)
        assert "refresh_token" in response.cookies
        assert db_session.query(User).count() == 1

    def test_the_binding_is_spent_so_a_failed_attempt_does_not_block_a_retry(
        self, client, db_session, google, state_store, monkeypatch
    ):
        """
        A binding left behind after a REFUSED callback would be matched against
        the next attempt's state, which it cannot satisfy -- locking the user
        out with the debris of the attempt that just failed. So it is cleared
        on failure as well as on success.
        """
        stub_provider(monkeypatch, verify_error=IdTokenInvalid("bad signature"))
        state, _ = begin(client)
        assert landing(finish(client, state))["error"] == "provider_error"

        stub_provider(monkeypatch)
        state, _ = begin(client)
        assert "refresh_token" in finish(client, state).cookies
        assert db_session.query(User).count() == 1

    def test_apples_cross_site_post_still_completes(
        self, client, db_session, apple, state_store, monkeypatch
    ):
        """
        Apple posts its callback from its own origin, so the binding cookie
        must be SameSite=None or it is never sent and EVERY Apple sign-in is
        refused -- the control breaking the provider rather than protecting it.
        TestClient does not enforce SameSite, so this pins that the POST path
        works end to end; the attribute itself is asserted separately.
        """
        stub_provider(monkeypatch)
        state, _ = begin(client, "apple")
        response = client.post(
            "/auth/oauth/apple/callback",
            data={"code": "an-auth-code", "state": state},
            follow_redirects=False,
        )
        assert "next" in landing(response)
        assert db_session.query(User).count() == 1

    def test_the_binding_cookie_is_httponly_and_scoped(
        self, client, google, state_store
    ):
        header = client.get(
            "/auth/oauth/google/start", follow_redirects=False
        ).headers["set-cookie"]
        assert "oauth_binding=" in header
        assert "HttpOnly" in header
        assert "Path=/auth/oauth" in header

    def test_the_binding_is_not_the_state_itself(self, client, google, state_store):
        """
        Two different secrets on purpose. The state travels through the
        provider, through browser history and through access logs; reusing it
        as the cookie would mean anything that leaked one also leaked the proof
        of whose browser this was.
        """
        response = client.get("/auth/oauth/google/start", follow_redirects=False)
        state = parse_qs(urlparse(response.headers["location"]).query)["state"][0]
        assert response.cookies["oauth_binding"] != state


class TestOneMailboxIsOneAccountWhateverTheCase:
    """
    THE SPLIT THIS CLOSES, and why it was a security bug rather than a tidiness
    one: registration and login matched `User.email == body.email`
    (case-SENSITIVE) while linking matched `func.lower(User.email) == email`
    (case-insensitive). So one real mailbox could hold two rows differing only
    in case, and signing in with a provider cleared the password on only one of
    them -- leaving an attacker who had registered `Victim@example.com` with a
    working credential on the victim's mailbox after the very event that was
    supposed to evict them.
    """

    def test_a_mixed_case_registration_is_the_same_account_as_its_lowercase_form(
        self, client, db_session
    ):
        client.post(
            "/auth/register",
            json={"email": "Shopper@Example.COM", "password": PASSWORD},
        )
        second = client.post(
            "/auth/register",
            json={"email": "shopper@example.com", "password": PASSWORD},
        )
        assert second.status_code == 409, second.text
        assert db_session.query(User).count() == 1

    def test_login_ignores_the_case_that_was_typed_at_signup(self, client):
        client.post(
            "/auth/register",
            json={"email": "Shopper@Example.COM", "password": PASSWORD},
        )
        response = client.post(
            "/auth/login",
            json={"email": "shopper@example.com", "password": PASSWORD},
        )
        assert response.status_code == 200

    def test_a_provider_links_to_the_mixed_case_account_and_evicts_its_password(
        self, client, db_session, google, state_store, monkeypatch
    ):
        """
        The takeover branch has to reach the row no matter how it was spelled.
        Registering with a capital and never confirming the address must not
        put the account out of the eviction's reach.
        """
        client.post(
            "/auth/register",
            json={"email": "Victim@Example.com", "password": PASSWORD},
        )
        stub_provider(monkeypatch, email="victim@example.com")
        state, _ = begin(client)
        landing(finish(client, state))

        assert db_session.query(User).count() == 1
        user = db_session.query(User).one()
        assert user.password_hash is None
        assert user.email_verified_at is not None
        assert db_session.query(OAuthIdentity).one().user_id == user.id
