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


def read_refresh_token(request: Request, body_token: str | None = None) -> str | None:
    """
    Get the refresh token, preferring the cookie.

    The body is accepted as a fallback for non-browser clients (a mobile app or
    a CLI has no cookie jar). This does not weaken the browser case: what
    protects the token there is that it is never *returned* in a response body,
    so page JavaScript never holds a copy to put in a request.
    """
    return request.cookies.get(settings.refresh_cookie_name) or body_token
