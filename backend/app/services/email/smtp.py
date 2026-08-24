"""
SMTP backend.

Uses the standard library rather than a provider SDK. Every free-tier
transactional provider (Resend, Brevo, SES, Mailgun) speaks SMTP, so the same
code works against any of them by changing credentials -- no dependency, no
lock-in, and nothing new for pip-audit to find a CVE in.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.config import get_settings
from app.services.email.base import EmailSender, Message

logger = logging.getLogger("app.email")
settings = get_settings()


class SMTPSender(EmailSender):
    def send(self, message: Message) -> None:
        email = EmailMessage()
        email["From"] = settings.email_from
        email["To"] = message.to
        email["Subject"] = message.subject
        email.set_content(message.text)
        if message.html:
            email.add_alternative(message.html, subtype="html")

        context = ssl.create_default_context()

        try:
            if settings.smtp_use_ssl:
                with smtplib.SMTP_SSL(
                    settings.smtp_host, settings.smtp_port, context=context, timeout=15
                ) as server:
                    self._authenticate(server)
                    server.send_message(email)
            else:
                with smtplib.SMTP(
                    settings.smtp_host, settings.smtp_port, timeout=15
                ) as server:
                    if settings.smtp_use_tls:
                        # STARTTLS upgrades a plaintext connection. Without it
                        # the credentials below cross the network in the clear.
                        server.starttls(context=context)
                    self._authenticate(server)
                    server.send_message(email)
        except Exception:
            # Log without the body: verification and reset emails contain
            # single-use credentials, and logs are shipped and widely readable.
            logger.error(
                "Email delivery failed",
                exc_info=True,
                extra={
                    "action": "email_send",
                    "target": message.subject,
                    "success": False,
                },
            )
            raise

        logger.info(
            "Email sent",
            extra={"action": "email_send", "target": message.subject, "success": True},
        )

    @staticmethod
    def _authenticate(server: smtplib.SMTP) -> None:
        if settings.smtp_username and settings.smtp_password:
            server.login(settings.smtp_username, settings.smtp_password)
