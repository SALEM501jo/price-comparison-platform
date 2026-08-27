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
        # Present in the Jordanian catalogues but previously unlisted, so every
        # listing from them resolved to brand=None and was excluded by the
        # brand gate. Motorola alone accounted for 10 of SmartBuy's 17
        # unparsed handsets; Doogee for 7 of AmmanCart's 29.
        "motorola", "tcl", "doogee", "microsoft",
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
        # "Moto Smart Phone G06" and "Motorola Moto Razr 50" are the same
        # marque. Keyword matches the longest candidate first, so "motorola"
        # is still preferred over "moto" when both appear.
        "moto": "motorola", "razr": "motorola",
        "surface": "microsoft",
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

# Laptops only. A graphics card advertises "16GB GDDR7" and a memory module
# "8GB DDR4"; both satisfied the laptops rule that a real machine states its
# storage, so iGeek's GPU and RAM aisles arrived in the catalogue as laptops.
# No laptop on sale ships a disk below 128GB and no consumer GPU carries that
# much memory, so the floor separates them cleanly -- and it is a property of
# the things themselves, not a list of words to keep extending.
#
# Phones keep the unbounded STORAGE above: 32GB and 64GB handsets are real.
LAPTOP_STORAGE = Quantity(
    pattern=CAPACITY_PATTERN,
    base_unit="gb",
    unit_multipliers={"gb": 1, "tb": 1024},
    select="max",
    minimum=128,
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


# Words that name a category this platform deliberately does NOT carry.
#
# NOT a blocklist of accessories -- that is what `requires_any` is for, and a
# list of "bag, case, mouse, ..." would need extending forever. This is one
# word per category we have decided is out of scope, which is a closed set
# that changes only when the product scope does.
#
# Televisions are the whole of it today. A TV shares a panel with a monitor
# and nothing else a buyer cares about: nobody cross-shops a 77-inch OLED
# television against a 27-inch 180Hz gaming panel. Without this, three TCL and
# Xiaomi televisions were categorised as PHONES, because "TCL C6K" has exactly
# the shape of a handset model code.
#
# Measured against the real feeds before adding it: of 487 listings in the
# three supported categories, ZERO mention a television. The false-negative
# cost is nil.
UNSUPPORTED_CATEGORIES: tuple[str, ...] = ("tv", "television", "televisions")


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
        "motorola", "moto", "doogee", "tcl",
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
                # Two-word sub-lines MUST precede the single-word rule below.
                # Regex returns the first pattern that matches, so a bare
                # "redmi" rule placed first would swallow "Redmi Note 15" and
                # report line=redmi with no number -- collapsing the Note range
                # into the numbered one.
                r"\b(?P<line>redmi\s+note)\s*(?P<num>\d{1,3}[a-z]?)\b",
                # Sub-brands, alphanumeric rather than digits only: real
                # listings read "Redmi A7 Pro" as often as "Redmi 17".
                r"\b(?P<line>redmi|poco|pixel|nova|mate)\s*(?P<num>[a-z]?\d{1,3}[a-z]?)\b",
                # Named product ranges. Tecno, Oppo, Motorola and Doogee name
                # their lines instead of numbering them off the marque, so the
                # brand-adjacent rule below never fires: "TECNO SPARK 50" has
                # no digits following "tecno" at all. These 24 listings parsed
                # to nothing before this pattern existed.
                r"\b(?P<line>spark|camon|pova|phantom|reno|blade|edge|narzo|nord"
                r"|razr)\s*(?P<num>\d{1,3}[a-z]?)\b",
                # Bare model codes after a brand: "Samsung A57", "Xiaomi 15T",
                # "Honor X7e". Without this a large part of the real catalogue
                # has no model at all -- 90 genuine handsets went uncategorised
                # the moment a model became a requirement.
                #
                # Filler words are tolerated because AmmanCart writes "Oppo
                # Smart Phones A5 PRO" -- the code is not adjacent to the
                # brand. The filler list is CLOSED on purpose. Allowing any
                # word here (\w+) let the rule reach across a product name and
                # seize the first number it found: "Samsung Galaxy Buds 3 Pro"
                # became phone model "samsung 3" and "Xiaomi Robot Vacuum X20"
                # became "xiaomi x20". Earbuds and vacuum cleaners then sat in
                # the phone tiers.
                #
                # The code must also contain a LETTER. Real model codes do --
                # A57, 15T, X7e, G35, S200c -- while a bare number next to a
                # brand is usually something else entirely: "Samsung 55" is a
                # television's screen size, and it satisfied the old rule.
                # The lookahead rejects a network suffix; without it "5G"
                # satisfies the code shape and becomes the model.
                r"\b(?P<line>honor|samsung|xiaomi|realme|oppo|vivo|infinix|tecno"
                r"|motorola|doogee|tcl)\b"
                r"(?:\s+(?:smart|smartphones?|mobile|phones?)){0,3}\s+"
                # The lookahead rejects a network suffix AND a resolution:
                # both "5G" and "4K" fit the bare code shape, and without this
                # "Xiaomi 4K TV Stick" became phone model "xiaomi 4k".
                r"(?P<num>(?!\d+[gk]\b)(?:[a-z]{1,2}\d{1,4}[a-z]?|\d{1,4}[a-z]))\b",
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
        "surface",
    ),
    brand_detectors=("dell", "hp", "lenovo", "asus", "acer", "msi", "microsoft"),
    attributes=(
        Attribute("brand", "brand", 0, BRANDS, gate=True),
        Attribute(
            "model", "model", 30,
            Regex(patterns=(
                r"\b(?P<line>macbook)\b",
                r"\b(?P<line>thinkpad|ideapad|inspiron|xps|pavilion|elitebook|zenbook|vivobook|omen|rog|surface)\s*(?P<num>\w{1,6})?",
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
                # Intel Core i-series, the OLD naming, still most of the
                # market. Matches a bare "i7" and the full part number alike
                # -- "i7-14650HX" and "i7 14650HX" both resolve to i7, which
                # is what a shopper searching "i7 laptop" means.
                r"\b(?P<cpu>i[3579])(?:[- ]?\d{4,5}[a-z]{0,2})?\b",
                # Intel's current naming: "Core Ultra 7 255U", and often just
                # "Ultra 7 256V" with the word Core omitted. Matched before the
                # Ryzen rule because a title may mention both a CPU and a GPU
                # vendor, and the processor is what this attribute is for.
                r"\b(?:core\s+)?(?P<line>ultra)\s*(?P<num>\d)\b",
                # Intel's OTHER new scheme, the one without "Ultra":
                # "Core 5-120U", "Core 7-150U". Named in the project's own
                # known-limitations list as unparsed. Distinct from both
                # "Core i5" and "Core Ultra 5" -- three different product
                # lines that happen to share a digit, so they must not
                # collapse onto one value.
                # [- ]? because normalize() has already turned the hyphen
                # into a space by the time this runs: "Core 5-120U" reaches
                # the extractor as "core 5 120u". A pattern written against
                # the raw title silently matches nothing.
                r"\b(?P<line>core)\s+(?P<num>\d)[- ]?\d{3,4}[a-z]{0,2}\b",
                # Budget silicon, common in the cheap end of this market and
                # previously invisible: a Celeron laptop and an i7 laptop
                # scored as equally unknown on processor.
                r"\b(?P<cpu>celeron|pentium|athlon)\b",
                # Ryzen. The trailing \b used to sit immediately after the
                # digit, which meant a full part number never matched: in
                # "Ryzen 5800H" the 5 is followed by 8, not a boundary, so 7
                # ASUS laptops came back with no processor at all. Only the
                # series digit is captured -- 5800H and 5 are both "ryzen 5" --
                # and "Ryzen AI 9" is tolerated because AMD inserts that
                # marketing token into current part names.
                r"\b(?P<line>ryzen)\s*(?:ai\s*)?(?P<num>\d)\d*[a-z]*",
                # Apple A-series ("A18 Pro chip"), LAST because it is the most
                # collision-prone rule here: ASUS names TUF models A14 and A16,
                # and while this pattern sat above the others it captured the
                # model designation instead of the processor -- "TUF Gaming A16
                # AMD Ryzen 7" reported cpu=a16. Real CPU tokens now win, and
                # this only fires when nothing else matched.
                r"\b(?P<cpu>a\d{2})\b",
            )),
        ),
        Attribute("storage", "storage", 20, LAPTOP_STORAGE),
        Attribute("ram", "memory", 10, RAM),
        # Space Gray and Silver are different SKUs at different prices, so
        # colour belongs here too -- weighted low, as on phones, because it is
        # the least identity-defining attribute.
        Attribute("color", "colour", 5, COLORS),
    ),
    requires_any=("storage", "cpu"),
)



