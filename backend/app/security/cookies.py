"""
Refresh token cookie handling.

WHY A COOKIE AND NOT localStorage:
Anything in localStorage is readable by any JavaScript running on the page, so
a single XSS hands an attacker the refresh token -- a credential good for days.
An httpOnly cookie is not exposed to JavaScript at all: the browser attaches it
to requests, and script cannot read it back. XSS can still *make* requests as
the user, but it cannot exfiltrate a token to use later, offline, or elsewhere.

The access token stays out of storage entirely and lives in memory in the SPA.
It dies on page refresh, at which point the app silently exchanges the cookie
for a new one. That is the point of the pair: the long-lived half is
unreadable, and the short-lived half is never persisted.

The trade-off cookies bring is CSRF, since browsers attach them automatically.
Three things address it here:
  - SameSite (lax by default, none+Secure only when the API is cross-site),
    which stops the cookie riding along on requests from other origins
  - the cookie is scoped by `path` to the refresh endpoints, so it is not sent
    on ordinary API calls at all
  - the API is JSON-only with a strict CORS allow-list, so a classic HTML form
    post from another origin cannot produce a request the API will act on
"""

from datetime import timedelta

from fastapi import Request, Response

from app.config import get_settings
from app.services import oauth_state

settings = get_settings()

# Scope the cookie to the endpoints that consume it. A cookie sent on every
# request to every path is a larger target and a wider CSRF surface than one
# the browser only attaches to /auth.
COOKIE_PATH = "/auth"


def set_refresh_cookie(response: Response, token: str) -> None:
    """Attach the refresh token as an httpOnly cookie."""
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=token,
        httponly=True,  # the whole point: invisible to document.cookie
        secure=settings.cookie_is_secure,
        samesite=settings.cookie_samesite,
        path=COOKIE_PATH,
        max_age=int(timedelta(days=settings.refresh_token_expire_days).total_seconds()),
    )


def clear_refresh_cookie(response: Response) -> None:
    """
    Remove the cookie on logout.

    The attributes must match those used to set it -- a browser treats a
    cookie with a different path as a different cookie and would leave the
    original in place.
    """
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_is_secure,
        samesite=settings.cookie_samesite,
    )


# --- The social sign-in browser binding ------------------------------------
#
# Scoped to the OAuth endpoints alone. It exists for one redirect and is spent
# at the callback, so sending it anywhere else is surface for nothing.
OAUTH_STATE_COOKIE = "oauth_binding"
OAUTH_STATE_COOKIE_PATH = "/auth/oauth"


def _oauth_cookie_policy() -> tuple[bool, str]:
    """
    Secure and SameSite for the binding cookie, which are not free choices.

    APPLE IS WHY THIS IS NOT `lax` LIKE THE REFRESH COOKIE. Apple mandates
    response_mode=form_post, so its callback arrives as a CROSS-SITE POST, and
    a Lax cookie is not sent on one. The binding would be missing on every
    Apple sign-in and every Apple sign-in would be refused -- a Lax cookie here
    does not weaken the control, it breaks the provider outright.

    SameSite=None is only honoured on a Secure cookie, so the two move
    together. When the deployment cannot be Secure -- plain-http local
    development -- this falls back to Lax, which still carries Google's
    top-level GET redirect back to us. Apple is unreachable in that
    configuration anyway: it refuses to register an http redirect URI at all,
    so the fallback never degrades a working Apple setup.
    """
    secure = settings.cookie_is_secure
    return secure, "none" if secure else "lax"


def set_oauth_state_cookie(response: Response, binding: str) -> None:
    """Remember, in this browser, that it is the one that began the sign-in."""
    secure, samesite = _oauth_cookie_policy()
    response.set_cookie(
        key=OAUTH_STATE_COOKIE,
        value=binding,
        httponly=True,  # script has no use for it; XSS should not reach it
        secure=secure,
        samesite=samesite,
        path=OAUTH_STATE_COOKIE_PATH,
        # The state it is paired with expires on the same clock. A binding
        # that outlived its state would be a value with nothing to match.
        max_age=oauth_state.DEFAULT_TTL_SECONDS,
    )


def clear_oauth_state_cookie(response: Response) -> None:
    """
    Spend the binding, whatever the outcome.

    Cleared on FAILURE as well as success. A binding left behind after a
    refused callback is matched against the next sign-in's state, which it
    cannot satisfy -- so the user's retry fails too, and they are locked out by
    the debris of their own last attempt rather than by anything real.
    """
    secure, samesite = _oauth_cookie_policy()
    response.delete_cookie(
        key=OAUTH_STATE_COOKIE,
        path=OAUTH_STATE_COOKIE_PATH,
        httponly=True,
        secure=secure,
        samesite=samesite,
    )


def read_oauth_state_cookie(request: Request) -> str | None:
    """The binding this browser is carrying, if it is carrying one."""
    return request.cookies.get(OAUTH_STATE_COOKIE)


def read_refresh_token(request: Request, body_token: str | None = None) -> str | None:
    """
    Get the refresh token, preferring the cookie.

    The body is accepted as a fallback for non-browser clients (a mobile app or
    a CLI has no cookie jar). This does not weaken the browser case: what
    protects the token there is that it is never *returned* in a response body,
    so page JavaScript never holds a copy to put in a request.
    """
    return request.cookies.get(settings.refresh_cookie_name) or body_token
