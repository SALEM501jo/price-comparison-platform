"""
robots.txt and the sitemap: what a search engine reads before the site.

THE FAILURE THESE EXIST FOR: live, both paths answered with the app shell --
200, text/html -- so Google saw a broken robots file and no sitemap at all.

The tests that matter most are the ones that could not be seen by looking at
either file:

  - robots.txt must not blind the renderer. Google renders this SPA with
    JavaScript, so a Disallow that covers an API a public page calls leaves
    that page indexed as an empty frame. /admin and /merchant are both a page
    and an API prefix, so the list is one careless edit away from that. The
    check walks the frontend's real imports rather than trusting a comment.
  - the sitemap must not leak. A product whose only price comes from an
    unverified merchant is invisible everywhere else on the site; a sitemap
    URL for it would publish that it exists.
  - absolute URLs come from configuration. A sitemap built from the Host
    header tells a crawler the site lives wherever the requester said.
"""

import itertools
import re
import urllib.robotparser
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.database import get_db
from app.frontend import API_PREFIXES, mount_frontend
from app.models.alias import ProductAlias
from app.models.price import Price
from app.models.product import Product
from app.models.store import Store
from app.routers import seo
from app.services import photos

BASE = "https://ahsanse3r.com"
NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
HOSTILE_HOST = "evil.example"

# Owner ids for merchant stores. owner_user_id is unique, and SQLite does not
# enforce the foreign key, so no user row is needed -- only a distinct id.
_owner_ids = itertools.count(1)


# --- Setup ------------------------------------------------------------------


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    """
    The configured public address, and a catalogue version that answers now.

    catalogue_version() is patched because it tries Redis first, and against
    a Redis that is not running that attempt costs seconds per request on
    some platforms -- the fallback it lands on is the same "0" returned here.
    Patched in products.py too, which imported the function by name, for the
    test that compares the sitemap against /products/browse.
    """
    monkeypatch.setattr(seo.settings, "app_base_url", BASE)

    async def version():
        return "0"

    monkeypatch.setattr("app.services.cache.catalogue_version", version)
    monkeypatch.setattr("app.routers.products.catalogue_version", version)


def make_store(db, name, *, merchant=False, verified=True, active=1):
    store = Store(
        name=name,
        is_active=active,
        owner_user_id=next(_owner_ids) if merchant else None,
        is_verified=verified,
    )
    db.add(store)
    db.flush()
    return store


def make_product(db, name, *, category="phones"):
    product = Product(canonical_name=name, match_category=category)
    db.add(product)
    db.flush()
    return product


def offer(db, store, product, *, available=True, last_updated=None, checked_at=None):
    """
    One store's listing, priced.

    `checked_at` is when a scraper last READ the price, `last_updated` when it
    last CHANGED. A scraped price whose newer of the two is past the age limit
    is not a current offer and leaves the sitemap, so a test that dates the
    CHANGE weeks back, to pin lastmod, must also say the price was read
    recently -- which is exactly the state of a real price confirmed
    unchanged on every run.
    """
    alias = ProductAlias(
        product_id=product.id,
        store_id=store.id,
        store_product_name=product.canonical_name,
        store_product_id=f"sku-{store.id}-{product.id}",
    )
    db.add(alias)
    db.flush()
    price = Price(
        alias_id=alias.id,
        price=100,
        delivery_cost=0,
        availability=available,
        checked_at=checked_at,
    )
    if last_updated is not None:
        price.last_updated = last_updated
    db.add(price)
    db.flush()
    return price


def urls(response) -> dict[str, str | None]:
    """loc -> lastmod, from a sitemap response. Parsing is the well-formedness check."""
    root = ET.fromstring(response.content)
    return {
        url.findtext(f"{NS}loc"): url.findtext(f"{NS}lastmod")
        for url in root.findall(f"{NS}url")
    }


