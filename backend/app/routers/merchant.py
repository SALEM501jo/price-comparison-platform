"""
Merchant self-service: a shop manages its own store and its own prices.

THE ACCESS CONTROL STORY, which is the whole point of this module:

Every route resolves the store from `current_user`, never from an id supplied
by the caller. There is deliberately no `/merchant/stores/{store_id}/...`
shape anywhere here -- an endpoint that takes a store id has to remember to
check it belongs to the caller, and one that cannot take a store id has
nothing to forget. Listing routes then filter on that resolved store, so a
merchant asking for listing 47 gets a 404 unless 47 is theirs.

This is a harder problem than the wishlist routes next door. There the
question is "is this row the user's own?". Here a merchant legitimately writes
data that strangers read, so two more questions follow:

  - is the claim real? Anyone can register and call themselves a well-known
    shop. Prices stay invisible to shoppers until an admin verifies the store,
    which is enforced in the search query rather than here.
  - is the number sane? Merchant input is untrusted in a way a scraped feed is
    not. Validation lives in app/schemas/merchant.py.
"""

from __future__ import annotations

import hashlib
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, get_rate_limited, require_merchant
from app.logging_config import get_security_logger
from app.matching import parse
from app.models.alias import ProductAlias
from app.models.price import Price, PriceHistory
from app.models.store import Store
from app.models.user import User, UserRole
from app.schemas.merchant import (
    ListingCreate,
    ListingResponse,
    ListingUpdate,
    StoreRegisterRequest,
    StoreResponse,
    StoreUpdateRequest,
)
from app.services import contact_stats, photos
from app.services.cache import bump_catalogue_version
from app.services.images import ImageRejected, MAX_UPLOAD_BYTES, process_upload
from app.services.deduplication import DeduplicationEngine

logger = get_security_logger("app.merchant")

router = APIRouter()


def _own_store(db: Session, user: User) -> Store:
    """
    The signed-in user's store, or 404.

    The single place a store is resolved for this module. Every route goes
    through it, which is what makes "a merchant can only touch their own
    store" a property of the code rather than a rule repeated in each handler.
    """
    store = db.query(Store).filter(Store.owner_user_id == user.id).first()
    if not store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No store registered for this account",
        )
    return store


def _listing_key(name: str, condition: str) -> str:
    """
    A stable per-listing identifier for a shop that has no SKUs.

    WHY THIS EXISTS: the deduplication engine's idempotency guard falls back
    to matching on store_product_name when no SKU is given, so a merchant who
    listed "iPhone 15 128GB" as new and then the same model as used had the
    second submission silently overwrite the first. Two units in genuinely
    different conditions are two listings.

    Folding the condition into the key also makes the existing
    (store_id, store_product_id) uniqueness constraint enforce "one listing
    per shop, per product, per condition" in the database rather than in a
    handler that has to remember.
    """
    digest = hashlib.sha1(" ".join(name.lower().split()).encode()).hexdigest()[:16]
    return f"merchant:{condition}:{digest}"


def _listing_response(alias: ProductAlias, price: Optional[Price]) -> ListingResponse:
    product = alias.product
    searchable = bool(product and product.match_category)
    return ListingResponse(
        id=alias.id,
        name=alias.store_product_name,
        price=float(price.price) if price else 0.0,
        delivery_cost=float(price.delivery_cost or 0) if price else 0.0,
        availability=bool(price.availability) if price else False,
        last_updated=price.last_updated if price else None,
        matched_product_id=product.id if product else None,
        matched_product_name=product.canonical_name if product else None,
        match_category=product.match_category if product else None,
        is_searchable=searchable,
        condition=alias.condition,
        battery_health=alias.battery_health,
        has_damage=alias.has_damage,
        damage_notes=alias.damage_notes,
        warranty_months=alias.warranty_months,
        listing_notes=alias.listing_notes,
        has_photo=alias.photo is not None,
    )


def _store_response(db: Session, store: Store) -> StoreResponse:
    count = db.query(ProductAlias).filter(ProductAlias.store_id == store.id).count()
    return StoreResponse(
        id=store.id,
        name=store.name,
        phone=store.phone,
        whatsapp=store.whatsapp,
        facebook_url=store.facebook_url,
        instagram_url=store.instagram_url,
        is_verified=store.is_verified,
        verified_at=store.verified_at,
        listing_count=count,
    )


