"""
Category matching rules -- DATA, not logic.

This module is the ONLY thing that has to change to support a new product
category. The parser and the scorer are category-agnostic: they read whatever
they find here. Adding washing machines means appending a CategoryRules entry
with its own attributes and weights; it does not mean touching the engine.

The weights of the non-gate attributes are what produce the search tiers:
matching every attribute the user asked for scores 100 (EXACT), losing only
colour scores 90 (CLOSE), losing storage scores 75 (SIMILAR).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.matching.extractors import Extractor, Keyword, Quantity, Regex

# --- Shared vocabulary ------------------------------------------------------

BRANDS = Keyword(
    values=(
        "apple", "samsung", "sony", "lg", "huawei", "xiaomi", "nokia",
        "oppo", "realme", "google", "dell", "hp", "lenovo", "asus", "acer", "msi",
        "honor", "vivo", "infinix", "tecno",
    ),
    # Product lines imply their brand, so "iPhone 15" resolves to apple even
    # when the listing never says "Apple".
    synonyms={
        "iphone": "apple", "ipad": "apple", "macbook": "apple",
        "airpods": "apple", "imac": "apple", "watch": "apple",
        "galaxy": "samsung", "note": "samsung",
        "redmi": "xiaomi", "poco": "xiaomi", "mi": "xiaomi",
        "playstation": "sony", "ps5": "sony", "ps4": "sony", "bravia": "sony",
        "pixel": "google",
        "thinkpad": "lenovo", "ideapad": "lenovo",
        "inspiron": "dell", "xps": "dell", "latitude": "dell",
        "pavilion": "hp", "elitebook": "hp", "omen": "hp",
        "zenbook": "asus", "vivobook": "asus", "rog": "asus",
        "nova": "huawei", "mate": "huawei",
    },
)

COLORS = Keyword(
    values=(
        "midnight green", "space gray", "sierra blue", "pacific blue",
        "phantom black", "natural titanium", "blue titanium", "alpine green",
        "deep purple", "rose gold", "sky blue", "starlight", "graphite",
        "midnight", "titanium", "lavender", "black", "white", "silver",
        "gold", "blue", "red", "green", "purple", "pink", "yellow",
        "orange", "gray", "cream", "mint", "beige",
    ),
    synonyms={
        "grey": "gray",
        "space grey": "space gray",
        "jet black": "black",
        "matte black": "black",
        # Apple's "Midnight" is the dark colourway that replaced Black on the
        # iPhone 13-15 lineup, and Jordanian stores use the two names for the
        # same handset. Without this, Carrefour's "iPhone 15 128GB Midnight"
        # became its own product instead of joining the other three stores.
        # "Midnight Green" (iPhone 11 Pro) is a genuinely different colour and
        # stays distinct -- Keyword matches the longest value first.
        "midnight": "black",
    },
)

# Capacities, split by size rather than by keyword. Real titles read
# "16GB DDR4 & 512GB SSD" or "4GB & 128GB" and never say "RAM", so matching on
# that word finds nothing and storage ends up holding the memory figure.
CAPACITY_PATTERN = r"(?P<num>\d+)\s*(?P<unit>gb|tb)\b"

STORAGE = Quantity(
    pattern=CAPACITY_PATTERN,
    base_unit="gb",
    unit_multipliers={"gb": 1, "tb": 1024},
    select="max",
)

RAM = Quantity(
    pattern=CAPACITY_PATTERN,
    base_unit="gb",
    # Same multipliers as STORAGE on purpose: this has to SEE the terabyte
    # figure to know it is the larger of the two. Omitting "tb" left
    # "32GB DDR5 & 1TB SSD" with a single visible capacity, so the guard below
    # fired and memory came back empty.
    unit_multipliers={"gb": 1, "tb": 1024},
    select="min",
    # Needs two capacities to distinguish memory from storage. With one, there
    # is nothing to compare and "iPhone 15 128GB" would claim 128GB of RAM.
    min_matches=2,
)


# --- Rule containers --------------------------------------------------------


@dataclass(frozen=True)
class Attribute:
    """One scoreable property of a product."""

    name: str
    label: str          # human-readable, shown in "why this matched" text
    weight: int         # share of the 100-point score
    extractor: Extractor
    gate: bool = False  # mismatch here excludes the candidate outright
    default: str | None = None  # value implied by absence (e.g. no "Pro" -> base)


@dataclass(frozen=True)
class CategoryRules:
    name: str
    # Strong evidence: product lines and category words. "macbook", "laptop",
    # "iphone" name the kind of thing directly.
    detectors: tuple[str, ...]
    attributes: tuple[Attribute, ...]

    # Weak evidence: manufacturer names. A brand is consulted only when no
    # category matched on a strong detector, because most of these firms make
    # several kinds of product -- "Samsung laptop 16GB" counted "samsung" for
    # phones and "laptop" for laptops, tied, and the phone rules won.
    brand_detectors: tuple[str, ...] = ()

    # At least one of these must be extracted for the category to apply.
    #
    # WHY: a detector word is weak evidence. "Lenovo ThinkPad Laptop Backpack",
    # "Agtc Brinch Laptop Bag" and an "Apple Magic Mouse" all landed in
    # `laptops` and came back as EXACT matches for a search of "Laptop" --
    # accessories presented as the thing they accessorise. A real laptop
    # listing always states storage or a processor; a bag states neither.
    #
    # A requirement rather than a list of banned words: "bag, backpack, case,
    # sleeve, mouse, ..." would need extending forever, exactly like the CPU
    # enumeration that went stale on the M5.
    requires_any: tuple[str, ...] = ()

    def scoreable(self) -> tuple[Attribute, ...]:
        return tuple(a for a in self.attributes if not a.gate and a.weight > 0)


# --- Categories -------------------------------------------------------------

PHONES = CategoryRules(
    name="phones",
    detectors=(
        # Product lines
        "iphone", "galaxy", "redmi", "poco", "pixel", "smartphone",
        "phone", "nova", "mate",
    ),
    brand_detectors=(
        "oppo", "realme", "nokia", "honor", "xiaomi", "samsung",
        "vivo", "infinix", "tecno", "huawei",
    ),
    attributes=(
        # Brand is a gate, not a score: an Apple result must never be offered
        # as a near-match for a Samsung query, however many specs coincide.
        Attribute("brand", "brand", 0, BRANDS, gate=True),
        Attribute(
            "model", "model", 33,
            Regex(patterns=(
                r"\b(?P<line>iphone)\s*(?P<num>\d{1,2})",
                r"\b(?P<line>galaxy)\s+(?P<series>note|[sazm])?\s*(?P<num>\d{1,3})",
                # Sub-brands, alphanumeric rather than digits only: real
                # listings read "Redmi A7 Pro" as often as "Redmi 17".
                r"\b(?P<line>redmi|poco|pixel|nova|mate)\s*(?P<num>[a-z]?\d{1,3}[a-z]?)\b",
                # Bare model codes after a brand: "Samsung A57", "Xiaomi 15T",
                # "Honor X7e". Without this a large part of the real catalogue
                # has no model at all -- 90 genuine handsets went uncategorised
                # the moment a model became a requirement.
                r"\b(?P<line>honor|samsung|xiaomi|realme|oppo|vivo|infinix|tecno)\s+"
                r"(?P<num>[a-z]{0,2}\d{1,4}[a-z]?)\b",
            )),
        ),
        Attribute(
            "variant", "variant", 28,
            Keyword(values=("pro max", "pro", "plus", "ultra", "mini", "fe", "max")),
            default="base",  # a plain "iPhone 11" IS a variant, not a blank
        ),
        Attribute("storage", "storage", 24, STORAGE),
        Attribute("ram", "memory", 5, RAM),
        Attribute("color", "colour", 10, COLORS),
    ),
    # Either identifies a real handset. Model alone was too strict: the model
    # patterns cannot name every phone on the market, and a listing they miss
    # is still a phone if it states storage.
    requires_any=("model", "storage"),
)

LAPTOPS = CategoryRules(
    name="laptops",
    detectors=(
        "macbook", "laptop", "notebook", "thinkpad", "ideapad", "inspiron",
        "xps", "pavilion", "elitebook", "zenbook", "vivobook", "omen", "rog",
        # "Omni Book", "Galaxy Book". Word-bounded, so it does not fire inside
        # "macbook".
        "book",
    ),
    brand_detectors=("dell", "hp", "lenovo", "asus", "acer", "msi"),
    attributes=(
        Attribute("brand", "brand", 0, BRANDS, gate=True),
        Attribute(
            "model", "model", 30,
            Regex(patterns=(
                r"\b(?P<line>macbook)\b",
                r"\b(?P<line>thinkpad|ideapad|inspiron|xps|pavilion|elitebook|zenbook|vivobook|omen|rog)\s*(?P<num>\w{1,6})?",
            )),
        ),
        Attribute(
            "variant", "variant", 15,
            Keyword(values=("air", "pro", "plus", "max")),
            # NO default here, unlike phones. "iPhone 11" really is the base
            # variant, distinct from the 11 Pro. There is no such thing as a
            # base MacBook -- every one is an Air or a Pro -- so defaulting a
            # bare "MacBook" query to variant=base mismatched every model in
            # the catalogue and returned nothing at all.
        ),
        Attribute(
            "cpu", "processor", 20,
            # Patterns, not a fixed list. Enumerating "m1, m2, m3, m4" went
            # stale the moment Apple shipped the M5 -- a MacBook Pro M5 was
            # already in the catalogue with cpu=None, so it could not be told
            # apart from any other MacBook Pro. Model numbers elsewhere in
            # these rules are matched the same way, which is why "iPhone 17"
            # and "Galaxy S25" work without anyone updating a list.
            Regex(patterns=(
                # Apple silicon: m1 .. m99. Word-bounded so "M.2 SSD" (which
                # normalises to "m 2") and RAM figures are not mistaken for it.
                r"\b(?P<cpu>m\d{1,2})\b",
                # Apple A-series, as used in "A18 Pro chip".
                r"\b(?P<cpu>a\d{2})\b",
                # Intel Core i-series. Stable naming, but a pattern anyway.
                r"\b(?P<cpu>i[3579])\b",
                r"\b(?P<line>ryzen)\s*(?P<num>\d)\b",
            )),
        ),
        Attribute("storage", "storage", 20, STORAGE),
        Attribute("ram", "memory", 10, RAM),
        # Space Gray and Silver are different SKUs at different prices, so
        # colour belongs here too -- weighted low, as on phones, because it is
        # the least identity-defining attribute.
        Attribute("color", "colour", 5, COLORS),
    ),
    requires_any=("storage", "cpu"),
)

CATEGORY_RULES: dict[str, CategoryRules] = {
    PHONES.name: PHONES,
    LAPTOPS.name: LAPTOPS,
}

DEFAULT_CATEGORY = PHONES.name
