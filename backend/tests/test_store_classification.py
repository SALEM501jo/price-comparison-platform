"""
The store's product_type is believed -- including when it says no.

THE PROBLEM THIS SOLVES: an accessory names the product it fits. "IPHONE 15
PRO CASE" states a model exactly as a handset does, and "Samsung microSD
256GB" states a capacity exactly as a handset does, so no tightening of
requires_any can separate them -- the evidence a phone provides is evidence a
phone case provides too. A blocklist of "case, cover, protector, ..." is the
approach this project already rejected for going stale.

The signal that does separate them is one nobody has to maintain: the shop
already classified its own catalogue. The code consulted that classification
and then ignored it whenever it was not one of ours, falling through to guess
from the title -- which is how a microwave oven, a Nintendo game, an SSD and a
refrigerator all became phones.
"""

from app.matching import detect_category, parse


class TestPluralsAreTheSameStatement:
    """
    Stores write "Phones" as readily as "Phone", and \\bphone\\b matches
    neither the plural nor "Mobiles". Before this, a shop that had classified
    its whole catalogue correctly was read as having said nothing at all.
    """

    def test_a_plural_product_type_still_resolves(self):
        assert detect_category("Phones") == "phones"
        assert detect_category("Monitors") == "monitors"
        assert detect_category("Laptops") == "laptops"

    def test_mobile_is_a_category_word(self):
        assert detect_category("Mobile") == "phones"
        assert detect_category("Mobiles") == "phones"

    def test_the_singular_still_works(self):
        assert detect_category("Smart Phone") == "phones"
        assert detect_category("Monitor") == "monitors"


class TestTheStoreIsBelievedWhenItSaysNo:
    """Each of these was really in the catalogue, filed as a phone."""

    def test_a_phone_case_is_not_a_phone(self):
        parsed = parse("Totu Ring Lenss, Iphone 15, Clear", hint="Covers & Cases")
        assert parsed.category is None

    def test_a_screen_protector_is_not_a_phone(self):
        parsed = parse("ANKER IPHONE 15 PRO MAX SCREEN PROTECTER", hint="Accessories")
        assert parsed.category is None

    def test_a_microwave_is_not_a_phone(self):
        """
        The clearest case. The store said "Microwave Ovens"; the word
        "Samsung" in the title was believed instead.
        """
        parsed = parse(
            "Samsung 30L Bespoke Grill Microwave Oven", hint="Microwave Ovens"
        )
        assert parsed.category is None

    def test_a_memory_card_is_not_a_phone(self):
        parsed = parse(
            "Samsung microSD Express 256GB for Switch 2", hint="External Storage"
        )
        assert parsed.category is None

    def test_a_motherboard_is_not_a_laptop(self):
        parsed = parse(
            "MSI MPG B850I EDGE TI WIFI Supports AMD Ryzen 9000", hint="Motherboard"
        )
        assert parsed.category is None


class TestRealProductsSurvive:
    def test_a_phone_filed_under_phones(self):
        parsed = parse("Apple iPhone 15 128GB 5G Smartphone - Black", hint="Phones")
        assert parsed.category == "phones"

    def test_a_phone_filed_under_mobile(self):
        parsed = parse("Samsung A26 8GB 256GB - Black", hint="Mobile")
        assert parsed.category == "phones"

    def test_a_monitor_filed_under_monitor(self):
        parsed = parse(
            'Dell SE2725HM Flat Monitor 27" FHD IPS @100HZ', hint="Monitor"
        )
        assert parsed.category == "monitors"

    def test_a_laptop_whose_title_names_no_category(self):
        """
        The reason the hint exists at all: this is unmistakably a laptop to a
        person and contains no word the parser recognises.
        """
        parsed = parse(
            "Hp Intel I7 -8550U, 16GB DDR4 & 512GB SSD, 15.6Inch", hint="Notebook"
        )
        assert parsed.category == "laptops"


class TestAPlaceholderIsNotAStatement:
    """
    "Uncategorized" is the platform's OWN filler -- deduplication.py writes it
    for every listing that arrives without a product_type, which is every
    merchant listing. Treating it as the shop's classification would let our
    placeholder veto a real shop's phone.
    """

    def test_uncategorized_falls_through_to_the_title(self):
        assert parse("iPhone 15 128GB Black", hint="Uncategorized").category == "phones"

    def test_the_british_spelling_too(self):
        assert parse("iPhone 15 128GB Black", hint="Uncategorised").category == "phones"

    def test_an_empty_hint_falls_through(self):
        assert parse("iPhone 15 128GB Black", hint="").category == "phones"
        assert parse("iPhone 15 128GB Black", hint=None).category == "phones"


