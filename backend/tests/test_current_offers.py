"""
Only CURRENT offers reach a shopper, a search engine or an email.

THE FAILURE THESE EXIST FOR: a listing the store had removed kept its last
price forever. Live, product 483 (iPhone 16 128GB) showed SmartBuy at 689 JOD
as the best price, with a "Visit store" link to a page SmartBuy answers 404
for -- because every read path asked whether the STORE was visible, and none
asked whether the store still sold the thing, or whether anybody had looked
lately.

offers.current_offer() is now the one rule. These tests walk every read path
that shows a price, a product or a link, and put the same listings in front of
each:

  - a scraped listing re-read an hour ago, price unchanged for weeks -> shown
  - a scraped listing the store no longer lists                     -> gone
  - a scraped listing nobody has re-read within the age limit       -> gone
  - a merchant's price typed a month ago                            -> shown

THE DELISTED AND STALE LISTINGS ARE THE CHEAPEST, deliberately. A path that
leaks them does not merely add a row -- it hands them "best price", the lowest
total and the saving, which is the exact failure seen live. And the fresh
scraped listing's price last CHANGED weeks ago, so a path that judged freshness
by last_updated alone would drop it and fail here too.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.config import get_settings
from app.matching import parse
from app.models.alias import ProductAlias
from app.models.price import Price, PriceAlert, PriceHistory
from app.models.product import Product
from app.models.store import Store
from app.models.user import User
from app.routers import seo
from app.services import catalogue
from app.services.deals import best_savings
from app.services.email.base import NullSender
from app.services.pricing import has_current_offer, offers_for, price_summary
from app.services.search import search_products

settings = get_settings()

BASE = "https://ahsanse3r.com"

# Owner ids for merchant stores. owner_user_id is unique, and SQLite does not
# enforce the foreign key, so no user row is needed -- only a distinct id.
_owner_ids = itertools.count(1000)


def ago(**delta) -> datetime:
    return datetime.now(timezone.utc) - timedelta(**delta)


def stale() -> datetime:
    """
    Past the age limit by a margin no slow test run can close.

    Derived from the setting rather than written as "49 hours", so the tests
    follow the limit if it is ever changed instead of quietly testing the old
    one.
    """
    return ago(hours=settings.scraped_price_max_age_hours + 6)


# --- Setup ------------------------------------------------------------------


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    """
    A fixed public address, and a catalogue version that answers at once.

    catalogue_version() tries Redis first, and against a Redis that is not
    running that attempt costs seconds per request on some platforms.
    """
    monkeypatch.setattr(seo.settings, "app_base_url", BASE)

    async def version():
        return "0"

    monkeypatch.setattr("app.services.cache.catalogue_version", version)
    monkeypatch.setattr("app.routers.products.catalogue_version", version)


def make_store(db, name, *, merchant=False):
    store = Store(
        name=name,
        is_active=1,
        owner_user_id=next(_owner_ids) if merchant else None,
        # Scraped stores are seeded verified; merchants here have been
        # approved. Neither is what these tests are about.
        is_verified=True,
        website=None if merchant else f"https://{name.lower().replace(' ', '')}.example",
    )
    db.add(store)
    db.flush()
    return store


def make_product(db, name, *, category=None):
    """
    Attributes and brand from the REAL parser, as deduplication writes them
    (parsed.specified): search narrows on (match_category, brand) and browse
    groups on the attributes, so a fixture that left them null would exercise
    paths no real row takes.
    """
    parsed = parse(name)
    product = Product(
        canonical_name=name,
        brand=parsed.get("brand"),
        match_category=category or parsed.category,
        match_attributes=parsed.specified,
        image_url=f"https://cdn.example/{abs(hash(name)) % 9999}.jpg",
    )
    db.add(product)
    db.flush()
    return product


def listing(db, store, product, price, *, read=None, changed=None, delisted=None,
            available=True):
    """
    One store's listing of one product.

    read     -> Price.checked_at: when a scraper last READ it (None for a
                merchant, whose prices nothing re-reads).
    changed  -> Price.last_updated: when the price last CHANGED.
    delisted -> ProductAlias.delisted_at: when the store stopped listing it.
    """
    alias = ProductAlias(
        product_id=product.id,
        store_id=store.id,
        store_product_name=product.canonical_name,
        store_product_id=f"sku-{store.id}-{product.id}",
        store_product_url=(
            None if store.is_merchant
            else f"{store.website}/products/{product.id}"
        ),
        delisted_at=delisted,
    )
    db.add(alias)
    db.flush()
    row = Price(
        alias_id=alias.id,
        price=Decimal(str(price)),
        delivery_cost=Decimal("0"),
        availability=available,
        checked_at=read,
    )
    if changed is not None:
        row.last_updated = changed
    db.add(row)
    db.flush()
    return row


@dataclass
class Market:
    db: object
    # Carried by all four stores. Current offers: Fresh 700, merchant 720.
    phone: Product
    # Would be a "deal" only because of a delisted / a stale second listing.
    delisted_deal: Product
    stale_deal: Product
    # The ONLY listing is delisted / stale / a month-old merchant price.
    delisted_only: Product
    stale_only: Product
    merchant_only: Product
    # A whole category whose only stock is delisted / stale.
    delisted_laptop: Product
    stale_monitor: Product
    fresh_changed: datetime
    deal_changed: datetime
    gone_url: str


FRESH, GONE, STALE, MERCHANT = "Fresh Shop", "Gone Shop", "Stale Shop", "Abu Ahmad Phones"


@pytest.fixture
def market(db_session):
    db = db_session
    fresh = make_store(db, FRESH)
    gone = make_store(db, GONE)
    old = make_store(db, STALE)
    merchant = make_store(db, MERCHANT, merchant=True)

    # Re-read an hour ago; the price itself last changed three weeks ago.
    fresh_changed = ago(days=20)
    deal_changed = ago(days=10)

    phone = make_product(db, "Apple iPhone 16 128GB Black")
    listing(db, fresh, phone, 700, read=ago(hours=1), changed=fresh_changed)
    # Read in the same run that found it gone: freshness alone would pass it.
    gone_row = listing(db, gone, phone, 600, read=ago(hours=1), changed=ago(hours=1),
                       delisted=ago(hours=1))
    listing(db, old, phone, 650, read=stale(), changed=stale())
    # A person typed this a month ago; nothing re-reads it, and nothing should.
    listing(db, merchant, phone, 720, changed=ago(days=30))

    delisted_deal = make_product(db, "Samsung Galaxy S24 256GB Black")
    listing(db, fresh, delisted_deal, 800, read=ago(hours=1), changed=deal_changed)
    listing(db, gone, delisted_deal, 900, read=ago(hours=1), delisted=ago(hours=1))

    stale_deal = make_product(db, "Samsung Galaxy S23 256GB Black")
    listing(db, fresh, stale_deal, 750, read=ago(hours=1), changed=deal_changed)
    listing(db, old, stale_deal, 950, read=stale(), changed=stale())

    delisted_only = make_product(db, "Apple iPhone 15 128GB Black")
    listing(db, gone, delisted_only, 500, read=ago(hours=1), delisted=ago(hours=1))

    stale_only = make_product(db, "Apple iPhone 14 128GB Black")
    listing(db, old, stale_only, 450, read=stale(), changed=stale())

    merchant_only = make_product(db, "Xiaomi Redmi Note 13 256GB Black")
    listing(db, merchant, merchant_only, 200, changed=ago(days=30))

    delisted_laptop = make_product(db, "Lenovo ThinkPad X1 Carbon 16GB 512GB")
    listing(db, gone, delisted_laptop, 1500, read=ago(hours=1), delisted=ago(hours=1))

    stale_monitor = make_product(db, "Dell UltraSharp U2723QE Monitor", category="monitors")
    listing(db, old, stale_monitor, 300, read=stale(), changed=stale())

    db.commit()
    gone_url = db.get(ProductAlias, gone_row.alias_id).store_product_url
    return Market(
        db=db,
        phone=phone,
        delisted_deal=delisted_deal,
        stale_deal=stale_deal,
        delisted_only=delisted_only,
        stale_only=stale_only,
        merchant_only=merchant_only,
        delisted_laptop=delisted_laptop,
        stale_monitor=stale_monitor,
        fresh_changed=fresh_changed,
        deal_changed=deal_changed,
        gone_url=gone_url,
    )


def gone_products(market):
    """Every product whose only listing is not a current offer."""
    return {
        market.delisted_only.id,
        market.stale_only.id,
        market.delisted_laptop.id,
        market.stale_monitor.id,
    }


# --- pricing.price_summary: search cards, wishlist, alerts ------------------


class TestPriceSummary:
    def test_prices_totals_best_deal_and_store_count_are_current_offers(self, market):
        summary = price_summary(market.db, [market.phone.id])
        new = offers_for(summary, market.phone.id)

        assert new["stores"] == {FRESH, MERCHANT}
        assert sorted(new["prices"]) == [Decimal("700"), Decimal("720")]
        assert sorted(new["totals"]) == [Decimal("700"), Decimal("720")]
        # The delisted listing at 600 and the stale one at 650 are cheaper;
        # either one leaking would take best price.
        assert new["best"] == FRESH
        assert new["best_total"] == Decimal("700")

    def test_a_product_with_no_current_offer_has_no_figures(self, market):
        ids = [market.delisted_only.id, market.stale_only.id]
        summary = price_summary(market.db, ids)
        for product_id in ids:
            assert offers_for(summary, product_id) == {}

    def test_a_merchant_price_older_than_the_limit_still_counts(self, market):
        new = offers_for(
            price_summary(market.db, [market.merchant_only.id]), market.merchant_only.id
        )
        assert new["best"] == MERCHANT
        assert new["best_total"] == Decimal("200")

    def test_a_scraped_row_never_stamped_by_a_read_falls_back_to_last_updated(self, db_session):
        """
        checked_at is null on rows no scraper has read since the column was
        added. Those are judged by last_updated: a recent one still counts,
        an old one does not.
        """
        shop = make_store(db_session, "Legacy Shop")
        recent = make_product(db_session, "Apple iPhone 16 Pro 256GB Black")
        listing(db_session, shop, recent, 900, read=None, changed=ago(hours=3))
        ancient = make_product(db_session, "Apple iPhone 13 128GB Black")
        listing(db_session, shop, ancient, 400, read=None, changed=stale())
        db_session.commit()

        summary = price_summary(db_session, [recent.id, ancient.id])
        assert offers_for(summary, recent.id)["best"] == "Legacy Shop"
        assert offers_for(summary, ancient.id) == {}


# --- products.get_product: the comparison table ------------------------------


class TestProductPage:
    def test_the_table_lists_only_current_offers(self, client, market):
        response = client.get(f"/products/{market.phone.id}")
        assert response.status_code == 200
        rows = response.json()["prices"]

        assert {row["store_name"] for row in rows} == {FRESH, MERCHANT}
        # Sorted by total, so the first row is the one the page calls best.
        assert rows[0]["store_name"] == FRESH
        assert float(rows[0]["total_cost"]) == 700.0
        # No "Visit store" link to the page the store has taken down.
        assert market.gone_url not in {row["store_product_url"] for row in rows}

    def test_a_product_whose_only_offer_is_delisted_is_a_404(self, client, market):
        assert client.get(f"/products/{market.delisted_only.id}").status_code == 404

    def test_a_product_whose_only_offer_is_stale_is_a_404(self, client, market):
        assert client.get(f"/products/{market.stale_only.id}").status_code == 404

    def test_a_month_old_merchant_price_still_has_a_page(self, client, market):
        response = client.get(f"/products/{market.merchant_only.id}")
        assert response.status_code == 200
        assert [row["store_name"] for row in response.json()["prices"]] == [MERCHANT]

    def test_a_scraped_price_read_within_the_limit_is_shown(self, client, db_session):
        """Unchanged for weeks, re-read an hour ago: that is a current price."""
        shop = make_store(db_session, "SmartBuy")
        product = make_product(db_session, "Apple iPhone 16 128GB Black")
        listing(db_session, shop, product, 689, read=ago(hours=1), changed=ago(days=19))
        db_session.commit()

        response = client.get(f"/products/{product.id}")
        assert response.status_code == 200
        assert [row["store_name"] for row in response.json()["prices"]] == ["SmartBuy"]


# --- products.get_price_history ----------------------------------------------


class TestPriceHistory:
    @pytest.fixture
    def charted(self, market):
        """Two recorded points for every listing of the phone and of the delisted-only iPhone."""
        aliases = (
            market.db.query(ProductAlias)
            .filter(ProductAlias.product_id.in_([market.phone.id, market.delisted_only.id]))
            .all()
        )
        for alias in aliases:
            for days in (5, 1):
                market.db.add(
                    PriceHistory(alias_id=alias.id, price=Decimal("600"),
                                 recorded_at=ago(days=days))
                )
        market.db.commit()
        return market

    def test_the_chart_draws_the_same_shops_as_the_table(self, client, charted):
        series = client.get(f"/products/{charted.phone.id}/history").json()
        assert {s["store_name"] for s in series} == {FRESH, MERCHANT}
        assert all(len(s["history"]) == 2 for s in series), "the join multiplied points"

    def test_a_product_with_no_current_offer_charts_nothing(self, client, charted):
        assert client.get(f"/products/{charted.delisted_only.id}/history").json() == []


# --- search.py candidates ----------------------------------------------------


def result_ids(response) -> set[int]:
    return {p.id for tier in (response.exact, response.close, response.similar) for p in tier}


class TestSearch:
    def test_the_card_quotes_only_current_offers(self, market):
        response = search_products(market.db, "iPhone 16 128GB Black")
        card = next(p for p in response.exact if p.id == market.phone.id)

        assert card.store_count == 2
        assert card.lowest_total_cost == Decimal("700")
        assert card.lowest_price == Decimal("700")
        assert card.highest_price == Decimal("720")
        assert card.best_deal_store == FRESH

    @pytest.mark.parametrize("query", ["iPhone 15 128GB Black", "iPhone 14 128GB Black"])
    def test_a_product_with_no_current_offer_is_not_a_result(self, market, query):
        """
        Not in ANY tier. It used to come back as an exact match with no price,
        linking to a product page that now answers 404.
        """
        found = result_ids(search_products(market.db, query))
        assert not found & gone_products(market)
        # The search itself still works: the current iPhone is still offered.
        assert market.phone.id in result_ids(search_products(market.db, "iPhone"))

    def test_a_month_old_merchant_price_is_still_a_result(self, market):
        found = result_ids(search_products(market.db, "Redmi Note 13 256GB Black"))
        assert market.merchant_only.id in found

    def test_the_existence_check_asks_about_the_product_not_one_listing(self, market):
        """
        has_current_offer() is correlated on Product alone. Used in a query
        that also names product_aliases, it must still ask whether the PRODUCT
        has a current offer -- all four of the phone's listing rows qualify --
        rather than silently narrowing to the outer row's own listing.
        """
        rows = (
            market.db.query(ProductAlias.id)
            .join(Product, Product.id == ProductAlias.product_id)
            .filter(ProductAlias.product_id == market.phone.id)
            .filter(has_current_offer())
            .all()
        )
        assert len(rows) == 4

    def test_the_name_search_fallback_applies_the_same_rule(self, db_session):
        """A query that does not parse goes down a second path. It must not leak."""
        shop = make_store(db_session, "Game Shop")
        gone = make_store(db_session, "Gone Games")
        live = make_product(db_session, "Sony PlayStation 5 Digital Edition")
        listing(db_session, shop, live, 450, read=ago(hours=1))
        delisted = make_product(db_session, "Sony PlayStation 5 Slim Edition")
        listing(db_session, gone, delisted, 399, read=ago(hours=1), delisted=ago(hours=1))
        old = make_product(db_session, "Sony PlayStation 5 Pro Edition")
        listing(db_session, shop, old, 799, read=stale(), changed=stale())
        db_session.commit()

        response = search_products(db_session, "playstation")
        assert response.interpretation.structured is False
        assert result_ids(response) == {live.id}


# --- products.suggest ---------------------------------------------------------


class TestSuggest:
    def labels(self, client, q):
        response = client.get("/products/suggest", params={"q": q})
        assert response.status_code == 200
        return {row["product_id"] for row in response.json()}

    def test_suggests_only_products_somebody_offers_now(self, client, market):
        found = self.labels(client, "iphone")
        assert market.phone.id in found
        assert market.delisted_only.id not in found, "suggested into a 404"
        assert market.stale_only.id not in found, "suggested into a 404"

    def test_every_suggestion_leads_to_a_page(self, client, market):
        """The failure to prevent, stated directly: a suggestion that 404s."""
        suggested = set()
        for q in ("apple", "samsung", "xiaomi", "lenovo", "dell"):
            suggested |= self.labels(client, q)
        assert suggested, "nothing was suggested, so nothing was checked"
        for product_id in suggested:
            assert client.get(f"/products/{product_id}").status_code == 200, product_id

    def test_a_month_old_merchant_price_is_still_suggested(self, client, market):
        assert market.merchant_only.id in self.labels(client, "redmi")


# --- deals.best_savings -------------------------------------------------------


class TestDeals:
    def test_the_saving_is_between_current_offers_only(self, market):
        deals = {d["id"]: d for d in best_savings(market.db, limit=24)}
        phone = deals[market.phone.id]

        # Fresh 700 against the merchant's month-old 720. Leaking the
        # delisted 600 would claim a 120 JOD saving at a shop that no longer
        # sells it.
        assert phone["lowest_total_cost"] == 700.0
        assert phone["highest_total_cost"] == 720.0
        assert phone["saving"] == 20.0
        assert phone["best_deal_store"] == FRESH
        assert phone["store_count"] == 2

    def test_a_removed_or_stale_listing_does_not_manufacture_a_deal(self, market):
        found = {d["id"] for d in best_savings(market.db, limit=24)}
        assert market.delisted_deal.id not in found
        assert market.stale_deal.id not in found


# --- catalogue: browse tiles and category counts ------------------------------


class TestBrowse:
    def test_category_counts_are_current_offers(self, market):
        counts = {row["category"]: row["count"] for row in catalogue.category_counts(market.db)}
        # iPhone 16, Galaxy S24, Galaxy S23 and the merchant's Redmi. Not the
        # iPhone 15 or 14; and no laptop or monitor tile at all.
        assert counts == {"phones": 4}
        assert catalogue.total_in(market.db) == 4

    def test_the_tiles_quote_only_current_offers(self, market):
        tiles = {t["id"]: t for t in catalogue.browse(market.db, category="phones", limit=48)}
        assert set(tiles) == {
            market.phone.id,
            market.delisted_deal.id,
            market.stale_deal.id,
            market.merchant_only.id,
        }
        phone = tiles[market.phone.id]
        assert phone["lowest_total_cost"] == 700.0
        assert phone["best_deal_store"] == FRESH
        assert phone["store_count"] == 2

    def test_the_route_agrees(self, client, market):
        body = client.get("/products/browse").json()
        assert body["categories"] == [{"category": "phones", "count": 4}]
        assert not {p["id"] for p in body["products"]} & gone_products(market)


# --- seo: the sitemap --------------------------------------------------------


class TestSitemap:
    def urls(self, client) -> dict[str, str | None]:
        import xml.etree.ElementTree as ET

        ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
        root = ET.fromstring(client.get("/sitemap.xml").content)
        return {u.findtext(f"{ns}loc"): u.findtext(f"{ns}lastmod") for u in root.findall(f"{ns}url")}

    def test_lists_no_product_without_a_current_offer(self, client, market):
        found = self.urls(client)
        for product in (market.phone, market.merchant_only):
            assert f"{BASE}/product/{product.id}" in found
        for product_id in gone_products(market):
            assert f"{BASE}/product/{product_id}" not in found, "a sitemap URL to a 404"

    def test_in_stock_and_current_must_be_the_same_listing(self, client, db_session):
        """
        A current listing that is sold out plus a removed listing still marked
        in stock is not a buyable product. Asking "has an in-stock row" of
        every row, and "is current" separately, would list it.
        """
        shop = make_store(db_session, "Fresh Shop")
        gone = make_store(db_session, "Gone Shop")
        product = make_product(db_session, "Apple iPhone 16 128GB Black")
        listing(db_session, shop, product, 700, read=ago(hours=1), available=False)
        listing(db_session, gone, product, 600, read=ago(hours=1), available=True,
                delisted=ago(hours=1))
        db_session.commit()

        assert f"{BASE}/product/{product.id}" not in self.urls(client)
        # Still a real page, though: the sold-out offer is current.
        assert client.get(f"/products/{product.id}").status_code == 200

    def test_lists_no_category_whose_stock_is_all_gone(self, client, market):
        found = self.urls(client)
        assert f"{BASE}/browse/phones" in found
        assert f"{BASE}/browse/laptops" not in found
        assert f"{BASE}/browse/monitors" not in found

    def test_lastmod_is_when_a_current_offer_last_changed(self, client, market):
        """
        Not the delisted listing's newer change, and not the fresh listing's
        re-read an hour ago: the price on the page last changed three weeks
        ago, and that is the date a crawler should be given.
        """
        found = self.urls(client)
        assert found[f"{BASE}/product/{market.phone.id}"] == seo._w3c(market.fresh_changed)
        assert found[f"{BASE}/browse/phones"] == seo._w3c(market.deal_changed)


# --- notifications and the alert / wishlist endpoints -------------------------


class TestAlertsAndWishlist:
    @pytest.fixture
    def mail(self, monkeypatch):
        sender = NullSender()
        monkeypatch.setattr("app.services.email.get_sender", lambda: sender)
        return sender

    def alert(self, db, product, target, email):
        user = User(email=email, password_hash="x", email_verified_at=ago(days=1))
        db.add(user)
        db.flush()
        db.add(PriceAlert(user_id=user.id, product_id=product.id,
                          target_price=Decimal(str(target))))
        db.commit()

    def test_no_email_for_a_price_only_a_removed_or_stale_listing_had(self, market, mail):
        from app.services.notifications import process_alerts

        # Met by the delisted 600 and the stale 650; not by the current 700.
        self.alert(market.db, market.phone, 690, "phone@example.com")
        self.alert(market.db, market.delisted_only, 9999, "gone@example.com")
        self.alert(market.db, market.stale_only, 9999, "stale@example.com")

        assert process_alerts(market.db)["notified"] == 0
        assert mail.sent == []

    def test_a_month_old_merchant_price_still_meets_a_target(self, market, mail):
        from app.services.notifications import process_alerts

        self.alert(market.db, market.merchant_only, 250, "redmi@example.com")
        assert process_alerts(market.db)["notified"] == 1
        assert MERCHANT in mail.sent[0].text

    def test_the_endpoints_quote_current_offers(self, client, market):
        response = client.post(
            "/auth/register", json={"email": "shopper@example.com", "password": "TestPass123"}
        )
        assert response.status_code == 201, response.text
        headers = {"Authorization": f"Bearer {response.json()['access_token']}"}

        for product in (market.phone, market.delisted_only):
            assert client.post(f"/prices/wishlist/{product.id}", headers=headers).status_code == 201
        items = {i["product_id"]: i for i in client.get("/prices/wishlist", headers=headers).json()}
        assert float(items[market.phone.id]["lowest_total_cost"]) == 700.0
        assert items[market.phone.id]["best_deal_store"] == FRESH
        assert items[market.phone.id]["store_count"] == 2
        assert items[market.delisted_only.id]["lowest_total_cost"] is None
        assert items[market.delisted_only.id]["store_count"] == 0

        created = client.post(
            "/prices/alerts",
            json={"product_id": market.phone.id, "target_price": 650},
            headers=headers,
        ).json()
        assert created["is_met"] is False, "met by a listing the store removed"
        assert created["best_deal_store"] == FRESH
