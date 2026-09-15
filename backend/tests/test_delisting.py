"""
Listings a store removed leave the site; listings it merely failed to show us do not.

THE BUG: a listing a store takes down simply stops appearing in its feed, and
nothing noticed. Its last price stayed in every comparison and could win "best
price" beside a "Visit store" link to a 404 -- live on 2026-09-15, iPhone 16
128GB at SmartBuy, 689 JOD, while its product page answered Not Found.

THE DANGER IN THE FIX: absence is only evidence of removal when the read saw
everything. A scraper that stopped on page two -- a 403, a page over the size
cap, a feed that stopped being JSON -- is missing listings too, and delisting
on that would take half a store off the site because its server hiccuped. So
most of what follows is about the read being COMPLETE, and about exactly whose
listings a read may speak for.

Driven through the real ShopifyScraper and IngestService with the network
replaced by a fake feed: the completeness logic lives in the scraper's paging
loop, and a fake scraper would test a copy of it.
"""

import json
from dataclasses import replace
from datetime import datetime, timezone

import httpx
import pytest

from app.models.alias import ProductAlias
from app.models.price import Price
from app.models.scrape_job import JobStatus
from app.models.store import Store
from app.models.user import User, UserRole
from app.services import jobs
from app.services.deduplication import DeduplicationEngine
from app.services.ingest import IngestService
from app.services.offers import current_offer
from app.services.scrapers import STORES, BlockedURLError
from app.services.scrapers.base import StoreConfig, StoreScraper
from app.services.scrapers.http import FetchResult
from app.services.scrapers.robots import RobotRules
from app.services.scrapers.shopify import ShopifyScraper

CONFIG = StoreConfig(
    code="smartbuy", name="SmartBuy", host="smartbuy-me.com", platform="shopify"
)


def phone(n, sku, title, price="899.000", handle=None):
    """One product exactly as /products.json lists it."""
    return {
        "id": n,
        "title": title,
        "handle": handle or sku.lower(),
        "vendor": "Apple",
        "product_type": "Smart Phone",
        "images": [],
        "variants": [
            {"id": 1000 + n, "sku": sku, "price": price, "available": True,
             "title": "Default Title"}
        ],
    }


A = phone(1, "SB-1", "Apple iPhone 15 128GB 5G Smartphone - Black")
B = phone(2, "SB-2", "Apple iPhone 15 256GB 5G Smartphone - Blue")
C = phone(3, "SB-3", "Apple iPhone 16 128GB 5G Smartphone - Black", price="689.000")


def response(body, status=200):
    return FetchResult(
        url="https://smartbuy-me.com/products.json",
        status_code=status,
        text=body if isinstance(body, str) else json.dumps(body),
        content_type="application/json",
    )


class Flaky:
    """A page that answers with each of `first` in turn, then with `then`."""

    def __init__(self, first, then):
        self.first = list(first)
        self.then = then

    def next(self):
        return self.first.pop(0) if self.first else self.then


class FakeFeed:
    """
    The store's /products.json, page by page.

    Each page is a list of products, a FetchResult, or an exception to raise.
    Every page past the last is empty -- the true end of a Shopify feed.
    """

    def __init__(self):
        self.pages = []
        self.requests = []
        # URL fragments robots.txt refuses.
        self.refused = ()

    def serve(self, *pages):
        self.pages = list(pages)
        self.requests = []

    def fetch(self, url, allowed_hosts, *, params=None, timeout=None):
        self.requests.append(params["page"])
        index = params["page"] - 1
        if index >= len(self.pages):
            return response({"products": []})
        page = self.pages[index]
        if isinstance(page, Flaky):
            page = page.next()
        if isinstance(page, BaseException):
            raise page
        if isinstance(page, FetchResult):
            return page
        return response({"products": page})


@pytest.fixture
def feed(monkeypatch):
    fake = FakeFeed()
    monkeypatch.setattr("app.services.scrapers.shopify.fetch", fake.fetch)
    monkeypatch.setattr(
        "app.services.scrapers.shopify.can_fetch",
        lambda url, hosts: not any(part in url for part in fake.refused),
    )
    monkeypatch.setattr(
        "app.services.scrapers.shopify.rules_for", lambda url, hosts: RobotRules()
    )
    # Politeness is real in production and pointless against a fake.
    monkeypatch.setattr(StoreScraper, "throttle", lambda self, minimum=None: None)
    monkeypatch.setattr("app.services.scrapers.shopify.time.sleep", lambda seconds: None)
    return fake


