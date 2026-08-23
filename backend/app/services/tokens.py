"""
Refresh token lifecycle: issue, rotate, revoke, and detect replay.

THE ATTACK THIS DEFENDS AGAINST:
An attacker steals a refresh token (XSS, a shared machine, a leaked backup).
Without rotation they hold a working 7-day credential and nothing on the server
can tell their requests from the real user's.

With rotation, every use of a refresh token burns it and issues a new one. That
does not stop the theft, but it guarantees the theft becomes *visible*: two
parties now hold tokens from the same chain, and whichever one refreshes second
presents a token that was already used. A token cannot legitimately be used
twice, so that second use is proof of compromise -- and the whole chain is
revoked, logging both parties out. The real user reauthenticates; the attacker
is locked out.

This is the pattern in OAuth 2.0 Security Best Current Practice (refresh token
rotation with automatic reuse detection).
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.logging_config import get_security_logger
from app.models.refresh_token import RefreshToken

settings = get_settings()
logger = get_security_logger("app.auth")


def record_issued(db: Session, jti: str, user_id: int) -> RefreshToken:
    """Store a newly issued refresh token so it can later be revoked."""
    record = RefreshToken(
        jti=jti,
        user_id=user_id,
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(record)
    db.commit()
    return record


def revoke_all_for_user(db: Session, user_id: int, reason: str) -> int:
    """
    Revoke every live refresh token for a user. Returns how many were revoked.

    Used both for "log out everywhere" and as the automatic response to a
    replayed token.
    """
    now = datetime.now(timezone.utc)
    revoked = (
        db.query(RefreshToken)
        .filter(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .update({RefreshToken.revoked_at: now}, synchronize_session=False)
    )
    db.commit()

    if revoked:
        logger.warning(
            "Refresh tokens revoked",
            extra={
                "user_id": user_id,
                "action": "revoke_refresh_tokens",
                "target": reason,
                "success": True,
            },
        )
    return revoked


class TokenReuseError(Exception):
    """A refresh token was presented that had already been used or revoked."""


class TokenUnknownError(Exception):
    """A validly signed refresh token with no server-side record."""


def consume(db: Session, jti: str, user_id: int) -> RefreshToken:
    """
    Spend a refresh token, or raise if it cannot be spent.

    Raises TokenReuseError after revoking the user's whole chain -- a second
    use of a one-time credential means two parties hold it.
    """
    record = db.query(RefreshToken).filter(RefreshToken.jti == jti).first()

    if record is None:
        # Correctly signed but unknown to us. Either it was issued before this
        # table existed, or the secret has leaked and tokens are being forged.
        raise TokenUnknownError()

    if record.revoked_at is not None:
        # REPLAY. Burn the entire chain, not just this token: we cannot tell
        # which party is legitimate, so both must reauthenticate.
        revoke_all_for_user(db, user_id, reason="refresh_token_reuse_detected")
        logger.warning(
            "Refresh token replay detected",
            extra={
                "user_id": user_id,
                "action": "refresh_token_reuse",
                "target": jti,
                "success": False,
            },
        )
        raise TokenReuseError()

    return record


def rotate(db: Session, old: RefreshToken, new_jti: str) -> RefreshToken:
    """Retire the used token and record its replacement, linking the chain."""
    old.revoked_at = datetime.now(timezone.utc)
    old.replaced_by_jti = new_jti
    replacement = RefreshToken(
        jti=new_jti,
        user_id=old.user_id,
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(replacement)
    db.commit()
    return replacement


def purge_expired(db: Session) -> int:
    """
    Delete records for tokens that expired long ago.

    The table is append-heavy, and a row for a token that expired months back
    protects nothing. Keeps a grace period so recent history stays auditable.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    deleted = (
        db.query(RefreshToken)
        .filter(RefreshToken.expires_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted
