"""
Check every store link a shopper can click, and confirm the product is there.

WHAT IT CHECKS
Every "Visit store" link on the site is a scraped listing's store_product_url.
This reads each one that is currently shown to shoppers -- the rows
offers.current_offer() admits, for scraped stores only -- asks the store
whether that product still exists, and sorts the answers:

  OK            the product answers under the same handle, and this listing's
                variant (by SKU, or by variant id for "shopify-<id>") is in it
  VARIANT_GONE  the product answers, but no longer has this listing's variant
  RENAMED       the product answers under a different handle: the JSON says
                so, or the store redirected to another /products/<handle>
  GONE          the store answered 404 for the product itself
  UNKNOWN       anything else -- 429, 5xx, a timeout, a blocked or unexpected
                redirect, a body that is not the product JSON, robots.txt
                saying no, a link that is not a /products/<handle> URL

WHY THIS EXISTS
A listing the store removed kept its last price forever. Live on 2026-09-15:
product 483, iPhone 16 128GB, showed SmartBuy at 689 JOD as the best price,
and https://smartbuy-me.com/products/abj1501st0307 was a 404 that no longer
appeared in SmartBuy's /products.json. The per-store scrape caps also meant
the oldest listings were never re-read, so nothing noticed. The owner's ask
was plain: look at every link a shopper can click and confirm it is real.

WHY <url>.js AND NOT THE PAGE ITSELF
Shopify serves every product's data at /products/<handle>.js. Measured on all
three stores on 2026-09-15: a product that exists answers 200 with JSON
carrying handle, title, available and variants [{id, sku, price, available}];
one that does not answers a hard 404 with an empty body -- and so does its
HTML page, so a 404 here is the same 404 the shopper would land on. The JSON
settles BOTH questions the audit asks (does the product exist; does it still
sell this variant) from structured data, where the HTML would need
theme-specific parsing that breaks whenever a merchant edits the theme -- the
reason shopify.py reads products.json too. It is also small: the largest
products.json page measured, 250 products on iGeek, was 3.38 MB, about 13.5 KB
per product with every variant and image; the HTML page wraps the same product
in the whole storefront theme. No redirects were observed.

POLITENESS
Every request goes through app.services.scrapers.http.fetch, so the host
allowlist, the SSRF checks, the redirect and size caps all apply, and it can
only GET. robots.txt is honoured through robots.can_fetch (all three stores
allowed /products/<handle>.js when measured, with no Crawl-delay). Requests to
one host are spaced by that store's registry delay, raised by any robots
Crawl-delay and never below MIN_DELAY_SECONDS -- the robots.txt read itself
counts as a request. Hosts are interleaved, so three stores cost roughly the
time of the largest, not the sum of all three.

WHY DRY RUN IS THE DEFAULT
Delisting takes a price out of every comparison the site shows. A store having
a bad hour -- a CDN answering 404 for everything, a botched theme migration --
looks exactly like a catalogue that vanished, and the first run of anything
that removes prices should be read by a person before it acts. --apply then
changes only GONE, VARIANT_GONE and RENAMED listings. UNKNOWN is never grounds
for a change: "could not tell" is not "gone", and treating it as gone would
delist a store's whole catalogue the first time it rate-limited us.

USAGE -- on the server, from the repository checkout. The production image
carries backend/ at /app (deploy/Dockerfile), so the worker container can run
it against the production database and Redis it already has:

    docker compose -f deploy/docker-compose.yml exec worker \\
        python scripts/audit_store_links.py                     # dry run
    ... python scripts/audit_store_links.py --store smartbuy --limit 20
    ... python scripts/audit_store_links.py --apply

It refuses to start while a scrape job is queued or running: the worker's
scrape and this audit each space their own requests two seconds apart, but not
from each other, so together they would hit a store twice as often. Run it
between scrapes (every six hours; a full scrape takes about five minutes).

--apply refuses, and changes nothing, when it would delist more than a fifth
of any store's checked listings (and more than three): the shape of a store
having a bad hour, not of a store clearing stock. Read the dry run, then pass
--force if the removals are real.

Locally: cd backend && .venv/Scripts/python.exe scripts/audit_store_links.py

THE REPORT is JSON. --report PATH puts it at PATH (relative to the current
directory). Without it, it goes to the system temp directory as
link-audit-<UTC time>.json -- deliberately NOT the current directory, because
this is run from backend/, which is inside a public repository, and a stray
report is one `git add .` from being published. In the container that is /tmp;
copy it out with
    docker compose -f deploy/docker-compose.yml cp worker:/tmp/<name> .
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import time
from collections import Counter, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional
from urllib.parse import quote, unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import update  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models.alias import ProductAlias  # noqa: E402
from app.models.price import Price  # noqa: E402
from app.models.scrape_job import JobStatus, ScrapeJob  # noqa: E402
from app.models.store import Store  # noqa: E402
from app.services.cache import bump_catalogue_version_sync  # noqa: E402
from app.services.offers import current_offer  # noqa: E402
from app.services.scrapers.base import StoreConfig  # noqa: E402
from app.services.scrapers.http import BlockedURLError, FetchResult, fetch  # noqa: E402
from app.services.scrapers.registry import ALLOWED_HOSTS, STORES, store_by_code  # noqa: E402
from app.services.scrapers.robots import can_fetch, rules_for  # noqa: E402

OK = "OK"
RENAMED = "RENAMED"
VARIANT_GONE = "VARIANT_GONE"
GONE = "GONE"
UNKNOWN = "UNKNOWN"
VERDICTS = (OK, RENAMED, VARIANT_GONE, GONE, UNKNOWN)

# The only verdicts that take a listing out of the comparison. UNKNOWN is
# deliberately absent -- see "WHY DRY RUN IS THE DEFAULT" above -- and the
# test suite breaks this set on purpose to prove that absence is load-bearing.
DELIST_VERDICTS = frozenset({GONE, VARIANT_GONE})

# A floor under every store's own delay. The registry says 2.0 for all three
# today; this keeps an audit polite even if someone lowers a scrape delay for
# a reason that has nothing to do with a thousand one-by-one product reads.
MIN_DELAY_SECONDS = 2.0

# store_product_url is String(500). A new URL longer than that would fail the
# UPDATE on PostgreSQL mid-commit and roll back every other change with it.
MAX_URL_LENGTH = 500

# /products/<handle> exactly, as shopify.py writes it. Collection-scoped or
# locale-prefixed forms are not what the scraper stores, so they are reported
# rather than guessed at.
_PAGE_PATH = re.compile(r"^/products/([^/]+)/?$")
_JS_PATH = re.compile(r"^/products/([^/]+)\.js$")

# What a handle from the store's JSON must look like before it is written into
# a link the site shows. The JSON is remote, untrusted text: without this a
# handle of "../account" or "x?y=z" would become a shopper-facing URL. Shopify
# handles are letters, digits and hyphens; \w also admits non-Latin letters,
# which a store with Arabic handles would use, and those are percent-encoded
# when the URL is built.
_HANDLE = re.compile(r"^[\w-]{1,255}$")

_CODE_BY_NAME = {config.name: config.code for config in STORES}


def _printable(text: str, limit: int = 300) -> str:
    """
    Remote text made safe to print to an operator's terminal.

    Details carry fragments the store chose -- a redirect target, an error
    message -- and a control character in one is an escape sequence in a
    terminal. Replaced rather than dropped, so it is visible that it was there.
    """
    return "".join(ch if ch.isprintable() else "?" for ch in str(text))[:limit]


@dataclass
class Listing:
    """One ProductAlias behind a link."""

    alias_id: int
    product_id: int
    store_product_id: Optional[str]
    verdict: str = ""
    detail: str = ""


@dataclass
class Link:
    """One distinct store_product_url, and every current listing that uses it."""

    url: str
    store_id: int
    store_code: str
    listings: list[Listing] = field(default_factory=list)
    host: str = ""
    handle: str = ""
    js_url: str = ""
    verdict: str = ""
    detail: str = ""
    http_status: Optional[int] = None
    new_url: Optional[str] = None


@dataclass
class Change:
    """One row --apply wrote, or would have written but found changed."""

    action: str  # "delisted" | "relinked" | "skipped"
    alias_id: int
    product_id: int
    store_code: str
    verdict: str
    url: str
    new_url: Optional[str] = None
    reason: str = ""


# --- Selection ---------------------------------------------------------------


def select_links(
    db: Session,
    now: datetime,
    store_code: Optional[str] = None,
    limit: Optional[int] = None,
) -> list[Link]:
    """
    Every distinct link a shopper can currently click, grouped with its listings.

    THE SAME PREDICATE THE SITE USES. A link is worth checking exactly when a
    shopper can see it, so this filters on offers.current_offer() rather than
    re-deriving "shown" here -- a second definition is how the audit would
    come to check a set of links different from the one the site displays.
    Delisted and stale listings are already out of every comparison, so
    fetching their pages would spend the stores' patience on nothing.

    Merchant stores are excluded: their listings have no store page to fetch,
    and nothing here may delist a price a person set.

    One row per alias comes back (prices are one per alias), and the grouping
    into distinct URLs happens below, because --apply needs to know which
    aliases each URL stands for.
    """
    query = (
        db.query(
            ProductAlias.id,
            ProductAlias.product_id,
            ProductAlias.store_product_id,
            ProductAlias.store_product_url,
            Store.id,
            Store.name,
        )
        .select_from(Price)
        .join(ProductAlias, ProductAlias.id == Price.alias_id)
        .join(Store, Store.id == ProductAlias.store_id)
        .filter(
            current_offer(now),
            Store.owner_user_id.is_(None),
            ProductAlias.store_product_url.isnot(None),
            ProductAlias.store_product_url != "",
        )
        # Stable order, so --limit samples the same links on every run and a
        # re-check after a fix looks at what the first run looked at.
        .order_by(Store.name, ProductAlias.store_product_url, ProductAlias.id)
    )
    if store_code:
        config = store_by_code(store_code)
        if config is None:
            raise ValueError(f"unknown store code {store_code!r}")
        # The ingest finds its Store row by config.name, so the name is the
        # join between the registry and the table.
        query = query.filter(Store.name == config.name)

    links: dict[tuple[int, str], Link] = {}
    for alias_id, product_id, sku, url, store_id, store_name in query.all():
        # Keyed by store as well as URL: two stores cannot share a product URL
        # (their hosts differ), but if data ever said otherwise, one store's
        # verdict must not be counted -- or applied -- as the other's.
        key = (store_id, url)
        link = links.get(key)
        if link is None:
            link = links[key] = Link(
                url=url,
                store_id=store_id,
                store_code=_CODE_BY_NAME.get(store_name, store_name),
            )
        link.listings.append(
            Listing(alias_id=alias_id, product_id=product_id, store_product_id=sku)
        )

    selected = list(links.values())
    if limit is not None:
        taken: Counter[str] = Counter()
        sample = []
        for link in selected:
            if taken[link.store_code] < limit:
                taken[link.store_code] += 1
                sample.append(link)
        selected = sample
    return selected


# --- Checking ------------------------------------------------------------------


def variant_present(store_product_id: Optional[str], variants: list) -> Optional[bool]:
    """
    Whether the store's product JSON still has this listing's variant.

    The scraper keys a listing on the variant's SKU, or on "shopify-<id>" when
    the variant has none (shopify.py), so the same two keys are looked up
    here. None means there is no key to look for, which is not evidence either
    way.
    """
    key = (store_product_id or "").strip()
    if not key:
        return None
    skus = set()
    ids = set()
    for variant in variants:
        if not isinstance(variant, dict):
            continue
        sku = str(variant.get("sku") or "").strip()
        if sku:
            skus.add(sku)
        if variant.get("id") is not None:
            ids.add(str(variant.get("id")))
    if key in skus:
        return True
    # Checked second, and as well rather than instead: a real SKU could begin
    # with "shopify-", and it must still match as a SKU.
    return key.startswith("shopify-") and key[len("shopify-"):] in ids


class HostThrottle:
    """
    Keeps requests to each host at least `delay` seconds apart.

    Per host rather than global, because politeness is owed to each store
    separately and one store's pace has nothing to do with another's. The
    clock and sleep are injected so the spacing can be tested without waiting.
    """

    def __init__(self, clock: Callable[[], float], sleep: Callable[[float], None]):
        self._clock = clock
        self._sleep = sleep
        self._last: dict[str, float] = {}

    def ready_at(self, host: str, delay: float) -> float:
        last = self._last.get(host)
        return float("-inf") if last is None else last + delay

    def wait(self, host: str, delay: float) -> None:
        # A loop, not one sleep: a sleep may return a hair early on some
        # platforms, and "at least" is the promise.
        while (remaining := self.ready_at(host, delay) - self._clock()) > 0:
            self._sleep(remaining)
        self._last[host] = self._clock()


class LinkAuditor:
    """Fetches each link's product JSON, politely, and gives it a verdict."""

    def __init__(
        self,
        *,
        fetch_fn: Callable[..., FetchResult] = fetch,
        rules_fn: Callable = rules_for,
        can_fetch_fn: Callable[[str, set[str]], bool] = can_fetch,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        stores: Iterable[StoreConfig] = STORES,
        allowed_hosts: set[str] = ALLOWED_HOSTS,
        progress: Optional[Callable[[str], None]] = None,
    ):
        self._fetch = fetch_fn
        self._rules = rules_fn
        self._can_fetch = can_fetch_fn
        self._throttle = HostThrottle(clock, sleep)
        self._config_by_host = {config.host: config for config in stores}
        self._allowed_hosts = allowed_hosts
        self._progress = progress or (lambda line: print(line, file=sys.stderr, flush=True))
        self._crawl_delay: dict[str, Optional[float]] = {}
        self._robots_read_at: dict[str, float] = {}

    def delay_for(self, host: str) -> float:
        config = self._config_by_host.get(host)
        configured = config.delay_seconds if config else 0.0
        # A site asking for more space gets it; nobody gets less than the floor.
        return max(MIN_DELAY_SECONDS, configured, self._crawl_delay.get(host) or 0.0)

    def run(self, links: list[Link]) -> None:
        """Give every link and listing a verdict, in place."""
        queues: dict[str, deque[Link]] = {}
        for link in links:
            if self._prepare(link):
                queues.setdefault(link.host, deque()).append(link)
            else:
                self._judge_listings(link, variants=None)

        total = sum(len(queue) for queue in queues.values())
        if total:
            longest = max(
                len(queue) * self.delay_for(host) for host, queue in queues.items()
            )
            self._progress(
                f"Checking {total} links on {len(queues)} host(s), each host's "
                f"requests >= {MIN_DELAY_SECONDS:g} s apart: about "
                f"{longest / 60:.1f} min."
            )

        done = 0
        while queues:
            # Whichever host may be asked soonest goes next. That interleaves
            # the stores, so the run takes about as long as the busiest one
            # instead of all of them end to end, without any store being asked
            # faster than its own delay.
            host = min(
                queues, key=lambda h: self._throttle.ready_at(h, self.delay_for(h))
            )
            link = queues[host].popleft()
            if not queues[host]:
                del queues[host]
            self._check(link)
            done += 1
            # The listings' verdicts, not the link's: a link that answers OK
            # can still be VARIANT_GONE for the listing that matters.
            found = {listing.verdict for listing in link.listings}
            shown = "+".join(verdict for verdict in VERDICTS if verdict in found)
            self._progress(
                f"[{done}/{total}] {link.store_code:<10} {shown:<12} "
                f"{_printable(link.url)}"
            )

    # --- one link -------------------------------------------------------

    def _prepare(self, link: Link) -> bool:
        """
        Parse the link. False when it can be judged without asking the store.

        Checked before any request so a link that could never be fetched does
        not cost a store a throttle slot -- fetch() would refuse it anyway.
        """
        parsed = urlparse(link.url)
        link.host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or link.host not in self._allowed_hosts:
            link.verdict = UNKNOWN
            link.detail = "not an https link on a scraped store's allow-listed host"
            return False
        match = _PAGE_PATH.match(parsed.path)
        if not match:
            link.verdict = UNKNOWN
            link.detail = "not a /products/<handle> link"
            return False
        segment = match.group(1)
        link.handle = unquote(segment)
        # Built from the path segment as stored, so an already percent-encoded
        # handle is not encoded twice. Any query string is dropped: .js
        # describes the whole product, whatever variant a link preselects.
        link.js_url = f"https://{link.host}/products/{segment}.js"
        return True

    def _check(self, link: Link) -> None:
        host = link.host
        self._throttle.wait(host, self.delay_for(host))
        try:
            rules = self._rules(f"https://{host}/", self._allowed_hosts)
            if getattr(rules, "fetched_at", None) != self._robots_read_at.get(host):
                # robots.txt was just READ -- the first link on this host, or
                # its hour-long cache expired mid-run. That read was a request
                # to the store, so the product request waits its turn behind
                # it; and a Crawl-delay it carries applies from here on.
                self._robots_read_at[host] = rules.fetched_at
                self._crawl_delay[host] = rules.crawl_delay
                self._throttle.wait(host, self.delay_for(host))
            allowed = self._can_fetch(link.js_url, self._allowed_hosts)
        except Exception as exc:  # noqa: BLE001 -- one link must not end the run
            self._unknown(link, f"robots.txt check failed: {type(exc).__name__}")
            return
        if not allowed:
            self._unknown(link, "robots.txt disallows this path")
            return

        try:
            result = self._fetch(link.js_url, self._allowed_hosts)
        except BlockedURLError as exc:
            self._unknown(link, f"blocked by the fetcher: {_printable(exc)}")
            return
        except Exception as exc:  # noqa: BLE001 -- timeouts, resets, TLS errors
            self._unknown(link, f"{type(exc).__name__}: {_printable(exc)}")
            return

        self._classify(link, result)

    def _unknown(self, link: Link, detail: str) -> None:
        link.verdict = UNKNOWN
        link.detail = detail
        self._judge_listings(link, variants=None)

    def _classify(self, link: Link, result: FetchResult) -> None:
        link.http_status = result.status_code

        # Did fetch() follow a redirect? It re-validates and follows each hop
        # itself, so the only trace is the final URL differing from ours.
        final = urlparse(result.url)
        final_host = (final.hostname or "").lower()
        redirect_handle = None
        if final_host != link.host or unquote(final.path) != unquote(
            urlparse(link.js_url).path
        ):
            match = _JS_PATH.match(final.path) if final_host == link.host else None
            if match is None:
                # Somewhere that is not a product: a password page, the home
                # page, a locale prefix. Not evidence the product is gone.
                self._unknown(
                    link,
                    f"redirected to {_printable(result.url)} "
                    f"(HTTP {result.status_code})",
                )
                return
            redirect_handle = unquote(match.group(1))

        if result.status_code == 404:
            if redirect_handle is None:
                link.verdict = GONE
                link.detail = "HTTP 404"
                self._judge_listings(link, variants=None)
            else:
                # The store pointed this product somewhere and THAT is
                # missing. Never observed; a delisting should rest on the
                # product's own 404, not on a hop the store chose.
                self._unknown(
                    link, f"redirected to {_printable(result.url)}, which answered 404"
                )
            return

        if result.status_code != 200:
            self._unknown(link, f"HTTP {result.status_code}")
            return

        try:
            payload = json.loads(result.text)
        except ValueError:
            self._unknown(link, "HTTP 200, but the body is not JSON")
            return
        handle = payload.get("handle") if isinstance(payload, dict) else None
        variants = payload.get("variants") if isinstance(payload, dict) else None
        if not isinstance(handle, str) or not _HANDLE.match(handle):
            self._unknown(link, "HTTP 200, but no usable handle in the JSON")
            return
        if not isinstance(variants, list):
            self._unknown(link, "HTTP 200, but no variants list in the JSON")
            return
        if redirect_handle is not None and redirect_handle != handle:
            self._unknown(
                link, "the redirect and the product JSON name different handles"
            )
            return

        if handle == link.handle:
            link.verdict = OK
            link.detail = "HTTP 200"
        else:
            new_url = f"https://{link.host}/products/{quote(handle, safe='-_')}"
            if len(new_url) > MAX_URL_LENGTH:
                self._unknown(link, "renamed, but the new URL is too long to store")
                return
            link.verdict = RENAMED
            link.new_url = new_url
            link.detail = f"handle is now {handle!r}"
        self._judge_listings(link, variants=variants)

    def _judge_listings(self, link: Link, variants: Optional[list]) -> None:
        """
        Carry the link's verdict to each listing, narrowed by its variant.

        One Shopify product is several listings here -- 128GB and 256GB are
        separate variants, often separate products -- so one link can be fine
        for one listing and wrong for another.
        """
        for listing in link.listings:
            listing.verdict = link.verdict
            listing.detail = link.detail
            if variants is None or link.verdict not in (OK, RENAMED):
                continue
            present = variant_present(listing.store_product_id, variants)
            if present is False:
                listing.verdict = VARIANT_GONE
                listing.detail = (
                    f"{_printable(listing.store_product_id)} is not among the "
                    "product's variants"
                )
            elif link.verdict == RENAMED and present is None:
                # A store may redirect a discontinued product to its successor.
                # Relinking a listing there without its SKU in the new product
                # would send an iPhone 15 shopper to an iPhone 16 page.
                listing.verdict = UNKNOWN
                listing.detail = (
                    "renamed, but the listing has no SKU or variant id to "
                    "confirm the new product is the same one"
                )


