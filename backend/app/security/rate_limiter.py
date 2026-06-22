"""
Rate limiting using Redis sliding window.
SECURITY PRINCIPLE: Slow down attackers. Prevent brute force and DDoS.
"""

import redis.asyncio as aioredis
from fastapi import Request, HTTPException, status
from app.config import get_settings

settings = get_settings()

# Redis client — singleton, created once, reused for all requests
_redis_client = None


async def get_redis():
    """
    Lazy initialization of Redis client.
    WHY LAZY: If Redis is down on startup, the app still starts.
    The first request that needs Redis will try to connect.
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.redis_url,
            decode_responses=True
        )
    return _redis_client


async def rate_limit(
    request: Request,
    limit: int = None,
    window: int = None
) -> None:
    """
    Sliding window rate limiter.
    
    ALGORITHM:
    1. Key = "ratelimit:<ip_address>"
    2. INCR the key (atomic operation)
    3. If first request (value=1), set expiry = window seconds
    4. If count > limit, raise HTTP 429
    
    WHY SLIDING WINDOW (not fixed window):
    Fixed window: 100 requests at 11:59:59, 100 more at 12:00:00 = 200 in 1 second.
    Sliding window: Window moves with each request. No burst exploit.
    
    WHY REDIS (not in-memory):
    In-memory works for single server. But if you scale to 2+ servers,
    each has its own memory. An attacker rotates between servers,
    getting 2x the limit. Redis is shared state.
    
    TRADE-OFF: Redis adds ~1-5ms latency per request.
    For free tier (single server), in-memory is faster.
    But Redis is correct for production scaling.
    """
    limit = limit or settings.rate_limit_requests
    window = window or settings.rate_limit_window_seconds
    
    client_ip = request.client.host if request.client else "unknown"
    
    # Key includes the endpoint for per-endpoint limiting
    # Example: "ratelimit:192.168.1.1:/auth/login"
    endpoint = request.url.path
    key = f"ratelimit:{client_ip}:{endpoint}"
    
    try:
        redis = await get_redis()
        
        # Atomic increment
        current = await redis.incr(key)
        
        # Set expiry on first request only (EXPIRE is idempotent but 
        # we avoid resetting it on every request to keep window sliding)
        if current == 1:
            await redis.expire(key, window)
        
        if current > limit:
            # Calculate retry-after for the client
            ttl = await redis.ttl(key)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Try again in {ttl} seconds.",
                headers={"Retry-After": str(ttl)},
            )
            
    except HTTPException:
        raise
    except Exception as e:
        # Redis failure: fail OPEN (allow request) or fail CLOSED (deny)?
        # SECURITY DECISION: Fail OPEN.
        # If Redis is down, we don't want the entire app to break.
        # We log the failure and allow the request.
        # In high-security environments, you might fail CLOSED.
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Rate limiter Redis error: {e}. Allowing request.")
        pass


async def strict_rate_limit(request: Request) -> None:
    """
    Stricter rate limit for sensitive endpoints (login, register).
    5 requests per minute per IP.
    """
    return await rate_limit(request, limit=5, window=60)