import enum
from sqlalchemy import Column, Integer, String, DateTime, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class UserRole(str, enum.Enum):
    user = "user"
    # A shop owner who submits their own prices. Deliberately NOT a flavour of
    # admin: a merchant has more power than a shopper over their own store and
    # none at all over anyone else's, which is a different shape of authority
    # from "can do everything".
    merchant = "merchant"
    admin = "admin"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), default=UserRole.user, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Null until the address is confirmed. A timestamp rather than a boolean:
    # "when" answers questions a flag cannot, and costs the same to store.
    email_verified_at = Column(DateTime(timezone=True))

    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    email_tokens = relationship("EmailToken", back_populates="user", cascade="all, delete-orphan")
    wishlist_items = relationship("WishlistItem", back_populates="user", cascade="all, delete-orphan")
    price_alerts = relationship("PriceAlert", back_populates="user", cascade="all, delete-orphan")

    # At most one store per account, enforced by a unique index on the store
    # side. uselist=False makes that a scalar here rather than a list of one.
    store = relationship("Store", back_populates="owner", uselist=False)