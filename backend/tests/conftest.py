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


# --- Shared fixtures --------------------------------------------------------
#
# These were copy-pasted into eleven test files, byte for byte. That is not
# just waste: a fixture duplicated eleven times is a fixture that gets FIXED
# in one place and stays wrong in ten, and the next person adding a test
# copies whichever version they happened to open.
#
# A test file that genuinely needs something different still defines its own;
# a fixture declared in a module shadows the one here, so overriding costs
# nothing and stays local to the file that needs it.

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


@pytest.fixture
def db_session():
    """
    A fresh in-memory database per test.

    StaticPool with check_same_thread=False because TestClient runs the app on
    another thread: the default pool would hand that thread a DIFFERENT
    connection, and an in-memory SQLite database belongs to its connection --
    so the app would find none of the rows the test had just written.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def db(db_session):
    """
    Alias for the suites that call it `db`.

    Kept rather than renamed: the point of this change is to delete
    duplication, not to churn every test that reads perfectly well already.
    """
    return db_session


@pytest.fixture
def client(db_session, monkeypatch):
    """
    A TestClient wired to the test database, with the rate limiter off.

    THE LIMITER IS NEUTRALISED because it is real and shared: 5 auth requests
    a minute against one Redis, so a suite that logs in a dozen times would
    fail on request six for reasons that have nothing to do with the code
    under test. Both rate_limit() and strict_rate_limit() funnel through
    _enforce(), so one patch covers both. The limiter's own behaviour is
    tested against the real server in scripts/e2e_test.py, where it belongs.

    create_all is patched out because the dev-convenience call in the lifespan
    is bound to the real Postgres engine, not to the SQLite session injected
    here -- without this, running the suite would need a database server up.
    """
    async def no_limit(*args, **kwargs):
        return None

    monkeypatch.setattr("app.security.rate_limiter._enforce", no_limit)
    monkeypatch.setattr(Base.metadata, "create_all", lambda *a, **k: None)

    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
