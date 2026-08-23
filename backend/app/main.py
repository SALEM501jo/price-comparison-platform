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
from app.routers import admin, auth, mock_stores, prices, products

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

    yield

    logger.info("Application shutting down...")


app = FastAPI(
    title="Jordan Price Comparison API",
    description="Secure price comparison platform for Jordanian retail stores",
    version="1.0.0",
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None,
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
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# 3. Trusted host (prevents Host-header injection / cache poisoning)
if settings.is_production:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_host_list)

# --- Routers ---
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(products.router, prefix="/products", tags=["products"])
app.include_router(prices.router, prefix="/prices", tags=["prices"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
app.include_router(mock_stores.router, prefix="/mock", tags=["mock stores"])


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "ok", "version": "1.0.0", "environment": settings.environment}
