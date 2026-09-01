"""
A wrong production configuration must refuse to boot, not fail silently.

THE CLASS OF BUG THIS CLOSES. Every setting checked here defaults to
something correct for a laptop and wrong for the internet, and each one used
to fail INVISIBLY:

    TRUSTED_HOSTS=*          serves traffic, accepts any Host header
    APP_BASE_URL=localhost   emails links nobody can open; signups never
                             complete and nothing reports an error
    ALLOWED_ORIGINS=localhost  the browser blocks the frontend entirely
    placeholder JWT secret   anyone with the repo can mint an admin token

None of those trip a health check, which is exactly why they are dangerous.
The mail backend proved the remedy -- turn the silent misconfiguration into a
refusal to start, so the machine never reports healthy and the platform rolls
the deploy back.
"""

from app.config import Settings

BASE = {
    "database_url": "postgresql://user:pw@db/app",
    "jwt_secret_key": "a" * 40,
}

GOOD = {
    **BASE,
    "environment": "production",
    "trusted_hosts": "api.example.com,example.com",
    "allowed_origins": "https://example.com",
    "app_base_url": "https://example.com",
    "email_backend": "smtp",
    "support_email": "you@example.com",
    "trusted_proxy_count": 1,
}


def errors_for(**overrides):
    return Settings(**{**GOOD, **overrides}).production_problems()[0]


def warnings_for(**overrides):
    return Settings(**{**GOOD, **overrides}).production_problems()[1]


class TestACorrectConfigurationIsAccepted:
    def test_no_errors(self):
        assert errors_for() == []

    def test_no_warnings(self):
        assert warnings_for() == []


class TestDevelopmentIsNeverChecked:
    def test_the_laptop_defaults_are_fine_in_development(self):
        """
        The checks must not fire outside production, or nobody could run the
        app locally at all.
        """
        settings = Settings(**BASE, environment="development")
        assert settings.production_problems() == ([], [])


class TestTheDangerousDefaultsAreRefused:
    def test_wildcard_trusted_hosts(self):
        assert any("TRUSTED_HOSTS" in e for e in errors_for(trusted_hosts="*"))

    def test_localhost_app_base_url(self):
        """Verification links would point at a machine nobody else can reach."""
        assert any("APP_BASE_URL" in e
                   for e in errors_for(app_base_url="http://localhost:5173"))

    def test_localhost_cors_origins(self):
        assert any("ALLOWED_ORIGINS" in e
                   for e in errors_for(allowed_origins="http://localhost:5173"))

    def test_empty_cors_origins(self):
        assert any("ALLOWED_ORIGINS" in e for e in errors_for(allowed_origins=""))

    def test_the_placeholder_secret_from_the_example_file(self):
        assert any("JWT_SECRET_KEY" in e for e in errors_for(
            jwt_secret_key="change_this_to_a_random_32_char_hex_string"))

    def test_samesite_none_without_a_secure_cookie(self):
        """Browsers reject the combination, so sessions would simply not work."""
        assert any("COOKIE_SAMESITE" in e for e in errors_for(
            cookie_samesite="none", cookie_secure_override=False))

    def test_every_problem_is_reported_at_once(self):
        """
        One error per boot would mean four deploys to find four mistakes.
        """
        found = errors_for(
            trusted_hosts="*",
            app_base_url="http://localhost:5173",
            allowed_origins="http://localhost:5173",
            jwt_secret_key="change_this_to_a_random_32_char_hex_string",
        )
        assert len(found) == 4, found


class TestTheSuspiciousOnesOnlyWarn:
    """
    The split is whether a correct deployment could legitimately look like
    this. Nobody deliberately runs a public site with TRUSTED_HOSTS=*; plenty
    of people legitimately run one with nothing in front of it.
    """

    def test_no_proxy_count_is_a_warning_not_an_error(self):
        assert errors_for(trusted_proxy_count=0) == []
        assert any("TRUSTED_PROXY_COUNT" in w
                   for w in warnings_for(trusted_proxy_count=0))

    def test_missing_support_email_is_a_warning(self):
        assert errors_for(support_email=None) == []
        assert any("SUPPORT_EMAIL" in w for w in warnings_for(support_email=None))

    def test_null_mail_is_a_warning(self):
        """Choosing to send nothing is allowed; drifting into it is not."""
        assert errors_for(email_backend="null") == []
        assert any("EMAIL_BACKEND" in w for w in warnings_for(email_backend="null"))


class TestTheCheckActuallyRuns:
    def test_startup_calls_it(self):
        """
        Without this the validator exists and never runs -- the same lazy-call
        mistake the mail backend had.
        """
        import inspect

        import app.main as main

        source = inspect.getsource(main.lifespan)
        assert "production_problems" in source
        assert "raise RuntimeError" in source


class TestTheProxyDetectorIsWiredIn:
    def test_the_rate_limiter_watches_for_a_forwarded_header(self):
        """
        A static check cannot know whether a proxy is present. This one can:
        an X-Forwarded-For arriving while the count is 0 proves it.
        """
        import inspect

        from app.security import rate_limiter

        source = inspect.getsource(rate_limiter.client_ip)
        assert "x-forwarded-for" in source.lower()
        assert "proxy_misconfigured" in source
