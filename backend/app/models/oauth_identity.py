from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class OAuthIdentity(Base):
    """
    One provider account (a Google or Apple login) bound to one local user.

    WHY THE SUBJECT AND NOT THE EMAIL. The provider's `sub` claim is a stable,
    opaque identifier for that person at that provider; the address attached
    to it is not. Corporate addresses change hands when someone leaves a job,
    and an Apple private-relay address stops resolving the moment the user
    revokes access to this app. Keying on the address would mean a later
    holder of alice@company.com signs in and lands in Alice's account -- so
    the email is used ONCE, at link time, to prove both sides control the same
    mailbox, and never again as an identifier.

    A user may hold several identities: the same person can sign in with
    Google today and add Apple later, and both must reach one account rather
    than silently forking their wishlist and price alerts in two.

    THE CASCADE IS DELIBERATE AND SHARED. Account deletion removes the users
    row; ON DELETE CASCADE is what makes this table disappear with it, so the
    delete-my-account flow covers provider links without having to know this
    table exists. Removing the cascade would leave orphaned rows whose unique
    (provider, provider_subject) pair then blocks the same person from ever
    signing up again.
    """

    __tablename__ = "oauth_identities"

    id = Column(Integer, primary_key=True, index=True)

    # "google" / "apple". A plain string rather than an Enum: adding a third
    # provider is a configuration change, and an enum would make it a
    # migration as well.
    provider = Column(String(32), nullable=False)

    # The provider's `sub` claim. Google's is a 21-digit number and Apple's is
    # a longer opaque string; 255 covers both with room to spare.
    provider_subject = Column(String(255), nullable=False)

    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="oauth_identities")

    __table_args__ = (
        # The pair, not the subject alone: two providers can and do hand out
        # the same-looking identifier, and nothing guarantees Google's number
        # space is disjoint from anyone else's. Unique here is what stops one
        # provider account being linked to two local users, which would make
        # "who does this login belong to?" answerable two ways.
        UniqueConstraint(
            "provider", "provider_subject", name="uq_oauth_identity_provider_subject"
        ),
    )
