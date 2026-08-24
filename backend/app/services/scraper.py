"""
Scraper service — runs via GitHub Actions cron, not as a server process.
This keeps your 256MB Fly.io VM free for API requests only.
"""

import logging
from decimal import Decimal
from typing import List, Dict
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.store import Store
from app.models.price import Price, PriceHistory
from app.services.deduplication import DeduplicationEngine

logger = logging.getLogger("app.scraper")


# Mock store data — realistic product listings from simulated stores
# In production, these would be HTTP responses from real store APIs
MOCK_STORE_DATA = {
    "dna": [
        {
            "store_product_id": "DNA-IPH15-128-BLK",
            "name": "Apple iPhone 15 128GB 5G Smartphone - Black",
            "price": 899.00,
            "availability": True,
            "delivery_cost": 0.0,
            "url": "https://www.dna.jo/iphone-15-128gb-black"
        },
        {
            "store_product_id": "DNA-IPH15-256-BLU",
            "name": "Apple iPhone 15 256GB 5G - Blue",
            "price": 999.00,
            "availability": True,
            "delivery_cost": 0.0,
            "url": "https://www.dna.jo/iphone-15-256gb-blue"
        },
        {
            "store_product_id": "DNA-S24-128-GRA",
            "name": "Samsung Galaxy S24 128GB 5G - Graphite",
            "price": 749.00,
            "availability": True,
            "delivery_cost": 2.50,
            "url": "https://www.dna.jo/galaxy-s24-128gb-graphite"
        }
    ],
    "smartbuy": [
        {
            "store_product_id": "SB-IP15-128-BLK",
            "name": "iPhone 15 128GB Black (5G)",
            "price": 875.00,
            "availability": True,
            "delivery_cost": 2.50,
            "url": "https://smartbuy-me.com/iphone-15-128gb-black"
        },
        {
            "store_product_id": "SB-IP15-256-BLU",
            "name": "iPhone 15 256GB Blue 5G",
            "price": 975.00,
            "availability": True,
            "delivery_cost": 2.50,
            "url": "https://smartbuy-me.com/iphone-15-256gb-blue"
        },
        {
            "store_product_id": "SB-S24-128-GRA",
            "name": "Samsung Galaxy S24 128GB Graphite",
            "price": 729.00,
            "availability": False,
            "delivery_cost": 3.00,
            "url": "https://smartbuy-me.com/galaxy-s24-128gb-graphite"
        }
    ],
    "carrefour": [
        {
            "store_product_id": "CF-IPHONE15-128-BLACK",
            "name": "Apple iPhone 15 128GB 5G - Midnight",
            "price": 889.00,
            "availability": True,
            "delivery_cost": 0.0,
            "url": "https://carrefourjordan.com/iphone-15-128gb-midnight"
        },
        {
            "store_product_id": "CF-S24-128-GR",
            "name": "Samsung Galaxy S24 128GB 5G Graphite",
            "price": 739.00,
            "availability": True,
            "delivery_cost": 1.50,
            "url": "https://carrefourjordan.com/galaxy-s24-128gb-graphite"
        }
    ],
    "citycenter": [
        {
            "store_product_id": "CC-IPH15-128-BLK",
            "name": "Apple iPhone 15 128GB Black",
            "price": 895.00,
            "availability": True,
            "delivery_cost": 0.0,
            "url": "https://citycenter.jo/iphone-15-128gb-black"
        },
        {
            "store_product_id": "CC-S24-128-GRA",
            "name": "Samsung Galaxy S24 128GB Graphite",
            "price": 745.00,
            "availability": True,
            "delivery_cost": 2.00,
            "url": "https://citycenter.jo/galaxy-s24-128gb-graphite"
        }
    ]
}


