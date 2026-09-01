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
    """
    The engine reports WHICH attribute differed and WHAT the two values were.

    It deliberately does not compose a sentence. These assertions are on the
    structure for that reason: an assertion on English prose here is exactly
    what let the explanation stay English-only on an Arabic-first site.
    """

    def test_exact_match_has_no_differences(self):
        result = score_match(parse(QUERY), parse("Apple iPhone 11 Pro 128GB Black"))
        assert result.differences == ()

    def test_difference_names_the_attribute_and_both_values(self):
        result = score_match(
            parse(QUERY), parse("Apple iPhone 11 Pro 128GB Midnight Green")
        )
        (colour,) = result.differences
        assert colour.name == "color"
        assert colour.label == "colour"
        assert colour.query_value == "black"
        assert colour.candidate_value == "midnight green"

    def test_storage_difference_is_reported(self):
        result = score_match(parse(QUERY), parse("Apple iPhone 11 Pro 256GB Black"))
        (storage,) = result.differences
        assert storage.name == "storage"
        assert (storage.query_value, storage.candidate_value) == ("128gb", "256gb")

    def test_unstated_attribute_is_null_not_absent(self):
        """
        "The listing does not say" and "the listing says something else" are
        different facts, and they read as different sentences. A null
        candidate_value is what lets the client tell them apart.
        """
        result = score_match(parse(QUERY), parse("Apple iPhone 11 Pro 128GB"))
        (colour,) = result.differences
        assert colour.name == "color"
        assert colour.query_value == "black"
        assert colour.candidate_value is None


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
        (brand,) = result.differences
        assert brand.name == "brand"
        assert (brand.query_value, brand.candidate_value) == ("apple", "samsung")

    def test_category_mismatch_is_excluded_without_crashing(self):
        result = score_match(parse("iPhone 15 Pro"), parse("MacBook Pro M3"))
        assert result.tier == EXCLUDED
        assert result.differences == ()


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


# --- Brands and product lines found in the real Jordanian catalogues --------


