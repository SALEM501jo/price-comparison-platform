"""
What a product costs, aggregated across the shops that sell it.

SPLIT OUT OF search.py because the callers gave the game away: the wishlist
router and the price-alert notifier both imported price_summary() from a
module named "search", and neither of them searches for anything. Deciding
what a product costs and deciding which products answer a query are different
jobs -- the first is arithmetic over money, the second is relevance -- and
only one of them is allowed to be approximate.
"""

from __future__ import annotations


from decimal import Decimal
from typing import Iterable

from sqlalchemy import exists
from sqlalchemy.orm import Session

from app.models.alias import ProductAlias, comparison_group
from app.models.price import Price
from app.models.product import Product
from app.models.store import Store
from app.services.offers import current_offer


def has_current_offer():
    """
    SQL predicate for a query over Product: at least one shop offers it now.

    For the paths that hand a shopper a PRODUCT rather than a price -- search
    candidates and type-ahead suggestions. Each of those used to offer any
    product in the table, so a listing the store had since removed still came
    up as a suggestion, and the suggestion led to a product page that now
    answers 404. Anything offered to a shopper must lead somewhere.

    OUT-OF-STOCK OFFERS COUNT, deliberately, because they count on the product
    page: the offer is real and the page shows it as such. This asks the same
    question the page's 404 rule asks, so the two cannot disagree about whether
    a product exists.

    AN EXISTS, NOT A JOIN. A join would return one row per listing -- a product
    four shops carry would come back four times and use up four of the
    candidate LIMIT's slots -- and a DISTINCT to undo that sorts the whole
    candidate set. EXISTS stops at the first qualifying listing, and every step
    of it is an indexed lookup: product_aliases.product_id, the unique
    prices.alias_id, and the stores primary key. Its cost is per candidate
    row the outer query reads, and those queries all carry a LIMIT.

    CORRELATED ON Product ONLY, explicitly. SQLAlchemy otherwise correlates
    every table the outer query also names, so dropped into a query that
    already joins product_aliases, the subquery would stop asking "does ANY
    listing of this product qualify" and quietly ask it of the outer row's
    listing instead.
    """
    return (
        exists()
        .where(
            ProductAlias.product_id == Product.id,
            Price.alias_id == ProductAlias.id,
            Store.id == ProductAlias.store_id,
            current_offer(),
        )
        .correlate(Product)
    )


def price_summary(db: Session, product_ids: Iterable[int]) -> dict[int, dict]:
    """
    Aggregate prices for many products in ONE query.

    The previous implementation ran a three-table join per product inside the
    result loop -- 20 results meant 21 round trips.

    Public because the wishlist needs the same figures: it used to return a
    hardcoded "lowest_price": 0 rather than duplicate the aggregation.
    """
    ids = list(product_ids)
    if not ids:
        return {}

    rows = (
        db.query(
            ProductAlias.product_id.label("product_id"),
            ProductAlias.condition,
            Price.price,
            Price.delivery_cost,
            Price.availability,
            Store.name.label("store_name"),
        )
        .join(Price, Price.alias_id == ProductAlias.id)
        .join(Store, Store.id == ProductAlias.store_id)
        .filter(ProductAlias.product_id.in_(ids))
        # Only CURRENT offers: from a store a shopper may see (an unverified
        # merchant is invisible), still listed by that store, and -- if
        # scraped -- read recently. Applied in the query rather than after it:
        # this function produces the lowest price, the best-deal store name and
        # the store count, so a row filtered out later would still have moved
        # every one of those numbers. It feeds search cards, the wishlist and
        # the alert emails, so a listing the store removed would otherwise go
        # on winning "best price" and on telling people their target was met.
        .filter(current_offer())
        .all()
    )

    summary: dict[int, dict] = {}
    for row in rows:
        # Out-of-stock listings are excluded from every statistic. Counting
        # them in store_count while excluding them from the price range (the
        # old behaviour) reported "4 stores" for a product buyable at one.
        if not row.availability:
            continue

        # New and second-hand are tallied apart. Folded together, one worn
        # handset makes every product carrying it look like a bargain, and
        # "best deal" goes to the used unit every single time.
        group = comparison_group(row.condition)
        product_bucket = summary.setdefault(row.product_id, {})
        bucket = product_bucket.setdefault(
            group,
            {"prices": [], "totals": [], "stores": set(), "best": None,
             "best_total": None},
        )
        # Decimal throughout: mixing in a float 0.0 would silently promote
        # the sum back to binary floating point and undo the point of the
        # Numeric column.
        total = (row.price or Decimal(0)) + (row.delivery_cost or Decimal(0))
        bucket["prices"].append(row.price)
        bucket["totals"].append(total)
        bucket["stores"].add(row.store_name)
        if bucket["best_total"] is None or total < bucket["best_total"]:
            bucket["best_total"] = total
            bucket["best"] = row.store_name

    return summary


def offers_for(summary: dict, product_id: int, group: str = "new") -> dict:
    """
    One product's figures for one comparison group.

    Defaults to NEW, and every caller outside search relies on that default:
    the wishlist's "lowest price", and — more consequentially — whether a
    price alert has been met.

    WHY ALERTS TRACK NEW STOCK: a shopper who asked to be told when an
    iPhone 15 drops below 700 meant a phone, not a phone with 81% battery and
    a cracked back. Firing on second-hand stock would make the feature
    untrustworthy in the one direction that matters, because the alert cannot
    be un-sent. A shopper who wants used prices is browsing, not waiting.
    """
    return (summary.get(product_id) or {}).get(group) or {}
