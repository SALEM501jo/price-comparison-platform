"""
Forgotten passwords: a single-use reset LINK, never a password in an email.

WHY NOT EMAIL A NEW PASSWORD, which is the obvious reading of "send them a
new password":

  - Email is not encrypted end to end. A password mailed in plaintext crosses
    several servers in the clear and then sits in an inbox forever. Anyone who
    reads that mailbox next year owns the account.
  - It would mean the SERVER generated and briefly knew the password. Every
    other part of this system is built so that never happens -- bcrypt exists
    precisely so a database dump reveals nothing.
  - People do not change a password that was chosen for them, so a credential
    they never picked and cannot remember becomes permanent, and gets reused
    on other sites.

A reset link has none of those properties: it expires, it works once, it
carries no secret that is useful after it is spent, and the user chooses the
password themselves so it is never transmitted or stored anywhere in the clear.

The token machinery is entirely reused from app/services/verification.py --
issue(), consume() and can_resend() are already parameterised by `purpose`, and
the email_tokens table already stores a SHA-256 hash with an expiry and a
single-use stamp. This module is the reset-shaped use of it.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from html import escape

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.user import User
from app.security.password import hash_password
from app.services import tokens as token_service
from app.services import verification
from app.services.email import Message
from app.services import email as email_service

logger = logging.getLogger("app.auth")
settings = get_settings()

PURPOSE_RESET = "reset_password"


def build_reset_link(token: str) -> str:
    """
    Into the FRONTEND, and built from configuration.

    Never from the request's Host header: that is client-supplied, and a link
    assembled from one is a phishing link the application sends out under its
    own name, to a user who has every reason to trust it.
    """
    return f"{settings.app_base_url.rstrip('/')}/reset-password?token={token}"


def can_request(db: Session, user: User) -> bool:
    """Throttled per ACCOUNT, so rotating IPs cannot bury one inbox."""
    return verification.can_resend(db, user, purpose=PURPOSE_RESET)


def _describe_minutes(minutes: int) -> str:
    """"60" -> "1 hour", "90" -> "90 minutes": what a person reads in an email."""
    if minutes % 60 == 0:
        hours = minutes // 60
        return "1 hour" if hours == 1 else f"{hours} hours"
    return f"{minutes} minutes"


def send_reset(db: Session, user: User) -> bool:
    """Issue a reset token and email the link."""
    # A reset link carries its own, much shorter lifetime -- see
    # password_reset_ttl_minutes in app/config.py for why.
    minutes = settings.password_reset_ttl_minutes
    token = verification.issue(
        db, user, purpose=PURPOSE_RESET, ttl=timedelta(minutes=minutes)
    )
    link = build_reset_link(token)
    lifetime = _describe_minutes(minutes)

    return email_service.send(
        Message(
            to=user.email,
            subject="Reset your Ahsan Se3r password",
            text=(
                "Someone asked to reset the password for this account.\n\n"
                "Choose a new password here:\n\n"
                f"{link}\n\n"
                f"The link works once and expires in {lifetime}.\n\n"
                # This used to add "and nobody can use this link without
                # opening it from your inbox". That stopped being true once the
                # mail provider rewrote links for click tracking: a copy of the
                # link exists in the provider's systems too. The reassurance a
                # recipient can rely on is the short expiry, so that is what it
                # now says.
                "If this was not you, ignore this email. Your password has "
                "not changed.\n"
            ),
            html=(
                "<p>Someone asked to reset the password for this account.</p>"
                # Escaped although the link is built here, from settings and a
                # URL-safe token: every email follows one rule -- nothing
                # interpolated into HTML unescaped -- so the next edit to this
                # string cannot be the one that forgets.
                f'<p><a href="{escape(link, quote=True)}">Choose a new password</a></p>'
                f"<p>The link works once and expires in {lifetime}.</p>"
                "<p>If this was not you, ignore this email. Your password has "
                "not changed.</p>"
            ),
        )
    )


class ResetError(Exception):
    """The token was missing, expired, already used, or unknown."""


def reset_password(db: Session, token: str, new_password: str) -> User:
    """
    Spend the token and set the new password.

    TWO THINGS HAPPEN BEYOND THE OBVIOUS:

    The address is marked verified. Redeeming this token requires having read
    the mail sent to it, which is exactly what verification proves -- refusing
    to accept that would make a user confirm the same mailbox twice.

    EVERY REFRESH TOKEN IS REVOKED. This is the point of a password reset. If
    somebody else is holding a live session -- which is the most likely reason
    a person is resetting in the first place -- leaving that session working
    would make the reset theatre. The user signs in again afterwards; so does
    the attacker, except they cannot.
    """
    try:
        user = verification.consume(db, token, purpose=PURPOSE_RESET)
    except verification.VerificationError as exc:
        # Same exception for expired, spent and unknown. Telling an attacker
        # holding a stale link which of those it is helps only them.
        raise ResetError() from exc

    user.password_hash = hash_password(new_password)
    db.commit()

    revoked = token_service.revoke_all_for_user(db, user.id, "password_reset")

    logger.warning(
        "Password reset completed",
        extra={
            "user_id": user.id,
            "action": "password_reset",
            "success": True,
            "target": f"{revoked} sessions revoked",
        },
    )
    return user
