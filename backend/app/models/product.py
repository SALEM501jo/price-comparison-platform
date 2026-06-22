from sqlalchemy import Column, Integer, String, JSON
from sqlalchemy.orm import relationship
from app.database import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    canonical_name = Column(String(255), nullable=False, index=True)
    brand = Column(String(100), index=True)
    category = Column(String(100), index=True)
    specs = Column(JSON)
    image_url = Column(String(500))
    description = Column(String(1000))

    aliases = relationship("ProductAlias", back_populates="product", cascade="all, delete-orphan")
    wishlist_items = relationship("WishlistItem", back_populates="product", cascade="all, delete-orphan")
    price_alerts = relationship("PriceAlert", back_populates="product", cascade="all, delete-orphan")