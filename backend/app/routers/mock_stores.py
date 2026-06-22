"""
Simulated store APIs.
These replace real web scraping with static JSON responses.
In production, you'd replace fetch_store_data() with actual HTTP calls.
"""

from fastapi import APIRouter, Query
from typing import List, Optional
from pydantic import BaseModel

router = APIRouter(prefix="/mock", tags=["mock stores"])


class MockProductResponse(BaseModel):
    store_product_id: str
    name: str
    price: float
    availability: bool
    delivery_cost: float
    url: str


class MockStoreResponse(BaseModel):
    store: str
    results: List[MockProductResponse]


# Realistic mock data — same data the scraper uses
MOCK_STORE_DATA = {
    "dna": [
        MockProductResponse(
            store_product_id="DNA-IPH15-128-BLK",
            name="Apple iPhone 15 128GB 5G Smartphone - Black",
            price=899.00,
            availability=True,
            delivery_cost=0.0,
            url="https://www.dna.jo/iphone-15-128gb-black"
        ),
        MockProductResponse(
            store_product_id="DNA-IPH15-256-BLU",
            name="Apple iPhone 15 256GB 5G - Blue",
            price=999.00,
            availability=True,
            delivery_cost=0.0,
            url="https://www.dna.jo/iphone-15-256gb-blue"
        ),
        MockProductResponse(
            store_product_id="DNA-S24-128-GRA",
            name="Samsung Galaxy S24 128GB 5G - Graphite",
            price=749.00,
            availability=True,
            delivery_cost=2.50,
            url="https://www.dna.jo/galaxy-s24-128gb-graphite"
        ),
        MockProductResponse(
            store_product_id="DNA-MBA-256-SLV",
            name="Apple MacBook Air M3 256GB SSD - Silver",
            price=1199.00,
            availability=True,
            delivery_cost=0.0,
            url="https://www.dna.jo/macbook-air-m3-256gb-silver"
        ),
        MockProductResponse(
            store_product_id="DNA-PS5-STD",
            name="Sony PlayStation 5 Standard Edition",
            price=499.00,
            availability=False,
            delivery_cost=5.00,
            url="https://www.dna.jo/playstation-5-standard"
        ),
    ],
    "smartbuy": [
        MockProductResponse(
            store_product_id="SB-IP15-128-BLK",
            name="iPhone 15 128GB Black (5G)",
            price=875.00,
            availability=True,
            delivery_cost=2.50,
            url="https://smartbuy-me.com/iphone-15-128gb-black"
        ),
        MockProductResponse(
            store_product_id="SB-IP15-256-BLU",
            name="iPhone 15 256GB Blue 5G",
            price=975.00,
            availability=True,
            delivery_cost=2.50,
            url="https://smartbuy-me.com/iphone-15-256gb-blue"
        ),
        MockProductResponse(
            store_product_id="SB-S24-128-GRA",
            name="Samsung Galaxy S24 128GB Graphite",
            price=729.00,
            availability=False,
            delivery_cost=3.00,
            url="https://smartbuy-me.com/galaxy-s24-128gb-graphite"
        ),
        MockProductResponse(
            store_product_id="SB-MBA-256-SLV",
            name="MacBook Air M3 256GB Silver",
            price=1149.00,
            availability=True,
            delivery_cost=3.00,
            url="https://smartbuy-me.com/macbook-air-m3-256gb-silver"
        ),
        MockProductResponse(
            store_product_id="SB-PS5-STD",
            name="Sony PlayStation 5 Console",
            price=489.00,
            availability=True,
            delivery_cost=4.00,
            url="https://smartbuy-me.com/playstation-5"
        ),
    ],
    "carrefour": [
        MockProductResponse(
            store_product_id="CF-IPHONE15-128-BLACK",
            name="Apple iPhone 15 128GB 5G - Midnight",
            price=889.00,
            availability=True,
            delivery_cost=0.0,
            url="https://carrefourjordan.com/iphone-15-128gb-midnight"
        ),
        MockProductResponse(
            store_product_id="CF-S24-128-GR",
            name="Samsung Galaxy S24 128GB 5G Graphite",
            price=739.00,
            availability=True,
            delivery_cost=1.50,
            url="https://carrefourjordan.com/galaxy-s24-128gb-graphite"
        ),
        MockProductResponse(
            store_product_id="CF-MBA-256-SIL",
            name="Apple MacBook Air 256GB SSD M3 Silver",
            price=1189.00,
            availability=True,
            delivery_cost=0.0,
            url="https://carrefourjordan.com/macbook-air-m3-256gb-silver"
        ),
        MockProductResponse(
            store_product_id="CF-PS5",
            name="Sony PlayStation 5 Gaming Console",
            price=495.00,
            availability=True,
            delivery_cost=2.00,
            url="https://carrefourjordan.com/playstation-5"
        ),
    ],
    "citycenter": [
        MockProductResponse(
            store_product_id="CC-IPH15-128-BLK",
            name="Apple iPhone 15 128GB Black",
            price=895.00,
            availability=True,
            delivery_cost=0.0,
            url="https://citycenter.jo/iphone-15-128gb-black"
        ),
        MockProductResponse(
            store_product_id="CC-S24-128-GRA",
            name="Samsung Galaxy S24 128GB Graphite",
            price=745.00,
            availability=True,
            delivery_cost=2.00,
            url="https://citycenter.jo/galaxy-s24-128gb-graphite"
        ),
        MockProductResponse(
            store_product_id="CC-MBA-256-SLV",
            name="Apple MacBook Air M3 256GB - Silver",
            price=1175.00,
            availability=True,
            delivery_cost=0.0,
            url="https://citycenter.jo/macbook-air-m3-256gb-silver"
        ),
        MockProductResponse(
            store_product_id="CC-PS5",
            name="Sony PS5 Standard Edition",
            price=490.00,
            availability=True,
            delivery_cost=3.00,
            url="https://citycenter.jo/playstation-5"
        ),
    ]
}


@router.get("/{store_code}/search", response_model=MockStoreResponse)
async def search_store(
    store_code: str,
    q: Optional[str] = Query(None, max_length=100)
):
    """
    Search a mock store for products.
    If 'q' is provided, filter by name. Otherwise return all.
    """
    if store_code not in MOCK_STORE_DATA:
        return MockStoreResponse(store=store_code, results=[])
    
    all_products = MOCK_STORE_DATA[store_code]
    
    if q:
        q_lower = q.lower()
        filtered = [
            p for p in all_products 
            if q_lower in p.name.lower()
        ]
        return MockStoreResponse(store=store_code, results=filtered)
    
    return MockStoreResponse(store=store_code, results=all_products)


@router.get("/stores", response_model=List[dict])
async def list_stores():
    """List all available mock stores."""
    return [
        {"code": "dna", "name": "DNA Jordan", "website": "https://www.dna.jo"},
        {"code": "smartbuy", "name": "SmartBuy", "website": "https://smartbuy-me.com"},
        {"code": "carrefour", "name": "Carrefour Jordan", "website": "https://carrefourjordan.com"},
        {"code": "citycenter", "name": "City Center", "website": "https://citycenter.jo"},
    ]