# --- Monitors ---------------------------------------------------------------
#
# NOT televisions. A TV and a PC monitor share a panel and nothing else that
# matters to a buyer: nobody cross-shops a 55-inch smart TV against a 27-inch
# 180Hz gaming monitor, and putting them in one category would produce
# "comparisons" between products that answer different questions. TVs have no
# category here at all, so they are filtered out at ingest rather than stored
# and hidden.
#
# Monitors earn one because they are real overlap: iGeek alone lists 169, and
# the attributes buyers actually compare on -- size, resolution, refresh rate
# -- are all stated in the title.

SCREEN_SIZE = Regex(
    patterns=(
        # WHY NOT MATCH ON THE INCH MARK: normalize() turns punctuation into
        # spaces before any extractor runs, so 27" arrives as a bare 27 and
        # 24.5" arrives as two tokens, "24 5". A pattern anchored on the quote
        # character silently matches nothing at all.
        #
        # So: the spelled-out form first, then a bare number inside a
        # plausible panel range that is not carrying a unit. 165hz, 100hz,
        # 1440p and 16gb all fail that test; 27 and 32 pass.
        r"\b(?P<size>1[7-9]|[2-9]\d)\s*inch\b",
        # The optional trailing digit recovers a fractional size: 24.5 has
        # already become "24 5" by this point, and 24.5 is a different
        # product from 24 at a different price.
        r"\b(?P<size>1[7-9]|[2-5]\d)\b(?!\s*(?:hz|gb|tb|mm|ms|w|k)\b)(?:\s(?P<frac>\d)\b)?",
    ),
)


