"""
Admin routes for merchant stores and their listings.

This is the gate that makes a merchant claim mean something.
Registration is open to anyone, so until a human confirms that the
account behind "Jado Mobile" is actually Jado Mobile, its prices stay
out of search -- otherwise the cheapest listing on the site would be
whatever a competitor felt like inventing under a rival's name.

Listing moderation lives here too, and deliberately NOT inside
routers/merchant.py: that module resolves the store from the signed-in
user and therefore cannot touch another shop's data, and an `if admin`
branch inside it would destroy exactly that guarantee.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.logging_config import get_security_logger
from app.models.alias import ProductAlias
from app.models.price import Price, PriceHistory
from app.models.product import Product
from app.models.store import Store
from app.models.user import User
from app.schemas.merchant import ListingUpdate
from app.services import contact_stats
from app.services.cache import bump_catalogue_version

router = APIRouter()
logger = get_security_logger("app.admin")


# --- Merchant store verification --------------------------------------------
#
# The gate that makes a merchant claim mean something. Registration is open to
# anyone, so until a human confirms that the account behind "Jado Mobile" is
# actually Jado Mobile, its prices stay out of search. Without this step the
# cheapest listing on the site would be whatever a competitor felt like
# inventing under a rival's name.


@router.get("/stores")
async def list_stores(
    pending_only: bool = False,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Every store, with what an admin needs in order to judge a claim."""
    query = db.query(Store)
    if pending_only:
        # "Pending" means NOT YET DECIDED. A declined claim is decided, and
        # leaving it here is what made the queue impossible to clear -- the
        # same bad claim was re-read on every visit because nothing recorded
        # that somebody had already said no.
        query = query.filter(
            Store.owner_user_id.isnot(None),
            Store.is_verified.is_(False),
            Store.rejected_at.is_(None),
        )

    stores = query.order_by(Store.id).all()

    # Two lookups for the whole page rather than two per row. The first
    # version ran a listing count and an owner fetch inside the loop, so
    # reviewing twenty shops meant forty-one queries -- the same N+1 shape
    # this codebase already removed from price_summary().
    store_ids = [store.id for store in stores]
    counts = dict(
        db.query(ProductAlias.store_id, func.count(ProductAlias.id))
        .filter(ProductAlias.store_id.in_(store_ids or [0]))
        .group_by(ProductAlias.store_id)
        .all()
    )
    owner_ids = [s.owner_user_id for s in stores if s.owner_user_id]
    owners = {
        user.id: user
        for user in db.query(User).filter(User.id.in_(owner_ids or [0])).all()
    }
    # A third bulk lookup, in the same spirit as the two above: one grouped
    # query for every store's taps rather than one per row.
    taps = contact_stats.totals_for_stores(db, store_ids)

    rows = []
    for store in stores:
        owner = owners.get(store.owner_user_id) if store.owner_user_id else None
        rows.append(
            {
                "id": store.id,
                "name": store.name,
                "is_merchant": store.is_merchant,
                "is_verified": store.is_verified,
                "verified_at": store.verified_at,
                "listing_count": counts.get(store.id, 0),
                "phone": store.phone,
                "whatsapp": store.whatsapp,
                "facebook_url": store.facebook_url,
                "instagram_url": store.instagram_url,
                # Derived on the model, so the screen cannot disagree with the
                # columns it is drawn from: verified | pending | declined.
                "review_status": store.review_status,
                "rejected_at": store.rejected_at,
                # The account behind the claim. An admin checking whether a
                # shop is genuine needs to know who is asking, and whether
                # they bothered to confirm their address.
                "owner_email": owner.email if owner else None,
                "owner_verified_email": bool(owner and owner.email_verified_at)
                if owner
                else None,
                "created_at": store.created_at,
                # How much traffic this shop is actually getting. An admin
                # judging a claim, or deciding what a shop is worth charging,
                # needs the number the merchant sees -- from the same query,
                # so the two screens can never disagree.
                #
                # TAPS, not calls: see app/models/contact_event.py.
                "contact_taps": taps.get(store.id, {}).get("total", 0),
                "contact_taps_by_channel": taps.get(store.id, {}).get(
                    "by_channel", {}
                ),
                "contact_taps_window_days": contact_stats.DEFAULT_WINDOW_DAYS,
            }
        )
    return rows


