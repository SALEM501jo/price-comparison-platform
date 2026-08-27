"""
Stores: both the ones we scrape and the ones that submit their own prices.

TWO KINDS OF STORE, ONE TABLE.

A scraped store (SmartBuy, iGeek) has a website and no owner -- nobody signs
in on its behalf. A merchant store (a shop whose only shopfront is a Facebook
page) has an owner, a phone number, and no feed at all. They differ in where
their prices come from, not in what they are, so they share a table and the
whole search path treats them identically.

`owner_user_id` is what separates them, and `is_verified` is what protects
them: anyone can register and claim to be a well-known shop, so a merchant's
prices stay invisible to shoppers until an admin confirms the claim. Without
that gate the cheapest listing on the site would be whatever a competitor felt
like inventing under a rival's name.
"""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    and_,
    or_,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Store(Base):
    __tablename__ = "stores"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    website = Column(String(255))
    logo_url = Column(String(500))
    is_active = Column(Integer, default=1)

    # --- Merchant stores -----------------------------------------------
    # Null for scraped stores: SmartBuy has no account here and never will.
    # A user owns at most one store; enforced by a unique index rather than
    # by trusting the endpoint that creates them.
    owner_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )

    # How a shopper actually buys from these shops. There is no checkout and
    # no delivery -- the transaction happens on the phone, which is how this
    # end of the Jordanian market already works. Offering a Buy button we
    # cannot honour would be worse than offering a number that rings.
    phone = Column(String(32))
    whatsapp = Column(String(32))
    facebook_url = Column(String(500))

    # False until an admin confirms the claim. Scraped stores are seeded
    # verified because their prices come from their own public feed.
    is_verified = Column(Boolean, nullable=False, default=False)
    verified_at = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    aliases = relationship("ProductAlias", back_populates="store")
    owner = relationship("User", back_populates="store")

    @property
    def is_merchant(self) -> bool:
        """A store somebody signs in to manage, rather than one we scrape."""
        return self.owner_user_id is not None

    @staticmethod
    def visible_to_shoppers():
        """
        SQL predicate for stores whose prices may reach a shopper.

        The same rule as `is_publicly_visible` below, expressed so it can go
        into a WHERE clause. Every query that surfaces a price applies this;
        filtering in Python after the fact would still leak the price through
        aggregates like "lowest price" and "number of stores".

        A scraped store (owner_user_id IS NULL) needs only to be active. A
        merchant store must also be verified, because until an admin has
        checked the claim there is nothing connecting the name on the listing
        to the shop it names.
        """
        return and_(
            Store.is_active == 1,
            or_(Store.owner_user_id.is_(None), Store.is_verified.is_(True)),
        )

    @property
    def is_publicly_visible(self) -> bool:
        """
        Whether this store's prices may be shown to shoppers.

        Scraped stores qualify on being active. Merchant stores must also be
        verified -- this is the single check that stops an unverified claim
        from reaching the search results, and it is applied in the query
        rather than in the template, so no caller can forget it.
        """
        if not self.is_active:
            return False
        return self.is_verified or not self.is_merchant
