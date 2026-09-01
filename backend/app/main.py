"""
FastAPI application assembly.
Wires all components together: routers, middleware, exception handlers, lifespan.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.config import get_settings
from app.database import Base, engine
from app.exceptions import setup_exception_handlers
from app.logging_config import setup_logging
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.routers import (
    admin,
    auth,
    merchant,
    mock_stores,
    prices,
    products,
    support,
)

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: logging (+ dev-only table creation). Shutdown: cleanup."""
    setup_logging()
    logger.info("Application starting up...")

    # Schema is owned by Alembic. create_all() stays available for a throwaway
    # dev database only -- running both against one DB gives two competing
    # sources of truth and silently drifts from the migration history.
    if not settings.is_production:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables verified (development convenience)")

    if settings.is_production:
        # THE REST OF THE PRODUCTION CONFIGURATION, checked the same way and
        # for the same reason: every one of these defaults to something right
        # for a laptop and wrong for the internet, and all of them fail
        # SILENTLY. A deploy that forgets TRUSTED_HOSTS serves traffic while
        # accepting any Host header; one that forgets APP_BASE_URL emails
        # verification links pointing at localhost, so nobody can ever confirm
        # an account and the only symptom is signups that never complete.
        # Nothing in a health check notices either.
        errors, warnings = settings.production_problems()
        for warning in warnings:
            logger.warning(
                "Production configuration warning: %s",
                warning,
                extra={"action": "startup_config_warning"},
            )
        if errors:
            for error in errors:
                logger.critical(
                    "Production configuration error: %s",
                    error,
                    extra={"action": "startup_config_error"},
                )
            raise RuntimeError(
                "Refusing to start: "
                + str(len(errors))
                + " production setting(s) would fail silently. "
                + " | ".join(errors)
            )

        # RESOLVE THE MAIL BACKEND AT BOOT, not at the first person who signs
        # up. get_sender() already refuses the console backend in production,
        # but it is lazy and nothing called it until send() did -- so a deploy
        # left on the default booted healthy, passed its health check, served
        # traffic, and silently dropped every verification and password-reset
        # link. send() swallows the failure by design (a mail outage must not
        # fail a signup), which is right at request time and exactly wrong at
        # startup: it turned a misconfiguration into an invisible one.
        #
        # Verified against a production-mode server before this existed:
        # registration returned 201, the token row was written, no mail went
        # anywhere, and the only trace was one ERROR line in the log.
        #
        # Failing here means the machine never reports healthy, which is what
        # every deploy platform is watching.
        from app.services.email import get_sender

        get_sender()
        logger.info(
            "Mail backend ready", extra={"action": "startup_email_check"}
        )

    yield

    logger.info("Application shutting down...")


app = FastAPI(
    title="Jordan Price Comparison API",
    description="Secure price comparison platform for Jordanian retail stores",
    version="1.0.0",
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None,
    # The spec too, not just the UI. Disabling /docs while still serving
    # /openapi.json hides the rendering and publishes the thing it renders --
    # every route, parameter and schema, which is a map of the attack surface.
    openapi_url=None if settings.is_production else "/openapi.json",
    lifespan=lifespan,
)

# --- Exception handlers (registered first so they catch everything) ---
setup_exception_handlers(app)

# --- Middleware (order matters: outermost runs first on request) ---

# 1. Security headers (CSP, HSTS, nosniff, ...)
app.add_middleware(SecurityHeadersMiddleware)

# 2. CORS - strict allow-list, never "*" while allow_credentials is on
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    # PATCH is not optional: every merchant edit uses it -- repricing a
    # listing, marking it out of stock, updating the shop's phone number --
    # and so does admin moderation. Omitting it let the browser reject the
    # preflight with "Disallowed CORS method" before the request was ever
    # sent, and axios reports that as a network failure, so the shop owner
    # was told "cannot reach the server" while every GET on the page worked.
    #
    # Not caught by the test suite because TestClient calls the app directly
    # and never performs a preflight; only a real browser exercises this.
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# 3. Trusted host (prevents Host-header injection / cache poisoning)
if settings.is_production:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_host_list)

# --- Routers ---
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(products.router, prefix="/products", tags=["products"])
app.include_router(prices.router, prefix="/prices", tags=["prices"])
app.include_router(support.router, prefix="/support", tags=["support"])
app.include_router(merchant.router, prefix="/merchant", tags=["merchant"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
# Development only. These serve invented prices, and a deployed site
# offering them next to real scraped data -- visible to anyone who opens
# /docs -- reads as carelessness rather than as a fixture.
if not settings.is_production:
    app.include_router(mock_stores.router, prefix="/mock", tags=["mock stores"])


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "ok", "version": "1.0.0", "environment": settings.environment}
