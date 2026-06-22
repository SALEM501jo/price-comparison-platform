"""
Wishlist and price alert endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.price import WishlistItem, PriceAlert
from app.models.product import Product
from app.schemas.price import PriceAlertCreate, PriceAlertResponse

router = APIRouter(prefix="/prices", tags=["prices"])


@router.post("/wishlist/{product_id}", status_code=status.HTTP_201_CREATED)
async def add_to_wishlist(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Add a product to user's wishlist."""
    # Check product exists
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Check not already in wishlist
    existing = (
        db.query(WishlistItem)
        .filter(WishlistItem.user_id == current_user.id)
        .filter(WishlistItem.product_id == product_id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Already in wishlist")
    
    item = WishlistItem(user_id=current_user.id, product_id=product_id)
    db.add(item)
    db.commit()
    
    return {"message": "Added to wishlist"}


@router.delete("/wishlist/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_wishlist(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Remove a product from wishlist."""
    item = (
        db.query(WishlistItem)
        .filter(WishlistItem.user_id == current_user.id)
        .filter(WishlistItem.product_id == product_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Not in wishlist")
    
    db.delete(item)
    db.commit()
    return None


@router.get("/wishlist")
async def get_wishlist(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get user's wishlist with current prices."""
    items = (
        db.query(WishlistItem, Product)
        .join(Product, WishlistItem.product_id == Product.id)
        .filter(WishlistItem.user_id == current_user.id)
        .all()
    )
    
    return [
        {
            "id": item.WishlistItem.id,
            "product_id": product.id,
            "name": product.canonical_name,
            "brand": product.brand,
            "image_url": product.image_url,
            "lowest_price": 0,  # Would be calculated from prices
        }
        for item, product in items
    ]


@router.post("/alerts", response_model=PriceAlertResponse, status_code=status.HTTP_201_CREATED)
async def create_alert(
    body: PriceAlertCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a price drop alert."""
    # Check product exists
    product = db.query(Product).filter(Product.id == body.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Check not already watching
    existing = (
        db.query(PriceAlert)
        .filter(PriceAlert.user_id == current_user.id)
        .filter(PriceAlert.product_id == body.product_id)
        .filter(PriceAlert.is_active == True)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Alert already exists for this product")
    
    alert = PriceAlert(
        user_id=current_user.id,
        product_id=body.product_id,
        target_price=body.target_price
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    
    return PriceAlertResponse(
        id=alert.id,
        product_id=alert.product_id,
        target_price=alert.target_price,
        is_active=alert.is_active,
        product_name=product.canonical_name
    )


@router.get("/alerts", response_model=List[PriceAlertResponse])
async def get_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get user's active price alerts."""
    alerts = (
        db.query(PriceAlert, Product)
        .join(Product, PriceAlert.product_id == Product.id)
        .filter(PriceAlert.user_id == current_user.id)
        .filter(PriceAlert.is_active == True)
        .all()
    )
    
    return [
        PriceAlertResponse(
            id=alert.PriceAlert.id,
            product_id=alert.PriceAlert.product_id,
            target_price=alert.PriceAlert.target_price,
            is_active=alert.PriceAlert.is_active,
            product_name=product.canonical_name
        )
        for alert, product in alerts
    ]


@router.delete("/alerts/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a price alert."""
    alert = (
        db.query(PriceAlert)
        .filter(PriceAlert.id == alert_id)
        .filter(PriceAlert.user_id == current_user.id)
        .first()
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    db.delete(alert)
    db.commit()
    return None