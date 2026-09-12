"""
Serving the built app from the API's own origin.

WHY THE SAME ORIGIN: the refresh token is an httpOnly cookie. Split the app
and the API across registrable domains and that cookie is third-party, which
Safari blocks by default -- every iPhone user silently logged out on each page
refresh, invisible to the test suite and to a Chrome session.

The interesting tests are the boundaries. A catch-all route that returns
index.html is one mistake away from swallowing the entire API, and one mistake
away from serving /etc/passwd.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.frontend import API_PREFIXES, mount_frontend


@pytest.fixture
def built_site(tmp_path, monkeypatch):
    """A minimal dist/, laid out the way Vite actually builds one."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><div id=root></div>")
    (dist / "assets" / "index-ABC123.js").write_text("console.log(1)")
    (dist / "fonts").mkdir()
    (dist / "fonts" / "cairo-arabic.woff2").write_bytes(b"wOF2fake")
    (dist / "favicon.svg").write_text("<svg/>")

    # A file OUTSIDE dist, for the traversal test to try to reach.
    (tmp_path / "secret.txt").write_text("do not serve me")

    monkeypatch.setattr("app.frontend.DIST", dist.resolve())

    app = FastAPI()

    @app.get("/products/search")
    async def search():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    assert mount_frontend(app) is True
    return TestClient(app)


class TestServing:
    def test_the_root_serves_the_app_shell(self, built_site):
        response = built_site.get("/")
        assert response.status_code == 200
        assert "<div id=root>" in response.text

    def test_a_client_route_falls_back_to_the_shell(self, built_site):
        """
        /browse/phones is a React Router path, not a file. A hard refresh on
        it has to reach index.html or the app 404s on its own URLs.
        """
        response = built_site.get("/browse/phones")
        assert response.status_code == 200
        assert "<div id=root>" in response.text

    def test_a_real_file_is_served_as_itself(self, built_site):
        assert built_site.get("/favicon.svg").text == "<svg/>"

    def test_hashed_assets_are_cached_forever(self, built_site):
        """
        Safe ONLY because Vite content-hashes these names: the filename
        changes whenever the bytes do, so a year-long cache cannot go stale.
        """
        response = built_site.get("/assets/index-ABC123.js")
        assert response.status_code == 200
        assert "immutable" in response.headers["cache-control"]
        assert "max-age=31536000" in response.headers["cache-control"]

    def test_fonts_are_cached_but_not_immutable(self, built_site):
        """
        Font filenames are hand-written, so they do NOT change when the bytes
        do. A long max-age keeps repeat visits off the network; `immutable`
        would pin every visitor to the first subset they ever loaded, with no
        way to push a correction.
        """
        response = built_site.get("/fonts/cairo-arabic.woff2")
        assert response.status_code == 200
        cache_control = response.headers["cache-control"]
        assert "max-age=604800" in cache_control
        assert "immutable" not in cache_control

    def test_a_cached_font_revalidates_to_304(self, built_site):
        """The bound on staleness is only real if the conditional GET works."""
        etag = built_site.get("/fonts/cairo-arabic.woff2").headers["etag"]
        again = built_site.get(
            "/fonts/cairo-arabic.woff2", headers={"If-None-Match": etag}
        )
        assert again.status_code == 304

    def test_the_shell_itself_must_revalidate(self, built_site):
        """
        index.html is the one file whose name never changes. Cached, a visitor
        is pinned to the build they first loaded -- pointing at asset
        filenames that no longer exist.
        """
        assert built_site.get("/").headers["cache-control"] == "no-cache"


class TestItDoesNotSwallowTheApi:
    def test_a_real_endpoint_still_answers(self, built_site):
        """The catch-all is registered last; it must not shadow the routers."""
        assert built_site.get("/products/search").json() == {"ok": True}

    def test_health_still_answers(self, built_site):
        assert built_site.get("/health").json() == {"status": "ok"}

    def test_an_unknown_api_path_404s_as_json_not_as_html(self, built_site):
        """
        THE MISTAKE THIS GUARDS. A missing endpoint under an API prefix must
        answer like an API, or an axios call receives a page of HTML and fails
        somewhere far away as an unparseable response.
        """
        response = built_site.get("/products/does-not-exist")
        assert response.status_code == 404
        assert "<div id=root>" not in response.text

    @pytest.mark.parametrize("prefix", API_PREFIXES)
    def test_every_api_prefix_is_excluded_from_the_fallback(self, built_site, prefix):
        response = built_site.get(f"{prefix}/definitely-not-a-route")
        assert response.status_code == 404, f"{prefix} fell through to the shell"
        assert "<div id=root>" not in response.text


class TestTraversal:
    @pytest.mark.parametrize(
        "path",
        [
            "/../secret.txt",
            "/assets/../../secret.txt",
            "/%2e%2e/secret.txt",
            "/....//secret.txt",
        ],
    )
    def test_it_cannot_be_walked_out_of_dist(self, built_site, path):
        """
        `full_path` is attacker-controlled. resolve() collapses the traversal,
        and only comparing the RESULT against dist catches it -- checking the
        raw string for ".." does not, because there are many spellings.
        """
        response = built_site.get(path)
        assert "do not serve me" not in response.text


class TestWithoutABuild:
    def test_nothing_is_mounted_and_the_api_is_untouched(self, tmp_path, monkeypatch):
        """
        Development runs Vite on :5173 and never builds. The backend must
        behave exactly as it does today when no dist exists.
        """
        monkeypatch.setattr("app.frontend.DIST", (tmp_path / "nothing").resolve())

        app = FastAPI()

        @app.get("/health")
        async def health():
            return {"status": "ok"}

        assert mount_frontend(app) is False

        client = TestClient(app)
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/browse/phones").status_code == 404
