"""Structured product matching: parse names into attributes, then score them."""

from app.matching.parser import ParsedProduct, detect_category, normalize, parse
from app.matching.rules import CATEGORY_RULES, CategoryRules
from app.matching.scorer import (
    CLOSE,
    EXACT,
    EXCLUDED,
    SIMILAR,
    AttributeComparison,
    MatchResult,
    score_match,
    tier_for,
)

__all__ = [
    "parse",
    "normalize",
    "detect_category",
    "ParsedProduct",
    "score_match",
    "tier_for",
    "MatchResult",
    "AttributeComparison",
    "EXACT",
    "CLOSE",
    "SIMILAR",
    "EXCLUDED",
    "CATEGORY_RULES",
    "CategoryRules",
]