# --- Acting ------------------------------------------------------------------


def apply_changes(db: Session, links: list[Link], at: datetime) -> list[Change]:
    """
    Delist GONE and VARIANT_GONE listings, relink RENAMED ones. One commit.

    Every UPDATE is guarded on the row still looking the way the audit saw it
    -- same URL, not already delisted. The audit takes minutes, and the worker
    may have scraped in between: an alias whose URL changed, or which was
    delisted with its own timestamp, is left alone and reported as skipped
    rather than overwritten on the strength of a check of something else.

    OK and UNKNOWN listings are not touched at all.
    """
    changes: list[Change] = []
    for link in links:
        for listing in link.listings:
            if listing.verdict in DELIST_VERDICTS:
                action = "delisted"
                values = {"delisted_at": at}
            elif listing.verdict == RENAMED and link.new_url:
                action = "relinked"
                values = {"store_product_url": link.new_url}
            else:
                continue

            statement = (
                update(ProductAlias)
                .where(
                    ProductAlias.id == listing.alias_id,
                    ProductAlias.store_product_url == link.url,
                    ProductAlias.delisted_at.is_(None),
                )
                .values(**values)
                .execution_options(synchronize_session=False)
            )
            written = db.execute(statement).rowcount == 1
            changes.append(
                Change(
                    action=action if written else "skipped",
                    alias_id=listing.alias_id,
                    product_id=listing.product_id,
                    store_code=link.store_code,
                    verdict=listing.verdict,
                    url=link.url,
                    new_url=link.new_url if action == "relinked" else None,
                    reason="" if written else "changed since it was audited",
                )
            )
    # One commit for the lot: a failure halfway leaves the catalogue as it
    # was, not half-applied with a report that describes neither state.
    db.commit()
    return changes


