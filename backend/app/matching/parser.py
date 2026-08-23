"""
Rules-driven product name parser.

Turns "Apple iPhone 11 Pro 128GB Black" into structured attributes:
    {brand: apple, model: iphone 11, variant: pro, storage: 128gb, color: black}

The SAME function is used on both sides of the system:
  - ingest time, to resolve a store listing to a canonical product
  - query time, to understand what the user typed
Parsing both with one code path is what makes their attributes comparable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.matching.rules import CATEGORY_RULES, DEFAULT_CATEGORY, CategoryRules


def normalize(text: str) -> str:
    """
    Lowercase, turn punctuation into spaces, collapse whitespace.

    Deliberately does NOT strip "filler" words. The old implementation removed
    words like "smartphone" to help a whole-string similarity comparison; with
    targeted attribute extraction that step buys nothing and actively loses
    information (it also deleted "phone", which is a category signal).
    """
    text = re.sub(r"[^\w\s]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def detect_category(text: str) -> str:
    """Pick the category whose detector words appear most often in the name."""
    normalized = normalize(text)
    best, best_hits = DEFAULT_CATEGORY, 0
    for name, rules in CATEGORY_RULES.items():
        hits = sum(
            1
            for word in rules.detectors
            if re.search(rf"\b{re.escape(word)}\b", normalized)
        )
        if hits > best_hits:
            best, best_hits = name, hits
    return best


@dataclass(frozen=True)
class ParsedProduct:
    """A product name reduced to comparable, structured attributes."""

    raw: str
    normalized: str
    category: str
    attributes: dict[str, str | None] = field(default_factory=dict)

    def get(self, name: str) -> str | None:
        return self.attributes.get(name)

    @property
    def specified(self) -> dict[str, str]:
        """Only the attributes that were actually found (drops the Nones)."""
        return {k: v for k, v in self.attributes.items() if v is not None}


def parse(text: str, category: str | None = None) -> ParsedProduct:
    """
    Parse a product name using its category's rules.

    `category` may be supplied when it is already known (e.g. from the store
    feed); otherwise it is detected from the name itself.
    """
    normalized = normalize(text)
    category = category or detect_category(text)
    rules: CategoryRules = CATEGORY_RULES.get(
        category, CATEGORY_RULES[DEFAULT_CATEGORY]
    )

    attributes: dict[str, str | None] = {}
    for attribute in rules.attributes:
        value = attribute.extractor.extract(normalized)
        # `default` encodes "absence means something": a phone with no "Pro"
        # or "Max" in its name is the base variant, not an unknown one.
        attributes[attribute.name] = value if value is not None else attribute.default

    return ParsedProduct(
        raw=text,
        normalized=normalized,
        category=rules.name,
        attributes=attributes,
    )
