"""
A small, invented catalogue for CI's smoke test. Never for a real database.

WHY THIS EXISTS. The smoke test searches for the home page's example products
and checks that one of them is compared across two shops, so it needs a
catalogue. CI used to fill one with `python -m app.services.scraper`, a module
that served mock stores and was deleted with the dead pipeline. From then on
the step failed on import, before a single smoke check ran, and CI went red on
every push.

WHY NOT SCRAPE FOR REAL (`python -m app.services.ingest`). That fetches from
real Jordanian retailers on every push and every weekly run -- load on their
sites for a test that has nothing to do with them -- and the result depends on
what they stock that day. The smoke test checks OUR code; its input should be
fixed.

WHAT IS IN IT, and why each row:

  * iPhone 15 128GB Black at BOTH stores, so /products/deals has a product
    carried by two shops and the aggregation checks have something to compare.
  * MacBook Air M2 256GB and Galaxy S24 128GB, the other two home page
    examples, so "every example returns results" is tested rather than skipped.
  * Deliberately NO iPhone 15 512GB: the smoke test searches for one and
    requires the 128GB to be DEMOTED, not matched exactly. Seeding a 512GB
    would make that search exact and turn a correct engine into a failed check.

Everything goes through IngestService.ingest_one, the same path scraped
listings take, so the catalogue is shaped exactly as a real one would be.

Refuses to run when ENVIRONMENT is production: invented prices on a live price
comparison site are the one thing it must never show.

    cd backend
    python scripts/seed_ci_catalogue.py
"""

import sys

sys.path.insert(0, ".")

from app.config import get_settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models.store import Store  # noqa: E402
from app.services.ingest import IngestService  # noqa: E402
from app.services.scrapers.base import ScrapedProduct  # noqa: E402

# .invalid is reserved (RFC 2606): nothing here can ever resolve to a real shop.
STORES = {
    "CI Fixture Store A": "ci-fixture-a.invalid",
    "CI Fixture Store B": "ci-fixture-b.invalid",
}

LISTINGS = (
    ("CI Fixture Store A", "A-IP15-128-BLK", "Apple iPhone 15 128GB Black", 649.0, "apple", "Smart Phone"),
    ("CI Fixture Store B", "B-IP15-128-BLK", "iPhone 15 128GB Black", 629.0, "apple", "Smart Phone"),
    ("CI Fixture Store A", "A-MBA-M2-256", "Apple MacBook Air M2 256GB", 799.0, "apple", "Laptops"),
    ("CI Fixture Store B", "B-S24-128", "Samsung Galaxy S24 128GB", 559.0, "samsung", "Smart Phone"),
)


def main() -> int:
    if get_settings().environment == "production":
        print("REFUSING: this writes invented prices. It is for CI only.")
        return 1

    db = SessionLocal()
    try:
        ingest = IngestService(db)
        stores = {}
        for name, host in STORES.items():
            store = db.query(Store).filter(Store.name == name).first()
            if store is None:
                store = Store(name=name, website=host)
                db.add(store)
                db.commit()
                db.refresh(store)
            stores[name] = store

        for store_name, sku, title, price, brand, category in LISTINGS:
            ingest.ingest_one(
                stores[store_name],
                ScrapedProduct(
                    store_product_id=sku,
                    name=title,
                    price=price,
                    currency="JOD",
                    availability=True,
                    url=f"https://{STORES[store_name]}/products/{sku.lower()}",
                    brand=brand,
                    category=category,
                ),
            )
        print(f"Seeded {len(LISTINGS)} listings across {len(STORES)} fixture stores.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
