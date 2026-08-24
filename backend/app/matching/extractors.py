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

    `select` decides which match wins when a name contains several:
      "first" -- the earliest match
      "max"   -- the largest quantity
      "min"   -- the smallest quantity

    WHY max/min RATHER THAN A KEYWORD: real listings almost never label memory
    the way test data does. Actual titles read "16GB DDR4 & 512GB SSD" and
    "4GB & 128GB" -- no "RAM" anywhere -- so a lookahead for that word finds
    nothing and storage silently takes the memory figure instead. Between two
    capacities on one device the larger is the storage and the smaller is the
    memory, which holds across every phone and laptop in the feeds.

    `min_matches` guards the memory case: with only one capacity present there
    is nothing to compare, and "iPhone 15 128GB" must not report 128GB of RAM.
    """

    pattern: str
    base_unit: str
    unit_multipliers: dict[str, int]
    select: str = "first"
    min_matches: int = 1

    def _values(self, text: str) -> list[int]:
        found: list[int] = []
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
            found.append(amount * multiplier)
        return found

    def extract(self, text: str) -> str | None:
        values = self._values(text)
        if len(values) < self.min_matches:
            return None

        if self.select == "max":
            chosen = max(values)
        elif self.select == "min":
            chosen = min(values)
        else:
            chosen = values[0]

        return f"{chosen}{self.base_unit}"
