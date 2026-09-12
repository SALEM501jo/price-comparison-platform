"""
What each identity provider is, as data.

WHY THE SERVER-SIDE REDIRECT FLOW AND NOT THE PROVIDERS' JAVASCRIPT SDKs:
the production Content-Security-Policy is script-src 'self'
(app/middleware/security_headers.py), so Google Identity Services and
appleid.auth.js are refused outright there -- while the development policy
allows inline script and a CDN, so an SDK-based sign-in works perfectly on a
laptop and dies silently on the deployed site with nothing but a console
message. Redirecting the browser ourselves needs no third-party script at all,
which keeps that policy closed AND means a visitor who never clicks the button
is never announced to Google.

NO OAUTH LIBRARY EITHER. The two things that are genuinely hard to get right
-- verifying an id token's signature and enforcing single-use state -- are
done explicitly in flow.py and app/services/oauth_state.py, where they can be
read and tested. What a library would add on top of httpx and PyJWT here is
URL construction.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlencode

import jwt

from app.config import get_settings

settings = get_settings()

GOOGLE = "google"
APPLE = "apple"


@dataclass(frozen=True)
class Provider:
    id: str
    authorize_url: str
    token_url: str
    jwks_url: str
    # A tuple because Google issues both "https://accounts.google.com" and the
    # bare "accounts.google.com" and has never committed to dropping either.
    issuers: tuple[str, ...]
    scope: str
    client_id: str
    client_secret: Callable[[], str]
    uses_pkce: bool
    # Apple insists on form_post the moment any scope is requested, which is
    # why the callback also accepts a POST. See app/routers/oauth.py.
    response_mode: str | None = None
    # NEVER read from the token's own header: letting a token name its own
    # algorithm is the classic confusion attack, the same reason
    # app/security/jwt_handler.py passes a list rather than a string.
    id_token_algorithms: tuple[str, ...] = field(default=("RS256",))

    @property
    def redirect_uri(self) -> str:
        return (
            settings.api_base_url.rstrip("/")
            + f"/auth/oauth/{self.id}/callback"
        )

    def authorization_url(
        self, *, state: str, nonce: str, code_challenge: str | None
    ) -> str:
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": self.scope,
            "state": state,
            # Binds the id token we get back to THIS start request. Without
            # it, an id token the attacker obtained elsewhere for the same
            # audience could be replayed into someone else's callback.
            "nonce": nonce,
        }
        if self.response_mode:
            params["response_mode"] = self.response_mode
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"
        return f"{self.authorize_url}?{urlencode(params)}"


def _google_client_secret() -> str:
    return settings.google_client_secret


# Apple's client secret is short-lived on purpose. The maximum it accepts is
# six months; minting one per exchange that lasts minutes means an intercepted
# secret is worthless almost immediately, and it costs one ES256 signature --
# microseconds, next to a network round trip to Apple.
APPLE_SECRET_TTL_SECONDS = 300


def _apple_client_secret() -> str:
    """
    Apple has no static client secret: it is an ES256 JWT we sign ourselves.

    Generated here rather than pasted into the environment because a pasted
    one expires -- silently, months after the deploy that worked, with every
    Apple sign-in failing at the token exchange and no configuration change to
    blame it on.
    """
    now = int(time.time())
    try:
        return jwt.encode(
            {
                "iss": settings.apple_team_id,
                "iat": now,
                "exp": now + APPLE_SECRET_TTL_SECONDS,
                "aud": "https://appleid.apple.com",
                # The Services ID -- what Apple calls the client_id for a web app.
                "sub": settings.apple_client_id,
            },
            settings.apple_private_key_pem,
            algorithm="ES256",
            headers={"kid": settings.apple_key_id},
        )
    except Exception as exc:
        # Imported here, not at module scope: flow.py already imports this
        # module, so a top-level import would be a cycle. This function is
        # only ever called lazily, so the cost is a dict lookup.
        from app.services.oauth.flow import TokenExchangeFailed

        # A PRESENT BUT UNLOADABLE KEY. The startup check can only see that
        # APPLE_PRIVATE_KEY is non-empty, and the three ways it is typically
        # wrong all survive that: an RSA key where Apple wants EC, a truncated
        # paste, or the FILE PATH pasted instead of the file's contents.
        #
        # Raised as TokenExchangeFailed rather than escaping as a bare
        # ValueError because the callback only catches the former. Escaping
        # gives the user a 500 and the operator a stack trace, for what is a
        # configuration mistake with a one-line fix; this way they get the
        # ordinary "provider_error" screen and the log line below says which
        # provider and why.
        raise TokenExchangeFailed(
            "Apple client secret could not be signed; check APPLE_PRIVATE_KEY "
            "is the contents of the .p8 file (an EC key), not a path to it"
        ) from exc


def _build(provider_id: str) -> Provider | None:
    if provider_id == GOOGLE and settings.google_oauth_enabled:
        return Provider(
            id=GOOGLE,
            authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            jwks_url="https://www.googleapis.com/oauth2/v3/certs",
            issuers=("https://accounts.google.com", "accounts.google.com"),
            # No profile scope. The platform stores no names or avatars, and
            # asking for data we would immediately throw away is a worse
            # consent screen for no gain.
            scope="openid email",
            client_id=settings.google_client_id,
            client_secret=_google_client_secret,
            uses_pkce=True,
        )

    if provider_id == APPLE and settings.apple_oauth_enabled:
        return Provider(
            id=APPLE,
            authorize_url="https://appleid.apple.com/auth/authorize",
            token_url="https://appleid.apple.com/auth/token",
            jwks_url="https://appleid.apple.com/auth/keys",
            issuers=("https://appleid.apple.com",),
            # "email" only. Apple returns the user's NAME exactly once, on the
            # very first authorization ever, in the form-encoded POST body --
            # never in the id token and never again afterwards. This project
            # stores no names, so it is not requested; anyone tempted to add
            # "name" here should know that reading it back on the second
            # sign-in is impossible, not merely awkward.
            scope="email",
            client_id=settings.apple_client_id,
            client_secret=_apple_client_secret,
            # Apple's authorization endpoint rejects code_challenge outright.
            uses_pkce=False,
            # Required by Apple once any scope is requested. It makes the
            # callback a CROSS-SITE POST, on which a SameSite=Lax cookie is
            # NOT sent -- which is the whole reason the CSRF state lives in
            # Redis rather than in a cookie.
            response_mode="form_post",
        )

    return None


def get_provider(provider_id: str) -> Provider | None:
    """The provider, or None if it is unknown or not configured."""
    return _build(provider_id)


def enabled_provider_ids() -> list[str]:
    """Which providers /auth/providers should advertise, in display order."""
    return [pid for pid in (GOOGLE, APPLE) if _build(pid) is not None]
