"""
Regression tests for the scrape pipeline.

The bug these guard against: process_new_product() found the existing product
via SKU but still called create_alias(), inserting a duplicate alias every run.
The scraper then saw an alias with no Price attached and inserted a duplicate
Price too. Four scrape runs produced four aliases and four prices per listing,
so store_count inflated and PriceHistory never recorded a single change.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.alias import ProductAlias
from app.models.price import Price, PriceHistory
from app.models.product import Product
from app.services.scraper import MOCK_STORE_DATA, ScraperService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def counts(db):
    return {
        "products": db.query(Product).count(),
        "aliases": db.query(ProductAlias).count(),
        "prices": db.query(Price).count(),
        "history": db.query(PriceHistory).count(),
    }


class TestScrapeIsIdempotent:
    def test_second_run_creates_no_duplicates(self, db):
        scraper = ScraperService(db)

        scraper.run_full_scrape()
        after_first = counts(db)

        scraper.run_full_scrape()
        after_second = counts(db)

        assert after_second["aliases"] == after_first["aliases"], (
            "re-scraping duplicated aliases"
        )
        assert after_second["prices"] == after_first["prices"], (
            "re-scraping duplicated prices"
        )
        assert after_second["products"] == after_first["products"], (
            "re-scraping duplicated canonical products"
        )

    def test_repeated_runs_stay_stable(self, db):
        scraper = ScraperService(db)
        scraper.run_full_scrape()
        baseline = counts(db)

        for _ in range(3):
            scraper.run_full_scrape()

        assert counts(db)["aliases"] == baseline["aliases"]
        assert counts(db)["prices"] == baseline["prices"]

    def test_one_alias_per_listing(self, db):
        ScraperService(db).run_full_scrape()
        expected = sum(len(items) for items in MOCK_STORE_DATA.values())
        assert db.query(ProductAlias).count() == expected


class TestPriceHistory:
    def test_price_change_is_recorded_once(self, db):
        scraper = ScraperService(db)
        scraper.run_full_scrape()
        assert db.query(PriceHistory).count() == 0, "no history before any change"

        # Simulate the store dropping its price on the next run.
        listing = MOCK_STORE_DATA["dna"][0]
        original = listing["price"]
        listing["price"] = original - 50
        try:
            scraper.run_full_scrape()
            history = db.query(PriceHistory).all()
            assert len(history) == 1, "exactly one history row for one price change"
            assert history[0].price == original, "history stores the OLD price"
        finally:
            listing["price"] = original

    def test_unchanged_price_records_no_history(self, db):
        scraper = ScraperService(db)
        scraper.run_full_scrape()
        scraper.run_full_scrape()
        assert db.query(PriceHistory).count() == 0
