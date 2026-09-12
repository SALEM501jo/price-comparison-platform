"""
Account deletion: erasure that does not take the catalogue with it.

WHY THIS EXISTS: Jordan's Personal Data Protection Law No. 24 of 2023 -- the
same law that shapes app/models/contact_event.py -- gives a person the right
to have their data erased, as does GDPR Article 17 for a European visitor.
Until this module there was no way for anyone to leave.

"Delete the user row" is not that right, and on this schema it is actively
dangerous. Three things are true here and none of them are visible from the
model file:

1. `db.delete(user)` does NOT delete a merchant's store. `User.store` carries
   no cascade, so SQLAlchemy de-associates the child first and emits
   `UPDATE stores SET owner_user_id = NULL` BEFORE `DELETE FROM users`. The
   `ON DELETE CASCADE` in the migration never fires, because by the time the
   user row goes there is nothing pointing at it.

2. An orphaned store is PUBLISHED, not hidden. `Store.visible_to_shoppers()`
   reads `owner_user_id IS NULL` as "scraped store, no verification needed",
   so releasing the owner promotes a pending -- or admin-DECLINED -- claim to
   a live shop. Deleting your account would publish the listings you invented
   under a rival's name, past the one gate that exists to stop exactly that.

3. The personal data on a store row is the contact columns, not the prices.
   Deleting the store would take the whole subtree with it -- listings, live
   prices a shopper is mid-comparison on, price history that is market data
   about a product rather than about a person, and the contact_events that
   are the platform's own evidence for an unpaid invoice.

So a merchant's store is RETIRED, never deleted and never orphaned. That gets
the erasure (the contact details are what identify a sole trader) without the
collateral damage, and `is_active = 0` fails visibility on its own arm of
`visible_to_shoppers()`, independent of the owner column -- which is what
closes the publication hole above.

EVERY STEP IS DONE EXPLICITLY IN PYTHON, never left to a database cascade.
The suite runs on SQLite without `PRAGMA foreign_keys=ON`, so no ON DELETE
clause fires under test at all: a deletion routine that leaned on the
cascades would be untestable, and a passing test would prove nothing about
the Postgres this runs on in production.
"""

import secrets
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.alias import ProductAlias
from app.models.listing_photo import ListingPhoto
from app.models.store import Store
from app.models.support import SupportMessage
from app.models.user import User
from app.services import tokens as token_service


@dataclass(frozen=True)
class DeletionSummary:
    """What the deletion actually touched, for the audit line."""

    sessions_revoked: int
    support_messages_scrubbed: int
    store_retired: bool


def _scrub_support_messages(db: Session, user_id: int) -> int:
    """
    Keep the ticket, destroy the reply-to address.

    A support thread is what proves what was promised, what was refunded and
    who reported abuse, so the message stays. The address does not: with
    nobody left to reply to it has no purpose, and it is the one column in
    this schema that would still name a deleted person -- `user_id` is SET
    NULL by the foreign key, but `email` is a separate column populated from
    the form body and survives untouched.

    Overwritten rather than set to NULL because the column is `nullable=False`.

    THE REPLACEMENT IS RANDOM, NOT DERIVED FROM THE ADDRESS. The obvious
    choice is `pseudonymize()` from app/logging_config.py, and it is the wrong
    one: it is an HMAC keyed on `jwt_secret_key`, so the address is not
    destroyed but ENCRYPTED under a key the platform can never throw away --
    anyone holding it can recompute the digest for any address and confirm, in
    one indexed query, whether that person ever wrote in. That is a
    pseudonym, which is still personal data, and this function is called
    because somebody exercised a right to have their data ERASED. It is also
    what the privacy policy promises. `pseudonymize` is scoped to LOGGING,
    where the values are ephemeral and correlating two lines in one request is
    the whole point; reusing it at rest quietly changes what it means.

    One random value PER DELETION, not per row, so the tickets of one person
    stay grouped -- which is the only property the support workflow actually
    needed -- without that group key saying anything about who they were.

    SCOPED BY user_id ONLY, NEVER BY MATCHING THE EMAIL STRING. Signup does
    not require a verified address, so an email-match scrub would let anyone
    register victim@example.com, delete the account, and erase a stranger's
    support history. The cost is that messages sent while logged out keep
    their address -- correct, because we cannot prove those are theirs.
    """
    rows = db.query(SupportMessage).filter(SupportMessage.user_id == user_id).all()
    # Minted once, outside the loop: this is the group key for one person's
    # tickets, and a per-row value would scatter them.
    scrubbed = f"deleted-{secrets.token_hex(8)}@removed.invalid"
    for row in rows:
        row.email = scrubbed
        # Set here as well as by the FK's ON DELETE SET NULL: under SQLite the
        # foreign key is not enforced, so without this the tests would observe
        # a user_id still pointing at a user who no longer exists.
        row.user_id = None
    return len(rows)


