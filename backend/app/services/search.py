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

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.matching import CLOSE, EXACT, SIMILAR, parse, score_match
from app.models.alias import ProductAlias
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
    term = f"%{escape_like(raw_query)}%"
    fallback = db.query(Product)
    if category:
        fallback = fallback.filter(Product.category == category)
    return (
        fallback.filter(
            or_(
                Product.canonical_name.ilike(term, escape="\\"),
                Product.brand.ilike(term, escape="\\"),
            )
        )
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
            Price.price,
            Price.delivery_cost,
            Price.availability,
            Store.name.label("store_name"),
        )
        .join(Price, Price.alias_id == ProductAlias.id)
        .join(Store, Store.id == ProductAlias.store_id)
        .filter(ProductAlias.product_id.in_(ids))
        .all()
    )

    summary: dict[int, dict] = {}
    for row in rows:
        # Out-of-stock listings are excluded from every statistic. Counting
        # them in store_count while excluding them from the price range (the
        # old behaviour) reported "4 stores" for a product buyable at one.
        if not row.availability:
            continue

        bucket = summary.setdefault(
            row.product_id,
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


def _to_response(product: Product, result, prices: dict | None) -> MatchedProduct:
    prices = prices or {}
    price_values = prices.get("prices") or []
    return MatchedProduct(
        id=product.id,
        canonical_name=product.canonical_name,
        brand=product.brand,
        category=product.category,
        image_url=product.image_url,
        attributes=product.match_attributes or None,
        lowest_price=min(price_values) if price_values else None,
        highest_price=max(price_values) if price_values else None,
        lowest_total_cost=prices.get("best_total"),
        store_count=len(prices.get("stores") or ()),
        best_deal_store=prices.get("best"),
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

    interpretation = SearchInterpretation(
        query=raw_query,
        category=parsed.category if parsed.specified else None,
        attributes=parsed.specified,
        structured=bool(parsed.specified),
    )

    empty = TieredSearchResponse(
        interpretation=interpretation, total=0, page=page, limit=limit, sort=sort
    )

    candidates = _candidates(db, parsed, raw_query, category)
    if not candidates:
        return empty

    scored = []
    for candidate in candidates:
        other = parse(candidate.canonical_name, category=candidate.match_category)
        result = score_match(parsed, other)
        if result.is_usable:
            scored.append((candidate, result))

    if not scored and not parsed.specified:
        # Unstructured query (e.g. "playstation"): the scorer has nothing to
        # work with, so surface the name matches rather than nothing at all.
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