def robots_parser(text: str) -> urllib.robotparser.RobotFileParser:
    """
    An independent reading of the file: Python's own robots parser.

    It takes the FIRST matching rule where Google takes the LONGEST, which is
    only the same answer while the file has no Allow lines and no wildcards.
    test_the_file_stays_readable_the_same_way_by_every_parser pins exactly
    that, so this cannot quietly start disagreeing with Googlebot.
    """
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(text.splitlines())
    return parser


# --- robots.txt -------------------------------------------------------------


class TestRobots:
    def test_is_plain_text_not_the_app_shell(self, client):
        response = client.get("/robots.txt")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        assert response.text.startswith("User-agent: *\n")
        assert "<" not in response.text

    def test_answers_a_head_request(self, client):
        """Uptime monitors and some crawlers ask with HEAD first."""
        assert client.head("/robots.txt").status_code == 200

    @pytest.mark.parametrize(
        "page",
        [
            "/account",
            "/wishlist",
            "/alerts",
            "/admin",
            "/merchant",
            "/oauth/callback?code=abc&state=def",
            "/verify-email?token=abc",
            "/reset-password?token=abc",
        ],
    )
    def test_every_private_page_is_disallowed(self, client, page):
        parser = robots_parser(client.get("/robots.txt").text)
        assert not parser.can_fetch("Googlebot", page), f"{page} is crawlable"

    @pytest.mark.parametrize(
        "page",
        [
            "/",
            "/results?q=iphone+15",
            "/browse/phones",
            "/product/123",
            "/about",
            "/privacy",
            "/terms",
            "/contact",
        ],
    )
    def test_every_public_page_is_crawlable(self, client, page):
        parser = robots_parser(client.get("/robots.txt").text)
        assert parser.can_fetch("Googlebot", page), f"{page} is blocked"

    def test_the_file_stays_readable_the_same_way_by_every_parser(self, client):
        """
        No Allow lines and no wildcards. With only plain Disallow prefixes,
        first-match and longest-match parsers reach the same verdict, which is
        what lets the stdlib parser above stand in for Googlebot. An
        `Allow: /` would make first-match crawlers ignore every rule after it.
        """
        rules = [
            line for line in client.get("/robots.txt").text.splitlines()
            if line.lower().startswith(("allow", "disallow"))
        ]
        assert rules, "no rules found at all"
        assert all(line.startswith("Disallow: /") for line in rules)
        assert not any("*" in line or "$" in line for line in rules)

    def test_names_the_sitemap_by_the_configured_address(self, client):
        parser = robots_parser(client.get("/robots.txt").text)
        assert parser.site_maps() == [f"{BASE}/sitemap.xml"]

    def test_a_hostile_host_header_does_not_reach_the_file(self, client):
        response = client.get("/robots.txt", headers={"Host": HOSTILE_HOST})
        assert HOSTILE_HOST not in response.text
        assert f"Sitemap: {BASE}/sitemap.xml" in response.text

    def test_a_tripped_rate_limiter_cannot_take_it_down(self, client, monkeypatch):
        """
        Google reads a 429 on robots.txt as the whole site being disallowed.
        The sitemap IS limited, like every catalogue endpoint -- asserted here
        too, so this proves the limiter really was tripped.
        """
        async def tripped(*args, **kwargs):
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

        monkeypatch.setattr("app.security.rate_limiter._enforce", tripped)

        assert client.get("/robots.txt").status_code == 200
        assert client.get("/sitemap.xml").status_code == 429


# --- robots.txt against the frontend's real API calls -----------------------

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
SRC = FRONTEND / "src"

# The pages anyone can open without an account -- the ones a crawler renders.
# NotFound too: it is what every unknown URL a crawler follows turns into.
PUBLIC_PAGES = (
    "Home",
    "Results",
    "Browse",
    "ProductDetail",
    "Privacy",
    "Terms",
    "Contact",
    "NotFound",
)

