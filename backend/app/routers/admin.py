"""
Admin-only endpoints.
SECURITY PRINCIPLE: Role-Based Access Control (RBAC).
Every admin endpoint must verify the user is an admin.
"""

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from typing import List, Literal
from app.database import get_db
from app.dependencies import require_admin
from app.models.user import User, UserRole
from app.models.product import Product
from app.models.price import Price, PriceHistory
from app.models.store import Store
from app.models.alias import ProductAlias
from app.schemas.auth import UserResponse
from app.schemas.merchant import ListingUpdate
from app.database import SessionLocal
from app.logging_config import get_security_logger
from app.services.cache import bump_catalogue_version
from app.models.scrape_job import ScrapeJob
from app.services import jobs as job_queue
from app.services.scrapers import STORES, store_by_code

router = APIRouter()
logger = get_security_logger("app.admin")


@router.get("/users", response_model=List[UserResponse])
async def list_users(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """
    List all users. Admin only.
    """
    logger.warning("Admin listing all users", extra={
        "admin_id": admin.id,
        "action": "admin_list_users",
        "target": "all_users"
    })
    
    # Bounded. This was an unqualified .all(): fine with 22 accounts, and a
    # way to load the entire user table into memory the day it is not. The
    # response is still a plain list, so callers are unaffected.
    return (
        db.query(User)
        .order_by(User.id)
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """
    Delete a user. Admin only.
    Cannot delete yourself.
    """
    if admin.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    logger.warning("Admin deleted user", extra={
        "admin_id": admin.id,
        "action": "admin_delete_user",
        "target": user_id
    })
    
    db.delete(user)
    db.commit()
    return None


@router.get("/stats")
async def get_stats(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """
    Platform statistics. Admin only.
    """
    logger.info("Admin viewing stats", extra={
        "admin_id": admin.id,
        "action": "admin_view_stats"
    })
    
    stats = {
        "users": db.query(func.count(User.id)).scalar(),
        "products": db.query(func.count(Product.id)).scalar(),
        "stores": db.query(func.count(Store.id)).scalar(),
        "aliases": db.query(func.count(ProductAlias.id)).scalar(),
        "prices": db.query(func.count(Price.id)).scalar(),
        "price_history_records": db.query(func.count(PriceHistory.id)).scalar(),
    }
    
    return stats


@router.post("/scrape", status_code=status.HTTP_202_ACCEPTED)
async def trigger_scrape(
    store: str | None = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Queue a scrape run. Admin only.

    ENQUEUES, rather than running the work behind the response. The previous
    version used BackgroundTasks, which runs inside the web process: a
    restart killed the run mid-flight, nothing recorded that it had ever
    existed, and the only sign was a log line nobody was watching. A deploy
    during a scrape simply lost it.

    The job is now a row. A worker claims it -- see app/services/worker.py --
    so the work outlives the process that asked for it, survives a deploy, and
    leaves a history the admin screen can show.

    `store` optionally limits the run to one store code.
    """
    targets = STORES
    if store:
        config = store_by_code(store)
        if not config:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown store. Known: {[s.code for s in STORES]}",
            )
        targets = (config,)

    job = job_queue.enqueue(
        db, [s.code for s in targets], requested_by=admin.id
    )

    logger.warning(
        "Admin queued a scrape",
        extra={
            "user_id": admin.id,
            "action": "admin_trigger_scrape",
            "target": ",".join(s.code for s in targets),
            "success": True,
        },
    )

    return {
        "status": "queued",
        "job_id": job.id,
        "stores": [s.name for s in targets],
        "note": "A worker picks this up; watch /admin/scrape-jobs for progress.",
    }


@router.get("/scrape-jobs")
async def list_scrape_jobs(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Recent scrape runs and how they went.

    The reason the queue is a table rather than a background thread: a run
    that failed at three in the morning is answerable here, instead of only
    in server logs nobody has kept.
    """
    rows = (
        db.query(ScrapeJob)
        .order_by(ScrapeJob.created_at.desc(), ScrapeJob.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": job.id,
            "status": job.status,
            "stores": job.store_codes or "all",
            "requested_by": job.requested_by,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "result": job.result,
            "error": job.error,
        }
        for job in rows
    ]


@router.get("/price-anomalies")
async def get_price_anomalies(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Products whose price moved more than 50% in 24h. Admin only.

    Usually a scrape error -- a parsing change, or a store publishing a
    placeholder -- rather than a real discount, which is why it is worth
    surfacing.

    Uses a window function so this is ONE query. The previous version ran a
    subquery per history row to find the preceding price, which is O(n) round
    trips against a table that grows with every scrape.
    """
    logger.info(
        "Admin checking price anomalies",
        extra={"admin_id": admin.id, "action": "admin_price_anomalies"},
    )

    cutoff = datetime.now(timezone.utc) - timedelta(days=1)

    previous_price = func.lag(PriceHistory.price).over(
        partition_by=PriceHistory.alias_id, order_by=PriceHistory.recorded_at
    )

    history = (
        select(
            PriceHistory.alias_id.label("alias_id"),
            PriceHistory.price.label("price"),
            PriceHistory.recorded_at.label("recorded_at"),
            previous_price.label("previous_price"),
        )
        .subquery()
    )

    rows = (
        db.query(
            Product.canonical_name.label("product"),
            Store.name.label("store"),
            history.c.previous_price,
            history.c.price,
            history.c.recorded_at,
        )
        .select_from(history)
        .join(ProductAlias, ProductAlias.id == history.c.alias_id)
        .join(Product, Product.id == ProductAlias.product_id)
        .join(Store, Store.id == ProductAlias.store_id)
        .filter(history.c.recorded_at > cutoff)
        .filter(history.c.previous_price.isnot(None))
        .filter(history.c.previous_price > 0)
        .order_by(history.c.recorded_at.desc())
        .all()
    )

    anomalies = []
    for row in rows:
        change = abs(row.price - row.previous_price) / row.previous_price * 100
        if change > 50:
            anomalies.append(
                {
                    "product": row.product,
                    # The store's NAME. This used to return alias.store_id, a
                    # raw integer under a field called "store".
                    "store": row.store,
                    "old_price": float(row.previous_price),
                    "new_price": float(row.price),
                    "change_percent": round(float(change), 2),
                    "recorded_at": row.recorded_at,
                }
            )

    return anomalies


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
        query = query.filter(
            Store.owner_user_id.isnot(None), Store.is_verified.is_(False)
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
                # The account behind the claim. An admin checking whether a
                # shop is genuine needs to know who is asking, and whether
                # they bothered to confirm their address.
                "owner_email": owner.email if owner else None,
                "owner_verified_email": bool(owner and owner.email_verified_at)
                if owner
                else None,
                "created_at": store.created_at,
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


# --- Role management --------------------------------------------------------
#
# WHY THIS EXISTS AT ALL: without it there is no way to create a second admin.
# The first one is made by hand against the database; every one after that has
# to come from here, and a platform with exactly one administrator is one
# forgotten password away from having none.


class RoleChange(BaseModel):
    """
    A role change, restricted to the three real roles.

    A Literal rather than the UserRole enum so an unknown value is a 422 at
    the edge instead of something the handler has to remember to reject.
    """

    role: Literal["user", "merchant", "admin"]


@router.patch("/users/{user_id}/role")
async def change_user_role(
    user_id: int,
    body: RoleChange,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Grant or revoke a role. Admin only.

    TWO GUARDS, BOTH ABOUT NOT LOCKING EVERYONE OUT:

      - An admin cannot change their OWN role. Demoting yourself by accident
        is unrecoverable from inside the application, and there is no reason
        to do it deliberately that a second admin cannot serve better.
      - The last admin cannot be demoted by anyone. A platform with zero
        admins cannot appoint one, and the only route back is manual surgery
        on the database.

    Demoting a merchant does NOT delete their store or its listings. The
    prices stay, and stay visible if the store was verified -- pulling a shop
    off the site is what unverify is for, and conflating the two would make
    a role change silently destroy a shop's public presence.
    """
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    if target.id == admin.id:
        raise HTTPException(
            status_code=400,
            detail="You cannot change your own role. Ask another admin.",
        )

    new_role = UserRole(body.role)

    if target.role == UserRole.admin and new_role != UserRole.admin:
        remaining = (
            db.query(User)
            .filter(User.role == UserRole.admin, User.id != target.id)
            .count()
        )
        if remaining == 0:
            raise HTTPException(
                status_code=400,
                detail="Cannot demote the last admin. Promote someone else first.",
            )

    previous = target.role
    target.role = new_role
    db.commit()

    logger.warning("Admin changed a user role", extra={
        "admin_id": admin.id,
        "action": "admin_change_role",
        "target": f"user {target.id}: {previous.value} -> {new_role.value}",
    })
    return {"id": target.id, "email": target.email, "role": new_role.value}


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
