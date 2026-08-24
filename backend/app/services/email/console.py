"""
Development backend: writes the message to the log instead of sending it.

This is what makes the whole feature work with no account, no domain and no
DNS records. The verification link appears in the server output, which is all
a developer needs -- and all a demo needs.

It is NOT selected automatically in production: see get_sender().
"""

from __future__ import annotations

import logging

from app.services.email.base import EmailSender, Message

logger = logging.getLogger("app.email")


class ConsoleSender(EmailSender):
    def send(self, message: Message) -> None:
        # Printed rather than logged through the JSON formatter: the point is
        # for a human to copy a link out of the terminal, and one-line JSON
        # makes that needlessly awkward.
        print(
            "\n"
            + "=" * 68
            + f"\n  EMAIL (not sent -- console backend)"
            + f"\n  To:      {message.to}"
            + f"\n  Subject: {message.subject}"
            + "\n" + "-" * 68
            + f"\n{message.text}\n"
            + "=" * 68
            + "\n",
            flush=True,
        )
        logger.info(
            "Email rendered to console",
            extra={"action": "email_console", "target": message.subject,
                   "success": True},
        )
