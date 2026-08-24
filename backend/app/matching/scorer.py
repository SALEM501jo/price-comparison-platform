"""
Attribute-based match scoring.

WHY NOT STRING SIMILARITY:
Levenshtein-style ratios count characters, not meaning. Measured against a real
catalogue, the listing "Apple iPhone 11 Pro 128GB Black" scored 67.9 against the
query "iPhone 11 Pro Black 128GB" -- tying exactly with the 256GB model (a
different product at a different price) and ranking BELOW the Pro Max. A
one-character edit (128 -> 256) changes the product; a large edit (word order)
does not. Edit distance sees that backwards, and no threshold value fixes the
ordering.

Scoring attributes instead makes every result explainable: a score is the sum of
the weights of the attributes that agreed, so the UI can say "90% - same model
and storage, different colour" rather than showing an opaque number.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.matching.parser import ParsedProduct
from app.matching.rules import CATEGORY_RULES, DEFAULT_CATEGORY

# Tier thresholds, as a share of the achievable score.
TIER_EXACT = 100.0
TIER_CLOSE = 85.0
TIER_SIMILAR = 70.0

EXACT, CLOSE, SIMILAR, EXCLUDED = "exact", "close", "similar", "excluded"


def tier_for(score: float) -> str:
    if score >= TIER_EXACT:
        return EXACT
    if score >= TIER_CLOSE:
        return CLOSE
    if score >= TIER_SIMILAR:
        return SIMILAR
    return EXCLUDED


@dataclass(frozen=True)
class AttributeComparison:
    name: str
    label: str
    weight: int
    query_value: str | None
    candidate_value: str | None
    matched: bool

    def reason(self) -> str:
        if self.matched:
            return f"same {self.label}"
        if self.candidate_value is None:
            return f"{self.label} not listed"
        return (
            f"different {self.label} "
            f"({self.candidate_value}, not {self.query_value})"
        )


@dataclass(frozen=True)
class MatchResult:
    score: float
    tier: str
    comparisons: tuple[AttributeComparison, ...]

    @property
    def differences(self) -> list[str]:
        """Human-readable reasons this is not an exact match. For the UI."""
        return [c.reason() for c in self.comparisons if not c.matched]

    @property
    def is_usable(self) -> bool:
        return self.tier != EXCLUDED


def score_match(query: ParsedProduct, candidate: ParsedProduct) -> MatchResult:
    """
    Score a candidate product against a parsed query, 0-100.

    Rules:
      - Gate attributes (brand) must agree, or the candidate is excluded
        outright regardless of how many other specs coincide.
      - Attributes the user did NOT specify are ignored, not penalised, so
        searching "iPhone 11 Pro" does not punish a listing for having a colour.
      - The score is earned weight / achievable weight, so a vague query and a
        precise one are both scored out of 100.
    """
    rules = CATEGORY_RULES.get(query.category, CATEGORY_RULES[DEFAULT_CATEGORY])

    if candidate.category != query.category:
        return MatchResult(0.0, EXCLUDED, ())

    for attribute in rules.attributes:
        if not attribute.gate:
            continue
        wanted = query.get(attribute.name)
        found = candidate.get(attribute.name)
        if wanted is not None and wanted != found:
            # Record WHY it was gated out. Returning an empty comparison list
            # here would make an excluded result indistinguishable from a
            # perfect one to any caller reading `differences`.
            gate_failure = AttributeComparison(
                name=attribute.name,
                label=attribute.label,
                weight=attribute.weight,
                query_value=wanted,
                candidate_value=found,
                matched=False,
            )
            return MatchResult(0.0, EXCLUDED, (gate_failure,))

    # Start from the category's FULL weight and deduct only what the user
    # asked for and did not get.
    #
    # WHY NOT earned/specified: normalising by the attributes the query happens
    # to mention makes the score depend on how much was typed. "iPhone 15
    # 512GB Black" specifies 67 points' worth, so a storage mismatch costs
    # 24/67 = 36% and drops to 64 -- excluded -- while the same mismatch on a
    # fuller query costs 24/95 = 25% and lands at 75, comfortably "similar".
    # The identical difference between the identical two products fell in
    # different tiers depending on the wording of the search.
    #
    # Deducting from the total instead measures how much of the PRODUCT'S
    # identity differs, which is a property of the two products alone.
    # Attributes the user did not mention are not mismatches, so they cost
    # nothing.
    total_weight = sum(a.weight for a in rules.scoreable())
    if total_weight == 0:
        return MatchResult(0.0, EXCLUDED, ())

    lost = 0
    specified = 0
    comparisons: list[AttributeComparison] = []

    for attribute in rules.scoreable():
        wanted = query.get(attribute.name)
        if wanted is None:
            continue  # not asked for -> neither earned nor lost

        specified += 1
        found = candidate.get(attribute.name)
        matched = wanted == found
        if not matched:
            lost += attribute.weight

        comparisons.append(
            AttributeComparison(
                name=attribute.name,
                label=attribute.label,
                weight=attribute.weight,
                query_value=wanted,
                candidate_value=found,
                matched=matched,
            )
        )

    if specified == 0:
        # Query carried no scoreable attributes (e.g. a bare brand name).
        return MatchResult(0.0, EXCLUDED, tuple(comparisons))

    score = round((total_weight - lost) / total_weight * 100, 1)
    return MatchResult(score, tier_for(score), tuple(comparisons))
