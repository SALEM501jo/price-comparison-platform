"""
The two provider round trips: exchanging the code, and proving the id token.

WHAT IS ACTUALLY BEING DEFENDED HERE. The id token is the only thing that
says who signed in. If it is accepted without a real signature check, anyone
can mint one for any address and become that user -- so this module never
decodes with verify_signature off, never asks the token which algorithm to
use, and never falls back to the provider's /userinfo endpoint, which is an
ordinary HTTP response and proves nothing about who authorized what.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import time
from dataclasses import dataclass

import httpx
import jwt

from app.services.oauth.providers import Provider

logger = logging.getLogger("app.oauth")


class OAuthError(Exception):
    """Anything that means this sign-in cannot be completed."""


class TokenExchangeFailed(OAuthError):
    """The provider refused the authorization code."""


class IdTokenInvalid(OAuthError):
    """The id token was missing, unverifiable, or not addressed to us."""


@dataclass(frozen=True)
class ProviderIdentity:
    provider: str
    subject: str
    email: str | None
    email_verified: bool


# --- PKCE -------------------------------------------------------------------


def new_pkce_verifier() -> str:
    return secrets.token_urlsafe(64)


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


# --- Token exchange ---------------------------------------------------------

# Long enough for a provider having a slow day, short enough that a hung
# connection does not pin a worker while the user stares at a blank tab.
EXCHANGE_TIMEOUT_SECONDS = 10.0


async def exchange_code(
    provider: Provider, code: str, code_verifier: str | None
) -> str:
    """
    Trade the authorization code for an id token.

    DELIBERATELY NOT app/services/scrapers/http.py. That wrapper exists to
    fetch attacker-influenced URLs safely and enforces a host allowlist,
    refuses redirects and caps the response -- none of which applies to a
    constant endpoint in our own source, and its allowlist would simply block
    the call.
    """
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": provider.redirect_uri,
        "client_id": provider.client_id,
        "client_secret": provider.client_secret(),
    }
    if code_verifier:
        data["code_verifier"] = code_verifier

    try:
        async with httpx.AsyncClient(timeout=EXCHANGE_TIMEOUT_SECONDS) as client:
            response = await client.post(
                provider.token_url, data=data, headers={"Accept": "application/json"}
            )
    except httpx.HTTPError as exc:
        raise TokenExchangeFailed(f"{provider.id} token endpoint unreachable") from exc

    if response.status_code != 200:
        # The body carries the provider's own error code and nothing about
        # our user, so it is safe to log and genuinely necessary: without it
        # "invalid_client" and "redirect_uri_mismatch" are indistinguishable
        # from the outside, and they need opposite fixes.
        logger.warning(
            "OAuth token exchange rejected",
            extra={"action": "oauth_token_exchange", "target": provider.id,
                   "success": False},
        )
        raise TokenExchangeFailed(
            f"{provider.id} returned {response.status_code} for the code exchange"
        )

    payload = response.json()
    id_token = payload.get("id_token")
    if not id_token:
        raise TokenExchangeFailed(f"{provider.id} returned no id_token")
    return id_token


# --- JWKS -------------------------------------------------------------------

# Providers rotate signing keys on their own schedule, so a cached set has to
# expire; an hour is what Google's own cache headers ask for.
JWKS_TTL_SECONDS = 3600

# A kid we have never seen is the normal signal that a rotation has happened,
# so it justifies one immediate refetch. It is ALSO what an attacker sends to
# make us hammer the provider on demand: a token with a random kid costs them
# nothing and would cost us one outbound request each. This floor means the
# whole internet can only provoke one refetch per provider per minute.
JWKS_MIN_REFETCH_SECONDS = 60

JWKS_TIMEOUT_SECONDS = 5.0

# url -> (PyJWKSet, fetched_at)
_jwks_cache: dict[str, tuple[jwt.PyJWKSet, float]] = {}


async def _fetch_jwks(url: str) -> dict:
    """Fetch a provider's key set. Separate so tests can replace it."""
    async with httpx.AsyncClient(timeout=JWKS_TIMEOUT_SECONDS) as client:
        response = await client.get(url)
    response.raise_for_status()
    return response.json()


async def _load_jwks(url: str) -> jwt.PyJWKSet:
    raw = await _fetch_jwks(url)
    key_set = jwt.PyJWKSet.from_dict(raw)
    _jwks_cache[url] = (key_set, time.monotonic())
    return key_set


async def signing_key(provider: Provider, kid: str | None) -> jwt.PyJWK:
    """The provider's public key for this token, refetching at most rarely."""
    if not kid:
        raise IdTokenInvalid("id token has no key id")

    url = provider.jwks_url
    cached = _jwks_cache.get(url)
    age = time.monotonic() - cached[1] if cached else None

    if cached is None or age is None or age > JWKS_TTL_SECONDS:
        try:
            key_set = await _load_jwks(url)
        except Exception as exc:
            raise IdTokenInvalid(f"{provider.id} key set unavailable") from exc
        age = 0.0
    else:
        key_set = cached[0]

    try:
        return key_set[kid]
    except (KeyError, jwt.PyJWKSetError):
        pass

    if age < JWKS_MIN_REFETCH_SECONDS:
        raise IdTokenInvalid("unknown signing key")

    try:
        key_set = await _load_jwks(url)
        return key_set[kid]
    except Exception as exc:
        raise IdTokenInvalid("unknown signing key") from exc


def reset_jwks_cache() -> None:
    """Drop the cached key sets. For tests; nothing in the app calls it."""
    _jwks_cache.clear()


# --- Id token verification --------------------------------------------------


def _email_verified(value) -> bool:
    """
    Apple sends this as the STRING "true"; Google sends a boolean.

    Written as an allowlist rather than bool(value) because bool("false") is
    True -- which would turn Apple's explicit denial into an approval, and the
    two branches that must not be reached without it are account creation and
    account linking.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return False


async def verify_id_token(
    provider: Provider, id_token: str, nonce: str
) -> ProviderIdentity:
    """
    Verify signature, issuer, audience, expiry and nonce. Then, and only then,
    believe what the token says.
    """
    try:
        header = jwt.get_unverified_header(id_token)
    except jwt.PyJWTError as exc:
        raise IdTokenInvalid("malformed id token") from exc

    key = await signing_key(provider, header.get("kid"))

    try:
        claims = jwt.decode(
            id_token,
            key,
            algorithms=list(provider.id_token_algorithms),
            # aud is what stops a token minted for a DIFFERENT application
            # from being replayed here. Google will happily issue one to
            # anybody who registers a client; without this check any of them
            # could sign in as our users.
            audience=provider.client_id,
            issuer=list(provider.issuers),
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except jwt.PyJWTError as exc:
        # One generic failure on purpose, exactly as jwt_handler.verify_token
        # does: telling a caller whether the signature or the audience was
        # wrong is free reconnaissance.
        raise IdTokenInvalid(str(exc)) from exc

    presented_nonce = claims.get("nonce")
    if not isinstance(presented_nonce, str) or not secrets.compare_digest(
        presented_nonce, nonce
    ):
        # The token is genuine but belongs to a different sign-in attempt --
        # which is what a replayed id token looks like.
        raise IdTokenInvalid("nonce mismatch")

    subject = claims.get("sub")
    if not subject:
        raise IdTokenInvalid("id token has no subject")

    return ProviderIdentity(
        provider=provider.id,
        subject=str(subject),
        email=claims.get("email"),
        email_verified=_email_verified(claims.get("email_verified")),
    )
