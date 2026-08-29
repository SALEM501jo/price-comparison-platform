"""
Tiered product search.

Two stages, deliberately separated:

  1. CANDIDATE GENERATION -- cheap, in the database, narrows thousands of rows
     to a few hundred using indexed columns.
  2. RERANKING -- expensive, in Python, scores each candidate on weighted
     attribute agreement and assigns it a tier.

Doing the scoring in SQL is not possible (the weights live in the category
rules), and doing the filtering in Python is what made the old engine load the
entire table on every request.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from sqlalchemy import distinct, func, or_
from sqlalchemy.orm import Session

from app.matching import CLOSE, EXACT, SIMILAR, parse, score_match
from app.matching import spelling
from app.models.alias import ProductAlias, comparison_group
from app.models.price import Price
from app.models.product import Product
from app.models.store import Store
from app.schemas.search import (
    MatchedProduct,
    SearchInterpretation,
    TierCounts,
    TieredSearchResponse,
)

# Cap on rows pulled into Python for reranking. Scoring is microseconds per
# candidate, so this is generous; it exists to bound worst-case memory.
CANDIDATE_LIMIT = 500


def escape_like(term: str) -> str:
    r"""
    Neutralise LIKE wildcards in user input.

    SQLAlchemy parameterises the value, so this is not SQL injection -- but an
    unescaped "%" or "_" is still interpreted as a wildcard. A query of "%%%%"
    matches every row in the table, which is a cheap denial-of-service against
    an unindexed ILIKE scan.
    """
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


SORT_KEYS = {
    # Products with nothing in stock have no price. Sorting them by a
    # substituted 0 would put unbuyable items at the top of a cheapest-first
    # list, so the None flag pushes them last under every ordering.
    "price_asc": lambda p: (p.lowest_total_cost is None, p.lowest_total_cost or 0),
    "price_desc": lambda p: (p.lowest_total_cost is None, -(p.lowest_total_cost or 0)),
    "name": lambda p: (p.canonical_name or "").lower(),
}
DEFAULT_SORT = "price_asc"


def _candidates(
    db: Session, parsed, raw_query: str, category: str | None = None
) -> list[Product]:
    """
    Narrow the catalogue before scoring.

    Prefers the indexed (match_category, brand) pair. Falls back to a name
    search when the query did not parse into anything structured -- a search
    for "playstation" should still return something.
    """
    query = db.query(Product)
    if category:
        query = query.filter(Product.category == category)

    if parsed.specified:
        filters = [Product.match_category == parsed.category]
        brand = parsed.get("brand")
        if brand:
            filters.append(Product.brand == brand)
        structured = query.filter(*filters).limit(CANDIDATE_LIMIT).all()
        if structured:
            return structured

    # Fallback: plain name search.
    #
    # BOTH the raw query and its normalised form are tried. For a Latin query
    # they are near enough the same string and the second costs nothing. For
    # an ARABIC one they are completely different: product names in the
    # catalogue are Latin, so matching the raw Arabic against them finds
    # nothing at all, while the normalised form has already been folded to
    # canonical English tokens ("سوني" -> "sony"). Without this an Arabic
    # query that does not parse structurally returns an empty page rather
    # than the name matches it should.
    terms = {raw_query.strip(), parsed.normalized}
    conditions = []
    for candidate_term in terms:
        if not candidate_term:
            continue
        like = f"%{escape_like(candidate_term)}%"
        conditions.append(Product.canonical_name.ilike(like, escape="\\"))
        conditions.append(Product.brand.ilike(like, escape="\\"))

    if not conditions:
        return []

    fallback = db.query(Product)
    if category:
        fallback = fallback.filter(Product.category == category)
    return (
        fallback.filter(or_(*conditions))
        .limit(CANDIDATE_LIMIT)
        .all()
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


def _to_response(product: Product, result, prices: dict | None) -> MatchedProduct:
    """
    Build one search result.

    The headline figures describe NEW stock only. Second-hand offers get their
    own two fields so the UI can say "from 850 JOD, or 620 used" rather than
    quietly quoting the used price as though it were the same offer.
    """
    groups = prices or {}
    new = groups.get("new") or {}
    second_hand = groups.get("second_hand") or {}

    price_values = new.get("prices") or []
    return MatchedProduct(
        id=product.id,
        canonical_name=product.canonical_name,
        brand=product.brand,
        category=product.category,
        image_url=product.image_url,
        attributes=product.match_attributes or None,
        lowest_price=min(price_values) if price_values else None,
        highest_price=max(price_values) if price_values else None,
        lowest_total_cost=new.get("best_total"),
        store_count=len(new.get("stores") or ()),
        best_deal_store=new.get("best"),
        second_hand_from=second_hand.get("best_total"),
        second_hand_store_count=len(second_hand.get("stores") or ()),
        match_score=result.score,
        match_tier=result.tier,
        differences=result.differences,
    )


def search_products(
    db: Session,
    raw_query: str,
    *,
    category: str | None = None,
    sort: str = DEFAULT_SORT,
    page: int = 1,
    limit: int = 20,
    allow_correction: bool = True,
) -> TieredSearchResponse:
    """
    Run a tiered search and return results grouped by match quality.

    Pagination applies PER TIER rather than across a flattened list. Paging a
    combined list would let a long tail of "similar" results push the exact
    match onto page two, which defeats the point of the tiers. `counts` carries
    the pre-pagination totals so the UI can show "3 of 40".
    """
    sort = sort if sort in SORT_KEYS else DEFAULT_SORT
    page = max(1, page)
    limit = max(1, limit)

    # require_evidence=False: the rule exists to keep accessories OUT of the
    # catalogue at ingest. A query of "MacBook" names no storage or chip and
    # still means every MacBook.
    # Neither rule applies to a query: requires_any keeps accessories out of
    # the CATALOGUE, and defaults describe what a LISTING implies. A shopper
    # who omits a word has not asserted its absence.
    parsed = parse(raw_query, require_evidence=False, apply_defaults=False)

    # SPELLING, second. The correction is only accepted when it makes the
    # query MORE understood than what was typed -- strictly more attributes
    # extracted. Correcting whenever a word happens to be near a known one
    # would let "iphone a16" drift to "a15", and the two are different
    # products; requiring the correction to earn its place means a typo that
    # changes nothing measurable is left exactly as the shopper wrote it.
    #
    # Runs AFTER the first parse, not before, so a query that already works
    # never pays for it and can never be altered.
    search_query = raw_query
    corrected_query: str | None = None
    corrections: dict[str, str] = {}

    candidate_text, candidate_fixes = spelling.correct(raw_query)
    if candidate_fixes and allow_correction:
        candidate = parse(
            candidate_text, require_evidence=False, apply_defaults=False
        )
        if len(candidate.specified) > len(parsed.specified):
            parsed = candidate
            search_query = candidate_text
            corrected_query = candidate_text
            corrections = candidate_fixes

    interpretation = SearchInterpretation(
        query=raw_query,
        category=parsed.category if parsed.specified else None,
        attributes=parsed.specified,
        structured=bool(parsed.specified),
        corrected_query=corrected_query,
        corrections=corrections,
    )

    empty = TieredSearchResponse(
        interpretation=interpretation, total=0, page=page, limit=limit, sort=sort
    )

    candidates = _candidates(db, parsed, search_query, category)
    if not candidates:
        return empty

    scored = []
    for candidate in candidates:
        other = parse(candidate.canonical_name, category=candidate.match_category)
        result = score_match(parsed, other)
        if result.is_usable:
            scored.append((candidate, result))

    if not scored:
        # Nothing cleared the 70% bar. Surface the candidates unscored, in the
        # lowest tier, rather than showing an empty page.
        #
        # WHY THIS NOW COVERS STRUCTURED QUERIES TOO. It used to require that
        # the query parsed to nothing at all, which left a whole class of
        # searches dead: a query naming only GATE attributes has plenty of
        # meaning and no score. "iphone a16" resolves to brand=apple and
        # nothing else -- A16 is the chip, and phones do not carry a processor
        # attribute -- so every candidate was excluded for having no scoreable
        # agreement, and a shopper who had named a brand we stock was told
        # nothing matched.
        #
        # The tier is honest about what these are: they arrive as "similar"
        # with no score and no difference list, which is exactly what they
        # are -- name and brand matches the engine could not rank.
        scored = [(c, _unscored()) for c in candidates]

    price_map = price_summary(db, (c.id for c, _ in scored))

    buckets: dict[str, list[MatchedProduct]] = {EXACT: [], CLOSE: [], SIMILAR: []}
    for candidate, result in scored:
        item = _to_response(candidate, result, price_map.get(candidate.id))
        buckets.setdefault(result.tier, []).append(item)

    counts = TierCounts(
        exact=len(buckets[EXACT]),
        close=len(buckets[CLOSE]),
        similar=len(buckets[SIMILAR]),
    )

    key = SORT_KEYS[sort]
    start = (page - 1) * limit
    end = start + limit

    paged = {}
    has_more = False
    for tier, items in buckets.items():
        items.sort(key=key)
        paged[tier] = items[start:end]
        if len(items) > end:
            has_more = True

    return TieredSearchResponse(
        interpretation=interpretation,
        exact=paged[EXACT],
        close=paged[CLOSE],
        similar=paged[SIMILAR],
        total=sum(len(v) for v in paged.values()),
        counts=counts,
        page=page,
        limit=limit,
        sort=sort,
        has_more=has_more,
    )


def _unscored():
    """Placeholder result for name-only matches, reported in the lowest tier."""
    from app.matching.scorer import MatchResult

    return MatchResult(score=0.0, tier=SIMILAR, comparisons=())


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
