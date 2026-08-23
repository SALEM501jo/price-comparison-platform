from sqlalchemy import Column, Integer, Float, String, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Price(Base):
    __tablename__ = "prices"

    id = Column(Integer, primary_key=True, index=True)
    alias_id = Column(Integer, ForeignKey("product_aliases.id", ondelete="CASCADE"), nullable=False, index=True)
    price = Column(Float, nullable=False)
    currency = Column(String(3), default="JOD")
    availability = Column(Boolean, default=True)
    delivery_cost = Column(Float, default=0.0)
    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    alias = relationship("ProductAlias", back_populates="prices")

    __table_args__ = (
        # "prices" holds the CURRENT price; history lives in price_history.
        UniqueConstraint("alias_id", name="uq_price_current_per_alias"),
    )
    


class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, index=True)
    alias_id = Column(Integer, ForeignKey("product_aliases.id", ondelete="CASCADE"), nullable=False, index=True)
    price = Column(Float, nullable=False)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    alias = relationship("ProductAlias", back_populates="price_history")


class WishlistItem(Base):
    __tablename__ = "wishlist_items"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="wishlist_items")
    product = relationship("Product", back_populates="wishlist_items")

    __table_args__ = (
        # The router checks for an existing row first; without this, two
        # concurrent requests can both pass that check and insert.
        UniqueConstraint("user_id", "product_id", name="uq_wishlist_user_product"),
    )


class PriceAlert(Base):
    __tablename__ = "price_alerts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    target_price = Column(Float, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="price_alerts")
    product = relationship("Product", back_populates="price_alerts")