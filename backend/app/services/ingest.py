"""
Ingest pipeline: store listings -> canonical products -> prices.

Sits between the scrapers (which know how to read one store) and the
deduplication engine (which knows whether two listings are the same product).
Neither knows about the other, which is what lets a new store be added without
touching the matching logic, and the matching rules to change without touching
any scraper.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import inspect
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.matching import parse
from app.models.alias import ProductAlias
from app.models.price import Price, PriceHistory
from app.models.store import Store
from app.services.deduplication import DeduplicationEngine
from app.services.offers import freshness_cutoff
from app.services.scrapers import STORES, ScrapedProduct, StoreConfig, get_scraper

logger = logging.getLogger("app.scraper")

# See IngestService._reconcile_listings: one run may delist at most this share
# of a store's currently shown offers, and never fewer than the floor.
MASS_DELIST_SHARE = 0.25
MASS_DELIST_FLOOR = 25


class IngestService:
    """Runs scrapers and folds their output into the catalogue."""

    def __init__(self, db: Session):
        self.db = db
        self.dedup = DeduplicationEngine(db)

    def _get_or_create_store(self, config: StoreConfig) -> Store:
        store = self.db.query(Store).filter(Store.name == config.name).first()
        if not store:
            store = Store(name=config.name, website=config.host)
            self.db.add(store)
            self.db.commit()
            self.db.refresh(store)
        return store

    def ingest_one(self, store: Store, item: ScrapedProduct) -> bool:
        """
        Fold one listing into the catalogue. Returns True if a price changed.

        The store's own category is passed to the parser as a hint: real titles
        frequently omit what the product IS ("Hp Intel I7 -8550U, 16GB DDR4 &
        512GB SSD") while the store files it under "Notebook".
        """
        changed, _alias_id = self._ingest(store, item)
        return changed

    def _ingest(self, store: Store, item: ScrapedProduct) -> tuple[bool, int]:
        """ingest_one, also returning the id of the alias the listing landed on."""
        parsed = parse(item.name, hint=item.category)

        product, alias, _is_new = self.dedup.process_new_product(
            store_id=store.id,
            store_product_name=item.name,
            store_product_id=item.store_product_id,
            store_product_url=item.url,
            brand=(item.brand or "").lower() or parsed.get("brand"),
            category=item.category,
        )

        # THE FEED'S URL WINS. The alias kept the URL it was created with, and
        # nothing changed it after: a store that renames a product's handle
        # moves its page, so the "Visit store" link went on pointing at the old
        # address -- the 404 this whole comparison exists to spare a shopper.
        # Committed with the price below.
        if item.url and alias.store_product_url != item.url:
            alias.store_product_url = item.url

        existing = self.db.query(Price).filter(Price.alias_id == alias.id).first()
        changed = False

        # Convert through str, not float: Decimal(0.1) captures the binary
        # approximation, Decimal("0.1") is exact. The feed gives us decimal
        # strings, so this round-trips the value the store actually quoted.
        price = Decimal(str(item.price))
        delivery = Decimal(str(item.delivery_cost))
        # Stamped on every read, unchanged prices included -- see
        # Price.checked_at for why last_updated cannot carry this.
        checked = datetime.now(timezone.utc)

        if existing:
            if existing.price != price:
                # Record the OLD price before overwriting it -- that is what
                # makes the history a series rather than a single point.
                self.db.add(PriceHistory(alias_id=alias.id, price=existing.price))
                changed = True
            existing.price = price
            existing.availability = item.availability
            existing.delivery_cost = delivery

            # Stamping checked_at makes the row dirty, and an UPDATE fills
            # last_updated from its onupdate=now() -- which would mark every
            # price "changed" every run. When nothing the shopper sees has
            # changed, last_updated is put in the UPDATE with its own value;
            # onupdate only fills columns the statement leaves out.
            state = inspect(existing)
            moved = any(
                state.attrs[name].history.has_changes()
                for name in ("price", "availability", "delivery_cost")
            )
            if not moved:
                flag_modified(existing, "last_updated")
            existing.checked_at = checked
        else:
            self.db.add(
                Price(
                    alias_id=alias.id,
                    price=price,
                    currency=item.currency,
                    availability=item.availability,
                    delivery_cost=delivery,
                    checked_at=checked,
                )
            )

        if item.image_url and not product.image_url:
            product.image_url = item.image_url

        # Taken before the commit, which expires the alias: reading .id after
        # it would cost a SELECT per listing to learn a number already known.
        alias_id = alias.id
        self.db.commit()
        return changed, alias_id

    def run_store(self, config: StoreConfig) -> dict:
        """
        Scrape one store, ingest everything it yields, and delist what it no
        longer lists.

        The result says whether the read was complete; jobs.run_job fails a
        store whose read was not.
        """
        store = self._get_or_create_store(config)
        scraper = get_scraper(config)

        seen = 0
        changed = 0
        failed = 0
        # What the feed contained, recorded two ways. By the store's own id,
        # added BEFORE ingesting, so a listing that fails to ingest below still
        # counts as present -- it was in the feed, and a bug of ours is not the
        # store removing it. And by the alias each listing landed on, because a
        # store can change a listing's SKU and keep its name: the dedup engine
        # matches that to the existing alias by name, the alias keeps the old
        # SKU, and by SKU alone a listing just re-read would look removed.
        seen_ids: set[str] = set()
        seen_alias_ids: set[int] = set()

        for item in scraper.scrape():
            seen += 1
            seen_ids.add(item.store_product_id)
            try:
                price_changed, alias_id = self._ingest(store, item)
            except Exception:
                # One malformed listing must not abandon the rest of the run.
                failed += 1
                self.db.rollback()
                logger.error(
                    "Failed to ingest listing",
                    exc_info=True,
                    extra={
                        "action": "ingest_item",
                        "target": item.store_product_id,
                        "success": False,
                    },
                )
                continue
            seen_alias_ids.add(alias_id)
            if price_changed:
                changed += 1

        # Read only now: the scraper decides completeness when its iteration
        # ends, and an exception out of scrape() skips all of this -- that run
        # delists nothing and the job records the store as failed.
        feed = scraper.feed

        # A COMPLETE READ OF NOTHING DELISTS NOTHING. No store on the registry
        # has an empty catalogue, and run_job already fails a store that
        # yields none; a feed answering page one with an empty list is a fault
        # at the store's end, and believing it would take every listing the
        # store has off the site in a single run.
        #
        # NOR DOES A READ WHOSE LISTINGS MOSTLY FAILED TO INGEST. Those were in
        # the feed, but their alias ids were never recorded, so a listing the
        # dedup engine merged by name would look absent and be delisted while
        # the store still sells it. A bug of ours must not remove offers.
        mostly_failed = seen > 0 and failed * 2 > seen
        delisted, relisted, refused = self._reconcile_listings(
            store,
            seen_ids,
            seen_alias_ids,
            delist_unseen=feed.complete and seen > 0 and not mostly_failed,
        )

        result = {"store": config.name, "seen": seen, "price_changes": changed,
                  "failed": failed, "complete": feed.complete,
                  "delisted": delisted, "relisted": relisted}
        if not feed.complete:
            result["incomplete_reason"] = feed.reason
        if refused:
            result["delist_refused"] = refused
        logger.info(
            "Store ingested",
            extra={
                "action": "ingest_store",
                "target": str(result),
                "success": feed.complete,
            },
        )
        return result

    def _reconcile_listings(
        self,
        store: Store,
        seen_ids: set[str],
        seen_alias_ids: set[int],
        *,
        delist_unseen: bool,
    ) -> tuple[int, int, str | None]:
        """
        Bring ProductAlias.delisted_at in line with one read. Returns
        (delisted, relisted, refused) -- `refused` says why a mass delisting
        was held back, or None.

        A listing the read contained is listed, whether or not the read was
        complete: finding it at all proves the store sells it, so a product
        republished comes back on the first read that finds it. A listing it
        did not contain is delisted only when `delist_unseen` -- a complete
        read. From a partial read its absence proves nothing.

        "Not contained" includes a listing the scraper no longer KEEPS -- one
        that stopped passing the category filter, or lost its price. That is
        deliberate: it is no longer re-read, so it is no longer an offer this
        site can stand behind, and it returns the moment a read yields it.
        """
        now = datetime.now(timezone.utc)
        aliases = (
            self.db.query(ProductAlias)
            .join(Store, ProductAlias.store_id == Store.id)
            .filter(
                # THIS store only. Another store's feed says nothing about what
                # this one sells, and SKU strings are not unique across stores
                # -- "SB-1" at one shop is no evidence about "SB-1" at another.
                ProductAlias.store_id == store.id,
                # Never a merchant's listing. Nothing reads a merchant's feed,
                # so no read can show one gone; a merchant store that happens
                # to share a registry entry's name is not evidence either.
                Store.owner_user_id.is_(None),
            )
            .all()
        )

        delisted = relisted = 0
        candidates = []
        for alias in aliases:
            contained = (
                alias.id in seen_alias_ids or alias.store_product_id in seen_ids
            )
            if contained and alias.delisted_at is not None:
                alias.delisted_at = None
                relisted += 1
            elif not contained and delist_unseen and alias.delisted_at is None:
                candidates.append(alias)

        # THE SAFETY VALVE. "The read reached an empty page" is the only proof
        # of completeness, and a store can serve an empty page in the middle
        # of its catalogue, or a change to the category rules can shrink what
        # is kept. Believed, either takes most of a store off the site in one
        # unattended run. So one run may not remove more than a quarter of the
        # offers shoppers can currently see from one store (with a floor, so a
        # small store can still lose a handful). Over that, the fresh ones are
        # kept and the result says so -- run_job fails the store, which holds
        # alerts back and puts the reason on the job row for a person.
        #
        # Only FRESH offers count and are protected. A listing whose price is
        # already past the freshness window is invisible to shoppers anyway,
        # so delisting it removes nothing a shopper sees. That is also what
        # stops a refusal repeating forever when a store genuinely dropped a
        # whole range: within the window the unseen offers go stale, stop
        # counting, and the next run delists them.
        refused = None
        if candidates:
            cutoff = freshness_cutoff(now)
            prices = {
                row.alias_id: row
                for row in self.db.query(Price)
                .filter(Price.alias_id.in_([a.id for a in aliases]))
                .all()
            }

            def fresh(alias) -> bool:
                row = prices.get(alias.id)
                read = row and (row.checked_at or row.last_updated)
                if not read:
                    return False
                read = read if read.tzinfo else read.replace(tzinfo=timezone.utc)
                return read >= cutoff

            showing = sum(1 for a in aliases if a.delisted_at is None and fresh(a))
            fresh_candidates = [a for a in candidates if fresh(a)]
            allowed = max(MASS_DELIST_FLOOR, int(showing * MASS_DELIST_SHARE))
            if len(fresh_candidates) > allowed:
                refused = (
                    f"would delist {len(fresh_candidates)} of {showing} current "
                    f"listings (limit {allowed}); kept them"
                )
                candidates = [a for a in candidates if not fresh(a)]
                logger.error(
                    "Mass delisting refused",
                    extra={
                        "action": "ingest_delist_refused",
                        "target": f"{store.name}: {refused}",
                        "success": False,
                    },
                )

        for alias in candidates:
            # Only stamped once: WHEN the listing went is the useful fact,
            # and re-stamping it every run would erase it.
            alias.delisted_at = now
            delisted += 1

        self.db.commit()
        if delisted or relisted:
            logger.info(
                "Store listings reconciled",
                extra={
                    "action": "ingest_delist",
                    "target": f"{store.name}: {delisted} delisted, {relisted} relisted",
                    "success": True,
                },
            )
        return delisted, relisted, refused

    def run_all(self, notify: bool = True) -> list[dict]:
        """Scrape every store, then act on any alerts the new prices met."""
        results = []
        for config in STORES:
            try:
                results.append(self.run_store(config))
            except Exception:
                # A store that is down or has changed its feed must not stop
                # the others from being refreshed.
                logger.error(
                    "Store run failed",
                    exc_info=True,
                    extra={
                        "action": "ingest_store",
                        "target": config.name,
                        "success": False,
                    },
                )
                results.append({"store": config.name, "error": True})

        # Held back after any store that did not read cleanly, for the reason
        # jobs.run_job gives: that store's removed listings are still in the
        # comparison. This is the manual path (python -m app.services.ingest);
        # the worker goes through run_job.
        clean = all(
            not r.get("error") and r.get("complete") and not r.get("delist_refused")
            for r in results
        )
        if notify and not clean:
            results.append({"alerts": "skipped: a store did not read cleanly"})
        elif notify:
            # After ingest, not during: an alert should fire on the final
            # price of the run, not on whichever store happened to be
            # scraped first.
            from app.services.notifications import process_alerts

            results.append({"alerts": process_alerts(self.db)})

        return results


if __name__ == "__main__":
    from app.database import SessionLocal
    from app.logging_config import setup_logging

    setup_logging()
    db = SessionLocal()
    try:
        for outcome in IngestService(db).run_all():
            print(outcome)
    finally:
        db.close()