# `import x from './y'`, `import { a,\n b } from '../y'`, `import './y'`,
# `export { a } from './y'`, and `import('./y')`. Only relative specifiers:
# packages from node_modules make no requests to this API. The clauses cannot
# contain a quote, so a match cannot run on into the code after an import.
MODULE_REF = re.compile(
    r"""\bimport\s+(?:[\w$*\s{},]+?\s+from\s+)?['"](\.{1,2}/[^'"]+)['"]"""
    r"""|\bexport\s+(?:\*|\{[^}]*\})\s+from\s+['"](\.{1,2}/[^'"]+)['"]"""
    r"""|\bimport\(\s*['"](\.{1,2}/[^'"]+)['"]"""
)


def _resolve(importer: Path, spec: str) -> Path | None:
    """The module a relative import names, the way Vite resolves it -- or None for CSS and assets."""
    base = importer.parent / spec
    for candidate in (
        base,
        base.with_name(base.name + ".jsx"),
        base.with_name(base.name + ".js"),
        base / "index.jsx",
        base / "index.js",
    ):
        if candidate.is_file():
            return candidate.resolve() if candidate.suffix in (".js", ".jsx") else None
    return None


def _reachable(roots: list[Path]) -> set[Path]:
    seen: set[Path] = set()
    queue = [root.resolve() for root in roots]
    while queue:
        module = queue.pop()
        if module in seen:
            continue
        seen.add(module)
        for match in MODULE_REF.finditer(module.read_text(encoding="utf-8")):
            spec = next(group for group in match.groups() if group)
            target = _resolve(module, spec)
            if target is not None:
                queue.append(target)
    return seen


def public_modules() -> set[Path]:
    """
    Every module a public page can execute: the page, everything it imports,
    and the chrome App.jsx wraps around every page -- the navbar, the auth
    provider that restores a session on load. Taken from App.jsx's own imports
    minus the pages, so chrome added later is covered without editing this.
    """
    assert SRC.is_dir(), (
        f"{SRC} is missing. This test reads the frontend source to prove "
        "robots.txt does not block a public page's API calls; run it from a "
        "full checkout of the repository."
    )
    app = SRC / "App.jsx"
    pages = (SRC / "pages").resolve()
    chrome = [
        target
        for match in MODULE_REF.finditer(app.read_text(encoding="utf-8"))
        if (target := _resolve(app, next(g for g in match.groups() if g)))
        and pages not in target.parents
    ]
    roots = [SRC / "pages" / f"{name}.jsx" for name in PUBLIC_PAGES]
    for root in roots:
        assert root.is_file(), f"public page {root.name} has moved; update PUBLIC_PAGES"
    return _reachable(roots + chrome)


def api_paths_in(modules: set[Path]) -> set[str]:
    """
    Every root-relative path under an API prefix that these modules spell out.

    DELIBERATELY NOT LIMITED TO RECOGNISED CALL SYNTAX (api.get, axios.post):
    a quoted API path anywhere in reachable code counts, so a new way of
    making a request cannot slip past a regex that only knew the old ones.
    Over-counting can only make this test stricter. Template placeholders
    become "1", which is what a product id looks like.
    """
    prefixes = "|".join(re.escape(p.lstrip("/")) for p in API_PREFIXES)
    literal = re.compile(
        r"""[`'"](?:\$\{API_BASE_URL\})?(/(?:""" + prefixes + r""")/[^`'"\s]*)"""
    )
    found = set()
    for module in modules:
        for match in literal.finditer(module.read_text(encoding="utf-8")):
            found.add(re.sub(r"\$\{[^}]*\}", "1", match.group(1)))
    return found


