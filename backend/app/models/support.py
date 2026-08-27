"""
Messages sent through the contact form.

STORED, NOT ONLY EMAILED. Mail is the least reliable link in this system: the
console backend discards it in development, SMTP fails in production, and a
support request that vanishes is worse than one that was never sent, because
the person who wrote it is waiting. The row is the record; the email is a
notification about the row.
"""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


class SupportMessage(Base):
    __tablename__ = "support_messages"

    id = Column(Integer, primary_key=True, index=True)

    # The address to reply to. Kept separate from the account below: someone
    # locked out of their account still needs to be able to write in, and the
    # address they type may be the one they cannot sign in with.
    email = Column(String(255), nullable=False, index=True)
    subject = Column(String(150))
    body = Column(Text, nullable=False)

    # Null when nobody was signed in. SET NULL rather than CASCADE: deleting
    # an account must not erase the support history that explains why.
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    handled = Column(Boolean, nullable=False, default=False, index=True)
