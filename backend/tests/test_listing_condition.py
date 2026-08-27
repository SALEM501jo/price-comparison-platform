"""
Condition: new and second-hand are separate categories, not one price list.

THE FAILURE THESE PREVENT:
A used iPhone at 620 JOD with 84% battery is not a cheaper new iPhone. Folded
into one table it takes the "best deal" badge every time, becomes the product's
headline price, and satisfies a price alert the shopper set expecting a working
new phone. Each of those is a comparison that is simply wrong, and the last one
cannot be un-sent.

So the two groups are tallied apart everywhere a price is summarised, and a
second-hand listing has to disclose what a buyer would ask about.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.alias import ProductAlias
from app.models.price import Price
from app.models.product import Product
from app.models.store import Store
from app.models.user import User, UserRole

PASSWORD = "TestPass123"
PHONE_NAME = "Apple iPhone 15 128GB Black"


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session, monkeypatch):
    async def no_limit(*args, **kwargs):
        return None

    monkeypatch.setattr("app.security.rate_limiter._enforce", no_limit)
    monkeypatch.setattr(Base.metadata, "create_all", lambda *a, **k: None)

    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def signup(client, email):
    response = client.post(
        "/auth/register", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def make_admin(client, db_session, email="admin@example.com"):
    headers = signup(client, email)
    user = db_session.query(User).filter(User.email == email).first()
    user.role = UserRole.admin
    db_session.commit()
    return headers


def open_shop(client, email, name):
    headers = signup(client, email)
    response = client.post(
        "/merchant/store",
        json={"name": name, "phone": "0791234567"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return headers, response.json()


def verify(client, db_session, store_id, admin_email="admin@example.com"):
    admin = make_admin(client, db_session, admin_email)
    response = client.post(f"/admin/stores/{store_id}/verify", headers=admin)
    assert response.status_code == 200, response.text


def seed_new_stock(db_session, price=850.0):
    """A scraped retailer listing, which is new by definition."""
    store = Store(name="SmartBuy", website="smartbuy-me.com", is_verified=True)
    product = Product(
        canonical_name=PHONE_NAME,
        brand="apple",
        match_category="phones",
        match_attributes={
            "brand": "apple",
            "model": "iphone 15",
            "variant": "base",
            "storage": "128gb",
            "color": "black",
        },
    )
    db_session.add_all([store, product])
    db_session.commit()

    alias = ProductAlias(
        product_id=product.id,
        store_id=store.id,
        store_product_name=PHONE_NAME,
        store_product_id="SB-1",
        match_confidence=1.0,
        condition="new",
    )
    db_session.add(alias)
    db_session.commit()
    db_session.add(Price(alias_id=alias.id, price=price, delivery_cost=0))
    db_session.commit()
    return product


def add_used(client, headers, price=620.0, **overrides):
    payload = {
        "name": PHONE_NAME,
        "price": price,
        "condition": "used",
        "battery_health": 84,
        "has_damage": False,
    }
    payload.update(overrides)
    return client.post("/merchant/listings", json=payload, headers=headers)


def add_new(client, headers, price=800.0):
    return client.post(
        "/merchant/listings",
        json={"name": PHONE_NAME, "price": price, "condition": "new"},
        headers=headers,
    )


# --- Disclosure -------------------------------------------------------------


class TestSecondHandDisclosure:
    """
    A used listing missing battery health or a damage answer is not an offer
    anyone can act on, and "no damage" must be distinguishable from "the
    seller did not say".
    """

    def test_a_used_listing_needs_battery_health(self, client):
        headers, _ = open_shop(client, "u1@example.com", "Used One")
        assert add_used(client, headers, battery_health=None).status_code == 422

    def test_a_used_listing_needs_a_damage_answer(self, client):
        headers, _ = open_shop(client, "u2@example.com", "Used Two")
        assert add_used(client, headers, has_damage=None).status_code == 422

    def test_claimed_damage_must_be_described(self, client):
        headers, _ = open_shop(client, "u3@example.com", "Used Three")
        assert add_used(client, headers, has_damage=True).status_code == 422

    def test_a_new_listing_cannot_claim_battery_health(self, client):
        """Otherwise a listing is sealed and 82% worn at the same time."""
        headers, _ = open_shop(client, "u4@example.com", "Used Four")
        response = client.post(
            "/merchant/listings",
            json={
                "name": PHONE_NAME,
                "price": 800,
                "condition": "new",
                "battery_health": 82,
            },
            headers=headers,
        )
        assert response.status_code == 422

    def test_a_complete_used_listing_is_accepted_and_echoed_back(self, client):
        headers, _ = open_shop(client, "u5@example.com", "Used Five")
        response = add_used(
            client,
            headers,
            has_damage=True,
            damage_notes="Hairline crack, bottom right of the screen",
            warranty_months=3,
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["condition"] == "used"
        assert body["battery_health"] == 84
        assert body["has_damage"] is True
        assert "Hairline crack" in body["damage_notes"]
        assert body["warranty_months"] == 3

    @pytest.mark.parametrize("battery", [0, -5, 101, 900])
    def test_impossible_battery_figures_are_rejected(self, client, battery):
        headers, _ = open_shop(client, f"b{battery}@example.com", f"Batt {battery}")
        assert add_used(client, headers, battery_health=battery).status_code == 422

    def test_condition_cannot_be_edited_after_listing(self, client):
        """
        A used row silently becoming new is exactly the edit a dishonest
        seller would want, and it would carry its price history across.
        """
        headers, _ = open_shop(client, "u6@example.com", "Used Six")
        listing = add_used(client, headers).json()
        client.patch(
            f"/merchant/listings/{listing['id']}",
            json={"condition": "new", "price": 640},
            headers=headers,
        )
        rows = client.get("/merchant/listings", headers=headers).json()
        assert rows[0]["condition"] == "used"

    def test_battery_health_can_be_updated_as_the_phone_ages(self, client):
        """Wear changes even when the condition does not."""
        headers, _ = open_shop(client, "u7@example.com", "Used Seven")
        listing = add_used(client, headers).json()
        client.patch(
            f"/merchant/listings/{listing['id']}",
            json={"battery_health": 79},
            headers=headers,
        )
        rows = client.get("/merchant/listings", headers=headers).json()
        assert rows[0]["battery_health"] == 79


# --- The two groups stay apart ---------------------------------------------


class TestNewAndUsedDoNotMix:
    def test_one_shop_can_list_the_same_phone_new_and_used(self, client):
        """
        Two units in different conditions are two listings. The dedup guard
        falls back to matching on name, so without a condition-aware key the
        second submission silently overwrote the first.
        """
        headers, _ = open_shop(client, "mix1@example.com", "Mixed Stock")
        assert add_new(client, headers, price=800.0).status_code == 201
        assert add_used(client, headers, price=620.0).status_code == 201

        rows = client.get("/merchant/listings", headers=headers).json()
        assert len(rows) == 2
        assert sorted(r["condition"] for r in rows) == ["new", "used"]

    def test_a_used_unit_never_becomes_the_headline_price(self, client, db_session):
        """
        The failure the whole split exists to prevent: one worn handset at
        620 making a product look like a bargain against a sealed one at 850.
        """
        product = seed_new_stock(db_session, price=850.0)
        headers, store = open_shop(client, "mix2@example.com", "Cheap Used Shop")
        add_used(client, headers, price=620.0)
        verify(client, db_session, store["id"])

        body = client.get("/products/search", params={"q": "iPhone 15 128GB"}).json()
        found = [
            item
            for tier in ("exact", "close", "similar")
            for item in body[tier]
            if item["id"] == product.id
        ]
        assert found, "the product should still be found"
        card = found[0]
        assert card["lowest_price"] == 850.0, "headline must be the new price"
        assert card["best_deal_store"] == "SmartBuy"
        assert card["store_count"] == 1
        # ...and the used offer is reported, not hidden
        assert card["second_hand_from"] == 620.0
        assert card["second_hand_store_count"] == 1

    def test_a_used_only_product_reports_no_new_price(self, client, db_session):
        headers, store = open_shop(client, "mix3@example.com", "Used Only Shop")
        listing = add_used(client, headers, price=500.0).json()
        verify(client, db_session, store["id"])

        detail = client.get(f"/products/{listing['matched_product_id']}").json()
        assert [p["comparison_group"] for p in detail["prices"]] == ["second_hand"]

    def test_the_product_page_labels_each_offer_group(self, client, db_session):
        product = seed_new_stock(db_session, price=850.0)
        headers, store = open_shop(client, "mix4@example.com", "Both Groups Shop")
        add_used(client, headers, price=620.0, battery_health=79)
        verify(client, db_session, store["id"])

        prices = client.get(f"/products/{product.id}").json()["prices"]
        groups = {p["comparison_group"]: p for p in prices}
        assert set(groups) == {"new", "second_hand"}
        assert groups["new"]["price"] == 850.0
        assert groups["second_hand"]["price"] == 620.0
        assert groups["second_hand"]["battery_health"] == 79
        assert groups["new"]["battery_health"] is None

    def test_a_price_alert_does_not_fire_on_a_used_phone(self, client, db_session):
        """
        A shopper waiting for an iPhone 15 under 700 meant a phone, not one
        with 84% battery and no warranty. An alert cannot be un-sent, so it
        tracks new stock.
        """
        product = seed_new_stock(db_session, price=850.0)
        shopper = signup(client, "waiting@example.com")
        created = client.post(
            "/prices/alerts",
            json={"product_id": product.id, "target_price": 700},
            headers=shopper,
        )
        assert created.status_code in (200, 201), created.text
        assert created.json()["is_met"] is False

        headers, store = open_shop(client, "mix5@example.com", "Undercut Used")
        add_used(client, headers, price=620.0)
        verify(client, db_session, store["id"])

        alerts = client.get("/prices/alerts", headers=shopper).json()
        assert alerts[0]["is_met"] is False, "a used unit must not satisfy the alert"
        assert alerts[0]["lowest_total_cost"] == 850.0

    def test_the_wishlist_quotes_the_new_price(self, client, db_session):
        product = seed_new_stock(db_session, price=850.0)
        shopper = signup(client, "wisher@example.com")
        client.post(f"/prices/wishlist/{product.id}", headers=shopper)

        headers, store = open_shop(client, "mix6@example.com", "Wishlist Used")
        add_used(client, headers, price=620.0)
        verify(client, db_session, store["id"])

        items = client.get("/prices/wishlist", headers=shopper).json()
        assert items[0]["lowest_total_cost"] == 850.0
        assert items[0]["best_deal_store"] == "SmartBuy"

    def test_scraped_listings_are_new_by_default(self, client, db_session):
        """A retailer's own feed does not sell worn stock."""
        product = seed_new_stock(db_session, price=850.0)
        prices = client.get(f"/products/{product.id}").json()["prices"]
        assert prices[0]["condition"] == "new"
        assert prices[0]["comparison_group"] == "new"
