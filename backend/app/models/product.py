from sqlalchemy import Column, Integer, String, JSON, Index
from sqlalchemy.orm import relationship
from app.database import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)

    # Human-facing name, shown in the UI. Kept separate from the matching
    # attributes below: normalising a name for comparison destroys the casing
    # and wording a shopper expects to read.
    canonical_name = Column(String(255), nullable=False, index=True)

    brand = Column(String(100), index=True)
    category = Column(String(100), index=True)
    image_url = Column(String(500))
    description = Column(String(1000))

    # --- Structured matching data (see app/matching/) ---

    # Which rule set describes this product: "phones", "laptops", ...
    match_category = Column(String(50), index=True)

    # Extracted attributes, e.g. {"model": "iphone 11", "variant": "pro",
    # "storage": "128gb", "color": "black"}.
    #
    # Deliberately JSON rather than one column per attribute: the attributes
    # that matter are defined per category in app/matching/rules.py, so adding
    # a category (washing machines: capacity_kg, energy_rating) must not
    # require a schema migration. Postgres can index into JSONB when the
    # catalogue grows large enough to need it.
    match_attributes = Column(JSON)

    aliases = relationship("ProductAlias", back_populates="product", cascade="all, delete-orphan")
    wishlist_items = relationship("WishlistItem", back_populates="product", cascade="all, delete-orphan")
    price_alerts = relationship("PriceAlert", back_populates="product", cascade="all, delete-orphan")

    __table_args__ = (
        # Candidate generation filters by category before scoring.
        Index("ix_products_match_category_brand", "match_category", "brand"),
    )