class TestQueriesAreUnaffected:
    """
    A shopper never supplies a product_type, so none of this touches search.
    Worth pinning: the hint path is ingest-only, and a change there that leaked
    into query parsing would break every search at once.
    """

    def test_a_query_still_parses_without_a_hint(self):
        parsed = parse(
            "iPhone 15 128GB Black", require_evidence=False, apply_defaults=False
        )
        assert parsed.category == "phones"
        assert parsed.get("storage") == "128gb"

    def test_an_explicit_category_skips_the_hint_entirely(self):
        """
        search.py and the dedup engine both re-parse a stored product with
        category= supplied. That path must not consult a hint at all.
        """
        parsed = parse("Totu Ring Lenss, Iphone 15, Clear", category="phones")
        assert parsed.category == "phones"


class TestOneGateAppliedOnce:
    def test_the_scraper_gate_matches_the_storage_side(self):
        """
        The relevance gate used to test the product_type as free-standing TEXT
        and the title separately, while the storage side parsed the title WITH
        the hint. Everything between the two gates was ingested and then filed
        with no category -- rows search can never return.
        """
        from app.services.scrapers.shopify import ShopifyScraper
        from app.services.scrapers.base import StoreConfig

        scraper = ShopifyScraper(
            StoreConfig(code="t", name="T", host="example.com", platform="shopify"),
            {"example.com"},
        )

        accessory = {
            "title": "Totu Ring Lenss, Iphone 15, Clear",
            "product_type": "Covers & Cases",
        }
        phone = {
            "title": "Apple iPhone 15 128GB 5G Smartphone - Black",
            "product_type": "Smart Phone",
        }

        assert scraper._is_relevant(accessory) is False
        assert scraper._is_relevant(phone) is True

        # And the gate agrees with what storage would decide.
        for raw, expected in ((accessory, None), (phone, "phones")):
            stored = parse(raw["title"], hint=raw["product_type"]).category
            assert stored == expected
            assert scraper._is_relevant(raw) is (stored is not None)


class TestTheHeadNounDecides:
    """
    A product_type is a LABEL, not prose: the last noun says what the thing
    is, and the earlier words qualify it.

    This was found the hard way. Adding "mobile" as a category word -- needed,
    because iGeek files real handsets under "Mobile" -- immediately made
    "Mobile Case" and "Mobile Accessories" resolve to phones, and three phone
    cases walked straight back into the catalogue. Scanning a label for any
    category word reads the qualifier as the subject.

    Grammar rather than a list of banned words, so it covers labels nobody has
    seen yet and needs no maintenance.
    """

    def test_a_qualifier_is_not_the_subject(self):
        from app.matching.parser import classify_hint

        assert classify_hint("Mobile Case") is None
        assert classify_hint("Mobile Accessories") is None
        assert classify_hint("Laptop Bag") is None
        assert classify_hint("Apple Covers & Cases") is None

    def test_the_bare_category_word_still_resolves(self):
        from app.matching.parser import classify_hint

        assert classify_hint("Mobile") == "phones"
        assert classify_hint("Smart Phone") == "phones"
        assert classify_hint("Gaming Monitor") == "monitors"
        assert classify_hint("Notebook") == "laptops"

    def test_a_trailing_model_number_is_dropped(self):
        """iGeek files real handsets under "iPhone 17"."""
        from app.matching.parser import classify_hint

        assert classify_hint("iPhone 17") == "phones"
        assert classify_hint("iPhone 16") == "phones"

    def test_the_three_cases_that_got_back_in(self):
        """The exact listings that survived the first version of this rule."""
        for name, hint in (
            ("SKINARAMA IPHONE 15 PRO CASE", "Mobile Case"),
            ("PULOKA IPHONE 15 PRO ALL ROUND PROTECTIVE CASE", "Mobile Case"),
            ("PULOKA IPHONE 15 ALL ROUND PROTECTIVE CASE", "Mobile Accessories"),
        ):
            assert parse(name, hint=hint).category is None, name

    def test_titles_are_still_read_as_prose(self):
        """
        The head-noun rule is for LABELS only. A title has no head noun in
        this sense -- "Apple iPhone 15 128GB Black" ends in a colour -- so
        titles keep the whole-string scan.
        """
        assert parse("Apple iPhone 15 128GB Black").category == "phones"
        assert parse("iPhone 15 128GB Midnight").category == "phones"
