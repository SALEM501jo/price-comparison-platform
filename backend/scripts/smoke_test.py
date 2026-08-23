"""
End-to-end smoke test against a RUNNING stack.

Unlike the pytest suite (SQLite, rate limiter stubbed out), this exercises the
real thing: real Postgres, real Redis, real HTTP. It is what tells you the app
actually boots and behaves outside the test environment.

Usage:
    docker compose up -d
    python -m app.services.scraper            # seed some products
    uvicorn app.main:app --port 8000
    python scripts/smoke_test.py
"""

from __future__ import annotations

import sys
import uuid

import httpx

BASE = "http://127.0.0.1:8000"
PASSWORD = "SmokeTest123"

passed: list[str] = []
failed: list[str] = []
skipped: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    if condition:
        passed.append(name)
        print(f"  PASS  {name}")
    else:
        failed.append(name)
        print(f"  FAIL  {name}{(' -- ' + detail) if detail else ''}")
    return condition


def skip(name: str, why: str) -> None:
    skipped.append(name)
    print(f"  SKIP  {name} -- {why}")


def redis_is_up(host: str = "127.0.0.1", port: int = 6379) -> bool:
    """The rate limiter fails OPEN by design, so a missing Redis produces no
    429 at all. Distinguish that from the control being genuinely broken."""
    import socket

    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def section(title: str) -> None:
    print(f"\n{title}")


