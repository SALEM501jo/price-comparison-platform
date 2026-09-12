"""
Id token verification: the one check that decides who somebody is.

Everything else in social sign-in arranges for a provider to hand us a signed
statement. This is where that statement is believed, so every way of forging
one has to be refused here or the whole feature is "tell us your user id".

The keys are generated in-process and the JWKS fetch is replaced, so nothing
here touches the network -- and unlike a mocked verifier, the real RS256
signature path runs.
"""

import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives import serialization
from jwt.algorithms import RSAAlgorithm

from app.services.oauth import flow, providers
from app.services.oauth.flow import IdTokenInvalid
from app.services.oauth.providers import Provider

AUDIENCE = "client-123.apps.googleusercontent.com"
ISSUER = "https://accounts.google.com"
KID = "test-key-1"
NONCE = "the-nonce-from-our-start-request"

# One key pair for the whole module: RSA generation is slow enough that doing
# it per test would dominate the suite's runtime.
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwks(key, kid=KID) -> dict:
    entry = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    entry.update({"kid": kid, "alg": "RS256", "use": "sig"})
    return {"keys": [entry]}


def _provider() -> Provider:
    return Provider(
        id="google",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        jwks_url="https://jwks.test/certs",
        issuers=(ISSUER,),
        scope="openid email",
        client_id=AUDIENCE,
        client_secret=lambda: "secret",
        uses_pkce=True,
    )


def _id_token(key=_KEY, kid=KID, **overrides) -> str:
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "1093847",
        "iat": now,
        "exp": now + 300,
        "nonce": NONCE,
        "email": "shopper@example.com",
        "email_verified": True,
    }
    claims.update(overrides)
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})


@pytest.fixture
def served_jwks(monkeypatch):
    """Serve a key set to the verifier, and count how often it is asked."""
    state = {"calls": 0, "document": _jwks(_KEY)}

    async def fetch(url):
        state["calls"] += 1
        return state["document"]

    flow.reset_jwks_cache()
    monkeypatch.setattr(flow, "_fetch_jwks", fetch)
    yield state
    flow.reset_jwks_cache()


class TestAGenuineTokenIsAccepted:
    async def test_claims_come_back(self, served_jwks):
        identity = await flow.verify_id_token(_provider(), _id_token(), NONCE)
        assert identity.subject == "1093847"
        assert identity.email == "shopper@example.com"
        assert identity.email_verified is True

    async def test_the_key_set_is_cached_between_tokens(self, served_jwks):
        """
        Two sign-ins must not be two outbound requests to the provider.
        """
        await flow.verify_id_token(_provider(), _id_token(), NONCE)
        await flow.verify_id_token(_provider(), _id_token(), NONCE)
        assert served_jwks["calls"] == 1


class TestEveryForgeryIsRefused:
    async def test_a_signature_from_another_key_is_rejected(self, served_jwks):
        """
        The whole feature reduces to this line: anyone can mint an unsigned
        JWT claiming to be anybody, so only the provider's own signature
        makes the claim mean anything.
        """
        token = _id_token(key=_OTHER_KEY)
        with pytest.raises(IdTokenInvalid):
            await flow.verify_id_token(_provider(), token, NONCE)

    async def test_a_token_for_another_audience_is_rejected(self, served_jwks):
        """
        Google issues id tokens to every client that registers. Without the
        aud check, any of them could sign in as our users with a token their
        own app legitimately received.
        """
        token = _id_token(aud="someone-elses-app.apps.googleusercontent.com")
        with pytest.raises(IdTokenInvalid):
            await flow.verify_id_token(_provider(), token, NONCE)

    async def test_a_token_from_another_issuer_is_rejected(self, served_jwks):
        token = _id_token(iss="https://accounts.evil.example")
        with pytest.raises(IdTokenInvalid):
            await flow.verify_id_token(_provider(), token, NONCE)

    async def test_an_expired_token_is_rejected(self, served_jwks):
        now = int(time.time())
        token = _id_token(iat=now - 7200, exp=now - 3600)
        with pytest.raises(IdTokenInvalid):
            await flow.verify_id_token(_provider(), token, NONCE)

    async def test_a_token_from_a_different_sign_in_is_rejected(self, served_jwks):
        """
        A perfectly valid token whose nonce belongs to another attempt is a
        replay: the nonce is what ties the token to the start request this
        browser actually made.
        """
        token = _id_token(nonce="a-nonce-we-never-issued")
        with pytest.raises(IdTokenInvalid):
            await flow.verify_id_token(_provider(), token, NONCE)

    async def test_a_token_with_no_nonce_is_rejected(self, served_jwks):
        claims_without_nonce = _id_token(nonce=None)
        with pytest.raises(IdTokenInvalid):
            await flow.verify_id_token(_provider(), claims_without_nonce, NONCE)

    async def test_a_token_with_no_subject_is_rejected(self, served_jwks):
        token = _id_token(sub=None)
        with pytest.raises(IdTokenInvalid):
            await flow.verify_id_token(_provider(), token, NONCE)

    async def test_a_token_with_no_key_id_is_rejected(self, served_jwks):
        token = jwt.encode({"sub": "x"}, _KEY, algorithm="RS256")
        with pytest.raises(IdTokenInvalid):
            await flow.verify_id_token(_provider(), token, NONCE)