# How a read can stop short, each as the fake feed serves it after a good
# page one. Every one of these used to be a quiet `break`.
FAILURES = {
    "http error": response("Service Unavailable", status=503),
    "page over the size cap": BlockedURLError("response exceeded 5242880 bytes"),
    "not JSON": response("<html>Checking your browser</html>"),
    "JSON of the wrong shape": response([{"products": []}]),
}
REASONS = {
    "http error": "HTTP 503",
    "page over the size cap": "exceeded",
    "not JSON": "not valid JSON",
    "JSON of the wrong shape": "no product list",
}


def read(feed, *pages, config=CONFIG):
    """Run the real scraper over the fake feed; return (items, scraper)."""
    feed.serve(*pages)
    scraper = ShopifyScraper(config, {config.host})
    return list(scraper.scrape()), scraper


# --- The scraper knows whether it read everything --------------------------


class TestTheScraperSaysWhetherItReadEverything:
    def test_a_feed_read_to_its_empty_page_is_complete(self, feed):
        items, scraper = read(feed, [A, B], [C])

        assert [i.store_product_id for i in items] == ["SB-1", "SB-2", "SB-3"]
        assert scraper.feed.complete is True
        assert scraper.feed.reason is None
        assert feed.requests == [1, 2, 3], "the read must reach the empty page"

    def test_nothing_is_complete_before_it_is_read(self):
        assert ShopifyScraper(CONFIG, {CONFIG.host}).feed.complete is False

    def test_a_read_abandoned_part_way_is_not_complete(self, feed):
        feed.serve([A, B], [C])
        scraper = ShopifyScraper(CONFIG, {CONFIG.host})
        stream = scraper.scrape()
        next(stream)
        stream.close()

        assert scraper.feed.complete is False

    @pytest.mark.parametrize("how", sorted(FAILURES))
    def test_a_read_that_stops_early_is_incomplete_and_says_why(
        self, feed, caplog, how
    ):
        with caplog.at_level("ERROR", logger="app.scraper"):
            items, scraper = read(feed, [A, B], FAILURES[how], [C])

        # What was read is still used -- those prices are real...
        assert [i.store_product_id for i in items] == ["SB-1", "SB-2"]
        # ...but the read does not claim to be the whole store.
        assert scraper.feed.complete is False
        assert REASONS[how] in scraper.feed.reason
        assert "page 2" in scraper.feed.reason
        # And never silently.
        logged = [r for r in caplog.records if "incomplete" in r.getMessage()]
        assert logged and REASONS[how] in logged[0].target

    def test_a_robots_refusal_is_incomplete(self, feed):
        feed.refused = ("/products.json",)
        items, scraper = read(feed, [A, B])

        assert items == []
        assert scraper.feed.complete is False
        assert "robots.txt" in scraper.feed.reason

    def test_hitting_the_runaway_bound_is_incomplete(self, feed):
        items, scraper = read(feed, [A, B, C], config=replace(CONFIG, max_products=2))

        assert len(items) == 2
        assert scraper.feed.complete is False
        assert "max_products=2" in scraper.feed.reason

    def test_exactly_the_bound_still_reads_complete(self, feed):
        """The guard is for MORE than the bound, not for a store at it."""
        items, scraper = read(feed, [A, B, C], config=replace(CONFIG, max_products=3))

        assert len(items) == 3
        assert scraper.feed.complete is True

    def test_a_feed_that_never_ends_is_given_up_on(self, feed, monkeypatch):
        """
        A feed answering every page number with the same products: repeats
        are de-duplicated, so max_products would never trip and the loop
        would never end.
        """
        monkeypatch.setattr("app.services.scrapers.shopify.MAX_PAGES", 5)
        items, scraper = read(feed, *([[A]] * 50))

        assert len(items) == 1
        assert len(feed.requests) == 5
        assert scraper.feed.complete is False
        assert "5 pages" in scraper.feed.reason

    def test_no_registered_store_is_capped_near_its_real_size(self):
        """
        Measured 2026-09-15: 158, 284 and 110 kept variants. A cap near those
        numbers is what left the oldest listings unread; the bound is a
        runaway guard now.
        """
        assert all(store.max_products >= 1000 for store in STORES)


