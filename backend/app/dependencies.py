"""
Reusable FastAPI dependencies.
SECURITY PRINCIPLE: Consistency. If auth is required, it should be IMPOSSIBLE
to forget adding it. Centralized dependencies prevent human error.
"""

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import get_settings
from app.security.jwt_handler import verify_token
from app.security.rate_limiter import rate_limit
from app.models.user import User, UserRole

settings = get_settings()
bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db)
) -> User:
    """
    Dependency: Extract user from JWT, verify in DB.
    Returns the full User object (not just token payload).
    Use this on ANY endpoint that requires authentication.
    """
    payload = verify_token(credentials.credentials)
    user_id = int(payload.get("sub"))
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    return user


async def require_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Dependency: Admin-only endpoints.
    Usage: @router.delete("/users/{id}", dependencies=[Depends(require_admin)])
    If a normal user hits this, they get 403 immediately.
    """
    if current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


async def get_rate_limited(
    request: Request,
    _: None = Depends(rate_limit)
) -> None:
    """
    Dependency wrapper for rate limiting.
    Usage: @router.get("/search", dependencies=[Depends(get_rate_limited)])
    """
    pass  # rate_limit() already raises HTTPException if exceeded


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db)
) -> User | None:
    """
    Dependency: For endpoints that work for both guests and logged-in users.
    Example: Search works without login, but shows wishlist status if logged in.
    Returns None if no valid token.
    """
    try:
        payload = verify_token(credentials.credentials)
        user_id = int(payload.get("sub"))
        return db.query(User).filter(User.id == user_id).first()
    except Exception:
        return None


# Convenience: combine common dependencies
CommonDeps = {
    "db": Depends(get_db),
    "rate_limit": Depends(get_rate_limited),
}