class TestRobotsDoNotBlindTheRenderer:
    """
    THE REAL RISK IN THIS FILE. Googlebot renders the SPA, and it obeys
    robots.txt for every request the page makes while it renders -- so a rule
    that covers an API call a public page depends on gets that page indexed
    as an empty frame, with nothing in Search Console saying why.
    """

    def test_the_walk_finds_the_calls_it_is_meant_to_check(self):
        """
        Guards the guard. If the import walk or the path pattern broke, the
        check below would pass over an empty set and prove nothing.
        """
        found = api_paths_in(public_modules())
        expected = {
            "/auth/refresh",       # every page, on load (AuthContext)
            "/auth/me",
            "/products/browse",    # home and category pages
            "/products/deals",
            "/products/search",    # results
            "/products/suggest",   # the search box's suggestions
            "/products/1",         # product page
            "/products/1/history",
            "/support/contact",    # contact form
        }
        assert expected <= found, f"walk missed: {sorted(expected - found)}"

    def test_the_walk_does_not_wander_into_private_pages(self):
        """
        And the other direction: if App.jsx's page imports leaked into the
        roots, the merchant and admin APIs would count as public, the check
        would fail for the wrong reason, and the obvious "fix" would be to
        take /admin out of robots.txt.
        """
        names = {module.name for module in public_modules()}
        assert "Merchant.jsx" not in names
        assert "Admin.jsx" not in names
        assert "merchant.js" not in names
        assert "admin.js" not in names

    def test_no_api_call_a_public_page_makes_is_disallowed(self, client):
        parser = robots_parser(client.get("/robots.txt").text)
        paths = api_paths_in(public_modules())
        # Not in the source as a literal: the API hands this path back in a
        # product's image_url, and the page loads it as an <img>.
        paths.add(photos.photo_path(1))

        blocked = sorted(p for p in paths if not parser.can_fetch("Googlebot", p))
        assert not blocked, f"robots.txt blocks API calls a public page makes: {blocked}"

    def test_no_file_the_shell_loads_is_disallowed(self, client):
        """
        The page cannot render without its script, styles and fonts. Read
        from index.html and index.css themselves, plus the two directories the
        build writes to.
        """
        parser = robots_parser(client.get("/robots.txt").text)
        sources = (FRONTEND / "index.html").read_text(encoding="utf-8") + (
            SRC / "index.css"
        ).read_text(encoding="utf-8")
        referenced = set(
            re.findall(r"""(?:href|src)=["'](/[^"']*)["']|url\(['"]?(/[^'")]+)""", sources)
        )
        paths = {a or b for a, b in referenced} | {"/assets/index-ABC123.js", "/fonts/x.woff2"}
        assert "/fonts/cairo-arabic.woff2" in paths, "reference scan found nothing"

        blocked = sorted(p for p in paths if not parser.can_fetch("Googlebot", p))
        assert not blocked, f"robots.txt blocks files the app shell loads: {blocked}"


# --- sitemap.xml ------------------------------------------------------------


@pytest.fixture
def shop(db_session):
    store = make_store(db_session, "SmartBuy")
    db_session.commit()
    return store


class TestSitemapDocument:
    def test_is_well_formed_xml_in_the_sitemaps_namespace(self, client, db_session, shop):
        offer(db_session, shop, make_product(db_session, "Galaxy S24"))
        db_session.commit()

        response = client.get("/sitemap.xml")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/xml")

        root = ET.fromstring(response.content)
        assert root.tag == f"{NS}urlset"
        assert root.findall(f"{NS}url"), "no <url> entries"
        for url in root:
            assert url.tag == f"{NS}url"
            assert url.findtext(f"{NS}loc")

    def test_answers_a_head_request(self, client):
        assert client.head("/sitemap.xml").status_code == 200

    def test_lists_the_fixed_pages_without_inventing_dates(self, client):
        found = urls(client.get("/sitemap.xml"))
        for page in ("/", "/about", "/privacy", "/terms", "/contact"):
            assert f"{BASE}{page}" in found
            assert found[f"{BASE}{page}"] is None, f"{page} has an invented lastmod"

    def test_uses_the_configured_address_not_the_host_header(self, client, db_session, shop):
        offer(db_session, shop, make_product(db_session, "Galaxy S24"))
        db_session.commit()

        response = client.get("/sitemap.xml", headers={"Host": HOSTILE_HOST})
        assert HOSTILE_HOST not in response.text
        # TestClient's default host, for the request that sends no header.
        assert "testserver" not in client.get("/sitemap.xml").text
        assert all(loc.startswith(f"{BASE}/") for loc in urls(response))

    def test_every_value_is_escaped(self, client, monkeypatch):
        """
        An ampersand in the configured address is unlikely; a sitemap that
        stops parsing the day one appears is not something to find out live.
        """
        monkeypatch.setattr(seo.settings, "app_base_url", "https://example.test/a&b's")
        response = client.get("/sitemap.xml")
        assert "&amp;" in response.text and "&apos;" in response.text
        assert "https://example.test/a&b's/privacy" in urls(response)

    def test_every_listed_url_is_crawlable(self, client, db_session, shop):
        """A sitemap URL that robots.txt blocks is an error in Search Console."""
        offer(db_session, shop, make_product(db_session, "Galaxy S24"))
        db_session.commit()

        parser = robots_parser(client.get("/robots.txt").text)
        for loc in urls(client.get("/sitemap.xml")):
            assert parser.can_fetch("Googlebot", loc), f"{loc} is disallowed"


