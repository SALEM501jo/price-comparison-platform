"""
JWT token creation and verification.
SECURITY PRINCIPLE: Tokens must be tamper-proof and short-lived.
"""

from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from fastapi import HTTPException, status
from app.config import get_settings

settings = get_settings()


def create_access_token(data: dict) -> str:
    """
    Create a short-lived access token (15 minutes).
    'data' should contain at minimum: {"sub": user_id, "role": "user"}
    
    WHY 15 MINUTES:
    If this token is stolen (XSS, network sniffing), the attacker has 
    only 15 minutes of access. After that, it's useless.
    """
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload.update({
        "exp": expire,
        "type": "access",
        "iat": datetime.now(timezone.utc),  # Issued at
    })
    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm
    )


def create_refresh_token(data: dict) -> str:
    """
    Create a long-lived refresh token (7 days).
    This is stored in the database and can be revoked.
    
    WHY SEPARATE TOKENS:
    Access token is used for every API call (fast, stateless).
    Refresh token is used only at /auth/refresh (rare, stateful).
    If access token leaks → 15 min damage.
    If refresh token leaks → revoke it in DB → attacker locked out.
    """
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.refresh_token_expire_days
    )
    payload.update({
        "exp": expire,
        "type": "refresh",
        "iat": datetime.now(timezone.utc),
    })
    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm
    )


def verify_token(token: str, token_type: str = "access") -> dict:
    """
    Verify a JWT token's signature and claims.
    
    SECURITY CHECKS:
    1. Signature valid? (secret key matches)
    2. Not expired? (exp > now)
    3. Correct token type? (access vs refresh)
    4. Contains required claims? (sub = user_id)
    
    WHY WE CHECK TYPE:
    If someone sends a refresh token to a protected endpoint,
    we reject it. Refresh tokens are ONLY for /auth/refresh.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # Decode and verify signature + expiry
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        
        # Verify token type (access vs refresh)
        if payload.get("type") != token_type:
            raise credentials_exception
        
        # Verify subject (user_id) exists
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
            
        return payload
        
    except JWTError:
        # JWTError covers: expired signature, invalid signature, 
        # malformed token, missing claims
        raise credentials_exception


def verify_refresh_token(token: str) -> dict:
    """
    Convenience wrapper for refresh token verification.
    """
    return verify_token(token, token_type="refresh")