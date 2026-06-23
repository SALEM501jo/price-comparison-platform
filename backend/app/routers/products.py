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
    ProductSearchResponse, 
    ProductDetailResponse, 
    StorePriceResponse,
    PriceHistoryResponse,
    PriceHistoryPoint
)
from app.config import get_settings
import redis.asyncio as aioredis
import json

router = APIRouter()
settings = get_settings()

# Redis cache singleton
_cache = None

async def get_cache():
    global _cache
    if _cache is None:
        _cache = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _cache


@router.get("/search", response_model=List[ProductSearchResponse])
async def search(
    request: Request,
    q: str = Query(..., min_length=2, max_length=100),
    category: Optional[str] = Query(None, max_length=50),
    sort_by: str = Query("price_asc", pattern=r"^(price_asc|price_desc|name)$"),
    page: int = Query(1, ge=1, le=100),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    _: None = Depends(get_rate_limited),
):
    """
    Search products with price comparison.
    """
    # Try cache first
    cache_key = f"search:{q}:{category}:{sort_by}:{page}:{limit}"
    cache = await get_cache()
    
    try:
        cached = await cache.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception:
        pass
    
    # Build query
    query = db.query(Product)
    
    # Search by name (case-insensitive)
    if q:
        search_term = f"%{q}%"
        query = query.filter(Product.canonical_name.ilike(search_term))
    
    if category:
        query = query.filter(Product.category == category)
    
    # Get products with price stats
    products = query.offset((page - 1) * limit).limit(limit).all()
    
    results = []
    for product in products:
        # Get all prices for this product (Price -> ProductAlias -> Store)
        prices = (
            db.query(Price, ProductAlias, Store)
            .join(ProductAlias, Price.alias_id == ProductAlias.id)
            .join(Store, ProductAlias.store_id == Store.id)
            .filter(ProductAlias.product_id == product.id)
            .all()
        )
        
        if not prices:
            continue
        
        # Calculate stats
        price_values = [price.price for price, alias, store in prices if price.availability]
        lowest = min(price_values) if price_values else 0
        highest = max(price_values) if price_values else 0
        
        # Find best deal (lowest total cost = price + delivery)
        best_deal = None
        best_total = float('inf')
        for price, alias, store in prices:
            if price.availability:
                total = price.price + price.delivery_cost
                if total < best_total:
                    best_total = total
                    best_deal = store.name
        
        results.append({
            "id": product.id,
            "canonical_name": product.canonical_name,
            "brand": product.brand,
            "category": product.category,
            "image_url": product.image_url,
            "specs": product.specs,
            "lowest_price": lowest,
            "highest_price": highest,
            "store_count": len(prices),
            "best_deal_store": best_deal
        })
    
    # Sort results
    if sort_by == "price_asc":
        results.sort(key=lambda x: x["lowest_price"])
    elif sort_by == "price_desc":
        results.sort(key=lambda x: x["highest_price"], reverse=True)
    elif sort_by == "name":
        results.sort(key=lambda x: x["canonical_name"])
    
    # Cache for 5 minutes
    try:
        await cache.setex(cache_key, 300, json.dumps(results, default=str))
    except Exception:
        pass
    
    return results


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