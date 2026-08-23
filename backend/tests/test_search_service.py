"""
Tests for tiered search against a seeded catalogue.

These cover the feature the platform exists for: a fully specified query
returns the exact product first, then close variants, then similar ones.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.alias import ProductAlias
from app.models.price import Price
from app.models.product import Product
from app.models.store import Store
from app.services.search import escape_like, search_products


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def add_product(db, name, prices, category="phones"):
    """Create a product with one alias+price per (store, price, available)."""
    from app.matching import parse

    parsed = parse(name)
    product = Product(
        canonical_name=name,
        brand=parsed.get("brand"),
        match_category=parsed.category,
        match_attributes=parsed.specified,
    )
    db.add(product)
    db.commit()
    db.refresh(product)

    for i, (store_name, price, available) in enumerate(prices):
        store = db.query(Store).filter_by(name=store_name).first()
        if not store:
            store = Store(name=store_name)
            db.add(store)
            db.commit()
            db.refresh(store)

        alias = ProductAlias(
            product_id=product.id,
            store_id=store.id,
            store_product_name=f"{name} @{store_name}",
            store_product_id=f"{product.id}-{i}",
        )
        db.add(alias)
        db.commit()
        db.refresh(alias)
        db.add(Price(alias_id=alias.id, price=price,
                     delivery_cost=0.0, availability=available))
        db.commit()

    return product


@pytest.fixture
def catalogue(db):
    add_product(db, "Apple iPhone 11 Pro 128GB Black",
                [("DNA", 899.0, True), ("SmartBuy", 875.0, True)])
    add_product(db, "Apple iPhone 11 Pro 128GB Midnight Green",
                [("DNA", 909.0, True)])
    add_product(db, "Apple iPhone 11 Pro 256GB Black", [("DNA", 999.0, True)])
    add_product(db, "Apple iPhone 11 Pro Max 128GB Black", [("DNA", 1099.0, True)])
    add_product(db, "Apple iPhone 12 Pro 128GB Black", [("DNA", 1199.0, True)])
    add_product(db, "Samsung Galaxy S24 128GB Black", [("DNA", 749.0, True)])
    return db


QUERY = "iPhone 11 Pro Black 128GB"


class TestTiers:
    def test_exact_match_is_returned_in_the_exact_bucket(self, catalogue):
        result = search_products(catalogue, QUERY)
        assert [p.canonical_name for p in result.exact] == [
            "Apple iPhone 11 Pro 128GB Black"
        ]

    def test_colour_variant_lands_in_close(self, catalogue):
        result = search_products(catalogue, QUERY)
        assert [p.canonical_name for p in result.close] == [
            "Apple iPhone 11 Pro 128GB Midnight Green"
        ]

    def test_storage_and_model_variants_land_in_similar(self, catalogue):
        result = search_products(catalogue, QUERY)
        names = {p.canonical_name for p in result.similar}
        assert "Apple iPhone 11 Pro 256GB Black" in names
        assert "Apple iPhone 11 Pro Max 128GB Black" in names

    def test_different_generation_is_excluded(self, catalogue):
        result = search_products(catalogue, QUERY)
        everything = result.exact + result.close + result.similar
        assert not any("iPhone 12" in p.canonical_name for p in everything)

    def test_different_brand_is_excluded(self, catalogue):
        result = search_products(catalogue, QUERY)
        everything = result.exact + result.close + result.similar
        assert not any("Samsung" in p.canonical_name for p in everything)


class TestExplanations:
    def test_exact_match_has_no_differences(self, catalogue):
        result = search_products(catalogue, QUERY)
        assert result.exact[0].differences == []

    def test_close_match_explains_itself(self, catalogue):
        result = search_products(catalogue, QUERY)
        assert result.close[0].differences == [
            "different colour (midnight green, not black)"
        ]

    def test_interpretation_reports_what_was_understood(self, catalogue):
        result = search_products(catalogue, QUERY)
        assert result.interpretation.structured is True
        assert result.interpretation.attributes["storage"] == "128gb"
        assert result.interpretation.attributes["variant"] == "pro"


class TestPriceAggregation:
    def test_lowest_price_is_the_cheapest_in_stock(self, catalogue):
        result = search_products(catalogue, QUERY)
        assert result.exact[0].lowest_price == 875.0

    def test_store_count_counts_stores_with_stock(self, catalogue):
        result = search_products(catalogue, QUERY)
        assert result.exact[0].store_count == 2

    def test_best_deal_store_is_the_cheapest_total(self, catalogue):
        result = search_products(catalogue, QUERY)
        assert result.exact[0].best_deal_store == "SmartBuy"

    def test_out_of_stock_listings_are_excluded_entirely(self, db):
        """A product buyable at one store must not report two."""
        add_product(db, "Apple iPhone 15 128GB Black",
                    [("DNA", 899.0, True), ("SmartBuy", 100.0, False)])
        result = search_products(db, "iPhone 15 128GB Black")
        product = result.exact[0]
        assert product.store_count == 1
        assert product.lowest_price == 899.0, "out-of-stock price leaked into the range"


class TestVagueAndUnmatchedQueries:
    def test_vague_query_returns_the_whole_family(self, catalogue):
        result = search_products(catalogue, "iPhone 11 Pro")
        assert result.total >= 3

    def test_unknown_product_returns_nothing(self, catalogue):
        assert search_products(catalogue, "Nokia 3310").total == 0

    def test_unstructured_query_falls_back_to_name_search(self, db):
        add_product(db, "Sony PlayStation 5 Standard Edition", [("DNA", 499.0, True)])
        result = search_products(db, "playstation")
        assert result.total == 1
        assert result.interpretation.structured is False


class TestLikeEscaping:
    @pytest.mark.parametrize(
        "raw,expected",
        [("100%", "100\\%"), ("a_b", "a\\_b"), ("c\\d", "c\\\\d"), ("plain", "plain")],
    )
    def test_wildcards_are_escaped(self, raw, expected):
        assert escape_like(raw) == expected

    def test_wildcard_query_does_not_match_everything(self, catalogue):
        """An unescaped '%' would ILIKE-match the entire table."""
        assert search_products(catalogue, "%%%%").total == 0
