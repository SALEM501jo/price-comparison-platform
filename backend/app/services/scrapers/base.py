"""
Store scraper interface and configuration.

A StoreConfig is DATA -- adding a store means adding an entry, in the same
spirit as the category rules in app/matching/rules.py. The host allowlist that
protects the fetcher is derived from these entries, so a store cannot be
scraped without first being declared here.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator

logger = logging.getLogger("app.scraper")


@dataclass(frozen=True)
class StoreConfig:
    code: str
    name: str
    host: str
    platform: str  # which adapter handles it
    # Seconds between requests. Overridden upward by robots.txt Crawl-delay,
    # never downward -- a site asking for more space gets it.
    delay_seconds: float = 1.5
    # Cap per run so a bug cannot walk an entire catalogue.
    max_products: int = 250
    # Optional collection handles. Empty means the whole catalogue feed, which
    # is more reliable -- collection handles are merchant-chosen and differ per
    # store ("mobile-phones" returned nothing on a store whose phones live
    # under product_type "Smart Phone").
    collections: tuple[str, ...] = field(default_factory=tuple)
    # Keep only listings the matching rules can categorise. Without this a
    # general feed fills the catalogue with hair care and vacuum cleaners,
    # which the engine cannot parse and no tier can rank.
    known_categories_only: bool = True


@dataclass(frozen=True)
class ScrapedProduct:
    """One listing, normalised across platforms."""

    store_product_id: str  # SKU or barcode -- the Layer 1 matching key
    name: str
    price: float
    currency: str
    availability: bool
    url: str
    brand: str | None = None
    category: str | None = None
    image_url: str | None = None
    delivery_cost: float = 0.0


class StoreScraper(ABC):
    """
    One store's adapter.

    Implementations only translate that store's feed into ScrapedProduct. All
    fetching goes through the hardened client, and politeness is enforced here
    rather than left to each adapter to remember.
    """

    def __init__(self, config: StoreConfig, allowed_hosts: set[str]):
        self.config = config
        self.allowed_hosts = allowed_hosts
        self._last_request_at = 0.0

    def throttle(self, minimum: float | None = None) -> None:
        """Space out requests. Called before every fetch."""
        delay = max(self.config.delay_seconds, minimum or 0.0)
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request_at = time.monotonic()

    @abstractmethod
    def scrape(self) -> Iterator[ScrapedProduct]:
        """Yield listings. Implementations should stop at config.max_products."""
