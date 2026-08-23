from sqlalchemy import Column, Integer, String, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base


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
    
    product = relationship("Product", back_populates="aliases")
    store = relationship("Store", back_populates="aliases")
    prices = relationship("Price", back_populates="alias", cascade="all, delete-orphan")
    price_history = relationship("PriceHistory", back_populates="alias", cascade="all, delete-orphan")

    __table_args__ = (
        # Defence in depth for the duplicate-alias bug: the scraper used to
        # insert a new alias on every run. The Python-side guard is the fast
        # path; this makes the invariant impossible to violate at all.
        UniqueConstraint("store_id", "store_product_id", name="uq_alias_store_sku"),
    )