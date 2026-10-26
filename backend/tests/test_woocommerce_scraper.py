"""
The WooCommerce adapter: the first source not behind Shopify's limit.

Fed canned Store API responses through a fake fetch(), so these tests make no
network calls. What they pin is what would silently go wrong: prices in minor
units, a read that ends early still counted as incomplete, and products with
several options not listed at a price that may belong to another option.
"""

import json

import pytest

from app.services.scrapers import http, robots, woocommerce
from app.services.scrapers.base import StoreConfig, StoreScraper
from app.services.scrapers.woocommerce import WooCommerceScraper

CONFIG = StoreConfig(
    code="leaders",
    name="Leaders Center",
    host="leaders.jo",
    platform="woocommerce",
    collections=("7958",),
)


def product(name, price="34900", *, kind="simple", sku="SKU1", stock=True, pid=1):
    return {
        "id": pid,
        "name": name,
        "type": kind,
        "sku": sku,
        "is_in_stock": stock,
        "permalink": f"https://leaders.jo/product/{pid}/",
        "images": [{"src": "https://leaders.jo/img.jpg"}],
        "prices": {"price": price, "currency_code": "JOD", "currency_minor_unit": 2},
    }


@pytest.fixture
def feed(monkeypatch):
    """pages: {page_number: response}; anything else answers 404."""
    pages = {}
    calls = []

    def fake_fetch(url, allowed_hosts, *, params=None, **kwargs):
        if url.endswith("/robots.txt"):
            return http.FetchResult(url=url, status_code=200, text="User-agent: *\nDisallow: /cart/\n", content_type="text/plain")
        calls.append(params)
        status, body = pages.get(params["page"], (404, ""))
        text = body if isinstance(body, str) else json.dumps(body)
        return http.FetchResult(url=url, status_code=status, text=text, content_type="application/json")

    monkeypatch.setattr(woocommerce, "fetch", fake_fetch)
    monkeypatch.setattr(robots, "fetch", fake_fetch)
    monkeypatch.setattr(StoreScraper, "throttle", lambda self, minimum=None: None)
    monkeypatch.setattr(woocommerce.time, "sleep", lambda s: None)
    return pages, calls


def read(pages):
    scraper = WooCommerceScraper(CONFIG, {"leaders.jo"})
    return list(scraper.scrape()), scraper.feed


def test_a_full_read_is_complete_and_prices_are_in_dinars(feed):
    pages, calls = feed
    pages[1] = (200, [product("Samsung Galaxy S26 Ultra 256GB", price="99900")])
    pages[2] = (200, [])

    items, result = read(pages)

    assert result.complete is True
    assert [i.price for i in items] == [999.0]
    assert items[0].currency == "JOD"
    # The category is sent, and the page size is the API's maximum.
    assert calls[0] == {"per_page": 100, "page": 1, "category": "7958"}


def test_a_refused_page_leaves_the_read_incomplete(feed):
    pages, _ = feed
    pages[1] = (200, [product("Samsung Galaxy S26 Ultra 256GB")])
    pages[2] = (429, "Too many requests")

    _, result = read(pages)

    assert result.complete is False
    assert "HTTP 429" in result.reason


def test_a_product_with_options_is_not_listed_at_a_guessed_price(feed):
    pages, _ = feed
    pages[1] = (200, [
        product("iPhone 17 Pro 256GB", kind="variable", sku="VAR"),
        product("iPhone 17 Pro 512GB", sku="SIMPLE", pid=2),
    ])
    pages[2] = (200, [])

    items, _ = read(pages)
    assert [i.store_product_id for i in items] == ["SIMPLE"]


def test_names_are_unescaped_and_irrelevant_products_dropped(feed):
    pages, _ = feed
    pages[1] = (200, [
        product("آبل آيفون 18 برو &#8211; iPhone 18 Pro 256GB", sku="PHONE"),
        product("محمصة خبز كهربائية", sku="TOASTER", pid=2),
    ])
    pages[2] = (200, [])

    items, _ = read(pages)
    assert [i.store_product_id for i in items] == ["PHONE"]
    assert "–" in items[0].name and "&#8211;" not in items[0].name


def test_a_response_that_is_not_a_list_is_not_read_as_the_end(feed):
    pages, _ = feed
    pages[1] = (200, {"code": "rest_error"})

    _, result = read(pages)
    assert result.complete is False
