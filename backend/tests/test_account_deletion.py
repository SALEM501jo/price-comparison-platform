"""
Account deletion: the right to erasure, and what it must not take with it.

Jordan's PDPL No. 24 of 2023 gives a person the right to leave. The hard part
is not removing the user row, it is everything that row touches, so most of
these tests are about what SURVIVES:

  - a merchant's shop leaves the site without its listings, prices or history
    being destroyed, and above all WITHOUT BEING PUBLISHED -- an ownerless
    store reads as a scraped store to Store.visible_to_shoppers(), which would
    turn "delete my account" into a way to push unverified prices live
  - contact_events, the only billing evidence this platform produces, are
    untouched
  - a support ticket keeps its text and loses the address that named the
    person who wrote it -- and only the tickets that are provably theirs

The suite runs on SQLite with foreign keys unenforced, so no ON DELETE clause
fires here. That is deliberate in these tests: they pass only if the deletion
does its work in Python, which is the same work Postgres would otherwise do
differently.
"""

import pytest

from app.models.alias import ProductAlias
from app.models.contact_event import ContactEvent
from app.models.email_token import EmailToken
from app.models.listing_photo import ListingPhoto
from app.models.price import Price, PriceAlert, WishlistItem
from app.models.product import Product
from app.models.refresh_token import RefreshToken
from app.models.store import Store
from app.models.support import SupportMessage
from app.models.user import User

PASSWORD = "LeavePass123"
LEAVER = "leaver@example.com"
COOKIE = "refresh_token"


