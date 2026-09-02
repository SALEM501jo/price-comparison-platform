"""
Product search and comparison routes.
"""

from fastapi import APIRouter, Depends, Query, Request, HTTPException, Response, status
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import Literal, Optional, List

from pydantic import BaseModel
from app.database import get_db
from app.dependencies import get_rate_limited
from app.models.product import Product
from app.models.alias import ProductAlias
from app.models.price import Price, PriceHistory
from app.models.store import Store
from app.models.contact_event import ContactEvent
from app.schemas.product import (
    ProductDetailResponse,
    StorePriceResponse,
    PriceHistoryResponse,
    PriceHistoryPoint
)
from app.schemas.search import SearchSuggestion, TieredSearchResponse
from app.matching import arabic, normalize
from app.matching import spelling
from app.services import photos
from app.services import catalogue
from app.services.deals import best_savings
from app.services.search import escape_like, search_products
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
    correct: bool = Query(
        True,
        description="Set false to search exactly what was typed. This is what "
        "the 'search instead for' link uses -- without it the server would "
        "just re-apply the same correction and the link would do nothing.",
    ),
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
    fingerprint = (
        f"{q.strip().lower()}|{category or ''}|{sort}|{page}|{limit}|{correct}"
    )
    cache_key = (
        f"search:v3:{version}:{hashlib.sha256(fingerprint.encode()).hexdigest()}"
    )

    # cached_json swallows every failure, the connection included. The cache
    # is an optimisation and must never be able to fail a search.
    cached = await cached_json(cache_key)
    if cached is not None:
        return TieredSearchResponse.model_validate(cached)

    response = search_products(
        db,
        q,
        category=category,
        sort=sort,
        page=page,
        limit=limit,
        allow_correction=correct,
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


@router.get("/browse")
async def browse(
    category: Optional[str] = Query(None, max_length=50),
    limit: int = Query(12, ge=1, le=48),
    db: Session = Depends(get_db),
    _: None = Depends(get_rate_limited),
):
    """
    A slice of the catalogue for someone who has not searched yet.

    WHY THIS EXISTS: the home page was built entirely on /deals, which can
    only show a product carried by two or more shops -- exactly ONE product in
    the real catalogue. A landing page with 423 products behind it rendered a
    single card. Savings answer "where is shopping around worth it"; this
    answers "what do you have", and they are different questions.

    Declared BEFORE /{product_id} for the same reason /deals and /suggest are:
    FastAPI matches in order, so the dynamic route would swallow "browse" and
    fail to validate it as an integer.

    Cached on the catalogue version like the deals query, so a scrape or a
    merchant edit invalidates it and nothing else has to.
    """
    version = await catalogue_version()
    cache_key = f"browse:v1:{version}:{category or 'all'}:{limit}"

    cached = await cached_json(cache_key)
    if cached is not None:
        return cached

    payload = {
        "categories": catalogue.category_counts(db),
        "products": catalogue.browse(db, category=category, limit=limit),
    }
    await store_json(cache_key, payload)
    return payload


@router.get("/suggest", response_model=List[SearchSuggestion])
async def suggest(
    q: str = Query(..., min_length=1, max_length=100),
    limit: int = Query(8, ge=1, le=20),
    db: Session = Depends(get_db),
    _: None = Depends(get_rate_limited),
):
    """
    Type-ahead suggestions, from the catalogue itself rather than a word list.

    DECLARED BEFORE /{product_id} for the same reason /deals is: FastAPI
    matches in order, so the dynamic route would otherwise swallow "suggest"
    and fail validating it as an integer.

    WHY SUGGEST REAL PRODUCT NAMES: the platform's whole argument is that a
    shopper should state the exact variant -- "iPhone 15 128GB Black", not
    "iPhone". A suggestion list made of real catalogue entries teaches that by
    example, and every suggestion is guaranteed to return something, which a
    generated word list cannot promise.

    The query is normalised first, so an Arabic prefix reaches the Latin
    product names it should: "ايفو" is folded to "iphone" before the LIKE.
    """
    typed = q.strip()
    if not typed:
        return []

    # ORDER MATTERS. Correct first, THEN normalise.
    #
    # Correcting after normalising was wrong for Arabic: normalize() is what
    # transliterates, so a word corrected afterwards ("سمسونج" -> "سامسونج")
    # was still Arabic when it reached a LIKE against Latin product names, and
    # matched nothing. Correcting first lets the fix flow through the
    # translation like any other word.
    #
    # expand_prefix then completes a half-typed Arabic word, which is the
    # whole point of a type-ahead: "ايفو" should list iPhones before the
    # shopper finishes typing "ايفون".
    corrected_input, _fixes = spelling.correct(typed)
    folded = normalize(corrected_input)
    corrected = normalize(arabic.expand_prefix(corrected_input))

    version = await catalogue_version()
    cache_key = (
        f"suggest:v1:{version}:{limit}:"
        f"{hashlib.sha256(corrected.encode()).hexdigest()}"
    )
    cached = await cached_json(cache_key)
    if cached is not None:
        return cached

    terms = {t for t in (folded, corrected, typed.lower()) if t}
    conditions = [
        Product.canonical_name.ilike(f"%{escape_like(term)}%", escape="\\")
        for term in terms
    ]

    rows = (
        db.query(Product)
        # Only products search can actually return. A suggestion that leads to
        # an empty result page is worse than no suggestion.
        .filter(Product.match_category.isnot(None))
        .filter(or_(*conditions))
        .order_by(func.length(Product.canonical_name), Product.id)
        .limit(limit)
        .all()
    )

    results = [
        SearchSuggestion(
            product_id=product.id,
            label=product.canonical_name,
            brand=product.brand,
            category=product.match_category,
        ).model_dump()
        for product in rows
    ]
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
            store_id=store.id,
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
            instagram_url=store.instagram_url,
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
        image_url=photos.display_image_url(
            product.id,
            product.image_url,
            photos.photo_for_product(db, product.id) is not None,
        ),
        description=product.description,
        attributes=product.match_attributes,
        prices=price_responses
    )


