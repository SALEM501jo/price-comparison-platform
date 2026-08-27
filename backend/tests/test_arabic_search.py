"""
Arabic queries reach the same products as their English equivalents.

The engine is English-canonical: Arabic is folded onto the tokens rules.py
already knows (see app/matching/arabic.py). These tests pin that down at the
two levels that matter -- the fold itself, and the parse it feeds.

WHAT WOULD BREAK WITHOUT THEM: silently. An Arabic query that fails to fold
does not error; it parses to nothing and returns an empty result page, which
looks exactly like "we do not stock that".
"""

from app.matching import parse
from app.matching.arabic import fold, has_arabic, prepare


class TestFolding:
    """Orthography, before any vocabulary is consulted."""

    def test_arabic_indic_digits_become_western(self):
        # "١٢٨" has to reach the capacity extractor as "128" or the storage
        # is simply not seen, and the query silently loses an attribute.
        assert fold("١٢٨") == "128"
        assert fold("٢٥٦") == "256"

    def test_extended_arabic_digits_become_western(self):
        """Persian digits, which some Arabic keyboards produce."""
        assert fold("۱۲۸") == "128"

    def test_diacritics_are_dropped(self):
        # Tashkeel are pronunciation marks; they carry no identity.
        assert fold("أَسْوَد") == fold("اسود")

    def test_the_alef_family_collapses(self):
        """The same handset is written three ways, all equally correct."""
        assert fold("آيفون") == fold("أيفون") == fold("ايفون")

    def test_ta_marbuta_and_alef_maqsura_fold(self):
        assert fold("شاشة") == "شاشه"
        assert fold("علي") == fold("على")

    def test_latin_is_untouched(self):
        assert fold("iPhone 15 128GB") == "iPhone 15 128GB"

    def test_has_arabic_detects_script_not_language(self):
        assert has_arabic("ايفون")
        assert not has_arabic("iPhone 15 Pro Max")
        assert has_arabic("iPhone ايفون")  # mixed, as people actually type


class TestVocabulary:
    def test_a_brand_becomes_its_canonical_token(self):
        assert prepare("ايفون") == "iphone"
        assert prepare("سامسونج") == "samsung"

    def test_the_definite_article_is_tolerated(self):
        """People type "الايفون" as readily as "ايفون"."""
        assert prepare("الايفون") == "iphone"
        assert prepare("الاسود") == "black"

    def test_longest_term_wins(self):
        # "جيجابايت" must not be matched as "جيجا" plus a stray tail.
        assert prepare("جيجابايت") == "gb"
        assert prepare("ماك بوك") == "macbook"

    def test_unknown_arabic_is_left_alone(self):
        """
        A word we do not know must survive untranslated rather than be
        guessed at. A wrong guess produces a confident match against the
        wrong product, which is worse than no match at all.
        """
        assert "كتاب" in prepare("كتاب")


class TestArabicQueriesParse:
    """The whole point: an Arabic query produces the same attributes."""

    def test_a_full_arabic_phone_query(self):
        arabic = parse(
            "ايفون ١٥ ١٢٨ جيجا اسود", require_evidence=False, apply_defaults=False
        )
        english = parse(
            "iPhone 15 128GB Black", require_evidence=False, apply_defaults=False
        )
        assert arabic.category == "phones"
        assert arabic.specified == english.specified

    def test_variants_survive_translation(self):
        parsed = parse(
            "ايفون ١٥ برو ماكس ٢٥٦ جيجا",
            require_evidence=False,
            apply_defaults=False,
        )
        assert parsed.get("variant") == "pro max"
        assert parsed.get("storage") == "256gb"

    def test_a_laptop_query_keeps_its_variant(self):
        parsed = parse(
            "لابتوب ماك بوك اير ٢٥٦ جيجا",
            require_evidence=False,
            apply_defaults=False,
        )
        assert parsed.category == "laptops"
        assert parsed.get("model") == "macbook"
        assert parsed.get("variant") == "air"

    def test_a_monitor_query_in_arabic(self):
        parsed = parse(
            "شاشة ٢٧ بوصة 2k ١٨٠ هرتز",
            require_evidence=False,
            apply_defaults=False,
        )
        assert parsed.category == "monitors"
        assert parsed.get("size") == "27"
        assert parsed.get("refresh") == "180"

    def test_mixed_script_is_normal_and_works(self):
        """Nobody switches keyboards mid-query for a Latin model number."""
        parsed = parse(
            "ايفون 15 pro max اسود", require_evidence=False, apply_defaults=False
        )
        assert parsed.get("model") == "iphone 15"
        assert parsed.get("variant") == "pro max"
        assert parsed.get("color") == "black"

    def test_televisions_are_excluded_in_arabic_too(self):
        """
        UNSUPPORTED_CATEGORIES is worthless if it only reads English. Without
        the TV terms in the vocabulary, "تلفزيون سامسونج" sails past the
        exclusion and is scored against the PHONE rules -- which is exactly
        how televisions became phones in this catalogue once already.
        """
        assert parse("تلفزيون سامسونج 55 بوصة").category is None
        assert parse("تلفاز ال جي 65 بوصة").category is None

    def test_an_arabic_listing_is_parsed_the_same_way(self):
        """
        Folding lives in normalize(), which both sides of the system use. A
        merchant who types their stock in Arabic must land on the same
        canonical product as the scraped English listing, or the comparison
        this platform exists for silently does not happen.
        """
        listing = parse("ايفون 15 128 جيجا اسود")
        query = parse(
            "iPhone 15 128GB Black", require_evidence=False, apply_defaults=False
        )
        assert listing.category == "phones"
        for name, value in query.specified.items():
            assert listing.get(name) == value
