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
    # A RUNAWAY GUARD, NOT A QUOTA. More kept listings than this and the
    # scraper stops, and the read counts as INCOMPLETE: nothing is delisted on
    # it and the job records the store as failed.
    #
    # It used to be a per-store cap sized close to the real counts (150, 400,
    # 100), and there it truncated: whatever relevant listings came furthest
    # down the feed -- the oldest -- were never re-read, so their prices aged
    # and a store removing them could never be noticed. Measured on
    # 2026-09-15 the kept counts are 158 (SmartBuy), 284 (iGeek) and 110
    # (AmmanCart) variants. 2,000 is seven times the largest, room for a new
    # category in app/matching/rules.py to widen what is kept; a category
    # filter broken into keeping everything still trips it on every store,
    # since each catalogue holds more than 3,000 products.
    max_products: int = 2000
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


@dataclass(frozen=True)
class FeedRead:
    """
    Whether the last scrape() read the store's WHOLE feed, and if not, why.

    WHY THIS EXISTS: a listing a store removes simply stops appearing in its
    feed, so the only evidence of a removal is a read that reached the end
    and did not contain it. A read that stopped early -- a 403, a page over
    the size cap, a feed that stopped being JSON -- is missing listings too,
    and treating that absence as removal would delist half a store because
    its server hiccuped on page four. The scraper used to stop on all of
    those with a log line and nothing more for its caller, which was harmless
    while nothing drew conclusions from what was missing. Now something
    does, so the scraper has to say.

    Incomplete by default: `complete` is True only when an adapter reached
    the end of every target and met no problem on the way.
    """

    complete: bool = False
    reason: str | None = "the feed has not been read"


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
        # Replaced by scrape() when it finishes. Read it only after iterating
        # scrape() to exhaustion; until then it says the read is incomplete.
        self.feed = FeedRead()

    def throttle(self, minimum: float | None = None) -> None:
        """Space out requests. Called before every fetch."""
        delay = max(self.config.delay_seconds, minimum or 0.0)
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request_at = time.monotonic()

    @abstractmethod
    def scrape(self) -> Iterator[ScrapedProduct]:
        """
        Yield listings, then record in self.feed whether that was all of them.

        Implementations must stop at config.max_products, and must mark the
        read complete only when every target was read to its end. Every early
        stop is logged and leaves self.feed incomplete, with the reason.
        """
