"""
Attribute extractors: the small, reusable pieces that pull one structured
value out of a free-text product name.

These are the only place regexes live. Category rules (rules.py) combine them
declaratively; the scoring engine (scorer.py) never sees a regex at all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol


class Extractor(Protocol):
    """Anything that can pull one attribute value out of a normalised name."""

    def extract(self, text: str) -> str | None: ...


@dataclass(frozen=True)
class Keyword:
    """
    Match one value from a fixed vocabulary.

    Longest value wins, so "midnight green" is found before "green" and
    "pro max" before "pro" -- without depending on declaration order.

    `synonyms` maps alternative spellings (and product lines) onto a canonical
    value: {"grey": "gray", "iphone": "apple"}.
    """

    values: tuple[str, ...]
    synonyms: dict[str, str] = field(default_factory=dict)

    def extract(self, text: str) -> str | None:
        candidates = list(self.values) + list(self.synonyms)
        for token in sorted(candidates, key=len, reverse=True):
            if re.search(rf"\b{re.escape(token)}\b", text):
                return self.synonyms.get(token, token)
        return None


@dataclass(frozen=True)
class Regex:
    r"""
    Match the first of several patterns and join its named groups.

    Every populated named group is joined with a single space, so
    r"(?P<line>iphone)\s*(?P<num>\d{1,2})" turns both "iPhone 15" and
    "iphone15" into the canonical value "iphone 15".
    """

    patterns: tuple[str, ...]

    def extract(self, text: str) -> str | None:
        for pattern in self.patterns:
            match = re.search(pattern, text)
            if match:
                parts = [g for g in match.groupdict().values() if g]
                if parts:
                    return " ".join(parts)
        return None


@dataclass(frozen=True)
class Quantity:
    """
    Match a number plus a unit and canonicalise it to a single base unit,
    so "1TB" and "1024GB" compare equal instead of looking like different
    products.

    `unit_multipliers` is expressed in the base unit: {"tb": 1024, "gb": 1}.
    """

    pattern: str
    base_unit: str
    unit_multipliers: dict[str, int]

    def extract(self, text: str) -> str | None:
        for match in re.finditer(self.pattern, text):
            groups = match.groupdict()
            unit = (groups.get("unit") or self.base_unit).lower()
            multiplier = self.unit_multipliers.get(unit)
            if multiplier is None:
                continue
            try:
                amount = int(groups["num"])
            except (KeyError, TypeError, ValueError):
                continue
            return f"{amount * multiplier}{self.base_unit}"
        return None
