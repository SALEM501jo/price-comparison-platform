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

from sqlalchemy.orm import Session

from app.models.alias import ProductAlias, comparison_group
from app.models.price import Price
from app.models.store import Store


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
        # Unverified merchant stores are invisible here. Applied in the query
        # rather than after it: this function produces the lowest price, the
        # best-deal store name and the store count, so a row filtered out
        # later would still have moved every one of those numbers.
        .filter(Store.visible_to_shoppers())
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