@router.post("/stores/{store_id}/verify")
async def verify_store(
    store_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Approve a merchant store, making its prices visible to shoppers."""
    store = db.query(Store).filter(Store.id == store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    if not store.is_merchant:
        raise HTTPException(
            status_code=400,
            detail="Scraped stores are not verified; they have no claim to check",
        )

    store.is_verified = True
    store.verified_at = datetime.now(timezone.utc)
    # Approval clears a previous decline, so turning a shop down is reversible
    # -- one that sends proof afterwards is approved, not stuck in a state it
    # cannot leave.
    store.rejected_at = None
    db.commit()
    await bump_catalogue_version()

    logger.warning("Admin verified a merchant store", extra={
        "admin_id": admin.id,
        "action": "admin_verify_store",
        "target": store.name,
    })
    return {"id": store.id, "name": store.name, "is_verified": True}


@router.post("/stores/{store_id}/unverify")
async def unverify_store(
    store_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Withdraw approval. The store keeps its listings; they stop being shown.

    Reversible on purpose. A store caught posting bad prices should disappear
    from search immediately, and deleting it would take its history with it
    and let the same claim be re-registered from scratch.
    """
    store = db.query(Store).filter(Store.id == store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")

    store.is_verified = False
    store.verified_at = None
    db.commit()
    await bump_catalogue_version()

    logger.warning("Admin withdrew store verification", extra={
        "admin_id": admin.id,
        "action": "admin_unverify_store",
        "target": store.name,
    })
    return {"id": store.id, "name": store.name, "is_verified": False}


@router.post("/stores/{store_id}/decline")
async def decline_store(
    store_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Turn down a merchant claim.

    WHY THIS EXISTS: verification had two states, and neither of them was
    "no". A claim that was obviously fake -- a shop whose listings are
    handbags, an account whose email was never confirmed -- could only be
    approved or left alone, so it sat in the pending queue forever, looking
    exactly like a claim nobody had got to yet. The queue could never be
    cleared, and every admin visit meant re-reading the same rejections.

    DECLINING IS NOT DELETING. The store, its listings and its history all
    stay; they simply remain invisible to shoppers, which they already were.
    Deleting would take a real shop's data with it on a judgement call that
    might be wrong, and would let the same claim be re-registered from scratch
    with no record that it had been refused before.

    Reversible: approving clears the rejection.
    """
    store = db.query(Store).filter(Store.id == store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    if not store.is_merchant:
        raise HTTPException(
            status_code=400,
            detail="Scraped stores have no claim to decline",
        )

    store.is_verified = False
    store.verified_at = None
    store.rejected_at = datetime.now(timezone.utc)
    db.commit()
    # Its prices were already hidden, but a store that was verified and is
    # now declined has to leave the cached results too.
    await bump_catalogue_version()

    logger.warning("Admin declined a merchant store", extra={
        "admin_id": admin.id,
        "action": "admin_decline_store",
        "target": store.name,
    })
    return {
        "id": store.id,
        "name": store.name,
        "is_verified": False,
        "review_status": store.review_status,
    }


@router.get("/stores/{store_id}/listings")
async def list_store_listings(
    store_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Everything one store lists, for reviewing a claim.

    Verification is a judgement call, and "is this really Jado Mobile" is
    partly answered by what they are selling: a shop claiming to be a phone
    retailer with three listings for handbags is not one. Approving blind,
    with only a name and an email to go on, is how a fake claim gets through.
    """
    store = db.query(Store).filter(Store.id == store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")

    rows = (
        db.query(ProductAlias, Price, Product)
        .outerjoin(Price, Price.alias_id == ProductAlias.id)
        .join(Product, Product.id == ProductAlias.product_id)
        .filter(ProductAlias.store_id == store_id)
        .order_by(ProductAlias.id.desc())
        .all()
    )

    return {
        "store": {
            "id": store.id,
            "name": store.name,
            "is_verified": store.is_verified,
            "is_merchant": store.is_merchant,
        },
        "listings": [
            {
                "id": alias.id,
                "name": alias.store_product_name,
                "matched_product": product.canonical_name,
                "match_category": product.match_category,
                "condition": alias.condition,
                "battery_health": alias.battery_health,
                "has_damage": alias.has_damage,
                "damage_notes": alias.damage_notes,
                "warranty_months": alias.warranty_months,
                "listing_notes": alias.listing_notes,
                "price": float(price.price) if price else None,
                "delivery_cost": float(price.delivery_cost or 0) if price else None,
                "availability": bool(price.availability) if price else False,
                "last_updated": price.last_updated if price else None,
            }
            for alias, price, product in rows
        ],
    }

# --- Listing moderation -----------------------------------------------------
#
# An admin has to be able to fix a merchant's listing without asking them.
# A wrong price on a comparison site is the one thing the product must never
# show, and "email the shop and wait" is not a remedy.


@router.patch("/listings/{listing_id}")
async def admin_update_listing(
    listing_id: int,
    body: ListingUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Edit ANY listing, whoever owns it.

    Deliberately a separate route from /merchant/listings/{id} rather than a
    role check inside it. The merchant route resolves the store from the
    signed-in user and can therefore never touch someone else's data -- that
    property is worth more than the few lines saved by merging them, and an
    `if admin` branch inside it would destroy exactly that guarantee.

    Every edit here is logged with the admin's id, because an administrator
    silently changing a shop's advertised price is precisely the action that
    needs to be answerable later.
    """
    alias = db.query(ProductAlias).filter(ProductAlias.id == listing_id).first()
    if not alias:
        raise HTTPException(status_code=404, detail="Listing not found")

    price = db.query(Price).filter(Price.alias_id == alias.id).first()
    if not price:
        raise HTTPException(status_code=404, detail="Listing has no price")

    changes = body.model_dump(exclude_unset=True)
    if changes.get("price") is not None and price.price != changes["price"]:
        # Same history trail as a merchant edit: an admin correction is still
        # a price change, and hiding it would put a gap in the series.
        db.add(PriceHistory(alias_id=alias.id, price=price.price))
        price.price = changes["price"]
    if changes.get("delivery_cost") is not None:
        price.delivery_cost = changes["delivery_cost"]
    if changes.get("availability") is not None:
        price.availability = changes["availability"]
    for field in ("battery_health", "has_damage", "damage_notes", "listing_notes"):
        if field in changes:
            setattr(alias, field, changes[field])
    if alias.has_damage is False:
        alias.damage_notes = None

    db.commit()
    await bump_catalogue_version()

    logger.warning("Admin edited a merchant listing", extra={
        "admin_id": admin.id,
        "action": "admin_edit_listing",
        "target": f"listing {alias.id} ({alias.store_product_name}): {sorted(changes)}",
    })
    return {
        "id": alias.id,
        "name": alias.store_product_name,
        "price": float(price.price),
        "delivery_cost": float(price.delivery_cost or 0),
        "availability": bool(price.availability),
        "condition": alias.condition,
    }


@router.delete("/listings/{listing_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_listing(
    listing_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Remove ANY listing. Prices and history cascade."""
    alias = db.query(ProductAlias).filter(ProductAlias.id == listing_id).first()
    if not alias:
        raise HTTPException(status_code=404, detail="Listing not found")

    logger.warning("Admin removed a merchant listing", extra={
        "admin_id": admin.id,
        "action": "admin_delete_listing",
        "target": f"listing {alias.id} ({alias.store_product_name})",
    })
    db.delete(alias)
    db.commit()
    await bump_catalogue_version()
    return None
