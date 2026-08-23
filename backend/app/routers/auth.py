"""
Authentication routes.
SECURITY PRINCIPLE: Every auth operation must be auditable and timing-safe.
"""

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.exceptions import AuthenticationError, ConflictError
from app.logging_config import get_security_logger, pseudonymize
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.security.jwt_handler import (
    create_access_token,
    create_refresh_token,
    verify_token,
)
from app.security.password import get_dummy_hash, hash_password, verify_password
from app.security.rate_limiter import strict_rate_limit
from app.services import tokens as token_service

router = APIRouter()
logger = get_security_logger("app.auth")


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _issue_tokens(db: Session, user: User) -> TokenResponse:
    """Mint an access/refresh pair and record the refresh token for revocation."""
    access_token = create_access_token({"sub": str(user.id), "role": user.role})
    refresh_token, jti = create_refresh_token({"sub": str(user.id)})
    token_service.record_issued(db, jti=jti, user_id=user.id)
    return TokenResponse(
        access_token=access_token, refresh_token=refresh_token, token_type="bearer"
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: Request,
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

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        role="user",
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
    return _issue_tokens(db, user)


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    body: LoginRequest,
    db: Session = Depends(get_db),
):
    """
    Log in an existing user.

    TIMING ATTACK PREVENTION:
    When the account does not exist we still run verify_password against a
    dummy hash. Without it, "no such user" returns in ~1ms and "wrong password"
    in ~250ms, and that gap alone reveals which addresses are registered.
    """
    await strict_rate_limit(request)

    user = db.query(User).filter(User.email == body.email).first()
    password_hash = user.password_hash if user else get_dummy_hash()
    password_valid = verify_password(body.password, password_hash)

    if not user or not password_valid:
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
    return _issue_tokens(db, user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: Request,
    body: RefreshRequest,
    db: Session = Depends(get_db),
):
    """
    Exchange a refresh token for a new pair.

    The old token is burned on use (rotation). Presenting it a second time is
    treated as proof of compromise and revokes every token the user holds --
    see app/services/tokens.py for why.
    """
    await strict_rate_limit(request)

    try:
        payload = verify_token(body.refresh_token, token_type="refresh")
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

    logger.info(
        "Token refreshed",
        extra={
            "user_id": user.id,
            "ip": _client_ip(request),
            "action": "refresh",
            "success": True,
        },
    )
    return TokenResponse(
        access_token=access_token, refresh_token=new_refresh, token_type="bearer"
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
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


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user info."""
    return current_user
