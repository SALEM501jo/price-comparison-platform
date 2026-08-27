from pydantic import BaseModel, Field
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

    # How a shopper reaches a merchant store. These shops have no website and
    # no checkout -- the sale happens on the phone, which is how this end of
    # the market already works. Null for scraped stores, which have a URL
    # instead, so the UI can offer whichever one exists.
    phone: Optional[str] = None
    whatsapp: Optional[str] = None
    facebook_url: Optional[str] = None

    # True when the price was submitted by the shop rather than scraped from
    # its own feed. Worth surfacing: a merchant price is only as fresh as the
    # last time somebody typed it, and `last_updated` means something
    # different for the two kinds of store.
    is_merchant: bool = False

    # --- What state this particular unit is in ---------------------------
    # A second-hand phone is not a cheaper new phone. These offers are shown
    # in their own table with their own cheapest, because putting a scratched
    # handset at 650 next to a sealed one at 850 and calling the first the
    # "best deal" is not a comparison, it is a category error.
    condition: str = "new"
    comparison_group: str = Field(
        "new", description="new | second_hand -- which table this belongs in"
    )
    battery_health: Optional[int] = None
    has_damage: Optional[bool] = None
    damage_notes: Optional[str] = None
    warranty_months: Optional[int] = None
    listing_notes: Optional[str] = None


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