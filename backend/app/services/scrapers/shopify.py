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
from typing import Iterator

from app.matching import parse
from app.services.scrapers.base import ScrapedProduct, StoreScraper
from app.services.scrapers.http import BlockedURLError, fetch
from app.services.scrapers.robots import can_fetch, rules_for

logger = logging.getLogger("app.scraper")

PAGE_SIZE = 50


class ShopifyScraper(StoreScraper):
    """Reads a Shopify storefront's public product feed."""

    def _endpoint(self, collection: str | None = None) -> str:
        base = f"https://{self.config.host}"
        if collection:
            return f"{base}/collections/{collection}/products.json"
        return f"{base}/products.json"

    def scrape(self) -> Iterator[ScrapedProduct]:
        targets = self.config.collections or (None,)
        seen: set[str] = set()
        emitted = 0

        robots = rules_for(f"https://{self.config.host}/", self.allowed_hosts)
        # A site asking for more space between requests gets it.
        minimum_delay = robots.crawl_delay

        for collection in targets:
            url = self._endpoint(collection)

            if not can_fetch(url, self.allowed_hosts):
                logger.warning(
                    "robots.txt disallows this path; skipping",
                    extra={"action": "scrape_skip", "target": url},
                )
                continue

            page = 1
            while emitted < self.config.max_products:
                self.throttle(minimum_delay)

                try:
                    result = fetch(
                        url,
                        self.allowed_hosts,
                        params={"limit": PAGE_SIZE, "page": page},
                    )
                except BlockedURLError as exc:
                    logger.error(
                        "Fetch blocked",
                        extra={"action": "scrape_blocked", "target": str(exc)},
                    )
                    break

                if result.status_code != 200:
                    logger.warning(
                        "Unexpected status from store feed",
                        extra={
                            "action": "scrape_http_error",
                            "target": f"{url} -> {result.status_code}",
                        },
                    )
                    break

                try:
                    payload = json.loads(result.text)
                except json.JSONDecodeError:
                    logger.error(
                        "Store feed was not valid JSON",
                        extra={"action": "scrape_parse_error", "target": url},
                    )
                    break

                products = payload.get("products") or []
                if not products:
                    break  # end of the catalogue

                for raw in products:
                    if self.config.known_categories_only and not self._is_relevant(raw):
                        continue
                    for item in self._to_products(raw):
                        if item.store_product_id in seen:
                            continue
                        seen.add(item.store_product_id)
                        emitted += 1
                        yield item
                        if emitted >= self.config.max_products:
                            return

                page += 1

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
        for field in ("product_type", "title"):
            value = (raw.get(field) or "").strip()
            if value and parse(value).category:
                return True
        return False

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
