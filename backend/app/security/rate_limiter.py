"""
Rate limiting using Redis counters.
SECURITY PRINCIPLE: Slow down attackers. Prevent brute force and credential stuffing.
"""

import logging

import redis.asyncio as aioredis
from fastapi import HTTPException, Request, status

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

# Redis client - singleton, created once, reused for all requests
_redis_client = None


async def get_redis():
    """
    Lazy initialization of the Redis client.
    WHY LAZY: if Redis is down at boot the app still starts; the first request
    that needs it will try to connect.
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


def client_ip(request: Request) -> str:
    """
    The address to rate-limit on.

    Without a proxy this is the socket peer. Behind one, every request appears
    to come from the proxy and all users collapse into a single bucket -- one
    busy user then rate-limits everybody.

    X-Forwarded-For fixes that, but it is client-supplied and each proxy
    APPENDS to it, so the list is:

        <forged by client>, <added by proxy 1>, ..., <added by proxy N>

    Everything left of the last N entries is attacker-controlled. Reading the
    leftmost value -- the common mistake -- lets a caller send
    "X-Forwarded-For: 1.2.3.4" and land in a fresh bucket on every request,
    which removes the rate limit rather than fixing it. Counting N from the
    RIGHT skips exactly the hops we control and lands on the address our
    outermost proxy observed.

    With trusted_proxy_count = 0 the header is ignored completely.
    """
    peer = request.client.host if request.client else "unknown"

    hops = settings.trusted_proxy_count
    if hops <= 0:
        return peer

    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded:
        return peer

    chain = [part.strip() for part in forwarded.split(",") if part.strip()]
    if len(chain) < hops:
        # Fewer entries than proxies means the header did not traverse the
        # expected path. Fall back to the peer rather than trusting a value
        # from an unexpected shape.
        return peer

    return chain[-hops]


async def _enforce(request: Request, limit: int, window: int) -> None:
    """
    Fixed-window counter: INCR a per-(ip, endpoint) key and EXPIRE it on the
    first hit of each window.

    HONEST DESCRIPTION OF THE ALGORITHM: this is a FIXED window, not a sliding
    one. A client can burst up to 2*limit across a window boundary. That is an
    accepted trade-off for one round-trip per request; a true sliding window
    needs a sorted set (ZADD/ZREMRANGEBYSCORE) and more memory per key.

    SECURITY - WHY limit/window LIVE ON A PRIVATE HELPER:
    FastAPI turns any plain scalar parameter of a dependency into a QUERY
    PARAMETER. When these two were parameters of the dependency itself, a
    caller could send ?limit=999999&window=1 and raise their own rate limit,
    which defeated the control entirely. Only `request` may be visible to
    FastAPI here.
    """
    key = f"ratelimit:{client_ip(request)}:{request.url.path}"

    try:
        redis = await get_redis()

        current = await redis.incr(key)
        if current == 1:
            await redis.expire(key, window)

        if current > limit:
            ttl = await redis.ttl(key)
            retry_after = ttl if ttl and ttl > 0 else window
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )

    except HTTPException:
        raise
    except Exception as exc:
        # Redis failure: fail OPEN (allow) rather than CLOSED (deny).
        # DECISION: a Redis outage should degrade protection, not take the
        # whole platform offline. The failure is logged so it is visible.
        logger.error("Rate limiter unavailable (%s). Allowing request.", exc)


async def rate_limit(request: Request) -> None:
    """Default limit for public endpoints. Use with Depends()."""
    await _enforce(
        request,
        limit=settings.rate_limit_requests,
        window=settings.rate_limit_window_seconds,
    )


async def strict_rate_limit(request: Request) -> None:
    """Stricter limit for sensitive endpoints (login, register, refresh)."""
    await _enforce(
        request,
        limit=settings.strict_rate_limit_requests,
        window=settings.strict_rate_limit_window_seconds,
    )
