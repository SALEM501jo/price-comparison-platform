"""
"Continue with Google" and "Sign in with Apple".

THE SHAPE OF THE FLOW, because it is not the one most tutorials show:

    GET  /auth/oauth/{provider}/start      -> 302 to the provider
    the provider authenticates the person
    GET  /auth/oauth/{provider}/callback   (Google, query string)
    POST /auth/oauth/{provider}/callback   (Apple, form_post, CROSS-SITE)
                                           -> 303 to the SPA, refresh cookie set

No provider JavaScript is loaded at any point, which is what keeps the
production CSP at script-src 'self', and no token of ours ever appears in a
URL -- see _spa_redirect below for why that mattered enough to design around.
"""

from __future__ import annotations

import secrets
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.exceptions import NotFoundError
from app.logging_config import get_security_logger
from app.security.cookies import (
    clear_oauth_state_cookie,
    read_oauth_state_cookie,
    set_oauth_state_cookie,
    set_refresh_cookie,
)
from app.security.jwt_handler import create_refresh_token
from app.security.rate_limiter import rate_limit, strict_rate_limit
from app.services import oauth_state
from app.services import tokens as token_service
from app.services.oauth import (
    SPA_CALLBACK_PATH,
    IdTokenInvalid,
    ProviderEmailUnverified,
    TokenExchangeFailed,
    enabled_provider_ids,
    exchange_code,
    get_provider,
    link_or_create,
    new_pkce_verifier,
    pkce_challenge,
    safe_next_path,
    verify_id_token,
)

router = APIRouter()
logger = get_security_logger("app.oauth")
settings = get_settings()

# What the SPA shows the user when a sign-in cannot be completed. Coarse on
# purpose: the person needs to know whether to try again or to use a password,
# and anything finer would narrate our internal checks to whoever is probing
# them.
ERROR_STATE = "state_invalid"
ERROR_UNAVAILABLE = "unavailable"
ERROR_PROVIDER = "provider_error"
ERROR_EMAIL_UNVERIFIED = "email_unverified"


def _spa_redirect(status_code: int = 303, **params: str) -> RedirectResponse:
    """
    Send the browser back to the app's landing page.

    NO TOKEN IS EVER PUT IN THESE PARAMETERS. A URL is the leakiest place a
    credential can sit: it lands in the server's access log, in the browser's
    history, in the Referer header of the next request the page makes, and in
    every proxy in between. The refresh token goes in the httpOnly cookie
    instead and the SPA exchanges it for an access token it keeps in memory --
    which is the arrangement the rest of this codebase already relies on, and
    a token in a query string would quietly undo it.

    303 rather than 302: Apple's callback is a POST, and only 303 guarantees
    the browser follows it with a GET.
    """
    base = settings.app_base_url.rstrip("/")
    query = f"?{urlencode(params)}" if params else ""
    return RedirectResponse(url=f"{base}{SPA_CALLBACK_PATH}{query}", status_code=status_code)


def _require_provider(provider_id: str):
    provider = get_provider(provider_id)
    if provider is None:
        # 404 rather than 503 or 400: a provider with no credentials is not
        # temporarily unwell, it does not exist here. /auth/providers is how
        # the frontend knows which buttons to render at all, so reaching this
        # means either a hand-typed URL or a stale build.
        raise NotFoundError("Unknown sign-in provider")
    return provider


@router.get("/providers")
async def list_providers(request: Request):
    """
    Which social sign-ins actually work on this deployment.

    THIS IS LOAD-BEARING, NOT COSMETIC. Sign in with Apple requires a paid
    Apple Developer account, so the site has to ship and work with Google
    alone -- and a button whose provider has no credentials is a button that
    leads to a 404 with nothing on screen to explain it.
    """
    await rate_limit(request)
    return {
        "providers": [
            {"id": pid, "start_url": f"/auth/oauth/{pid}/start"}
            for pid in enabled_provider_ids()
        ]
    }