# --- Store ------------------------------------------------------------------


@router.post("/store", response_model=StoreResponse, status_code=status.HTTP_201_CREATED)
async def register_store(
    payload: StoreRegisterRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(get_rate_limited),
):
    """
    Claim a store.

    Open to any signed-in user -- this is how someone BECOMES a merchant, so
    requiring the merchant role here would make the role unreachable. The
    account is promoted on success, unless it is already an admin, whose
    wider authority must not be quietly downgraded.

    The store is created UNVERIFIED and its prices stay out of search until an
    admin approves it.
    """
    if db.query(Store).filter(Store.owner_user_id == current_user.id).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This account already has a store",
        )

    # Case-insensitive, because "Jado Mobile" and "jado mobile" are one shop
    # and letting both exist would split its listings across two rows.
    clash = db.query(Store).filter(Store.name.ilike(payload.name)).first()
    if clash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A store with that name already exists",
        )

    store = Store(
        name=payload.name,
        owner_user_id=current_user.id,
        phone=payload.phone,
        whatsapp=payload.whatsapp,
        facebook_url=payload.facebook_url,
        instagram_url=payload.instagram_url,
        is_verified=False,
        is_active=1,
    )
    db.add(store)

    if current_user.role == UserRole.user:
        current_user.role = UserRole.merchant

    db.commit()
    db.refresh(store)

    logger.info("Merchant registered a store", extra={
        "action": "merchant_store_registered",
        "target": store.name,
        "user_id": current_user.id,
    })
    return _store_response(db, store)


@router.get("/store", response_model=StoreResponse)
async def get_my_store(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_merchant),
):
    """The signed-in merchant's own store."""
    return _store_response(db, _own_store(db, current_user))


@router.patch("/store", response_model=StoreResponse)
async def update_my_store(
    payload: StoreUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_merchant),
    _: None = Depends(get_rate_limited),
):
    """
    Update contact details.

    The store NAME is deliberately not editable. It is what an admin verified
    and what shoppers recognise, so allowing a rename would let a store pass
    review as itself and then become someone else. Renaming is an admin action.
    """
    store = _own_store(db, current_user)

    # exclude_unset so omitting a field leaves it alone, while sending null
    # clears it -- otherwise a merchant could never remove a stale number.
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(store, field, value)

    db.commit()
    db.refresh(store)
    return _store_response(db, store)


# --- Listings ---------------------------------------------------------------


@router.get("/listings", response_model=List[ListingResponse])
async def list_my_listings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_merchant),
):
    """Everything this store sells. Scoped to the caller's own store."""
    store = _own_store(db, current_user)
    aliases = (
        db.query(ProductAlias)
        .filter(ProductAlias.store_id == store.id)
        .order_by(ProductAlias.id.desc())
        .all()
    )
    prices = {
        p.alias_id: p
        for p in db.query(Price).filter(
            Price.alias_id.in_([a.id for a in aliases] or [0])
        )
    }
    return [_listing_response(a, prices.get(a.id)) for a in aliases]


