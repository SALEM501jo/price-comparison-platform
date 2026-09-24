"""
The Matching Lab: one search, explained step by step, beside the alternative.

WHY THIS EXISTS. The argument this project rests on -- that string similarity
cannot tell one product from another and structured attributes can -- was
stated in a docstring (matching/scorer.py) and a README table. Both are
claims a reader has to take on trust. The Lab lets anyone test the claim with
their own words: type a search, type how stores name things, and watch both
methods rank them.

NOTHING HERE DECIDES ANYTHING. Every score comes from the same calls the site
makes: read_query() is search's own reading of a query (spelling correction
included), listings are parsed with the store's category as a hint exactly as
ingest parses them, and score_match() is the scorer. This module only records
what those calls did, so the Lab can never explain a search the site does not
run.

It touches no database and no network. Its whole cost is parsing at most
MAX_LISTINGS short strings, and the request model bounds every input.
"""

from __future__ import annotations

from app.matching import CATEGORY_RULES, EXCLUDED, arabic, normalize, parse, score_match
from app.matching.parser import store_refuses
from app.schemas.explain import (
    AttributeWeight,
    ComparisonOut,
    ExplainRequest,
    ExplainResponse,
    ListingExplanation,
    QueryExplanation,
    ReadingStep,
)
from app.services.search import read_query

# Why a listing scored what it did. The client writes the sentence; these are
# the facts it is written from.
SCORED = "scored"                    # compared attribute by attribute
GATED = "gated"                      # a gate attribute (brand) disagreed
OTHER_CATEGORY = "other_category"    # a laptop offered for a phone search
NOTHING_TO_SCORE = "nothing_to_score"  # the query named only a gate (a brand)
REFUSED_BY_STORE = "refused_by_store"  # the store's own category says "not ours"
UNRECOGNISED = "unrecognised"        # not a phone, laptop or monitor we can read
QUERY_UNREAD = "query_unread"        # the query itself parsed to nothing


def lcs_length(a: str, b: str) -> int:
    """
    Length of the longest common subsequence of two strings.

    Bit-parallel (Allison-Dix, as refined by Hyyro): each row of the textbook
    dynamic-programming table is one integer, and one character of `b`
    updates the whole row in a few arithmetic operations. Same answer as the
    table -- tests/test_explain.py checks it against one on random strings --
    in time proportional to len(b) rather than len(a) * len(b).
    """
    if not a or not b:
        return 0
    masks: dict[str, int] = {}
    for i, ch in enumerate(a):
        masks[ch] = masks.get(ch, 0) | (1 << i)
    full = (1 << len(a)) - 1
    row = full
    for ch in b:
        matches = row & masks.get(ch, 0)
        row = ((row + matches) | (row - matches)) & full
    return len(a) - bin(row).count("1")


def string_similarity(query: str, title: str) -> float:
    """
    The alternative this engine replaced, given every advantage it can have.

    A normalised Indel similarity, 0-100 -- what rapidfuzz.fuzz.ratio
    computes, and the measure scorer.py's docstring was measured with. Both
    strings are first put through normalize(), the same cleaning the engine
    gets: lowercase, punctuation gone, Arabic folded and read as English
    tokens. So the comparison the Lab draws is between two ways of RANKING,
    not between a method that was handed clean text and one that was not.

    On scorer.py's own example it reproduces the documented figures exactly:
    "iPhone 11 Pro Black 128GB" against the right listing scores 67.9, tied
    with the 256GB model and below the Pro Max at 70.0.
    """
    a, b = normalize(query), normalize(title)
    if not a and not b:
        return 100.0
    return round(200 * lcs_length(a, b) / (len(a) + len(b)), 1)


def _reading_steps(typed: str, searched: str) -> list[ReadingStep]:
    """The text as it passes through each stage that changed it."""
    steps = [ReadingStep(stage="typed", text=typed)]
    if searched != typed:
        steps.append(ReadingStep(stage="spelling", text=searched))
    if arabic.has_arabic(searched):
        steps.append(ReadingStep(stage="arabic", text=arabic.prepare(searched.lower())))
    steps.append(ReadingStep(stage="normalized", text=normalize(searched)))
    return steps


def _comparison(c) -> ComparisonOut:
    return ComparisonOut(
        attribute=c.name,
        label=c.label,
        weight=c.weight,
        query_value=c.query_value,
        candidate_value=c.candidate_value,
        matched=c.matched,
    )


def explain(request: ExplainRequest) -> ExplainResponse:
    reading = read_query(request.query, allow_correction=request.correct)
    query = reading.parsed
    rules = CATEGORY_RULES.get(query.category) if query.specified else None

    query_out = QueryExplanation(
        query=request.query,
        steps=_reading_steps(request.query, reading.text),
        corrected_query=reading.corrected_query,
        corrections=reading.corrections,
        category=query.category if rules else None,
        attributes=query.specified,
        weights=[
            AttributeWeight(
                attribute=a.name, label=a.label, weight=a.weight, gate=a.gate
            )
            for a in (rules.attributes if rules else ())
        ],
    )

    gate_names = {a.name for a in rules.attributes if a.gate} if rules else set()

    listings = []
    for item in request.listings:
        hint = item.store_category
        # Exactly as ingest reads a listing: the store's category as a hint,
        # defaults applied, evidence required.
        listing = parse(item.title, hint=hint)
        similarity = string_similarity(request.query, item.title)

        result = None
        gate = None
        if listing.category is None:
            outcome = REFUSED_BY_STORE if store_refuses(hint) else UNRECOGNISED
        elif rules is None:
            outcome = QUERY_UNREAD
        elif listing.category != query.category:
            outcome = OTHER_CATEGORY
        else:
            result = score_match(query, listing)
            failed_gate = next(
                (c for c in result.comparisons if c.name in gate_names and not c.matched),
                None,
            )
            if failed_gate is not None:
                outcome, gate = GATED, _comparison(failed_gate)
            elif not result.comparisons:
                outcome = NOTHING_TO_SCORE
            else:
                outcome = SCORED

        listings.append(
            ListingExplanation(
                title=item.title,
                store_category=hint,
                category=listing.category,
                attributes=listing.specified,
                outcome=outcome,
                score=result.score if result and outcome == SCORED else 0.0,
                tier=result.tier if result and outcome == SCORED else EXCLUDED,
                comparisons=(
                    [_comparison(c) for c in result.comparisons]
                    if result and outcome == SCORED
                    else []
                ),
                gate=gate,
                string_similarity=similarity,
            )
        )

    return ExplainResponse(query=query_out, listings=listings)
