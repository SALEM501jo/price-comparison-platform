"""
Ingest pipeline: store listings -> canonical products -> prices.

Sits between the scrapers (which know how to read one store) and the
deduplication engine (which knows whether two listings are the same product).
Neither knows about the other, which is what lets a new store be added without
touching the matching logic, and the matching rules to change without touching
any scraper.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy.orm import Session

from app.matching import parse
from app.models.price import Price, PriceHistory
from app.models.store import Store
from app.services.deduplication import DeduplicationEngine
from app.services.scrapers import STORES, ScrapedProduct, StoreConfig, get_scraper

logger = logging.getLogger("app.scraper")


class IngestService:
    """Runs scrapers and folds their output into the catalogue."""

    def __init__(self, db: Session):
        self.db = db
        self.dedup = DeduplicationEngine(db)

    def _get_or_create_store(self, config: StoreConfig) -> Store:
        store = self.db.query(Store).filter(Store.name == config.name).first()
        if not store:
            store = Store(name=config.name, website=config.host)
            self.db.add(store)
            self.db.commit()
            self.db.refresh(store)
        return store

    def ingest_one(self, store: Store, item: ScrapedProduct) -> bool:
        """
        Fold one listing into the catalogue. Returns True if a price changed.

        The store's own category is passed to the parser as a hint: real titles
        frequently omit what the product IS ("Hp Intel I7 -8550U, 16GB DDR4 &
        512GB SSD") while the store files it under "Notebook".
        """
        parsed = parse(item.name, hint=item.category)

        product, alias, _is_new = self.dedup.process_new_product(
            store_id=store.id,
            store_product_name=item.name,
            store_product_id=item.store_product_id,
            store_product_url=item.url,
            brand=(item.brand or "").lower() or parsed.get("brand"),
            category=item.category,
        )

        existing = self.db.query(Price).filter(Price.alias_id == alias.id).first()
        changed = False

        # Convert through str, not float: Decimal(0.1) captures the binary
        # approximation, Decimal("0.1") is exact. The feed gives us decimal
        # strings, so this round-trips the value the store actually quoted.
        price = Decimal(str(item.price))
        delivery = Decimal(str(item.delivery_cost))

        if existing:
            if existing.price != price:
                # Record the OLD price before overwriting it -- that is what
                # makes the history a series rather than a single point.
                self.db.add(PriceHistory(alias_id=alias.id, price=existing.price))
                changed = True
            existing.price = price
            existing.availability = item.availability
            existing.delivery_cost = delivery
        else:
            self.db.add(
                Price(
                    alias_id=alias.id,
                    price=price,
                    currency=item.currency,
                    availability=item.availability,
                    delivery_cost=delivery,
                )
            )

        if item.image_url and not product.image_url:
            product.image_url = item.image_url

        self.db.commit()
        return changed

    def run_store(self, config: StoreConfig) -> dict:
        """Scrape one store and ingest everything it yields."""
        store = self._get_or_create_store(config)
        scraper = get_scraper(config)

        seen = 0
        changed = 0
        failed = 0

        for item in scraper.scrape():
            seen += 1
            try:
                if self.ingest_one(store, item):
                    changed += 1
            except Exception:
                # One malformed listing must not abandon the rest of the run.
                failed += 1
                self.db.rollback()
                logger.error(
                    "Failed to ingest listing",
                    exc_info=True,
                    extra={
                        "action": "ingest_item",
                        "target": item.store_product_id,
                        "success": False,
                    },
                )

        result = {"store": config.name, "seen": seen, "price_changes": changed,
                  "failed": failed}
        logger.info(
            "Store ingested",
            extra={"action": "ingest_store", "target": str(result), "success": True},
        )
        return result

    def run_all(self) -> list[dict]:
        results = []
        for config in STORES:
            try:
                results.append(self.run_store(config))
            except Exception:
                # A store that is down or has changed its feed must not stop
                # the others from being refreshed.
                logger.error(
                    "Store run failed",
                    exc_info=True,
                    extra={
                        "action": "ingest_store",
                        "target": config.name,
                        "success": False,
                    },
                )
                results.append({"store": config.name, "error": True})
        return results


if __name__ == "__main__":
    from app.database import SessionLocal
    from app.logging_config import setup_logging

    setup_logging()
    db = SessionLocal()
    try:
        for outcome in IngestService(db).run_all():
            print(outcome)
    finally:
        db.close()
