"""
Browsing the catalogue, for a visitor who has not typed anything yet.

WHY THIS EXISTS, and why it is not deals.py: the home page was built entirely
on `best_savings`, which by definition can only show a product carried by TWO
OR MORE shops. Measured against the real catalogue that is exactly ONE product
out of 364 with a price -- so the landing page of a site with 423 products and
418 photographs rendered a single card and looked broken.

That is not a bug in the savings query. A saving between two shops is the
honest claim this platform exists to make, and inventing more of them would be
the one unforgivable thing here. The fix is to stop asking one merchandising
query to be the whole page: savings answer "where is shopping around worth
it", browsing answers "what do you even have". They are different questions
and they get different queries.

Split into its own module for the same reason pricing/deals/search are split:
nobody typed anything, nothing is scored, no tier is assigned, and no saving
is claimed.
"""

from __future__ import annotations

from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from app.models.alias import ProductAlias
from app.models.price import Price
from app.models.product import Product
from app.models.store import Store
from app.services import photos

# The categories this platform carries, in the order the home page shows them.
# Read from rules.py rather than hardcoded would be circular -- the matching
# engine imports nothing from the app, and this is app-side presentation.
BROWSABLE = ("phones", "laptops", "monitors")


def _total():
    """Price plus delivery -- what a buyer actually pays.

    A function rather than a module constant: a SQLAlchemy label() is bound
    into the query it is compiled for, and sharing one instance across two
    queries makes the second one carry the first one's alias.
    """
    return (Price.price + func.coalesce(Price.delivery_cost, 0)).label("total")


def _visible_offers(query):
    """The filters that define an offer a shopper may see. Applied everywhere."""
    return (
        query.join(Price, Price.alias_id == ProductAlias.id)
        .join(Store, Store.id == ProductAlias.store_id)
        .filter(Price.availability.is_(True))
        .filter(Store.visible_to_shoppers())
    )


def category_counts(db: Session) -> list[dict]:
    """
    How many buyable products sit in each category.

    Counts what a shopper can actually reach, not what the table holds: a
    product with no in-stock price from a visible shop is not something to
    advertise on the front page, and a category tile promising 169 phones that
    leads to 40 is worse than no tile.
    """
    rows = (
        _visible_offers(
            db.query(
                Product.match_category.label("category"),
                func.count(distinct(Product.id)).label("count"),
            ).join(ProductAlias, ProductAlias.product_id == Product.id)
        )
        .filter(Product.match_category.in_(BROWSABLE))
        .group_by(Product.match_category)
        .all()
    )

    found = {row.category: row.count for row in rows}
    # Fixed order, and categories with nothing in them are dropped rather than
    # shown as zero -- an empty tile is an invitation to a dead end.
    return [
        {"category": name, "count": found[name]}
        for name in BROWSABLE
        if found.get(name)
    ]


def total_in(db: Session, category: str | None = None) -> int:
    """
    How many buyable products a browse would eventually reach.

    Counts DISTINCT PRODUCTS, not offers: a product carried by three shops is
    one thing to look at, and paging that counted offers would promise pages
    that do not exist.
    """
    query = _visible_offers(
        db.query(func.count(distinct(ProductAlias.product_id)))
        .select_from(ProductAlias)
        .join(Product, Product.id == ProductAlias.product_id)
    ).filter(ProductAlias.condition == "new")

    if category:
        query = query.filter(Product.match_category == category)

    return query.filter(Product.match_category.in_(BROWSABLE)).scalar() or 0


