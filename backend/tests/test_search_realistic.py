"""
Regression tests for bugs found by driving the real UI against real data.

Every case here returned nothing, or returned the wrong thing, while 226 unit
tests passed. They are grouped by what they cost a shopper.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.matching import detect_category, parse, score_match
from app.models.alias import ProductAlias
from app.models.price import Price
from app.models.product import Product
from app.models.store import Store
from app.services.search import search_products

# Titles copied verbatim from the SmartBuy feed.
REAL_LISTINGS = [
    ("Apple MacBook Air 15Inch M2, 8 Core Cpu & 10 Core Gpu, 256GB SSD, Silver", "Notebook"),
    ("Apple MacBook Air 13Inch M2 Chip, 8 Core Cpu & 10Core Gpu, 512GB, Silver", "Notebook"),
    ("Apple MacBook Pro 14Inch, M5 Pro chip with 15-Core CPU, 1TB SSD", "MacBook"),
    ("Apple MacBook Neo A18 Pro chip, 6Core CPU & 5Core GPU, 8GB & 256GB", "MacBook"),
    ("Honor X7e Plus 5G, 8GB & 256GB, 6.8Inch, 8100MAh, Meteor Grey", "Smart Phone"),
    ("Samsung A57 5G, 8GB &a 256GB, 6.7Inch, 5000Mah, Dark Blue", "Smart Phone"),
    ("Xiaomi 15T Pro 5G, 12GB & 1024GB, 6.8Inch, 5500Mah, Black", "Smart Phone"),
    ("Xiaomi Redmi A7 Pro 4G, 4GB & 64GB, 6.9Inch, 6000Mah, Black", "Smart Phone"),
    # Accessories the store files near the products they accessorise.
    ("Lenovo ThinkPad Laptop Backpack High-end Business Casual", "BAGS"),
    ("Agtc Brinch Laptop Bag, 15.6Inch, Grey", "BAGS"),
    ("Apple Magic Mouse Multi-Touch Surface, Black", "MacBook"),
]


@pytest.fixture
def catalogue():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()

    store = Store(name="SmartBuy")
    db.add(store)
    db.commit()

    for i, (title, product_type) in enumerate(REAL_LISTINGS):
        parsed = parse(title, hint=product_type)
        product = Product(
            canonical_name=title,
            brand=parsed.get("brand"),
            category=product_type,
            match_category=parsed.category,
            match_attributes=parsed.specified,
        )
        db.add(product)
        db.commit()

        alias = ProductAlias(
            product_id=product.id,
            store_id=store.id,
            store_product_name=title,
            store_product_id=f"SKU-{i}",
        )
        db.add(alias)
        db.commit()
        db.add(Price(alias_id=alias.id, price=500 + i, delivery_cost=0, availability=True))
        db.commit()

    try:
        yield db
    finally:
        db.close()


class TestFamilyNameSearches:
    """
    A bare family name returned NOTHING. "MacBook" found none of ten MacBooks,
    because the laptop `variant` defaulted to "base" and no MacBook is a base
    model -- every one is an Air or a Pro.
    """

    def test_macbook_finds_macbooks(self, catalogue):
        assert search_products(catalogue, "MacBook").total >= 4

    def test_macbook_air_narrows_to_airs(self, catalogue):
        names = [p.canonical_name for p in search_products(catalogue, "MacBook Air").exact]
        assert names and all("Air" in n for n in names)

    def test_honor_x7e_finds_the_plus(self, catalogue):
        """
        The catalogue stocks only "X7e Plus". Omitting one word returned
        nothing at all -- 67.1%, just under the 70% floor -- because a query
        without a variant was read as asserting the base model.
        """
        assert search_products(catalogue, "Honor X7e").total >= 1

    def test_a_stated_variant_still_discriminates(self, catalogue):
        """Relaxing the default must not stop "Pro" from meaning Pro."""
        query = parse("iPhone 11 Pro 128GB", require_evidence=False, apply_defaults=False)
        base = parse("Apple iPhone 11 128GB Black")
        assert score_match(query, base).tier != "exact"


class TestAccessoriesAreNotProducts:
    """
    A laptop bag, a backpack and a mouse were filed as `laptops` and came back
    as EXACT matches for a search of "Laptop" -- accessories presented as the
    thing they accessorise.
    """

    @pytest.mark.parametrize(
        "title",
        [
            "Lenovo ThinkPad Laptop Backpack High-end Business Casual",
            "Agtc Brinch Laptop Bag, 15.6Inch, Grey",
            "Apple Magic Mouse Multi-Touch Surface, Black",
        ],
    )
    def test_accessories_get_no_category(self, title):
        assert parse(title, hint="BAGS").category is None

    def test_a_real_laptop_still_gets_one(self):
        parsed = parse("Apple MacBook Air 15Inch M2, 8 Core Cpu, 256GB SSD", hint="Notebook")
        assert parsed.category == "laptops"

    def test_no_accessory_is_ever_an_exact_match_for_laptop(self, catalogue):
        exact = search_products(catalogue, "Laptop").exact
        assert not any(
            word in p.canonical_name.lower() for p in exact for word in ("bag", "backpack", "mouse")
        )


class TestChipDetection:
    """
    The processor list enumerated m1-m4. A MacBook Pro M5 was already in the
    catalogue with cpu=None, indistinguishable from any other MacBook Pro.
    """

    @pytest.mark.parametrize(
        "title,expected",
        [
            ("Apple MacBook Pro 14Inch, M5 Pro chip with 15-Core CPU, 1TB", "m5"),
            ("Apple MacBook Neo A18 Pro chip, 6Core CPU, 8GB & 256GB", "a18"),
            ("Apple MacBook Air 15Inch M2, 256GB SSD", "m2"),
            ("Hp Intel I7 -8550U, 16GB DDR4 & 512GB SSD", "i7"),
            ("Lenovo Ryzen 7 5700U, 8GB & 512GB SSD", "ryzen 7"),
        ],
    )
    def test_processors_are_recognised(self, title, expected):
        assert parse(title, hint="Notebook").get("cpu") == expected

    def test_an_m2_ssd_is_not_a_processor(self):
        """"M.2" normalises to "m 2" and must not be read as Apple silicon."""
        assert parse("Dell XPS 13, M.2 SSD 512GB, 16GB RAM", hint="Notebook").get("cpu") is None


class TestCategoryDetection:
    @pytest.mark.parametrize(
        "text,expected",
        [
            # Brand-only, which matched no detector at all before.
            ("Samsung A57", "phones"),
            ("Honor X7e 256GB", "phones"),
            ("Xiaomi 15T Pro", "phones"),
            # A category word must outrank a brand: counting them together
            # tied, and the phone rules won on declaration order.
            ("Samsung laptop 16GB & 512GB SSD", "laptops"),
            ("Samsung Galaxy Book laptop, 16GB", "laptops"),
            # Unchanged.
            ("iPhone 15", "phones"),
            ("MacBook Air M2", "laptops"),
            ("playstation", None),
            ("%%%%", None),
        ],
    )
    def test_detection(self, text, expected):
        assert detect_category(text) == expected


class TestModelPatterns:
    """
    The model patterns knew iPhone and Galaxy and little else, so most of the
    real catalogue had no model. Once a model became a requirement, 90 genuine
    handsets went uncategorised.
    """

    @pytest.mark.parametrize(
        "title,expected",
        [
            ("Honor X7e Plus 5G, 8GB & 256GB", "honor x7e"),
            # "galaxy a 57", not "samsung a57": the same value a listing that
            # says "Galaxy A57" gets, or the two are two models of one phone.
            # See tests/test_samsung_models.py.
            ("Samsung A57 5G, 8GB &a 256GB", "galaxy a 57"),
            ("Xiaomi 15T Pro 5G, 12GB & 1024GB", "xiaomi 15t"),
            ("Xiaomi Redmi A7 Pro 4G, 4GB & 64GB", "redmi a7"),
            ("Xiaomi Redmi 17 4G, 4GB & 128GB", "redmi 17"),
            ("Apple iPhone 15 128GB Black", "iphone 15"),
        ],
    )
    def test_models_parse(self, title, expected):
        assert parse(title, hint="Smart Phone").get("model") == expected