@router.post(
    "/listings", response_model=ListingResponse, status_code=status.HTTP_201_CREATED
)
async def create_listing(
    payload: ListingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_merchant),
    _: None = Depends(get_rate_limited),
):
    """
    Add a product this shop sells.

    The submitted name goes through the SAME deduplication engine a scraped
    listing does, so a merchant's "iPhone 15 128GB Black" joins the existing
    product rather than creating a second one -- which is what puts two prices
    side by side and makes the comparison real.

    Re-submitting a name already listed updates its price instead of creating
    a duplicate: process_new_product returns the existing alias, and the
    caller almost certainly meant to correct the price.
    """
    store = _own_store(db, current_user)
    dedup = DeduplicationEngine(db)

    product, alias, _is_new = dedup.process_new_product(
        store_id=store.id,
        store_product_name=payload.name,
        # These shops have no SKUs, so we synthesise one that includes the
        # condition -- see _listing_key. Passing null here instead made a
        # used listing overwrite the new one of the same phone.
        store_product_id=_listing_key(payload.name, payload.condition),
        store_product_url=store.facebook_url,
        brand=parse(payload.name).get("brand"),
        category=None,
        # Scopes the engine's name fallback, so listing the same phone new
        # and used produces two listings rather than one overwriting the other.
        condition=payload.condition,
    )

    # Condition describes the unit, so it is stamped on the alias rather than
    # on the shared product. Re-submitting the same phone in the same
    # condition is an edit, so these are refreshed either way.
    alias.condition = payload.condition
    alias.battery_health = payload.battery_health
    alias.has_damage = payload.has_damage
    alias.damage_notes = payload.damage_notes
    alias.warranty_months = payload.warranty_months
    alias.listing_notes = payload.listing_notes

    existing = db.query(Price).filter(Price.alias_id == alias.id).first()
    if existing:
        if existing.price != payload.price:
            db.add(PriceHistory(alias_id=alias.id, price=existing.price))
        existing.price = payload.price
        existing.delivery_cost = payload.delivery_cost
        existing.availability = payload.availability
        price = existing
    else:
        price = Price(
            alias_id=alias.id,
            price=payload.price,
            currency="JOD",
            delivery_cost=payload.delivery_cost,
            availability=payload.availability,
        )
        db.add(price)

    db.commit()
    db.refresh(alias)
    db.refresh(price)

    await bump_catalogue_version()

    logger.info("Merchant listing saved", extra={
        "action": "merchant_listing_created",
        "target": f"{store.name}: {payload.name}",
        "user_id": current_user.id,
    })
    return _listing_response(alias, price)


@router.patch("/listings/{listing_id}", response_model=ListingResponse)
async def update_listing(
    listing_id: int,
    payload: ListingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_merchant),
    _: None = Depends(get_rate_limited),
):
    """
    Change a price.

    The store filter is what makes this safe. Without it, `listing_id` alone
    would let any merchant rewrite any shop's prices -- including undercutting
    a rival on the rival's own listing.
    """
    store = _own_store(db, current_user)
    alias = (
        db.query(ProductAlias)
        .filter(ProductAlias.id == listing_id)
        .filter(ProductAlias.store_id == store.id)
        .first()
    )
    if not alias:
        # 404 rather than 403: a merchant has no business learning whether
        # someone else's listing id exists.
        raise HTTPException(status_code=404, detail="Listing not found")

    price = db.query(Price).filter(Price.alias_id == alias.id).first()
    if not price:
        raise HTTPException(status_code=404, detail="Listing has no price")

    changes = payload.model_dump(exclude_unset=True)
    if "price" in changes and changes["price"] is not None:
        if price.price != changes["price"]:
            db.add(PriceHistory(alias_id=alias.id, price=price.price))
        price.price = changes["price"]
    if changes.get("delivery_cost") is not None:
        price.delivery_cost = changes["delivery_cost"]
    if changes.get("availability") is not None:
        price.availability = changes["availability"]

    # Wear changes even when the condition does not. Condition itself is not
    # editable -- see ListingUpdate for why.
    for field in ("battery_health", "has_damage", "damage_notes", "listing_notes"):
        if field in changes:
            setattr(alias, field, changes[field])
    if alias.has_damage is False:
        alias.damage_notes = None

    db.commit()
    db.refresh(price)
    await bump_catalogue_version()
    return _listing_response(alias, price)


@router.delete("/listings/{listing_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_listing(
    listing_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_merchant),
):
    """Remove a listing. Scoped to the caller's store, as above."""
    store = _own_store(db, current_user)
    alias = (
        db.query(ProductAlias)
        .filter(ProductAlias.id == listing_id)
        .filter(ProductAlias.store_id == store.id)
        .first()
    )
    if not alias:
        raise HTTPException(status_code=404, detail="Listing not found")

    db.delete(alias)  # prices and history cascade
    db.commit()
    await bump_catalogue_version()
    return None


