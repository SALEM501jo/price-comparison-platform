from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime


class StorePriceResponse(BaseModel):
    store_name: str
    store_logo: Optional[str]
    price: float
    currency: str
    availability: bool
    delivery_cost: float
    total_cost: float
    last_updated: datetime
    store_product_url: Optional[str]
    match_confidence: float


class ProductSearchResponse(BaseModel):
    id: int
    canonical_name: str
    brand: Optional[str]
    category: Optional[str]
    image_url: Optional[str]
    specs: Optional[Dict]
    lowest_price: float
    highest_price: float
    store_count: int
    best_deal_store: Optional[str]


class ProductDetailResponse(BaseModel):
    id: int
    canonical_name: str
    brand: Optional[str]
    category: Optional[str]
    image_url: Optional[str]
    description: Optional[str]
    # Structured attributes from app/matching. `specs` is the legacy column
    # written by the old regex extractor and still holds its output shape
    # ({"storage": "128", "model_year": "15"}), so clients should prefer this.
    attributes: Optional[Dict] = None
    specs: Optional[Dict]
    prices: List[StorePriceResponse]


class PriceHistoryPoint(BaseModel):
    price: float
    recorded_at: datetime


class PriceHistoryResponse(BaseModel):
    alias_id: int
    store_name: str
    history: List[PriceHistoryPoint]