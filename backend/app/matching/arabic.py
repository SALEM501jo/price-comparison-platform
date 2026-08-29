"""
Arabic input, folded onto the vocabulary the rules already speak.

THE DESIGN DECISION: the engine stays English-canonical. An Arabic query is
translated into the same tokens a Latin one produces -- "ايفون" becomes
"iphone", "أسود" becomes "black", "١٢٨ جيجا" becomes "128gb" -- and everything
downstream is unchanged. rules.py does not gain an Arabic column, extractors
do not gain Arabic patterns, and the scorer never learns there is a second
language.

WHY NOT ARABIC PATTERNS IN rules.py: because then every category would need
maintaining twice, and the two copies would drift the first time someone added
a brand. The same argument the project already makes for parsing listings and
queries with one code path applies to parsing two languages with one rule set.
It also means a THIRD language is another table here, not another rewrite of
the rules.

This is a vocabulary, not a translator. It knows the words that appear in
phone, laptop and monitor listings in Jordan, which is a closed set of a few
hundred terms -- brands, colours, capacities, and the words for the categories
themselves. It has no opinion about Arabic generally.

ORTHOGRAPHY IS THE HARD PART, not vocabulary. The same handset is written
"ايفون", "آيفون" and "أيفون"; the same colour is "أسود" and "اسود"; prices and
capacities arrive in both Western (128) and Arabic-Indic (١٢٨) digits. So the
text is FOLDED first -- digits unified, diacritics dropped, the alef and ya
families collapsed -- and the vocabulary is written in folded form, so one
entry covers every spelling of a word rather than one entry per spelling.
"""

from __future__ import annotations

import re

# --- Digits -----------------------------------------------------------------
#
# Arabic-Indic (٠-٩) and Extended Arabic-Indic/Persian (۰-۹). A shopper typing
# on an Arabic keyboard gets these, and "١٢٨ جيجا" has to reach the capacity
# extractor as "128 gb" or the storage is simply not seen.
#
# NOTE the project already decided the UI renders Western digits, because
# Jordanian price tags use them (see the [dir='rtl'] rule in index.css). This
# is the input side of that same decision.
_DIGITS = {}
for _base in (0x0660, 0x06F0):  # Arabic-Indic, then Extended
    for _offset in range(10):
        _DIGITS[_base + _offset] = ord("0") + _offset

# --- Diacritics and joiners -------------------------------------------------
#
# Tashkeel (َ ُ ِ ّ ْ ...) are pronunciation marks that carry no identity: "أَسْوَد"
# and "أسود" are one word. Tatweel (ـ) is a decorative stretch inside a word.
#
# These MUST be removed before normalize() strips punctuation. Combining marks
# are not alphanumeric, so normalize()'s [^\w\s] pass would replace each with a
# SPACE and split one word into three.
_DIACRITICS = re.compile(r"[ً-ٰٕـ]")

# --- Letter folding ---------------------------------------------------------
#
# Collapses the families that are typed interchangeably. This is the standard
# set for Arabic search normalisation:
#   أ إ آ ٱ -> ا   (alef with any hamza)
#   ة -> ه         (ta marbuta, routinely typed as ha)
#   ى -> ي         (alef maqsura, routinely typed as ya)
#   ؤ -> و, ئ -> ي (hamza carriers)
#   گ چ پ ڤ        Persian/dialect letters used for sounds Arabic lacks, which
#                  is how "چيجا" and "غيغا" both appear for "giga"
_LETTERS = str.maketrans(
    {
        "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
        "ة": "ه",
        "ى": "ي",
        "ؤ": "و",
        "ئ": "ي",
        "گ": "ك",
        "چ": "ج",
        "پ": "ب",
        "ڤ": "ف",
    }
)


def fold(text: str) -> str:
    """Unify digits, drop diacritics, collapse the letter families."""
    return _DIACRITICS.sub("", text.translate(_DIGITS)).translate(_LETTERS)


# --- Vocabulary -------------------------------------------------------------
#
# Arabic term -> the canonical token rules.py already recognises. Keys are
# written WITHOUT hamza and WITHOUT ta marbuta, because fold() has already run
# by the time they are matched; writing "أسود" here would simply never match.
#
# Values are deliberately the existing English tokens rather than new ones, so
# nothing downstream needs to know this file exists.

