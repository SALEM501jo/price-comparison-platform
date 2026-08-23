"""
Tests for the structured matching engine.

The headline case is the one the platform exists to solve: a fully specified
query must return the exact product first, then close variants, then similar
ones -- and must never rank a different product above the right one.
"""

import pytest

from app.matching import CLOSE, EXACT, EXCLUDED, SIMILAR, parse, score_match

QUERY = "iPhone 11 Pro Black 128GB"


def rank(query_text, listings):
    """Score every listing and return (score, tier, name), best first."""
    query = parse(query_text)
    scored = []
    for name in listings:
        result = score_match(query, parse(name))
        scored.append((result.score, result.tier, name))
    return sorted(scored, key=lambda row: -row[0])


# --- Parsing ---------------------------------------------------------------


class TestParsing:
    def test_extracts_all_phone_attributes(self):
        parsed = parse("Apple iPhone 11 Pro 128GB Black")
        assert parsed.specified == {
            "brand": "apple",
            "model": "iphone 11",
            "variant": "pro",
            "storage": "128gb",
            "color": "black",
        }

    def test_word_order_does_not_change_the_parse(self):
        """The failure mode that broke string similarity must not exist here."""
        a = parse("iPhone 11 Pro Black 128GB")
        b = parse("Apple iPhone 11 Pro 128GB Black")
        assert a.attributes == b.attributes

    def test_filler_words_are_ignored(self):
        a = parse("iPhone 11 Pro 128GB Black")
        b = parse("Apple iPhone 11 Pro 128GB 5G Smartphone - Black (New)")
        assert a.attributes == b.attributes

    def test_brand_inferred_from_product_line(self):
        assert parse("iPhone 15 128GB").get("brand") == "apple"
        assert parse("Galaxy S24 256GB").get("brand") == "samsung"

    def test_absent_variant_means_base_not_unknown(self):
        assert parse("Apple iPhone 11 128GB Black").get("variant") == "base"
        assert parse("Apple iPhone 11 Pro 128GB").get("variant") == "pro"

    def test_pro_max_beats_pro_and_max(self):
        assert parse("iPhone 15 Pro Max 256GB").get("variant") == "pro max"

    def test_terabyte_normalised_to_gigabytes(self):
        assert parse("iPhone 15 Pro 1TB").get("storage") == "1024gb"

    def test_multiword_colour_wins_over_substring(self):
        assert parse("iPhone 11 Pro 128GB Midnight Green").get("color") == "midnight green"

    def test_ram_is_not_mistaken_for_storage(self):
        parsed = parse("MacBook Pro M3 16GB RAM 512GB SSD")
        assert parsed.get("storage") == "512gb"
        assert parsed.get("ram") == "16gb"

    def test_category_detection(self):
        assert parse("iPhone 15 Pro").category == "phones"
        assert parse("MacBook Air M3 256GB").category == "laptops"


# --- The core requirement --------------------------------------------------


class TestTieredResults:
    CATALOGUE = [
        "Apple iPhone 11 Pro 128GB Black",
        "iPhone 11 Pro Black 128GB Smartphone 5G",
        "Apple iPhone 11 Pro 128GB Midnight Green",
        "Apple iPhone 11 Pro 256GB Black",
        "Apple iPhone 11 Pro Max 128GB Black",
        "Apple iPhone 11 128GB Black",
        "Apple iPhone 12 Pro 128GB Black",
    ]

    def test_exact_match_ranks_first(self):
        ranked = rank(QUERY, self.CATALOGUE)
        assert ranked[0][1] == EXACT

    def test_both_spellings_of_the_exact_product_are_exact(self):
        ranked = rank(QUERY, self.CATALOGUE)
        exact = {name for score, tier, name in ranked if tier == EXACT}
        assert exact == {
            "Apple iPhone 11 Pro 128GB Black",
            "iPhone 11 Pro Black 128GB Smartphone 5G",
        }

    def test_no_wrong_product_outranks_the_right_one(self):
        """
        Regression guard for the original engine, where iPhone 11 Pro Max and
        the 256GB model both outranked the product the user actually asked for.
        """
        ranked = rank(QUERY, self.CATALOGUE)
        best = ranked[0][0]
        for score, _tier, name in ranked:
            if name != "Apple iPhone 11 Pro 128GB Black" and score >= best:
                assert name == "iPhone 11 Pro Black 128GB Smartphone 5G", (
                    f"{name!r} scored {score}, at or above the exact match"
                )

    @pytest.mark.parametrize(
        "listing,expected_tier",
        [
            ("Apple iPhone 11 Pro 128GB Black", EXACT),
            ("Apple iPhone 11 Pro 128GB Midnight Green", CLOSE),
            ("Apple iPhone 11 Pro 256GB Black", SIMILAR),
            ("Apple iPhone 11 Pro Max 128GB Black", SIMILAR),
            ("Apple iPhone 12 Pro 128GB Black", EXCLUDED),
        ],
    )
    def test_tier_assignment(self, listing, expected_tier):
        result = score_match(parse(QUERY), parse(listing))
        assert result.tier == expected_tier

    def test_colour_difference_scores_higher_than_storage_difference(self):
        """Colour is cosmetic; storage is a different product at a different price."""
        query = parse(QUERY)
        colour = score_match(query, parse("Apple iPhone 11 Pro 128GB Midnight Green"))
        storage = score_match(query, parse("Apple iPhone 11 Pro 256GB Black"))
        assert colour.score > storage.score