def main() -> int:
    client = httpx.Client(base_url=BASE, timeout=15.0)
    email = f"smoke-{uuid.uuid4().hex[:8]}@example.com"

    # --- Liveness ----------------------------------------------------------
    section("Liveness")
    try:
        health = client.get("/health")
    except httpx.ConnectError:
        print(f"  FAIL  cannot reach {BASE} -- is uvicorn running?")
        return 1
    check("GET /health returns 200", health.status_code == 200, health.text)
    check(
        "health reports an environment",
        bool(health.json().get("environment")),
        health.text,
    )

    # --- Security headers --------------------------------------------------
    section("Security headers")
    headers = health.headers
    check("Content-Security-Policy present", "content-security-policy" in headers)
    check("X-Frame-Options is DENY", headers.get("x-frame-options") == "DENY")
    check("X-Content-Type-Options is nosniff", headers.get("x-content-type-options") == "nosniff")
    check("Referrer-Policy present", "referrer-policy" in headers)
    check("Server header stripped", "server" not in headers)

    # --- Registration and login -------------------------------------------
    section("Auth")
    weak = client.post("/auth/register", json={"email": email, "password": "weak"})
    check("weak password rejected (422)", weak.status_code == 422, weak.text)

    registered = client.post("/auth/register", json={"email": email, "password": PASSWORD})
    if not check("register returns 201", registered.status_code == 201, registered.text):
        return report()
    tokens = registered.json()
    check("register returns both tokens",
          bool(tokens.get("access_token") and tokens.get("refresh_token")))

    duplicate = client.post("/auth/register", json={"email": email, "password": PASSWORD})
    check("duplicate registration is 409", duplicate.status_code == 409, duplicate.text)

    logged_in = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    check("login returns 200", logged_in.status_code == 200, logged_in.text)

    bad = client.post("/auth/login", json={"email": email, "password": "WrongPass123"})
    check("wrong password is 401", bad.status_code == 401, bad.text)

    auth = {"Authorization": f"Bearer {tokens['access_token']}"}
    me = client.get("/auth/me", headers=auth)
    check("GET /auth/me returns 200", me.status_code == 200, me.text)
    check("password hash never returned", "password_hash" not in me.text)

    # --- The refresh fix ---------------------------------------------------
    section("Refresh (was broken: expected a query parameter)")
    refreshed = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    check("refresh accepts a JSON body", refreshed.status_code == 200, refreshed.text)
    if refreshed.status_code == 200:
        check("refresh returns a new access token", bool(refreshed.json().get("access_token")))

    wrong_type = client.post("/auth/refresh", json={"refresh_token": tokens["access_token"]})
    check("access token rejected as refresh token", wrong_type.status_code == 401, wrong_type.text)

    # --- Tiered search (the core feature) ----------------------------------
    section("Tiered search")
    search = client.get("/products/search", params={"q": "iPhone 15 128GB Black"})
    if not check("search returns 200", search.status_code == 200, search.text):
        return report()

    body = search.json()
    interpretation = body.get("interpretation", {})
    check("search reports what it understood", interpretation.get("structured") is True,
          str(interpretation))
    check("query parsed into attributes",
          interpretation.get("attributes", {}).get("storage") == "128gb",
          str(interpretation))

    exact = body.get("exact", [])
    check("exact match found", len(exact) == 1,
          f"got {len(exact)} -- run: python -m app.services.scraper")
    if exact:
        check("exact match scores 100", exact[0]["match_score"] == 100.0)
        check("exact match has no differences", exact[0]["differences"] == [])
        check("exact match aggregates several stores", exact[0]["store_count"] >= 2,
              str(exact[0].get("store_count")))
        check("exact match names a best-deal store", bool(exact[0]["best_deal_store"]))

    # A different storage size is a DIFFERENT product, and must not be exact.
    other = client.get("/products/search", params={"q": "iPhone 15 512GB Black"})
    if other.status_code == 200:
        tiers = other.json()
        check("wrong storage is not an exact match", len(tiers.get("exact", [])) == 0)
        demoted = tiers.get("close", []) + tiers.get("similar", [])
        check("wrong storage is demoted, not dropped", len(demoted) > 0)
        if demoted:
            check("demotion is explained in words",
                  any("storage" in d for d in demoted[0]["differences"]),
                  str(demoted[0]["differences"]))

    # Junk input must not match anything.
    junk = client.get("/products/search", params={"q": "%%%%"})
    check("wildcard query returns nothing",
          junk.status_code == 200 and junk.json().get("total") == 0,
          junk.text[:200])

    product_id = exact[0]["id"] if exact else None
    if product_id:
        detail = client.get(f"/products/{product_id}")
        check("product detail returns 200", detail.status_code == 200, detail.text)
        check("product detail lists store prices", len(detail.json().get("prices", [])) > 0)

    # --- The wishlist / alerts fixes --------------------------------------
    if product_id:
        section("Wishlist and alerts (both used to 500 on every call)")
        added = client.post(f"/prices/wishlist/{product_id}", headers=auth)
        check("add to wishlist returns 201", added.status_code == 201, added.text)

        wishlist = client.get("/prices/wishlist", headers=auth)
        check("GET /prices/wishlist returns 200", wishlist.status_code == 200, wishlist.text)
        check("wishlist contains the product",
              any(i["product_id"] == product_id for i in wishlist.json())
              if wishlist.status_code == 200 else False)

        alert = client.post("/prices/alerts",
                            json={"product_id": product_id, "target_price": 500.0},
                            headers=auth)
        check("create alert returns 201", alert.status_code == 201, alert.text)

        alerts = client.get("/prices/alerts", headers=auth)
        check("GET /prices/alerts returns 200", alerts.status_code == 200, alerts.text)

    # --- Access control ----------------------------------------------------
    section("Access control")
    check("admin endpoint denies a normal user",
          client.get("/admin/users", headers=auth).status_code == 403)
    check("admin endpoint denies anonymous",
          client.get("/admin/users").status_code == 403)
    check("wishlist requires auth",
          client.get("/prices/wishlist").status_code == 403)

    # --- The rate limit fix ------------------------------------------------
    section("Rate limiting (real Redis)")
    if product_id:
        spoofed = client.get(f"/products/{product_id}",
                             params={"limit": 999999, "window": 1})
        check("spoofed limit/window params are ignored", spoofed.status_code == 200,
              spoofed.text)

    # strict_rate_limit is 5/minute on auth endpoints. The 6th must be refused.
    if redis_is_up():
        codes = [
            client.post("/auth/login",
                        json={"email": f"nobody-{uuid.uuid4().hex[:6]}@x.com",
                              "password": "WrongPass123"}).status_code
            for _ in range(8)
        ]
        check("strict rate limit triggers a 429", 429 in codes, f"got {codes}")
    else:
        skip("strict rate limit triggers a 429",
             "Redis not reachable on 127.0.0.1:6379; run 'docker compose up -d'")

    client.close()
    return report()


def report() -> int:
    print(f"\n{'=' * 60}")
    summary = f"  {len(passed)} passed, {len(failed)} failed"
    if skipped:
        summary += f", {len(skipped)} skipped"
    print(summary)
    if failed:
        print("\n  Failures:")
        for name in failed:
            print(f"    - {name}")
    if skipped:
        print("\n  Skipped (NOT verified):")
        for name in skipped:
            print(f"    - {name}")
    print(f"{'=' * 60}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
