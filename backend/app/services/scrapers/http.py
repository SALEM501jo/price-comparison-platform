"""
SSRF-hardened HTTP client for scraping.

THE RISK (OWASP A10):
A scraper fetches URLs. The moment any part of a URL comes from data rather
than from code -- a store's product feed, a link in a page, an admin-supplied
config row -- the fetcher becomes a way to make the SERVER issue requests. An
attacker who can steer it points it at http://169.254.169.254/ (cloud instance
metadata, often containing credentials), at http://localhost:6379 (this app's
own Redis), or at any host inside the private network the app is deployed in.
The response comes back through the scraper, so it is also an exfiltration
path, not only a probe.

Five controls, all of which have to hold:

  1. Scheme allowlist -- https only. file://, gopher://, ftp:// and friends are
     rejected outright.
  2. Host allowlist -- only the domains we deliberately configured. This is the
     strongest control by far; the rest exist for when it is loosened.
  3. DNS resolution BEFORE connecting, with every resolved address checked
     against private, loopback, link-local, and reserved ranges. A hostname on
     the allowlist that resolves to 127.0.0.1 is still refused.
  4. No redirect following. A redirect is a fresh URL chosen by the remote
     server -- exactly the input we are trying not to trust. Each hop is
     re-validated explicitly instead.
  5. Bounded time and size, so a slow or enormous response cannot exhaust the
     worker.

WHAT THIS DOES NOT SOLVE: DNS rebinding, where a name resolves to a safe
address for the check and a private one for the connection. Closing that needs
the connection pinned to the validated IP. The host allowlist is what makes the
gap acceptable here.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("app.scraper")

ALLOWED_SCHEMES = {"https"}
MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB
DEFAULT_TIMEOUT = 15.0
MAX_REDIRECTS = 3

# Identify ourselves honestly. A scraper that pretends to be a browser is
# both rude and a reason for a site to block the whole IP range.
USER_AGENT = (
    "PriceCompareBot/0.1 (+https://ahsanse3r.com; "
    "Ahsan Se3r price comparison)"
)


class BlockedURLError(Exception):
    """The URL failed a safety check and was not fetched."""


@dataclass(frozen=True)
class FetchResult:
    url: str
    status_code: int
    text: str
    content_type: str


def _is_public_address(ip: str) -> bool:
    """
    True only for addresses that are safe to connect to from a server.

    Rejects loopback (127/8, ::1), private ranges (10/8, 172.16/12, 192.168/16,
    fc00::/7), link-local (169.254/16 -- cloud metadata lives at 169.254.169.254),
    plus multicast, reserved and unspecified.
    """
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False

    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def validate_url(url: str, allowed_hosts: set[str]) -> str:
    """
    Check a URL is safe to fetch, or raise BlockedURLError.

    Returns the normalised hostname on success.
    """
    parsed = urlparse(url)

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise BlockedURLError(f"scheme {parsed.scheme!r} is not allowed")

    host = (parsed.hostname or "").lower()
    if not host:
        raise BlockedURLError("URL has no host")

    if host not in allowed_hosts:
        # The primary control. Everything below is defence in depth for the
        # case where this list is widened.
        raise BlockedURLError(f"host {host!r} is not in the allow-list")

    try:
        resolved = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise BlockedURLError(f"could not resolve {host!r}: {exc}") from exc

    addresses = {info[4][0] for info in resolved}
    if not addresses:
        raise BlockedURLError(f"{host!r} resolved to nothing")

    # EVERY address must be public. One private answer is enough to refuse:
    # otherwise a host with both a public and an internal record slips through.
    for address in addresses:
        if not _is_public_address(address):
            raise BlockedURLError(
                f"{host!r} resolves to non-public address {address}"
            )

    return host


def fetch(
    url: str,
    allowed_hosts: set[str],
    *,
    params: dict | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> FetchResult:
    """
    Fetch a URL with every SSRF control applied.

    Redirects are followed manually so each hop is validated; httpx is told not
    to follow them itself.
    """
    seen: list[str] = []
    current = url

    for _ in range(MAX_REDIRECTS + 1):
        validate_url(current, allowed_hosts)
        seen.append(current)

        with httpx.Client(
            timeout=timeout,
            follow_redirects=False,  # each hop is re-validated above
            headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"},
        ) as client:
            with client.stream("GET", current, params=params) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise BlockedURLError("redirect without a Location header")
                    current = str(httpx.URL(current).join(location))
                    params = None  # the new URL carries its own query
                    continue

                # Read with a cap rather than trusting Content-Length, which a
                # server can understate.
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > MAX_RESPONSE_BYTES:
                        raise BlockedURLError(
                            f"response exceeded {MAX_RESPONSE_BYTES} bytes"
                        )
                    chunks.append(chunk)

                body = b"".join(chunks)
                return FetchResult(
                    url=str(response.url),
                    status_code=response.status_code,
                    text=body.decode(response.encoding or "utf-8", errors="replace"),
                    content_type=response.headers.get("content-type", ""),
                )

    raise BlockedURLError(f"too many redirects: {' -> '.join(seen)}")