@router.get("/oauth/{provider_id}/start")
async def start(
    request: Request,
    provider_id: str,
    next_path: Optional[str] = Query(default=None, alias="next"),
):
    """Begin a sign-in: mint the state and hand the browser to the provider."""
    await strict_rate_limit(request)
    provider = _require_provider(provider_id)

    nonce = new_pkce_verifier()
    verifier = new_pkce_verifier() if provider.uses_pkce else None
    # Paired with the cookie set on the way out, this is what makes the state
    # belong to THIS browser rather than merely to this server. Kept separate
    # from the state token itself so that the value in the URL and the value
    # in the cookie are different secrets: the state travels through the
    # provider, through browser history and through access logs, and none of
    # that should hand anyone the half that proves whose browser this is.
    binding = secrets.token_urlsafe(32)

    payload = {
        "provider": provider.id,
        "nonce": nonce,
        "verifier": verifier,
        "binding": binding,
        # Validated HERE rather than on the way out, so a hostile `next`
        # never even reaches Redis.
        "next": safe_next_path(next_path),
    }

    try:
        state = await oauth_state.issue(payload)
    except oauth_state.StateStoreUnavailable:
        # Without a state token this sign-in could not be proved to be ours
        # when it came back, so there is nothing to start. Password login is
        # unaffected, which is why this is a partial outage rather than one.
        logger.error(
            "Social sign-in unavailable: state store unreachable",
            extra={"action": "oauth_start", "target": provider.id, "success": False},
        )
        return _spa_redirect(error=ERROR_UNAVAILABLE)

    challenge = pkce_challenge(verifier) if verifier else None
    response = RedirectResponse(
        url=provider.authorization_url(
            state=state, nonce=nonce, code_challenge=challenge
        ),
        # 302, not 303: nothing was submitted, and this is the ordinary
        # "your destination is elsewhere" redirect.
        status_code=302,
    )
    # SET ON THE RESPONSE THAT IS ACTUALLY RETURNED, for the same reason the
    # refresh cookie is: a cookie written to an injected Response object is
    # dropped when the handler returns a RedirectResponse of its own, and the
    # failure is silent -- every callback would simply be refused.
    set_oauth_state_cookie(response, binding)
    return response


