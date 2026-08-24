"""Email delivery: an interface, a dev backend that costs nothing, and SMTP."""

from __future__ import annotations

import logging
from functools import lru_cache

from app.config import get_settings
from app.services.email.base import EmailSender, Message, NullSender
from app.services.email.console import ConsoleSender
from app.services.email.smtp import SMTPSender

logger = logging.getLogger("app.email")

BACKENDS = {
    "console": ConsoleSender,
    "smtp": SMTPSender,
    "null": NullSender,
}


@lru_cache()
def get_sender() -> EmailSender:
    """
    Build the configured backend.

    Production refuses to fall back to the console backend silently: an app
    that believes it is emailing users while writing to stdout is worse than
    one that fails loudly, because nobody notices until a user reports that no
    verification link ever arrived.
    """
    settings = get_settings()
    backend = (settings.email_backend or "console").lower()

    if settings.is_production and backend == "console":
        raise RuntimeError(
            "EMAIL_BACKEND=console in production. Set EMAIL_BACKEND=smtp with "
            "SMTP credentials, or set it explicitly to 'null' to accept that no "
            "mail will be sent."
        )

    sender = BACKENDS.get(backend)
    if sender is None:
        raise RuntimeError(
            f"Unknown EMAIL_BACKEND {backend!r}. Known: {sorted(BACKENDS)}"
        )
    return sender()


def send(message: Message) -> bool:
    """
    Send, returning whether it succeeded.

    Never raises. Callers are registration and the alert run: a mail outage
    must not fail a signup or abandon a scrape partway through.
    """
    try:
        get_sender().send(message)
        return True
    except Exception:
        logger.error(
            "Email could not be sent",
            exc_info=True,
            extra={"action": "email_send", "success": False},
        )
        return False


__all__ = ["EmailSender", "Message", "NullSender", "get_sender", "send", "BACKENDS"]
