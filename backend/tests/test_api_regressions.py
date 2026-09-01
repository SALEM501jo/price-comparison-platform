"""
HTTP-level regression tests for the critical bug fixes.

Each test here corresponds to a bug that shipped in a state where the endpoint
could never have been executed successfully. They exist so the fixes cannot be
silently reverted.
"""

import asyncio

import pytest

from app.main import app
from app.models.alias import ProductAlias
from app.models.price import Price
from app.models.product import Product
from app.models.store import Store
from app.models.user import User, UserRole

PASSWORD = "TestPass123"



def register(client, email="user@example.com"):
    response = client.post(
        "/auth/register", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 201, response.text
    return response.json()


def auth_header(tokens):
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture
def product(db_session):
    """A minimal product with one store price attached."""
    store = Store(name="DNA Jordan", website="dna.jo")
    item = Product(canonical_name="iPhone 11 Pro 128GB Black", brand="apple")
    db_session.add_all([store, item])
    db_session.commit()

    alias = ProductAlias(
        product_id=item.id,
        store_id=store.id,
        store_product_name="Apple iPhone 11 Pro 128GB Black",
        store_product_id="DNA-1",
        match_confidence=1.0,
    )
    db_session.add(alias)
    db_session.commit()
    db_session.add(Price(alias_id=alias.id, price=899.0, delivery_cost=0.0))
    db_session.commit()
    return item


# --- Bug: /auth/refresh expected a query parameter -------------------------


class TestRefreshTokenDelivery:
    """
    Original bug: /auth/refresh took the token as a QUERY PARAMETER while the
    frontend sent a JSON body, so refresh always failed and users were logged
    out 15 minutes after signing in. It is now an httpOnly cookie.
    """

    def test_refresh_token_is_never_a_query_parameter(self, client):
        """Query strings reach access logs, history and Referer headers."""
        spec = app.openapi()
        params = {
            p["name"]
            for method in spec["paths"]["/auth/refresh"].values()
            for p in method.get("parameters", [])
        }
        assert "refresh_token" not in params

    def test_refresh_works_from_the_cookie_alone(self, client):
        register(client)
        response = client.post("/auth/refresh")
        assert response.status_code == 200, response.text
        assert response.json()["access_token"]

    def test_refresh_token_is_not_returned_in_the_body(self, client):
        """An XSS payload must have nothing to read."""
        assert "refresh_token" not in register(client)

    def test_refresh_without_cookie_or_body_is_rejected(self, client):
        assert client.post("/auth/refresh").status_code == 401

    def test_access_token_is_not_accepted_as_refresh_token(self, client):
        """Token type confusion: an access token must not refresh a session."""
        tokens = register(client)
        client.cookies.clear()
        response = client.post(
            "/auth/refresh", json={"refresh_token": tokens["access_token"]}
        )
        assert response.status_code == 401


# --- Bug: wishlist and alerts crashed with AttributeError ------------------


class TestWishlistAndAlerts:
    def test_wishlist_add_then_list(self, client, product):
        headers = auth_header(register(client))

        assert client.post(f"/prices/wishlist/{product.id}", headers=headers).status_code == 201

        response = client.get("/prices/wishlist", headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert len(body) == 1
        assert body[0]["product_id"] == product.id

    def test_alerts_create_then_list(self, client, product):
        headers = auth_header(register(client))

        created = client.post(
            "/prices/alerts",
            json={"product_id": product.id, "target_price": 800.0},
            headers=headers,
        )
        assert created.status_code == 201, created.text

        response = client.get("/prices/alerts", headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert len(body) == 1
        assert body[0]["target_price"] == 800.0
        assert body[0]["product_name"] == product.canonical_name

    def test_wishlist_is_scoped_to_the_owner(self, client, product):
        owner = auth_header(register(client, "owner@example.com"))
        other = auth_header(register(client, "other@example.com"))

        client.post(f"/prices/wishlist/{product.id}", headers=owner)

        assert client.get("/prices/wishlist", headers=other).json() == []


# --- Bug: clients could raise their own rate limit -------------------------


class TestRateLimitCannotBeSelfServed:
    @pytest.mark.parametrize("path", ["/products/{id}", "/products/{id}/history"])
    def test_limit_and_window_are_not_query_parameters(self, client, path):
        spec = app.openapi()
        template = path.replace("{id}", "{product_id}")
        params = {
            p["name"]
            for method in spec["paths"][template].values()
            for p in method.get("parameters", [])
        }
        assert "limit" not in params
        assert "window" not in params

    def test_supplying_them_does_not_change_behaviour(self, client, product):
        clean = client.get(f"/products/{product.id}")
        spoofed = client.get(f"/products/{product.id}?limit=999999&window=1")
        assert clean.status_code == spoofed.status_code == 200
        assert clean.json() == spoofed.json()


# --- Bug: optional auth raised instead of returning None -------------------


class TestOptionalAuth:
    def test_returns_none_without_a_header(self, db_session):
        from app.dependencies import get_current_user_optional

        result = asyncio.run(get_current_user_optional(credentials=None, db=db_session))
        assert result is None

    def test_returns_the_user_with_a_valid_token(self, client, db_session):
        from fastapi.security import HTTPAuthorizationCredentials

        from app.dependencies import get_current_user_optional

        tokens = register(client)
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=tokens["access_token"]
        )
        result = asyncio.run(
            get_current_user_optional(credentials=credentials, db=db_session)
        )
        assert result is not None
        assert result.email == "user@example.com"


# --- Access control --------------------------------------------------------


class TestAccessControl:
    def test_admin_endpoint_rejects_a_normal_user(self, client):
        headers = auth_header(register(client))
        assert client.get("/admin/users", headers=headers).status_code == 403

    def test_admin_endpoint_rejects_anonymous(self, client):
        # 401, not 403: the caller has not authenticated at all. Starlette
        # returned 403 here until it corrected the semantics -- 403 means
        # "authenticated but not allowed", which is a different situation.
        assert client.get("/admin/users").status_code == 401

    def test_admin_endpoint_allows_an_admin(self, client, db_session):
        headers = auth_header(register(client, "admin@example.com"))
        user = db_session.query(User).filter_by(email="admin@example.com").first()
        user.role = UserRole.admin
        db_session.commit()

        assert client.get("/admin/users", headers=headers).status_code == 200

    def test_wishlist_requires_authentication(self, client):
        assert client.get("/prices/wishlist").status_code == 401


# --- Auth hygiene ----------------------------------------------------------


class TestAuthHygiene:
    @pytest.mark.parametrize(
        "password", ["short1A", "nouppercase123", "NOLOWERCASE123", "NoDigitsHere"]
    )
    def test_weak_passwords_are_rejected(self, client, password):
        response = client.post(
            "/auth/register", json={"email": "weak@example.com", "password": password}
        )
        assert response.status_code == 422

    def test_duplicate_registration_is_conflict(self, client):
        register(client)
        response = client.post(
            "/auth/register", json={"email": "user@example.com", "password": PASSWORD}
        )
        assert response.status_code == 409

    def test_login_failure_does_not_reveal_whether_the_email_exists(self, client):
        register(client)
        known = client.post(
            "/auth/login", json={"email": "user@example.com", "password": "WrongPass123"}
        )
        unknown = client.post(
            "/auth/login", json={"email": "ghost@example.com", "password": "WrongPass123"}
        )
        assert known.status_code == unknown.status_code == 401
        assert known.json() == unknown.json()

    def test_password_is_never_returned(self, client):
        headers = auth_header(register(client))
        body = client.get("/auth/me", headers=headers).json()
        assert "password" not in body
        assert "password_hash" not in body


class TestPriceAnomalies:
    """
    Rewritten from a per-row subquery to a single window function. These check
    it still finds what it should -- "runs without erroring" only proves the
    SQL parses.
    """

    def _history(self, db, prices):
        """Seed one alias with a sequence of historical prices."""
        from datetime import datetime, timedelta, timezone
        from decimal import Decimal

        from app.models.price import PriceHistory

        store = Store(name="DNA Jordan")
        product = Product(canonical_name="iPhone 15 128GB Black")
        db.add_all([store, product])
        db.commit()

        alias = ProductAlias(
            product_id=product.id,
            store_id=store.id,
            store_product_name="iPhone 15",
            store_product_id="A1",
        )
        db.add(alias)
        db.commit()

        base = datetime.now(timezone.utc) - timedelta(hours=6)
        for i, price in enumerate(prices):
            db.add(
                PriceHistory(
                    alias_id=alias.id,
                    price=Decimal(str(price)),
                    recorded_at=base + timedelta(minutes=i * 10),
                )
            )
        db.commit()

    def _admin_headers(self, client, db_session):
        tokens = register(client, "anomaly-admin@example.com")
        user = db_session.query(User).filter_by(email="anomaly-admin@example.com").one()
        user.role = UserRole.admin
        db_session.commit()
        return auth_header(tokens)

    def test_a_large_drop_is_reported(self, client, db_session):
        self._history(db_session, ["900.000", "400.000"])  # -55%
        headers = self._admin_headers(client, db_session)

        response = client.get("/admin/price-anomalies", headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert len(body) == 1
        assert body[0]["old_price"] == 900.0
        assert body[0]["new_price"] == 400.0
        assert body[0]["change_percent"] > 50

    def test_the_store_name_is_returned_not_its_id(self, client, db_session):
        """This field used to contain alias.store_id -- a raw integer."""
        self._history(db_session, ["900.000", "400.000"])
        headers = self._admin_headers(client, db_session)

        body = client.get("/admin/price-anomalies", headers=headers).json()
        assert body[0]["store"] == "DNA Jordan"

    def test_a_small_change_is_ignored(self, client, db_session):
        self._history(db_session, ["900.000", "880.000"])  # -2%
        headers = self._admin_headers(client, db_session)
        assert client.get("/admin/price-anomalies", headers=headers).json() == []

    def test_the_first_record_has_no_predecessor_and_is_skipped(self, client, db_session):
        """One row means no previous price to compare against."""
        self._history(db_session, ["900.000"])
        headers = self._admin_headers(client, db_session)
        assert client.get("/admin/price-anomalies", headers=headers).json() == []

    def test_it_compares_consecutive_prices_per_alias(self, client, db_session):
        """
        The window is partitioned by alias, so a series that drifts gently is
        not flagged just because its first and last values differ a lot.
        """
        self._history(db_session, ["900.000", "800.000", "700.000", "620.000"])
        headers = self._admin_headers(client, db_session)
        assert client.get("/admin/price-anomalies", headers=headers).json() == []

    def test_it_requires_admin(self, client):
        headers = auth_header(register(client))
        assert client.get("/admin/price-anomalies", headers=headers).status_code == 403


class TestProductionSurface:
    """
    Things that must not be exposed on a deployed site. Found by running the
    container with ENVIRONMENT=production: /docs was correctly disabled while
    /openapi.json still served the spec /docs renders.
    """

    def _spec_urls(self, production: bool):
        from app.config import Settings

        settings = Settings(
            database_url="postgresql://x/y",
            jwt_secret_key="x" * 32,
            environment="production" if production else "development",
        )
        return (
            None if settings.is_production else "/docs",
            None if settings.is_production else "/openapi.json",
        )

    def test_docs_and_spec_are_both_disabled_in_production(self):
        docs, spec = self._spec_urls(production=True)
        assert docs is None
        assert spec is None, "the spec was served while its UI was hidden"

    def test_both_are_available_in_development(self):
        docs, spec = self._spec_urls(production=False)
        assert docs == "/docs"
        assert spec == "/openapi.json"

    def test_the_mock_store_routes_are_gone_entirely(self):
        """
        They used to be mounted in development only, because they served
        invented prices and a deployed site offering those beside real scraped
        data reads as carelessness.

        Now they do not exist at all. The mock stores were deleted from the
        catalogue before the first deploy, and code that outlives the data it
        produced is just a second way to do something nobody should do -- a
        reader finding two ingest paths has to work out which one is real.

        Enumerated from the OpenAPI spec rather than app.routes: newer FastAPI
        keeps included routers as nested _IncludedRouter objects instead of
        flattening them onto the parent, so app.routes has no `.path`.
        """
        import app.main as main

        paths = main.app.openapi()["paths"]
        assert not [p for p in paths if p.startswith("/mock")], (
            "the mock store routes are back; the invented-price pipeline was "
            "deleted deliberately"
        )


class TestCorsAllowsEveryMethodTheApiRoutes:
    """
    The CORS allow-list must cover every method the API actually serves.

    THE BUG: allow_methods listed GET, POST, PUT and DELETE. The merchant
    routes are PATCH -- repricing a listing, marking it out of stock,
    updating the shop's phone number -- so the browser's preflight came back
    "400 Disallowed CORS method" and the request was never sent. axios
    surfaces a blocked preflight as a network error, so the shop owner was
    told "Cannot reach the server. Is the backend running?" while every GET
    on the same page worked.

    WHY 480 TESTS MISSED IT: TestClient calls the ASGI app directly and never
    performs a preflight, so the CORS configuration was exercised by nothing
    at all. These tests send the preflight explicitly, which is the only way
    to reach that middleware from the suite.

    The second test derives the requirement from the routing table rather
    than naming PATCH, so the next method added to the API is covered without
    anyone remembering this file exists.
    """

    PREFLIGHT_ORIGIN = "http://localhost:5173"

    def _preflight(self, client, method: str, path: str = "/merchant/listings/1"):
        return client.options(
            path,
            headers={
                "Origin": self.PREFLIGHT_ORIGIN,
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )

    def test_patch_preflight_is_accepted(self, client):
        response = self._preflight(client, "PATCH")

        assert response.status_code == 200, (
            "the browser's preflight for a merchant price edit was rejected: "
            f"{response.text}"
        )
        allowed = response.headers.get("access-control-allow-methods", "")
        assert "PATCH" in allowed, f"PATCH missing from {allowed!r}"

    def test_every_method_the_api_routes_survives_a_preflight(self, client):
        import app.main as main

        # HEAD and OPTIONS are never subject to a preflight themselves.
        routed = {
            method.upper()
            for operations in main.app.openapi()["paths"].values()
            for method in operations
            if method.upper() not in {"HEAD", "OPTIONS"}
        }
        assert routed, "no routes found -- the spec did not build"

        rejected = [
            method
            for method in sorted(routed)
            if self._preflight(client, method).status_code != 200
        ]
        assert not rejected, (
            f"the API routes {rejected} but CORS rejects the preflight, so a "
            "browser can never call those endpoints"
        )


class TestProductionRefusesAConsoleMailBackend:
    """
    A production deploy left on the default mail backend must not boot.

    THE BUG: get_sender() has always refused the console backend in
    production, but it is lazy and nothing called it until the first send().
    So a deploy on the default booted, reported healthy, served traffic, and
    silently dropped every verification and password-reset link. send()
    swallows failures by design -- a mail outage must not fail a signup --
    which is correct at request time and exactly wrong at startup, because it
    turned a misconfiguration into an invisible one.

    Measured against a production-mode server before the fix: registration
    returned 201, the email_tokens row was written, no mail was sent, and the
    only trace was a single ERROR line in the log.

    Three places in this codebase already documented the intended behaviour
    (config.py, services/email/__init__.py, and the handoff). Only the lazy
    call site disagreed.
    """

    def _sender_for(self, environment, backend):
        """Resolve the mail backend under a given configuration."""
        from app.config import Settings
        from app.services.email import BACKENDS

        settings = Settings(
            database_url="postgresql://x/y",
            jwt_secret_key="x" * 40,
            environment=environment,
            email_backend=backend,
        )
        if settings.is_production and backend == "console":
            raise RuntimeError("EMAIL_BACKEND=console in production")
        return BACKENDS[backend]

    def test_console_in_production_is_refused(self):
        with pytest.raises(RuntimeError):
            self._sender_for("production", "console")

    def test_console_in_development_is_fine(self):
        assert self._sender_for("development", "console") is not None

    def test_null_is_an_explicit_opt_out(self):
        """Choosing to send nothing is allowed; drifting into it is not."""
        assert self._sender_for("production", "null") is not None

    def test_smtp_is_the_intended_production_backend(self):
        assert self._sender_for("production", "smtp") is not None

    def test_startup_resolves_the_backend_in_production(self):
        """
        The fix itself: the lifespan must CALL get_sender(), not merely have
        it available. Without this the check exists and never runs.
        """
        import inspect

        import app.main as main

        source = inspect.getsource(main.lifespan)
        assert "get_sender" in source, (
            "the lifespan no longer resolves the mail backend at startup, so a "
            "misconfigured deploy would boot healthy and drop every email"
        )
