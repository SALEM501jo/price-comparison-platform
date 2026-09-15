"""
/health/catalogue: an alarm before the freshness window empties the site.

A scraped price not re-read for 48 hours stops being an offer, and every run
re-reads every store within minutes -- so a dead worker takes the whole
catalogue off the site at once, two days later, silently. This endpoint goes
503 at 14 hours so an external monitor can email a person first.
"""

from datetime import datetime, timedelta, timezone

from app.main import CATALOGUE_STALE_AFTER_HOURS
from app.models.alias import ProductAlias
from app.models.price import Price
from app.models.product import Product
from app.models.store import Store
from app.models.user import User


def listing(db, *, read, merchant=False, name="SmartBuy"):
    owner = None
    if merchant:
        user = User(email=f"{name.lower()}@example.com", password_hash="x")
        db.add(user)
        db.commit()
        owner = user.id
    store = Store(name=name, website="x.example", is_active=1,
                  owner_user_id=owner, is_verified=True)
    product = Product(canonical_name=f"Phone at {name}", match_category="phones")
    db.add_all([store, product])
    db.commit()
    alias = ProductAlias(product_id=product.id, store_id=store.id,
                         store_product_name="Phone", store_product_id=f"{name}-1")
    db.add(alias)
    db.commit()
    db.add(Price(alias_id=alias.id, price=100, delivery_cost=0, availability=True,
                 checked_at=read, last_updated=read))
    db.commit()


def ago(hours):
    return datetime.now(timezone.utc) - timedelta(hours=hours)


class TestCatalogueHealth:
    def test_recent_reads_are_healthy(self, client, db_session):
        listing(db_session, read=ago(1))
        response = client.get("/health/catalogue")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_reads_older_than_the_threshold_are_an_alarm(self, client, db_session):
        listing(db_session, read=ago(CATALOGUE_STALE_AFTER_HOURS + 1))
        response = client.get("/health/catalogue")
        assert response.status_code == 503
        assert response.json()["status"] == "stale"

    def test_the_alarm_comes_well_before_offers_disappear(self):
        from app.config import get_settings

        assert CATALOGUE_STALE_AFTER_HOURS * 3 <= get_settings().scraped_price_max_age_hours + 6

    def test_a_merchant_price_does_not_hide_a_dead_scraper(self, client, db_session):
        """A shop typing prices today says nothing about the worker."""
        listing(db_session, read=ago(30))
        listing(db_session, read=ago(0), merchant=True, name="Jado")
        assert client.get("/health/catalogue").status_code == 503

    def test_no_scraped_prices_at_all_is_an_alarm(self, client, db_session):
        assert client.get("/health/catalogue").status_code == 503

    def test_it_says_nothing_about_the_catalogue(self, client, db_session):
        listing(db_session, read=ago(1))
        assert set(client.get("/health/catalogue").json()) == {"status", "newest_read_hours"}
