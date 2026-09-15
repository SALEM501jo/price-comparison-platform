from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

# Money. Numeric(10, 3), not Float.
#
# JOD is a three-decimal currency -- the scraped feeds literally return
# "136.000" -- and binary floating point cannot represent most decimal
# fractions exactly. 0.1 + 0.2 != 0.3 in float, so "price + delivery" produces
# values that are a hair off, and the app compares those totals to decide which
# store is cheapest and whether a price alert has been met. Two stores a
# thousandth of a dinar apart could be ordered wrongly, and an alert could stay
# unmet at exactly its target.
#
# 10 digits with 3 decimals allows up to 9,999,999.999 JOD, far beyond any
# retail price here.
MONEY = Numeric(10, 3)


class Price(Base):
    __tablename__ = "prices"

    id = Column(Integer, primary_key=True, index=True)
    alias_id = Column(Integer, ForeignKey("product_aliases.id", ondelete="CASCADE"), nullable=False, index=True)
    price = Column(MONEY, nullable=False)
    currency = Column(String(3), default="JOD")
    availability = Column(Boolean, default=True)
    delivery_cost = Column(MONEY, default=0)
    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # When a scraper last READ this price from the store, changed or not.
    # last_updated cannot say that: onupdate only fires when a column actually
    # changes, so a price confirmed unchanged every six hours kept a
    # three-week-old timestamp, and the product page told shoppers "updated 19
    # days ago" beside a figure checked minutes earlier. Kept separate rather
    # than bumping last_updated, which still means "the price changed" -- the
    # sitemap's lastmod and the merchant staleness warning depend on that.
    # Null for merchant prices (a person types those; nothing re-reads them)
    # and for scraped rows not seen since this column was added.
    checked_at = Column(DateTime(timezone=True))

    alias = relationship("ProductAlias", back_populates="prices")

    __table_args__ = (
        # "prices" holds the CURRENT price; history lives in price_history.
        UniqueConstraint("alias_id", name="uq_price_current_per_alias"),
    )
    


class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, index=True)
    alias_id = Column(Integer, ForeignKey("product_aliases.id", ondelete="CASCADE"), nullable=False, index=True)
    price = Column(MONEY, nullable=False)
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
    target_price = Column(MONEY, nullable=False)
    is_active = Column(Boolean, default=True)
    # When the user was last told this alert fired. Prevents re-sending on
    # every scrape while the price stays below target; cleared when it rises
    # back above, so a later drop notifies again.
    notified_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="price_alerts")
    product = relationship("Product", back_populates="price_alerts")