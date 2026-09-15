"""
What counts as an offer a shopper may see, defined once.

A price row is an OFFER only when all of these hold:

  * its store is visible to shoppers -- active, and verified if a merchant's
    (Store.visible_to_shoppers, which this includes);
  * the store still lists it -- ProductAlias.delisted_at is null. A complete
    read of the store's feed that no longer contains the listing, or a link
    check that finds its product page gone, sets that column;
  * for a SCRAPED store, it was read recently -- COALESCE(checked_at,
    last_updated) within settings.scraped_price_max_age_hours. Merchant
    prices are exempt: a person sets those, and they carry their own
    staleness warning on the product page.

WHY ONE PREDICATE. Before this, every query that surfaced a price applied
Store.visible_to_shoppers() and nothing else, so a listing the store had
removed kept its last price in search, the product page, deals, browse, the
sitemap and alert emails -- and could win "best price" with a link to a 404.
Seven call sites each re-deriving "current" is how one of them gets missed.

Every query that joins Price, ProductAlias and Store and shows the result to a
shopper, a search engine or an email filters on current_offer(). Availability
(in stock) is deliberately NOT part of it: an out-of-stock listing the store
still sells is real, and the product page shows it as such.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, func, or_

from app.config import get_settings
from app.models.alias import ProductAlias
from app.models.price import Price
from app.models.store import Store

settings = get_settings()


def freshness_cutoff(now: Optional[datetime] = None) -> datetime:
    """The oldest read a scraped price may have and still be shown."""
    now = now or datetime.now(timezone.utc)
    return now - timedelta(hours=settings.scraped_price_max_age_hours)


def current_offer(now: Optional[datetime] = None):
    """
    SQL predicate: this Price/ProductAlias/Store row is an offer a shopper may see.

    The query must already join Price, ProductAlias and Store. `now` is for
    tests; production passes nothing.
    """
    return and_(
        Store.visible_to_shoppers(),
        ProductAlias.delisted_at.is_(None),
        or_(
            # A merchant store: freshness is the shop's own responsibility.
            Store.owner_user_id.isnot(None),
            func.coalesce(Price.checked_at, Price.last_updated)
            >= freshness_cutoff(now),
        ),
    )
