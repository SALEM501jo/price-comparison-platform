from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from app.database import Base


class Store(Base):
    __tablename__ = "stores"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    website = Column(String(255))
    logo_url = Column(String(500))
    is_active = Column(Integer, default=1)

    aliases = relationship("ProductAlias", back_populates="store")