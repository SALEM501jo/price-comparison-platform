"""
Read the stores' feeds on one machine and ingest them on another.

WHY THIS EXISTS: since 2026-09-30 Shopify answers the production server
(Hetzner, AS24940) with HTTP 429 on roughly nine requests in ten, on every
store at once and however long the worker waits. The same request from a home
connection is answered every time. The worker itself is healthy; it simply
cannot reach its source, so every scheduled scrape failed, prices passed the
48-hour freshness window, and the catalogue fell from ~355 products to 19.

So the two halves are split:

    record   on a machine the feeds answer (the owner's PC). Runs the REAL
             scrapers -- same honest User-Agent, same robots.txt check, same
             delay between requests -- and saves each response to one file.
    replay   on the server, inside the worker container. Runs the REAL job
             (jobs.run_job: ingest, delisting and its safety valve, cache
             version, price alerts) with fetch() answered from that file.

Nothing here disguises the bot or goes around a refusal: record makes exactly
the requests the worker would, as the worker, and stops where it would stop.
What it changes is where they are sent from. No database credential leaves
the server, and no application code is patched on disk -- both modes swap
fetch() in memory for one process.

A response that was not recorded is replayed as HTTP 599, which the scraper
treats like any other failed page: that store's read is incomplete, nothing
of it is delisted, and the job says so.

    python scripts/offsite_scrape.py record feeds.jsonl.gz
    PYTHONPATH=/app python /tmp/offsite_scrape.py replay /tmp/feeds.jsonl.gz
"""

from __future__ import annotations

import gzip
import json
import os
import sys
from datetime import datetime, timezone
from urllib.parse import urlencode

# Run as `python scripts/offsite_scrape.py` from backend/, the app is one
# directory up. In the container the script sits in /tmp and PYTHONPATH says
# where the app is, so this only applies when the app really is beside it.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.isdir(os.path.join(_ROOT, "app")):
    sys.path.insert(0, _ROOT)

# record needs no database, but importing the app reads its settings.
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET_KEY", "x" * 48)

from app.services.scrapers import STORES, get_scraper  # noqa: E402
from app.services.scrapers import http, robots, shopify  # noqa: E402
from app.services.scrapers.base import StoreScraper  # noqa: E402

# Everything ShopifyScraper reads from a product, and nothing else. A page of
# 100 products is ~0.5-1.4 MB, almost all of it descriptions and image lists;
# kept whole, one run is ~150 MB to upload. EVERY PRODUCT IS KEPT, relevant or
# not: an emptied page would read as the end of the feed, and a read that
# ended early and called itself complete is what delists a store.
PRODUCT_KEYS = ("title", "handle", "vendor", "product_type")
VARIANT_KEYS = ("id", "sku", "price", "title", "available")


def _key(url: str, params: dict | None) -> str:
    return f"{url}?{urlencode(sorted(params.items()))}" if params else url


def _slim(text: str) -> str:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text
    products = payload.get("products") if isinstance(payload, dict) else None
    if not isinstance(products, list):
        return text
    slim = []
    for product in products:
        item = {key: product.get(key) for key in PRODUCT_KEYS}
        images = product.get("images") or []
        item["images"] = [{"src": images[0].get("src")}] if images else []
        item["variants"] = [
            {key: variant.get(key) for key in VARIANT_KEYS}
            for variant in product.get("variants") or []
        ]
        slim.append(item)
    return json.dumps({"products": slim}, ensure_ascii=False)


def record(path: str) -> int:
    real_fetch = http.fetch
    saved: dict[str, dict] = {}

    def recording_fetch(url, allowed_hosts, *, params=None, **kwargs):
        result = real_fetch(url, allowed_hosts, params=params, **kwargs)
        # Keyed by request, so a retried page keeps its LAST answer.
        saved[_key(url, params)] = {
            "url": result.url,
            "status_code": result.status_code,
            "text": _slim(result.text),
            "content_type": result.content_type,
        }
        return result

    shopify.fetch = robots.fetch = recording_fetch

    all_complete = True
    for config in STORES:
        scraper = get_scraper(config)
        kept = sum(1 for _ in scraper.scrape())
        all_complete &= scraper.feed.complete
        print(
            f"{config.name}: {kept} listings kept, "
            f"{'complete' if scraper.feed.complete else 'INCOMPLETE: ' + str(scraper.feed.reason)}",
            flush=True,
        )

    with gzip.open(path, "wt", encoding="utf-8") as out:
        for key, entry in saved.items():
            out.write(json.dumps({"key": key, **entry}, ensure_ascii=False) + "\n")
    print(f"{len(saved)} responses -> {path} ({os.path.getsize(path) // 1024} KB)")
    return 0 if all_complete else 1


def replay(path: str) -> int:
    with gzip.open(path, "rt", encoding="utf-8") as source:
        saved = {entry["key"]: entry for entry in map(json.loads, source)}

    def replayed_fetch(url, allowed_hosts, *, params=None, **kwargs):
        entry = saved.get(_key(url, params))
        if entry is None:
            return http.FetchResult(url=url, status_code=599, text="", content_type="")
        return http.FetchResult(
            url=entry["url"],
            status_code=entry["status_code"],
            text=entry["text"],
            content_type=entry["content_type"],
        )

    shopify.fetch = robots.fetch = replayed_fetch
    # The delay is owed to the store's server, and nothing here reaches it.
    StoreScraper.throttle = lambda self, minimum=None: None

    from app.database import SessionLocal
    from app.models.scrape_job import JobStatus, ScrapeJob
    from app.services import jobs

    db = SessionLocal()
    try:
        # Born `running`, never `queued`: the worker claims queued rows, and it
        # would run this one against the live feeds and fail it.
        job = ScrapeJob(
            status=JobStatus.running.value,
            # Named explicitly, so SCRAPE_STORES (which limits FULL runs to the
            # stores the server can reach) does not drop what was recorded.
            store_codes=",".join(store.code for store in STORES),
            started_at=datetime.now(timezone.utc),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        jobs.run_job(db, job)
        db.refresh(job)
        print(f"job {job.id}: {job.status}")
        print(f"result: {job.result}")
        if job.error:
            print(f"error: {job.error}")
        return 0 if job.status == JobStatus.succeeded.value else 1
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in {"record", "replay"}:
        sys.exit(__doc__)
    sys.exit({"record": record, "replay": replay}[sys.argv[1]](sys.argv[2]))
