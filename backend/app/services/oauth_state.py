"""
The one-time CSRF state for a social sign-in round trip.

WHY THIS IS NOT IN app/services/cache.py, AND WHY IT LOOKS "WORSE" THAN IT.

cache.py swallows every Redis failure and returns None, because a missed
cache is a slow page and nothing more. Copying that habit here would turn the
state parameter into decoration, and the attack is not subtle:

    the attacker starts a Google authorization themselves, stops at the
    callback URL instead of following it, and sends that URL to a victim.
    The victim's browser completes it, and the victim is signed in as the
    ATTACKER. Every search, wishlist entry, price alert and contact message
    they make from then on lands in the attacker's account. Nothing in the UI
    shows anything wrong.

TWO VALUES ARE NEEDED TO STOP THAT, AND THIS MODULE ONLY HOLDS ONE. The state
proves the server minted this sign-in and has not seen it since. It CANNOT
prove which browser started it -- it is a server-side value, so any browser
presenting a live one satisfies it, which is exactly the attack above. The
second value is the `binding` carried in the payload: a separate secret that
also goes out as a cookie, so the callback is only accepted from the browser
that holds it, and an attacker cannot set a cookie on someone else's browser.
Both are checked in app/routers/oauth.py; dropping either one reopens the
attack. So:

  - FAIL CLOSED. An unreachable Redis rejects the sign-in. That is a partial
    outage, not a total one -- password login is untouched -- and it is the
    opposite policy to both neighbouring modules (cache.py:89 and
    rate_limiter.py:133 deliberately carry on without Redis). Do not "fix"
    this to match them.
  - SINGLE USE, atomically. GETDEL reads and deletes in one round trip, so
    two concurrent callbacks carrying the same state cannot both win. Reading
    and then deleting would leave a window; not deleting at all would leave
    the same callback URL replayable for the whole TTL.

The payload carries more than randomness -- the nonce that binds the id token
to this request, the PKCE verifier, the browser binding, and the post-login
path -- so none of those can be swapped by whoever holds the callback URL.
"""

from __future__ import annotations

import json
import re
import secrets

from app.services.cache import get_cache

KEY_PREFIX = "oauth:state:"

# Long enough to survive a slow provider round trip and a user who reads the
# consent screen, short enough that an abandoned sign-in leaves nothing usable
# lying around. It only has to cover one redirect there and back.
DEFAULT_TTL_SECONDS = 600

# What we mint: token_urlsafe output. Anything else never came from us, so it
# is refused before it can become part of a Redis key.
_STATE_FORMAT = re.compile(r"\A[A-Za-z0-9_-]{22,128}\Z")


class StateStoreUnavailable(Exception):
    """Redis could not be reached, so no sign-in can be proved to be ours."""


async def issue(payload: dict, ttl: int = DEFAULT_TTL_SECONDS) -> str:
    """Mint a state token and store what it stands for. Returns the token."""
    # 32 bytes of os.urandom: guessing one is not a realistic attack, which is
    # what lets the callback be an ordinary unauthenticated GET.
    state = secrets.token_urlsafe(32)
    try:
        client = await get_cache()
        await client.setex(KEY_PREFIX + state, ttl, json.dumps(payload))
    except Exception as exc:
        raise StateStoreUnavailable(str(exc)) from exc
    return state


async def consume(state: str | None) -> dict | None:
    """
    Spend a state token. Returns its payload, or None if it is not ours.

    Raises StateStoreUnavailable rather than returning None when Redis itself
    is unreachable: the caller has to be able to tell "this callback is
    forged" from "we cannot check", because only one of those may ever be
    allowed to continue, and neither is allowed to continue silently.
    """
    if not state or not _STATE_FORMAT.match(state):
        return None

    try:
        client = await get_cache()
        raw = await client.getdel(KEY_PREFIX + state)
    except Exception as exc:
        raise StateStoreUnavailable(str(exc)) from exc

    if not raw:
        return None

    try:
        payload = json.loads(raw)
    except ValueError:
        return None

    return payload if isinstance(payload, dict) else None
