"""
Administrator authority: appointing other admins, and fixing merchant data.

Two things make this worth testing carefully. Role assignment is the only
route by which privilege is granted, so it is the first thing an attacker
reaches for. And the guards against locking every administrator out are
exactly the kind of code nobody exercises until the day it matters.
"""

import pytest

from app.models.price import PriceHistory
from app.models.user import User, UserRole

PASSWORD = "TestPass123"



def signup(client, email, kind="buyer"):
    response = client.post(
        "/auth/register",
        json={"email": email, "password": PASSWORD, "account_type": kind},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def make_admin(client, db_session, email):
    headers = signup(client, email)
    user = db_session.query(User).filter(User.email == email).first()
    user.role = UserRole.admin
    db_session.commit()
    return headers


def user_id(db_session, email):
    return db_session.query(User).filter(User.email == email).first().id


def role_of(db_session, email):
    db_session.expire_all()
    return db_session.query(User).filter(User.email == email).first().role


def open_shop(client, email, name):
    headers = signup(client, email, "merchant")
    response = client.post(
        "/merchant/store",
        json={"name": name, "phone": "0791234567"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return headers, response.json()


def add_listing(client, headers, price=800.0):
    response = client.post(
        "/merchant/listings",
        json={"name": "Apple iPhone 15 128GB Black", "price": price, "condition": "new"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- Appointing admins ------------------------------------------------------


class TestRoleManagement:
    def test_an_admin_can_appoint_another_admin(self, client, db_session):
        """
        Without this there is no second administrator, and the platform is one
        forgotten password away from having none.
        """
        admin = make_admin(client, db_session, "boss@example.com")
        signup(client, "deputy@example.com")

        response = client.patch(
            f"/admin/users/{user_id(db_session, 'deputy@example.com')}/role",
            json={"role": "admin"},
            headers=admin,
        )
        assert response.status_code == 200, response.text
        assert role_of(db_session, "deputy@example.com") == UserRole.admin

    def test_the_new_admin_really_has_the_power(self, client, db_session):
        admin = make_admin(client, db_session, "boss@example.com")
        deputy = signup(client, "deputy@example.com")
        assert client.get("/admin/users", headers=deputy).status_code == 403

        client.patch(
            f"/admin/users/{user_id(db_session, 'deputy@example.com')}/role",
            json={"role": "admin"},
            headers=admin,
        )
        assert client.get("/admin/users", headers=deputy).status_code == 200

    def test_an_admin_can_promote_a_shopper_to_merchant(self, client, db_session):
        admin = make_admin(client, db_session, "boss@example.com")
        signup(client, "shopper@example.com")
        client.patch(
            f"/admin/users/{user_id(db_session, 'shopper@example.com')}/role",
            json={"role": "merchant"},
            headers=admin,
        )
        assert role_of(db_session, "shopper@example.com") == UserRole.merchant

    def test_an_admin_cannot_change_their_own_role(self, client, db_session):
        """Demoting yourself is unrecoverable from inside the application."""
        admin = make_admin(client, db_session, "boss@example.com")
        response = client.patch(
            f"/admin/users/{user_id(db_session, 'boss@example.com')}/role",
            json={"role": "user"},
            headers=admin,
        )
        assert response.status_code == 400
        assert role_of(db_session, "boss@example.com") == UserRole.admin

    def test_the_last_admin_cannot_be_demoted(self, client, db_session):
        """
        A platform with zero admins cannot appoint one. The only way back is
        surgery on the database.
        """
        first = make_admin(client, db_session, "first@example.com")
        second = make_admin(client, db_session, "second@example.com")

        # Second demotes first -- fine, one admin remains.
        assert (
            client.patch(
                f"/admin/users/{user_id(db_session, 'first@example.com')}/role",
                json={"role": "user"},
                headers=second,
            ).status_code
            == 200
        )
        # Now the demoted account has no power to demote anyone.
        assert (
            client.patch(
                f"/admin/users/{user_id(db_session, 'second@example.com')}/role",
                json={"role": "user"},
                headers=first,
            ).status_code
            == 403
        )
        assert role_of(db_session, "second@example.com") == UserRole.admin

    def test_a_third_admin_can_demote_down_to_one_but_not_zero(
        self, client, db_session
    ):
        a = make_admin(client, db_session, "a@example.com")
        make_admin(client, db_session, "b@example.com")
        make_admin(client, db_session, "c@example.com")

        assert (
            client.patch(
                f"/admin/users/{user_id(db_session, 'b@example.com')}/role",
                json={"role": "user"},
                headers=a,
            ).status_code
            == 200
        )
        assert (
            client.patch(
                f"/admin/users/{user_id(db_session, 'c@example.com')}/role",
                json={"role": "user"},
                headers=a,
            ).status_code
            == 200
        )
        # `a` is now the last admin and cannot demote itself.
        assert (
            client.patch(
                f"/admin/users/{user_id(db_session, 'a@example.com')}/role",
                json={"role": "user"},
                headers=a,
            ).status_code
            == 400
        )

    @pytest.mark.parametrize("who", ["buyer", "merchant"])
    def test_a_non_admin_cannot_grant_roles(self, client, db_session, who):
        make_admin(client, db_session, "boss@example.com")
        attacker = signup(client, "attacker@example.com", who)
        response = client.patch(
            f"/admin/users/{user_id(db_session, 'attacker@example.com')}/role",
            json={"role": "admin"},
            headers=attacker,
        )
        assert response.status_code == 403
        assert role_of(db_session, "attacker@example.com") != UserRole.admin

    @pytest.mark.parametrize("bogus", ["superuser", "root", "ADMIN", "", None, 7])
    def test_only_the_three_real_roles_are_accepted(self, client, db_session, bogus):
        admin = make_admin(client, db_session, "boss@example.com")
        signup(client, "target@example.com")
        response = client.patch(
            f"/admin/users/{user_id(db_session, 'target@example.com')}/role",
            json={"role": bogus},
            headers=admin,
        )
        assert response.status_code == 422

    def test_demoting_a_merchant_does_not_delete_their_shop(
        self, client, db_session
    ):
        """
        A role change is not a takedown. Conflating them would make an admin
        tidying up roles silently destroy a shop's listings.
        """
        admin = make_admin(client, db_session, "boss@example.com")
        headers, store = open_shop(client, "shop@example.com", "Demoted Shop")
        add_listing(client, headers)

        client.patch(
            f"/admin/users/{user_id(db_session, 'shop@example.com')}/role",
            json={"role": "user"},
            headers=admin,
        )

        listings = client.get(
            f"/admin/stores/{store['id']}/listings", headers=admin
        ).json()
        assert len(listings["listings"]) == 1


# --- Fixing merchant data ---------------------------------------------------


class TestAdminListingModeration:
    """
    A wrong price is the one thing a comparison site must never show, and
    "email the shop and wait" is not a remedy.
    """

    def test_an_admin_can_correct_any_shops_price(self, client, db_session):
        admin = make_admin(client, db_session, "boss@example.com")
        headers, _ = open_shop(client, "shop@example.com", "Typo Shop")
        listing = add_listing(client, headers, price=8000.0)

        response = client.patch(
            f"/admin/listings/{listing['id']}",
            json={"price": 800.0},
            headers=admin,
        )
        assert response.status_code == 200, response.text
        assert response.json()["price"] == 800.0

        rows = client.get("/merchant/listings", headers=headers).json()
        assert rows[0]["price"] == 800.0

    def test_an_admin_correction_is_recorded_in_history(self, client, db_session):
        """Hiding it would leave a gap in the series with no explanation."""
        admin = make_admin(client, db_session, "boss@example.com")
        headers, _ = open_shop(client, "shop@example.com", "History Shop")
        listing = add_listing(client, headers, price=900.0)

        client.patch(
            f"/admin/listings/{listing['id']}", json={"price": 850.0}, headers=admin
        )
        assert db_session.query(PriceHistory).count() == 1

    def test_an_admin_can_take_a_listing_out_of_stock(self, client, db_session):
        admin = make_admin(client, db_session, "boss@example.com")
        headers, _ = open_shop(client, "shop@example.com", "Stock Shop")
        listing = add_listing(client, headers)

        client.patch(
            f"/admin/listings/{listing['id']}",
            json={"availability": False},
            headers=admin,
        )
        rows = client.get("/merchant/listings", headers=headers).json()
        assert rows[0]["availability"] is False

    def test_an_admin_can_remove_any_listing(self, client, db_session):
        admin = make_admin(client, db_session, "boss@example.com")
        headers, _ = open_shop(client, "shop@example.com", "Removal Shop")
        listing = add_listing(client, headers)

        response = client.delete(
            f"/admin/listings/{listing['id']}", headers=admin
        )
        assert response.status_code == 204
        assert client.get("/merchant/listings", headers=headers).json() == []

    @pytest.mark.parametrize("who", ["buyer", "merchant"])
    def test_a_non_admin_cannot_moderate_listings(self, client, db_session, who):
        make_admin(client, db_session, "boss@example.com")
        owner, _ = open_shop(client, "victim@example.com", "Victim Shop")
        listing = add_listing(client, owner, price=900.0)

        attacker = signup(client, "attacker@example.com", who)
        assert (
            client.patch(
                f"/admin/listings/{listing['id']}",
                json={"price": 1.0},
                headers=attacker,
            ).status_code
            == 403
        )
        assert (
            client.delete(
                f"/admin/listings/{listing['id']}", headers=attacker
            ).status_code
            == 403
        )
        rows = client.get("/merchant/listings", headers=owner).json()
        assert rows[0]["price"] == 900.0

    def test_admin_moderation_still_validates_the_price(self, client, db_session):
        """An administrator is trusted, not infallible."""
        admin = make_admin(client, db_session, "boss@example.com")
        headers, _ = open_shop(client, "shop@example.com", "Validation Shop")
        listing = add_listing(client, headers, price=800.0)

        for bad in (0, -5, 10_000_000):
            assert (
                client.patch(
                    f"/admin/listings/{listing['id']}",
                    json={"price": bad},
                    headers=admin,
                ).status_code
                == 422
            )
        rows = client.get("/merchant/listings", headers=headers).json()
        assert rows[0]["price"] == 800.0

    def test_moderating_a_missing_listing_is_a_404(self, client, db_session):
        admin = make_admin(client, db_session, "boss@example.com")
        assert (
            client.patch(
                "/admin/listings/999999", json={"price": 5.0}, headers=admin
            ).status_code
            == 404
        )
