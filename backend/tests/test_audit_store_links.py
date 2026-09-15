"""
The store link audit: scripts/audit_store_links.py.

WHAT IS AT STAKE. --apply takes prices out of every comparison on the site,
so the rules that matter most are the ones about what it must NOT do: act on
an answer it could not interpret (UNKNOWN), act at all without --apply, look
at merchant listings or listings the site already hides, or ask a store for
pages faster than the scraper's own delay. Each has a test below, and the
UNKNOWN rule, the throttle, the variant check, the selection and the dry run
were each proven real by breaking the code and watching the test fail.

NEVER THE NETWORK. fetch, the robots.txt lookups, the clock and sleep are all
injected fakes; FakeStores refuses any URL it was not told about.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

import httpx
import pytest

from app.models.alias import ProductAlias
from app.models.price import Price
from app.models.product import Product
from app.models.store import Store
from app.services.scrapers.base import StoreConfig
from app.services.scrapers.http import BlockedURLError, FetchResult

# scripts/ is not a package, so the module is loaded from its path. Registered
# in sys.modules before executing: dataclasses resolves its own module there.
_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "audit_store_links.py"
_spec = importlib.util.spec_from_file_location("audit_store_links", _SCRIPT)
audit = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = audit
_spec.loader.exec_module(audit)

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
SB = "smartbuy-me.com"
IG = "igeekjo.com"


# --- Fakes ---------------------------------------------------------------------


class FakeClock:
    """monotonic() and sleep() over a clock that only moves when slept."""

    def __init__(self):
        self.now = 1000.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class FakeRules:
    def __init__(self, fetched_at: float, crawl_delay=None):
        self.fetched_at = fetched_at
        self.crawl_delay = crawl_delay


class UnexpectedRequest(BaseException):
    """
    A BaseException, so the auditor's `except Exception` -- which rightly
    turns a failed request into UNKNOWN -- cannot swallow a test's mistake.
    """


class FakeStores:
    """
    Stands in for every store. Records each request with the clock time.

    robots.txt is "read" (and logged as a request) the first time a host is
    asked about, like the real hour-long cache; `expire_robots` forces the
    next lookup to read again, as an expired cache would.
    """

    def __init__(self, clock: FakeClock):
        self.clock = clock
        self.pages: dict[str, object] = {}
        self.requests: list[tuple[str, str, float]] = []
        self.crawl_delay: dict[str, float] = {}
        self.disallowed: set[str] = set()
        self._rules: dict[str, FakeRules] = {}

    def page(self, url: str, answer) -> None:
        self.pages[url] = answer

    def fetch(self, url, allowed_hosts, **kwargs):
        host = urlparse(url).hostname
        self.requests.append((host, url, self.clock.now))
        if url not in self.pages:
            raise UnexpectedRequest(url)
        answer = self.pages[url]
        if isinstance(answer, BaseException):
            raise answer
        return answer

    def rules_for(self, base_url, allowed_hosts):
        host = urlparse(base_url).hostname
        if host not in self._rules:
            self.requests.append((host, "robots.txt", self.clock.now))
            self._rules[host] = FakeRules(self.clock.now, self.crawl_delay.get(host))
        return self._rules[host]

    def expire_robots(self, host: str) -> None:
        self._rules.pop(host, None)

    def can_fetch(self, url, allowed_hosts):
        return urlparse(url).path not in self.disallowed


def product_json(url, handle, variants, status=200, final_url=None) -> FetchResult:
    body = json.dumps({"handle": handle, "title": handle, "available": True,
                       "variants": variants})
    return FetchResult(url=final_url or url, status_code=status, text=body,
                       content_type="application/json")


def not_found(url, final_url=None) -> FetchResult:
    # Measured: a missing product's .js is a 404 with a 0-byte body.
    return FetchResult(url=final_url or url, status_code=404, text="",
                       content_type="text/html")


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def stores(clock):
    return FakeStores(clock)


@pytest.fixture
def auditor(stores, clock):
    return audit.LinkAuditor(
        fetch_fn=stores.fetch,
        rules_fn=stores.rules_for,
        can_fetch_fn=stores.can_fetch,
        clock=clock.monotonic,
        sleep=clock.sleep,
        progress=lambda line: None,
    )


@pytest.fixture
def bumps(monkeypatch):
    calls = []
    monkeypatch.setattr(audit, "bump_catalogue_version_sync", lambda: calls.append(1))
    return calls


# --- Catalogue fixtures -------------------------------------------------------


def add_store(db, name="SmartBuy", host=SB, *, owner_user_id=None, verified=True,
              active=1) -> Store:
    store = Store(name=name, website=host, owner_user_id=owner_user_id,
                  is_verified=verified, is_active=active)
    db.add(store)
    db.commit()
    return store


def add_listing(db, store, *, sku, url, product=None, checked=NOW - timedelta(hours=1),
                delisted_at=None) -> ProductAlias:
    if product is None:
        product = Product(canonical_name=f"Product {sku}")
        db.add(product)
        db.flush()
    alias = ProductAlias(product_id=product.id, store_id=store.id,
                         store_product_name=f"Listing {sku}", store_product_id=sku,
                         store_product_url=url, delisted_at=delisted_at)
    db.add(alias)
    db.flush()
    db.add(Price(alias_id=alias.id, price=Decimal("100.000"), checked_at=checked))
    db.commit()
    return alias


def run_main(db, auditor, tmp_path, *args):
    report = tmp_path / "report.json"
    code = audit.main([*args, "--report", str(report)], session_factory=lambda: db,
                      auditor=auditor, now=NOW)
    assert code == 0
    return json.loads(report.read_text(encoding="utf-8"))


def fresh(db, alias_id) -> ProductAlias:
    db.expire_all()
    return db.get(ProductAlias, alias_id)


def audited(auditor, *links):
    auditor.run(list(links))
    return links


def link(url, *listings, store_code="smartbuy"):
    return audit.Link(url=url, store_id=1, store_code=store_code, listings=[
        audit.Listing(alias_id=i + 1, product_id=100 + i, store_product_id=sku)
        for i, sku in enumerate(listings)
    ])


# --- Verdicts -----------------------------------------------------------------


class TestVerdicts:
    def test_same_handle_with_the_variant_is_ok(self, auditor, stores):
        url = f"https://{SB}/products/iphone-16"
        stores.page(url + ".js", product_json(url + ".js", "iphone-16",
                                              [{"id": 11, "sku": "SKU-1"}]))
        (checked,) = audited(auditor, link(url, "SKU-1"))
        assert checked.verdict == audit.OK
        assert checked.listings[0].verdict == audit.OK
        assert checked.http_status == 200

    def test_a_404_is_gone(self, auditor, stores):
        # The live case that started this: product 483's SmartBuy link.
        url = f"https://{SB}/products/abj1501st0307"
        stores.page(url + ".js", not_found(url + ".js"))
        (checked,) = audited(auditor, link(url, "ABJ1501ST0307"))
        assert checked.verdict == audit.GONE
        assert checked.listings[0].verdict == audit.GONE

    def test_a_different_handle_in_the_json_is_renamed(self, auditor, stores):
        url = f"https://{SB}/products/old-name"
        stores.page(url + ".js", product_json(url + ".js", "new-name",
                                              [{"id": 1, "sku": "SKU-1"}]))
        (checked,) = audited(auditor, link(url, "SKU-1"))
        assert checked.verdict == audit.RENAMED
        assert checked.new_url == f"https://{SB}/products/new-name"
        assert checked.listings[0].verdict == audit.RENAMED

    def test_a_redirect_to_another_product_is_renamed(self, auditor, stores):
        url = f"https://{SB}/products/old-name"
        final = f"https://{SB}/products/new-name.js"
        stores.page(url + ".js", product_json(url + ".js", "new-name",
                                              [{"id": 1, "sku": "SKU-1"}],
                                              final_url=final))
        (checked,) = audited(auditor, link(url, "SKU-1"))
        assert checked.verdict == audit.RENAMED
        assert checked.new_url == f"https://{SB}/products/new-name"

    @pytest.mark.parametrize(
        "answer,why",
        [
            (FetchResult("", 429, "", "text/html"), "rate limited"),
            (FetchResult("", 503, "", "text/html"), "server error"),
            (FetchResult("", 403, "", "text/html"), "bot wall"),
            (FetchResult("", 200, "<html>not json</html>", "text/html"), "not JSON"),
            (FetchResult("", 200, "[1, 2]", "application/json"), "JSON, wrong shape"),
            (FetchResult("", 200, '{"handle": "x"}', "application/json"), "no variants"),
            (BlockedURLError("response exceeded 5242880 bytes"), "blocked"),
            (httpx.ReadTimeout("timed out"), "timeout"),
            (ConnectionResetError("reset"), "connection reset"),
        ],
    )
    def test_anything_else_is_unknown(self, auditor, stores, answer, why):
        url = f"https://{SB}/products/iphone-16"
        if isinstance(answer, FetchResult):
            answer = FetchResult(url + ".js", answer.status_code, answer.text,
                                 answer.content_type)
        stores.page(url + ".js", answer)
        (checked,) = audited(auditor, link(url, "SKU-1"))
        assert checked.verdict == audit.UNKNOWN, why
        assert checked.listings[0].verdict == audit.UNKNOWN, why

    def test_a_404_reached_through_a_redirect_is_unknown_not_gone(self, auditor, stores):
        url = f"https://{SB}/products/old-name"
        stores.page(url + ".js", not_found(url + ".js",
                                           final_url=f"https://{SB}/products/other.js"))
        (checked,) = audited(auditor, link(url, "SKU-1"))
        assert checked.verdict == audit.UNKNOWN

    def test_a_redirect_somewhere_that_is_not_a_product_is_unknown(self, auditor, stores):
        url = f"https://{SB}/products/iphone-16"
        stores.page(url + ".js", FetchResult(f"https://{SB}/password", 200,
                                             "<html></html>", "text/html"))
        (checked,) = audited(auditor, link(url, "SKU-1"))
        assert checked.verdict == audit.UNKNOWN

    def test_robots_disallow_is_unknown_and_nothing_is_fetched(self, auditor, stores):
        url = f"https://{SB}/products/iphone-16"
        stores.disallowed.add("/products/iphone-16.js")
        (checked,) = audited(auditor, link(url, "SKU-1"))
        assert checked.verdict == audit.UNKNOWN
        assert [r for r in stores.requests if r[1] != "robots.txt"] == []

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.igeekjo.com/products/x",   # host the scraper does not use
            "http://smartbuy-me.com/products/x",    # not https
            "https://smartbuy-me.com/collections/phones",  # not a product link
        ],
    )
    def test_links_that_cannot_be_fetched_are_unknown_without_a_request(
        self, auditor, stores, url
    ):
        (checked,) = audited(auditor, link(url, "SKU-1"))
        assert checked.verdict == audit.UNKNOWN
        assert stores.requests == []

    @pytest.mark.parametrize("handle", ["../account", "x?y=z", "a/b", "", "evil handle"])
    def test_an_unsafe_handle_from_the_store_is_never_made_into_a_link(
        self, auditor, stores, handle
    ):
        url = f"https://{SB}/products/iphone-16"
        stores.page(url + ".js", product_json(url + ".js", handle,
                                              [{"id": 1, "sku": "SKU-1"}]))
        (checked,) = audited(auditor, link(url, "SKU-1"))
        assert checked.verdict == audit.UNKNOWN
        assert checked.new_url is None


class TestVariantCheck:
    VARIANTS = [{"id": 111, "sku": "6941812790793"}, {"id": 222, "sku": None}]

    @pytest.mark.parametrize(
        "key,expected",
        [
            ("6941812790793", True),     # by SKU
            ("shopify-222", True),       # by variant id, for a variant with no SKU
            ("shopify-999", False),
            ("0000000000000", False),
            ("", None),                  # nothing to look for is not evidence
            (None, None),
        ],
    )
    def test_variant_present(self, key, expected):
        assert audit.variant_present(key, self.VARIANTS) is expected

    def test_one_link_can_be_ok_for_one_listing_and_variant_gone_for_another(
        self, auditor, stores
    ):
        url = f"https://{SB}/products/iphone-16"
        stores.page(url + ".js", product_json(url + ".js", "iphone-16", self.VARIANTS))
        (checked,) = audited(auditor, link(url, "6941812790793", "SOLD-OUT-FOR-GOOD",
                                           "shopify-222"))
        assert [item.verdict for item in checked.listings] == [
            audit.OK, audit.VARIANT_GONE, audit.OK
        ]

    def test_renamed_without_the_variant_is_variant_gone_not_relinked(
        self, auditor, stores
    ):
        # A store redirecting a discontinued product to its successor: the
        # listing's SKU is not in the new product, so its link must not move.
        url = f"https://{SB}/products/iphone-15"
        stores.page(url + ".js", product_json(url + ".js", "iphone-16",
                                              [{"id": 5, "sku": "IPHONE-16-SKU"}]))
        (checked,) = audited(auditor, link(url, "IPHONE-15-SKU"))
        assert checked.verdict == audit.RENAMED
        assert checked.listings[0].verdict == audit.VARIANT_GONE

    def test_renamed_with_no_key_to_check_is_unknown(self, auditor, stores):
        url = f"https://{SB}/products/old"
        stores.page(url + ".js", product_json(url + ".js", "new", [{"id": 5, "sku": "A"}]))
        (checked,) = audited(auditor, link(url, None))
        assert checked.listings[0].verdict == audit.UNKNOWN


# --- Selection ----------------------------------------------------------------


class TestSelection:
    def test_only_current_scraped_listings_are_selected(self, db):
        smartbuy = add_store(db)
        shown = add_listing(db, smartbuy, sku="SHOWN", url=f"https://{SB}/products/shown")
        # Two listings on one URL are one link, not two requests.
        also_shown = add_listing(db, smartbuy, sku="SHOWN-2",
                                 url=f"https://{SB}/products/shown")

        add_listing(db, smartbuy, sku="STALE", url=f"https://{SB}/products/stale",
                    checked=NOW - timedelta(hours=72))
        add_listing(db, smartbuy, sku="DELISTED", url=f"https://{SB}/products/delisted",
                    delisted_at=NOW - timedelta(days=1))
        add_listing(db, smartbuy, sku="NO-URL", url=None)

        merchant = add_store(db, "Phone Shop", None, owner_user_id=7, verified=True)
        add_listing(db, merchant, sku="MERCHANT", url=f"https://{SB}/products/merchant",
                    checked=None)
        closed = add_store(db, "iGeek Megastore", IG, active=0)
        add_listing(db, closed, sku="INACTIVE", url=f"https://{IG}/products/inactive")

        links = audit.select_links(db, NOW)

        assert [item.url for item in links] == [f"https://{SB}/products/shown"]
        assert {item.alias_id for item in links[0].listings} == {shown.id, also_shown.id}
        assert links[0].store_code == "smartbuy"

    def test_store_filter_and_per_store_limit(self, db):
        smartbuy = add_store(db)
        igeek = add_store(db, "iGeek Megastore", IG)
        for n in range(3):
            add_listing(db, smartbuy, sku=f"S{n}", url=f"https://{SB}/products/s{n}")
            add_listing(db, igeek, sku=f"I{n}", url=f"https://{IG}/products/i{n}")

        limited = audit.select_links(db, NOW, limit=2)
        assert sorted(item.url for item in limited) == [
            f"https://{IG}/products/i0", f"https://{IG}/products/i1",
            f"https://{SB}/products/s0", f"https://{SB}/products/s1",
        ]
        only = audit.select_links(db, NOW, store_code="igeek")
        assert {item.store_code for item in only} == {"igeek"}
        assert len(only) == 3

    def test_merchant_and_non_current_links_are_never_fetched_end_to_end(
        self, db, auditor, stores, tmp_path, bumps
    ):
        merchant = add_store(db, "Phone Shop", None, owner_user_id=7, verified=True)
        add_listing(db, merchant, sku="M", url=f"https://{SB}/products/m", checked=None)
        smartbuy = add_store(db)
        add_listing(db, smartbuy, sku="OLD", url=f"https://{SB}/products/old",
                    checked=NOW - timedelta(hours=49))

        report = run_main(db, auditor, tmp_path, "--apply")

        assert stores.requests == []
        assert report["links"] == []
        assert bumps == []


# --- Dry run and --apply ------------------------------------------------------


@pytest.fixture
def catalogue(db, stores):
    """One listing per verdict, with the store answering accordingly."""
    smartbuy = add_store(db)
    rows = {
        "ok": add_listing(db, smartbuy, sku="OK-SKU", url=f"https://{SB}/products/ok"),
        "gone": add_listing(db, smartbuy, sku="GONE-SKU",
                            url=f"https://{SB}/products/abj1501st0307"),
        "renamed": add_listing(db, smartbuy, sku="REN-SKU",
                               url=f"https://{SB}/products/old-name"),
        "variant_gone": add_listing(db, smartbuy, sku="VG-SKU",
                                    url=f"https://{SB}/products/phone"),
        "unknown": add_listing(db, smartbuy, sku="UNK-SKU",
                               url=f"https://{SB}/products/busy"),
    }
    base = f"https://{SB}/products/"
    stores.page(base + "ok.js", product_json(base + "ok.js", "ok", [{"id": 1, "sku": "OK-SKU"}]))
    stores.page(base + "abj1501st0307.js", not_found(base + "abj1501st0307.js"))
    stores.page(base + "old-name.js", product_json(base + "old-name.js", "new-name",
                                                   [{"id": 2, "sku": "REN-SKU"}]))
    stores.page(base + "phone.js", product_json(base + "phone.js", "phone",
                                                [{"id": 3, "sku": "SOMETHING-ELSE"}]))
    stores.page(base + "busy.js", FetchResult(base + "busy.js", 429, "", "text/html"))
    return rows


def snapshot(db):
    db.expire_all()
    return sorted(
        (row.id, row.store_product_url, row.delisted_at)
        for row in db.query(ProductAlias).all()
    )


class TestDryRunAndApply:
    def test_dry_run_changes_nothing(self, db, auditor, catalogue, tmp_path, bumps, capsys):
        gone_product = catalogue["gone"].product_id
        before = snapshot(db)

        report = run_main(db, auditor, tmp_path)

        assert snapshot(db) == before
        assert bumps == []
        assert report["mode"] == "dry-run"
        assert "changes" not in report
        verdicts = {entry["url"].rsplit("/", 1)[1]: entry["listings"][0]["verdict"]
                    for entry in report["links"]}
        assert verdicts == {"ok": "OK", "abj1501st0307": "GONE", "old-name": "RENAMED",
                            "phone": "VARIANT_GONE", "busy": "UNKNOWN"}
        out = capsys.readouterr().out
        assert "DRY RUN: nothing was changed" in out
        assert f"product {gone_product}" in out

    def test_apply_delists_gone_relinks_renamed_and_leaves_unknown_alone(
        self, db, auditor, catalogue, tmp_path, bumps, capsys
    ):
        ids = {name: row.id for name, row in catalogue.items()}
        report = run_main(db, auditor, tmp_path, "--apply")

        gone = fresh(db, ids["gone"])
        assert gone.delisted_at is not None
        assert gone.delisted_at.replace(tzinfo=timezone.utc) == NOW

        assert fresh(db, ids["variant_gone"]).delisted_at is not None

        renamed = fresh(db, ids["renamed"])
        assert renamed.store_product_url == f"https://{SB}/products/new-name"
        assert renamed.delisted_at is None

        unknown = fresh(db, ids["unknown"])
        assert unknown.delisted_at is None
        assert unknown.store_product_url == f"https://{SB}/products/busy"

        ok = fresh(db, ids["ok"])
        assert ok.delisted_at is None
        assert ok.store_product_url == f"https://{SB}/products/ok"

        assert bumps == [1]
        actions = sorted((c["action"], c["alias_id"]) for c in report["changes"])
        assert actions == sorted([("delisted", ids["gone"]),
                                  ("delisted", ids["variant_gone"]),
                                  ("relinked", ids["renamed"])])
        out = capsys.readouterr().out
        assert "Committed 3 change(s)" in out
        assert f"https://{SB}/products/old-name -> https://{SB}/products/new-name" in out

    def test_unknown_is_never_delisted_whatever_the_reason(
        self, db, auditor, stores, tmp_path, bumps
    ):
        """Every flavour of "could not tell" in one run; --apply touches none."""
        smartbuy = add_store(db)
        base = f"https://{SB}/products/"
        answers = {
            "rate-limited": FetchResult(base + "rate-limited.js", 429, "", ""),
            "down": FetchResult(base + "down.js", 503, "", ""),
            "garbled": FetchResult(base + "garbled.js", 200, "<html>", "text/html"),
            "blocked": BlockedURLError("too many redirects"),
            "slow": httpx.ConnectTimeout("timed out"),
        }
        rows = []
        for handle, answer in answers.items():
            rows.append(add_listing(db, smartbuy, sku=handle.upper(), url=base + handle))
            stores.page(base + handle + ".js", answer)
        stores.disallowed.add("/products/robots-says-no.js")
        rows.append(add_listing(db, smartbuy, sku="R", url=base + "robots-says-no"))
        before = snapshot(db)

        report = run_main(db, auditor, tmp_path, "--apply")

        assert {entry["verdict"] for entry in report["links"]} == {"UNKNOWN"}
        assert snapshot(db) == before
        assert report["changes"] == []
        assert bumps == []

    def test_apply_skips_a_row_that_changed_while_it_was_being_audited(
        self, db, auditor, stores
    ):
        smartbuy = add_store(db)
        url = f"https://{SB}/products/gone"
        row = add_listing(db, smartbuy, sku="G", url=url)
        stores.page(url + ".js", not_found(url + ".js"))
        links = audit.select_links(db, NOW)
        auditor.run(links)

        # Meanwhile the worker re-read the store and recorded a new link.
        row.store_product_url = f"https://{SB}/products/moved"
        db.commit()

        changes = audit.apply_changes(db, links, NOW)

        assert [c.action for c in changes] == ["skipped"]
        assert fresh(db, row.id).delisted_at is None

    def test_default_report_is_outside_the_repository(self):
        path = audit.default_report_path(NOW)
        repo = Path(__file__).resolve().parent.parent.parent
        assert path.parent == Path(tempfile.gettempdir())
        assert path.name == "link-audit-20260915T120000Z.json"
        assert repo not in path.resolve().parents


# --- Politeness ---------------------------------------------------------------


def gaps(requests, host):
    times = [t for h, _, t in requests if h == host]
    return [b - a for a, b in zip(times, times[1:])]


class TestThrottle:
    def test_each_host_is_spaced_and_hosts_interleave(self, auditor, stores, clock):
        stores.crawl_delay[IG] = 5.0  # robots.txt asking for more gets more
        links = []
        for n in range(3):
            url = f"https://{SB}/products/s{n}"
            stores.page(url + ".js", product_json(url + ".js", f"s{n}", [{"id": 1, "sku": "X"}]))
            links.append(link(url, "X"))
        for n in range(2):
            url = f"https://{IG}/products/i{n}"
            stores.page(url + ".js", product_json(url + ".js", f"i{n}", [{"id": 1, "sku": "X"}]))
            links.append(link(url, "X", store_code="igeek"))
        start = clock.now

        auditor.run(links)

        # robots.txt + 3 products, and robots.txt + 2 products.
        assert len([r for r in stores.requests if r[0] == SB]) == 4
        assert len([r for r in stores.requests if r[0] == IG]) == 3
        assert all(gap >= 2.0 for gap in gaps(stores.requests, SB))
        assert all(gap >= 5.0 for gap in gaps(stores.requests, IG))
        # End to end the two stores would need 3*2 + 2*5 = 16 s. Interleaved,
        # the run takes as long as the slower store alone.
        assert clock.now - start < 16
        hosts_in_order = [h for h, _, _ in stores.requests]
        assert hosts_in_order != sorted(hosts_in_order, key=hosts_in_order.index)

    def test_the_floor_holds_even_if_a_store_delay_is_lowered(self, stores, clock):
        hasty = audit.LinkAuditor(
            fetch_fn=stores.fetch, rules_fn=stores.rules_for,
            can_fetch_fn=stores.can_fetch, clock=clock.monotonic, sleep=clock.sleep,
            stores=(StoreConfig(code="smartbuy", name="SmartBuy", host=SB,
                                platform="shopify", delay_seconds=0.1),),
            progress=lambda line: None,
        )
        links = []
        for n in range(4):
            url = f"https://{SB}/products/p{n}"
            stores.page(url + ".js", not_found(url + ".js"))
            links.append(link(url, "X"))

        hasty.run(links)

        assert len(gaps(stores.requests, SB)) == 4
        # The literal, not audit.MIN_DELAY_SECONDS: the promise to the stores
        # is two seconds, and a test reading the constant would pass happily
        # if the constant itself were lowered.
        assert min(gaps(stores.requests, SB)) >= 2.0

    def test_a_robots_txt_re_read_mid_run_counts_as_a_request(self, auditor, stores, clock):
        links = []
        for n in range(3):
            url = f"https://{SB}/products/p{n}"
            stores.page(url + ".js", not_found(url + ".js"))
            links.append(link(url, "X"))

        original = stores.fetch

        def fetch_then_expire(url, allowed_hosts, **kwargs):
            # The hour-long robots cache runs out after the second product.
            result = original(url, allowed_hosts, **kwargs)
            if url.endswith("p1.js"):
                stores.expire_robots(SB)
            return result

        auditor._fetch = fetch_then_expire
        auditor.run(links)

        kinds = [what.rsplit("/", 1)[-1] for _, what, _ in stores.requests]
        assert kinds == ["robots.txt", "p0.js", "p1.js", "robots.txt", "p2.js"]
        assert all(gap >= 2.0 for gap in gaps(stores.requests, SB))


class TestGuards:
    """Review round 2: the audit must not double the load, or delist in a panic."""

    def test_refuses_to_start_while_a_scrape_is_in_progress(
        self, db, auditor, catalogue, stores, tmp_path, capsys
    ):
        from app.models.scrape_job import JobStatus, ScrapeJob

        db.add(ScrapeJob(status=JobStatus.running.value, store_codes=""))
        db.commit()
        before = snapshot(db)

        code = audit.main(["--apply", "--report", str(tmp_path / "r.json")],
                          session_factory=lambda: db, auditor=auditor, now=NOW)

        assert code == 2
        assert "scrape job is queued or running" in capsys.readouterr().out
        assert snapshot(db) == before
        assert stores.requests == [], "the stores were asked while a scrape was running"

    def _many_gone(self, db, stores, count, total):
        smartbuy = add_store(db)
        base = f"https://{SB}/products/"
        for n in range(total):
            url = f"{base}item-{n}"
            add_listing(db, smartbuy, sku=f"SKU-{n}", url=url)
            if n < count:
                stores.page(url + ".js", not_found(url + ".js"))
            else:
                stores.page(url + ".js", product_json(url + ".js", f"item-{n}",
                                                      [{"id": n, "sku": f"SKU-{n}"}]))

    def test_apply_refuses_to_delist_a_large_share_without_force(
        self, db, auditor, stores, tmp_path, bumps, capsys
    ):
        self._many_gone(db, stores, count=5, total=10)
        before = snapshot(db)

        code = audit.main(["--apply", "--report", str(tmp_path / "r.json")],
                          session_factory=lambda: db, auditor=auditor, now=NOW)

        assert code == 3
        out = capsys.readouterr().out
        assert "REFUSED" in out and "5 of 10" in out
        assert snapshot(db) == before
        assert bumps == []

    def test_force_applies_them(self, db, auditor, stores, tmp_path, bumps):
        self._many_gone(db, stores, count=5, total=10)

        report = run_main(db, auditor, tmp_path, "--apply", "--force")

        assert sum(1 for c in report["changes"] if c["action"] == "delisted") == 5
        assert bumps == [1]

    def test_a_few_removals_need_no_force(self, db, auditor, stores, tmp_path, bumps):
        self._many_gone(db, stores, count=3, total=10)

        report = run_main(db, auditor, tmp_path, "--apply")

        assert sum(1 for c in report["changes"] if c["action"] == "delisted") == 3
