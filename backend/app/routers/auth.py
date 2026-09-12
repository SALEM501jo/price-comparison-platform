"""
Authentication routes.
SECURITY PRINCIPLE: Every auth operation must be auditable and timing-safe.
"""

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.exceptions import AppException, AuthenticationError, ConflictError
from app.logging_config import get_security_logger, pseudonymize
from app.models.user import User, UserRole
from app.schemas.auth import (
    DeleteAccountRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ForgotPasswordRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserResponse,
    VerifyEmailRequest,
)
from app.security.jwt_handler import (
    create_access_token,
    create_refresh_token,
    verify_token,
)
from app.security.cookies import (
    clear_refresh_cookie,
    read_refresh_token,
    set_refresh_cookie,
)
from app.security.password import get_dummy_hash, hash_password, verify_password
from app.security.rate_limiter import rate_limit, strict_rate_limit
from app.services import tokens as token_service
from app.services import account, password_reset, verification

router = APIRouter()
logger = get_security_logger("app.auth")


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _issue_tokens(db: Session, user: User, response: Response) -> TokenResponse:
    """
    Mint an access/refresh pair, record the refresh token, and set the cookie.

    The refresh token goes out ONLY as an httpOnly cookie -- it is never part
    of the JSON body, so no JavaScript on the page ever sees it.
    """
    access_token = create_access_token({"sub": str(user.id), "role": user.role})
    refresh_token, jti = create_refresh_token({"sub": str(user.id)})
    token_service.record_issued(db, jti=jti, user_id=user.id)
    set_refresh_cookie(response, refresh_token)
    return TokenResponse(access_token=access_token, token_type="bearer")


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: Request,
    response: Response,
    body: RegisterRequest,
    db: Session = Depends(get_db),
):
    """
    Register a new user.

    SECURITY MEASURES:
    1. Rate limiting: 5 attempts/min per IP
    2. Password policy enforced in the schema
    3. bcrypt cost 12: ~250ms per hash, which is what slows offline cracking
    4. Audit logging of every attempt
    """
    await strict_rate_limit(request)

    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        # NOTE: this endpoint is knowingly an account-existence oracle -- it
        # returns 409 for a taken address. Registration cannot avoid that
        # without an email round-trip, so the honest fix is verification-on-
        # signup rather than pretending the response is uniform. The strict
        # rate limit is what keeps it from being enumerable at scale.
        logger.warning(
            "Registration failed: email already exists",
            extra={
                "ip": _client_ip(request),
                "action": "register",
                "success": False,
                "target": pseudonymize(body.email),
            },
        )
        raise ConflictError("An account with this email already exists")

    # Mapped, never passed through. body.account_type is restricted to two
    # values by the schema, and this dict is the only place either becomes a
    # role -- so a request cannot name a role the platform did not offer.
    role = UserRole.merchant if body.account_type == "merchant" else UserRole.user

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info(
        "User registered",
        extra={
            "user_id": user.id,
            "ip": _client_ip(request),
            "action": "register",
            "success": True,
        },
    )

    # Best effort: send() never raises. A mail outage must not fail a signup
    # and leave the account in limbo -- the user can request a new link.
    verification.send_verification(db, user)

    return _issue_tokens(db, user, response)


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    db: Session = Depends(get_db),
):
    """
    Log in an existing user.

    TIMING ATTACK PREVENTION:
    When the account does not exist we still run verify_password against a
    dummy hash. Without it, "no such user" returns in ~1ms and "wrong password"
    in ~250ms, and that gap alone reveals which addresses are registered.

    THE SAME APPLIES TO AN ACCOUNT WITH NO PASSWORD -- one that signs in with
    Google or Apple, or one whose password was cleared when a provider was
    linked to it. Skipping bcrypt for those is the obvious shortcut and it is
    a worse leak than plain account enumeration: a reply in ~0ms against
    ~240ms says "this address exists AND uses a provider", which tells an
    attacker exactly which login page to imitate. Measured before this
    existed, it was not even a timing gap -- password_hash=None reached
    bcrypt, raised AttributeError, and returned HTTP 500 instantly.
    So the hash comparison still RUNS against the dummy, its result is
    discarded, and there is one uniform failure branch below.
    """
    await strict_rate_limit(request)

    user = db.query(User).filter(User.email == body.email).first()
    stored_hash = user.password_hash if user else None
    password_valid = verify_password(body.password, stored_hash or get_dummy_hash())

    if not user or stored_hash is None or not password_valid:
        logger.warning(
            "Login failed",
            extra={
                "ip": _client_ip(request),
                "action": "login",
                "success": False,
                "target": pseudonymize(body.email),
            },
        )
        raise AuthenticationError("Invalid email or password")

    logger.info(
        "User logged in",
        extra={
            "user_id": user.id,
            "ip": _client_ip(request),
            "action": "login",
            "success": True,
        },
    )
    return _issue_tokens(db, user, response)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    body: RefreshRequest | None = None,
):
    """
    Exchange a refresh token for a new pair.

    The old token is burned on use (rotation). Presenting it a second time is
    treated as proof of compromise and revokes every token the user holds --
    see app/services/tokens.py for why.
    """
    # The ordinary limit, not the strict one. The SPA exchanges the cookie for
    # an access token on every page load, so 5/min would 429 anyone who
    # reloaded a few times. The strict limit exists to slow password guessing;
    # a refresh token is a signed 256-bit value that cannot be guessed, so the
    # signature is what protects this endpoint, not the request rate.
    await rate_limit(request)

    presented = read_refresh_token(request, body.refresh_token if body else None)
    if not presented:
        raise AuthenticationError("Invalid refresh token")

    try:
        payload = verify_token(presented, token_type="refresh")
    except Exception:
        logger.warning(
            "Token refresh failed: invalid token",
            extra={"ip": _client_ip(request), "action": "refresh", "success": False},
        )
        raise AuthenticationError("Invalid refresh token")

    user_id = int(payload["sub"])
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise AuthenticationError("Invalid refresh token")

    try:
        record = token_service.consume(db, jti=payload["jti"], user_id=user_id)
    except token_service.TokenReuseError:
        # consume() has already revoked the chain and logged the replay.
        raise AuthenticationError("Session revoked. Please log in again.")
    except token_service.TokenUnknownError:
        logger.warning(
            "Refresh token has no server-side record",
            extra={
                "user_id": user_id,
                "ip": _client_ip(request),
                "action": "refresh",
                "success": False,
            },
        )
        raise AuthenticationError("Invalid refresh token")

    access_token = create_access_token({"sub": str(user.id), "role": user.role})
    new_refresh, new_jti = create_refresh_token({"sub": str(user.id)})
    token_service.rotate(db, record, new_jti)
    set_refresh_cookie(response, new_refresh)

    logger.info(
        "Token refreshed",
        extra={
            "user_id": user.id,
            "ip": _client_ip(request),
            "action": "refresh",
            "success": True,
        },
    )
    return TokenResponse(access_token=access_token, token_type="bearer")


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Log out everywhere: revoke every refresh token this user holds.

    Access tokens already issued stay valid until they expire (at most 15
    minutes) -- that is the deliberate cost of keeping them stateless.
    """
    revoked = token_service.revoke_all_for_user(
        db, current_user.id, reason="user_logout"
    )
    clear_refresh_cookie(response)
    logger.info(
        "User logged out",
        extra={
            "user_id": current_user.id,
            "ip": _client_ip(request),
            "action": "logout",
            "target": revoked,
            "success": True,
        },
    )
    return None


@router.post("/verify-email", response_model=UserResponse)
async def verify_email(
    request: Request,
    body: VerifyEmailRequest,
    db: Session = Depends(get_db),
):
    """
    Redeem a verification link.

    Unauthenticated on purpose: the link is opened from an email client, often
    in a different browser from the one that signed up.
    """
    await strict_rate_limit(request)

    try:
        user = verification.consume(db, body.token)
    except verification.VerificationError:
        # One message for every failure. Telling a caller whether a token
        # expired, was already used, or never existed is free information for
        # anyone holding a stale link, and no help to a real user beyond
        # "request another".
        raise AuthenticationError("This link is invalid or has expired.")

    return user


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED)
async def resend_verification(
    request: Request,
    body: ResendVerificationRequest,
    db: Session = Depends(get_db),
):
    """
    Send a fresh verification link.

    ALWAYS returns 202, whatever happens. This endpoint is unauthenticated and
    takes an email address, which makes it the easiest account-enumeration
    oracle in the application: a 404 for unknown addresses would turn it into a
    membership check anyone can run. It is also a way to send mail to a
    stranger using our infrastructure, which is why verification.can_resend
    throttles per ACCOUNT as well as the per-IP limit here.
    """
    await strict_rate_limit(request)

    accepted = {"status": "accepted"}

    user = db.query(User).filter(User.email == body.email).first()
    if user is None or user.email_verified_at is not None:
        # Nothing to do -- and the response is identical either way.
        logger.info(
            "Verification resend ignored",
            extra={
                "ip": _client_ip(request),
                "action": "resend_verification",
                "target": pseudonymize(body.email),
                "success": True,
            },
        )
        return accepted

    if not verification.can_resend(db, user):
        logger.warning(
            "Verification resend throttled",
            extra={
                "user_id": user.id,
                "ip": _client_ip(request),
                "action": "resend_verification",
                "success": False,
            },
        )
        return accepted

    verification.send_verification(db, user)
    return accepted


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user info."""
    return current_user


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    db: Session = Depends(get_db),
):
    """
    Send a password reset link.

    A LINK, NOT A PASSWORD. Mailing a generated password would put a working
    credential in plaintext into an inbox where it stays forever, and would
    mean this server briefly knew it -- the one thing bcrypt exists to prevent.
    See app/services/password_reset.py.

    ALWAYS returns 202, whatever happens. Unauthenticated and taking an email
    address, this is the easiest account-enumeration oracle in the application:
    a 404 for unknown addresses turns it into a membership check anyone can
    run against any list of emails. The throttle is per ACCOUNT as well as
    per IP, so rotating addresses cannot bury one person's inbox either.
    """
    await strict_rate_limit(request)

    accepted = {"status": "accepted"}
    user = db.query(User).filter(User.email == body.email).first()

    if user is None:
        logger.info(
            "Password reset requested for unknown address",
            extra={
                "ip": _client_ip(request),
                "action": "forgot_password",
                "target": pseudonymize(body.email),
                "success": True,
            },
        )
        return accepted

    if not password_reset.can_request(db, user):
        logger.warning(
            "Password reset throttled",
            extra={
                "user_id": user.id,
                "ip": _client_ip(request),
                "action": "forgot_password",
                "success": False,
            },
        )
        return accepted

    password_reset.send_reset(db, user)
    logger.warning(
        "Password reset link sent",
        extra={
            "user_id": user.id,
            "ip": _client_ip(request),
            "action": "forgot_password",
            "success": True,
        },
    )
    return accepted


