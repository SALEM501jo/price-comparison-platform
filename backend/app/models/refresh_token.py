from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class RefreshToken(Base):
    """
    A record of one issued refresh token, so it can be revoked.

    WHY THIS TABLE EXISTS: a JWT is valid until it expires, full stop. Nothing
    about the token itself can withdraw it, so a stolen 7-day refresh token
    grants a week of access no matter what the user does. Recording the `jti`
    lets /auth/refresh check the token against server-side state, which is the
    only thing that makes "log out everywhere" or "revoke a leaked session"
    possible.

    The access token deliberately gets no such record. Checking one would mean
    a database read on every single request, which is exactly the cost the
    stateless short-lived design exists to avoid -- its 15-minute lifetime is
    what limits the damage instead.
    """

    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)

    # The token's own unique id (the "jti" claim). Only the id is stored --
    # never the token itself, so a leaked database dump cannot be replayed.
    jti = Column(String(36), unique=True, nullable=False, index=True)

    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    issued_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)

    # Set when the token is rotated away or explicitly revoked. Null means live.
    revoked_at = Column(DateTime(timezone=True))

    # The token issued in its place on rotation. Turns the records into a
    # chain, which is what makes replay of an old link detectable.
    replaced_by_jti = Column(String(36))

    user = relationship("User", back_populates="refresh_tokens")

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None
