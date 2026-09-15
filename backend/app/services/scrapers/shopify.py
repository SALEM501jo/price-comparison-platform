"""
Shopify storefront adapter.

WHY THE JSON ENDPOINT AND NOT HTML:
Shopify exposes /products.json on every storefront -- the same catalogue the
theme renders, as structured data. Parsing HTML instead would mean guessing at
CSS selectors that change whenever the merchant edits their theme, and
re-guessing per store. The JSON shape is Shopify's, identical across every
store on the platform, so one adapter covers all of them.

It also carries the barcode as the variant SKU, which is what makes Layer 1 of
the matching engine (exact SKU match) work on real data rather than on
generated identifiers.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Iterator

import httpx

from app.matching import parse
from app.services.scrapers.base import FeedRead, ScrapedProduct, StoreScraper
from app.services.scrapers.http import BlockedURLError, fetch
from app.services.scrapers.robots import can_fetch, rules_for

logger = logging.getLogger("app.scraper")

# 100 products a page. Every run now reads each catalogue to its end, so this
# trades requests against response size. Shopify allows up to 250, but the
# heaviest 250-product page measured on 2026-09-15 (iGeek) was 3.38 MB against
# the 5 MB cap in http.py -- two thirds of it, with merchant-written
# descriptions free to grow -- and a page over the cap is refused, which would
# make every run of that store incomplete. At that page's density (~13.5 KB a
# product) 100 products is ~1.4 MB: the heaviest page could grow more than
# threefold before it reached the cap. The price is requests: the three
# catalogues (3,158 + 5,074 + 5,431 products) are ~140 pages, about five
# minutes at two seconds apart, once every six hours.
PAGE_SIZE = 100

# A transient fault on one of ~140 pages must not fail a whole store: see
# ShopifyScraper._fetch_page. Two retries, 5 s then 10 s on top of the delay.
PAGE_RETRIES = 2
RETRY_BACKOFF_SECONDS = 5.0
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

# A feed that stopped paging -- answering every page number with the same
# products -- would otherwise be read forever: the de-duplication below keeps
# the repeats from being emitted, so max_products never trips either. 200
# pages is 20,000 products, over three times the largest catalogue measured
# (AmmanCart, 5,431), and about seven minutes of requests before giving up.
MAX_PAGES = 200


class ShopifyScraper(StoreScraper):
    """Reads a Shopify storefront's public product feed."""

    def _endpoint(self, collection: str | None = None) -> str:
        base = f"https://{self.config.host}"
        if collection:
            return f"{base}/collections/{collection}/products.json"
        return f"{base}/products.json"

    def scrape(self) -> Iterator[ScrapedProduct]:
        # INCOMPLETE UNTIL PROVEN OTHERWISE. Only the last line of this method
        # marks the read complete, and only with no problem recorded. A read
        # abandoned any other way -- an exception raised out of this
        # generator, a caller that stops iterating -- never reaches it.
        self.feed = FeedRead(reason="the read stopped before the end of the feed")
        problems: list[str] = []

        targets = self.config.collections or (None,)
        seen: set[str] = set()
        emitted = 0

        robots = rules_for(f"https://{self.config.host}/", self.allowed_hosts)
        # Reading robots.txt is a request to the store too. Without this the
        # first page went out 0.7-0.8 s after it on every store, every run --
        # the throttle only knew about product pages. When robots.txt came
        # from the cache this costs one extra delay, which is the cheap side.
        self._last_request_at = time.monotonic()
        # A site asking for more space between requests gets it.
        minimum_delay = robots.crawl_delay

        for collection in targets:
            url = self._endpoint(collection)

            # Every stop below still moves on to the next target rather than
            # returning: the prices that CAN be read are worth refreshing. What
            # the stop costs is completeness, recorded in `problems`.
            if not can_fetch(url, self.allowed_hosts):
                self._stopped(problems, "scrape_skip", f"robots.txt disallows {url}")
                continue

            page = 1
            while True:
                if page > MAX_PAGES:
                    self._stopped(
                        problems,
                        "scrape_page_limit",
                        f"{url} had not ended after {MAX_PAGES} pages",
                    )
                    break

                try:
                    result = self._fetch_page(url, page, minimum_delay)
                except BlockedURLError as exc:
                    # Includes a page larger than http.py's response cap: the
                    # rest of the feed is unread, not absent.
                    self._stopped(
                        problems, "scrape_blocked", f"{url} page {page}: blocked: {exc}"
                    )
                    break

                if result.status_code != 200:
                    self._stopped(
                        problems,
                        "scrape_http_error",
                        f"{url} page {page}: HTTP {result.status_code}",
                    )
                    break

                try:
                    payload = json.loads(result.text)
                except json.JSONDecodeError:
                    self._stopped(
                        problems, "scrape_parse_error", f"{url} page {page}: not valid JSON"
                    )
                    break

                products = payload.get("products") if isinstance(payload, dict) else None
                if not isinstance(products, list):
                    # Valid JSON of the wrong shape is not an empty page. Read
                    # as one, it would end the feed early and call that complete.
                    self._stopped(
                        problems,
                        "scrape_parse_error",
                        f"{url} page {page}: no product list in the response",
                    )
                    break

                if not products:
                    break  # the end of this target: the only clean way out

                for raw in products:
                    if self.config.known_categories_only and not self._is_relevant(raw):
                        continue
                    for item in self._to_products(raw):
                        if item.store_product_id in seen:
                            continue
                        # Checked BEFORE emitting, so a store with exactly
                        # max_products kept listings still reads to its end
                        # and counts as complete; one more trips the guard.
                        if emitted >= self.config.max_products:
                            self._stopped(
                                problems,
                                "scrape_limit",
                                f"more than max_products={self.config.max_products} "
                                f"kept listings, stopped at {url} page {page}",
                            )
                            self.feed = FeedRead(reason="; ".join(problems))
                            return
                        seen.add(item.store_product_id)
                        emitted += 1
                        yield item

                page += 1

        self.feed = FeedRead(
            complete=not problems, reason="; ".join(problems) or None
        )

    def _fetch_page(self, url: str, page: int, minimum_delay: float | None):
        """
        One page of the feed, retried a little before giving up.

        A full read is now ~140 requests. Without a retry, one 429, one 5xx or
        one timeout anywhere in them made the store's read incomplete -- which
        fails the store, holds everyone's price alerts back for the run, and,
        repeated, lets that store's offers age out of the site. A transient
        fault deserves a second ask; a real one fails on every attempt and is
        reported exactly as before. Each retry waits the store's own delay
        (throttle) plus a growing back-off, so a store asking us to slow down
        is slowed down for. A BlockedURLError is never retried: it is a safety
        check or a size cap, and asking again changes nothing.
        """
        attempt = 0
        while True:
            self.throttle(minimum_delay)
            try:
                result = fetch(
                    url,
                    self.allowed_hosts,
                    params={"limit": PAGE_SIZE, "page": page},
                )
            except httpx.TransportError as exc:
                if attempt >= PAGE_RETRIES:
                    raise
                why = f"{type(exc).__name__}"
            else:
                if result.status_code not in RETRYABLE_STATUS or attempt >= PAGE_RETRIES:
                    return result
                why = f"HTTP {result.status_code}"

            attempt += 1
            logger.warning(
                "Retrying a feed page",
                extra={
                    "action": "scrape_retry",
                    "target": f"{url} page {page}: {why}, attempt {attempt + 1}",
                },
            )
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    def _stopped(self, problems: list[str], action: str, reason: str) -> None:
        """
        Record why the read is incomplete, and say so in the log.

        Every early stop comes through here. Each used to be a `break` after a
        log line, and the run carried on as if nothing had happened: nothing
        downstream could tell a feed read to its end from one abandoned on
        page two, which was harmless only while nothing drew conclusions from
        what a read did not contain.
        """
        problems.append(reason)
        logger.error(
            "Store feed read incomplete",
            extra={
                "action": action,
                "target": f"{self.config.code}: {reason}",
                "success": False,
            },
        )

    def _is_relevant(self, raw: dict) -> bool:
        """
        Keep only what the matching engine understands.

        Uses the engine's own parser rather than a second list of keywords
        here -- one source of truth, so adding a category to
        app/matching/rules.py widens what gets scraped automatically.

        WHY parse() AND NOT detect_category(): detect_category only asks
        whether a category word appears; the full parse also enforces that
        category's `requires_any`. Gating on the weaker of the two while the
        storage side used the stronger one meant everything in between was
        ingested and then filed with no category at all -- "Lenovo ThinkPad
        Laptop Backpack" and "HP M290 Wireless Mouse" are laptops to
        detect_category and nothing to parse. Those rows are invisible to
        search, so they were pure noise in the catalogue. One gate, applied
        once.
        """
        product_type = (raw.get("product_type") or "").strip()
        title = (raw.get("title") or "").strip()
        if not title:
            return False

        # THE SAME CALL THE STORAGE SIDE MAKES, hint and all. Testing the
        # product_type as free-standing TEXT was a subtly different gate: a
        # "Covers & Cases" product_type resolved to nothing, so the title was
        # tried on its own, "Totu Ring Lenss, Iphone 15" looked like a phone,
        # and the listing was ingested -- then the storage side parsed it WITH
        # the hint, refused it, and filed it with no category at all. Two
        # gates, and everything between them became a row that search can
        # never return.
        return parse(title, hint=product_type or None).category is not None

    def _to_products(self, raw: dict) -> Iterator[ScrapedProduct]:
        """
        One ScrapedProduct per variant.

        Variants are separate products for our purposes: "128GB Black" and
        "256GB Blue" are different things at different prices, and collapsing
        them to the parent would make the price comparison meaningless.
        """
        title = (raw.get("title") or "").strip()
        if not title:
            return

        handle = raw.get("handle") or ""
        vendor = (raw.get("vendor") or "").strip() or None
        product_type = (raw.get("product_type") or "").strip() or None

        images = raw.get("images") or []
        image_url = images[0].get("src") if images else None

        for variant in raw.get("variants") or []:
            sku = (variant.get("sku") or "").strip()
            variant_id = variant.get("id")
            # Prefer the barcode/SKU; fall back to Shopify's variant id so a
            # listing without one still gets a stable key.
            identifier = sku or (f"shopify-{variant_id}" if variant_id else "")
            if not identifier:
                continue

            try:
                price = float(variant.get("price"))
            except (TypeError, ValueError):
                continue
            if price <= 0:
                continue  # "call for price" placeholders

            # A variant title of "Default Title" means the product has no real
            # options; anything else is a genuine variant worth appending.
            variant_title = (variant.get("title") or "").strip()
            name = title
            if variant_title and variant_title.lower() not in {
                "default title",
                title.lower(),
            } and not variant_title.replace("-", "").isalnum():
                name = f"{title} {variant_title}"

            yield ScrapedProduct(
                store_product_id=identifier,
                name=name,
                price=price,
                currency="JOD",
                availability=bool(variant.get("available")),
                url=f"https://{self.config.host}/products/{handle}",
                brand=vendor,
                category=product_type,
                image_url=image_url,
            )