RESOLUTION = Keyword(
    values=("8k", "5k", "4k", "2k", "fhd", "hd"),
    synonyms={
        # One panel, several marketing names. Without these, the same monitor
        # listed as "4K" at one shop and "UHD" at another is two products.
        "uhd": "4k",
        "2160p": "4k",
        "qhd": "2k",
        "wqhd": "2k",
        "dqhd": "2k",
        "1440p": "2k",
        "full hd": "fhd",
        "1080p": "fhd",
    },
)

REFRESH_RATE = Regex(patterns=(r"\b(?P<hz>\d{2,3})\s*hz\b",))

PANEL = Keyword(
    values=("qd-oled", "oled", "nano ips", "ips", "va", "tn"),
    synonyms={"quantum dot oled": "qd-oled"},
)

MONITORS = CategoryRules(
    name="monitors",
    # "monitor" only. A television never calls itself one, which is exactly
    # how TVs stay out without a list of banned words.
    detectors=("monitor",),
    # DELIBERATELY NO brand_detectors, unlike every other category here.
    #
    # Brand detectors fire when no strong detector matched, and a television
    # carries exactly the same weak signals a monitor does: a brand, a
    # resolution and a refresh rate. With "lg" in this list, 20 of the 130 TVs
    # in the real feeds were categorised as monitors -- a 77-inch OLED TV
    # offered as a near-match for a 27-inch gaming panel.
    #
    # Requiring the word "monitor" keeps them out without a list of banned
    # words: a television never calls itself one, and the ingest path passes
    # the store's own product_type as a hint, so a monitor whose title omits
    # the word is still caught.
    attributes=(
        Attribute("brand", "brand", 0, BRANDS, gate=True),
        # Size dominates. A 24-inch and a 27-inch are not near-matches of one
        # another however well everything else agrees.
        Attribute("size", "screen size", 32, SCREEN_SIZE),
        Attribute("resolution", "resolution", 26, RESOLUTION),
        Attribute("refresh", "refresh rate", 22, REFRESH_RATE),
        Attribute("panel", "panel type", 12, PANEL),
        Attribute("color", "colour", 8, COLORS),
    ),
    # Every real monitor listing states its size. A stand, an arm or a cable
    # "for 27-inch monitors" states one too, but states nothing else -- which
    # is why size alone is not enough and resolution or refresh must also be
    # present for the listing to count as a monitor.
    requires_any=("resolution", "refresh"),
)

CATEGORY_RULES: dict[str, CategoryRules] = {
    PHONES.name: PHONES,
    LAPTOPS.name: LAPTOPS,
    MONITORS.name: MONITORS,
}

DEFAULT_CATEGORY = PHONES.name