def register(client, email=LEAVER):
    response = client.post(
        "/auth/register", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def delete_account(client, headers, email=LEAVER):
    """DELETE with a body -- httpx's .delete() takes no json= argument."""
    return client.request(
        "DELETE", "/auth/me", json={"email": email}, headers=headers
    )


@pytest.fixture
def product(db_session):
    """A scraped store with one product and one price, to hang a user off."""
    store = Store(name="DNA Jordan", website="dna.jo", is_active=1)
    item = Product(canonical_name="iPhone 15 128GB Black", brand="apple")
    db_session.add_all([store, item])
    db_session.commit()

    alias = ProductAlias(
        product_id=item.id,
        store_id=store.id,
        store_product_name="Apple iPhone 15 128GB Black",
        store_product_id="DNA-1",
    )
    db_session.add(alias)
    db_session.commit()
    db_session.add(Price(alias_id=alias.id, price=799.0, delivery_cost=0.0))
    db_session.commit()
    return item


@pytest.fixture
def populated(client, db_session, product):
    """
    An account with one of everything that hangs off a user.

    No single fixture in the suite builds this, and a deletion test that runs
    against a bare account proves only that the user row goes.
    """
    headers = register(client)

    assert client.post(
        f"/prices/wishlist/{product.id}", headers=headers
    ).status_code == 201
    assert client.post(
        "/prices/alerts",
        json={"product_id": product.id, "target_price": 700.0},
        headers=headers,
    ).status_code == 201
    assert client.post(
        "/support/contact",
        json={
            "email": LEAVER,
            "subject": "Wrong price",
            "body": "The price on this listing is out of date.",
        },
        headers=headers,
    ).status_code == 202

    # A second session, so "revoke everything" has more than one row to prove
    # itself against.
    assert client.post("/auth/refresh").status_code == 200

    user = db_session.query(User).filter(User.email == LEAVER).first()
    assert db_session.query(EmailToken).filter(
        EmailToken.user_id == user.id
    ).count() == 1, "registration should have issued a verification token"
    assert db_session.query(RefreshToken).filter(
        RefreshToken.user_id == user.id
    ).count() == 2

    return headers, user


@pytest.fixture
def shop(client, db_session):
    """
    A merchant with an unverified store, one listing, a price and a photo.

    Built through the real API up to the photo, which is only reachable
    through the image pipeline and is inserted directly instead.
    """
    headers = register(client, "merchant@example.com")
    created = client.post(
        "/merchant/store",
        json={
            "name": "Jado Mobile",
            "phone": "0791234567",
            "whatsapp": "0791234567",
            "facebook_url": "https://facebook.com/jadomobile",
            "instagram_url": "https://instagram.com/jadomobile",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text

    listing = client.post(
        "/merchant/listings",
        json={"name": "Apple iPhone 15 128GB Black", "price": 780.0},
        headers=headers,
    )
    assert listing.status_code == 201, listing.text

    store = db_session.query(Store).filter(Store.name == "Jado Mobile").first()
    alias = (
        db_session.query(ProductAlias).filter(ProductAlias.store_id == store.id).first()
    )
    db_session.add(
        ListingPhoto(
            alias_id=alias.id,
            content_type="image/webp",
            data=b"not-really-webp",
            width=600,
            height=600,
            byte_size=15,
            checksum="0" * 64,
        )
    )
    db_session.commit()
    return headers, store, alias


# --- The confirmation -------------------------------------------------------


class TestConfirmation:
    def test_deletion_requires_a_token(self, client, populated):
        """Anonymous deletion would be a one-request account wipe."""
        headers, _ = populated

        response = client.request("DELETE", "/auth/me", json={"email": LEAVER})

        assert response.status_code == 401
        assert client.get("/auth/me", headers=headers).status_code == 200

    def test_a_different_address_does_not_delete_the_account(
        self, client, db_session, populated
    ):
        """
        The confirmation exists so a mis-click cannot destroy an account. If a
        wrong address still deleted it, the field would be decoration.
        """
        headers, user = populated

        response = delete_account(client, headers, email="someone@example.com")

        assert response.status_code == 400
        assert "email" in response.json()["detail"].lower()
        assert db_session.query(User).filter(User.id == user.id).first() is not None

    def test_the_confirmation_ignores_case_and_surrounding_space(
        self, client, db_session, populated
    ):
        """A phone keyboard capitalises, and a paste brings a trailing space."""
        headers, user = populated

        response = delete_account(client, headers, email="  Leaver@Example.COM ")

        assert response.status_code == 204, response.text
        assert db_session.query(User).filter(User.id == user.id).first() is None

    def test_a_password_is_never_asked_for(self, client):
        """
        An account created through a social login has no password at all, so
        confirming with one would lock out exactly the people this endpoint
        was built alongside. Pinned in the OpenAPI schema so a later "harden
        this" change cannot quietly reintroduce the requirement.
        """
        spec = client.get("/openapi.json").json()
        body = spec["paths"]["/auth/me"]["delete"]["requestBody"]
        ref = body["content"]["application/json"]["schema"]["$ref"]
        schema = spec["components"]["schemas"][ref.rsplit("/", 1)[-1]]

        assert set(schema["properties"]) == {"email"}


# --- What is erased ---------------------------------------------------------


class TestWhatIsErased:
    def test_everything_that_only_served_the_account_goes_with_it(
        self, client, db_session, populated
    ):
        headers, user = populated

        assert delete_account(client, headers).status_code == 204

        assert db_session.query(User).filter(User.id == user.id).first() is None
        for model in (RefreshToken, EmailToken, WishlistItem, PriceAlert):
            assert (
                db_session.query(model).filter(model.user_id == user.id).count() == 0
            ), f"{model.__name__} outlived the account"

    def test_another_account_is_untouched(self, client, db_session, populated, product):
        """
        Deletion is scoped by user id everywhere. A filter that was forgotten,
        or written against the email string instead, would take a stranger's
        rows with it.
        """
        headers, user = populated
        other = register(client, "stays@example.com")
        assert client.post(
            f"/prices/wishlist/{product.id}", headers=other
        ).status_code == 201

        assert delete_account(client, headers).status_code == 204

        survivor = db_session.query(User).filter(User.email == "stays@example.com").first()
        assert survivor is not None
        assert (
            db_session.query(WishlistItem)
            .filter(WishlistItem.user_id == survivor.id)
            .count()
            == 1
        )
        assert (
            db_session.query(RefreshToken)
            .filter(RefreshToken.user_id == survivor.id)
            .count()
            == 1
        )

    def test_the_address_is_free_to_register_again(self, client, populated):
        """No tombstone: a deleted account leaves no shadow record behind."""
        headers, _ = populated

        assert delete_account(client, headers).status_code == 204

        assert client.post(
            "/auth/register", json={"email": LEAVER, "password": PASSWORD}
        ).status_code == 201


# --- Support history --------------------------------------------------------


class TestSupportHistory:
    def test_the_ticket_survives_without_the_address_that_names_the_writer(
        self, client, db_session, populated
    ):
        """
        The message is the business record -- what was promised, what was
        refunded, who reported abuse. The reply-to address has no purpose once
        there is nobody to reply to, and it is the one column that would still
        identify a deleted person.
        """
        headers, user = populated

        assert delete_account(client, headers).status_code == 204

        ticket = db_session.query(SupportMessage).one()
        assert ticket.body == "The price on this listing is out of date."
        assert ticket.subject == "Wrong price"
        assert ticket.user_id is None
        assert ticket.email != LEAVER
        # Replaced, not blanked: the column is NOT NULL.
        assert ticket.email

        # AND THE REPLACEMENT MUST NOT BE DERIVED FROM THE ADDRESS. A keyed
        # digest of the email looks erased and is not: whoever holds the key
        # can recompute it for any address and confirm in one query whether
        # that person ever wrote in. This asserts the property rather than the
        # spelling -- the address must not be recoverable from what is left,
        # by us or by anyone who takes a copy of the database and the secret.
        from app.logging_config import pseudonymize

        assert ticket.email != pseudonymize(LEAVER)
        assert LEAVER.split("@")[0] not in ticket.email

    def test_a_message_from_the_same_address_but_a_different_sender_is_kept(
        self, client, db_session, populated
    ):
        """
        THE ATTACK: signup does not verify addresses, so scrubbing by email
        string would let anyone register a stranger's address, delete the
        account, and erase that stranger's support history. Scoped to user_id
        only, this row is untouched.
        """
        headers, user = populated
        db_session.add(
            SupportMessage(email=LEAVER, body="Sent by somebody else entirely.")
        )
        db_session.commit()

        assert delete_account(client, headers).status_code == 204

        kept = (
            db_session.query(SupportMessage)
            .filter(SupportMessage.body == "Sent by somebody else entirely.")
            .one()
        )
        assert kept.email == LEAVER


# --- Sessions ---------------------------------------------------------------


class TestSessions:
    def test_the_refresh_cookie_is_cleared(self, client, populated):
        """
        A deleted account whose refresh cookie still sits in the browser is a
        live account as far as the browser is concerned. The cookie is
        httpOnly and path-scoped, so nothing else can remove it.
        """
        headers, _ = populated
        assert client.cookies.get(COOKIE)

        response = delete_account(client, headers)

        assert response.status_code == 204
        assert "set-cookie" in response.headers
        assert not client.cookies.get(COOKIE)

    def test_a_refresh_token_captured_beforehand_no_longer_works(
        self, client, populated
    ):
        """Clearing the cookie is cosmetic if the token itself still refreshes."""
        headers, _ = populated
        stolen = client.cookies.get(COOKIE)

        assert delete_account(client, headers).status_code == 204

        client.cookies.clear()
        replay = client.post("/auth/refresh", json={"refresh_token": stolen})
        assert replay.status_code == 401

    def test_the_access_token_dies_with_the_account(self, client, populated):
        """
        Unlike logout there is no 15-minute window: get_current_user re-reads
        the user on every request, so the token stops working immediately.
        """
        headers, _ = populated

        assert delete_account(client, headers).status_code == 204

        assert client.get("/auth/me", headers=headers).status_code == 401


# --- The merchant case ------------------------------------------------------


class TestMerchantShop:
    def test_the_shop_is_retired_and_its_catalogue_is_kept(
        self, client, db_session, shop
    ):
        """
        Deleting the store would destroy live prices a shopper is mid-
        comparison on, price history that is market data rather than personal
        data, and the platform's own billing evidence. Retiring it removes the
        shop from the site and strips what actually identifies the merchant.
        """
        headers, store, alias = shop
        store_id, alias_id = store.id, alias.id

        assert delete_account(client, headers, "merchant@example.com").status_code == 204

        retired = db_session.query(Store).filter(Store.id == store_id).one()
        assert retired.is_active == 0
        assert retired.is_verified is False
        assert (retired.phone, retired.whatsapp) == (None, None)
        assert (retired.facebook_url, retired.instagram_url) == (None, None)
        assert retired.name != "Jado Mobile"

        assert db_session.query(ProductAlias).filter(ProductAlias.id == alias_id).count() == 1
        assert db_session.query(Price).filter(Price.alias_id == alias_id).count() == 1

    def test_deleting_the_owner_does_not_publish_an_unverified_shop(
        self, client, db_session, shop
    ):
        """
        THE REGRESSION THIS GUARDS: Store.visible_to_shoppers() treats
        owner_user_id IS NULL as "scraped store, no verification needed". The
        ORM releases that column on delete whether we ask it to or not, so
        without the deactivation this shop -- which no admin ever approved --
        would become publicly visible the moment its owner left. Registering a
        rival's name, inventing prices and deleting the account would be a way
        past the verification gate.
        """
        headers, store, _ = shop
        assert store.is_verified is False

        assert delete_account(client, headers, "merchant@example.com").status_code == 204

        visible = db_session.query(Store).filter(Store.visible_to_shoppers()).all()
        assert store.id not in [s.id for s in visible]

    def test_a_declined_shop_stays_declined(self, client, db_session, shop):
        """
        The worst version of the same bug: an admin turns down a fake claim,
        the account is then deleted, and the fake shop's prices go live.
        """
        from datetime import datetime, timezone

        headers, store, _ = shop
        store.rejected_at = datetime.now(timezone.utc)
        db_session.commit()

        assert delete_account(client, headers, "merchant@example.com").status_code == 204

        db_session.refresh(store)
        assert store.is_publicly_visible is False

    def test_contact_events_are_untouched(self, client, db_session, shop):
        """
        A merchant's taps are what a 10 JOD invoice is argued over, and the
        last billing period is usually unsettled when somebody leaves. They
        survive because the store row survives -- the table has no user column
        at all, so nothing else could reach them. Anyone reaching for
        passive_deletes=True on User.store to tidy up the cascade will delete
        these instead, and should fail here first.
        """
        headers, store, _ = shop
        db_session.add_all(
            [
                ContactEvent(store_id=store.id, channel="call"),
                ContactEvent(store_id=store.id, channel="whatsapp"),
            ]
        )
        db_session.commit()

        assert delete_account(client, headers, "merchant@example.com").status_code == 204

        assert (
            db_session.query(ContactEvent)
            .filter(ContactEvent.store_id == store.id)
            .count()
            == 2
        )

    def test_the_listing_photo_is_deleted(self, client, db_session, shop):
        """
        The one thing in the store subtree that goes. A shop photo is the
        merchant's own content, may show them or their premises, is the
        largest payload here, and can never be displayed again once the shop
        is off the site.
        """
        headers, _, alias = shop
        alias_id = alias.id
        assert db_session.query(ListingPhoto).filter(
            ListingPhoto.alias_id == alias_id
        ).count() == 1

        assert delete_account(client, headers, "merchant@example.com").status_code == 204

        assert db_session.query(ListingPhoto).filter(
            ListingPhoto.alias_id == alias_id
        ).count() == 0

    def test_the_shop_name_is_released(self, client, shop):
        """
        stores.name is UNIQUE. A retired row holding the name forever would
        block the same business from ever registering again, with no way out
        through the UI.
        """
        headers, _, _ = shop

        assert delete_account(client, headers, "merchant@example.com").status_code == 204

        reopened = register(client, "again@example.com")
        response = client.post(
            "/merchant/store",
            json={"name": "Jado Mobile", "phone": "0791111111"},
            headers=reopened,
        )
        assert response.status_code == 201, response.text

    def test_a_squatted_retirement_name_cannot_veto_the_deletion(
        self, client, db_session, shop
    ):
        """
        THE ATTACK THIS GUARDS: a stranger vetoing someone's right to erasure.

        `stores.name` is UNIQUE, and store ids are PUBLIC -- `store_id` is a
        field of the price and listing responses, so anyone can read the id of
        the shop they want to pin down. If the retirement name were derived
        from the id alone it would be perfectly predictable, and registering a
        shop under that exact name first would make the retirement UPDATE
        collide forever. The merchant could then never delete their account.

        Worse than a plain refusal: sessions are revoked BEFORE the store step,
        so every attempt would still log the victim out while leaving the
        account standing -- a right to erasure that a stranger can turn into a
        denial of service.
        """
        headers, store, _ = shop

        # The attacker takes the name the victim's shop would be renamed to.
        db_session.add(Store(name=f"Closed store #{store.id}", is_active=1))
        db_session.commit()

        assert delete_account(client, headers, "merchant@example.com").status_code == 204

        retired = db_session.query(Store).filter(Store.id == store.id).one()
        assert retired.owner_user_id is None
        assert retired.is_active == 0
        # It still says what it is, for the admin reading a list of inactive
        # ownerless rows -- it just is not guessable in advance.
        assert str(store.id) in retired.name
        assert retired.name != f"Closed store #{store.id}"

    def test_two_merchants_retiring_do_not_collide_with_each_other(
        self, client, db_session, shop
    ):
        """
        The unique column has to survive the ordinary case too: a suffix that
        made the name unguessable but constant would simply move the collision
        from an attacker to the second honest merchant who leaves.
        """
        headers, store, _ = shop
        assert delete_account(client, headers, "merchant@example.com").status_code == 204
        first = db_session.query(Store).filter(Store.id == store.id).one().name

        second = Store(name="Another Shop", is_active=1)
        db_session.add(second)
        db_session.commit()
        from app.services import account as account_service

        account_service._retire_store(db_session, second)
        db_session.commit()

        assert second.name != first
