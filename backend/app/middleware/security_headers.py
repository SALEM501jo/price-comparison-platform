from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from app.config import get_settings

settings = get_settings()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        if settings.environment == "development":
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "img-src 'self' data: https:; "
                "font-src 'self'; "
                "connect-src 'self'; "
                "frame-ancestors 'none'; "
                "form-action 'self'; "
                "base-uri 'self'; "
            )
        else:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self'; "
                # No font host is named here because Cairo ships from our own
                # origin (frontend/public/fonts, declared in src/index.css).
                # Loading it from Google meant every visitor's IP reached
                # fonts.googleapis.com before the first paint, with no notice
                # and no consent -- the same instinct that already put
                # referrerPolicy="no-referrer" on the product images. Keeping
                # style-src and font-src at 'self' is what makes that
                # structural rather than a habit: a stray @import or a
                # copy-pasted <link> back to a font CDN now fails loudly in
                # the browser console instead of quietly leaking again.
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https:; "
                "font-src 'self'; "
                "connect-src 'self'; "
                "frame-ancestors 'none'; "
                "form-action 'self'; "
                "base-uri 'self'; "
                "upgrade-insecure-requests;"
            )

        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        if settings.environment == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), "
            "payment=(), usb=(), magnetometer=(), gyroscope=()"
        )

        # NOTE: the Server header CANNOT be removed from here. Uvicorn writes it
        # at the ASGI protocol level, after this middleware has already returned,
        # so a del here silently does nothing -- a smoke test against a running
        # server confirmed "server: uvicorn" still reaching the client.
        # It must be suppressed at the server instead:
        #     uvicorn app.main:app --no-server-header
        # (see start-dev.ps1), or stripped by the reverse proxy in production.

        return response