async def _complete(
    request: Request,
    provider_id: str,
    code: str | None,
    state: str | None,
    provider_error: str | None,
    db: Session,
) -> RedirectResponse:
    """The callback, shared by the GET (Google) and POST (Apple) forms."""
    await strict_rate_limit(request)
    provider = _require_provider(provider_id)

    if provider_error or not code:
        # The user pressed Cancel, or the provider refused. Not an incident.
        return _spa_redirect(error=ERROR_PROVIDER)

    try:
        payload = await oauth_state.consume(state)
    except oauth_state.StateStoreUnavailable:
        # FAIL CLOSED, and this is the single most important line in the file.
        #
        # The neighbouring Redis users (app/services/cache.py, the rate
        # limiter) both carry on when Redis is down, because a missed cache is
        # slow and a missed rate limit is merely weaker. Carrying on HERE
        # means accepting a callback nobody can prove we started -- login
        # CSRF: the attacker completes a Google authorization themselves and
        # feeds the resulting callback URL to a victim, who is then silently
        # signed in as the ATTACKER. Every search, wishlist entry, price alert
        # and contact message the victim makes afterwards lands in the
        # attacker's account, with nothing on screen to show it.
        #
        # Apple makes this sharper still: its callback is a cross-site POST,
        # on which no SameSite=Lax cookie is sent, so the state token is the
        # ONLY CSRF control there is.
        logger.error(
            "Social sign-in refused: state store unreachable",
            extra={"action": "oauth_callback", "target": provider.id, "success": False},
        )
        return _spa_redirect(error=ERROR_UNAVAILABLE)

    # None covers all of: never minted, already spent, and expired. They are
    # deliberately one answer -- a caller learning which of the three it hit
    # learns whether a state token is worth replaying.
    if payload is None or payload.get("provider") != provider.id:
        logger.warning(
            "Social sign-in rejected: state not recognised",
            extra={"action": "oauth_callback", "target": provider.id, "success": False},
        )
        return _spa_redirect(error=ERROR_STATE)

    # IS THIS THE BROWSER THAT STARTED THE SIGN-IN? The state alone cannot
    # answer that. It is a server-side value, so ANY browser presenting a live
    # one is accepted -- which is the whole login-CSRF attack, working against
    # a perfectly healthy Redis:
    #
    #   the attacker calls /start themselves, consents as their OWN account,
    #   captures the callback URL WITHOUT following it, and sends it to a
    #   victim. Everything downstream then verifies honestly -- the code
    #   redeems, the id token's signature and nonce are genuine -- and the
    #   victim's browser is handed a refresh cookie for the ATTACKER's user.
    #   They are silently signed in as someone else, including if they were
    #   already logged in as themselves, and everything they do from then on
    #   lands in an account the attacker reads at will.
    #
    # The binding cookie is what the attacker cannot forge: they cannot set a
    # cookie on the victim's browser for our domain. Compared in constant time
    # because it is a secret being checked for equality, and answered with the
    # SAME error as an unrecognised state so that a prober cannot learn which
    # half of the pair they got wrong.
    binding = payload.get("binding")
    presented = read_oauth_state_cookie(request)
    if (
        not binding
        or not presented
        or not secrets.compare_digest(str(binding), str(presented))
    ):
        logger.warning(
            "Social sign-in rejected: callback came from a different browser",
            extra={"action": "oauth_callback", "target": provider.id, "success": False},
        )
        return _spa_redirect(error=ERROR_STATE)

    try:
        id_token = await exchange_code(provider, code, payload.get("verifier"))
        identity = await verify_id_token(provider, id_token, payload["nonce"])
    except (TokenExchangeFailed, IdTokenInvalid):
        logger.warning(
            "Social sign-in rejected: provider response failed verification",
            extra={"action": "oauth_callback", "target": provider.id, "success": False},
        )
        return _spa_redirect(error=ERROR_PROVIDER)

    try:
        user = link_or_create(db, identity)
    except ProviderEmailUnverified:
        return _spa_redirect(error=ERROR_EMAIL_UNVERIFIED)

    # ONLY the refresh token. No access token is minted here because there is
    # nowhere safe to put one: the SPA calls /auth/refresh on every page load
    # anyway (frontend/src/context/AuthContext.jsx), so the cookie alone is a
    # complete sign-in.
    refresh_token, jti = create_refresh_token({"sub": str(user.id)})
    token_service.record_issued(db, jti=jti, user_id=user.id)

    response = _spa_redirect(next=payload.get("next") or "/")
    # SET ON THE RESPONSE THAT IS ACTUALLY RETURNED. FastAPI's injected
    # Response object only contributes its headers when the handler returns a
    # body model; write the cookie there and return a RedirectResponse and the
    # cookie is dropped -- the redirect works, the SPA's boot-time refresh
    # 401s, the user lands back on the login screen, and nothing is logged
    # anywhere.
    set_refresh_cookie(response, refresh_token)

    logger.info(
        "Signed in with a social provider",
        extra={"user_id": user.id, "action": "oauth_login",
               "target": provider.id, "success": True},
    )
    return response


@router.get("/oauth/{provider_id}/callback")
async def callback_get(
    request: Request,
    provider_id: str,
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """Google's callback: an ordinary redirect back with a query string."""
    response = await _complete(request, provider_id, code, state, error, db)
    # Cleared here rather than inside _complete so that no exit path can
    # forget: the binding is single-use like the state it is paired with, and
    # one left behind is matched against the NEXT attempt's state, which it
    # cannot satisfy -- locking the user out with the debris of the attempt
    # that just failed.
    clear_oauth_state_cookie(response)
    return response


@router.post("/oauth/{provider_id}/callback")
async def callback_post(
    request: Request,
    provider_id: str,
    code: Optional[str] = Form(default=None),
    state: Optional[str] = Form(default=None),
    error: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
):
    """
    Apple's callback: a CROSS-SITE form POST.

    Apple mandates response_mode=form_post as soon as any scope is requested,
    so the parameters arrive as form fields rather than in the URL.

    THIS IS WHY THE BINDING COOKIE IS SameSite=None. A cross-site POST carries
    no Lax cookie, so a Lax binding would be absent on every Apple sign-in and
    every Apple sign-in would be refused -- not weakened, broken. See
    app/security/cookies.py, which pairs None with Secure because browsers
    honour it no other way.

    Apple would also post a `user` field carrying the person's name, and only
    ever on their first authorization. It is not read: this platform stores no
    names, and code that depended on it would work once per user and then
    quietly stop.
    """
    response = await _complete(request, provider_id, code, state, error, db)
    clear_oauth_state_cookie(response)
    return response