class TestAnUnknownKeyIdCannotBeUsedToHammerTheProvider:
    async def test_it_does_not_refetch_immediately(self, served_jwks):
        """
        A kid we have not seen normally means the provider rotated keys, so a
        refetch is the right reflex. It is also free for an attacker to
        provoke: a token with a random kid costs them nothing and would cost
        us one outbound request each. The floor is what stops us being an
        amplifier pointed at Google.
        """
        token = _id_token(kid="a-kid-that-does-not-exist")
        with pytest.raises(IdTokenInvalid):
            await flow.verify_id_token(_provider(), token, NONCE)
        assert served_jwks["calls"] == 1

    async def test_it_does_refetch_once_the_floor_has_passed(
        self, served_jwks, monkeypatch
    ):
        """A real rotation must still be picked up, or sign-in breaks for good."""
        monkeypatch.setattr(flow, "JWKS_MIN_REFETCH_SECONDS", 0)
        rotated_kid = "rotated-key"
        await flow.verify_id_token(_provider(), _id_token(), NONCE)

        served_jwks["document"] = _jwks(_KEY, kid=rotated_kid)
        identity = await flow.verify_id_token(
            _provider(), _id_token(kid=rotated_kid), NONCE
        )
        assert identity.subject == "1093847"
        assert served_jwks["calls"] == 2


class TestAppleSendsEmailVerifiedAsAString:
    """
    Apple sends "true"/"false" as strings where Google sends booleans, and
    bool("false") is True -- which would turn Apple's explicit denial that it
    has verified an address into an approval, on the exact branch that creates
    and links accounts.
    """

    def test_the_string_true_counts_as_verified(self):
        assert flow._email_verified("true") is True

    def test_the_string_false_does_not(self):
        assert flow._email_verified("false") is False

    def test_the_boolean_forms_still_work(self):
        assert flow._email_verified(True) is True
        assert flow._email_verified(False) is False

    def test_an_absent_claim_is_not_verified(self):
        assert flow._email_verified(None) is False


class TestApplesClientSecretIsGeneratedNotPasted:
    """
    Apple has no static client secret: it is an ES256 JWT signed with the .p8
    key. A pasted one expires -- silently, months after the deploy that
    worked, with no configuration change to blame.
    """

    @pytest.fixture
    def apple_configured(self, monkeypatch):
        key = ec.generate_private_key(ec.SECP256R1())
        pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()
        settings = providers.settings
        monkeypatch.setattr(settings, "apple_client_id", "com.example.web")
        monkeypatch.setattr(settings, "apple_team_id", "TEAM123456")
        monkeypatch.setattr(settings, "apple_key_id", "KEY7890123")
        # Written with literal backslash-n, which is how a PEM survives an
        # environment variable on every deploy platform this would run on.
        monkeypatch.setattr(settings, "apple_private_key", pem.replace("\n", "\\n"))
        return key

    def test_it_is_a_signed_jwt_apple_would_accept(self, apple_configured):
        secret = providers._apple_client_secret()
        claims = jwt.decode(
            secret,
            apple_configured.public_key(),
            algorithms=["ES256"],
            audience="https://appleid.apple.com",
        )
        assert claims["iss"] == "TEAM123456"
        assert claims["sub"] == "com.example.web"
        assert claims["exp"] > claims["iat"]

    def test_the_key_id_is_in_the_header(self, apple_configured):
        header = jwt.get_unverified_header(providers._apple_client_secret())
        assert header["kid"] == "KEY7890123"
        assert header["alg"] == "ES256"

    def test_a_single_line_pem_is_restored(self, apple_configured):
        """
        Left with literal backslash-n it is not a PEM at all, and the only
        symptom is every Apple sign-in failing at signing time.
        """
        assert providers.settings.apple_private_key_pem.startswith("-----BEGIN")
        assert "\\n" not in providers.settings.apple_private_key_pem
