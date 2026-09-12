"""
Serving the built React app from the API's own origin.

WHY THE SAME ORIGIN, and why this is not just a convenience: the refresh token
lives in an httpOnly cookie. Put the app on `ahsanse3r.com` and the API on
`api.ahsanse3r.com` and that cookie becomes THIRD-PARTY, which Safari blocks by
default -- so every iPhone user is silently logged out on each page refresh,
and nothing in the test suite or a Chrome session would ever show it. One
origin removes the whole class of problem, and takes CORS with it.

It is also the cheapest shape: one process, one certificate, one thing to
deploy, rather than a second static host and a second DNS name.

DEV IS UNAFFECTED. Vite serves the app on :5173 during development and this
module does nothing at all unless a built `dist/` is actually present, so the
backend keeps behaving exactly as it does today when run from a checkout.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

# backend/app/frontend.py -> backend/ -> repo root -> frontend/dist
DIST = (Path(__file__).resolve().parent.parent.parent / "frontend" / "dist").resolve()

# Everything the API owns. A request under one of these prefixes that matched
# no route is a MISSING ENDPOINT and must answer with the JSON 404 an API
# client expects -- not with index.html, which would hand an axios call a page
# of HTML and surface as an unparseable-response error somewhere far away.
API_PREFIXES = (
    "/auth",
    "/products",
    "/prices",
    "/support",
    "/merchant",
    "/admin",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
)


class ImmutableStatic(StaticFiles):
    """
    Static files that may be cached forever.

    Only mounted at /assets, and only safe there because Vite CONTENT-HASHES
    those filenames: index-B_j_Vvhc.js changes its name whenever its bytes
    change, so a year-long cache can never serve a stale build. index.html is
    deliberately NOT served through this -- it is the one file whose name
    stays put, so it must revalidate or a visitor is pinned to the deploy they
    first saw.
    """

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


class RevalidatedStatic(StaticFiles):
    """
    Static files cached for a week, then revalidated.

    Mounted at /fonts, whose filenames are HAND-WRITTEN (cairo-arabic.woff2)
    and referenced by that name from index.css. Unlike /assets, the name does
    NOT change when the bytes do, so `immutable` would be the index.html bug
    with a longer fuse: re-subset a font under the same name and every visitor
    who ever loaded it keeps the old glyphs for a year, with no way to push a
    correction. Content-hashing these names instead would mean importing the
    fonts through the bundler, which breaks the `<link rel=preload>` in
    index.html that keeps Arabic text from flashing unstyled.

    A week of max-age means a repeat visitor spends no request on 81 KB of
    fonts, and the conditional GET afterwards is a 304 against the ETag
    StaticFiles already sends -- cheap, and it bounds staleness at seven days.
    """

    FONT_MAX_AGE = 604800  # one week

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = f"public, max-age={self.FONT_MAX_AGE}"
        return response


def mount_frontend(app: FastAPI) -> bool:
    """
    Serve `frontend/dist` from this app. Returns whether anything was mounted.

    MUST BE CALLED AFTER EVERY ROUTER. The catch-all below matches any path,
    so registering it earlier would shadow the entire API.
    """
    index = DIST / "index.html"
    if not index.is_file():
        logger.info(
            "No frontend build found; serving the API only",
            extra={"action": "frontend_not_mounted", "target": str(DIST)},
        )
        return False

    app.mount("/assets", ImmutableStatic(directory=DIST / "assets"), name="assets")

    # Without its own mount, /fonts/*.woff2 falls through to the SPA catch-all
    # below, which serves the bytes with no Cache-Control at all -- so every
    # cold navigation re-fetches 81 KB of self-hosted Cairo that used to be
    # cached for a year when it came from Google.
    fonts = DIST / "fonts"
    if fonts.is_dir():
        app.mount("/fonts", RevalidatedStatic(directory=fonts), name="fonts")

    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def spa(full_path: str):
        """
        A real file if there is one, otherwise the app shell.

        The fallback is what makes client-side routing work: /browse/phones is
        a React Router path, not a file, and a hard refresh on it has to reach
        index.html rather than a 404.
        """
        path = "/" + full_path
        if any(path == p or path.startswith(p + "/") for p in API_PREFIXES):
            raise HTTPException(status_code=404, detail="Not found")

        if full_path:
            candidate = (DIST / full_path).resolve()
            # `full_path` is attacker-controlled, so the resolved path is
            # checked to be INSIDE dist. Without this, "../../etc/passwd"
            # walks straight out of the directory -- resolve() collapses the
            # traversal, and only comparing afterwards catches it.
            inside = candidate == DIST or DIST in candidate.parents
            if inside and candidate.is_file():
                return FileResponse(candidate)

        return FileResponse(
            index,
            # The one file whose name never changes. Without no-cache a
            # visitor keeps whichever build they first loaded, forever,
            # pointing at asset filenames that no longer exist.
            headers={"Cache-Control": "no-cache"},
        )

    logger.info(
        "Serving the frontend from the API origin",
        extra={"action": "frontend_mounted", "target": str(DIST)},
    )
    return True