# --- Delisting --------------------------------------------------------------


def run(db, feed, *pages, config=CONFIG):
    feed.serve(*pages)
    return IngestService(db).run_store(config)


def alias(db, sku, store_name="SmartBuy"):
    return (
        db.query(ProductAlias)
        .join(Store, ProductAlias.store_id == Store.id)
        .filter(Store.name == store_name, ProductAlias.store_product_id == sku)
        .one()
    )


def delisted(db, sku, store_name="SmartBuy"):
    row = alias(db, sku, store_name)
    db.refresh(row)
    return row.delisted_at is not None


class TestACompleteReadDelists:
    def test_what_the_store_removed_is_delisted_and_the_rest_kept(self, db, feed):
        run(db, feed, [A, B, C])
        result = run(db, feed, [A, B])

        assert result["complete"] is True
        assert result["delisted"] == 1
        assert delisted(db, "SB-3")
        assert not delisted(db, "SB-1")
        assert not delisted(db, "SB-2")

    def test_a_removed_listing_is_no_longer_an_offer(self, db, feed):
        """The live case: the 689 JOD iPhone 16 must stop being best price."""
        run(db, feed, [A, B, C])
        run(db, feed, [A, B])

        offered = {
            row.store_product_id
            for row in db.query(ProductAlias)
            .join(Price, Price.alias_id == ProductAlias.id)
            .join(Store, ProductAlias.store_id == Store.id)
            .filter(current_offer())
            .all()
        }
        assert offered == {"SB-1", "SB-2"}

    def test_the_date_it_went_is_kept_on_later_runs(self, db, feed):
        run(db, feed, [A, B, C])
        run(db, feed, [A, B])
        first = alias(db, "SB-3").delisted_at

        result = run(db, feed, [A, B])
        db.refresh(alias(db, "SB-3"))

        assert result["delisted"] == 0
        assert alias(db, "SB-3").delisted_at == first

    def test_the_aliases_are_kept_not_deleted(self, db, feed):
        """Price history and wishlists hang off the alias."""
        run(db, feed, [A, B, C])
        run(db, feed, [A, B])
        assert db.query(ProductAlias).count() == 3


class TestAnIncompleteReadDelistsNothing:
    @pytest.mark.parametrize("how", sorted(FAILURES))
    def test_a_read_that_stopped_early(self, db, feed, how):
        run(db, feed, [A, B], [C])
        # C lives on page two, which this time does not arrive.
        result = run(db, feed, [A, B], FAILURES[how])

        assert result["complete"] is False
        assert REASONS[how] in result["incomplete_reason"]
        assert result["delisted"] == 0
        assert not delisted(db, "SB-3")

    def test_a_read_stopped_by_the_runaway_bound(self, db, feed):
        run(db, feed, [A, B, C])
        result = run(db, feed, [A, B, C], config=replace(CONFIG, max_products=2))

        assert result["complete"] is False
        assert result["delisted"] == 0
        assert not delisted(db, "SB-3")

    def test_a_robots_refusal_of_one_target(self, db, feed):
        """One collection read, one refused: listings seen, yet not all of them."""
        config = replace(CONFIG, collections=("phones", "laptops"))
        run(db, feed, [A, B, C], config=config)

        feed.refused = ("/collections/laptops/",)
        result = run(db, feed, [A, B], config=config)

        assert result["seen"] == 2
        assert result["complete"] is False
        assert "robots.txt" in result["incomplete_reason"]
        assert result["delisted"] == 0
        assert not delisted(db, "SB-3")

    def test_a_read_that_raised(self, db, feed):
        """A connection error escapes run_store; nothing after it runs."""
        run(db, feed, [A, B], [C])
        with pytest.raises(httpx.ConnectTimeout):
            run(db, feed, [A, B], httpx.ConnectTimeout("store did not answer"))

        assert not delisted(db, "SB-3")

    def test_a_complete_read_of_nothing(self, db, feed):
        """An empty page one is a fault at the store, not an empty store."""
        run(db, feed, [A, B, C])
        result = run(db, feed)

        assert result["complete"] is True and result["seen"] == 0
        assert result["delisted"] == 0
        assert not any(delisted(db, sku) for sku in ("SB-1", "SB-2", "SB-3"))