class TestJordanianCatalogueBrands:
    """
    Regression cover for listings that parsed to nothing before.

    Every title here is copied verbatim from a live store feed. Measured
    against the four real catalogues, these rules moved SmartBuy's phones from
    85% to 100% parsed, AmmanCart's from 39% to 89%, and iGeek's laptops from
    89% to 97%. A brand the engine cannot see is excluded by the brand gate,
    so an unlisted marque is not a cosmetic gap -- it is silent data loss.
    """

    @pytest.mark.parametrize(
        "title, brand",
        [
            ("Motorola Edge 70 5G, 12GB & 512GB, 6.7Inch, Grey", "motorola"),
            ("Moto Smart Phone G06 4G, 4GB & 128GB, 6.8Inch, Green", "motorola"),
            ("TCL Smart Phone 60 SE 4G, 8GB & 512GB, 6.7Inch, White", "tcl"),
            ("DOOGEE Blade 10 Ultra", "doogee"),
            ("TECNO SPARK 50", "tecno"),
            ("oppo Smart Phones A3", "oppo"),
        ],
    )
    def test_previously_invisible_brands_now_resolve(self, title, brand):
        assert parse(title).get("brand") == brand

    @pytest.mark.parametrize(
        "title, model",
        [
            # These marques name their ranges instead of numbering them off
            # the brand, so the brand-adjacent rule never fired: there are no
            # digits after "tecno" in "TECNO SPARK 50".
            ("TECNO SPARK 50", "spark 50"),
            ("TECNO CAMON 40 Pro", "camon 40"),
            ("Tecno POVA 6 Pro 5G", "pova 6"),
            ("Oppo Smart Phones Reno12 F 4G", "reno 12"),
            ("Motorola Edge 70 5G, 12GB & 512GB, 6.7Inch, Grey", "edge 70"),
            ("Motorola Moto Razr 50, 8GB & 256GB, 6.9Inch, Grey", "razr 50"),
            ("DOOGEE Blade 10 Ultra", "blade 10"),
        ],
    )
    def test_named_product_ranges_yield_a_model(self, title, model):
        assert parse(title).get("model") == model

    def test_redmi_note_is_not_collapsed_into_redmi(self):
        """
        The two-word sub-line has to be tried before the bare one.

        AmmanCart writes "Redmi Note 15" where SmartBuy writes "Xiaomi Redmi
        17". If the bare "redmi" pattern runs first it swallows the Note range
        and reports a model with no number, merging every Note into one row.
        """
        assert parse("Redmi Note 15 Pro+ 5G").get("model") == "redmi note 15"
        assert parse("Xiaomi Redmi Note 13").get("model") == "redmi note 13"
        assert parse("Xiaomi Redmi 17 4G, 6GB & 128GB").get("model") == "redmi 17"

    def test_redmi_note_still_belongs_to_xiaomi_not_samsung(self):
        """"note" alone maps to Samsung; the longer "redmi" token must win."""
        assert parse("Redmi Note 15 Pro+ 5G").get("brand") == "xiaomi"
        assert parse("Samsung Galaxy Note 20").get("brand") == "samsung"
        assert parse("Samsung Galaxy Note 20").get("model") == "galaxy note 20"

    def test_network_suffix_is_never_mistaken_for_a_model(self):
        """
        "5G" fits the bare model-code shape (digits then a letter). Without an
        explicit guard, every 5G handset came back with model "5g".
        """
        for title in ("oppo Smart Phones A5 PRO 5G", "TECNO SPARK 30C 5G"):
            assert parse(title).get("model") not in {"5g", "4g"}

    def test_ryzen_part_number_yields_a_processor(self):
        """
        The boundary used to sit straight after the series digit, so a full
        part number never matched -- in "Ryzen 5800H" the 5 is followed by an
        8, not a word boundary. Seven ASUS laptops carried no processor.
        """
        assert parse("ASUS Vivobook Pro 14 OLED M3401QA AMD RYZEN 5800H").get("cpu") == "ryzen 5"
        assert parse("ASUS TUF Gaming A16 AMD Ryzen 7 260 512GB").get("cpu") == "ryzen 7"

    def test_intel_core_ultra_is_a_processor(self):
        """Intel's current naming, with and without the word "Core"."""
        assert parse("HP 15-fd2104TU Intel Core Ultra 5 225U 512GB").get("cpu") == "ultra 5"
        assert parse("ASUS Vivobook 14 Flip (2025) Ultra 7 256V 1TB 32GB").get("cpu") == "ultra 7"

    def test_surface_is_a_laptop_with_a_model(self):
        parsed = parse("Microsoft Surface Pro 11 (2025) Intel Core Ultra 7 266V 512GB 16GB")
        assert parsed.category == "laptops"
        assert parsed.get("brand") == "microsoft"
        assert parsed.get("model") == "surface pro"

    def test_new_brands_do_not_disturb_the_headline_case(self):
        """The case the platform exists to solve must be untouched."""
        assert parse("Apple iPhone 11 Pro 128GB Black").specified == {
            "brand": "apple",
            "model": "iphone 11",
            "variant": "pro",
            "storage": "128gb",
            "color": "black",
        }

    def test_brand_gate_still_excludes_across_the_new_marques(self):
        """A Tecno must never be offered as a near-match for a Motorola."""
        result = score_match(parse("Motorola Edge 70 256GB"), parse("TECNO SPARK 50"))
        assert result.tier == EXCLUDED

    @pytest.mark.parametrize(
        "title",
        [
            # A screen size sits exactly where a model code does.
            'Samsung 55" U8000F Crystal UHD 4K Smart TV',
            "LG 65 inch UR78 4K Smart TV",
            "Samsung 32 inch M5 Smart Monitor",
            # A generation number does too.
            "Samsung Galaxy Buds 3 Pro",
            "oppo Enco Buds 2 Wireless Earbuds",
            "Xiaomi Robot Vacuum X20",
            "Xiaomi PFJ4197EU Xiaomi TV Stick 4K",
        ],
    )
    def test_appliances_and_accessories_are_not_phones(self, title):
        """
        The brand-adjacent model rule must not reach across a product name.

        AmmanCart's feed is mostly televisions and white goods. While the rule
        allowed any filler word before the code it produced phone model
        "samsung 3" for Galaxy Buds and "xiaomi x20" for a vacuum cleaner, and
        a 55-inch television matched a phone query -- the same failure as a
        laptop bag ranking as an exact match for "Laptop".
        """
        assert parse(title).category != "phones"

    def test_a_television_never_scores_against_a_phone(self):
        query = parse("Samsung A57 5G 256GB")
        listing = parse('Samsung 55" U8000F Crystal UHD 4K Smart TV')
        assert score_match(query, listing).tier == EXCLUDED

    @pytest.mark.parametrize(
        "title",
        [
            "ASUS TUF Gaming GeForce RTX 5070 Ti 16GB GDDR7 Graphics Card",
            "ASUS Dual GeForce RTX 5060 8GB GDDR7 OC Edition",
            "Kingston ValueRAM 8GB 3200MT/s DDR4 Non-ECC (Laptop RAM)",
        ],
    )
    def test_components_are_not_laptops(self, title):
        """
        A component's memory is not a machine's disk.

        iGeek sells GPUs and RAM beside laptops. "16GB GDDR7" satisfied the
        laptops rule that a real machine states its storage, so the graphics
        aisle arrived in the catalogue as laptops. The storage floor separates
        them on a property of the things themselves rather than a word list.
        """
        assert parse(title).category != "laptops"

    def test_the_storage_floor_does_not_reject_real_machines(self):
        assert parse("MacBook Air M3 256GB Silver").get("storage") == "256gb"
        assert parse("ASUS ROG Strix G16 i7 16GB 1TB SSD").get("storage") == "1024gb"
        assert parse("Lenovo ThinkPad X1 i7 16GB 512GB").get("storage") == "512gb"

    def test_phone_storage_keeps_no_floor(self):
        """32GB and 64GB handsets are real; the floor is a laptop rule only."""
        assert parse("Samsung A57 5G 64GB").get("storage") == "64gb"