def _ranked(db: Session, category: str | None, limit: int, offset: int = 0):
    """
    The cheapest `limit` buyable products, optionally within one category.

    ORDERED BY PRICE, CHEAPEST FIRST, not by id or insertion date. "Newest"
    would be meaningless here: the scraper inserts in feed order, so it really
    means "whatever that shop happened to list last". Cheapest first is at
    least a claim a price-comparison site can defend.

    Products WITHOUT a picture sort LAST rather than being filtered out. Five
    of 423 have no image; dropping them would quietly hide real stock, while
    letting them lead would put placeholder tiles at the top of the front page.
    """
    total = _total()

    query = _visible_offers(
        db.query(
            ProductAlias.product_id.label("product_id"),
            func.min(total).label("lowest"),
            func.count(distinct(ProductAlias.store_id)).label("store_count"),
        ).join(Product, Product.id == ProductAlias.product_id)
    ).filter(ProductAlias.condition == "new")

    if category:
        query = query.filter(Product.match_category == category)

    return (
        query.filter(Product.match_category.in_(BROWSABLE))
        # NULLS LAST is not portable to SQLite, so the flag is computed and
        # sorted on instead -- the tests run on SQLite deliberately.
        .group_by(ProductAlias.product_id, Product.image_url)
        .order_by(
            (Product.image_url.is_(None)).asc(),
            func.min(total).asc(),
            ProductAlias.product_id.asc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )


def browse(
    db: Session,
    *,
    category: str | None = None,
    limit: int = 12,
    offset: int = 0,
) -> list[dict]:
    """
    A sample of the catalogue: real products, with prices and pictures.

    WITH NO CATEGORY, THE RESULT IS INTERLEAVED ACROSS CATEGORIES, and that is
    the whole point of this function rather than an ornament. Ranking the
    whole catalogue by price alone returns twelve monitors: the cheapest
    monitor is 69 JOD and the cheapest phone is several times that, so one
    global sort silently turns the front page of a phone-led comparison site
    into a monitor aisle. Interleaving shows what the catalogue actually
    holds.

    With a category named, plain cheapest-first is right -- somebody who asked
    for phones wants phones, in an order that means something.

    Bounded either way: at most one ranking query per category plus two
    lookups, and every one of them carries a LIMIT. Cost is a function of
    `limit`, not of catalogue size.
    """
    if category:
        ranked = _ranked(db, category, limit, offset)
    else:
        # Round-robin, cheapest-first within each category.
        #
        # EACH CATEGORY IS ASKED FOR THE FULL `limit`, not for a 1/3 share.
        # A share would cap the result at share x 3, so a lopsided catalogue
        # -- six phones and one monitor -- returns three rows for a limit of
        # five and the page comes back half empty. Over-fetching and trimming
        # is what lets a deep category cover for a thin one. Still bounded:
        # three queries, each carrying the same LIMIT.
        #
        # Offset is applied AFTER interleaving, not pushed into each query:
        # page 2 of a round-robin is not the round-robin of each category's
        # page 2. Each category is asked for enough rows to cover the window,
        # which stays bounded because the route caps limit and page.
        window = limit + offset
        per_category = [_ranked(db, name, window) for name in BROWSABLE]
        longest = max((len(rows) for rows in per_category), default=0)
        ranked = [
            rows[i]
            for i in range(longest)
            for rows in per_category
            if i < len(rows)
        ][offset:window]

    if not ranked:
        return []

    summary = {row.product_id: row for row in ranked}
    products = {
        product.id: product
        for product in db.query(Product).filter(Product.id.in_(list(summary))).all()
    }

    # Which shop is cheapest, for the "from X at Y" line. Same second pass the
    # savings query makes, bounded to the products actually being returned.
    cheapest: dict[int, tuple] = {}
    rows = (
        _visible_offers(
            db.query(ProductAlias.product_id, Store.name.label("store"), _total())
        )
        .filter(ProductAlias.product_id.in_(list(summary)))
        .filter(ProductAlias.condition == "new")
        .all()
    )
    for product_id, store, offer_total in rows:
        best = cheapest.get(product_id)
        if best is None or offer_total < best[0]:
            cheapest[product_id] = (offer_total, store)

    photo_ids = photos.product_ids_with_photos(db, list(summary))

    results = []
    for product_id, row in summary.items():
        product = products.get(product_id)
        if product is None:
            continue
        results.append(
            {
                "id": product.id,
                "canonical_name": product.canonical_name,
                "brand": product.brand,
                "category": product.match_category,
                "image_url": photos.display_image_url(
                    product.id, product.image_url, product.id in photo_ids
                ),
                "attributes": product.match_attributes or None,
                "lowest_total_cost": float(row.lowest),
                "best_deal_store": cheapest.get(product_id, (None, None))[1],
                "store_count": row.store_count,
            }
        )

    # The database already ordered these; the dict round-trip is what loses it.
    order = {pid: i for i, pid in enumerate(summary)}
    results.sort(key=lambda item: order[item["id"]])
    return results
