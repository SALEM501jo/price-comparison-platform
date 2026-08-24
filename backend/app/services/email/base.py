"""
Email sending interface.

Deliberately an interface with swappable backends rather than a direct call to
a provider SDK. The engineering that matters -- token lifetime, single use,
throttling, not leaking whether an address exists -- is entirely on our side;
delivery is a detail that should be replaceable with a config change and
should never be required for the flow to be testable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class Message:
    to: str
    subject: str
    text: str
    # Optional HTML alternative. Plain text is always sent as well: some
    # clients block HTML, and a verification link that only exists inside an
    # HTML body is unreachable for those users.
    html: str | None = None


class EmailSender(ABC):
    @abstractmethod
    def send(self, message: Message) -> None:
        """Deliver a message, or raise."""


class NullSender(EmailSender):
    """Discards everything. Used in tests so no test can accidentally send."""

    def __init__(self) -> None:
        self.sent: list[Message] = []

    def send(self, message: Message) -> None:
        self.sent.append(message)
