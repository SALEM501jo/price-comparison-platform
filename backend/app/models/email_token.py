from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class EmailToken(Base):
    """
    A single-use, expiring token delivered by email.

    ONLY THE HASH IS STORED. The token itself exists in the email and nowhere
    else, so a database dump -- or a backup, or a leaked read replica -- yields
    no working links. Same reasoning as the refresh tokens: storing a
    credential you only ever need to *compare* is storing it for no reason.

    A lookup by hash is also why no constant-time comparison is needed here:
    the secret is never compared byte by byte, it is used as an index key.

    `purpose` keeps one table serving verification today and password reset
    later, without a token issued for one being usable for the other.
    """

    __tablename__ = "email_tokens"

    id = Column(Integer, primary_key=True, index=True)

    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    purpose = Column(String(32), nullable=False, index=True)

    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    # Set the moment it is redeemed. Single use: a link forwarded, quoted in a
    # support ticket, or sitting in a mailbox backup cannot be replayed.
    consumed_at = Column(DateTime(timezone=True))

    user = relationship("User", back_populates="email_tokens")
