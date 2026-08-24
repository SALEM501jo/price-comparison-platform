"""
robots.txt compliance.

Not a security control -- robots.txt is a request, not an enforcement
mechanism, and nothing stops a client ignoring it. It is here because a
project that scrapes commercial sites should be able to say it asked. It is
also self-interested: sites block scrapers that ignore it, and a block lands on
the whole IP range.

Deliberately NOT using urllib.robotparser: it fetches the URL itself, which
would bypass every SSRF control in http.py. Rules are fetched through the
hardened client and parsed here.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

from app.services.scrapers.http import USER_AGENT, BlockedURLError, fetch

logger = logging.getLogger("app.scraper")

CACHE_TTL_SECONDS = 3600


@dataclass
class RobotRules:
    """Parsed directives for the group that applies to us."""

    allow: list[str] = field(default_factory=list)
    disallow: list[str] = field(default_factory=list)
    crawl_delay: float | None = None
    fetched_at: float = 0.0

    def is_allowed(self, path: str) -> bool:
        """
        Longest-match wins, and Allow beats Disallow at equal length -- the
        behaviour Google documents and most sites are written against.
        """
        best_allow = max(
            (len(rule) for rule in self.allow if _matches(path, rule)), default=-1
        )
        best_disallow = max(
            (len(rule) for rule in self.disallow if _matches(path, rule)), default=-1
        )
        if best_disallow < 0:
            return True
        return best_allow >= best_disallow


def _matches(path: str, rule: str) -> bool:
    """Path matching with Shopify-style `*` wildcards and `$` anchors."""
    if not rule:
        return False

    anchored = rule.endswith("$")
    if anchored:
        rule = rule[:-1]

    if "*" not in rule:
        return path == rule if anchored else path.startswith(rule)

    parts = rule.split("*")
    if not path.startswith(parts[0]):
        return False

    cursor = len(parts[0])
    for part in parts[1:]:
        if not part:
            continue
        found = path.find(part, cursor)
        if found == -1:
            return False
        cursor = found + len(part)

    return path.endswith(parts[-1]) if anchored else True


def parse_robots(text: str, user_agent: str = USER_AGENT) -> RobotRules:
    """
    Parse robots.txt, preferring a group naming us over the `*` group.

    NOTE: everything in this file is untrusted remote text. It is read only for
    Allow/Disallow/Crawl-delay directives; any other content -- including prose
    addressed to automated clients, which real store robots.txt files do
    contain -- is ignored rather than acted on.
    """
    groups: dict[str, RobotRules] = {}
    current_agents: list[str] = []
    last_line_was_agent = False

    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue

        field_name, _, value = line.partition(":")
        field_name = field_name.strip().lower()
        value = value.strip()

        if field_name == "user-agent":
            if not last_line_was_agent:
                current_agents = []
            current_agents.append(value.lower())
            groups.setdefault(value.lower(), RobotRules())
            last_line_was_agent = True
            continue

        last_line_was_agent = False
        if not current_agents:
            continue

        for agent in current_agents:
            rules = groups.setdefault(agent, RobotRules())
            if field_name == "disallow" and value:
                rules.disallow.append(value)
            elif field_name == "allow" and value:
                rules.allow.append(value)
            elif field_name == "crawl-delay":
                try:
                    rules.crawl_delay = float(value)
                except ValueError:
                    pass

    ua = user_agent.lower()
    for agent, rules in groups.items():
        if agent and agent != "*" and agent in ua:
            return rules
    return groups.get("*", RobotRules())


_cache: dict[str, RobotRules] = {}


def rules_for(base_url: str, allowed_hosts: set[str]) -> RobotRules:
    """
    Fetch and cache a site's rules.

    On any failure the site is treated as fully allowed. That is the
    conventional reading -- absent rules mean no restrictions -- and failing
    closed would let one unreachable robots.txt silently stop all scraping.
    """
    host = urlparse(base_url).hostname or ""
    cached = _cache.get(host)
    if cached and time.time() - cached.fetched_at < CACHE_TTL_SECONDS:
        return cached

    try:
        result = fetch(f"https://{host}/robots.txt", allowed_hosts)
        rules = parse_robots(result.text) if result.status_code == 200 else RobotRules()
    except (BlockedURLError, Exception) as exc:  # noqa: B014
        logger.warning("Could not read robots.txt for %s: %s", host, exc)
        rules = RobotRules()

    rules.fetched_at = time.time()
    _cache[host] = rules
    return rules


def can_fetch(url: str, allowed_hosts: set[str]) -> bool:
    path = urlparse(url).path or "/"
    return rules_for(url, allowed_hosts).is_allowed(path)
