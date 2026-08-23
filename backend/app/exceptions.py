"""
Centralized exception handling.
SECURITY PRINCIPLE: Never leak internal details to the client.
An attacker should never see your file paths, DB URLs, or stack traces.
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
import logging

logger = logging.getLogger(__name__)


class AppException(Exception):
    """
    Base application exception.
    All custom exceptions inherit from this.
    'status_code' is what the client sees.
    'detail' is the user-friendly message.
    'internal' is the technical detail (logged, never sent to client).
    """
    def __init__(
        self,
        status_code: int,
        detail: str,
        internal: str | None = None
    ):
        self.status_code = status_code
        self.detail = detail
        self.internal = internal
        super().__init__(detail)


class AuthenticationError(AppException):
    """Invalid credentials, expired token, missing token."""
    def __init__(self, detail: str = "Authentication failed"):
        super().__init__(status.HTTP_401_UNAUTHORIZED, detail)


class AuthorizationError(AppException):
    """Valid token, but not enough permissions (e.g., user hitting admin endpoint)."""
    def __init__(self, detail: str = "Insufficient permissions"):
        super().__init__(status.HTTP_403_FORBIDDEN, detail)


class NotFoundError(AppException):
    """Resource doesn't exist."""
    def __init__(self, detail: str = "Resource not found"):
        super().__init__(status.HTTP_404_NOT_FOUND, detail)


class ConflictError(AppException):
    """Resource already exists (e.g., duplicate email)."""
    def __init__(self, detail: str = "Resource already exists"):
        super().__init__(status.HTTP_409_CONFLICT, detail)


class RateLimitError(AppException):
    """Too many requests."""
    def __init__(self, detail: str = "Too many requests. Please slow down."):
        super().__init__(status.HTTP_429_TOO_MANY_REQUESTS, detail)


def setup_exception_handlers(app):
    """
    Attach all exception handlers to the FastAPI app.
    Called once in main.py during startup.
    """
    
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        """
        Our custom exceptions: return structured JSON, log internals.
        The client sees only 'status_code' and 'detail'.
        The server log sees 'internal' for debugging.
        """
        logger.warning(
            f"AppException: {exc.detail} | Internal: {exc.internal} | "
            f"Path: {request.url.path} | IP: {request.client.host if request.client else 'unknown'}"
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail}
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """
        Pydantic validation failures (malformed JSON, wrong types).
        SECURITY: Don't return the raw Pydantic error dict — it reveals schema structure.
        An attacker can learn your field names and types from error messages.
        """
        # Sanitize: name the field that failed and why, but nothing about the
        # schema around it. The old format leaked the request structure into
        # the UI ("Field 'body -> password': Value error, ...") and was too
        # ugly to show a user, so clients displayed the generic detail instead
        # and the actual reason never reached anyone.
        simplified_errors = []
        for error in exc.errors():
            parts = [
                str(loc)
                for loc in error.get("loc", [])
                if loc not in ("body", "query", "path", "header")
            ]
            message = error.get("msg", "invalid")
            for noise in ("Value error, ", "Assertion failed, "):
                if message.startswith(noise):
                    message = message[len(noise):]
            simplified_errors.append(
                {"field": ".".join(parts) or "request", "message": message}
            )
        
        logger.info(
            f"Validation failed: {simplified_errors} | Path: {request.url.path} | "
            f"IP: {request.client.host if request.client else 'unknown'}"
        )
        
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "detail": "Invalid input data",
                "fields": simplified_errors  # Still useful for frontend, but limited
            }
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_exception_handler(request: Request, exc: SQLAlchemyError):
        """
        Database errors.
        SECURITY CRITICAL: Never return SQLAlchemy's raw error message.
        It might contain table names, column names, or SQL snippets.
        """
        logger.error(
            f"Database error: {str(exc)} | Path: {request.url.path} | "
            f"IP: {request.client.host if request.client else 'unknown'}",
            exc_info=True  # Full traceback in server logs only
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"}  # Generic. No details.
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError):
        """
        Unique constraint violations (duplicate email, etc.).
        These are user errors, not server errors. Return 409, not 500.
        """
        logger.warning(
            f"Integrity error: {str(exc)} | Path: {request.url.path}"
        )
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "Resource conflict. It may already exist."}
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """
        Catch-all for anything unexpected.
        This is your safety net. If an exception reaches here, it's a bug.
        The client gets a generic 500. You get a full traceback in logs.
        """
        logger.critical(
            f"Unhandled exception: {str(exc)} | Path: {request.url.path} | "
            f"IP: {request.client.host if request.client else 'unknown'}",
            exc_info=True  # Full traceback with file paths, line numbers — in logs only
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"}
        )