"""
Account type at signup, and the home-page savings list.

The account-type tests matter more than they look. Registration is the one
endpoint that creates a role, and it accepts a body from an anonymous caller.
If that body could name a role directly, anyone could register as an admin.
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


def role_of(db_session, email):
    return db_session.query(User).filter(User.email == email).first().role


class TestAccountTypeAtSignup:
    def test_the_default_is_a_shopper(self, client, db_session):
        """Omitting the field must never grant more than the least privilege."""
        response = client.post(
            "/auth/register",
            json={"email": "plain@example.com", "password": PASSWORD},
        )
        assert response.status_code == 201
        assert role_of(db_session, "plain@example.com") == UserRole.user

    def test_choosing_buyer_creates_a_shopper(self, client, db_session):
        client.post(
            "/auth/register",
            json={
                "email": "buyer@example.com",
                "password": PASSWORD,
                "account_type": "buyer",
            },
        )
        assert role_of(db_session, "buyer@example.com") == UserRole.user

    def test_choosing_merchant_creates_a_merchant(self, client, db_session):
        client.post(
            "/auth/register",
            json={
                "email": "seller@example.com",
                "password": PASSWORD,
                "account_type": "merchant",
            },
        )
        assert role_of(db_session, "seller@example.com") == UserRole.merchant

    @pytest.mark.parametrize(
        "value", ["admin", "Admin", "ADMIN", "superuser", "user", "", None, 1]
    )
    def test_no_request_can_name_a_privileged_role(self, client, db_session, value):
        """
        The field is a two-value Literal, not the role enum. Anything else is
        rejected outright rather than quietly falling back to a default --
        a silent fallback would make a typo indistinguishable from an attack.
        """
        response = client.post(
            "/auth/register",
            json={
                "email": f"attacker{value}@example.com",
                "password": PASSWORD,
                "account_type": value,
            },
        )
        assert response.status_code == 422, response.text

    def test_a_merchant_signup_has_no_store_until_they_register_one(
        self, client, db_session
    ):
        """The role is the intent; the store is a separate, verified claim."""
        response = client.post(
            "/auth/register",
            json={
                "email": "intent@example.com",
                "password": PASSWORD,
                "account_type": "merchant",
            },
        )
        headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        assert client.get("/merchant/store", headers=headers).status_code == 404


class TestBestSavings:
    """
    The home page list. A "deal" here is the gap between the cheapest and the
    dearest shop for the same product -- the only saving this platform can
    stand behind, since it has no list price to discount from.
    """

    def _stock(self, db_session, product, store_name, price, condition="new"):
        store = db_session.query(Store).filter(Store.name == store_name).first()
        if store is None:
            store = Store(name=store_name, website=f"{store_name}.jo", is_verified=True)
            db_session.add(store)
            db_session.commit()
        alias = ProductAlias(
            product_id=product.id,
            store_id=store.id,
            store_product_name=product.canonical_name,
            store_product_id=f"{store_name}-{product.id}-{condition}",
            match_confidence=1.0,
            condition=condition,
        )
        db_session.add(alias)
        db_session.commit()
        db_session.add(Price(alias_id=alias.id, price=price, delivery_cost=0))
        db_session.commit()

    def _product(self, db_session, name):
        product = Product(
            canonical_name=name,
            brand="apple",
            match_category="phones",
            match_attributes={"brand": "apple", "model": "iphone 15"},
        )
        db_session.add(product)
        db_session.commit()
        return product

    def test_a_product_at_one_shop_is_not_a_deal(self, client, db_session):
        product = self._product(db_session, "Single Shop Phone")
        self._stock(db_session, product, "OnlyShop", 800)

        deals = client.get("/products/deals").json()
        assert [d["id"] for d in deals] == []

    def test_the_saving_is_the_gap_between_shops(self, client, db_session):
        product = self._product(db_session, "Two Shop Phone")
        self._stock(db_session, product, "Cheap", 800)
        self._stock(db_session, product, "Dear", 950)

        deals = client.get("/products/deals").json()
        deal = next(d for d in deals if d["id"] == product.id)
        assert deal["lowest_total_cost"] == 800.0
        assert deal["highest_total_cost"] == 950.0
        assert deal["saving"] == 150.0
        assert deal["best_deal_store"] == "Cheap"
        assert deal["store_count"] == 2

    def test_a_used_unit_does_not_manufacture_a_saving(self, client, db_session):
        """
        Otherwise every product with one second-hand listing looks like a
        bargain, and the "saving" is really the cost of buying a worn phone.
        """
        product = self._product(db_session, "Used Trap Phone")
        self._stock(db_session, product, "NewOnly", 800)
        self._stock(db_session, product, "UsedShop", 400, condition="used")

        deals = client.get("/products/deals").json()
        assert [d["id"] for d in deals] == []

    def test_deals_are_ordered_by_how_much_is_saved(self, client, db_session):
        small = self._product(db_session, "Small Gap Phone")
        self._stock(db_session, small, "A", 800)
        self._stock(db_session, small, "B", 820)

        large = self._product(db_session, "Large Gap Phone")
        self._stock(db_session, large, "A", 500)
        self._stock(db_session, large, "B", 900)

        deals = client.get("/products/deals").json()
        ids = [d["id"] for d in deals]
        assert ids.index(large.id) < ids.index(small.id)

    def test_an_unverified_shop_cannot_invent_a_saving(self, client, db_session):
        """
        The verification gate applies here too. A fabricated 1 JOD listing
        would otherwise put its product straight onto the front page.
        """
        product = self._product(db_session, "Gate Test Phone")
        self._stock(db_session, product, "Real", 800)

        owner = client.post(
            "/auth/register",
            json={"email": "fake@example.com", "password": PASSWORD},
        )
        headers = {"Authorization": f"Bearer {owner.json()['access_token']}"}
        client.post(
            "/merchant/store",
            json={"name": "Unverified Shop", "phone": "0791234567"},
            headers=headers,
        )
        client.post(
            "/merchant/listings",
            json={"name": "Gate Test Phone", "price": 1, "condition": "new"},
            headers=headers,
        )

        deals = client.get("/products/deals").json()
        assert [d["id"] for d in deals] == []