def _own_listing(db: Session, user: User, listing_id: int) -> ProductAlias:
    """
    Resolve a listing the caller actually owns, or 404.

    Extracted because the photo routes need exactly what the price routes
    needed, and a second hand-written copy of a store-scoping filter is how
    one of them eventually gets written without the filter.
    """
    store = _own_store(db, user)
    alias = (
        db.query(ProductAlias)
        .filter(ProductAlias.id == listing_id)
        .filter(ProductAlias.store_id == store.id)
        .first()
    )
    if not alias:
        # 404, not 403: same reason as the price routes -- a merchant has no
        # business learning whether someone else's listing id exists.
        raise HTTPException(status_code=404, detail="Listing not found")
    return alias


@router.put("/listings/{listing_id}/photo", status_code=status.HTTP_204_NO_CONTENT)
async def upload_listing_photo(
    listing_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_merchant),
    _: None = Depends(get_rate_limited),
):
    """
    Attach a photo to one of this shop's listings.

    PUT, not POST: one photo per listing, and uploading again replaces it.
    That is what a shop owner correcting a bad shot means, and it makes the
    request idempotent -- a retry after a dropped connection cannot leave two.

    The file is decoded and RE-ENCODED before anything is stored; see
    services/images.py for why that single step does most of the security
    work here. Nothing the client claims about the file is believed.
    """
    alias = _own_listing(db, current_user, listing_id)

    # Read with a hard ceiling rather than trusting Content-Length, which is
    # a client-supplied number. Reading one byte past the limit is enough to
    # know it was exceeded without holding the whole oversized body.
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "too_large",
                "message": f"The file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)}MB.",
            },
        )

    try:
        processed = process_upload(raw)
    except ImageRejected as rejected:
        # The CODE is what the client translates; the message is the fallback
        # for anything without a translation yet. Same contract as match
        # differences -- the server does not compose the sentence.
        raise HTTPException(
            status_code=422,
            detail={"code": rejected.code, "message": str(rejected)},
        ) from None

    photos.save_photo(db, alias.id, processed)
    db.commit()
    await bump_catalogue_version()

    logger.info("Merchant listing photo uploaded", extra={
        "action": "merchant_photo_uploaded",
        "target": f"listing {alias.id}",
        "user_id": current_user.id,
    })
    return None


@router.delete("/listings/{listing_id}/photo", status_code=status.HTTP_204_NO_CONTENT)
async def delete_listing_photo(
    listing_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_merchant),
):
    """Remove a listing's photo. Scoped to the caller's store, as above."""
    alias = _own_listing(db, current_user, listing_id)
    photos.delete_photo(db, alias.id)
    db.commit()
    await bump_catalogue_version()
    return None


@router.get("/listings/{listing_id}/photo")
async def get_my_listing_photo(
    listing_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_merchant),
):
    """
    The shop's own photo, verified or not.

    The public route refuses to serve an unverified store's photo, which is
    right for shoppers and useless for the shop owner -- they would have no
    way to tell a failed upload from a pending claim. This one is scoped to
    the caller, so it can show what they actually uploaded.
    """
    alias = _own_listing(db, current_user, listing_id)
    photo = photos.photo_for_listing(db, alias.id)
    if not photo:
        raise HTTPException(status_code=404, detail="No photo")
    return Response(
        content=photo.data,
        media_type=photo.content_type,
        headers={
            "Cache-Control": "private, no-cache",
            "ETag": f'"{photo.checksum}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/stats")
async def my_stats(
    days: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_merchant),
):
    """
    How many shoppers asked for this shop's number.

    THE POINT OF THE WHOLE FEATURE, and the answer to the question a merchant
    asks before paying anything: what did this platform actually do for me.

    Scoped to the caller's own store by _own_store, like every other route in
    this module -- there is no store id to pass and therefore none to forget
    to check.

    WHAT THE NUMBERS MEAN: these are TAPS -- a shopper pressing Call or
    WhatsApp -- not calls, and not sales. Whether the phone rang, was
    answered, or led to a sale happens off this platform entirely. The labels
    say taps because a merchant is being asked to pay against this figure, and
    inflating it by calling it something it is not would be the fastest way to
    lose the shop's trust the first time they compared it with their own call
    log.
    """
    store = _own_store(db, current_user)
    days = max(1, min(days, 365))

    return {
        "store_id": store.id,
        "is_verified": store.is_verified,
        **contact_stats.totals_for_store(db, store.id, days=days),
        "top_products": contact_stats.per_product_for_store(db, store.id, days=days),
    }
