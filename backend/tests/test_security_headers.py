"""
The Content-Security-Policy, and the third-party hosts it is allowed to name.

WHY THIS FILE EXISTS. The CSP is the one place in the codebase where a privacy
leak can be reintroduced by ADDING a word rather than by breaking something.
Nothing fails, no test goes red, no page looks different -- a host appears in a
header and from then on every visitor's IP is handed to it before the first
paint. That is exactly how Cairo used to load: fonts.googleapis.com served the
stylesheet, fonts.gstatic.com served the files, both were named here, and the
cost was invisible from inside the application.

Cairo is self-hosted now (frontend/public/fonts, declared in src/index.css), so
both hosts are gone. The tests below keep them gone, and catch the NEXT one
too: `test_no_unexpected_third_party_hosts` pins the entire set of external
origins the policy permits, so a newly added CDN, font host or analytics
beacon has to be justified by editing an assertion here rather than slipping
in unnoticed.
"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware import security_headers
from app.middleware.security_headers import SecurityHeadersMiddleware

ENVIRONMENTS = ["development", "production"]


@pytest.fixture
def headers(monkeypatch):
    """Return a callable giving the response headers for a given environment.

    The middleware reads `settings` once at import time and closes over it, so
    the environment is swapped by replacing that module-level object rather
    than by rebuilding the app. monkeypatch restores the real settings after
    each test, which matters because every other test in the suite shares it.
    """

    def fetch(environment):
        monkeypatch.setattr(
            security_headers,
            "settings",
            SimpleNamespace(environment=environment),
        )

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/ping")
        async def ping():
            return {"ok": True}

        return TestClient(app).get("/ping").headers

    return fetch


@pytest.fixture
def csp(headers):
    """The CSP for an environment, as (raw header, {directive: [values]})."""

    def parse(environment):
        header = headers(environment)["content-security-policy"]

        directives = {}
        for part in header.split(";"):
            part = part.strip()
            if not part:
                continue
            name, _, values = part.partition(" ")
            directives[name] = values.split()
        return header, directives

    return parse


class TestTheFontsAreNoLongerThirdParty:
    """
    The regression these guard is a PRIVACY leak, not a rendering one.
    Asserting the two hostnames are absent is the literal check; asserting
    style-src and font-src are back to 'self' is the check that actually keeps
    it true, because a page can only pull a remote font if some directive
    permits the origin.
    """

    @pytest.mark.parametrize("environment", ENVIRONMENTS)
    def test_google_font_hosts_appear_nowhere_in_the_policy(self, environment, csp):
        header, _ = csp(environment)
        assert "fonts.googleapis.com" not in header
        assert "fonts.gstatic.com" not in header

    @pytest.mark.parametrize("environment", ENVIRONMENTS)
    def test_fonts_may_only_come_from_our_own_origin(self, environment, csp):
        _, directives = csp(environment)
        assert directives["font-src"] == ["'self'"]

    @pytest.mark.parametrize("environment", ENVIRONMENTS)
    def test_no_remote_stylesheet_origin_is_permitted(self, environment, csp):
        """
        A remote font sneaks back through style-src as easily as through
        font-src: one @import in a permitted stylesheet is enough. Development
        allows jsdelivr for the API docs bundle and nothing else; production
        allows no remote stylesheet host at all.
        """
        _, directives = csp(environment)
        remote = [v for v in directives["style-src"] if "://" in v]
        expected = ["https://cdn.jsdelivr.net"] if environment == "development" else []
        assert remote == expected

    @pytest.mark.parametrize("environment", ENVIRONMENTS)
    def test_no_unexpected_third_party_hosts(self, environment, csp):
        """
        THE BROAD GUARD, and the reason this file is worth more than a string
        comparison. Every external origin the policy permits, across all
        directives, collected in one set. A new font CDN, tag manager or
        analytics beacon cannot reach the middleware without turning this
        red and forcing a deliberate decision.

        Matching on "://" rather than on "http" is what keeps img-src's bare
        `https:` out of the set: that is a SCHEME, not an origin, and it is
        deliberate -- product photos are hotlinked from arbitrary merchant
        domains, which is why they also carry referrerPolicy="no-referrer".
        """
        _, directives = csp(environment)
        hosts = {
            value
            for values in directives.values()
            for value in values
            if "://" in value
        }
        expected = (
            {"https://cdn.jsdelivr.net"} if environment == "development" else set()
        )
        assert hosts == expected


class TestTighteningTheFontsMovedNothingElse:
    @pytest.mark.parametrize("environment", ENVIRONMENTS)
    def test_the_lockdown_directives_hold(self, environment, csp):
        _, directives = csp(environment)
        assert directives["default-src"] == ["'self'"]
        assert directives["connect-src"] == ["'self'"]
        assert directives["frame-ancestors"] == ["'none'"]
        assert directives["form-action"] == ["'self'"]
        assert directives["base-uri"] == ["'self'"]

    @pytest.mark.parametrize("environment", ENVIRONMENTS)
    def test_hotlinked_product_images_still_load(self, environment, csp):
        _, directives = csp(environment)
        assert directives["img-src"] == ["'self'", "data:", "https:"]

    def test_production_allows_no_inline_script(self, csp):
        """
        'unsafe-inline' on script-src is what makes a CSP decorative. It is
        permitted in development only because the Swagger UI bundle needs it.
        """
        _, directives = csp("production")
        assert directives["script-src"] == ["'self'"]


class TestTheOtherSecurityHeaders:
    @pytest.mark.parametrize("environment", ENVIRONMENTS)
    def test_they_are_present_in_every_environment(self, environment, headers):
        sent = headers(environment)
        assert sent["X-Frame-Options"] == "DENY"
        assert sent["X-Content-Type-Options"] == "nosniff"
        assert sent["Referrer-Policy"] == "strict-origin-when-cross-origin"

    @pytest.mark.parametrize("environment", ENVIRONMENTS)
    def test_hsts_is_production_only(self, environment, headers):
        """
        HSTS on a development machine pins localhost to https in the browser's
        own cache, and it keeps doing so long after the header stops being
        sent -- an unpleasant thing to debug on a laptop.
        """
        sent = headers(environment)
        assert ("strict-transport-security" in sent) is (environment == "production")
