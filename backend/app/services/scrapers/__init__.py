"""Real store scraping, with SSRF controls and robots.txt compliance."""

from app.services.scrapers.base import ScrapedProduct, StoreConfig, StoreScraper
from app.services.scrapers.http import BlockedURLError, fetch, validate_url
from app.services.scrapers.registry import (
    ALLOWED_HOSTS,
    STORES,
    get_scraper,
    store_by_code,
)

__all__ = [
    "ScrapedProduct",
    "StoreConfig",
    "StoreScraper",
    "BlockedURLError",
    "fetch",
    "validate_url",
    "ALLOWED_HOSTS",
    "STORES",
    "get_scraper",
    "store_by_code",
]
