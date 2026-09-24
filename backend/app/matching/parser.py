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

from app.matching import arabic
from app.matching.rules import UNSUPPORTED_CATEGORIES, CATEGORY_RULES, CategoryRules


def normalize(text: str) -> str:
    r"""
    Lowercase, turn punctuation into spaces, collapse whitespace.

    Deliberately does NOT strip "filler" words. The old implementation removed
    words like "smartphone" to help a whole-string similarity comparison; with
    targeted attribute extraction that step buys nothing and actively loses
    information (it also deleted "phone", which is a category signal).

    ARABIC IS FOLDED HERE, at the single point both sides of the system pass
    through. Putting it in the search router instead would translate queries
    and not listings, so a merchant who typed their stock in Arabic would be
    invisible to an Arabic search -- and the property that makes this engine
    work is that both sides are parsed by one code path. See arabic.py.

    It runs BEFORE the punctuation pass on purpose: Arabic diacritics are
    combining marks, which are not alphanumeric, so [^\w\s] would replace each
    with a space and split one word into three.
    """
    text = arabic.prepare(text.lower())
    # "+" IS A WORD, not punctuation: it is the whole difference between a
    # Redmi Note 15 Pro and a Redmi Note 15 Pro+, and between a Galaxy
    # A56 and an A56+. Dropped with the rest of the punctuation, the two
    # models parsed identically and a search for one offered the other as
    # a match whose only stated difference was storage.
    text = text.replace("+", " plus ")
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def detect_category(text: str) -> str | None:
    """
    Pick the category whose detector words appear most often in the name.

    Returns None when nothing matches, rather than falling back to a default.
    Defaulting silently mislabelled every unrecognised string as a phone: a
    search for "playstation" was parsed with the phone rules, and a search for
    "%%%%" picked up the phone variant default and came back as a 100% EXACT
    match against a real handset.
    """
    normalized = normalize(text)

    # A listing that names an unsupported category belongs to none of ours,
    # however well its other words happen to match. Checked BEFORE scoring:
    # a television states a brand, a resolution and a refresh rate, which is
    # indistinguishable from a monitor by weight alone.
    for word in UNSUPPORTED_CATEGORIES:
        if re.search(rf"\b{re.escape(word)}\b", normalized):
            return None

    def count(words) -> int:
        # `s?` tolerates a plural. Stores write "Phones", "Mobiles" and
        # "Monitors" as often as the singular, and \bphone\b matches none of
        # them -- so a store that had classified its catalogue perfectly was
        # read as having said nothing at all, and the title was guessed from
        # instead. One character, and it is a rule rather than a second list
        # of words to keep in step with the first.
        return sum(
            1 for w in words if re.search(rf"\b{re.escape(w)}s?\b", normalized)
        )

    # Strong evidence first: product lines and category words.
    best, best_hits = None, 0
    for name, rules in CATEGORY_RULES.items():
        hits = count(rules.detectors)
        if hits > best_hits:
            best, best_hits = name, hits
    if best is not None:
        return best

    # Only if nothing named the kind of thing do brands get a say. Counting
    # them alongside product lines let "Samsung laptop 16GB" tie -- "samsung"
    # for phones against "laptop" for laptops -- and the phone rules won on
    # declaration order.
    for name, rules in CATEGORY_RULES.items():
        hits = count(rules.brand_detectors)
        if hits > best_hits:
            best, best_hits = name, hits
    return best


# Values that mean "nobody said", not "this is a thing of that kind".
# "Uncategorized" is OUR OWN filler -- services/deduplication.py writes it when
# a listing arrives with no product_type at all, which is every merchant
# listing -- so treating it as the store's classification would let the
# platform's own placeholder veto a real shop's phone.
UNCLASSIFIED_HINTS = frozenset({"uncategorized", "uncategorised", "unknown", "n/a"})


def _is_a_classification(hint: str) -> bool:
    """Whether a product_type is a statement about what the thing is."""
    return hint.strip().lower() not in UNCLASSIFIED_HINTS


def classify_hint(hint: str) -> str | None:
    """
    Read a store's product_type as a LABEL, not as prose.

    THE HEAD NOUN IS WHAT THE THING IS. In an English compound label the last
    noun names the thing and the earlier words qualify it: a "Mobile Case" is
    a case, a "Laptop Bag" is a bag, and "Covers & Cases" are covers. Scanning
    the whole label for any category word gets all three exactly backwards --
    it reads the qualifier as the subject and files a phone case as a phone.

    This is grammar rather than a list of banned words, so it needs no
    maintenance and covers labels nobody has seen yet. It is the same
    distinction the project already makes between a store's classification and
    an inference from a title, applied one level down.

    Trailing model numbers are dropped first: iGeek files real handsets under
    "iPhone 17", whose last token is a number that names nothing.

    Used for the HINT ONLY. A title is prose -- "Apple iPhone 15 128GB Black"
    has no head noun in this sense -- so titles keep the whole-string scan.
    """
    tokens = normalize(hint).split()
    while tokens and any(ch.isdigit() for ch in tokens[-1]):
        tokens.pop()
    if not tokens:
        return None
    return detect_category(tokens[-1])


def store_refuses(hint: str | None) -> bool:
    """
    Whether a store's product_type says the item is none of our categories.

    The decision parse() takes before it reads a single word of the title,
    exposed so a caller can say WHY a listing was turned away -- "the store
    files this under Mobile Case" -- rather than only that it was.
    """
    if not hint or not hint.strip() or not _is_a_classification(hint):
        return False
    return classify_hint(hint) is None


