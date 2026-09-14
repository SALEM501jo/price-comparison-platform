"""
Merchant self-service: registration, listings, verification, and the
authorisation boundaries between shops.

The interesting tests here are the negative ones. A merchant legitimately
writes data that strangers read, which creates two risks the rest of the
platform does not have: one shop rewriting another's prices, and an
unverified claim reaching shoppers as if it were a real shop.
"""

import pytest

from app.models.alias import ProductAlias
from app.models.price import Price
from app.models.product import Product
from app.models.store import Store
from app.models.user import User, UserRole

PASSWORD = "TestPass123"



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
    # Role is read from the database on every request, so the token issued
    # before the change is still the right one to keep using.
    return headers


def open_shop(client, email, name, **extra):
    headers = signup(client, email)
    payload = {"name": name, "phone": "0791234567"}
    payload.update(extra)
    response = client.post("/merchant/store", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return headers, response.json()


def add_listing(client, headers, name="Apple iPhone 15 128GB Black", price=790.0):
    response = client.post(
        "/merchant/listings",
        json={"name": name, "price": price},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- Registration -----------------------------------------------------------


class TestStoreRegistration:
    def test_a_shopper_becomes_a_merchant_by_claiming_a_store(
        self, client, db_session
    ):
        headers = signup(client, "jado@example.com")
        assert (
            db_session.query(User)
            .filter(User.email == "jado@example.com")
            .first()
            .role
            == UserRole.user
        )

        response = client.post(
            "/merchant/store",
            json={"name": "Jado Mobile", "phone": "0791757546"},
            headers=headers,
        )
        assert response.status_code == 201, response.text

        db_session.expire_all()
        assert (
            db_session.query(User)
            .filter(User.email == "jado@example.com")
            .first()
            .role
            == UserRole.merchant
        )

    def test_a_new_store_is_not_verified(self, client):
        _, store = open_shop(client, "flick@example.com", "Flick Mobile")
        assert store["is_verified"] is False
        assert store["verified_at"] is None

    def test_one_store_per_account(self, client):
        headers, _ = open_shop(client, "one@example.com", "First Shop")
        second = client.post(
            "/merchant/store",
            json={"name": "Second Shop", "phone": "0791234567"},
            headers=headers,
        )
        assert second.status_code == 409

    def test_store_names_do_not_collide_on_case(self, client):
        """"Jado Mobile" and "jado mobile" are one shop, not two."""
        open_shop(client, "a@example.com", "Jado Mobile")
        headers = signup(client, "impostor@example.com")
        response = client.post(
            "/merchant/store",
            json={"name": "jado mobile", "phone": "0791234567"},
            headers=headers,
        )
        assert response.status_code == 409

    def test_registration_requires_a_signed_in_account(self, client):
        response = client.post(
            "/merchant/store", json={"name": "Anonymous Shop", "phone": "0791234567"}
        )
        assert response.status_code in (401, 403)

    def test_admin_claiming_a_store_keeps_admin(self, client, db_session):
        """Promotion must never quietly reduce a wider authority."""
        headers = make_admin(client, db_session)
        client.post(
            "/merchant/store",
            json={"name": "Admin Test Shop", "phone": "0791234567"},
            headers=headers,
        )
        db_session.expire_all()
        assert (
            db_session.query(User)
            .filter(User.email == "admin@example.com")
            .first()
            .role
            == UserRole.admin
        )


# --- Input validation -------------------------------------------------------


class TestUntrustedMerchantInput:
    """A scraped feed we chose to trust; this input arrives from strangers."""

    @pytest.mark.parametrize("price", [0, -1, -0.001, 10_000_000])
    def test_impossible_prices_are_rejected(self, client, price):
        headers, _ = open_shop(client, "p@example.com", "Price Shop")
        response = client.post(
            "/merchant/listings",
            json={"name": "iPhone 15 128GB", "price": price},
            headers=headers,
        )
        assert response.status_code == 422

    @pytest.mark.parametrize(
        "phone", ["12345", "notaphone", "0591234567", "+15551234567", "079123456789"]
    )
    def test_non_jordanian_numbers_are_rejected(self, client, phone):
        headers = signup(client, f"phone{abs(hash(phone))}@example.com")
        response = client.post(
            "/merchant/store", json={"name": f"Shop {phone}", "phone": phone},
            headers=headers,
        )
        assert response.status_code == 422

    @pytest.mark.parametrize(
        "written, stored",
        [
            ("0791234567", "0791234567"),
            ("+962791234567", "0791234567"),
            ("00962791234567", "0791234567"),
            ("079 123 4567", "0791234567"),
            ("079-123-4567", "0791234567"),
        ],
    )
    def test_one_number_has_one_spelling(self, client, written, stored):
        headers = signup(client, f"n{abs(hash(written))}@example.com")
        response = client.post(
            "/merchant/store",
            json={"name": f"Shop {abs(hash(written))}", "phone": written},
            headers=headers,
        )
        assert response.status_code == 201, response.text
        assert response.json()["phone"] == stored

    @pytest.mark.parametrize(
        "url",
        [
            "https://evil.example.com/phish",
            "http://facebook.com.evil.example/x",
            "javascript:alert(1)",
            "https://notfacebook.com/shop",
        ],
    )
    def test_only_a_real_facebook_page_is_accepted(self, client, url):
        """
        The store profile is rendered as a link on every product page it
        appears on. Accepting any URL would publish an open redirect.
        """
        headers = signup(client, f"u{abs(hash(url))}@example.com")
        response = client.post(
            "/merchant/store",
            json={
                "name": f"Shop {abs(hash(url))}",
                "phone": "0791234567",
                "facebook_url": url,
            },
            headers=headers,
        )
        assert response.status_code == 422

    def test_a_real_facebook_page_is_accepted(self, client):
        _, store = open_shop(
            client,
            "fb@example.com",
            "FB Shop",
            facebook_url="https://www.facebook.com/Flickmobile/",
        )
        assert store["facebook_url"] == "https://www.facebook.com/Flickmobile/"


# --- Authorisation between merchants ---------------------------------------


class TestOneMerchantCannotTouchAnother:
    """
    The bug class this feature introduces, and the reason every route resolves
    the store from the signed-in user rather than from an id in the URL.
    """

    def test_a_merchant_cannot_edit_a_rivals_price(self, client):
        rival_headers, _ = open_shop(client, "rival@example.com", "Rival Shop")
        listing = add_listing(client, rival_headers, price=900.0)

        attacker_headers, _ = open_shop(client, "attacker@example.com", "Attacker Shop")
        response = client.patch(
            f"/merchant/listings/{listing['id']}",
            json={"price": 1.0},
            headers=attacker_headers,
        )
        assert response.status_code == 404

    def test_a_merchant_cannot_delete_a_rivals_listing(self, client):
        rival_headers, _ = open_shop(client, "rival2@example.com", "Rival Two")
        listing = add_listing(client, rival_headers)

        attacker_headers, _ = open_shop(client, "attacker2@example.com", "Attacker Two")
        response = client.delete(
            f"/merchant/listings/{listing['id']}", headers=attacker_headers
        )
        assert response.status_code == 404

    def test_the_rivals_price_is_unchanged_after_a_failed_attempt(
        self, client, db_session
    ):
        rival_headers, _ = open_shop(client, "rival3@example.com", "Rival Three")
        listing = add_listing(client, rival_headers, price=900.0)

        attacker_headers, _ = open_shop(client, "attacker3@example.com", "Attacker Three")
        client.patch(
            f"/merchant/listings/{listing['id']}",
            json={"price": 1.0},
            headers=attacker_headers,
        )

        still = client.get("/merchant/listings", headers=rival_headers).json()
        assert [row["price"] for row in still] == [900.0]

    def test_listings_show_only_the_callers_own_store(self, client):
        a_headers, _ = open_shop(client, "sa@example.com", "Shop A")
        add_listing(client, a_headers, name="Samsung Galaxy S24 256GB", price=700.0)

        b_headers, _ = open_shop(client, "sb@example.com", "Shop B")
        add_listing(client, b_headers, name="Apple iPhone 15 128GB Black", price=800.0)

        b_listings = client.get("/merchant/listings", headers=b_headers).json()
        assert len(b_listings) == 1
        assert "iPhone" in b_listings[0]["name"]

    def test_a_missing_listing_is_indistinguishable_from_someone_elses(self, client):
        """A 403 would confirm the id exists. A merchant has no business knowing."""
        headers, _ = open_shop(client, "probe@example.com", "Probe Shop")
        assert (
            client.patch(
                "/merchant/listings/999999", json={"price": 5.0}, headers=headers
            ).status_code
            == 404
        )


class TestRoleBoundary:
    def test_a_plain_shopper_cannot_reach_merchant_routes(self, client):
        headers = signup(client, "shopper@example.com")
        for method, path in [
            ("get", "/merchant/store"),
            ("get", "/merchant/listings"),
        ]:
            response = getattr(client, method)(path, headers=headers)
            assert response.status_code == 403, path

    def test_a_merchant_without_a_store_gets_404_not_500(self, client, db_session):
        """The role can be granted before a store exists; the routes must cope."""
        headers = signup(client, "roleonly@example.com")
        user = db_session.query(User).filter(User.email == "roleonly@example.com").first()
        user.role = UserRole.merchant
        db_session.commit()
        assert client.get("/merchant/store", headers=headers).status_code == 404

    def test_the_store_name_cannot_be_changed_by_its_owner(self, client):
        """
        The name is what an admin verified and what shoppers recognise. If it
        were editable, a store could pass review as itself and then become
        somebody else.
        """
        headers, store = open_shop(client, "rename@example.com", "Original Name")
        client.patch(
            "/merchant/store",
            json={"name": "Something Else", "phone": "0791111111"},
            headers=headers,
        )
        assert client.get("/merchant/store", headers=headers).json()["name"] == (
            "Original Name"
        )


# --- Verification gate ------------------------------------------------------


class TestVerificationGate:
    """
    The control that makes a claim mean something. Anyone can register and
    call themselves a well-known shop; nothing they submit reaches a shopper
    until an admin says the claim is real.
    """

    def test_an_unverified_stores_price_is_invisible_on_the_product_page(
        self, client, db_session
    ):
        headers, _ = open_shop(client, "hidden@example.com", "Unverified Shop")
        listing = add_listing(client, headers, price=1.0)
        product_id = listing["matched_product_id"]

        # Not an empty table: no page at all. The product's name is the shop's
        # own unreviewed text, and an empty 200 still published it.
        detail = client.get(f"/products/{product_id}")
        assert detail.status_code == 404
        assert "Unverified" not in detail.text

    def test_verifying_the_store_reveals_its_price(self, client, db_session):
        headers, store = open_shop(client, "reveal@example.com", "Reveal Shop")
        listing = add_listing(client, headers, price=555.0)
        product_id = listing["matched_product_id"]

        admin_headers = make_admin(client, db_session)
        approved = client.post(
            f"/admin/stores/{store['id']}/verify", headers=admin_headers
        )
        assert approved.status_code == 200, approved.text

        prices = client.get(f"/products/{product_id}").json()["prices"]
        assert [p["price"] for p in prices] == [555.0]
        assert prices[0]["is_merchant"] is True
        assert prices[0]["phone"] == "0791234567"

    def test_withdrawing_verification_hides_the_price_again(
        self, client, db_session
    ):
        headers, store = open_shop(client, "withdraw@example.com", "Withdraw Shop")
        listing = add_listing(client, headers, price=42.0)
        product_id = listing["matched_product_id"]
        admin_headers = make_admin(client, db_session)

        client.post(f"/admin/stores/{store['id']}/verify", headers=admin_headers)
        assert client.get(f"/products/{product_id}").json()["prices"] != []

        client.post(f"/admin/stores/{store['id']}/unverify", headers=admin_headers)
        assert client.get(f"/products/{product_id}").status_code == 404

    def test_an_unverified_price_does_not_move_the_lowest_price(
        self, client, db_session
    ):
        """
        The strongest form of the leak. Even with the row hidden from the
        table, an aggregate computed before filtering would still advertise
        a fabricated price as the best deal on the site.
        """
        store = Store(name="SmartBuy", website="smartbuy-me.com", is_verified=True)
        product = Product(
            canonical_name="Apple iPhone 15 128GB Black",
            brand="apple",
            match_category="phones",
            match_attributes={"brand": "apple", "model": "iphone 15"},
        )
        db_session.add_all([store, product])
        db_session.commit()
        alias = ProductAlias(
            product_id=product.id,
            store_id=store.id,
            store_product_name="Apple iPhone 15 128GB Black",
            store_product_id="SB-1",
            match_confidence=1.0,
        )
        db_session.add(alias)
        db_session.commit()
        db_session.add(Price(alias_id=alias.id, price=850.0, delivery_cost=0))
        db_session.commit()

        headers, _ = open_shop(client, "undercut@example.com", "Undercut Shop")
        add_listing(client, headers, name="Apple iPhone 15 128GB Black", price=1.0)

        results = client.get("/products/search", params={"q": "iPhone 15 128GB"})
        assert results.status_code == 200, results.text
        body = results.json()
        found = [
            item
            for tier in ("exact", "close", "similar")
            for item in body[tier]
            if item["id"] == product.id
        ]
        assert found, "the real product should still be found"
        assert found[0]["lowest_price"] == 850.0
        assert found[0]["store_count"] == 1

    def test_only_an_admin_can_verify(self, client):
        _, store = open_shop(client, "self@example.com", "Self Approve Shop")
        headers = signup(client, "nobody@example.com")
        response = client.post(
            f"/admin/stores/{store['id']}/verify", headers=headers
        )
        assert response.status_code == 403

    def test_a_merchant_cannot_verify_their_own_store(self, client):
        headers, store = open_shop(client, "selfmerch@example.com", "Self Merchant")
        response = client.post(
            f"/admin/stores/{store['id']}/verify", headers=headers
        )
        assert response.status_code == 403

    def test_a_scraped_store_cannot_be_verified(self, client, db_session):
        """Nothing to check: its prices come from its own public feed."""
        store = Store(name="SmartBuy", website="smartbuy-me.com", is_verified=True)
        db_session.add(store)
        db_session.commit()

        admin_headers = make_admin(client, db_session)
        response = client.post(
            f"/admin/stores/{store.id}/verify", headers=admin_headers
        )
        assert response.status_code == 400


# --- Listings join the catalogue -------------------------------------------


class TestListingsJoinTheCatalogue:
    """
    The point of the whole feature: a merchant's listing has to land on the
    SAME product a scraped listing did, or there are two rows with one price
    each instead of one row with two prices.
    """

    def test_a_merchant_listing_joins_an_existing_scraped_product(
        self, client, db_session
    ):
        store = Store(name="SmartBuy", website="smartbuy-me.com", is_verified=True)
        product = Product(
            canonical_name="Apple iPhone 15 128GB Black",
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
            store_product_name="Apple iPhone 15 128GB Black",
            store_product_id="SB-1",
            match_confidence=1.0,
        )
        db_session.add(alias)
        db_session.commit()
        db_session.add(Price(alias_id=alias.id, price=850.0, delivery_cost=0))
        db_session.commit()

        headers, store_row = open_shop(client, "join@example.com", "Joining Shop")
        listing = add_listing(
            client, headers, name="iPhone 15 128GB Black", price=790.0
        )

        assert listing["matched_product_id"] == product.id

        admin_headers = make_admin(client, db_session)
        client.post(f"/admin/stores/{store_row['id']}/verify", headers=admin_headers)

        prices = client.get(f"/products/{product.id}").json()["prices"]
        assert sorted(p["price"] for p in prices) == [790.0, 850.0]

    def test_resubmitting_a_name_updates_the_price_rather_than_duplicating(
        self, client
    ):
        headers, _ = open_shop(client, "resub@example.com", "Resubmit Shop")
        add_listing(client, headers, name="Apple iPhone 15 128GB Black", price=800.0)
        add_listing(client, headers, name="Apple iPhone 15 128GB Black", price=770.0)

        listings = client.get("/merchant/listings", headers=headers).json()
        assert len(listings) == 1
        assert listings[0]["price"] == 770.0

    def test_a_listing_the_engine_cannot_categorise_is_flagged_not_dropped(
        self, client
    ):
        """
        Silently discarding it would look like the form was broken. The
        merchant is told it will not appear in search instead.
        """
        headers, _ = open_shop(client, "junk@example.com", "Junk Shop")
        listing = add_listing(client, headers, name="Generic Carry Bag", price=15.0)
        assert listing["is_searchable"] is False

    def test_a_price_change_is_recorded_in_history(self, client, db_session):
        from app.models.price import PriceHistory

        headers, _ = open_shop(client, "hist@example.com", "History Shop")
        listing = add_listing(client, headers, price=800.0)
        client.patch(
            f"/merchant/listings/{listing['id']}",
            json={"price": 750.0},
            headers=headers,
        )
        assert db_session.query(PriceHistory).count() == 1

    def test_an_unverified_stores_price_history_is_hidden_too(self, client):
        """
        The price table was guarded but the history endpoint was not, so a
        hidden price was still readable one URL away -- along with the fact
        that the store existed at all.
        """
        headers, store = open_shop(client, "hist2@example.com", "History Leak Shop")
        listing = add_listing(client, headers, price=800.0)
        client.patch(
            f"/merchant/listings/{listing['id']}",
            json={"price": 700.0},
            headers=headers,
        )
        product_id = listing["matched_product_id"]

        history = client.get(f"/products/{product_id}/history")
        assert history.status_code == 200
        assert history.json() == []

    def test_history_appears_once_the_store_is_verified(self, client, db_session):
        headers, store = open_shop(client, "hist3@example.com", "History Shown Shop")
        listing = add_listing(client, headers, price=800.0)
        client.patch(
            f"/merchant/listings/{listing['id']}",
            json={"price": 700.0},
            headers=headers,
        )
        admin_headers = make_admin(client, db_session)
        client.post(f"/admin/stores/{store['id']}/verify", headers=admin_headers)

        history = client.get(
            f"/products/{listing['matched_product_id']}/history"
        ).json()
        assert len(history) == 1
        assert history[0]["store_name"] == "History Shown Shop"
