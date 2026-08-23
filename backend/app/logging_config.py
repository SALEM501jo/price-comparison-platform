"""
Structured JSON logging configuration.
SECURITY PRINCIPLE: You can't investigate what you can't see.
Every auth attempt, every admin action, every price change must be auditable.
"""

import hashlib
import hmac
import json
import logging
import sys
from datetime import datetime, timezone


def pseudonymize(value: str | None) -> str | None:
    """
    Turn an identifier into a stable, non-reversible tag for logging.

    WHY: failed-login records used to write the submitted email address into
    the log verbatim. Those logs are shipped, retained and widely readable, so
    every mistyped password quietly deposited someone's address in them --
    including addresses belonging to people who never signed up.

    Keyed HMAC rather than a plain hash: an unkeyed digest of an email is
    trivially reversed by hashing a wordlist. The same address always yields
    the same tag, so brute-force attempts against one account are still
    correlatable, which is the reason the field exists at all.
    """
    if not value:
        return None

    # Imported here: app.config imports nothing from this module, but keeping
    # the dependency local avoids an import cycle if that ever changes.
    from app.config import get_settings

    digest = hmac.new(
        get_settings().jwt_secret_key.encode(),
        value.strip().lower().encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"anon:{digest[:16]}"


class JSONFormatter(logging.Formatter):
    """
    Custom formatter that outputs JSON lines.
    Machine-parseable. Ingestible by security tools.
    """
    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add extra fields if present (we'll attach these manually in routers)
        if hasattr(record, "user_id"):
            log_obj["user_id"] = record.user_id
        if hasattr(record, "ip"):
            log_obj["ip"] = record.ip
        if hasattr(record, "endpoint"):
            log_obj["endpoint"] = record.endpoint
        if hasattr(record, "action"):
            log_obj["action"] = record.action  # 'login', 'price_update', 'admin_delete'
        if hasattr(record, "success"):
            log_obj["success"] = record.success  # True/False
        if hasattr(record, "target"):
            log_obj["target"] = record.target  # What was affected (product_id, user_id)
        
        # Include exception info if present
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_obj, default=str)


def setup_logging():
    """
    Configure root logger.
    In production, you might send this to a file or external service.
    For now, stdout (Fly.io captures this).
    """
    # Remove existing handlers to prevent duplicate logs
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)
    
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    
    # Security-specific loggers
    logging.getLogger("app.security").setLevel(logging.INFO)
    logging.getLogger("app.auth").setLevel(logging.INFO)
    logging.getLogger("app.admin").setLevel(logging.WARNING)  # Admin actions are always logged
    logging.getLogger("app.scraper").setLevel(logging.INFO)


def get_security_logger(name: str = "app.security"):
    """
    Helper to get a logger with security context.
    Usage in routers:
        logger = get_security_logger("app.auth")
        logger.info("Login attempt", extra={
            "user_id": user_id,
            "ip": request.client.host,
            "action": "login",
            "success": False
        })
    """
    return logging.getLogger(name)