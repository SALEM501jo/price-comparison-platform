"""
One store's listing of one product.

WHAT BELONGS HERE VS ON Product:
A `Product` is a model -- "iPhone 15 128GB Black" -- and is shared by every
shop that sells it. A `ProductAlias` is one shop's actual unit: what they call
it, what they charge, and what condition it is in. Anything describing the
specific handset in the specific shop belongs on this side of the line, or one
merchant's worn second-hand phone ends up describing everyone else's listing.
"""

import enum

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Condition(str, enum.Enum):
    """
    What state the unit is in.

    Stored as a plain string column rather than a PostgreSQL enum: adding a
    value to a database enum needs ALTER TYPE and cannot be reversed without
    rewriting the column. This class is the vocabulary; the column is text.
    """

    new = "new"
    used = "used"
    refurbished = "refurbished"

    @property
    def is_second_hand(self) -> bool:
        """Whether the details a buyer needs about wear apply."""
        return self is not Condition.new


# New and used are never compared against each other, so a product page and a
# search result carry one figure per group rather than one overall. A shopper
# choosing between a sealed phone and a scratched one is making a different
# decision from choosing between two sealed ones, and a single "best price"
# collapses the two.
COMPARISON_GROUPS = ("new", "second_hand")


def comparison_group(condition: str | None) -> str:
    """Which price table a listing belongs in."""
    return "new" if (condition or "new") == Condition.new.value else "second_hand"


class ProductAlias(Base):
    __tablename__ = "product_aliases"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    store_id = Column(Integer, ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True)

    store_product_name = Column(String(255), nullable=False)
    store_product_id = Column(String(100))
    store_product_url = Column(String(500))

    match_confidence = Column(Float, default=0.0)
    match_method = Column(String(20), default="manual")

    # --- Condition of this particular unit -------------------------------
    # Scraped listings are new: a retailer's own feed does not sell worn
    # stock. Merchant listings say which they are.
    condition = Column(String(16), nullable=False, default=Condition.new.value, index=True)

    # Null for a new unit. "Unknown" and "100%" are different claims, and a
    # sealed phone makes neither.
    battery_health = Column(Integer)
    has_damage = Column(Boolean)
    damage_notes = Column(String(500))
    warranty_months = Column(Integer)
    listing_notes = Column(String(1000))

    product = relationship("Product", back_populates="aliases")
    store = relationship("Store", back_populates="aliases")
    prices = relationship("Price", back_populates="alias", cascade="all, delete-orphan")
    price_history = relationship("PriceHistory", back_populates="alias", cascade="all, delete-orphan")

    # uselist=False: the unique constraint on listing_photos.alias_id already
    # makes this one-to-one, and letting SQLAlchemy hand back a list would
    # invite callers to write photo[0] against an invariant the database
    # already guarantees.
    photo = relationship(
        "ListingPhoto",
        back_populates="alias",
        uselist=False,
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        # Defence in depth for the duplicate-alias bug: the scraper used to
        # insert a new alias on every run. The Python-side guard is the fast
        # path; this makes the invariant impossible to violate at all.
        UniqueConstraint("store_id", "store_product_id", name="uq_alias_store_sku"),
    )

    @property
    def comparison_group(self) -> str:
        return comparison_group(self.condition)

    @property
    def is_second_hand(self) -> bool:
        return self.comparison_group == "second_hand"