# --- Output ------------------------------------------------------------------


def summary(links: list[Link]) -> str:
    """Counts per store and verdict, then every link that is not OK."""
    stores = sorted({link.store_code for link in links})
    lines = []
    listing_total = sum(len(link.listings) for link in links)
    lines.append(
        f"Checked {len(links)} links ({listing_total} listings) "
        f"across {len(stores)} store(s). Counts are listings."
    )
    header = f"{'store':<12}{'links':>6}" + "".join(f"{v:>14}" for v in VERDICTS)
    lines.append("")
    lines.append(header)
    for code in stores:
        own = [link for link in links if link.store_code == code]
        counts = Counter(item.verdict for link in own for item in link.listings)
        lines.append(
            f"{code:<12}{len(own):>6}" + "".join(f"{counts[v]:>14}" for v in VERDICTS)
        )

    problems = []
    for link in links:
        by_verdict: dict[str, list[Listing]] = {}
        for listing in link.listings:
            if listing.verdict != OK:
                by_verdict.setdefault(listing.verdict, []).append(listing)
        for verdict, listings in by_verdict.items():
            products = ",".join(str(p) for p in sorted({item.product_id for item in listings}))
            line = (
                f"  {verdict:<13} {link.store_code:<10} product {products:<10} "
                f"{_printable(link.url)}"
            )
            if verdict == RENAMED and link.new_url:
                line += f" -> {link.new_url}"
            details = sorted({item.detail for item in listings if item.detail})
            if details:
                line += f"  ({'; '.join(details)})"
            problems.append(line)

    lines.append("")
    if problems:
        lines.append("Not OK:")
        lines.extend(problems)
    else:
        lines.append("Every link checked is OK.")
    return "\n".join(lines)


