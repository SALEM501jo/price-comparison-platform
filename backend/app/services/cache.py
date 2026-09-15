"""
The search cache, and the one counter that invalidates it.

WHY A VERSION COUNTER RATHER THAN DELETING KEYS:
A search response is keyed by query, category, sort, page and limit, so a
single price change would have to invalidate an unbounded set of keys nobody
tracks. Folding a global version into every key means one INCR retires the
whole cache at once, and the stale entries expire on their own TTL.

WHAT MADE THIS NECESSARY:
Scraped prices change every six hours, so a five-minute cache was invisible.
Merchant prices change when a shop owner edits them, and an admin approving a
store expects to see it live immediately. Verified in the browser: a merchant
undercutting SmartBuy appeared on the product page at once but stayed absent
from search until the cache expired, which reads as the site being broken.

Redis is an optimisation here, never a dependency: every call degrades to
"no cache" rather than failing the request.
"""

from __future__ import annotations

import json
import logging

import redis.asyncio as aioredis

from app.config import get_settings

logger = logging.getLogger("app.cache")
settings = get_settings()

VERSION_KEY = "catalogue:version"

_client = None


async def get_cache():
    global _client
    if _client is None:
        _client = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _client


async def catalogue_version() -> str:
    """
    The current catalogue generation, as a cache-key component.

    Falls back to a constant when Redis is unreachable. That is deliberate:
    without it every request would produce a different key, so nothing would
    ever hit the cache and the fallback would be worse than no cache at all.
    """
    try:
        cache = await get_cache()
        return await cache.get(VERSION_KEY) or "0"
    except Exception:
        return "0"


async def bump_catalogue_version() -> None:
    """
    Retire every cached search result.

    Called after any write that changes what a shopper would see: a merchant
    adding or repricing a listing, and an admin granting or withdrawing a
    store's verification.
    """
    try:
        cache = await get_cache()
        await cache.incr(VERSION_KEY)
    except Exception:
        # A missed invalidation means results are stale for up to the TTL,
        # which is the behaviour we had before this existed. Not worth
        # failing a merchant's price update over.
        logger.warning("Could not bump catalogue version", exc_info=True)


def bump_catalogue_version_sync() -> None:
    """
    bump_catalogue_version() for code that is not async -- the scrape worker.

    NOT asyncio.run(bump_catalogue_version()). The async client above is a
    module-level singleton, and redis.asyncio binds its connections to the
    event loop that first used them; asyncio.run makes a new loop each call,
    so the second scrape of a worker's life would bump through a client tied
    to a closed loop, fail, and have the failure swallowed below -- leaving
    search serving pre-scrape prices until the TTL, silently. A short-lived
    synchronous client has no loop to be wrong about.
    """
    try:
        import redis

        client = redis.Redis.from_url(
            settings.redis_url, socket_timeout=5, socket_connect_timeout=5
        )
        try:
            client.incr(VERSION_KEY)
        finally:
            client.close()
    except Exception:
        logger.warning("Could not bump catalogue version", exc_info=True)


async def cached_json(key: str):
    """
    Read a cached JSON payload, or None.

    Swallows everything, including the connection itself. The routers used to
    call get_cache() outside their try/except, so an unreachable Redis would
    have turned "the cache is an optimisation" into a 500 on the two busiest
    read endpoints. from_url() is lazy, so it never bit in practice -- which
    is precisely the kind of guarantee worth making structural instead of
    relying on.
    """
    try:
        client = await get_cache()
        raw = await client.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None


async def store_json(key: str, value, ttl: int = 300) -> None:
    """Write a cached JSON payload. Never raises."""
    try:
        client = await get_cache()
        await client.setex(key, ttl, json.dumps(value, default=str))
    except Exception:
        pass
