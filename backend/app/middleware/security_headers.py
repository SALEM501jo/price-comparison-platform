"""
HTTP Security Headers middleware.
SECURITY PRINCIPLE: The browser is a hostile environment. 
CSP tells the browser what it's allowed to execute.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from app.config import get_settings

settings = get_settings()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        
        # Content-Security-Policy: The nuclear option against XSS
        # 'self' = only same-origin resources
        # 'unsafe-inline' for styles = React injects CSS. Acceptable risk.
        # NO 'unsafe-eval' = blocks dynamic code execution (eval, setTimeout with string)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "           # JS: only our bundled files
            "style-src 'self' 'unsafe-inline'; "  # CSS: our files + inline (React needs)
            "img-src 'self' data: https:; "      # Images: us, data URIs, HTTPS stores
            "font-src 'self'; "             # Fonts: only us
            "connect-src 'self'; "          # API calls: only our backend
            "frame-ancestors 'none'; "      # No clickjacking
            "form-action 'self'; "          # Forms: only submit to us
            "base-uri 'self'; "             # <base> tag: only self
            "upgrade-insecure-requests;"     # Force HTTP→HTTPS
        )
        
        # X-Frame-Options: Legacy clickjacking protection (backup for CSP)
        response.headers["X-Frame-Options"] = "DENY"
        
        # X-Content-Type-Options: Prevent MIME sniffing
        # Browser won't guess content type. If we say it's JSON, it's JSON.
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # Referrer-Policy: Don't leak full URL to third parties
        # When user clicks external link, send only origin, not full path with query params
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Strict-Transport-Security: Force HTTPS for 1 year
        # Once browser sees this, it refuses HTTP for your domain
        # Include subdomains + preload for HSTS preload list
        if settings.environment == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )
        
        # Permissions-Policy: Disable browser features we don't need
        # Reduces attack surface. If XSS injects code, it can't access camera/mic/location
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), "
            "payment=(), usb=(), magnetometer=(), gyroscope=()"
        )
        
        # Remove server fingerprint. Don't advertise tech stack.
        # "Server: uvicorn" tells attackers exactly what to exploit
        response.headers.pop("Server", None)
        
        return response