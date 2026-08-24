"""
Admin-only endpoints.
SECURITY PRINCIPLE: Role-Based Access Control (RBAC).
Every admin endpoint must verify the user is an admin.
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from app.database import get_db
from app.dependencies import require_admin
from app.models.user import User
from app.models.product import Product
from app.models.price import Price, PriceHistory
from app.models.store import Store
from app.models.alias import ProductAlias
from app.schemas.auth import UserResponse
from app.database import SessionLocal
from app.logging_config import get_security_logger
from app.services.ingest import IngestService
from app.services.scrapers import STORES, store_by_code

router = APIRouter()
logger = get_security_logger("app.admin")


@router.get("/users", response_model=List[UserResponse])
async def list_users(
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
    
    users = db.query(User).all()
    return users


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
    background: BackgroundTasks,
    store: str | None = None,
    admin: User = Depends(require_admin),
):
    """
    Run the real scrapers. Admin only.

    202 Accepted with the work queued behind the response: a full run takes
    minutes (deliberately -- requests are spaced out to be polite to the store),
    which is far longer than any sensible HTTP timeout.

    `store` optionally limits the run to one store code.

    NOTE: BackgroundTasks runs in this process, so the work dies with a restart
    and does not spread across replicas. A real deployment wants a task queue.
    The scheduled path does not rely on this at all -- CI runs the same code as
    a standalone command on a cron.
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

    logger.warning(
        "Admin triggered a scrape",
        extra={
            "user_id": admin.id,
            "action": "admin_trigger_scrape",
            "target": ",".join(s.code for s in targets),
            "success": True,
        },
    )

    background.add_task(_run_scrape, [s.code for s in targets])

    return {
        "status": "started",
        "stores": [s.name for s in targets],
        "note": "Runs in the background; watch the logs or re-check /admin/stats.",
    }


def _run_scrape(store_codes: list[str]) -> None:
    """
    Background worker. Opens its OWN session: the request's session is closed
    when the response is sent, so reusing it here would fail partway through.
    """
    db = SessionLocal()
    try:
        service = IngestService(db)
        for code in store_codes:
            config = store_by_code(code)
            if config:
                service.run_store(config)
    except Exception:
        logger.error(
            "Background scrape failed",
            exc_info=True,
            extra={"action": "admin_scrape_run", "success": False},
        )
    finally:
        db.close()


@router.get("/price-anomalies")
async def get_price_anomalies(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """
    Find products with suspicious price changes (>50% change in 24h).
    Admin only.
    """
    # This is a simplified query — in production you'd use window functions
    logger.info("Admin checking price anomalies", extra={
        "admin_id": admin.id,
        "action": "admin_price_anomalies"
    })
    
    # Get recent price history
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    
    recent_changes = (
        db.query(PriceHistory, ProductAlias, Product)
        .join(ProductAlias, PriceHistory.alias_id == ProductAlias.id)
        .join(Product, ProductAlias.product_id == Product.id)
        .filter(PriceHistory.recorded_at > cutoff)
        .all()
    )
    
    anomalies = []
    for history, alias, product in recent_changes:
        # Get previous price (before this history entry)
        previous = (
            db.query(PriceHistory)
            .filter(PriceHistory.alias_id == alias.id)
            .filter(PriceHistory.recorded_at < history.recorded_at)
            .order_by(PriceHistory.recorded_at.desc())
            .first()
        )
        
        if previous and previous.price > 0:
            change_pct = abs(history.price - previous.price) / previous.price * 100
            if change_pct > 50:
                anomalies.append({
                    "product": product.canonical_name,
                    "store": alias.store_id,
                    "old_price": previous.price,
                    "new_price": history.price,
                    "change_percent": round(change_pct, 2)
                })
    
    return anomalies