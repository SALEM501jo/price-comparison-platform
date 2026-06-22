"""
FastAPI application assembly.
Wires all components together: routers, middleware, exception handlers, lifespan.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from contextlib import asynccontextmanager
import logging

from app.config import get_settings
from app.database import engine, Base
from app.logging_config import setup_logging
from app.exceptions import setup_exception_handlers
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.routers import auth, products, prices, admin, mock_stores

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan events.
    Startup: Create tables, setup logging.
    Shutdown: Cleanup.
    """
    # Startup
    setup_logging()
    logger.info("Application starting up...")
    
    # Create tables (use Alembic in production, this is for dev convenience)
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified")
    
    yield
    
    # Shutdown
    logger.info("Application shutting down...")


app = FastAPI(
    title="Jordan Price Comparison API",
    description="Secure price comparison platform for Jordanian retail stores",
    version="1.0.0",
    docs_url="/docs" if settings.environment == "development" else None,
    redoc_url=None,
    lifespan=lifespan,
)

# --- Exception handlers (must be first to catch all errors) ---
setup_exception_handlers(app)

# --- Middleware (order matters: outermost runs first on request) ---

# 1. Security headers (adds CSP, HSTS, etc.)
app.add_middleware(SecurityHeadersMiddleware)

# 2. CORS — strict allow-list
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# 3. Trusted host (prevents host header injection)
if settings.environment == "production":
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["your-api-domain.fly.dev"]
    )

# --- Routers ---
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(products.router, prefix="/products", tags=["products"])
app.include_router(prices.router, prefix="/prices", tags=["prices"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
app.include_router(mock_stores.router, prefix="/mock", tags=["mock stores"])


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {
        "status": "ok",
        "version": "1.0.0",
        "environment": settings.environment
    }