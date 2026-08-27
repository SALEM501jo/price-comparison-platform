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
    StoreConfig(
        code="igeek",
        name="iGeek Megastore",
        # Apex, not www: this store serves robots.txt on the apex and 301s the
        # www form. fetch() does not follow redirects by design, so the host
        # recorded here has to be the one that answers both robots.txt and
        # products.json with a 200. Verified for each entry below.
        host="igeekjo.com",
        platform="shopify",
        delay_seconds=2.0,
        # ~5,000 products in the feed, of which roughly 100 are laptops; the
        # rest are peripherals and games the matching rules do not cover.
        # known_categories_only filters them, so this cap applies to what is
        # KEPT, and the scraper pages the whole catalogue to find them.
        #
        # RAISED FROM 150, which was the binding constraint rather than the
        # safety net it was meant to be: the run was spending its whole
        # allowance on laptops and phones and stopping before it reached this
        # store's monitors. The catalogue held two monitors in total, both
        # from AmmanCart, so a search for "27 inch 4K monitor 144hz" parsed
        # perfectly and then matched nothing -- a whole category invisible
        # because of one number. The cap still does its real job of stopping
        # a bug from walking all 5,000 rows.
        max_products=400,
    ),
    StoreConfig(
        code="ammancart",
        name="AmmanCart",
        # www, not apex -- the mirror image of iGeek above.
        host="www.ammancart.com",
        platform="shopify",
        delay_seconds=2.0,
        # Phones are the overlap with SmartBuy. The bulk of this catalogue is
        # televisions and white goods, which no category rule covers yet.
        max_products=100,
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
