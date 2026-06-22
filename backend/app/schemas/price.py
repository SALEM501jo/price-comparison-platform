from pydantic import BaseModel
from typing import Optional


class PriceAlertCreate(BaseModel):
    product_id: int
    target_price: float


class PriceAlertResponse(BaseModel):
    id: int
    product_id: int
    target_price: float
    is_active: bool
    product_name: Optional[str] = None