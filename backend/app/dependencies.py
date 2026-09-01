"""
Reusable FastAPI dependencies.
SECURITY PRINCIPLE: Consistency. If auth is required, it should be IMPOSSIBLE
to forget adding it. Centralized dependencies prevent human error.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.user import User, UserRole
from app.security.jwt_handler import verify_token
from app.security.rate_limiter import rate_limit

settings = get_settings()

# Two schemes on purpose:
#   - required: rejects the request itself when the header is missing (401)
#   - optional: auto_error=False so a missing header yields None instead of
#     raising BEFORE our function body runs. With the default auto_error=True
#     the "optional" dependency below could never actually return None.
bearer_scheme = HTTPBearer()
bearer_scheme_optional = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Extract the user from a JWT and confirm they still exist in the DB.
    Use this on ANY endpoint that requires authentication.
    """
    payload = verify_token(credentials.credentials)

    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        # The token is validly signed but the account is gone (deleted user).
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    return user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """
    Admin-only endpoints.
    Usage: @router.delete("/users/{id}", dependencies=[Depends(require_admin)])
    """
    if current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


async def require_merchant(current_user: User = Depends(get_current_user)) -> User:
    """
    Endpoints a shop owner uses to manage their own store.

    Admins pass too. They already administer every store through /admin, so
    refusing them here would mean an admin could not reproduce a merchant's
    bug without a second account.

    This only establishes WHO is asking. It says nothing about WHICH store
    they may touch -- that is resolved per request from the signed-in user,
    never from an id in the URL. See app/routers/merchant.py.
    """
    if current_user.role not in (UserRole.merchant, UserRole.admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Merchant access required",
        )
    return current_user


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme_optional),
    db: Session = Depends(get_db),
) -> User | None:
    """
    For endpoints that serve both guests and logged-in users.
    Example: search works without login, but can show wishlist state if present.
    Returns None when there is no usable token.
    """
    if credentials is None:
        return None
    try:
        payload = verify_token(credentials.credentials)
        return db.query(User).filter(User.id == int(payload.get("sub"))).first()
    except Exception:
        return None


async def get_rate_limited(_: None = Depends(rate_limit)) -> None:
    """
    Rate-limiting dependency.
    Usage: @router.get("/search", dependencies=[Depends(get_rate_limited)])
    rate_limit() raises 429 itself; nothing to do here.
    """
    return None