def report_data(
    links: list[Link],
    *,
    generated_at: datetime,
    apply: bool,
    store_code: Optional[str],
    limit: Optional[int],
    changes: Optional[list[Change]] = None,
) -> dict:
    by_store: dict[str, dict] = {}
    for link in links:
        entry = by_store.setdefault(
            link.store_code, {"links": 0, **{verdict: 0 for verdict in VERDICTS}}
        )
        entry["links"] += 1
        for listing in link.listings:
            entry[listing.verdict] += 1
    data = {
        "generated_at": generated_at.isoformat(),
        "mode": "apply" if apply else "dry-run",
        "store": store_code,
        "limit_per_store": limit,
        "by_store": by_store,
        "links": [
            {
                "url": link.url,
                "store": link.store_code,
                "host": link.host,
                "verdict": link.verdict,
                "detail": link.detail,
                "http_status": link.http_status,
                "new_url": link.new_url,
                "listings": [asdict(listing) for listing in link.listings],
            }
            for link in links
        ],
    }
    if apply:
        # null until the changes are committed: an --apply report without a
        # list is one whose run stopped before, or while, applying.
        data["changes"] = (
            None if changes is None else [asdict(change) for change in changes]
        )
    return data


def default_report_path(now: datetime) -> Path:
    """Outside the repository -- see THE REPORT in the module docstring."""
    stamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path(tempfile.gettempdir()) / f"link-audit-{stamp}.json"