class TestRelisting:
    def test_a_listing_that_comes_back_is_relisted(self, db, feed):
        run(db, feed, [A, B, C])
        run(db, feed, [A, B])
        assert delisted(db, "SB-3")

        result = run(db, feed, [A, B, C])

        assert result["relisted"] == 1
        assert not delisted(db, "SB-3")

    def test_a_partial_read_that_finds_it_still_relists_it(self, db, feed):
        """Finding a listing proves the store sells it, however the read ended."""
        run(db, feed, [A, B, C])
        run(db, feed, [A, B])

        result = run(db, feed, [C], response("", status=429))

        assert result["complete"] is False
        assert result["relisted"] == 1
        assert not delisted(db, "SB-3")


class TestWhoseListingsAReadSpeaksFor:
    def _other_store(self, db, name, sku, owner=None, gone=False):
        """A listing at another store, created the way its own path would."""
        store = Store(name=name, website=None, is_verified=True, owner_user_id=owner)
        db.add(store)
        db.commit()
        _product, row, _new = DeduplicationEngine(db).process_new_product(
            store_id=store.id,
            store_product_name=f"Samsung Galaxy S24 128GB 5G - Graphite {sku}",
            store_product_id=sku,
            category="Smart Phone",
        )
        db.add(Price(alias_id=row.id, price=500))
        if gone:
            row.delisted_at = datetime(2026, 9, 1, tzinfo=timezone.utc)
        db.commit()
        return row

    def test_another_stores_listings_are_untouched(self, db, feed):
        """
        SmartBuy's feed says nothing about iGeek. SKU strings are not unique
        across stores either: iGeek's "SB-3" is not SmartBuy's.
        """
        self._other_store(db, "iGeek Megastore", "SB-3")
        # And a listing AmmanCart removed stays removed, even though
        # SmartBuy's feed carries the same SKU string.
        self._other_store(db, "AmmanCart", "SB-1", gone=True)

        run(db, feed, [A, B, C])
        run(db, feed, [A, B])

        assert delisted(db, "SB-3", "SmartBuy")
        assert not delisted(db, "SB-3", "iGeek Megastore")
        assert delisted(db, "SB-1", "AmmanCart")

    def test_a_merchants_listings_are_never_delisted(self, db, feed):
        """
        Nothing reads a merchant's feed, so no read can show a listing gone --
        including a merchant store that shares a registry entry's name, which
        is the one way a scraper run can reach one.
        """
        owner = User(email="shop@example.com", role=UserRole.merchant)
        db.add(owner)
        db.commit()
        self._other_store(db, "SmartBuy", "M-1", owner=owner.id)

        result = run(db, feed, [A])

        assert result["complete"] is True
        assert result["delisted"] == 0
        assert not delisted(db, "M-1", "SmartBuy")


class TestWhatStillCountsAsSeen:
    def test_a_listing_that_failed_to_ingest_is_not_delisted(
        self, db, feed, monkeypatch
    ):
        """It was in the feed. A bug of ours is not the store removing it."""
        run(db, feed, [A, B, C])

        original = DeduplicationEngine.process_new_product

        def breaks_on_sb3(self, **kwargs):
            if kwargs.get("store_product_id") == "SB-3":
                raise RuntimeError("one malformed listing")
            return original(self, **kwargs)

        monkeypatch.setattr(DeduplicationEngine, "process_new_product", breaks_on_sb3)
        result = run(db, feed, [A, B, C])

        assert result["failed"] == 1
        assert result["complete"] is True
        assert result["delisted"] == 0
        assert not delisted(db, "SB-3")

    def test_a_listing_whose_sku_changed_is_not_delisted(self, db, feed):
        """
        The dedup engine matches a changed SKU under an unchanged name to the
        existing alias, which keeps the old SKU. Judged by SKU alone, the
        listing just re-read would look removed.
        """
        run(db, feed, [A, B])
        renumbered = phone(1, "SB-1-NEW", A["title"])
        result = run(db, feed, [renumbered, B])

        assert db.query(ProductAlias).count() == 2
        assert result["delisted"] == 0
        assert not delisted(db, "SB-1")


# --- The job ----------------------------------------------------------------


