"""
Turning a verified provider identity into a local account.

THIS FILE IS THE SECURITY CRUX OF SOCIAL SIGN-IN. Everything before it proves
"Google says this is subject 1234, whose address is alice@gmail.com". This is
where that becomes "and therefore you are user 87 on our site", and the wrong
rule here is account takeover rather than a bug.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.logging_config import get_security_logger
from app.models.oauth_identity import OAuthIdentity
from app.models.user import User, UserRole
from app.services import tokens as token_service
from app.services.oauth.flow import OAuthError, ProviderIdentity

logger = get_security_logger("app.oauth")


class ProviderEmailUnverified(OAuthError):
    """The provider would not vouch for the address, so nothing may be linked."""


def link_or_create(db: Session, identity: ProviderIdentity) -> User:
    """
    Find, link, or create the local account this provider identity belongs to.
    """
    existing = (
        db.query(OAuthIdentity)
        .filter(
            OAuthIdentity.provider == identity.provider,
            OAuthIdentity.provider_subject == identity.subject,
        )
        .first()
    )
    if existing is not None:
        # The link was made once, against a verified address, and the subject
        # is what identifies the person from then on. The address is not
        # re-checked here on purpose: Apple's private relay changes if the
        # user unlinks and relinks, and requiring it to match would lock them
        # out of their own account.
        return existing.user

    # NOTHING BELOW THIS LINE MAY RUN ON AN UNVERIFIED ADDRESS. A provider
    # that will not say the mailbox is confirmed has given us a string the
    # user typed, and typing "alice@gmail.com" into a signup form is not
    # evidence of anything. Linking on it would hand Alice's account to
    # whoever typed it.
    if not identity.email or not identity.email_verified:
        raise ProviderEmailUnverified(
            f"{identity.provider} did not assert a verified email address"
        )

    email = identity.email.strip().lower()
    now = datetime.now(timezone.utc)

    user = db.query(User).filter(func.lower(User.email) == email).first()

    if user is None:
        # No password at all, rather than a random one nobody knows: a row
        # with a real hash in it says "this account has a password", and the
        # difference matters to /auth/login and to anyone reading the table.
        user = User(
            email=email,
            password_hash=None,
            role=UserRole.user,
            # Provider-asserted, so verification mail would be noise -- and
            # noise that reads as phishing to somebody who just proved control
            # of the mailbox thirty seconds ago through Google.
            email_verified_at=now,
        )
        db.add(user)
        db.flush()
        logger.info(
            "Account created through social sign-in",
            extra={"user_id": user.id, "action": "oauth_register",
                   "target": identity.provider, "success": True},
        )

    elif user.email_verified_at is None:
        # THE ACCOUNT TAKEOVER PATH, and the reason this branch is not simply
        # "link it".
        #
        # An unverified local account is one where somebody chose a password
        # for an address they never proved they own. The attack is patient and
        # cheap: register victim@gmail.com, set a password, wait. When the
        # real owner later clicks "Continue with Google", a naive link would
        # join their identity to the attacker's row -- and the attacker's
        # password still opens it. They would then be inside the real owner's
        # account for as long as they cared to stay, with the victim seeing
        # nothing at all.
        #
        # So the password is cleared and every session is revoked. Google has
        # just proved who owns the mailbox; the person who typed a password
        # into it has proved nothing, and loses the only two things that would
        # let them back in. The real owner can set a password whenever they
        # like through the existing forgot-password flow, which is itself
        # gated on that same mailbox.
        user.password_hash = None
        user.email_verified_at = now
        db.flush()
        token_service.revoke_all_for_user(
            db, user.id, reason="oauth_link_to_unverified_account"
        )
        logger.warning(
            "Linked a provider to an unverified account: password cleared "
            "and sessions revoked",
            extra={"user_id": user.id, "action": "oauth_link_unverified",
                   "target": identity.provider, "success": True},
        )

    else:
        # Both sides independently proved control of the same mailbox, which
        # is the whole basis on which they are the same person.
        logger.info(
            "Provider linked to an existing verified account",
            extra={"user_id": user.id, "action": "oauth_link",
                   "target": identity.provider, "success": True},
        )

    db.add(
        OAuthIdentity(
            provider=identity.provider,
            provider_subject=identity.subject,
            user_id=user.id,
        )
    )
    db.commit()
    db.refresh(user)
    return user