def write_report(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# --- Guards -------------------------------------------------------------------

# --apply may delist at most this share of one store's checked listings, and
# always at least this many, without --force. See the module docstring.
MASS_REMOVAL_SHARE = 0.2
MASS_REMOVAL_FLOOR = 3


def scrape_in_progress(db: Session) -> bool:
    """True while the worker has a scrape queued or running."""
    return (
        db.query(ScrapeJob.id)
        .filter(ScrapeJob.status.in_([JobStatus.queued.value, JobStatus.running.value]))
        .first()
        is not None
    )


def mass_removals(links: list[Link]) -> dict[str, tuple[int, int]]:
    """Stores whose --apply would delist too much: code -> (delist, checked)."""
    checked: Counter = Counter()
    delist: Counter = Counter()
    for link in links:
        for item in link.listings:
            checked[link.store_code] += 1
            if item.verdict in DELIST_VERDICTS:
                delist[link.store_code] += 1
    return {
        code: (delist[code], checked[code])
        for code in checked
        if delist[code] > max(MASS_REMOVAL_FLOOR, int(checked[code] * MASS_REMOVAL_SHARE))
    }


# --- Entry point -------------------------------------------------------------


def main(
    argv: Optional[list[str]] = None,
    *,
    session_factory: Optional[Callable[[], Session]] = None,
    auditor: Optional[LinkAuditor] = None,
    now: Optional[datetime] = None,
) -> int:
    parser = argparse.ArgumentParser(
        description="Check that every store link shoppers can click still "
        "leads to the product. Dry run unless --apply."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="delist GONE and VARIANT_GONE listings and relink RENAMED ones "
        "(UNKNOWN is never changed)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="with --apply: apply even when a store would lose more than a "
        "fifth of its checked listings",
    )
    parser.add_argument(
        "--store", choices=[config.code for config in STORES], help="one store only"
    )
    parser.add_argument(
        "--limit", type=int, metavar="N", help="check at most N links per store"
    )
    parser.add_argument(
        "--report",
        type=Path,
        metavar="PATH",
        help="where to write the JSON report (default: the system temp "
        "directory, never the repository)",
    )
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")

    started = now or datetime.now(timezone.utc)
    report_path = args.report or default_report_path(started)
    db = (session_factory or SessionLocal)()
    try:
        if scrape_in_progress(db):
            print(
                "A scrape job is queued or running. Run the audit after it "
                "finishes, so the stores are not asked twice as often."
            )
            return 2
        links = select_links(db, started, store_code=args.store, limit=args.limit)
        # Nothing has been written. Ending the read transaction now keeps the
        # database from holding it open for the minutes the audit spends
        # waiting politely on the stores.
        db.rollback()

        (auditor or LinkAuditor()).run(links)

        mode = "APPLY" if args.apply else "DRY RUN -- nothing will be changed"
        print(f"Store link audit, {started.isoformat()} ({mode})")
        print(summary(links))

        common = dict(
            generated_at=started,
            apply=args.apply,
            store_code=args.store,
            limit=args.limit,
        )
        # Written before anything is applied, so a failure while applying
        # still leaves the audit's findings on disk.
        write_report(report_path, report_data(links, **common))

        if not args.apply:
            delist = sum(
                1
                for link in links
                for item in link.listings
                if item.verdict in DELIST_VERDICTS
            )
            relink = sum(
                1 for link in links for item in link.listings if item.verdict == RENAMED
            )
            print(
                f"\nDRY RUN: nothing was changed. --apply would delist {delist} "
                f"listing(s) and relink {relink}; UNKNOWN is never changed."
            )
            print(f"Report: {report_path}")
            return 0

        too_many = mass_removals(links)
        if too_many and not args.force:
            print("\nREFUSED: nothing was changed. --apply would delist too much of:")
            for code, (count, total) in sorted(too_many.items()):
                print(f"  {code}: {count} of {total} checked listings")
            print(
                "A store having a bad hour looks exactly like this. Read the "
                f"report ({report_path}); pass --force if the removals are real."
            )
            return 3
        if scrape_in_progress(db):
            print("A scrape job started while auditing; nothing was changed. Run it again after.")
            return 2

        applied_at = now or datetime.now(timezone.utc)
        changes = apply_changes(db, links, applied_at)
        print("\nApplied:")
        for change in changes:
            target = f" -> {change.new_url}" if change.new_url else ""
            reason = f"  ({change.reason})" if change.reason else ""
            print(
                f"  {change.action:<9} alias {change.alias_id:<7} product "
                f"{change.product_id:<7} {change.store_code:<10} "
                f"{change.verdict:<13} {_printable(change.url)}{target}{reason}"
            )
        written = sum(1 for change in changes if change.action != "skipped")
        if written:
            # Search responses are cached; without this a delisted price stays
            # in cached results until their TTL runs out.
            bump_catalogue_version_sync()
            print(f"Committed {written} change(s); catalogue cache version bumped.")
        else:
            print("Nothing to change.")

        write_report(
            report_path, report_data(links, changes=changes, **common)
        )
        print(f"Report: {report_path}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
