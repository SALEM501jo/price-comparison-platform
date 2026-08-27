"""
Spelling correction of query words.

THE LINE THIS FEATURE HAS TO NOT CROSS: the project rejects string similarity
for deciding WHICH PRODUCT a query means, and it is right to -- 128GB and
256GB are one edit apart and are different products. Correcting a misspelled
WORD against a closed vocabulary is a different question, and these tests pin
down the boundary: brands and colours get corrected, model codes and
capacities never do.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.matching import parse
from app.matching.spelling import VOCABULARY, correct, correct_token
from app.models.alias import ProductAlias
from app.models.price import Price
from app.models.product import Product
from app.models.store import Store


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def catalogue(db_session):
    """One real handset, priced at one shop, so search has something to find."""
    name = "Apple iPhone 15 128GB Black"
    parsed = parse(name)
    product = Product(
        canonical_name=name,
        brand=parsed.get("brand"),
        match_category=parsed.category,
        match_attributes=parsed.specified,
    )
    store = Store(name="SmartBuy")
    db_session.add_all([product, store])
    db_session.commit()

    alias = ProductAlias(
        product_id=product.id,
        store_id=store.id,
        store_product_name=name,
        store_product_id="SB-1",
    )
    db_session.add(alias)
    db_session.commit()
    db_session.add(
        Price(alias_id=alias.id, price=800, delivery_cost=0, availability=True)
    )
    db_session.commit()
    return product


class TestVocabularyComesFromTheRules:
    def test_it_is_not_empty(self):
        assert len(VOCABULARY) > 50

    def test_it_carries_brands_colours_and_categories(self):
        for word in ("samsung", "apple", "black", "laptop", "monitor", "macbook"):
            assert word in VOCABULARY, f"{word} missing from the vocabulary"

    def test_a_brand_added_to_the_rules_is_spell_checked_for_free(self):
        """
        The vocabulary is derived from rules.py rather than hand-copied. These
        four were added to BRANDS after the first release; if the derivation
        broke, they would silently stop being correctable.
        """
        for word in ("motorola", "doogee", "tcl", "microsoft"):
            assert word in VOCABULARY

    def test_it_holds_no_digits(self):
        """
        Model codes must never enter the vocabulary: correcting towards them
        is how "a16" becomes "a15", which is a different laptop.
        """
        assert not [w for w in VOCABULARY if any(c.isdigit() for c in w)]


class TestCorrectToken:
    def test_a_misspelled_brand_is_corrected(self):
        assert correct_token("smasung") == "samsung"
        assert correct_token("xiomi") == "xiaomi"

    def test_a_misspelled_product_line_is_corrected(self):
        assert correct_token("iphon") == "iphone"
        assert correct_token("macbok") == "macbook"

    def test_a_correct_word_is_left_alone(self):
        assert correct_token("samsung") is None
        assert correct_token("black") is None

    def test_tokens_with_digits_are_never_touched(self):
        """
        The single most important guard here. Model codes are the densest
        source of near-misses in this catalogue -- a15/a16, s24/s23 -- and a
        one-character "correction" silently answers a different question.
        """
        assert correct_token("a16") is None
        assert correct_token("s24") is None
        assert correct_token("128gb") is None

    def test_short_tokens_are_left_alone(self):
        """At three characters almost everything is within one edit."""
        assert correct_token("lg") is None
        assert correct_token("air") is None

    def test_a_word_far_from_everything_is_left_alone(self):
        """
        An unknown word must survive rather than be dragged to the nearest
        vocabulary entry. "playstation" is not in the rules and must not
        become something that is.
        """
        assert correct_token("playstation") is None
        assert correct_token("refrigerator") is None


class TestCorrectQuery:
    def test_it_reports_what_it_changed(self):
        corrected, fixes = correct("ipone 15 blak")
        assert corrected == "iphone 15 black"
        assert fixes == {"ipone": "iphone", "blak": "black"}

    def test_a_clean_query_is_returned_unchanged(self):
        corrected, fixes = correct("iPhone 15 128GB Black")
        assert corrected == "iPhone 15 128GB Black"
        assert fixes == {}

    def test_numbers_and_capacities_survive(self):
        corrected, _ = correct("smasung galaxy s24 128gb")
        assert "s24" in corrected and "128gb" in corrected
        assert corrected.startswith("samsung")


class TestSearchAppliesItConservatively:
    """
    The service only accepts a correction that makes the query MORE
    understood. These exercise that rule through the real search entry point.
    """

    def test_a_typo_is_corrected_and_reported(self, db_session, catalogue):
        from app.services.search import search_products

        response = search_products(db_session, "ipone 15 128gb blak")

        assert response.interpretation.corrected_query == "iphone 15 128gb black"
        assert response.interpretation.corrections == {
            "ipone": "iphone",
            "blak": "black",
        }
        assert response.counts.exact == 1

    def test_a_clean_query_reports_no_correction(self, db_session, catalogue):
        from app.services.search import search_products

        response = search_products(db_session, "iPhone 15 128GB Black")

        assert response.interpretation.corrected_query is None
        assert response.interpretation.corrections == {}

    def test_a_correction_that_understands_no_more_is_refused(
        self, db_session, catalogue
    ):
        """
        The guard that stops this feature from rewriting queries it does not
        improve. "playstation" corrects to nothing, and even if a near word
        existed, the parse would gain no attribute -- so the shopper's own
        words are what get searched.
        """
        from app.services.search import search_products

        response = search_products(db_session, "playstation")
        assert response.interpretation.corrected_query is None
