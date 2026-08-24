from typing import Optional

from pydantic import BaseModel, Field


class PriceAlertCreate(BaseModel):
    product_id: int
    # gt=0: a target of 0 or a negative price can never trigger, so accepting
    # one silently creates an alert that will never fire.
    target_price: float = Field(..., gt=0, le=1_000_000)


class PriceAlertResponse(BaseModel):
    id: int
    product_id: int
    target_price: float
    is_active: bool
    product_name: Optional[str] = None

    # Current market position, so the UI can show whether the target is close.
    lowest_total_cost: Optional[float] = None
    best_deal_store: Optional[str] = None
    is_met: bool = Field(
        False, description="True when the cheapest total is at or below target"
    )


class WishlistItemResponse(BaseModel):
    id: int
    product_id: int
    name: str
    brand: Optional[str] = None
    image_url: Optional[str] = None

    lowest_price: Optional[float] = None
    lowest_total_cost: Optional[float] = None
    best_deal_store: Optional[str] = None
    store_count: int = 0