TERMS: dict[str, str] = {
    # --- Categories. These drive detect_category, so they are what makes an
    # Arabic query reach the right rule set at all.
    "جوال": "phone",
    "جوالات": "phone",
    "موبايل": "phone",
    "موبايلات": "phone",
    "هاتف": "phone",
    "هواتف": "phone",
    "تلفون": "phone",
    "ايفون": "iphone",
    "لابتوب": "laptop",
    "لاب توب": "laptop",
    "حاسوب": "laptop",
    "كمبيوتر": "laptop",
    "نوت بوك": "notebook",
    "شاشه": "monitor",
    "شاشات": "monitor",
    "مونيتور": "monitor",
    # Televisions are NOT carried (UNSUPPORTED_CATEGORIES in rules.py). That
    # exclusion is worthless if it only understands the English word: a search
    # for "تلفزيون" would sail past it and be scored against the phone rules,
    # which is exactly how TVs became phones in the first place.
    "تلفزيون": "tv",
    "تليفزيون": "tv",
    "تلفاز": "tv",
    # --- Brands and product lines
    "ابل": "apple",
    "ايباد": "ipad",
    "ماك بوك": "macbook",
    "ماكبوك": "macbook",
    "سامسونج": "samsung",
    "سامسونغ": "samsung",
    "جالاكسي": "galaxy",
    "غالاكسي": "galaxy",
    "شاومي": "xiaomi",
    "شياومي": "xiaomi",
    "ريدمي": "redmi",
    "بوكو": "poco",
    "هواوي": "huawei",
    "نوكيا": "nokia",
    "اوبو": "oppo",
    "ريلمي": "realme",
    "هونر": "honor",
    "فيفو": "vivo",
    "انفينكس": "infinix",
    "تكنو": "tecno",
    "موتورولا": "motorola",
    "دوجي": "doogee",
    "جوجل": "google",
    "غوغل": "google",
    "بكسل": "pixel",
    "سوني": "sony",
    "ال جي": "lg",
    "ديل": "dell",
    "لينوفو": "lenovo",
    "اسوس": "asus",
    "ايسر": "acer",
    "مايكروسوفت": "microsoft",
    "هونداي": "hyundai",
    # --- Variants
    "برو": "pro",
    "ماكس": "max",
    "بلس": "plus",
    "بلاس": "plus",
    "الترا": "ultra",
    "ميني": "mini",
    # MacBook Air. Without it "ماك بوك اير" resolves the model and loses
    # the variant, which is the difference between two machines.
    "اير": "air",
    "ايه": "air",
    # --- Colours
    "اسود": "black",
    "ابيض": "white",
    "ازرق": "blue",
    "احمر": "red",
    "اخضر": "green",
    "اصفر": "yellow",
    "ذهبي": "gold",
    "فضي": "silver",
    "رمادي": "gray",
    "رصاصي": "gray",
    "وردي": "pink",
    "زهري": "pink",
    "بنفسجي": "purple",
    "برتقالي": "orange",
    "بيج": "beige",
    "نحاسي": "bronze",
    # --- Units and specs
    # No space is inserted between the number and the unit: the capacity
    # pattern allows one either way, and "١٢٨ جيجا" -> "128 gb" matches.
    "جيجا": "gb",
    "جيجابايت": "gb",
    "غيغا": "gb",
    "غيغابايت": "gb",
    "جيغا": "gb",
    "تيرا": "tb",
    "تيرابايت": "tb",
    "رام": "ram",
    "ذاكره": "ram",
    "تخزين": "storage",
    "بوصه": "inch",
    "انش": "inch",
    "هرتز": "hz",
    "بطاريه": "battery",
    "جديد": "new",
    "مستعمل": "used",
}

# Longest first, so "ماك بوك" is replaced before "بوك" could be, and
# "جيجابايت" before "جيجا". Same rule the Keyword extractor uses.
_ORDERED = sorted(TERMS.items(), key=lambda kv: len(kv[0]), reverse=True)

# "ال" is the definite article, written joined to its noun: a shopper types
# "الايفون" as readily as "ايفون", and "الاسود" for the colour. Allowing an
# optional article on every term costs nothing and covers most of the gap
# between written and typed Arabic.
_PATTERNS = [
    (
        re.compile(rf"(?<![^\W\d_])(?:ال)?{re.escape(term)}(?![^\W\d_])"),
        canonical,
    )
    for term, canonical in _ORDERED
]


def has_arabic(text: str) -> bool:
    """Whether the text contains any Arabic-script character."""
    return any("؀" <= ch <= "ۿ" for ch in text)


def transliterate(text: str) -> str:
    """
    Replace known Arabic terms with their canonical English tokens.

    Anything not in the vocabulary is left exactly as it is. An unknown Arabic
    word should reach the parser untouched rather than be guessed at -- a
    wrong guess produces a confident match against the wrong product, which is
    worse than no match.
    """
    for pattern, canonical in _PATTERNS:
        text = pattern.sub(canonical, text)
    return text


def expand_prefix(text: str) -> str:
    """
    Complete a partial Arabic word to the term it is starting to spell.

    FOR TYPE-AHEAD ONLY, and deliberately not used by parse(). Suggestions
    exist to answer half-typed input: "ايفو" is three quarters of "ايفون" and
    a shopper expects iPhones before they finish the word. But GUESSING is
    exactly what the parser must not do -- a search should answer what was
    typed, not what we think was about to be typed -- so this stays on the
    suggestion path where a wrong guess costs a dropdown row rather than a
    wrong product.

    Only expands when exactly one term starts with the fragment. Two
    candidates means we do not know which, and a dropdown that flickers
    between meanings is worse than one that waits for another keystroke.
    """
    if not has_arabic(text):
        return text

    folded = fold(text)
    words = folded.split()
    if not words:
        return folded

    last = words[-1]
    if len(last) < 2 or last in TERMS:
        return folded

    matches = {
        canonical
        for term, canonical in TERMS.items()
        if term.startswith(last)
    }
    if len(matches) == 1:
        words[-1] = matches.pop()
    return " ".join(words)


def prepare(text: str) -> str:
    """
    Fold and translate, in that order.

    Order matters: the vocabulary is written in folded form, so folding has to
    happen first or nothing matches.
    """
    if not has_arabic(text):
        # Fast path. Latin queries are the majority and must not pay for this,
        # and folding cannot change ASCII anyway.
        return text
    return transliterate(fold(text))
