"""
The monitors category, and both eras of processor naming.

Every title here is copied from a live store feed.
"""

import pytest

from app.matching import parse
from app.matching.rules import UNSUPPORTED_CATEGORIES


# --- Televisions are not carried --------------------------------------------


class TestTelevisionsAreExcluded:
    """
    A TV shares a panel with a monitor and nothing else a buyer cares about.
    Nobody cross-shops a 77-inch OLED television against a 27-inch 180Hz
    gaming panel, so televisions are not a category here and must not be
    smuggled into one that is.
    """

    @pytest.mark.parametrize(
        "title",
        [
            "TCL C6K MiniLED QLED TV - 4K Ultra HD & 144Hz Google TV",
            'TCL P8K 85" QLED 4K UHD TV - Smart 144Hz & Dolby Atmos',
            "77 inch LG OLED evo AI C5 4K 144Hz Smart TV AI Magic remote webOS",
            'Samsung 55" U8000F Crystal UHD 4K Smart TV',
            "Xiaomi 4K TV Stick OB6-EU, Black",
        ],
    )
    def test_a_television_belongs_to_no_category(self, title):
        assert parse(title).category is None

    def test_a_television_is_excluded_even_with_a_store_hint(self):
        """The ingest path passes product_type, which must not override this."""
        assert (
            parse("TCL C6K MiniLED QLED TV 4K 144Hz", hint="Televisions").category
            is None
        )

    def test_the_exclusion_is_a_category_word_not_a_blocklist(self):
        """
        One word per category we have decided not to carry -- a closed set that
        changes when the product scope does. Accessories are kept out by
        requires_any instead, which does not need extending forever.

        It grew once, for desktops: an all-in-one carries every attribute this
        engine scores on a laptop, so nothing but the words tells them apart.
        """
        assert set(UNSUPPORTED_CATEGORIES) <= {
            "tv", "television", "televisions", "all in one", "desktop",
        }

    def test_a_resolution_is_not_a_phone_model(self):
        """"Xiaomi 4K TV Stick" became phone model "xiaomi 4k" before this."""
        assert parse("Xiaomi 4K TV Stick OB6-EU, Black").get("model") != "xiaomi 4k"


# --- Monitors ---------------------------------------------------------------


class TestMonitors:
    @pytest.mark.parametrize(
        "title",
        [
            'ASUS TUF Gaming VG27WQ 27" Curved 2K HDR 165Hz GAMING MONITOR',
            'LG UltraGear 32G810SA-W 32" 4K 144Hz UHD IPS Gaming Monitor',
            "MSI PRO MP243XW 100HZ IPS FHD 1ms Monitor",
        ],
    )
    def test_real_monitor_listings_are_recognised(self, title):
        assert parse(title).category == "monitors"

    def test_a_monitor_whose_title_omits_the_word_is_caught_by_the_hint(self):
        """
        "Lenovo ThinkVision S27-4e IPS 27" FHD 100Hz" never says "monitor",
        and "lenovo" is a laptop brand -- so the title alone routed it to
        LAPTOPS, where it failed requires_any and parsed to nothing. The
        store files it under product_type "Monitor", which is why the hint is
        consulted before the title rather than after it.
        """
        title = 'Lenovo ThinkVision S27-4e IPS 27" FHD 99% sRGB 100Hz - Black'
        assert parse(title, hint="Monitor").category == "monitors"
        assert parse(title, hint="Monitor").get("size") == "27"

    def test_the_attributes_a_buyer_compares_on_are_extracted(self):
        parsed = parse('ASUS TUF Gaming VG27WQ 27" Curved 2K HDR 165Hz GAMING MONITOR')
        assert parsed.get("size") == "27"
        assert parsed.get("resolution") == "2k"
        assert parsed.get("refresh") == "165"

    @pytest.mark.parametrize(
        "written, stored",
        [
            ("UHD", "4k"),
            ("4K", "4k"),
            ("QHD", "2k"),
            ("WQHD", "2k"),
            ("1440P", "2k"),
            ("FHD", "fhd"),
            ("1080p", "fhd"),
        ],
    )
    def test_one_panel_has_one_resolution_however_it_is_marketed(
        self, written, stored
    ):
        """
        The same monitor sold as "4K" at one shop and "UHD" at another is one
        product, not two.
        """
        title = f'Dell S2721 27" {written} IPS 75Hz Monitor'
        assert parse(title).get("resolution") == stored

    def test_fractional_sizes_survive(self):
        """
        24.5 and 23.8 are real panels, distinct from 24 at distinct prices.

        The stored value is "24 5", not "24.5": normalize() turned the decimal
        point into a space long before the extractor saw it. That is fine and
        deliberate -- what matters is that the value is CANONICAL (two shops
        both writing 24.5" produce the same string) and DISTINCT from 24. It
        is a matching key, not a label.
        """
        parsed = parse('MSI G255F 24.5" FHD 180Hz IPS Monitor')
        assert parsed.get("size") == "24 5"
        assert parsed.get("size") != parse('MSI G24C4 24" FHD 180Hz Monitor').get("size")

    def test_size_dominates_the_score(self):
        """
        A 24-inch is not a near-match for a 27-inch however well everything
        else agrees -- they are the decision a monitor buyer is making.
        """
        from app.matching import score_match

        a = parse('Dell S2421 24" FHD 75Hz IPS Monitor')
        b = parse('Dell S2721 27" FHD 75Hz IPS Monitor')
        assert score_match(a, b).score < 100

    def test_a_monitor_needs_more_than_a_size(self):
        """
        A stand or an arm "for 27-inch monitors" states a size and nothing
        else, which is why size alone does not make a listing a monitor.
        """
        assert parse('Generic Monitor Arm for 27" Displays').category != "monitors"

    def test_a_different_brand_is_still_excluded_outright(self):
        from app.matching import EXCLUDED, score_match

        a = parse('ASUS TUF VG27WQ 27" 2K 165Hz Monitor')
        b = parse('LG UltraGear 27" 2K 165Hz Monitor')
        assert score_match(a, b).tier == EXCLUDED


