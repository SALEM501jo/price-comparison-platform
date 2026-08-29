"""
Spelling correction for query WORDS.

READ THIS BEFORE ASSUMING IT CONTRADICTS THE PROJECT:

app/matching/scorer.py opens by rejecting string similarity, and it is right
to. But it rejects it for a different job. Two distinct questions:

  "which PRODUCT does this query mean?"   -- edit distance is the wrong tool,
      because 128GB and 256GB are one character apart and are different
      products, while word order is a large edit and changes nothing. That
      argument is unaffected by anything here.

  "did they mean to type this WORD?"      -- edit distance is exactly the
      right tool, because it is the actual question: which known word is this
      typo nearest to? "smasung" is not a brand, and "samsung" is one edit
      away.

So this corrects tokens against a CLOSED vocabulary and then hands the
corrected string to the same structured parser as always. It never scores a
product, never ranks anything, and never sees a price. The output of this
module is a string; the engine downstream is unchanged.

WHERE THE VOCABULARY COMES FROM: rules.py, at import time. Every brand, brand
synonym, colour, colour synonym, category detector and keyword the engine
already knows. Deriving it means a brand added to the rules is spell-checked
for free, and -- more importantly -- a vocabulary hand-copied here would drift
from the rules the first time anyone edited one and not the other. That is the
same failure the project's own notes describe for the CPU chip list that went
stale on the M5.

WHAT IT DELIBERATELY WILL NOT DO:
  - correct a token containing a digit. Model codes are the densest source of
    near-misses in this catalogue: A15, A16, S24, M2, 128. "a16" is one edit
    from "a15" and they are different products, which is the scorer's whole
    argument.
  - correct a token already in the vocabulary.
  - correct short tokens. At three characters almost everything is within one
    edit of something.
  - guess when two vocabulary words are equally close. An ambiguous
    correction is a coin flip presented to the shopper as a fact.
"""

from __future__ import annotations

import re

from app.matching import arabic
from app.matching.rules import CATEGORY_RULES
from app.matching.extractors import Keyword

# Edits allowed, by token length. Longer words tolerate more because a
# proportional slip is a bigger absolute one, and because a long word matching
# within two edits is far less likely to be a coincidence than a short one.
_MAX_EDITS = ((3, 0), (5, 1), (99, 2))


def _allowed_edits(length: int) -> int:
    for limit, edits in _MAX_EDITS:
        if length <= limit:
            return edits
    return 0


def _build_vocabulary() -> frozenset[str]:
    """
    Every literal word the rules can recognise, harvested from rules.py.

    Regex-based extractors (model numbers, refresh rates) contribute nothing:
    they match patterns, not words, and there is no fixed spelling to correct
    towards.
    """
    words: set[str] = set()

    for rules in CATEGORY_RULES.values():
        words.update(rules.detectors)
        words.update(rules.brand_detectors)
        for attribute in rules.attributes:
            extractor = attribute.extractor
            if isinstance(extractor, Keyword):
                words.update(extractor.values)
                words.update(extractor.synonyms)

    # Multi-word entries ("pro max", "space gray") are split: correction works
    # token by token, and "spcae gray" should still find "space".
    tokens: set[str] = set()
    for word in words:
        tokens.update(word.split())

    return frozenset(t for t in tokens if len(t) >= 3 and not any(c.isdigit() for c in t))


VOCABULARY = _build_vocabulary()


def _build_arabic_vocabulary() -> frozenset[str]:
    """
    The Arabic side, harvested from arabic.TERMS the same way.

    WHY A SECOND VOCABULARY RATHER THAN ONE: a misspelled Arabic word is not
    near any English word, and vice versa. Comparing "سمسونج" against "samsung"
    is a distance of the whole string, so a single mixed pool would find
    nothing while making every lookup slower. Script picks the pool.

    Keys are already folded (see arabic.py), so a correction lands on the
    spelling the transliterator can actually match.
    """
    tokens: set[str] = set()
    for term in arabic.TERMS:
        tokens.update(term.split())
    return frozenset(t for t in tokens if len(t) >= 3)


ARABIC_VOCABULARY = _build_arabic_vocabulary()

# The definite article, written joined to its noun. "الايفون" should correct
# and transliterate as readily as "ايفون".
_ARTICLE = "ال"