class ScraperService:
    """
    Simulates scraping by reading mock store data.
    In production, replace MOCK_STORE_DATA with actual HTTP requests.
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.dedup = DeduplicationEngine(db)
    
    def fetch_store_data(self, store_code: str) -> List[Dict]:
        """
        Fetch product data from a store.
        Currently returns mock data. Replace with:
            response = httpx.get(f"https://{store_domain}/api/products")
        """
        return MOCK_STORE_DATA.get(store_code, [])
    
    def process_store(self, store_code: str, store_id: int):
        """
        Process all products from a store:
        1. Fetch data
        2. Deduplicate (find or create canonical product)
        3. Update prices
        4. Record price history
        """
        products = self.fetch_store_data(store_code)
        
        for item in products:
            # Deduplication: find existing or create new
            product, alias, is_new = self.dedup.process_new_product(
                store_id=store_id,
                store_product_name=item["name"],
                store_product_id=item["store_product_id"],
                store_product_url=item["url"],
                brand=None,  # Let dedup extract from name
                category="Phones"  # Would be extracted in real scraper
            )
            
            # Update or create price record
            existing_price = (
                self.db.query(Price)
                .filter(Price.alias_id == alias.id)
                .first()
            )
            
            if existing_price:
                # Price changed? Record history
                if existing_price.price != Decimal(str(item["price"])):
                    history = PriceHistory(
                        alias_id=alias.id,
                        price=existing_price.price  # Old price
                    )
                    self.db.add(history)
                
                # Update current price
                existing_price.price = Decimal(str(item["price"]))
                existing_price.availability = item["availability"]
                existing_price.delivery_cost = Decimal(str(item["delivery_cost"]))
            else:
                # First time seeing this product at this store
                new_price = Price(
                    alias_id=alias.id,
                    price=Decimal(str(item["price"])),
                    availability=item["availability"],
                    delivery_cost=Decimal(str(item["delivery_cost"]))
                )
                self.db.add(new_price)
            
            self.db.commit()
        
        return len(products)
    
    def run_full_scrape(self):
        """
        Scrape all stores.
        This is the entry point called by GitHub Actions cron.
        """
        # Get or create stores
        stores = {
            "dna": self._get_or_create_store("DNA Jordan", "dna.jo"),
            "smartbuy": self._get_or_create_store("SmartBuy", "smartbuy-me.com"),
            "carrefour": self._get_or_create_store("Carrefour Jordan", "carrefourjordan.com"),
            "citycenter": self._get_or_create_store("City Center", "citycenter.jo"),
        }
        
        total_processed = 0
        
        for store_code, store in stores.items():
            try:
                count = self.process_store(store_code, store.id)
                total_processed += count
                logger.info(
                    "Store scraped", extra={"action": "scrape_store",
                                            "target": store.name, "success": True}
                )
            except Exception:
                # Continue with other stores -- one failure must not kill the job.
                # exc_info gives the real traceback; the previous version printed
                # a non-ASCII marker that raised UnicodeEncodeError on the Windows
                # console, hiding the very error it was trying to report.
                logger.error(
                    "Store scrape failed", exc_info=True,
                    extra={"action": "scrape_store",
                           "target": store.name, "success": False},
                )
        
        return total_processed
    
    def _get_or_create_store(self, name: str, website: str) -> Store:
        """Get existing store or create new one."""
        store = self.db.query(Store).filter(Store.name == name).first()
        if not store:
            store = Store(name=name, website=website)
            self.db.add(store)
            self.db.commit()
            self.db.refresh(store)
        return store


# Standalone script entry point for GitHub Actions
if __name__ == "__main__":
    """
    Run this file directly to execute a scrape:
        python -m app.services.scraper
    
    GitHub Actions workflow:
        - cron: "0 */6 * * *"  # Every 6 hours
        - steps:
            - checkout code
            - install dependencies
            - run: python -m app.services.scraper
    """
    from app.logging_config import setup_logging

    setup_logging()
    db = SessionLocal()
    try:
        scraper = ScraperService(db)
        total = scraper.run_full_scrape()
        logger.info(
            "Scrape complete",
            extra={"action": "scrape_complete", "target": total, "success": True},
        )
    finally:
        db.close()