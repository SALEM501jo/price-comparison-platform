"""
Shared test setup.

WHY THIS EXISTS: the search and deals endpoints cache their responses in
Redis, and Redis is a real server shared by every test in the run. Each test
gets a fresh in-memory database, but they all talked to the same cache, so one
test's answer was served to the next. Two tests failed that way -- a deals list
computed for one fixture came back for a completely different one -- and the
ones that passed only did so because merchant writes happened to bump the
cache version between them. That is luck, not isolation.

Disabling the cache for tests rather than flushing it between them: flushing
would still leave a window where a parallel run interferes, and every cache
call in the application is already wrapped so that an unreachable Redis
degrades to "no cache". Making it unreachable is the smallest change that
makes each test depend only on its own data.

The application's caching behaviour is exercised against the real server
instead, where it belongs.
"""

import pytest


@pytest.fixture(autouse=True)
def no_response_cache(monkeypatch):
    async def always_miss(*args, **kwargs):
        return None

    async def discard(*args, **kwargs):
        return None

    # Patched where they are USED, not only where they are defined:
    # products.py does `from app.services.cache import cached_json`, which
    # binds the function into that module's namespace, so patching the source
    # module alone would leave the already-imported reference untouched.
    for target in (
        "app.services.cache.cached_json",
        "app.routers.products.cached_json",
    ):
        monkeypatch.setattr(target, always_miss, raising=False)
    for target in (
        "app.services.cache.store_json",
        "app.routers.products.store_json",
    ):
        monkeypatch.setattr(target, discard, raising=False)
