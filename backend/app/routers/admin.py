"""
Admin-only endpoints.
SECURITY PRINCIPLE: Role-Based Access Control (RBAC).
Every admin endpoint must verify the user is an admin.
"""

from fastapi import APIRouter, Depends, HTTPException, status
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
from app.logging_config import get_security_logger

router = APIRouter(prefix="/admin", tags=["admin"])
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
    admin: User = Depends(require_admin)
):
    """
    Manually trigger a scrape run. Admin only.
    Returns 202 Accepted — scraping happens in background.
    """
    logger.warning("Admin triggered manual scrape", extra={
        "admin_id": admin.id,
        "action": "admin_trigger_scrape"
    })
    
    # In production, this would queue a Celery task or trigger GitHub Actions
    # For now, return a message
    return {"message": "Scrape triggered", "status": "pending"}


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