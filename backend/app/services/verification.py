"""
Email verification: issuing, sending and redeeming links.

THE SECURITY SHAPE OF THIS FEATURE:
Verification endpoints are unauthenticated and take an email address, which
makes them the easiest account-enumeration oracle in any application, and a
convenient way to send mail to a stranger's inbox using someone else's
infrastructure. Three things address that:

  - responses never differ based on whether the address exists
  - resending is throttled per address, not only per IP, so rotating IPs does
    not turn the endpoint into a mail cannon aimed at one person
  - tokens are single use and short lived
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from html import escape

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.email_token import EmailToken
from app.models.user import User
from app.services import email as email_service
from app.services.email import Message

logger = logging.getLogger("app.auth")
settings = get_settings()

PURPOSE_VERIFY = "verify_email"

# Minimum gap between verification emails to the same account. Cheap to send,
# annoying to receive: without it the endpoint floods an inbox on request.
RESEND_COOLDOWN = timedelta(minutes=2)


def _hash(token: str) -> str:
    """
    SHA-256 is right here, unlike for passwords.

    A password is low-entropy and guessable, so it needs a deliberately slow
    hash. These tokens are 256 bits of CSPRNG output -- there is nothing to
    brute force, and the hash only has to be one-way and fast.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def issue(db: Session, user: User, purpose: str = PURPOSE_VERIFY) -> str:
    """Create a token, store only its hash, and return the plaintext once."""
    # Any previously issued token for this purpose is retired, so a user who
    # requests a second link cannot leave a first one live.
    db.query(EmailToken).filter(
        EmailToken.user_id == user.id,
        EmailToken.purpose == purpose,
        EmailToken.consumed_at.is_(None),
    ).update({EmailToken.consumed_at: datetime.now(timezone.utc)},
             synchronize_session=False)

    token = secrets.token_urlsafe(32)
    db.add(
        EmailToken(
            token_hash=_hash(token),
            purpose=purpose,
            user_id=user.id,
            expires_at=datetime.now(timezone.utc)
            + timedelta(hours=settings.email_token_ttl_hours),
        )
    )
    db.commit()
    return token


def build_link(token: str) -> str:
    """
    Link into the FRONTEND, not the API.

    Built from configuration rather than the request's Host header: a header is
    client-supplied, and a link assembled from one is a phishing link that the
    application itself sends out under its own name.
    """
    return f"{settings.app_base_url.rstrip('/')}/verify-email?token={token}"


def send_verification(db: Session, user: User) -> bool:
    """Issue a token and email the link. Returns whether the mail went out."""
    token = issue(db, user)
    link = build_link(token)
    hours = settings.email_token_ttl_hours

    # THE BRAND IN THIS EMAIL IS THE FIRST THING A NEW ACCOUNT EVER RECEIVES.
    # It said "PriceCompare" -- the project's working name -- while the site,
    # the sender address and every other email say Ahsan Se3r. A confirmation
    # email from a name the recipient has never heard of reads as phishing,
    # and the likely outcomes are deletion or a spam report, either of which
    # leaves the account unconfirmed and quietly hurts the domain's sending
    # reputation for everyone after them.
    h_link = escape(link, quote=True)
    return email_service.send(
        Message(
            to=user.email,
            subject="Confirm your email for Ahsan Se3r",
            text=(
                "Welcome to Ahsan Se3r.\n\n"
                "Confirm this address to finish setting up your account:\n\n"
                f"{link}\n\n"
                f"The link works once and expires in {hours} hours.\n\n"
                "If you did not create an account, ignore this email -- "
                "nothing will happen.\n"
            ),
            html=(
                "<p>Welcome to Ahsan Se3r.</p>"
                "<p>Confirm this address to finish setting up your account:</p>"
                f'<p><a href="{h_link}">Confirm my email</a></p>'
                f"<p>The link works once and expires in {hours} hours.</p>"
                "<p>If you did not create an account, ignore this email — "
                "nothing will happen.</p>"
            ),
        )
    )


class VerificationError(Exception):
    """The token was missing, expired, already used, or unknown."""


def consume(db: Session, token: str, purpose: str = PURPOSE_VERIFY) -> User:
    """
    Redeem a token and mark the user verified.

    Every failure raises the same exception on purpose. Distinguishing
    "expired" from "already used" from "never existed" tells an attacker
    holding a stale link which of those it is, and none of that helps a
    legitimate user beyond "request a new one".
    """
    if not token:
        raise VerificationError()

    record = (
        db.query(EmailToken)
        .filter(EmailToken.token_hash == _hash(token))
        .filter(EmailToken.purpose == purpose)
        .first()
    )

    if record is None or record.consumed_at is not None:
        raise VerificationError()

    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        # SQLite hands back naive datetimes; Postgres does not.
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise VerificationError()

    user = db.query(User).filter(User.id == record.user_id).first()
    if user is None:
        raise VerificationError()

    record.consumed_at = datetime.now(timezone.utc)
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(timezone.utc)
    db.commit()

    logger.info(
        "Email verified",
        extra={"user_id": user.id, "action": "verify_email", "success": True},
    )
    return user


def can_resend(db: Session, user: User, purpose: str = PURPOSE_VERIFY) -> bool:
    """
    Whether enough time has passed since the last link for this account.

    Throttled per ACCOUNT rather than only per IP: an IP limit alone still lets
    someone rotate addresses and bury a stranger's inbox, using our sending
    reputation to do it.
    """
    latest = (
        db.query(EmailToken)
        .filter(EmailToken.user_id == user.id, EmailToken.purpose == purpose)
        .order_by(EmailToken.created_at.desc())
        .first()
    )
    if latest is None or latest.created_at is None:
        return True

    created_at = latest.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - created_at >= RESEND_COOLDOWN
