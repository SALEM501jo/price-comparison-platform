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

WHAT IS NO LONGER HERE: price aggregation moved to services/pricing.py and the
home page's savings query to services/deals.py. Neither was searching, and
both had callers -- the wishlist, the alert notifier, the deals endpoint --
that had to import from a module called "search" to reach them.
"""

from __future__ import annotations



from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.matching import CLOSE, EXACT, SIMILAR, parse, score_match
from app.matching import spelling
from app.models.product import Product
from app.services.pricing import price_summary
from app.schemas.search import (
    MatchDifference,
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
        differences=[
            MatchDifference(
                attribute=c.name,
                label=c.label,
                query_value=c.query_value,
                candidate_value=c.candidate_value,
            )
            for c in result.differences
        ],
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