@pytest.fixture
def job_run(db, feed, monkeypatch):
    """run_job over the real ingest path, with alerts and Redis replaced."""
    calls = {"alerts": 0}

    def process_alerts(session):
        calls["alerts"] += 1
        return {"checked": 0, "notified": 0}

    monkeypatch.setattr("app.services.scrapers.STORES", (CONFIG,))
    monkeypatch.setattr("app.services.notifications.process_alerts", process_alerts)
    monkeypatch.setattr("app.services.cache.bump_catalogue_version_sync", lambda: None)

    def go(*pages):
        feed.serve(*pages)
        jobs.enqueue(db)
        job = jobs.claim_next(db)
        jobs.run_job(db, job)
        db.refresh(job)
        return job

    go.calls = calls
    return go


class TestTheJobFailsAnIncompleteRead:
    def test_an_incomplete_read_is_a_failed_store(self, db, job_run):
        job_run([A, B], [C])
        job = job_run([A, B], response("Too Many Requests", status=429))

        # The only store failed, so the job did.
        assert job.status == JobStatus.failed.value
        assert "SmartBuy: feed read incomplete:" in job.error
        assert "HTTP 429" in job.error
        assert not delisted(db, "SB-3")

    def test_alerts_are_held_back_while_a_read_is_incomplete(
        self, db, job_run, monkeypatch
    ):
        """A second, healthy store keeps the job succeeded; alerts still wait."""

        def run_store(self, config):
            if config.code == "down":
                return {"store": "Down", "seen": 5, "complete": False,
                        "incomplete_reason": "page 3: HTTP 403"}
            return {"store": "Up", "seen": 5, "complete": True}

        monkeypatch.setattr(
            "app.services.scrapers.STORES",
            (replace(CONFIG, code="up", name="Up"), replace(CONFIG, code="down", name="Down")),
        )
        monkeypatch.setattr("app.services.ingest.IngestService.run_store", run_store)
        job = job_run()

        assert job.status == JobStatus.succeeded.value
        assert "FAILED Down: feed read incomplete: page 3: HTTP 403" in job.result
        assert "alerts skipped" in job.result
        assert job_run.calls["alerts"] == 0

    def test_a_complete_read_succeeds_and_sends_alerts(self, db, job_run):
        job = job_run([A, B], [C])

        assert job.status == JobStatus.succeeded.value
        assert "FAILED" not in job.result
        assert job_run.calls["alerts"] == 1


# --- Review round 2: retries, the safety valve, ingest failures, alerts -----


D = phone(4, "SB-4", "Samsung Galaxy S24 128GB 5G - Graphite", price="749.000")


class TestATransientFaultIsAskedAgain:
    """
    A full read is ~140 requests. One 429 or timeout among them used to fail
    the store and hold everyone's alerts back for the run.
    """

    @pytest.mark.parametrize(
        "fault",
        [response("Too Many Requests", status=429), response("Bad Gateway", status=502),
         httpx.ReadTimeout("slow")],
        ids=["429", "502", "timeout"],
    )
    def test_a_page_that_fails_once_is_retried_and_the_read_completes(self, feed, fault):
        items, scraper = read(feed, [A], Flaky([fault], [B]))

        assert [i.store_product_id for i in items] == ["SB-1", "SB-2"]
        assert scraper.feed.complete is True
        assert feed.requests == [1, 2, 2, 3]

    def test_a_fault_that_persists_still_ends_the_read(self, feed):
        items, scraper = read(feed, [A], response("Service Unavailable", status=503), [B])

        assert scraper.feed.complete is False
        assert feed.requests == [1, 2, 2, 2], "two retries, then give up"

    def test_a_blocked_page_is_not_retried(self, feed):
        items, scraper = read(feed, [A], BlockedURLError("response exceeded 5242880 bytes"))

        assert scraper.feed.complete is False
        assert feed.requests == [1, 2]

    def test_robots_counts_as_a_request_for_spacing(self, monkeypatch):
        """The first page used to go out 0.7 s after robots.txt."""
        calls = []
        monkeypatch.setattr(
            "app.services.scrapers.shopify.rules_for",
            lambda url, hosts: calls.append("robots") or RobotRules(),
        )
        monkeypatch.setattr("app.services.scrapers.shopify.can_fetch", lambda u, h: True)
        stamps = []
        real_throttle = StoreScraper.throttle

        def spy(self, minimum=None):
            stamps.append(self._last_request_at)

        monkeypatch.setattr(StoreScraper, "throttle", spy)
        monkeypatch.setattr(
            "app.services.scrapers.shopify.fetch",
            lambda url, hosts, params=None, timeout=None: response({"products": []}),
        )
        scraper = ShopifyScraper(CONFIG, {CONFIG.host})
        list(scraper.scrape())

        assert calls == ["robots"]
        assert stamps and stamps[0] > 0.0, "the first page did not wait after robots.txt"
        assert real_throttle is not None


