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
from app.services.search import best_savings, search_products
from app.config import get_settings
from app.services.cache import cached_json, catalogue_version, store_json
import hashlib

router = APIRouter()
settings = get_settings()


@router.get("/search", response_model=TieredSearchResponse)
async def search(
    request: Request,
    q: str = Query(..., min_length=2, max_length=100),
    category: Optional[str] = Query(None, max_length=50),
    sort: str = Query("price_asc", pattern=r"^(price_asc|price_desc|name)$"),
    page: int = Query(1, ge=1, le=100),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    _: None = Depends(get_rate_limited),
):
    """
    Search products, grouped by how well they match the query.

    Returns three buckets -- exact, close (85-99%), similar (70-84%) -- each
    carrying the reason it landed there, e.g. "different colour (blue, not
    black)". See app/services/search.py for the two-stage design.

    `limit` and `page` apply PER TIER: paging a flattened list would let a long
    tail of similar products push the exact match onto page two.
    """
    # Every parameter that changes the response must be in the cache key, or
    # page 2 gets served page 1's rows.
    # The catalogue version is part of the key, so a merchant repricing a
    # listing or an admin verifying a store retires every cached result at
    # once instead of leaving search five minutes behind the product page.
    version = await catalogue_version()
    fingerprint = f"{q.strip().lower()}|{category or ''}|{sort}|{page}|{limit}"
    cache_key = (
        f"search:v3:{version}:{hashlib.sha256(fingerprint.encode()).hexdigest()}"
    )

    # cached_json swallows every failure, the connection included. The cache
    # is an optimisation and must never be able to fail a search.
    cached = await cached_json(cache_key)
    if cached is not None:
        return TieredSearchResponse.model_validate(cached)

    response = search_products(
        db, q, category=category, sort=sort, page=page, limit=limit
    )
    await store_json(cache_key, response.model_dump(mode="json"))
    return response


@router.get("/deals")
async def deals(
    limit: int = Query(8, ge=1, le=24),
    db: Session = Depends(get_db),
    _: None = Depends(get_rate_limited),
):
    """
    Products where shopping around saves the most, for the home page.

    Declared BEFORE /{product_id}: FastAPI matches routes in order, so with
    the dynamic route first a request for /products/deals would be parsed as
    a product id of "deals" and fail validation.
    """
    version = await catalogue_version()
    cache_key = f"deals:v1:{version}:{limit}"

    cached = await cached_json(cache_key)
    if cached is not None:
        return cached

    results = best_savings(db, limit=limit)
    await store_json(cache_key, results)
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
        # An unverified merchant store must not reach a shopper here either.
        # The comparison table is the most visible place a fabricated price
        # could land, so the same predicate that guards search guards it.
        .filter(Store.visible_to_shoppers())
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
            match_confidence=alias.match_confidence,
            phone=store.phone,
            whatsapp=store.whatsapp,
            facebook_url=store.facebook_url,
            is_merchant=store.is_merchant,
            condition=alias.condition,
            comparison_group=alias.comparison_group,
            battery_health=alias.battery_health,
            has_damage=alias.has_damage,
            damage_notes=alias.damage_notes,
            warranty_months=alias.warranty_months,
            listing_notes=alias.listing_notes,
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
    """
    Price history for every visible store listing this product.

    ONE QUERY, NOT ONE PER STORE. This used to load the aliases, then run a
    history query for each, then a store lookup for each again -- four shops
    meant nine round trips, and the count grew with every shop that started
    stocking the product. That is the same shape price_summary() was
    rewritten to avoid; the comment there still reads "20 results meant 21
    round trips".

    Grouping in Python is safe here in a way it is not for the deals list:
    the rows are already restricted to one product.
    """
    rows = (
        db.query(PriceHistory, ProductAlias.id.label("alias_id"), Store.name)
        .join(ProductAlias, ProductAlias.id == PriceHistory.alias_id)
        .join(Store, Store.id == ProductAlias.store_id)
        .filter(ProductAlias.product_id == product_id)
        # Same visibility rule as the price table. Without it an unverified
        # store's history is readable even though its current price is
        # hidden, which leaks both the price and that the store exists.
        .filter(Store.visible_to_shoppers())
        .order_by(PriceHistory.recorded_at)
        .all()
    )

    by_alias: dict[int, dict] = {}
    for record, alias_id, store_name in rows:
        bucket = by_alias.setdefault(
            alias_id, {"store_name": store_name, "points": []}
        )
        bucket["points"].append(
            PriceHistoryPoint(price=record.price, recorded_at=record.recorded_at)
        )

    return [
        PriceHistoryResponse(
            alias_id=alias_id,
            store_name=bucket["store_name"],
            history=bucket["points"],
        )
        for alias_id, bucket in by_alias.items()
    ]