@router.post("/reset-password", response_model=UserResponse)
async def reset_password(
    request: Request,
    body: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    """
    Spend a reset link and set the new password.

    Deliberately does NOT sign the user in. Someone who has just proved
    control of the mailbox should still enter the password they chose -- it is
    the only thing that confirms they remember it, and it means a reset link
    opened on a shared machine does not leave a live session behind.

    Every existing session is revoked inside reset_password(); see there.
    """
    await strict_rate_limit(request)

    try:
        user = password_reset.reset_password(db, body.token, body.password)
    except password_reset.ResetError:
        logger.warning(
            "Password reset failed",
            extra={
                "ip": _client_ip(request),
                "action": "password_reset",
                "success": False,
            },
        )
        raise AuthenticationError("This link is invalid or has expired.")

    return user


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(
    request: Request,
    response: Response,
    body: DeleteAccountRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Delete the signed-in account. Permanent, and not appealable.

    THE ERASURE ITSELF is in app/services/account.py, table by table --
    including why a merchant's shop is retired rather than deleted, and why a
    support ticket keeps its text but loses the address that would still name
    the person who wrote it.

    EVERY SESSION DIES HERE. The refresh tokens are revoked and then removed
    with the account, and the cookie is cleared exactly as logout clears it: a
    deleted account whose refresh cookie still works is a live account. The
    access token that authorised this request dies with the row as well --
    get_current_user re-reads the user on every request -- so unlike logout
    there is no 15-minute window where a token outlives what it names.
    """
    # The ordinary limit, not the strict one. The strict limit exists to slow
    # credential guessing, and there is no credential to guess here: the
    # confirmation is the account's own address, which anyone holding this
    # token can read straight off GET /auth/me. This only keeps a destructive
    # endpoint from being hammered.
    await rate_limit(request)

    # Compared case-insensitively and with surrounding space ignored, because
    # a mobile keyboard capitalises the first letter and a paste brings a
    # trailing space -- neither is a different address, and refusing them
    # would teach people to retype until something works.
    if body.email.strip().lower() != current_user.email.strip().lower():
        logger.warning(
            "Account deletion refused: confirmation did not match",
            extra={
                "user_id": current_user.id,
                "ip": _client_ip(request),
                "action": "delete_account",
                "success": False,
            },
        )
        raise AppException(
            status.HTTP_400_BAD_REQUEST,
            "That is not the email address on this account.",
        )

    # Read before the row goes: once the account is deleted the instance is
    # detached and expired, and reading .id then raises rather than logging.
    user_id = current_user.id

    summary = account.delete_account(db, current_user)
    clear_refresh_cookie(response)

    logger.warning(
        "Account deleted",
        extra={
            "user_id": user_id,
            "ip": _client_ip(request),
            "action": "delete_account",
            "target": "store_retired" if summary.store_retired else "no_store",
            "success": True,
        },
    )
    return None
