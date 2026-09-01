"""
Money precision and proxy-aware client identification.

Both are cases where the obvious implementation is subtly wrong: floats lose
decimal fractions, and trusting X-Forwarded-For naively removes the rate limit
instead of fixing it.
"""

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.alias import ProductAlias
from app.models.price import Price
from app.models.product import Product
from app.models.store import Store
from app.security.rate_limiter import client_ip
from app.services.pricing import offers_for, price_summary


# --- Money ------------------------------------------------------------------


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def add_price(db, store_name, price, delivery, product=None):
    store = db.query(Store).filter_by(name=store_name).first()
    if not store:
        store = Store(name=store_name)
        db.add(store)
        db.commit()
        db.refresh(store)

    if product is None:
        product = Product(canonical_name="Test Phone", match_category="phones")
        db.add(product)
        db.commit()
        db.refresh(product)

    alias = ProductAlias(
        product_id=product.id,
        store_id=store.id,
        store_product_name=f"Test Phone @{store_name}",
        store_product_id=f"{store_name}-{price}",
    )
    db.add(alias)
    db.commit()
    db.refresh(alias)
    db.add(
        Price(
            alias_id=alias.id,
            price=Decimal(str(price)),
            delivery_cost=Decimal(str(delivery)),
            availability=True,
        )
    )
    db.commit()
    return product


class TestMoneyPrecision:
    def test_three_decimal_prices_survive_a_round_trip(self, db):
        """JOD has three decimals and the feeds return "136.000"."""
        product = add_price(db, "SmartBuy", "136.125", "0")
        stored = db.query(Price).one()
        assert stored.price == Decimal("136.125")

    def test_totals_are_exact(self, db):
        """
        0.1 + 0.2 != 0.3 in binary floating point. These totals decide which
        store is cheapest and whether a price alert has been met.
        """
        product = add_price(db, "SmartBuy", "0.1", "0.2")
        summary = offers_for(price_summary(db, [product.id]), product.id)
        assert summary["best_total"] == Decimal("0.3")

    def test_a_thousandth_of_a_dinar_still_orders_correctly(self, db):
        product = add_price(db, "StoreA", "100.001", "0")
        add_price(db, "StoreB", "100.002", "0", product=product)

        summary = offers_for(price_summary(db, [product.id]), product.id)
        assert summary["best"] == "StoreA"
        assert summary["best_total"] == Decimal("100.001")

    def test_delivery_decides_the_cheapest_store(self, db):
        """A lower sticker price with dearer delivery is not the better deal."""
        product = add_price(db, "Cheap sticker", "100.000", "10.000")
        add_price(db, "Free delivery", "105.000", "0.000", product=product)

        summary = offers_for(price_summary(db, [product.id]), product.id)
        assert summary["best"] == "Free delivery"
        assert summary["best_total"] == Decimal("105.000")

    def test_alert_target_is_met_at_exactly_the_target(self, db):
        """
        The boundary case floats get wrong: a target equal to the price must
        count as met.
        """
        product = add_price(db, "SmartBuy", "839.150", "0")
        lowest = offers_for(price_summary(db, [product.id]), product.id)["best_total"]
        assert lowest <= Decimal("839.150")


# --- Proxy-aware client IP --------------------------------------------------


class FakeClient:
    def __init__(self, host):
        self.host = host


class FakeRequest:
    def __init__(self, peer="203.0.113.9", forwarded=None):
        self.client = FakeClient(peer)
        self.headers = {}
        if forwarded is not None:
            self.headers["x-forwarded-for"] = forwarded


@pytest.fixture
def proxies(monkeypatch):
    """Set how many proxies the app believes sit in front of it."""

    def _set(count):
        monkeypatch.setattr(
            "app.security.rate_limiter.settings.trusted_proxy_count", count
        )

    return _set


class TestClientIP:
    def test_without_proxies_the_header_is_ignored(self, proxies):
        """
        The critical case. If the header were trusted with no proxy in front,
        any caller could send a new value per request and never be limited.
        """
        proxies(0)
        request = FakeRequest(peer="203.0.113.9", forwarded="1.2.3.4")
        assert client_ip(request) == "203.0.113.9"

    def test_one_proxy_uses_the_last_entry(self, proxies):
        proxies(1)
        request = FakeRequest(peer="10.0.0.1", forwarded="198.51.100.7")
        assert client_ip(request) == "198.51.100.7"

    def test_forged_entries_on_the_left_are_ignored(self, proxies):
        """
        The client can prepend anything. With one trusted proxy only the last
        entry was written by infrastructure we control.
        """
        proxies(1)
        request = FakeRequest(
            peer="10.0.0.1", forwarded="1.2.3.4, 5.6.7.8, 198.51.100.7"
        )
        assert client_ip(request) == "198.51.100.7"

    def test_two_proxies_count_from_the_right(self, proxies):
        proxies(2)
        request = FakeRequest(
            peer="10.0.0.1", forwarded="1.2.3.4, 198.51.100.7, 10.0.0.2"
        )
        assert client_ip(request) == "198.51.100.7"

    def test_a_short_chain_falls_back_to_the_peer(self, proxies):
        """Fewer hops than expected means the request did not take the
        expected path; trusting the value would be guessing."""
        proxies(2)
        request = FakeRequest(peer="10.0.0.1", forwarded="198.51.100.7")
        assert client_ip(request) == "10.0.0.1"

    def test_missing_header_behind_a_proxy_falls_back_to_the_peer(self, proxies):
        proxies(1)
        assert client_ip(FakeRequest(peer="10.0.0.1")) == "10.0.0.1"

    def test_whitespace_and_empty_entries_are_tolerated(self, proxies):
        proxies(1)
        request = FakeRequest(peer="10.0.0.1", forwarded="  1.2.3.4 , , 198.51.100.7 ")
        assert client_ip(request) == "198.51.100.7"

    def test_no_client_at_all(self, proxies):
        proxies(0)
        request = FakeRequest()
        request.client = None
        assert client_ip(request) == "unknown"
