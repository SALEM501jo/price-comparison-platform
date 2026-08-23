"""
Tests for the rate limiter, against a real Redis protocol implementation.

The pytest API tests stub the limiter out entirely so they stay deterministic,
and the smoke test can only exercise it when a Redis server is actually
reachable. That left the single control protecting login from brute force
completely unverified. fakeredis runs the real INCR / EXPIRE / TTL command path
in-process, so the counting logic is tested without needing a container.

What this does NOT cover: real network behaviour, Redis eviction under memory
pressure, and clustering. Those still need the smoke test against a live server.
"""

import fakeredis.aioredis
import pytest
from fastapi import HTTPException

from app.security import rate_limiter


class DummyClient:
    def __init__(self, host: str):
        self.host = host


class DummyURL:
    def __init__(self, path: str):
        self.path = path


class DummyRequest:
    """Minimal stand-in for starlette's Request: the limiter only reads these."""

    def __init__(self, ip: str = "1.2.3.4", path: str = "/auth/login"):
        self.client = DummyClient(ip)
        self.url = DummyURL(path)


@pytest.fixture
def fake_redis(monkeypatch):
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def get_fake():
        return client

    monkeypatch.setattr(rate_limiter, "get_redis", get_fake)
    return client


async def hit(request, limit=5, window=60):
    """Call the limiter once; return True if allowed, False if refused."""
    try:
        await rate_limiter._enforce(request, limit=limit, window=window)
        return True
    except HTTPException as exc:
        assert exc.status_code == 429
        return False


@pytest.mark.asyncio
class TestCounting:
    async def test_requests_under_the_limit_are_allowed(self, fake_redis):
        request = DummyRequest()
        for _ in range(5):
            assert await hit(request, limit=5) is True

    async def test_the_request_after_the_limit_is_refused(self, fake_redis):
        request = DummyRequest()
        for _ in range(5):
            await hit(request, limit=5)
        assert await hit(request, limit=5) is False

    async def test_it_keeps_refusing_once_over(self, fake_redis):
        request = DummyRequest()
        for _ in range(5):
            await hit(request, limit=5)
        assert [await hit(request, limit=5) for _ in range(3)] == [False, False, False]

    async def test_limit_of_one_allows_exactly_one(self, fake_redis):
        request = DummyRequest()
        assert await hit(request, limit=1) is True
        assert await hit(request, limit=1) is False


@pytest.mark.asyncio
class TestBucketIsolation:
    async def test_different_ips_have_separate_budgets(self, fake_redis):
        attacker = DummyRequest(ip="1.1.1.1")
        innocent = DummyRequest(ip="2.2.2.2")

        for _ in range(6):
            await hit(attacker, limit=5)

        assert await hit(attacker, limit=5) is False
        assert await hit(innocent, limit=5) is True, "one IP exhausted another's budget"

    async def test_different_endpoints_have_separate_budgets(self, fake_redis):
        login = DummyRequest(path="/auth/login")
        search = DummyRequest(path="/products/search")

        for _ in range(6):
            await hit(login, limit=5)

        assert await hit(login, limit=5) is False
        assert await hit(search, limit=5) is True


@pytest.mark.asyncio
class TestResponseShape:
    async def test_refusal_carries_a_retry_after_header(self, fake_redis):
        request = DummyRequest()
        for _ in range(5):
            await hit(request, limit=5)

        with pytest.raises(HTTPException) as caught:
            await rate_limiter._enforce(request, limit=5, window=60)

        assert caught.value.status_code == 429
        assert "Retry-After" in caught.value.headers
        assert int(caught.value.headers["Retry-After"]) > 0

    async def test_expiry_is_set_on_the_first_request(self, fake_redis):
        request = DummyRequest(ip="9.9.9.9", path="/auth/login")
        await hit(request, limit=5, window=60)

        ttl = await fake_redis.ttl("ratelimit:9.9.9.9:/auth/login")
        assert 0 < ttl <= 60, "key would never expire, locking the client out forever"


@pytest.mark.asyncio
class TestFailureMode:
    async def test_it_fails_open_when_redis_is_unreachable(self, monkeypatch):
        """
        DELIBERATE TRADE-OFF: a Redis outage degrades protection rather than
        taking the platform down. This test documents that choice so it cannot
        change silently.
        """

        async def broken():
            raise ConnectionError("redis is down")

        monkeypatch.setattr(rate_limiter, "get_redis", broken)

        assert await hit(DummyRequest(), limit=1) is True
        assert await hit(DummyRequest(), limit=1) is True


@pytest.mark.asyncio
class TestConfiguredLimits:
    async def test_strict_limit_is_stricter_than_the_default(self, fake_redis):
        from app.config import get_settings

        settings = get_settings()
        assert settings.strict_rate_limit_requests < settings.rate_limit_requests

    async def test_strict_rate_limit_refuses_the_sixth_login_attempt(self, fake_redis):
        """The brute-force control on /auth/login, end to end."""
        request = DummyRequest(path="/auth/login")

        allowed = 0
        refused = 0
        for _ in range(8):
            try:
                await rate_limiter.strict_rate_limit(request)
                allowed += 1
            except HTTPException as exc:
                assert exc.status_code == 429
                refused += 1

        assert allowed == 5, f"expected 5 attempts through, got {allowed}"
        assert refused == 3
