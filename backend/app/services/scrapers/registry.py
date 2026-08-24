"""
Which stores we scrape, and with what.

This is the SSRF host allowlist. A store that is not listed here cannot be
fetched, because ALLOWED_HOSTS is derived from these entries and every request
is checked against it.

Adding a store: append a StoreConfig and, if it runs on a platform with no
adapter yet, write one. Nothing else changes.

ON SCRAPING REAL SITES: only public catalogue endpoints are read, robots.txt
is honoured, requests are spaced out, and the client identifies itself
honestly. That is the courteous baseline, not a legal opinion -- each
retailer's terms of service govern what is actually permitted, and anyone
deploying this should read them.
"""

from __future__ import annotations

from app.services.scrapers.base import StoreConfig, StoreScraper
from app.services.scrapers.shopify import ShopifyScraper

STORES: tuple[StoreConfig, ...] = (
    StoreConfig(
        code="smartbuy",
        name="SmartBuy",
        host="smartbuy-me.com",
        platform="shopify",
        delay_seconds=2.0,
        max_products=150,
        # No collections: the whole catalogue feed, filtered to the categories
        # the matching rules understand. Collection handles are merchant-chosen
        # -- "mobile-phones" existed on this store and was empty, while its
        # phones sit under product_type "Smart Phone".
    ),
)

ADAPTERS: dict[str, type[StoreScraper]] = {
    "shopify": ShopifyScraper,
}

# The SSRF allowlist. Derived, never hand-maintained -- a hand-written second
# list is how a host ends up fetchable without anyone deciding it should be.
ALLOWED_HOSTS: set[str] = {store.host for store in STORES}


def get_scraper(config: StoreConfig) -> StoreScraper:
    adapter = ADAPTERS.get(config.platform)
    if adapter is None:
        raise ValueError(f"No adapter for platform {config.platform!r}")
    return adapter(config, ALLOWED_HOSTS)


def store_by_code(code: str) -> StoreConfig | None:
    return next((store for store in STORES if store.code == code), None)