class TestSitemapProducts:
    def test_includes_a_product_a_shopper_can_buy(self, client, db_session, shop):
        product = make_product(db_session, "Galaxy S24")
        offer(db_session, shop, product)
        db_session.commit()

        assert f"{BASE}/product/{product.id}" in urls(client.get("/sitemap.xml"))

    def test_includes_a_verified_merchants_product(self, client, db_session):
        """Merchant stock is not second-class once an admin has confirmed the shop."""
        verified = make_store(db_session, "Abu Ahmad Phones", merchant=True, verified=True)
        product = make_product(db_session, "Redmi Note 13")
        offer(db_session, verified, product)
        db_session.commit()

        assert f"{BASE}/product/{product.id}" in urls(client.get("/sitemap.xml"))

    def test_excludes_a_product_only_an_unverified_merchant_prices(self, client, db_session, shop):
        """
        THE LEAK. Anyone can register a store under any name; until an admin
        confirms it, its listings reach no shopper. A sitemap URL would still
        announce the product to every crawler.
        """
        visible = make_product(db_session, "Galaxy S24")
        offer(db_session, shop, visible)
        pending = make_store(db_session, "Totally SmartBuy", merchant=True, verified=False)
        hidden = make_product(db_session, "Phone Only A Pending Shop Sells")
        offer(db_session, pending, hidden)
        db_session.commit()

        found = urls(client.get("/sitemap.xml"))
        assert f"{BASE}/product/{visible.id}" in found
        assert f"{BASE}/product/{hidden.id}" not in found

    def test_excludes_a_product_whose_only_price_is_out_of_stock(self, client, db_session, shop):
        sold_out = make_product(db_session, "Discontinued Phone")
        offer(db_session, shop, sold_out, available=False)
        db_session.commit()

        assert f"{BASE}/product/{sold_out.id}" not in urls(client.get("/sitemap.xml"))

    def test_excludes_a_store_that_has_been_switched_off(self, client, db_session):
        closed = make_store(db_session, "Closed Shop", active=0)
        product = make_product(db_session, "Phone From A Closed Shop")
        offer(db_session, closed, product)
        db_session.commit()

        assert f"{BASE}/product/{product.id}" not in urls(client.get("/sitemap.xml"))

    def test_in_stock_and_visible_must_be_the_same_offer(self, client, db_session, shop):
        """
        A verified store listing it OUT of stock plus an unverified store
        listing it IN stock is not a buyable product -- the only buyable offer
        is the hidden one. Checking "has an in-stock price" and "has a visible
        store" as two separate facts would list it.
        """
        product = make_product(db_session, "Split Signals Phone")
        offer(db_session, shop, product, available=False)
        pending = make_store(db_session, "Pending Shop", merchant=True, verified=False)
        offer(db_session, pending, product, available=True)
        db_session.commit()

        assert f"{BASE}/product/{product.id}" not in urls(client.get("/sitemap.xml"))

    def test_lastmod_is_the_offers_own_timestamp(self, client, db_session, shop):
        """
        A real date from the price row, never one made up -- and a hidden
        store's edit cannot move it, or the sitemap would say when an
        unverified shop last touched its prices.
        """
        product = make_product(db_session, "Galaxy S24")
        # Read a moment ago, changed on the 1st: lastmod is the change.
        offer(db_session, shop, product,
              last_updated=datetime(2026, 9, 1, 12, 30, tzinfo=timezone.utc),
              checked_at=datetime.now(timezone.utc))
        pending = make_store(db_session, "Pending Shop", merchant=True, verified=False)
        offer(db_session, pending, product,
              last_updated=datetime(2026, 9, 13, 8, 0, tzinfo=timezone.utc))
        db_session.commit()

        found = urls(client.get("/sitemap.xml"))
        assert found[f"{BASE}/product/{product.id}"] == "2026-09-01T12:30:00+00:00"

    def test_the_list_is_capped(self, client, db_session, shop, monkeypatch, caplog):
        """
        50,000 is the protocol's limit per file, past which a crawler may
        discard the whole thing. Tested with a small cap: the cut must keep
        the fixed pages, fill exactly to the limit, and say so in the log.
        """
        products = [make_product(db_session, f"Phone {i}") for i in range(5)]
        for product in products:
            offer(db_session, shop, product)
        db_session.commit()

        # The fixed pages + the phones category + room for two products.
        # Counted from STATIC_PAGES rather than written as a number, so adding
        # a fixed page does not silently change what this test measures.
        cap = len(seo.STATIC_PAGES) + 1 + 2
        monkeypatch.setattr(seo, "MAX_URLS", cap)
        with caplog.at_level("WARNING", logger="app.routers.seo"):
            found = urls(client.get("/sitemap.xml"))

        assert len(found) == cap
        assert f"{BASE}/privacy" in found
        assert f"{BASE}/product/{products[0].id}" in found
        assert f"{BASE}/product/{products[1].id}" in found
        assert f"{BASE}/product/{products[2].id}" not in found
        assert any(getattr(r, "action", None) == "sitemap_truncated" for r in caplog.records)


