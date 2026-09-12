"""
Where the browser is sent afterwards, and why almost nothing is allowed.

The post-login destination is supplied by whoever builds the "Continue with
Google" link, which means it is attacker-controlled. Reflected unchecked, it
is an open redirect on an authentication endpoint -- the most valuable kind,
because the URL genuinely starts on our domain, the user genuinely signs in,
and the page they land on afterwards is the attacker's. That is a credible
"your session expired, sign in again" phishing page arriving from a link the
victim has every reason to trust.
"""

from __future__ import annotations

import re

DEFAULT_PATH = "/"

# Where the SPA handles the landing. Deliberately NOT under /auth: that prefix
# belongs to the API, and app/frontend.py answers any unmatched path under it
# with a JSON 404 rather than the app shell -- so an SPA route there would
# 404 on a hard refresh in a built deploy. /verify-email and /reset-password
# are top-level for the same reason.
SPA_CALLBACK_PATH = "/oauth/callback"

MAX_LENGTH = 512

# Backslash is in here because browsers normalise "\" to "/" in a URL: "/\evil.com"
# and "/\/evil.com" are read as protocol-relative and leave the site, while a
# naive startswith("/") and not startswith("//") check waves both through.
# Control characters are refused too -- a bare CR or LF in a Location header is
# response splitting.
_FORBIDDEN = re.compile(r"[\x00-\x1f\x7f\\]")


def safe_next_path(raw: str | None) -> str:
    """
    A relative path we are willing to send a freshly authenticated user to.

    Anything else silently becomes "/" rather than raising: a rejected `next`
    is a nuisance for the caller and an attack for everyone else, and failing
    the whole sign-in over it would make the attack a denial of service too.
    """
    if not raw or len(raw) > MAX_LENGTH:
        return DEFAULT_PATH
    if _FORBIDDEN.search(raw):
        return DEFAULT_PATH
    # Exactly one leading slash. Two means protocol-relative ("//evil.com"),
    # which the browser reads as a different ORIGIN even though it looks like
    # a path; none means a scheme ("https://evil.com") or a bare word the
    # browser resolves relative to the current page.
    if not raw.startswith("/") or raw.startswith("//"):
        return DEFAULT_PATH
    return raw