# --- Processors, old naming and new -----------------------------------------


class TestProcessorNaming:
    """
    Intel has shipped three naming schemes and AMD one, and the market carries
    all of them at once. A laptop whose processor cannot be read scores the
    same as one with no processor stated at all.
    """

    @pytest.mark.parametrize(
        "title, cpu",
        [
            # The old scheme, still most of the market.
            ("ASUS ROG Strix G16 Intel Core i7 14650HX 16GB 1TB SSD", "i7"),
            ("Dell Latitude i5-1335U 16GB 512GB", "i5"),
            ("HP 250 G9 Intel Core i3 1215U 8GB 256GB", "i3"),
            # The newer "Core Ultra" scheme.
            ("ASUS Zenbook S 14 OLED Intel Core Ultra 7 256V 1TB 32GB", "ultra 7"),
            ("HP AI Business 15-fd2104TU Intel Ultra 5 225U 512GB", "ultra 5"),
            # And Intel's OTHER new scheme, without "Ultra" -- named in the
            # project's own known-limitations list as unparsed.
            ("HP ProBook Intel Core 5-120U 16GB 512GB SSD", "core 5"),
            ("Dell Latitude Core 7-150U 16GB 512GB", "core 7"),
            # AMD.
            ("ASUS Vivobook Pro 14 OLED AMD RYZEN 5800H 512GB", "ryzen 5"),
            ("ASUS TUF Gaming A16 AMD Ryzen 7 260 512GB", "ryzen 7"),
            # Apple silicon.
            ("MacBook Pro 14 M5 512GB Space Gray", "m5"),
            # The cheap end, previously invisible.
            ("Lenovo IdeaPad Celeron N4020 4GB 128GB SSD", "celeron"),
        ],
    )
    def test_every_naming_scheme_is_read(self, title, cpu):
        assert parse(title).get("cpu") == cpu

    def test_the_three_intel_schemes_stay_distinct(self):
        """
        "Core i5", "Core Ultra 5" and "Core 5-120U" are three different product
        lines that happen to share a digit. Collapsing them onto one value
        would make a budget machine an exact match for a premium one.
        """
        values = {
            parse("Laptop Intel Core i5 1235U 16GB 512GB").get("cpu"),
            parse("Laptop Intel Core Ultra 5 225U 16GB 512GB").get("cpu"),
            parse("Laptop Intel Core 5-120U 16GB 512GB").get("cpu"),
        }
        assert len(values) == 3, values

    def test_a_bare_series_still_matches_a_full_part_number(self):
        """
        A shopper typing "i7 laptop" means any i7. Reading the part number as
        a different processor would make the obvious search fail.
        """
        assert parse("HP Laptop i7 16GB 512GB").get("cpu") == "i7"
        assert parse("HP Laptop i7-14650HX 16GB 512GB").get("cpu") == "i7"

    def test_a_model_designation_is_not_a_processor(self):
        """ASUS names TUF models A14 and A16; the Apple A-series must not win."""
        parsed = parse("ASUS TUF Gaming A16 AMD Ryzen 7 260 16GB 512GB")
        assert parsed.get("cpu") == "ryzen 7"