class TestSitemapCategories:
    def test_lists_exactly_the_categories_browse_lists(self, client, db_session, shop):
        """
        The sitemap and the home page's category tiles must agree, or a
        crawler is sent to a category the site itself shows as empty.
        """
        offer(db_session, shop, make_product(db_session, "Galaxy S24", category="phones"))
        offer(db_session, shop, make_product(db_session, "Dell U2723", category="monitors"))
        db_session.commit()

        tiles = {row["category"] for row in client.get("/products/browse").json()["categories"]}
        listed = {
            loc.rpartition("/browse/")[2]
            for loc in urls(client.get("/sitemap.xml"))
            if "/browse/" in loc
        }
        assert tiles == {"phones", "monitors"}
        assert listed == tiles

    def test_a_category_with_only_hidden_stock_is_not_listed(self, client, db_session, shop):
        offer(db_session, shop, make_product(db_session, "Galaxy S24", category="phones"))
        pending = make_store(db_session, "Pending Laptops", merchant=True, verified=False)
        offer(db_session, pending, make_product(db_session, "ThinkPad X1", category="laptops"))
        db_session.commit()

        found = urls(client.get("/sitemap.xml"))
        assert f"{BASE}/browse/phones" in found
        assert f"{BASE}/browse/laptops" not in found

    def test_category_lastmod_ignores_hidden_stores(self, client, db_session, shop):
        offer(db_session, shop, make_product(db_session, "Galaxy S24"),
              last_updated=datetime(2026, 9, 2, 9, 0, tzinfo=timezone.utc),
              checked_at=datetime.now(timezone.utc))
        pending = make_store(db_session, "Pending Shop", merchant=True, verified=False)
        offer(db_session, pending, make_product(db_session, "Pending Phone"),
              last_updated=datetime(2026, 9, 14, 9, 0, tzinfo=timezone.utc))
        db_session.commit()

        found = urls(client.get("/sitemap.xml"))
        assert found[f"{BASE}/browse/phones"] == "2026-09-02T09:00:00+00:00"


