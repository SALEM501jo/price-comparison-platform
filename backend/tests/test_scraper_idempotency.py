"""
Regression tests for the ingest pipeline.

The bug these guard against: process_new_product() found the existing product
via SKU but still called create_alias(), inserting a duplicate alias every
run. The pipeline then saw an alias with no Price attached and inserted a
duplicate Price too. Four runs produced four aliases and four prices per
listing, so store_count inflated and PriceHistory never recorded a change.

THESE USED TO DRIVE THE MOCK SCRAPER. That service existed to seed a
catalogue before real scraping worked; it has been deleted along with the
invented prices it produced, and driving IngestService directly is strictly
better anyway -- it is the code that actually runs in production, and the
fixtures below say plainly what a "listing" is instead of hiding it in a
module-level dict that tests mutated and restored.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.alias import ProductAlias
from app.models.price import Price, PriceHistory
from app.models.product import Product
from app.models.store import Store
from app.services.ingest import IngestService
from app.services.scrapers import ScrapedProduct


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def store(db):
    row = Store(name="SmartBuy", website="smartbuy-me.com", is_verified=True)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def listing(sku, name, price, category="Smart Phone"):
    """One listing exactly as a store feed yields it."""
    return ScrapedProduct(
        store_product_id=sku,
        name=name,
        price=price,
        currency="JOD",
        availability=True,
        url=f"https://smartbuy-me.com/products/{sku}",
        brand="Apple",
        category=category,
    )


FEED = [
    listing("SB-1", "Apple iPhone 15 128GB 5G Smartphone - Black", 899.0),
    listing("SB-2", "Apple iPhone 15 256GB 5G Smartphone - Blue", 999.0),
    listing("SB-3", "Samsung Galaxy S24 128GB 5G - Graphite", 749.0),
]


def run(db, store, feed=None):
    """One full pass of the feed through the real ingest path."""
    service = IngestService(db)
    for item in feed or FEED:
        service.ingest_one(store, item)


def counts(db):
    return {
        "products": db.query(Product).count(),
        "aliases": db.query(ProductAlias).count(),
        "prices": db.query(Price).count(),
        "history": db.query(PriceHistory).count(),
    }


class TestRepeatedRuns:
    def test_a_single_run_creates_one_row_per_listing(self, db, store):
        run(db, store)
        assert counts(db)["aliases"] == len(FEED)
        assert counts(db)["prices"] == len(FEED)

    def test_repeated_runs_stay_stable(self, db, store):
        """
        The actual regression. The scraper re-processes every listing on every
        run; without the idempotency guard each pass inserted another alias
        and another price.
        """
        run(db, store)
        baseline = counts(db)

        for _ in range(3):
            run(db, store)

        assert counts(db)["aliases"] == baseline["aliases"]
        assert counts(db)["prices"] == baseline["prices"]
        assert counts(db)["products"] == baseline["products"]

    def test_one_alias_per_listing(self, db, store):
        run(db, store)
        assert db.query(ProductAlias).count() == len(FEED)


class TestPriceHistory:
    def test_no_history_before_anything_changes(self, db, store):
        run(db, store)
        assert db.query(PriceHistory).count() == 0

    def test_a_price_change_is_recorded_once(self, db, store):
        run(db, store)

        cheaper = [listing("SB-1", FEED[0].name, 849.0)] + FEED[1:]
        run(db, store, cheaper)

        history = db.query(PriceHistory).all()
        assert len(history) == 1, "exactly one history row for one price change"
        assert float(history[0].price) == 899.0, "history stores the OLD price"

    def test_an_unchanged_price_records_no_history(self, db, store):
        run(db, store)
        run(db, store)
        assert db.query(PriceHistory).count() == 0

    def test_the_current_price_is_the_new_one(self, db, store):
        run(db, store)
        run(db, store, [listing("SB-1", FEED[0].name, 849.0)])

        alias = (
            db.query(ProductAlias)
            .filter(ProductAlias.store_product_id == "SB-1")
            .one()
        )
        price = db.query(Price).filter(Price.alias_id == alias.id).one()
        assert float(price.price) == 849.0


class TestTheStoreKeepsItsOwnNaming:
    def test_a_renamed_listing_under_one_sku_does_not_duplicate(self, db, store):
        """
        A store can retitle a product without it becoming a second product:
        the SKU is the identity, which is Layer 1 of the matching engine.
        """
        run(db, store, [listing("SB-1", "Apple iPhone 15 128GB Black", 899.0)])
        run(db, store, [listing("SB-1", "iPhone 15 128GB (Black) 5G", 899.0)])

        assert db.query(ProductAlias).count() == 1


class TestWhenAPriceWasLastChecked:
    """
    The product page tells shoppers how fresh a price is. A price re-read
    unchanged every six hours used to keep the timestamp of its last CHANGE,
    so a figure checked minutes ago read "updated 19 days ago".
    """

    def _row(self, db, sku="SB-1"):
        return (
            db.query(Price)
            .join(ProductAlias, Price.alias_id == ProductAlias.id)
            .filter(ProductAlias.store_product_id == sku)
            .one()
        )

    def _age(self, db, **stamps):
        from datetime import datetime, timezone

        old = datetime(2026, 8, 27, 19, 13, tzinfo=timezone.utc)
        row = self._row(db)
        for name in stamps or ("last_updated", "checked_at"):
            setattr(row, name, old)
        db.commit()
        return old

    @staticmethod
    def _aware(moment):
        from datetime import timezone

        return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)

    def test_a_new_price_is_checked_now(self, db, store):
        run(db, store)
        assert self._row(db).checked_at is not None

    def test_an_unchanged_price_is_checked_but_not_changed(self, db, store):
        run(db, store)
        old = self._age(db)

        run(db, store)
        row = self._row(db)
        db.refresh(row)

        assert self._aware(row.checked_at) > old, "the re-read was not recorded"
        assert self._aware(row.last_updated) == old, "an unchanged price was marked changed"

    def test_a_changed_price_moves_both(self, db, store):
        run(db, store)
        old = self._age(db)

        run(db, store, [listing("SB-1", FEED[0].name, 849.0)] + FEED[1:])
        row = self._row(db)
        db.refresh(row)

        assert self._aware(row.checked_at) > old
        assert self._aware(row.last_updated) > old