@pytest.fixture
def tiny_valve(monkeypatch):
    """The valve's numbers scaled to a four-listing store."""
    monkeypatch.setattr("app.services.ingest.MASS_DELIST_FLOOR", 1)
    monkeypatch.setattr("app.services.ingest.MASS_DELIST_SHARE", 0.25)


class TestTheSafetyValve:
    def test_a_read_that_would_remove_too_much_removes_nothing_fresh(
        self, db, feed, tiny_valve
    ):
        run(db, feed, [A, B, C, D])
        result = run(db, feed, [A, B])  # half the store "gone" at once

        assert result["complete"] is True
        assert "would delist 2 of 4" in result["delist_refused"]
        assert not delisted(db, "SB-3") and not delisted(db, "SB-4")

    def test_a_small_removal_goes_through(self, db, feed, tiny_valve):
        run(db, feed, [A, B, C, D])
        result = run(db, feed, [A, B, C])

        assert "delist_refused" not in result
        assert delisted(db, "SB-4")

    def test_offers_already_stale_are_still_delisted(self, db, feed, monkeypatch):
        """Invisible anyway -- and it is what ends a refusal on its own."""
        monkeypatch.setattr("app.services.ingest.MASS_DELIST_FLOOR", 0)
        monkeypatch.setattr("app.services.ingest.MASS_DELIST_SHARE", 0.0)
        run(db, feed, [A, B, C, D])
        old = datetime(2026, 8, 1, tzinfo=timezone.utc)
        price = db.query(Price).filter(Price.alias_id == alias(db, "SB-3").id).one()
        price.checked_at = old
        price.last_updated = old
        db.commit()

        result = run(db, feed, [A, B])

        assert "delist_refused" in result
        assert delisted(db, "SB-3"), "a stale unseen listing should go"
        assert not delisted(db, "SB-4"), "a fresh one is protected"


class TestIngestFailuresRemoveNothing:
    def test_a_read_whose_listings_mostly_failed_delists_nothing(
        self, db, feed, monkeypatch
    ):
        run(db, feed, [A, B, C])

        def broken(self, store, item):
            raise RuntimeError("matching bug")

        monkeypatch.setattr(IngestService, "_ingest", broken)
        result = run(db, feed, [A])

        assert result["failed"] == 1 and result["seen"] == 1
        assert not delisted(db, "SB-2") and not delisted(db, "SB-3")


class TestTheJobReportsWhatItHeldBack:
    def test_mostly_failed_ingest_fails_the_store(self, db, job_run, monkeypatch):
        def broken(self, store, item):
            raise RuntimeError("matching bug")

        monkeypatch.setattr(IngestService, "_ingest", broken)
        job = job_run([A, B], [C])

        assert job.status == JobStatus.failed.value
        assert "3 of 3 listings failed to ingest" in job.error

    def test_a_refused_delisting_fails_the_store(self, db, job_run, tiny_valve):
        job_run([A, B, C, D])
        job_run.calls["alerts"] = 0
        job = job_run([A, B])

        assert job.status == JobStatus.failed.value
        assert "would delist 2 of 4" in job.error
        assert job_run.calls["alerts"] == 0

    def test_a_one_store_run_sends_no_alerts(self, db, feed, job_run):
        """An admin's ?store= proves nothing about the other stores."""
        feed.serve([A, B], [C])
        jobs.enqueue(db, ["smartbuy"])
        job = jobs.claim_next(db)
        jobs.run_job(db, job)
        db.refresh(job)

        assert job.status == JobStatus.succeeded.value
        assert "alerts skipped: not every store was read" in job.result
        assert job_run.calls["alerts"] == 0