@dataclass(frozen=True)
class ParsedProduct:
    """A product name reduced to comparable, structured attributes."""

    raw: str
    normalized: str
    category: str | None
    attributes: dict[str, str | None] = field(default_factory=dict)

    def get(self, name: str) -> str | None:
        return self.attributes.get(name)

    @property
    def specified(self) -> dict[str, str]:
        """Only the attributes that were actually found (drops the Nones)."""
        return {k: v for k, v in self.attributes.items() if v is not None}


def parse(
    text: str,
    category: str | None = None,
    hint: str | None = None,
    require_evidence: bool = True,
    apply_defaults: bool = True,
) -> ParsedProduct:
    """
    Parse a product name using its category's rules.

    `category` may be supplied when it is already known. `hint` is extra text
    consulted ONLY for category detection, never for attributes -- a store's
    own product_type field, typically.

    WHY THE HINT EXISTS: real listings often do not name their category in the
    title. "Hp Intel I7 -8550U, 16GB DDR4 & 512GB SSD, 15.6Inch" is
    unmistakably a laptop to a person and contains no word this parser
    recognises; the store files it under product_type "Notebook". Without the
    hint every such listing is uncategorised and unmatchable.

    `require_evidence` enforces CategoryRules.requires_any, which keeps
    accessories out of the catalogue. It applies to LISTINGS, not to QUERIES: a
    shopper typing "MacBook" has given no storage or processor and still means
    every MacBook, so search parses with it off.

    `apply_defaults` is the same distinction for Attribute.default. A LISTING
    called "iPhone 11" really is the base variant, distinct from the 11 Pro. A
    QUERY of "iPhone 11" means the shopper did not say which -- reading it as
    an assertion of "base" made "Honor X7e" score 67% against the seven
    "Honor X7e Plus" handsets in the catalogue and return nothing at all, for
    want of one word.
    """
    normalized = normalize(text)
    # THE HINT IS CONSULTED FIRST, not as a fallback. A store's product_type
    # is a direct statement of what the thing is; the title is an inference
    # from whatever words happen to appear in it. Trying the title first meant
    # brand detectors claimed listings they had no business claiming: a
    # "Lenovo ThinkVision 27 FHD 100Hz" monitor was routed to LAPTOPS because
    # "lenovo" is a laptop brand, then failed the laptop requires_any and
    # parsed to nothing at all -- with the store filing it under "Monitor"
    # the whole time.
    #
    # AND THE STATEMENT IS BELIEVED WHEN IT SAYS NO. Consulting the hint first
    # was only half the decision: when it resolved to none of our categories
    # the code fell through and guessed from the title anyway, which threw the
    # store's answer away in exactly the case it was most useful. That is how
    # a "Microwave Ovens" became a phone -- the store said what it was, and
    # the word "Samsung" in the title was believed instead. Phone cases,
    # screen protectors, SSDs, keyboards, a Nintendo game and a refrigerator
    # all arrived the same way, and every one of them named a real handset or
    # laptop in its title, so no amount of tightening requires_any could
    # separate them: "IPHONE 15 PRO CASE" states a model exactly as a phone
    # does.
    #
    # Measured over the 497-product catalogue: 74 listings are dropped, of
    # which one is a genuine handset (a Samsung the store filed under
    # "Connectivity"). The rest are accessories and appliances.
    if category is None and hint and hint.strip():
        if _is_a_classification(hint):
            category = classify_hint(hint)
            if category is None:
                # The store classified this, and it is not one of ours.
                return ParsedProduct(
                    raw=text, normalized=normalized, category=None, attributes={}
                )
        else:
            # A placeholder is the absence of a statement, not a statement.
            category = None
    category = category or detect_category(text)
    rules: CategoryRules | None = CATEGORY_RULES.get(category) if category else None

    if rules is None:
        # Nothing recognised this text. Return it unparsed rather than forcing
        # it through an arbitrary rule set -- callers treat an empty attribute
        # set as "fall back to a plain name search".
        return ParsedProduct(
            raw=text, normalized=normalized, category=None, attributes={}
        )

    attributes: dict[str, str | None] = {}
    extracted: set[str] = set()
    for attribute in rules.attributes:
        value = attribute.extractor.extract(normalized)
        if value is not None:
            extracted.add(attribute.name)
        # `default` encodes "absence means something": a phone with no "Pro"
        # or "Max" in its name is the base variant, not an unknown one. That
        # holds for a listing; for a query, absence means unsaid.
        if value is None and apply_defaults:
            value = attribute.default
        attributes[attribute.name] = value

    # A detector word alone is weak evidence. Accessories name the thing they
    # accessorise -- "ThinkPad Laptop Backpack", "Laptop Bag" -- and were being
    # filed as laptops, then returned as EXACT matches for a search of
    # "Laptop". Requiring one real attribute separates a product from a
    # product's bag. Defaults do not count: they were assumed, not found.
    if require_evidence and rules.requires_any and not (
        extracted & set(rules.requires_any)
    ):
        return ParsedProduct(
            raw=text, normalized=normalized, category=None, attributes={}
        )

    return ParsedProduct(
        raw=text,
        normalized=normalized,
        category=rules.name,
        attributes=attributes,
    )
