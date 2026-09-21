"""
What a search engine reads before it reads the site: robots.txt and the sitemap.

WHAT MADE THIS NECESSARY. Live, /robots.txt and /sitemap.xml both answered
with the SPA's index.html -- 200, text/html -- because nothing owned either
path and the catch-all in app/frontend.py hands the app shell to anything it
does not recognise. Google reads that as a robots file that is broken and a
sitemap that does not exist, so the only way into the catalogue was whatever
links it happened to follow from the home page.

WHY ROUTES, NOT FILES IN frontend/public. Both answers belong to THIS
deployment rather than to the build: the sitemap is the database, and both
files name the site by absolute URL, which has to come from
settings.app_base_url. A static file would bake one domain into every build,
and building it from the request's Host header instead would let whoever sends
the request choose which domain a crawler is told the site lives on.

Registered as an ordinary router, so both work whether or not a build is
mounted, and both answer before the SPA catch-all ever runs.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from urllib.parse import quote
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_rate_limited
from app.models.alias import Condition, ProductAlias
from app.models.price import Price
from app.models.product import Product
from app.models.store import Store
from app.services import catalogue
from app.services.offers import current_offer

# THE MODULE, NOT THE FUNCTIONS. `from app.services.cache import cached_json`
# would bind the function into this namespace, and tests/conftest.py disables
# the cache by patching app.services.cache -- so a direct import would quietly
# keep talking to the real Redis in the test suite, and one test's sitemap
# would be served to the next.
from app.services import cache

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"

# The sitemaps.org protocol's limit for ONE sitemap file: 50,000 URLs (and
# 50 MB uncompressed, which at roughly a hundred bytes an entry the count
# reaches first). Past it, crawlers are entitled to ignore the whole file, not
# just the tail -- so the list is cut here rather than sent over the limit.
# The catalogue is a few hundred products today; reaching this is the signal
# to switch to a sitemap index pointing at several files, and the cut is
# logged so that day does not pass unnoticed.
MAX_URLS = 50_000

# Pages that are the same for every visitor and exist without a database.
# No lastmod: nothing records when their content last changed, and a date
# made up here -- the deploy time, today -- would teach a crawler to stop
# trusting the dates on the pages where it is real.
STATIC_PAGES = ("/", "/about", "/privacy", "/terms", "/contact")

# Pages a crawler has no business fetching.
#
# THIS IS NOT ACCESS CONTROL. Every one of these is enforced server-side, and
# robots.txt is public, so the list names nothing that is not already visible
# in the app's own JavaScript. What it does is keep crawl budget on the
# catalogue and keep a URL carrying a one-time token out of a crawler's queue:
#
#   /account, /wishlist, /alerts   signed-in only. A crawler has no session,
#                                  so all it would ever render is the
#                                  redirect to /login.
#   /admin, /merchant              the same, AND an API prefix. Written without
#                                  a trailing slash on purpose, so the rule
#                                  covers the page and every endpoint below it.
#                                  Safe only because no public page calls
#                                  either API -- which tests/test_seo.py
#                                  proves by walking the frontend's imports,
#                                  rather than trusting this comment.
#   /oauth/                        the provider callback, carrying a one-time
#                                  code and state. Trailing slash, because it
#                                  is the only thing under that path.
#   /verify-email, /reset-password the links from our emails, token in the
#                                  query string. Rendering /verify-email RUNS
#                                  its JavaScript, and that JavaScript spends
#                                  the token on load -- so a crawler that ever
#                                  found a leaked link would confirm somebody
#                                  else's address. A noindex tag cannot prevent
#                                  that; it is only read by fetching the page.
#
# WHAT IS DELIBERATELY NOT HERE: /auth, /products, /prices, /support. Google
# renders this SPA with JavaScript, and a disallowed API call is a blank page
# as far as the index is concerned -- disallow /products and every product
# page is indexed as an empty frame, which is worse than having no robots.txt
# at all. Every page also calls /auth/refresh on load to restore a session.
PRIVATE_PAGES = (
    "/account",
    "/wishlist",
    "/alerts",
    "/admin",
    "/merchant",
    "/oauth/",
    "/verify-email",
    "/reset-password",
)


def _base_url() -> str:
    """
    The public address of the site, from configuration and nowhere else.

    Read per request rather than captured at import, so what is served always
    matches the settings the process is actually running with.
    """
    return settings.app_base_url.rstrip("/")


@router.api_route("/robots.txt", methods=["GET", "HEAD"], include_in_schema=False)
async def robots_txt():
    """
    Crawl everything except the private pages, and here is the sitemap.

    NO `Allow: /` LINE. Anything not disallowed is already allowed, and the
    line is read two different ways: Google takes the LONGEST matching rule,
    but the original robots convention -- still what Python's own
    urllib.robotparser and plenty of smaller crawlers implement -- takes the
    FIRST, and would stop at `Allow: /` and crawl the private pages anyway.
    With only Disallow lines, both readings agree.

    NOT RATE LIMITED, unlike every catalogue endpoint. Google reads a 429 or a
    5xx on robots.txt as the whole site being disallowed, so a limiter tripped
    by a burst of crawler traffic would switch off indexing -- to protect a
    response that touches neither the database nor Redis.
    """
    lines = ["User-agent: *"]
    lines += [f"Disallow: {path}" for path in PRIVATE_PAGES]
    lines += ["", f"Sitemap: {_base_url()}/sitemap.xml"]
    return PlainTextResponse("\n".join(lines) + "\n")


@router.api_route("/sitemap.xml", methods=["GET", "HEAD"], include_in_schema=False)
async def sitemap_xml(
    db: Session = Depends(get_db),
    _: None = Depends(get_rate_limited),
):
    """
    Every public page worth crawling, built from the database.

    CACHED ON THE CATALOGUE VERSION, like /products/browse and /deals. The
    URL is public and takes no parameters, so without a cache anyone could
    make it re-run a scan of the whole catalogue on every request. With one,
    it is built once per catalogue generation: a merchant repricing a listing
    or an admin verifying -- or unverifying -- a store bumps the version, so
    a store that loses its verification drops out of the sitemap at once
    rather than a TTL later.

    The base URL is in the key too. It is part of the response, and a cache
    entry written under one APP_BASE_URL must not be served under another.
    """
    base = _base_url()
    version = await cache.catalogue_version()
    fingerprint = hashlib.sha256(base.encode()).hexdigest()[:16]
    cache_key = f"sitemap:v1:{version}:{fingerprint}"

    body = await cache.cached_json(cache_key)
    # A string or nothing. Anything else under this key is not a sitemap this
    # code wrote, and rebuilding is cheaper than serving it.
    if not isinstance(body, str):
        body = build_sitemap(db, base)
        await cache.store_json(cache_key, body)

    return Response(content=body, media_type="application/xml")


def build_sitemap(db: Session, base: str) -> str:
    """The sitemap document, as text. Separate from the route so the cache can wrap it."""
    entries: list[tuple[str, str | None]] = [
        (f"{base}{path}", None) for path in STATIC_PAGES
    ]

    # THE SAME CALL /products/browse MAKES for its category tiles, not a
    # second query written to mean the same thing. Two queries would drift,
    # and a sitemap URL for a category the site shows as empty is a crawl
    # that ends on "nothing here".
    touched = _category_lastmod(db)
    for row in catalogue.category_counts(db):
        name = row["category"]
        entries.append(
            (f"{base}/browse/{quote(name, safe='')}", _w3c(touched.get(name)))
        )

    room = MAX_URLS - len(entries)
    # One more than there is room for, so a cut is detectable without a
    # separate COUNT over the whole table.
    products = _product_rows(db, limit=room + 1)
    if len(products) > room:
        logger.warning(
            "Sitemap reached the %s URL limit; products beyond it are omitted",
            MAX_URLS,
            extra={"action": "sitemap_truncated"},
        )
        products = products[:room]

    entries += [
        (f"{base}/product/{product_id}", _w3c(last_updated))
        for product_id, last_updated in products
    ]
    return _render(entries)


def _product_rows(db: Session, *, limit: int) -> list[tuple[int, datetime | None]]:
    """
    Products a shopper can buy right now, with when their page last changed.

    A PRODUCT QUALIFIES ON ONE OFFER THAT IS BOTH IN STOCK AND FROM A VISIBLE
    STORE -- the same row, not one of each. The visibility rule is in the
    WHERE, so it removes an unverified merchant's rows BEFORE grouping, and
    the HAVING then asks about availability among the rows that are left.
    Asking the two questions separately would list a product whose only
    in-stock offer is from a store nobody has verified, as long as a verified
    store lists it out of stock -- a sitemap URL that exists only because of
    the unverified store.

    lastmod is the newest change to any visible offer, in stock or not: the
    product page shows both, and an offer going out of stock is a change to
    that page. Rows from hidden stores cannot move it, or the sitemap would
    say when an unverified shop last edited its prices.

    "VISIBLE OFFER" MEANS A CURRENT ONE -- offers.current_offer(), the rule
    the product page itself applies. A product whose only in-stock listing the
    store has removed, or nobody has re-read in two days, answers 404 there,
    and a sitemap URL that 404s is an error in Search Console and crawl budget
    spent on nothing. It sits in the WHERE, where store visibility sat, for
    the reason above: the in-stock HAVING must see only rows that are offers,
    or a delisted listing still marked in stock would qualify a product whose
    current offers are all sold out.

    lastmod is still Price.last_updated -- when a price CHANGED -- and never
    checked_at, which moves on every six-hourly re-read of an unchanged price
    and would tell a crawler every page in the catalogue changed four times a
    day. A listing LEAVING does not move lastmod: nothing records when a price
    went stale, and dating only the delisted half of that change would make
    the date mean two different things.

    Ordered by id so the document is stable between builds. The LIMIT bounds
    the document, not the work: the grouping still reads every visible offer,
    which is what the route's cache is for.
    """
    in_stock = func.max(case((Price.availability.is_(True), 1), else_=0))
    rows = (
        db.query(ProductAlias.product_id, func.max(Price.last_updated))
        .join(Price, Price.alias_id == ProductAlias.id)
        .join(Store, Store.id == ProductAlias.store_id)
        .filter(current_offer())
        .group_by(ProductAlias.product_id)
        .having(in_stock == 1)
        .order_by(ProductAlias.product_id)
        .limit(limit)
        .all()
    )
    return [(product_id, last_updated) for product_id, last_updated in rows]


def _category_lastmod(db: Session) -> dict[str, datetime]:
    """
    When each category page last changed: the newest visible offer it draws on.

    Scoped the way the browse listing is -- current offers, new condition,
    browsable categories -- so a second-hand listing, a hidden store's edit or
    a listing the store has removed does not claim a change on a page that
    never shows it. current_offer() is what catalogue.category_counts applies
    to decide which of these categories are listed at all.
    """
    rows = (
        db.query(Product.match_category, func.max(Price.last_updated))
        .join(ProductAlias, ProductAlias.product_id == Product.id)
        .join(Price, Price.alias_id == ProductAlias.id)
        .join(Store, Store.id == ProductAlias.store_id)
        .filter(current_offer())
        .filter(ProductAlias.condition == Condition.new.value)
        .filter(Product.match_category.in_(catalogue.BROWSABLE))
        .group_by(Product.match_category)
        .all()
    )
    return {name: moment for name, moment in rows if moment is not None}


def _w3c(moment: datetime | None) -> str | None:
    """
    A timestamp in the W3C Datetime form the protocol asks for, or None.

    A NAIVE VALUE IS TAKEN AS UTC. Postgres returns this column timezone-aware;
    SQLite, which the tests run on, drops the zone, and the only thing that
    ever writes it is the database's own now(), which SQLite keeps in UTC.
    """
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _escape(value: str) -> str:
    """
    Entity-escape a value for the sitemap.

    ALL FIVE CHARACTERS, not the three XML strictly needs inside text: the
    sitemaps.org protocol requires quotes to be escaped as well, and a
    validator that follows it to the letter rejects the file otherwise.
    """
    return escape(value, {"'": "&apos;", '"': "&quot;"})


def _render(entries: list[tuple[str, str | None]]) -> str:
    """
    The urlset document.

    Every value passes through _escape here, in the one place entries become
    XML, so no caller can forget it. Today the values are a configured base
    URL, fixed paths and integer ids, which is exactly why it must not depend
    on them staying that tame.

    ONE URL PER PAGE, WITH NO hreflang ALTERNATES. The English toggle changes
    the language on the SAME URL, so there is no second address to point to.
    """
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<urlset xmlns="{SITEMAP_NS}">',
    ]
    for loc, lastmod in entries:
        parts.append("  <url>")
        parts.append(f"    <loc>{_escape(loc)}</loc>")
        if lastmod:
            parts.append(f"    <lastmod>{_escape(lastmod)}</lastmod>")
        parts.append("  </url>")
    parts.append("</urlset>")
    return "\n".join(parts) + "\n"
