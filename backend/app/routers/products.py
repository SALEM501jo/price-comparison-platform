"""
Product search and comparison routes.
"""

from fastapi import APIRouter, Depends, Query, Request, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List
from app.database import get_db
from app.dependencies import get_current_user_optional, get_rate_limited
from app.models.product import Product
from app.models.alias import ProductAlias
from app.models.price import Price, PriceHistory
from app.models.store import Store
from app.schemas.product import (
    ProductDetailResponse,
    StorePriceResponse,
    PriceHistoryResponse,
    PriceHistoryPoint
)
from app.schemas.search import TieredSearchResponse
from app.services.search import search_products
from app.config import get_settings
import redis.asyncio as aioredis
import hashlib

router = APIRouter()
settings = get_settings()

# Redis cache singleton
_cache = None

async def get_cache():
    global _cache
    if _cache is None:
        _cache = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _cache


@router.get("/search", response_model=TieredSearchResponse)
async def search(
    request: Request,
    q: str = Query(..., min_length=2, max_length=100),
    db: Session = Depends(get_db),
    _: None = Depends(get_rate_limited),
):
    """
    Search products, grouped by how well they match the query.

    Returns three buckets -- exact, close (85-99%), similar (70-84%) -- each
    carrying the reason it landed there, e.g. "different colour (blue, not
    black)". See app/services/search.py for the two-stage design.
    """
    cache_key = f"search:v2:{hashlib.sha256(q.strip().lower().encode()).hexdigest()}"
    cache = await get_cache()

    try:
        cached = await cache.get(cache_key)
        if cached:
            return TieredSearchResponse.model_validate_json(cached)
    except Exception:
        pass  # cache is an optimisation, never a dependency

    response = search_products(db, q)

    try:
        await cache.setex(cache_key, 300, response.model_dump_json())
    except Exception:
        pass

    return response


@router.get("/{product_id}", response_model=ProductDetailResponse)
async def get_product(
    product_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(get_rate_limited),
):
    """Get product details with all store prices."""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Get all prices with store info (Price -> ProductAlias -> Store)
    prices = (
        db.query(Price, ProductAlias, Store)
        .join(ProductAlias, Price.alias_id == ProductAlias.id)
        .join(Store, ProductAlias.store_id == Store.id)
        .filter(ProductAlias.product_id == product_id)
        .all()
    )
    
    price_responses = []
    for price, alias, store in prices:
        price_responses.append(StorePriceResponse(
            store_name=store.name,
            store_logo=store.logo_url,
            price=price.price,
            currency=price.currency,
            availability=price.availability,
            delivery_cost=price.delivery_cost,
            total_cost=price.price + price.delivery_cost,
            last_updated=price.last_updated,
            store_product_url=alias.store_product_url,
            match_confidence=alias.match_confidence
        ))
    
    # Sort by total cost (price + delivery)
    price_responses.sort(key=lambda x: x.total_cost)
    
    return ProductDetailResponse(
        id=product.id,
        canonical_name=product.canonical_name,
        brand=product.brand,
        category=product.category,
        image_url=product.image_url,
        description=product.description,
        attributes=product.match_attributes,
        specs=product.specs,
        prices=price_responses
    )


@router.get("/{product_id}/history", response_model=List[PriceHistoryResponse])
async def get_price_history(
    product_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(get_rate_limited),
):
    """Get price history for all stores of a product."""
    # Get all aliases for this product
    aliases = db.query(ProductAlias).filter(ProductAlias.product_id == product_id).all()
    
    history_by_store = []
    
    for alias in aliases:
        history = (
            db.query(PriceHistory)
            .filter(PriceHistory.alias_id == alias.id)
            .order_by(PriceHistory.recorded_at)
            .all()
        )
        
        if history:
            store = db.query(Store).filter(Store.id == alias.store_id).first()
            points = [
                PriceHistoryPoint(price=h.price, recorded_at=h.recorded_at)
                for h in history
            ]
            
            history_by_store.append(PriceHistoryResponse(
                alias_id=alias.id,
                store_name=store.name if store else "Unknown",
                history=points
            ))
    
    return history_by_store