# --- Explainability --------------------------------------------------------


class TestExplainability:
    def test_exact_match_has_no_differences(self):
        result = score_match(parse(QUERY), parse("Apple iPhone 11 Pro 128GB Black"))
        assert result.differences == []

    def test_difference_is_described_in_words(self):
        result = score_match(
            parse(QUERY), parse("Apple iPhone 11 Pro 128GB Midnight Green")
        )
        assert result.differences == ["different colour (midnight green, not black)"]

    def test_storage_difference_is_described(self):
        result = score_match(parse(QUERY), parse("Apple iPhone 11 Pro 256GB Black"))
        assert result.differences == ["different storage (256gb, not 128gb)"]


# --- Gates and edge cases --------------------------------------------------


class TestGatesAndEdgeCases:
    def test_different_brand_is_excluded_outright(self):
        result = score_match(
            parse("iPhone 11 Pro 128GB Black"),
            parse("Samsung Galaxy S24 128GB Black"),
        )
        assert result.tier == EXCLUDED
        assert result.score == 0.0

    def test_different_category_is_excluded(self):
        result = score_match(
            parse("iPhone 15 Pro 256GB"), parse("MacBook Pro M3 256GB")
        )
        assert result.tier == EXCLUDED

    def test_unspecified_attributes_are_not_penalised(self):
        """Searching "iPhone 11 Pro" must not punish a listing for having a colour."""
        result = score_match(
            parse("iPhone 11 Pro"), parse("Apple iPhone 11 Pro 128GB Black")
        )
        assert result.tier == EXACT

    def test_vague_query_still_scores_out_of_100(self):
        result = score_match(parse("iPhone 11"), parse("Apple iPhone 11 128GB Black"))
        assert result.score == 100.0

    def test_scoring_is_symmetric_for_identical_products(self):
        a = parse("Apple iPhone 11 Pro 128GB Black")
        b = parse("iPhone 11 Pro Black 128GB Smartphone 5G")
        assert score_match(a, b).score == score_match(b, a).score


class TestGateExplainability:
    def test_brand_gate_failure_is_explained(self):
        """An excluded result must not look identical to a perfect one."""
        result = score_match(
            parse("iPhone 11 Pro 128GB Black"),
            parse("Samsung Galaxy S24 128GB Black"),
        )
        assert result.tier == EXCLUDED
        assert result.differences == ["different brand (samsung, not apple)"]

    def test_category_mismatch_is_excluded_without_crashing(self):
        result = score_match(parse("iPhone 15 Pro"), parse("MacBook Pro M3"))
        assert result.tier == EXCLUDED
        assert result.differences == []


class TestColourSynonyms:
    def test_apple_midnight_is_the_black_colourway(self):
        """The scraper docstring's own example: three names, one product."""
        assert parse("Apple iPhone 15 128GB 5G - Midnight").get("color") == "black"
        assert parse("Apple iPhone 15 128GB Black").get("color") == "black"

    def test_midnight_listing_matches_the_black_listing_exactly(self):
        result = score_match(
            parse("Apple iPhone 15 128GB 5G Smartphone - Black"),
            parse("Apple iPhone 15 128GB 5G - Midnight"),
        )
        assert result.tier == EXACT

    def test_midnight_green_stays_a_distinct_colour(self):
        """Longest match wins, so the iPhone 11 Pro colour is not swallowed."""
        assert parse("iPhone 11 Pro 128GB Midnight Green").get("color") == "midnight green"

    def test_grey_and_gray_are_the_same_colour(self):
        assert parse("MacBook Air M3 Space Grey").get("color") == "space gray"
        assert parse("MacBook Air M3 Space Gray").get("color") == "space gray"


class TestUnrecognisedInput:
    """
    Regression guards. detect_category() used to fall back to a default, so
    anything unrecognised was parsed with the phone rules -- and because
    `variant` defaults to "base", a query of "%%%%" produced a non-empty
    attribute set and scored 100% EXACT against a real handset.
    """

    @pytest.mark.parametrize("junk", ["%%%%", "____", "zzzz", "!!!", "12345"])
    def test_junk_input_yields_no_category_and_no_attributes(self, junk):
        parsed = parse(junk)
        assert parsed.category is None
        assert parsed.specified == {}

    def test_junk_never_scores_against_a_real_product(self):
        result = score_match(parse("%%%%"), parse("Apple iPhone 11 Pro 128GB Black"))
        assert result.tier == EXCLUDED
        assert result.score == 0.0

    def test_unknown_category_is_not_forced_into_phones(self):
        """A console is not a phone just because nothing else matched."""
        assert parse("Sony PlayStation 5 Standard Edition").category is None

    def test_a_recognised_product_still_parses(self):
        assert parse("Apple iPhone 11 Pro 128GB Black").category == "phones"
        assert parse("MacBook Air M3 256GB Silver").category == "laptops"