def _distance_within(a: str, b: str, budget: int) -> int | None:
    """
    Levenshtein distance, abandoned as soon as it exceeds `budget`.

    Returns None when the words are further apart than the budget allows. The
    early exit matters: this runs against the whole vocabulary for every
    unrecognised token, and most candidates are nowhere near.
    """
    if abs(len(a) - len(b)) > budget:
        return None

    previous = list(range(len(b) + 1))
    for i, ch_a in enumerate(a, start=1):
        current = [i]
        for j, ch_b in enumerate(b, start=1):
            current.append(
                min(
                    previous[j] + 1,          # deletion
                    current[j - 1] + 1,       # insertion
                    previous[j - 1] + (ch_a != ch_b),  # substitution
                )
            )
        # Every path through the remaining rows can only grow, so once the
        # best cell in this row is over budget the answer is too.
        if min(current) > budget:
            return None
        previous = current

    return previous[-1] if previous[-1] <= budget else None


def correct_token(token: str) -> str | None:
    """
    The vocabulary word this token was probably meant to be, or None.

    None means "leave it alone", which is the answer for the overwhelming
    majority of tokens: words we already know, model codes, numbers, and words
    that are simply not close to anything.

    Arabic tokens are corrected against the Arabic vocabulary and returned in
    Arabic -- transliteration happens later, in normalize(). Correcting
    straight to the English token here would work for search but would leave
    the reported correction unreadable to the person who typed it: being told
    that "سمسونج" was read as "samsung" explains nothing to an Arabic reader.
    """
    if any(ch.isdigit() for ch in token):
        return None  # model codes and capacities -- see the module docstring

    if arabic.has_arabic(token):
        return _correct_arabic(token)

    if token in VOCABULARY:
        return None  # already a word we know
    budget = _allowed_edits(len(token))
    if budget == 0:
        return None

    best: str | None = None
    best_distance = budget + 1
    tied = False

    for word in VOCABULARY:
        distance = _distance_within(token, word, budget)
        if distance is None:
            continue
        if distance < best_distance:
            best, best_distance, tied = word, distance, False
        elif distance == best_distance and word != best:
            tied = True

    if best is None or tied:
        # A tie is a coin flip. Correcting "samsng" to whichever of two equally
        # near words happened to be iterated first would present a guess to the
        # shopper as a decision.
        return None
    return best


def correct(text: str) -> tuple[str, dict[str, str]]:
    """
    Correct a whole query.

    Returns the corrected text and a {typed: corrected} map, so the caller can
    tell the shopper what was changed. Showing the correction is not a nicety:
    a search that silently answers a different question than the one asked is
    how someone ends up buying the wrong phone.
    """
    corrections: dict[str, str] = {}

    def replace(match: re.Match) -> str:
        token = match.group(0)
        fixed = correct_token(token.lower())
        if fixed is None:
            return token
        corrections[token] = fixed
        return fixed

    corrected = re.sub(r"[^\W\d_]+", replace, text)
    return corrected, corrections


def _correct_arabic(token: str) -> str | None:
    """
    The Arabic vocabulary word this token was probably meant to be.

    Folded before comparing, because the vocabulary is stored folded: without
    it "أيفون" and "ايفون" are one edit apart from each other and the budget
    is spent on orthography instead of on the actual typo.

    The definite article is tried both ways -- "الايفون" is the same word as
    "ايفون" and must not be judged two edits away from it.
    """
    folded = arabic.fold(token)
    if folded in ARABIC_VOCABULARY:
        return None

    stem = folded
    prefix = ""
    if folded.startswith(_ARTICLE) and folded[len(_ARTICLE):] in ARABIC_VOCABULARY:
        return None  # "الايفون" -- already correct, article and all
    if folded.startswith(_ARTICLE) and len(folded) > len(_ARTICLE) + 2:
        stem = folded[len(_ARTICLE):]
        prefix = _ARTICLE

    budget = _allowed_edits(len(stem))
    if budget == 0:
        return None

    best_distance = budget + 1
    best: list[str] = []

    for word in ARABIC_VOCABULARY:
        distance = _distance_within(stem, word, budget)
        if distance is None:
            continue
        if distance < best_distance:
            best_distance, best = distance, [word]
        elif distance == best_distance:
            best.append(word)

    if not best:
        return None

    if len(best) > 1:
        # A tie between words that MEAN THE SAME THING is not a guess.
        # "شاشت" is one edit from both "شاشه" and "شاشات", and both are the
        # word for a monitor -- refusing there would fail the shopper to
        # protect them from a distinction that does not exist. A tie between
        # different meanings is still refused, which is the case the rule was
        # written for.
        meanings = {arabic.TERMS.get(word) for word in best}
        if len(meanings) > 1 or None in meanings:
            return None

    return prefix + sorted(best)[0]