class TestSitemapCache:
    """
    The sitemap is public, unparameterised and scans the catalogue, so it is
    cached on the catalogue version the way /products/browse is. Tested with
    an in-memory stand-in: the wiring is what can break, not Redis.
    """

    @pytest.fixture
    def fake_cache(self, monkeypatch):
        state = {"version": "1", "store": {}, "builds": 0}

        async def version():
            return state["version"]

        async def cached_json(key):
            return state["store"].get(key)

        async def store_json(key, value, ttl=300):
            state["store"][key] = value

        real_build = seo.build_sitemap

        def counting_build(db, base):
            state["builds"] += 1
            return real_build(db, base)

        monkeypatch.setattr("app.services.cache.catalogue_version", version)
        monkeypatch.setattr("app.services.cache.cached_json", cached_json)
        monkeypatch.setattr("app.services.cache.store_json", store_json)
        monkeypatch.setattr(seo, "build_sitemap", counting_build)
        return state

    def test_a_repeat_request_does_not_rebuild(self, client, fake_cache):
        first = client.get("/sitemap.xml").text
        second = client.get("/sitemap.xml").text
        assert fake_cache["builds"] == 1
        assert first == second

    def test_a_catalogue_change_rebuilds(self, client, db_session, shop, fake_cache):
        """A store losing its verification bumps the version; its products must go at once."""
        client.get("/sitemap.xml")
        product = make_product(db_session, "Galaxy S24")
        offer(db_session, shop, product)
        db_session.commit()
        fake_cache["version"] = "2"

        assert f"{BASE}/product/{product.id}" in urls(client.get("/sitemap.xml"))
        assert fake_cache["builds"] == 2

    def test_a_different_base_url_is_a_different_entry(self, client, fake_cache, monkeypatch):
        client.get("/sitemap.xml")
        monkeypatch.setattr(seo.settings, "app_base_url", "https://staging.example")

        body = client.get("/sitemap.xml").text
        assert BASE not in body
        assert "https://staging.example/" in body
        assert fake_cache["builds"] == 2


# --- Independent of the frontend build --------------------------------------


class TestWithOrWithoutABuild:
    """
    Both routes are ordinary routers, so they must answer the same whether
    frontend/dist exists (production) or not (CI, a fresh checkout). The build
    here also carries its OWN stale robots.txt, the way one would arrive if
    somebody dropped a file into frontend/public: the router must still win.
    """

    @pytest.fixture(params=["built", "no build"])
    def site(self, request, tmp_path, monkeypatch, db_session):
        dist = tmp_path / "dist"
        if request.param == "built":
            (dist / "assets").mkdir(parents=True)
            (dist / "index.html").write_text("<!doctype html><div id=root></div>")
            (dist / "robots.txt").write_text("User-agent: *\nDisallow: /\n")
            (dist / "sitemap.xml").write_text("<stale/>")
        monkeypatch.setattr("app.frontend.DIST", dist.resolve())

        async def no_limit(*args, **kwargs):
            return None

        monkeypatch.setattr("app.security.rate_limiter._enforce", no_limit)

        app = FastAPI()
        app.include_router(seo.router)
        assert mount_frontend(app) is (request.param == "built")
        app.dependency_overrides[get_db] = lambda: db_session
        return TestClient(app)

    def test_robots_is_the_routers(self, site):
        response = site.get("/robots.txt")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        assert "Disallow: /\n" not in response.text
        assert f"Sitemap: {BASE}/sitemap.xml" in response.text

    def test_sitemap_is_the_routers(self, site):
        response = site.get("/sitemap.xml")
        assert response.status_code == 200
        assert f"{BASE}/privacy" in urls(response)
