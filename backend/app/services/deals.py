"""
The home page's "biggest savings".

SPLIT OUT OF search.py because it is not a search: nobody typed a query, no
candidate is scored, and no tier is assigned. It is a merchandising query
that happens to read the same tables, and keeping it beside the matching
engine made a 487-line file that covered three unrelated jobs.
"""

from __future__ import annotations


from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from app.models.alias import ProductAlias
from app.models.price import Price
from app.models.product import Product
from app.models.store import Store


def best_savings(db: Session, limit: int = 8) -> list[dict]:
    """
    Products where shopping around saves the most.

    WHAT MAKES A "DEAL" HERE: not a discount off some list price -- we have no
    list price, and inventing one would be dishonest. The saving is the gap
    between the cheapest and the dearest shop selling the same product right
    now, which is the only claim this platform can actually stand behind: buy
    it at the wrong shop and you pay this much more.

    Restricted to NEW stock and to products carried by at least two shops. A
    used unit against a sealed one is not a saving, and a single-shop product
    has nothing to compare.

    TWO BOUNDED QUERIES, NOT ONE UNBOUNDED SCAN. The first version pulled
    every listing in the catalogue into Python and grouped it in a dict --
    480 rows and 14ms at the time, but with no LIMIT anywhere, so the cost
    grew with the catalogue and was paid again every time the five-minute
    cache expired. The min/max/count now happen in the database, which is
    what databases are for, and only the winning `limit` products are read
    back. Cost is now a function of `limit`, not of catalogue size.
    """
    total = (Price.price + func.coalesce(Price.delivery_cost, 0)).label("total")
    store_count = func.count(distinct(ProductAlias.store_id))

    def visible_new(query):
        """The filters that define a comparable offer. Applied to both passes."""
        return (
            query.join(Price, Price.alias_id == ProductAlias.id)
            .join(Store, Store.id == ProductAlias.store_id)
            .filter(Price.availability.is_(True))
            .filter(ProductAlias.condition == "new")
            .filter(Store.visible_to_shoppers())
        )

    # Pass 1: let the database find the biggest gaps.
    ranked = (
        visible_new(
            db.query(
                ProductAlias.product_id.label("product_id"),
                func.min(total).label("lowest"),
                func.max(total).label("dearest"),
                store_count.label("store_count"),
            ).join(Product, Product.id == ProductAlias.product_id)
        )
        .filter(Product.match_category.isnot(None))
        .group_by(ProductAlias.product_id)
        # Two distinct shops, and a gap worth reporting.
        .having(store_count >= 2)
        .having(func.max(total) > func.min(total))
        # Product id as a tie-break so the list is STABLE. Savings tie far more
        # often than they look like they would -- a synthetic catalogue of
        # 1,000 products produced only seven distinct savings, with 142
        # products sharing the top one. Without a second key the front page
        # reshuffles every time the cache expires, for no reason a visitor
        # could see.
        .order_by((func.max(total) - func.min(total)).desc(), ProductAlias.product_id)
        .limit(limit)
        .all()
    )
    if not ranked:
        return []

    summary = {row.product_id: row for row in ranked}

    # Pass 2: read back only the winners, and find which shop is cheapest.
    # Bounded by `limit` products, so a handful of rows however big the
    # catalogue gets.
    rows = visible_new(
        db.query(Product, Store.name.label("store_name"), total).join(
            ProductAlias, ProductAlias.product_id == Product.id
        )
    ).filter(Product.id.in_(list(summary))).all()

    cheapest_store: dict[int, tuple] = {}
    products: dict[int, Product] = {}
    for product, store_name, offer_total in rows:
        products[product.id] = product
        best = cheapest_store.get(product.id)
        if best is None or offer_total < best[0]:
            cheapest_store[product.id] = (offer_total, store_name)

    deals = []
    for product_id, row in summary.items():
        product = products.get(product_id)
        if product is None:
            continue
        saving = row.dearest - row.lowest
        deals.append(
            {
                "id": product.id,
                "canonical_name": product.canonical_name,
                "brand": product.brand,
                "image_url": product.image_url,
                "attributes": product.match_attributes or None,
                "lowest_total_cost": float(row.lowest),
                "highest_total_cost": float(row.dearest),
                "saving": float(saving),
                # Percentage off the dearest price, which is what a shopper
                # avoids paying rather than a markup off some invented RRP.
                "saving_percent": round(float(saving / row.dearest * 100), 1),
                "best_deal_store": cheapest_store.get(product_id, (None, None))[1],
                "store_count": row.store_count,
            }
        )

    # Same ordering as the database applied, re-established because the second
    # pass rebuilt the list from a dict. Id breaks ties so the order is stable.
    deals.sort(key=lambda d: (-d["saving"], d["id"]))
    return deals
