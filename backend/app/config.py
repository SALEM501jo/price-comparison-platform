"""
Application settings.
Loaded once from the environment / .env and cached for the process lifetime.
"""

import json
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolved from this file, not the working directory. A bare ".env" is looked
# up relative to CWD, so the app booted from backend/ but failed to find its
# settings from the repo root -- which made `pytest backend/tests/` blow up on
# a missing database_url while `cd backend && pytest tests/` passed.
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    redis_url: str = "redis://localhost:6379/0"

    # Default limit for public endpoints
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60
    # Stricter limit for auth endpoints (login/register/refresh)
    strict_rate_limit_requests: int = 5
    strict_rate_limit_window_seconds: int = 60

    environment: str = "development"
    trusted_hosts: str = "*"

    # How many reverse proxies sit in front of the app. 0 means none, and
    # X-Forwarded-For is ignored entirely.
    #
    # WHY A COUNT AND NOT A BOOLEAN: the header is a client-supplied list that
    # each proxy APPENDS to. Trusting the leftmost entry lets any caller forge
    # their address -- "X-Forwarded-For: 1.2.3.4" and the rate limiter counts a
    # different bucket on every request, which removes the control entirely.
    # Only the last N entries were written by infrastructure we control, so the
    # real client is the (N+1)th from the right.
    trusted_proxy_count: int = 0

    # --- Email ---
    # "console" writes messages to the log and sends nothing, which is what
    # lets verification work with no account, no domain and no DNS records.
    # get_sender() refuses this in production rather than silently pretending
    # to send.
    email_backend: str = "console"
    email_from: str = "PriceCompare <noreply@localhost>"
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False

    # Where the links in emails point. The API cannot infer this: it is the
    # FRONTEND's address, and a link built from the request Host header would
    # be forgeable into a phishing link by anyone who can set that header.
    app_base_url: str = "http://localhost:5173"

    # How long a verification link stays valid.
    email_token_ttl_hours: int = 24

    # Where contact-form messages are forwarded. Optional: with no address
    # set, messages are still STORED and readable in the admin panel -- the
    # notification is the part that is missing, not the message.
    support_email: str | None = None

    # --- Refresh token cookie ---
    # The refresh token travels in an httpOnly cookie so that JavaScript --
    # and therefore any XSS payload -- cannot read it.
    refresh_cookie_name: str = "refresh_token"
    # "lax" is enough while the API and the app share a site (localhost:5173
    # and localhost:8000 are the same site; SameSite ignores the port). Split
    # them across real domains and this must become "none", which browsers
    # only honour on a Secure cookie.
    cookie_samesite: str = "lax"
    # Secure is forced on in production regardless; see cookie_is_secure.
    cookie_secure_override: bool | None = None

    # Kept as a plain string on purpose. pydantic-settings JSON-decodes any
    # complex field type (list/dict) straight from the env var, which made
    # the documented comma-separated form in .env.example crash on startup.
    # Parsing ourselves accepts BOTH forms. See cors_origins below.
    allowed_origins: str = "http://localhost:5173"

    @field_validator("jwt_secret_key")
    @classmethod
    def _secret_must_be_strong(cls, v: str) -> str:
        # A short secret makes HS256 signatures brute-forceable offline.
        if len(v) < 32:
            raise ValueError(
                "JWT_SECRET_KEY must be at least 32 characters. "
                "Generate one with: openssl rand -hex 32"
            )
        return v

    @staticmethod
    def _split_list(raw: str) -> list[str]:
        raw = (raw or "").strip()
        if not raw:
            return []
        if raw.startswith("["):
            return [str(x).strip() for x in json.loads(raw)]
        return [part.strip() for part in raw.split(",") if part.strip()]

    @property
    def cors_origins(self) -> list[str]:
        """CORS allow-list. Accepts JSON (["a","b"]) or comma-separated (a,b)."""
        return self._split_list(self.allowed_origins)

    @property
    def trusted_host_list(self) -> list[str]:
        return self._split_list(self.trusted_hosts) or ["*"]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    # Values that ship in .env.example. Live in production they mean somebody
    # copied the template and deployed it.
    _PLACEHOLDER_SECRETS = frozenset({
        "change_this_to_a_random_32_char_hex_string",
        "your_secret_key_here",
        "changeme",
    })

    @staticmethod
    def _is_local(url: str) -> bool:
        return any(host in (url or "").lower()
                   for host in ("localhost", "127.0.0.1", "0.0.0.0", "::1"))

    def production_problems(self) -> tuple[list[str], list[str]]:
        """
        What is wrong with this configuration for a public deployment.

        Returns (errors, warnings). Errors refuse the boot; warnings are
        logged and the app starts.

        WHY THIS EXISTS. Every setting below defaults to something correct for
        a laptop and wrong for the internet, and -- apart from the mail backend
        -- each one fails SILENTLY. A deploy that forgets TRUSTED_HOSTS serves
        traffic happily while accepting any Host header. One that forgets
        APP_BASE_URL sends verification links pointing at localhost, so every
        new account is unverifiable and the only symptom is users not
        completing signup. Nothing in a health check notices either.

        The mail backend already proved the fix: turn the silent
        misconfiguration into a refusal to start, so the machine never reports
        healthy and the deploy platform rolls back. This applies the same rule
        to the rest of them.

        THE SPLIT BETWEEN ERROR AND WARNING is whether a correct deployment
        could legitimately look like this. Nobody deliberately runs a public
        site with TRUSTED_HOSTS=*; somebody might legitimately run one with no
        reverse proxy in front, so the proxy count is a warning rather than a
        refusal -- and the rate limiter detects that case at runtime instead,
        where it can see an actual X-Forwarded-For header.
        """
        errors: list[str] = []
        warnings: list[str] = []

        if not self.is_production:
            return errors, warnings

        if "*" in self.trusted_host_list:
            errors.append(
                "TRUSTED_HOSTS is '*'. Set it to your real hostnames "
                "(api.example.com,example.com) or the app accepts any Host "
                "header, which is cache-poisoning and password-reset "
                "phishing waiting to happen."
            )

        if self._is_local(self.app_base_url):
            errors.append(
                f"APP_BASE_URL is {self.app_base_url!r}. Every verification "
                "and password-reset link would point at localhost, so no new "
                "account could ever be confirmed. Set it to the FRONTEND's "
                "public address."
            )

        origins = self.cors_origins
        if not origins:
            errors.append(
                "ALLOWED_ORIGINS is empty, so the browser will refuse every "
                "request the frontend makes to this API."
            )
        elif all(self._is_local(o) for o in origins):
            errors.append(
                f"ALLOWED_ORIGINS is still {origins}. The deployed frontend "
                "is not on localhost, so CORS would block it entirely."
            )

        if self.jwt_secret_key in self._PLACEHOLDER_SECRETS:
            errors.append(
                "JWT_SECRET_KEY is the value from .env.example. Anyone with "
                "the repository can mint an admin token. Generate one with: "
                "openssl rand -hex 32"
            )

        if self.trusted_proxy_count <= 0:
            warnings.append(
                "TRUSTED_PROXY_COUNT is 0. If anything sits in front of this "
                "app (a load balancer, Fly's edge, Cloudflare), every visitor "
                "shares ONE rate-limit bucket and the 101st request in any "
                "minute returns 429 to everybody. Set it to the number of "
                "proxies. If the app really is exposed directly, 0 is right."
            )

        if not self.support_email:
            warnings.append(
                "SUPPORT_EMAIL is unset. Contact-form messages are still "
                "stored and readable in /admin, but nobody is notified."
            )

        if (self.email_backend or "").lower() == "null":
            warnings.append(
                "EMAIL_BACKEND=null. No verification or password-reset mail "
                "will be sent to anyone. Deliberate, but worth knowing."
            )

        if self.cookie_samesite.lower() == "none" and not self.cookie_is_secure:
            errors.append(
                "COOKIE_SAMESITE=none requires a Secure cookie; browsers "
                "reject the combination outright and sessions would not work."
            )

        return errors, warnings

    @property
    def cookie_is_secure(self) -> bool:
        """
        Whether the refresh cookie is marked Secure (HTTPS only).

        Always on in production -- a refresh token sent over plain HTTP is
        readable by anyone on the path, which defeats the point of hiding it
        from JavaScript. Off by default in development so the cookie works
        over http://localhost, and overridable for an HTTPS dev setup.
        """
        if self.cookie_secure_override is not None:
            return self.cookie_secure_override
        return self.is_production


@lru_cache()
def get_settings() -> Settings:
    return Settings()
