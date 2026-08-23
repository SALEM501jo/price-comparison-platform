"""
JWT creation and verification.
SECURITY PRINCIPLE: Tokens must be tamper-proof, short-lived, and identifiable.

WHY PyJWT AND NOT python-jose:
python-jose 3.3.0 was the last release (2021) and carries five known
advisories, including PYSEC-2025-185 with no fixed version available. It also
pulls in `ecdsa`, which has its own unfixed advisory. Since this module signs
every token the platform issues, an unmaintained dependency here is the single
worst place to accept known CVEs. PyJWT is actively maintained and the API
difference is small.
"""

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, status

from app.config import get_settings

settings = get_settings()

ACCESS = "access"
REFRESH = "refresh"

# Claims every token must carry. Listing them explicitly means a token missing
# one is rejected by the library rather than silently treated as valid.
REQUIRED_CLAIMS = ["exp", "iat", "sub", "type", "jti"]


def _build(data: dict, token_type: str, lifetime: timedelta) -> tuple[str, str]:
    """Encode a token. Returns (token, jti)."""
    now = datetime.now(timezone.utc)
    token_id = str(uuid.uuid4())

    payload = data.copy()
    payload.update(
        {
            "exp": now + lifetime,
            "iat": now,
            "type": token_type,
            # A unique id per token. Without it two tokens issued in the same
            # second for the same user are byte-identical, so neither can be
            # revoked or audited individually.
            "jti": token_id,
        }
    )
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, token_id


def create_access_token(data: dict) -> str:
    """
    Short-lived access token (15 minutes by default).
    'data' should contain at minimum: {"sub": user_id, "role": "user"}

    WHY SO SHORT: this token is sent on every request and is not revocable.
    Its lifetime IS its blast radius -- if it leaks, the attacker has 15
    minutes, then it is worthless.
    """
    token, _ = _build(data, ACCESS, timedelta(minutes=settings.access_token_expire_minutes))
    return token


def create_refresh_token(data: dict) -> tuple[str, str]:
    """
    Long-lived refresh token (7 days by default).
    Returns (token, jti) so the caller can record it for revocation.

    WHY SEPARATE TOKENS:
    The access token is used constantly and is stateless, so it must be short.
    The refresh token is used rarely, at /auth/refresh only, so it can afford a
    database lookup -- which is what makes revoking it possible.
    """
    token, token_id = _build(
        data, REFRESH, timedelta(days=settings.refresh_token_expire_days)
    )
    return token, token_id


def verify_token(token: str, token_type: str = ACCESS) -> dict:
    """
    Verify a token's signature, expiry, required claims, and type.

    WHY THE TYPE CHECK MATTERS:
    Without it a 7-day refresh token would be accepted at every protected
    endpoint, silently turning the 15-minute access window into a week.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            # A list, never a bare string: passing the algorithm from the
            # token's own header is the classic algorithm-confusion hole.
            algorithms=[settings.jwt_algorithm],
            options={"require": REQUIRED_CLAIMS},
        )
    except jwt.PyJWTError:
        # Covers expired signature, bad signature, malformed token, and
        # missing required claims. Deliberately one generic response: telling
        # a caller which of those failed is free reconnaissance.
        raise credentials_exception

    if payload.get("type") != token_type:
        raise credentials_exception

    return payload


def verify_refresh_token(token: str) -> dict:
    """Convenience wrapper for refresh token verification."""
    return verify_token(token, token_type=REFRESH)