def _retire_store(db: Session, store: Store) -> None:
    """
    Take the shop off the site and strip its contact details, keeping the
    listings, prices and history that belong to the catalogue.

    ORDER MATTERS: `is_active` goes to 0 before `owner_user_id` is released.
    Releasing the owner is what makes the row look like a scraped store to
    `visible_to_shoppers()`, and the deactivation is the only thing standing
    in front of that -- so it is set first and never conditionally.

    The rename does two jobs. `stores.name` is UNIQUE, so a retired row would
    otherwise reserve that shop's name forever and block the same business
    from registering again -- the first person that bites would have no way
    out through the UI. It also removes the name itself, which for a Jordanian
    sole trader is frequently their own, and it labels the row so the next
    admin looking at an inactive ownerless store knows it is a closed shop
    rather than a scraped feed waiting to be switched back on.
    """
    # The one thing in this subtree that is deleted rather than kept. A photo
    # is the merchant's own content, may show them or their premises, is by
    # far the largest payload here, and can never be displayed again once the
    # shop is retired -- so keeping it buys nothing and answers "what happened
    # to my photos" with the wrong answer.
    # A SUBQUERY, NOT A LIST OF IDS. Reading every alias id into Python and
    # splicing them into one IN (...) puts a bind parameter per listing on the
    # statement, and nothing caps how many listings a merchant may create --
    # so a large enough shop exceeds the driver's parameter ceiling and its
    # owner can no longer delete their account at all. The ceiling is reached
    # by ordinary success, which is the worst way to find a limit.
    owned_aliases = (
        db.query(ProductAlias.id)
        .filter(ProductAlias.store_id == store.id)
        .scalar_subquery()
    )
    db.query(ListingPhoto).filter(ListingPhoto.alias_id.in_(owned_aliases)).delete(
        synchronize_session=False
    )

    store.is_active = 0
    store.is_verified = False
    store.verified_at = None

    store.phone = None
    store.whatsapp = None
    store.facebook_url = None
    store.instagram_url = None
    # THE SUFFIX IS NOT DECORATION -- IT IS WHAT KEEPS ERASURE POSSIBLE.
    # stores.name is UNIQUE, and store ids are public: store_id is a field of
    # the price and listing responses, so anyone can read the id of the shop
    # they want to target. A name derived from the id alone is therefore
    # PREDICTABLE, and an attacker who registers a shop under that exact name
    # first makes this UPDATE collide forever -- that merchant can then never
    # delete their account, and because sessions are revoked before this step,
    # every attempt still logs them out while leaving the account standing.
    # A right to erasure that a stranger can veto is not a right at all.
    #
    # Random rather than a retry loop: a collision cannot be resolved by
    # trying again with the same input, and a loop that appends until it fits
    # is a slower way of writing this line.
    store.name = f"Closed store #{store.id} ({secrets.token_hex(4)})"

    # Last, and only now that the row is invisible on its own account.
    store.owner_user_id = None


def delete_account(db: Session, user: User) -> DeletionSummary:
    """
    Erase an account. Irreversible: there is no tombstone and the address is
    immediately free to register again.

    No soft delete on purpose. A `deleted_at` flag would keep `users.email` --
    the very identifier the person asked to be rid of -- and every query in
    the codebase would need a predicate it does not have today, where one
    forgotten filter leaks a deleted account back into the product.

    Sessions are revoked FIRST, and deliberately not as part of the same
    transaction as the rest: `revoke_all_for_user` commits, and the ORM
    cascade then hard-deletes the refresh_tokens rows a moment later. Revoking
    afterwards would be a no-op against rows that no longer exist, and the
    security log would have no record that the sessions ever ended. If a later
    step fails the account survives with dead sessions, which is the failure
    worth having.
    """
    user_id = user.id

    sessions_revoked = token_service.revoke_all_for_user(
        db, user_id, reason="account_deleted"
    )

    scrubbed = _scrub_support_messages(db, user_id)

    store = db.query(Store).filter(Store.owner_user_id == user_id).first()
    if store is not None:
        _retire_store(db, store)

    # refresh_tokens, email_tokens, wishlist_items and price_alerts go with
    # the user through `cascade="all, delete-orphan"` on the relationships, so
    # they are deleted by the ORM and not by the database -- which is what
    # makes them observable under SQLite in the tests.
    #
    # contact_events are not reachable from here at all: the table has no user
    # column by design (see app/models/contact_event.py) and its only link to
    # a person is through stores.id, which this function never deletes. That
    # is structural, not luck, and test_account_deletion.py pins it.
    db.delete(user)
    db.commit()

    return DeletionSummary(
        sessions_revoked=sessions_revoked,
        support_messages_scrubbed=scrubbed,
        store_retired=store is not None,
    )