@router.get("/{product_id}/photo")
async def get_product_photo(
    product_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(get_rate_limited),
):
    """
    A merchant photo for this product, if a visible shop supplied one.

    ANONYMOUS ON PURPOSE, like every other part of the catalogue -- a shopper
    browsing has no account. What it will not serve is an unverified shop's
    photo: `photo_for_product` filters on the same predicate the prices do,
    so a pending claim cannot put a picture on a product page.

    Served with an ETag because these bytes come out of the database. A
    thumbnail grid that revalidates is a page of 304s with no bodies; one
    that does not is a page of blob reads on every scroll.
    """
    photo = photos.photo_for_product(db, product_id)
    if not photo:
        raise HTTPException(status_code=404, detail="No photo")

    etag = f'"{photo.checksum}"'
    if request.headers.get("if-none-match") == etag:
        # 304 carries no body, which is the entire point -- the bytes are the
        # expensive part and the browser already has them.
        return Response(status_code=304, headers={"ETag": etag})

    return Response(
        content=photo.data,
        media_type=photo.content_type,
        headers={
            "ETag": etag,
            # Content-addressed by the ETag, so a long max-age is safe: a
            # replaced photo changes the checksum and revalidates.
            "Cache-Control": "public, max-age=86400",
            # The image is served from the API's own origin, so belt and
            # braces on top of the re-encode: never let a browser sniff these
            # bytes into something executable, and never render them as a
            # document.
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
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


class ContactTap(BaseModel):
    """A shopper tapping Call, WhatsApp or Facebook on a shop's listing."""

    store_id: int
    product_id: Optional[int] = None
    # A Literal, not the enum, so an unknown channel is a 422 at the edge
    # rather than a string the handler has to remember to reject -- the same
    # treatment /admin's RoleChange gets.
    channel: Literal["call", "whatsapp", "facebook", "instagram"]


@router.post("/contact-event", status_code=status.HTTP_202_ACCEPTED)
async def record_contact(
    body: ContactTap,
    db: Session = Depends(get_db),
    _: None = Depends(get_rate_limited),
):
    """
    Record that a shopper asked for a shop's number.

    THIS IS THE ONLY EVIDENCE THE PLATFORM PRODUCES. There is no checkout, so
    a tap is the last thing visible before the conversation moves to the
    phone. Without it a merchant asked to pay has no answer to "what did I
    get for this", which the project's own notes flag as the thing to build
    before charging anyone.

    Unauthenticated, because shoppers are not required to have accounts and
    requiring one would measure only the minority who do.

    ALWAYS 202, whatever happens -- including for a store id that does not
    exist or is not publicly visible. This endpoint takes a store id from an
    anonymous caller, so a 404 would turn it into a way to enumerate which
    shops exist and which are still unverified. Nothing is written in those
    cases; the response simply does not say so.

    Stores NO personal data: see app/models/contact_event.py. The per-IP rate
    limit is what makes casual inflation tedious; it cannot make it
    impossible, which is exactly why the figure is reported as taps rather
    than as calls or customers.
    """
    store = (
        db.query(Store)
        .filter(Store.id == body.store_id)
        .filter(Store.visible_to_shoppers())
        .first()
    )
    if store is None:
        return {"status": "accepted"}

    # A product id that is not real is dropped rather than rejected: the tap
    # against the shop still happened and is the number that matters.
    product_id = body.product_id
    if product_id is not None:
        exists = db.query(Product.id).filter(Product.id == product_id).first()
        if exists is None:
            product_id = None

    db.add(
        ContactEvent(
            store_id=store.id, product_id=product_id, channel=body.channel
        )
    )
    db.commit()
    return {"status": "accepted"}
