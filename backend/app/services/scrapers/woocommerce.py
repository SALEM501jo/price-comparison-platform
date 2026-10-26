"""
WooCommerce storefront adapter.

WHY A SECOND PLATFORM: since 2026-09-30 Shopify refuses the production server
(HTTP 429 on nine requests in ten, on every Shopify shop at once), and from
late October it began refusing the owner's home connection too. Every source
the site had was on Shopify. WooCommerce shops are not behind that limit, and
WooCommerce publishes its own public catalogue endpoint, the Store API, which
the shop's own pages use to show products -- so this reads exactly what any
visitor's browser is sent, as structured data.

    GET /wp-json/wc/store/v1/products?per_page=100&page=N[&category=ID]

Everything about politeness and completeness is ShopifyScraper's and is
inherited rather than re-implemented: robots.txt is checked, requests are
spaced by the store's delay (or its Crawl-delay), a failed page is retried a
little and then ends the read as INCOMPLETE, and a read is complete only when
every target reached an empty page. Only the URL, the paging parameter and
the shape of a product differ.

`collections` on the StoreConfig holds WooCommerce CATEGORY IDS here. Reading
only the device categories is three pages instead of twenty-seven for a shop
whose catalogue is mostly kitchen appliances; completeness means "every listed
category was read to its end", which is what delisting needs.
"""

from __future__ import annotations

import html
import json
import time
from typing import Iterator

import httpx

from app.services.scrapers.base import ScrapedProduct
from app.services.scrapers.http import fetch
from app.services.scrapers.shopify import (
    PAGE_RETRIES,
    RETRY_BACKOFF_SECONDS,
    RETRYABLE_STATUS,
    ShopifyScraper,
    logger,
)

PAGE_SIZE = 100  # the Store API's maximum


class WooCommerceScraper(ShopifyScraper):
    """Reads a WooCommerce shop's public Store API product feed."""

    def _endpoint(self, collection: str | None = None) -> str:
        # The category travels as a query parameter (see _fetch_page), so the
        # URL is the same for every target and robots.txt is checked once.
        return f"https://{self.config.host}/wp-json/wc/store/v1/products"

    def scrape(self):
        # ShopifyScraper.scrape iterates `collections` and calls
        # _endpoint(collection) for each; this adapter needs the category to
        # reach _fetch_page instead, so the current target is kept here.
        self._category = None
        original_endpoint = self._endpoint

        def endpoint_for(collection=None):
            self._category = collection
            return original_endpoint(collection)

        self._endpoint = endpoint_for
        try:
            yield from super().scrape()
        finally:
            self._endpoint = original_endpoint

    def _fetch_page(self, url: str, page: int, minimum_delay: float | None):
        """ShopifyScraper._fetch_page with this API's parameter names."""
        params = {"per_page": PAGE_SIZE, "page": page}
        if self._category:
            params["category"] = self._category

        attempt = 0
        while True:
            self.throttle(minimum_delay)
            try:
                result = fetch(url, self.allowed_hosts, params=params)
            except httpx.TransportError as exc:
                if attempt >= PAGE_RETRIES:
                    raise
                why = type(exc).__name__
            else:
                if result.status_code not in RETRYABLE_STATUS or attempt >= PAGE_RETRIES:
                    return self._as_feed_page(result)
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

    @staticmethod
    def _as_feed_page(result):
        """
        The Store API answers with a bare JSON list; ShopifyScraper.scrape
        expects {"products": [...]}. Wrapping it here keeps every check that
        method makes -- valid JSON, a list, an empty page as the only clean
        end -- applying unchanged. Anything that is not a list is passed
        through as it is, so it still fails those checks.
        """
        if result.status_code != 200:
            return result
        try:
            payload = json.loads(result.text)
        except json.JSONDecodeError:
            return result
        if not isinstance(payload, list):
            return result
        return type(result)(
            url=result.url,
            status_code=result.status_code,
            text=json.dumps({"products": payload}, ensure_ascii=False),
            content_type=result.content_type,
        )

    def _is_relevant(self, raw: dict) -> bool:
        return super()._is_relevant(self._as_shopify_shape(raw))

    @staticmethod
    def _as_shopify_shape(raw: dict) -> dict:
        # Names arrive HTML-escaped ("&#8211;" for the dash Leaders puts
        # between the Arabic and English names).
        return {
            "title": html.unescape(raw.get("name") or "").strip(),
            "product_type": "",
        }

    def _to_products(self, raw: dict) -> Iterator[ScrapedProduct]:
        """
        One ScrapedProduct per SIMPLE product.

        A variable product (several colours or sizes) carries a price RANGE at
        this level, with each option's own price only behind a further request
        per variation. Listing it at the range's minimum would advertise a
        price that may belong to a different option, so it is skipped -- the
        same honesty rule that keeps used prices out of a new phone's title.
        """
        if raw.get("type") != "simple":
            return
        name = html.unescape(raw.get("name") or "").strip()
        if not name:
            return

        prices = raw.get("prices") or {}
        try:
            minor = int(prices.get("currency_minor_unit", 2))
            price = int(prices.get("price")) / (10**minor)
        except (TypeError, ValueError):
            return
        if price <= 0:
            return  # "call for price"
        if (prices.get("currency_code") or "JOD") != "JOD":
            return

        identifier = (raw.get("sku") or "").strip() or (
            f"woo-{raw.get('id')}" if raw.get("id") else ""
        )
        if not identifier:
            return

        images = raw.get("images") or []
        yield ScrapedProduct(
            store_product_id=identifier,
            name=name,
            price=price,
            currency="JOD",
            availability=bool(raw.get("is_in_stock")),
            url=raw.get("permalink") or f"https://{self.config.host}/",
            brand=None,
            category=None,
            image_url=images[0].get("src") if images else None,
        )
