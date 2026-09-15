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

import re

from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from app.models.alias import ProductAlias
from app.models.price import Price
from app.models.product import Product
from app.models.store import Store
from app.services import photos
from app.services.offers import current_offer

# The categories this platform carries, in the order the home page shows them.
# Read from rules.py rather than hardcoded would be circular -- the matching
# engine imports nothing from the app, and this is app-side presentation.
BROWSABLE = ("phones", "laptops", "monitors")

# The most rows a single family scan will read. Far above the real
# catalogue (364 products across three categories) and low enough that a
# runaway import cannot turn one request into a full table scan.
_FAMILY_SCAN_LIMIT = 5000


def _total():
    """Price plus delivery -- what a buyer actually pays.

    A function rather than a module constant: a SQLAlchemy label() is bound
    into the query it is compiled for, and sharing one instance across two
    queries makes the second one carry the first one's alias.
    """
    return (Price.price + func.coalesce(Price.delivery_cost, 0)).label("total")


def _visible_offers(query):
    """
    The filters that define an offer a shopper may see. Applied everywhere.

    current_offer(), not just store visibility: every tile here carries a
    "from X JOD at Y" line and every category tile a count, and a listing the
    store has removed -- or one nobody has re-read in two days -- would keep
    both. Browse is the page a visitor lands on before searching, so it is the
    first place a price that no longer exists would be believed.
    """
    return (
        query.join(Price, Price.alias_id == ProductAlias.id)
        .join(Store, Store.id == ProductAlias.store_id)
        .filter(Price.availability.is_(True))
        .filter(current_offer())
    )


def category_counts(db: Session) -> list[dict]:
    """
    How many buyable products sit in each category.

    Counts what a shopper can actually reach, not what the table holds: a
    product with no in-stock price from a visible shop is not something to
    advertise on the front page, and a category tile promising 169 phones that
    leads to 40 is worse than no tile.

    COUNTS FAMILIES, THE SAME UNIT THE LISTING RENDERS. Counting products here
    while `browse` collapses colour variants would put "151 phones" on a tile
    whose page stops at 73 -- the identical broken promise these tiles made
    when they pointed at a search. The number on the tile and the number of
    tiles behind it are the same query or they will drift.
    """
    found = {name: len(_families(db, name)) for name in BROWSABLE}
    # Fixed order, and categories with nothing in them are dropped rather than
    # shown as zero -- an empty tile is an invitation to a dead end.
    return [
        {"category": name, "count": found[name]}
        for name in BROWSABLE
        if found.get(name)
    ]


def total_in(db: Session, category: str | None = None) -> int:
    """
    How many tiles a browse would eventually show.

    Counts FAMILIES, not products, because that is what the page renders: 151
    phones are 101 handsets once colours are collapsed, and a count of 151
    above a list that stops at 101 is the same broken promise the category
    tiles used to make.
    """
    if category:
        return len(_families(db, category))
    return sum(len(_families(db, name)) for name in BROWSABLE)



def _family_key(name: str, attributes: dict | None) -> tuple:
    """
    What makes two listings THE SAME HANDSET IN A DIFFERENT COLOUR.

    Measured problem: of 151 phones, only 71 are distinct handsets. The first
    page of a browse showed 24 tiles carrying 14 phones -- four Honor X5c, three
    Infinix Smart 20 -- which is a colour swatch, not a catalogue.

    THE KEY IS ATTRIBUTES *PLUS* THE NAME'S LEADING SEGMENT, and both halves
    are load-bearing:

      - Attributes alone merge different products. An Infinix Tab XPAD 30E (a
        TABLET) and an Infinix Smart 20 both parse to
        (infinix, model=None, base, 128gb, 4gb), because the model pattern does
        not cover either name. Grouping on that would have hidden the tablet.
      - The name alone merges across storage. "Infinix Smart 20 ... 64GB" and
        "... 128GB" share a leading segment and are genuinely different things
        to buy.

    THE NAME SEGMENT IS ONLY CONSULTED WHEN THE MODEL DID NOT PARSE. When the
    model is known, brand + model + variant + storage + memory already
    identifies a handset, and dragging the name in splits families that should
    merge: "VIVO Y02 Orchid Blue" and "VIVO Y02 Cosmic Grey" carry no comma, so
    the segment is the whole name including the colour, and the two stay apart
    for no reason. The segment exists to separate products the MODEL PATTERN
    MISSED, which is exactly the Infinix case above.

    THE COLOUR IS NEVER PARSED OUT OF THE NAME, deliberately. Stripping the
    colour word fails on marketing names: Honor writes "Tidal Blue" and
    "Midnight Black", so removing "blue"/"black" leaves "Tidal " and
    "Midnight " -- different strings for the same handset. Cutting at the first
    comma instead keeps the model segment, which these feeds all put first.
    """
    a = attributes or {}
    model = a.get("model")
    segment = (
        ""
        if model
        else re.sub(r"[^a-z0-9]+", " ", (name or "").split(",")[0].lower()).strip()
    )
    return (
        a.get("brand"),
        model,
        a.get("variant"),
        a.get("storage"),
        a.get("ram"),
        segment,
    )


def _families(db: Session, category: str | None) -> list[dict]:
    """
    Every browsable handset in a category, one entry per colour family,
    cheapest first.

    WHY THIS READS THE WHOLE CATEGORY rather than a page of it: the grouping
    key is built in Python from a product name, so it cannot go into the ORDER
    BY. Grouping after a LIMIT would give pages of unpredictable size and a
    total that disagreed with them.

    That trades away the "cost is a function of limit, not catalogue size"
    property the paged version had. At 364 products it is a few hundred rows,
    and the ROUTE CACHES the whole payload on the catalogue version, so this
    runs once per scrape rather than once per visitor. It is the right trade
    at this size and the wrong one at 50,000 products -- at which point the
    family key belongs in a column, computed at ingest, and indexed.
    """
    rows = _ranked(db, category, limit=_FAMILY_SCAN_LIMIT)
    if not rows:
        return []

    products = {
        product.id: product
        for product in db.query(Product)
        .filter(Product.id.in_([r.product_id for r in rows]))
        .all()
    }

    families: dict[tuple, dict] = {}
    for row in rows:
        product = products.get(row.product_id)
        if product is None:
            continue
        key = _family_key(product.canonical_name, product.match_attributes)
        existing = families.get(key)
        if existing is None:
            # `rows` is already cheapest-first, so the FIRST one seen is the
            # cheapest and becomes the family's representative.
            families[key] = {"row": row, "product": product, "variants": 1}
        else:
            existing["variants"] += 1

    return list(families.values())


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
        families = _families(db, category)
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
        per_category = [_families(db, name) for name in BROWSABLE]
        longest = max((len(rows) for rows in per_category), default=0)
        families = [
            rows[i]
            for i in range(longest)
            for rows in per_category
            if i < len(rows)
        ]

    # Sliced AFTER interleaving and after grouping: page 2 of a round-robin is
    # not the round-robin of each category's page 2.
    families = families[offset:offset + limit]

    if not families:
        return []

    summary = {f["row"].product_id: f["row"] for f in families}
    products = {f["product"].id: f["product"] for f in families}
    variants = {f["product"].id: f["variants"] for f in families}

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
                # How many colours of this exact handset the catalogue holds,
                # the representative included. 1 means there is nothing else
                # to say, so the UI stays quiet.
                "variant_count": variants.get(product_id, 1),
            }
        )

    # The database already ordered these; the dict round-trip is what loses it.
    order = {pid: i for i, pid in enumerate(summary)}
    results.sort(key=lambda item: order[item["id"]])
    return results
