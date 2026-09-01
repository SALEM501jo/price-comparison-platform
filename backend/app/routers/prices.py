"""
Wishlist and price alert endpoints.

Every query here is scoped by current_user.id. That is the whole access control
story for these routes: without the filter, any authenticated user could read
or delete another's saved items by guessing an id.
"""

from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.price import PriceAlert, WishlistItem
from app.models.product import Product
from app.models.user import User
from app.schemas.price import (
    PriceAlertCreate,
    PriceAlertResponse,
    WishlistItemResponse,
)
from app.services import photos
from app.services.pricing import offers_for, price_summary

router = APIRouter()


@router.post("/wishlist/{product_id}", status_code=status.HTTP_201_CREATED)
async def add_to_wishlist(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a product to the user's wishlist."""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    existing = (
        db.query(WishlistItem)
        .filter(WishlistItem.user_id == current_user.id)
        .filter(WishlistItem.product_id == product_id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Already in wishlist")

    db.add(WishlistItem(user_id=current_user.id, product_id=product_id))
    db.commit()
    return {"message": "Added to wishlist"}


@router.delete("/wishlist/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_wishlist(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a product from the wishlist."""
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


@router.get("/wishlist", response_model=List[WishlistItemResponse])
async def get_wishlist(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    The user's wishlist with current prices.

    Prices come from the same aggregation the search uses, in one query for the
    whole list. This endpoint previously returned a hardcoded "lowest_price": 0
    with a "would be calculated" comment, which made the feature useless -- the
    entire point of a wishlist here is watching what the item costs today.
    """
    rows = (
        db.query(WishlistItem, Product)
        .join(Product, WishlistItem.product_id == Product.id)
        .filter(WishlistItem.user_id == current_user.id)
        .order_by(WishlistItem.created_at.desc())
        .all()
    )

    prices = price_summary(db, (product.id for _, product in rows))
    photo_ids = photos.product_ids_with_photos(db, [p.id for _, p in rows])

    return [
        WishlistItemResponse(
            id=item.id,
            product_id=product.id,
            name=product.canonical_name,
            brand=product.brand,
            image_url=photos.display_image_url(
                product.id, product.image_url, product.id in photo_ids
            ),
            lowest_price=min(offers_for(prices, product.id)["prices"])
            if offers_for(prices, product.id).get("prices")
            else None,
            lowest_total_cost=offers_for(prices, product.id).get("best_total"),
            best_deal_store=offers_for(prices, product.id).get("best"),
            store_count=len(offers_for(prices, product.id).get("stores") or ()),
        )
        for item, product in rows
    ]


@router.post("/alerts", response_model=PriceAlertResponse, status_code=status.HTTP_201_CREATED)
async def create_alert(
    body: PriceAlertCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a price drop alert."""
    product = db.query(Product).filter(Product.id == body.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    existing = (
        db.query(PriceAlert)
        .filter(PriceAlert.user_id == current_user.id)
        .filter(PriceAlert.product_id == body.product_id)
        .filter(PriceAlert.is_active.is_(True))
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409, detail="Alert already exists for this product"
        )

    alert = PriceAlert(
        user_id=current_user.id,
        product_id=body.product_id,
        # via str so the user's typed target is stored exactly, not as the
        # nearest binary approximation of it.
        target_price=Decimal(str(body.target_price)),
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)

    summary = offers_for(price_summary(db, [product.id]), product.id)
    lowest = summary.get("best_total")

    return PriceAlertResponse(
        id=alert.id,
        product_id=alert.product_id,
        target_price=alert.target_price,
        is_active=alert.is_active,
        product_name=product.canonical_name,
        lowest_total_cost=lowest,
        best_deal_store=summary.get("best"),
        is_met=lowest is not None and lowest <= alert.target_price,
    )


@router.get("/alerts", response_model=List[PriceAlertResponse])
async def get_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The user's active price alerts, with how each stands against the market."""
    rows = (
        db.query(PriceAlert, Product)
        .join(Product, PriceAlert.product_id == Product.id)
        .filter(PriceAlert.user_id == current_user.id)
        .filter(PriceAlert.is_active.is_(True))
        .order_by(PriceAlert.created_at.desc())
        .all()
    )

    prices = price_summary(db, (product.id for _, product in rows))

    results = []
    for alert, product in rows:
        summary = offers_for(prices, product.id)
        lowest = summary.get("best_total")
        results.append(
            PriceAlertResponse(
                id=alert.id,
                product_id=alert.product_id,
                target_price=alert.target_price,
                is_active=alert.is_active,
                product_name=product.canonical_name,
                lowest_total_cost=lowest,
                best_deal_store=summary.get("best"),
                is_met=lowest is not None and lowest <= alert.target_price,
            )
        )
    return results


@router.delete("/alerts/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a price alert."""
    alert = (
        db.query(PriceAlert)
        .filter(PriceAlert.id == alert_id)
        # Scoped by owner: without this, any user could delete any alert by id.
        .filter(PriceAlert.user_id == current_user.id)
        .first()
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    db.delete(alert)
    db.commit()
    return None
