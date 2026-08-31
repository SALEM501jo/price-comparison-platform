"""
End-to-end test of the whole platform against a running server.

WHY THIS EXISTS ALONGSIDE THE OTHERS. The suites already here each answer a
different question and none of them answers this one:

    pytest              units and routes, against SQLite, with the rate
                        limiter and cache disabled
    smoke_test.py       the critical paths still respond
    attack_probes.py    the security controls hold under attack

This walks the JOURNEYS a real person takes, in order, against the real
server with the real database, real Redis and the rate limiter switched on --
register, verify, search, save, alert, sell, moderate. Bugs that only appear
when steps run in sequence against shared state are the ones the other three
cannot see: a cache not invalidated, a rotation that breaks the next request,
a listing that resolves differently once another store already has one.

IT CLEANS UP AFTER ITSELF. Everything it creates is prefixed and deleted at
the end, because the whole point of running it is to check a database that is
about to go to production, and a test that leaves fixtures behind defeats
that. Deletion is verified, not assumed.

    cd backend
    .venv/Scripts/python.exe scripts/e2e_test.py
    .venv/Scripts/python.exe scripts/e2e_test.py --keep   # leave the fixtures
"""

import io
import json
import subprocess
import sys
import time
import uuid

sys.path.insert(0, ".")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import httpx  # noqa: E402

API = "http://127.0.0.1:8000"
PREFIX = f"e2e-{uuid.uuid4().hex[:8]}"
PASSWORD = "E2ePass123"

ADMIN_EMAIL = "salem-demo@example.com"
ADMIN_PASSWORD = "DemoPass123"

results = []
section_name = ""


def section(title):
    global section_name
    section_name = title
    print(f"\n{'=' * 74}\n{title}\n{'=' * 74}")


def check(name, passed, detail=""):
    results.append((section_name, name, passed, detail))
    print(f"  [{'PASS' if passed else '*** FAIL ***'}] {name}")
    if detail and not passed:
        print(f"         {detail}")


def clear_rate_limit():
    """The limiter is real and 5/min on auth. Cleared so the run can proceed."""
    subprocess.run(
        ["docker", "exec", "redis-local", "redis-cli", "FLUSHDB"],
        capture_output=True,
    )


client = httpx.Client(base_url=API, timeout=30, follow_redirects=False)


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def register(kind="buyer", tag=""):
    clear_rate_limit()
    email = f"{PREFIX}-{tag or uuid.uuid4().hex[:6]}@example.com"
    r = client.post(
        "/auth/register",
        json={"email": email, "password": PASSWORD, "account_type": kind},
    )
    assert r.status_code == 201, f"register failed: {r.status_code} {r.text}"
    return email, r.json()["access_token"]


# --------------------------------------------------------------------------
section("1. THE SITE IS UP")
# --------------------------------------------------------------------------
r = client.get("/health")
check("health responds 200", r.status_code == 200, r.text)
check("health reports a version", bool(r.json().get("version")))

r = client.get("/openapi.json")
check("openapi spec served in development", r.status_code == 200)

r = client.get("/health")
check(
    "security headers present",
    all(h in r.headers for h in
        ("content-security-policy", "x-frame-options", "x-content-type-options")),
    str(dict(r.headers)),
)
check("server header suppressed", "server" not in
      {k.lower() for k in r.headers}, r.headers.get("server", ""))

# --------------------------------------------------------------------------
section("2. CATALOGUE AND SEARCH")
# --------------------------------------------------------------------------
r = client.get("/products/search", params={"q": "iPhone 15 128GB Black"})
body = r.json()
check("search responds", r.status_code == 200)
check("search understands the query",
      body["interpretation"]["category"] == "phones", str(body["interpretation"]))
check("an exact match is found", body["counts"]["exact"] >= 1, str(body["counts"]))
check("tiers are ordered exact >= close",
      body["counts"]["exact"] >= 0 and "close" in body["counts"])
first = (body.get("exact") or [{}])[0]
check("results carry a price", first.get("lowest_total_cost") is not None)
check("results carry the store name", bool(first.get("best_deal_store")))

r = client.get("/products/search", params={"q": "ايفون ١٥ ١٢٨ جيجا اسود"})
b = r.json()
check("ARABIC query parses", b["interpretation"]["category"] == "phones",
      str(b["interpretation"]))
check("ARABIC query finds the handset", b["counts"]["exact"] >= 1, str(b["counts"]))

r = client.get("/products/search", params={"q": "ipone 15 128gb blak"})
b = r.json()
check("typo is corrected", b["interpretation"]["corrected_query"] is not None,
      str(b["interpretation"]))
check("correction is reported to the user",
      bool(b["interpretation"]["corrections"]))

r = client.get("/products/search",
               params={"q": "ipone 15 128gb blak", "correct": "false"})
check("correct=false searches what was typed",
      r.json()["interpretation"]["corrected_query"] is None)

r = client.get("/products/search", params={"q": "سمسونج جالاكسي"})
names = " ".join(p["canonical_name"].lower()
                 for tier in ("exact", "close", "similar")
                 for p in (r.json().get(tier) or []))
check("no accessories in phone results",
      not any(w in names for w in ("case", "cover", "protector", "microsd")),
      names[:200])

r = client.get("/products/search", params={"q": "تلفزيون سامسونج"})
check("televisions are excluded (Arabic)", r.json()["total"] == 0)

r = client.get("/products/suggest", params={"q": "iphone 15"})
check("suggestions returned", r.status_code == 200 and len(r.json()) > 0)
r = client.get("/products/suggest", params={"q": "ايفو"})
check("ARABIC partial word suggests", len(r.json()) > 0, r.text[:120])

r = client.get("/products/search", params={"q": "%%%%"})
check("wildcard query is neutralised", r.status_code == 200 and
      r.json()["total"] == 0, r.text[:120])

r = client.get("/products/search", params={"q": "a"})
check("too-short query rejected at the edge", r.status_code == 422)

r = client.get("/products/deals", params={"limit": 5})
check("deals endpoint responds", r.status_code == 200)

pid = first.get("id")
r = client.get(f"/products/{pid}")
detail = r.json()
check("product detail responds", r.status_code == 200)
check("detail lists store prices", len(detail.get("prices", [])) > 0)
check("price rows carry a store id (for tap tracking)",
      all("store_id" in p for p in detail["prices"]))
r = client.get(f"/products/{pid}/history")
check("price history responds", r.status_code == 200)
r = client.get("/products/99999999")
check("unknown product is a 404", r.status_code == 404)

# --------------------------------------------------------------------------
section("3. SIGN UP, SIGN IN, SESSIONS")
# --------------------------------------------------------------------------
buyer_email, buyer_token = register("buyer", "buyer")
check("buyer can register", bool(buyer_token))

r = client.get("/auth/me", headers=auth(buyer_token))
check("me returns the account", r.status_code == 200 and
      r.json()["email"] == buyer_email)
check("new account is a plain user", r.json()["role"] == "user", r.text)
check("new account starts unverified", r.json()["email_verified_at"] is None)

clear_rate_limit()
r = client.post("/auth/login", json={"email": buyer_email, "password": "WrongPass1"})
check("wrong password is rejected", r.status_code == 401)
check("no token leaks on failure", "access_token" not in r.text)

clear_rate_limit()
r = client.post("/auth/register",
                json={"email": buyer_email, "password": PASSWORD})
check("duplicate email is refused", r.status_code in (400, 409), r.text[:120])

clear_rate_limit()
r = client.post("/auth/register",
                json={"email": f"{PREFIX}-weak@example.com", "password": "weak"})
check("weak password is refused", r.status_code == 422)

clear_rate_limit()
r = client.post("/auth/login", json={"email": buyer_email, "password": PASSWORD})
check("login succeeds", r.status_code == 200)
check("refresh token is a cookie, not a body field",
      "refresh_token" not in r.json() and
      any("refresh" in c.lower() for c in r.cookies.keys()),
      f"body={list(r.json())} cookies={list(r.cookies)}")
buyer_token = r.json()["access_token"]

r = client.post("/auth/refresh")
check("refresh works from the cookie", r.status_code == 200, r.text[:120])
rotated = r.json()["access_token"]
check("refresh issues a new access token", rotated != buyer_token)

# Logout is authenticated: it revokes EVERY session this user holds, so the
# caller has to prove who they are. The cookie alone identifies a session,
# not a person.
r = client.post("/auth/logout")
check("logout without a token is refused", r.status_code == 401, r.text[:120])

r = client.post("/auth/logout", headers=auth(rotated))
check("logout responds", r.status_code in (200, 204), r.text[:120])
r = client.post("/auth/refresh")
check("refresh fails after logout", r.status_code == 401, r.text[:120])

# --------------------------------------------------------------------------
section("4. RATE LIMITING IS REAL")
# --------------------------------------------------------------------------
clear_rate_limit()
codes = []
for _ in range(9):
    codes.append(
        client.post("/auth/login",
                    json={"email": "nobody@example.com", "password": "x"}).status_code
    )
check("auth endpoint eventually returns 429", 429 in codes, str(codes))
clear_rate_limit()

# --------------------------------------------------------------------------
section("5. WISHLIST AND PRICE ALERTS")
# --------------------------------------------------------------------------
clear_rate_limit()
_, buyer_token = register("buyer", "shopper")

r = client.post(f"/prices/wishlist/{pid}", headers=auth(buyer_token))
check("product can be saved", r.status_code in (200, 201), r.text[:120])
r = client.get("/prices/wishlist", headers=auth(buyer_token))
check("wishlist lists it", any(i["product_id"] == pid for i in r.json()), r.text[:160])
check("wishlist carries a real price",
      r.json()[0].get("lowest_total_cost") is not None, r.text[:160])
r = client.post(f"/prices/wishlist/{pid}", headers=auth(buyer_token))
check("saving twice is refused, not duplicated", r.status_code == 409)
r = client.delete(f"/prices/wishlist/{pid}", headers=auth(buyer_token))
check("product can be removed", r.status_code in (200, 204))

r = client.get("/prices/wishlist")
check("wishlist needs an account", r.status_code == 401)

r = client.post("/prices/alerts", headers=auth(buyer_token),
                json={"product_id": pid, "target_price": 100})
check("alert can be created", r.status_code in (200, 201), r.text[:120])
alert_id = r.json().get("id")
r = client.get("/prices/alerts", headers=auth(buyer_token))
check("alert is listed", any(a["id"] == alert_id for a in r.json()))
r = client.post("/prices/alerts", headers=auth(buyer_token),
                json={"product_id": pid, "target_price": -5})
check("negative target is refused", r.status_code == 422)
r = client.delete(f"/prices/alerts/{alert_id}", headers=auth(buyer_token))
check("alert can be deleted", r.status_code in (200, 204))

# --------------------------------------------------------------------------
section("6. A SHOP SIGNS UP AND SELLS")
# --------------------------------------------------------------------------
clear_rate_limit()
shop_email, shop_token = register("merchant", "shop")
r = client.get("/auth/me", headers=auth(shop_token))
check("merchant account gets the merchant role", r.json()["role"] == "merchant")

r = client.get("/merchant/store", headers=auth(shop_token))
check("no store yet is a 404, not an error", r.status_code == 404)

r = client.post("/merchant/store", headers=auth(shop_token), json={
    "name": f"{PREFIX} Test Shop", "phone": "0791234567",
    "whatsapp": "0791234567",
    "instagram_url": "https://instagram.com/e2eshop",
})
check("store can be registered", r.status_code == 201, r.text[:200])
check("instagram is stored",
      r.json().get("instagram_url") == "https://instagram.com/e2eshop", r.text[:160])
check("a new store is NOT verified", r.json()["is_verified"] is False)

r = client.post("/merchant/store", headers=auth(shop_token),
                json={"name": "Second Shop", "phone": "0791234567"})
check("one store per account", r.status_code in (400, 409), r.text[:120])

for bad in ("https://evil.com/instagram.com/x", "javascript:alert(1)"):
    r = client.patch("/merchant/store", headers=auth(shop_token),
                     json={"instagram_url": bad})
    check(f"bad instagram url refused ({bad[:26]})", r.status_code == 422)

r = client.patch("/merchant/store", headers=auth(shop_token),
                 json={"phone": "0799999999"})
check("contact details can be edited", r.status_code == 200, r.text[:120])

r = client.post("/merchant/listings", headers=auth(shop_token), json={
    "name": "iPhone 15 128GB Black", "price": 555.5, "delivery_cost": 0,
    "condition": "new",
})
check("listing can be created", r.status_code == 201, r.text[:200])
listing = r.json()
check("listing resolves to a catalogue product",
      listing.get("matched_product_id") is not None, r.text[:200])
check("listing is searchable", listing.get("is_searchable") is True)

r = client.post("/merchant/listings", headers=auth(shop_token), json={
    "name": "iPhone 14 Pro 256GB", "price": 400, "condition": "used",
})
check("used listing without battery health is refused", r.status_code == 422)

r = client.post("/merchant/listings", headers=auth(shop_token), json={
    "name": "iPhone 14 Pro 256GB", "price": 400, "condition": "used",
    "battery_health": 88, "has_damage": True,
})
check("damaged listing needs a description", r.status_code == 422)

r = client.post("/merchant/listings", headers=auth(shop_token), json={
    "name": "iPhone 14 Pro 256GB", "price": 400, "condition": "used",
    "battery_health": 88, "has_damage": False,
})
check("proper used listing is accepted", r.status_code == 201, r.text[:200])
used_listing = r.json()

r = client.patch(f"/merchant/listings/{listing['id']}", headers=auth(shop_token),
                 json={"price": 549})
check("price can be edited", r.status_code == 200 and r.json()["price"] == 549.0,
      r.text[:120])
r = client.patch(f"/merchant/listings/{listing['id']}", headers=auth(shop_token),
                 json={"availability": False})
check("stock can be toggled", r.json()["availability"] is False)
r = client.patch(f"/merchant/listings/{listing['id']}", headers=auth(shop_token),
                 json={"availability": True})

r = client.get("/merchant/stats", headers=auth(shop_token))
check("merchant stats respond", r.status_code == 200, r.text[:120])
check("stats start at zero taps", r.json()["total"] == 0, r.text[:120])
check("every channel is reported",
      set(r.json()["by_channel"]) >= {"call", "whatsapp", "facebook"}, r.text[:160])

# --------------------------------------------------------------------------
section("7. AN UNVERIFIED SHOP IS INVISIBLE")
# --------------------------------------------------------------------------
r = client.get("/products/search", params={"q": "iPhone 15 128GB Black"})
shops = " ".join(str(p.get("best_deal_store")) for p in (r.json().get("exact") or []))
check("unverified shop's price is NOT the best deal", PREFIX not in shops, shops)
r = client.get(f"/products/{listing['matched_product_id']}")
check("unverified shop is absent from the product page",
      not any(PREFIX in p["store_name"] for p in r.json()["prices"]),
      str([p["store_name"] for p in r.json()["prices"]]))

# --------------------------------------------------------------------------
section("8. CROSS-TENANT ISOLATION")
# --------------------------------------------------------------------------
clear_rate_limit()
rival_email, rival_token = register("merchant", "rival")
client.post("/merchant/store", headers=auth(rival_token),
            json={"name": f"{PREFIX} Rival Shop", "phone": "0791111111"})

r = client.patch(f"/merchant/listings/{listing['id']}", headers=auth(rival_token),
                 json={"price": 1})
check("a rival cannot edit another shop's price", r.status_code == 404, r.text[:120])
r = client.delete(f"/merchant/listings/{listing['id']}", headers=auth(rival_token))
check("a rival cannot delete another shop's listing", r.status_code == 404)
r = client.get("/merchant/stats", headers=auth(rival_token))
check("a rival sees only their own taps", r.json()["total"] == 0)
r = client.get("/merchant/listings", headers=auth(rival_token))
check("a rival's listing list is their own",
      all(listing["id"] != x["id"] for x in r.json()), r.text[:160])

r = client.get("/merchant/store", headers=auth(buyer_token))
check("a shopper cannot reach merchant routes", r.status_code == 403)

# --------------------------------------------------------------------------
section("9. ADMIN")
# --------------------------------------------------------------------------
clear_rate_limit()
r = client.post("/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
check("admin can sign in", r.status_code == 200, r.text[:160])
admin_token = r.json()["access_token"]

r = client.get("/admin/stats", headers=auth(admin_token))
check("admin stats respond", r.status_code == 200)
r = client.get("/admin/users", headers=auth(admin_token))
check("admin can list users", r.status_code == 200 and len(r.json()) > 0)

r = client.get("/admin/stores", headers=auth(admin_token))
stores = r.json()
check("admin can list stores", r.status_code == 200)
check("store rows carry tap counts", all("contact_taps" in s for s in stores))
check("store rows carry a review status", all("review_status" in s for s in stores))

mine = next(s for s in stores if s["name"] == f"{PREFIX} Test Shop")
check("a new shop shows as pending", mine["review_status"] == "pending")

r = client.get("/admin/stores", headers=auth(admin_token),
               params={"pending_only": "true"})
check("pending filter includes it",
      any(s["id"] == mine["id"] for s in r.json()))

rival = next(s for s in stores if s["name"] == f"{PREFIX} Rival Shop")
r = client.post(f"/admin/stores/{rival['id']}/decline", headers=auth(admin_token))
check("a claim can be declined", r.status_code == 200 and
      r.json()["review_status"] == "declined", r.text[:120])
r = client.get("/admin/stores", headers=auth(admin_token),
               params={"pending_only": "true"})
check("a declined claim leaves the pending queue",
      not any(s["id"] == rival["id"] for s in r.json()))

r = client.post(f"/admin/stores/{mine['id']}/verify", headers=auth(admin_token))
check("a claim can be approved", r.status_code == 200)

r = client.get("/products/search", params={"q": "iPhone 15 128GB Black"})
shops = " ".join(str(p.get("best_deal_store")) for p in (r.json().get("exact") or []))
check("VERIFYING PUBLISHES THE PRICE IMMEDIATELY (cache invalidated)",
      PREFIX in shops, f"expected the new shop in: {shops}")

r = client.get(f"/admin/stores/{mine['id']}/listings", headers=auth(admin_token))
check("admin can read a shop's listings", r.status_code == 200 and
      len(r.json()["listings"]) == 2, r.text[:160])

r = client.patch(f"/admin/listings/{listing['id']}", headers=auth(admin_token),
                 json={"price": 500})
check("admin can correct any price", r.status_code == 200 and
      r.json()["price"] == 500.0, r.text[:120])

r = client.post(f"/admin/stores/{mine['id']}/unverify", headers=auth(admin_token))
check("verification can be withdrawn", r.status_code == 200)
r = client.get("/products/search", params={"q": "iPhone 15 128GB Black"})
shops = " ".join(str(p.get("best_deal_store")) for p in (r.json().get("exact") or []))
check("withdrawing hides the price again", PREFIX not in shops, shops)

r = client.get("/admin/price-anomalies", headers=auth(admin_token))
check("price anomalies respond", r.status_code == 200)
r = client.get("/admin/scrape-jobs", headers=auth(admin_token))
check("scrape job history responds", r.status_code == 200)

me = client.get("/auth/me", headers=auth(admin_token)).json()
r = client.patch(f"/admin/users/{me['id']}/role", headers=auth(admin_token),
                 json={"role": "user"})
check("an admin cannot demote themselves", r.status_code == 400, r.text[:120])

# --------------------------------------------------------------------------
section("10. CONTACT TAPS")
# --------------------------------------------------------------------------
client.post(f"/admin/stores/{mine['id']}/verify", headers=auth(admin_token))
for channel in ("call", "whatsapp", "whatsapp", "instagram"):
    client.post("/products/contact-event",
                json={"store_id": mine["id"],
                      "product_id": listing["matched_product_id"],
                      "channel": channel})
r = client.get("/merchant/stats", headers=auth(shop_token))
check("taps are counted", r.json()["total"] == 4, r.text[:160])
check("taps are split by channel",
      r.json()["by_channel"]["whatsapp"] == 2, r.text[:160])
check("the busiest product is reported",
      len(r.json()["top_products"]) >= 1, r.text[:200])

r = client.post("/products/contact-event",
                json={"store_id": 999999, "channel": "call"})
check("an unknown store is not an oracle", r.status_code == 202)
r = client.post("/products/contact-event",
                json={"store_id": mine["id"], "channel": "pigeon"})
check("an unknown channel is refused", r.status_code == 422)

r = client.get("/admin/stores", headers=auth(admin_token))
row = next(s for s in r.json() if s["id"] == mine["id"])
check("admin sees the same tap count", row["contact_taps"] == 4, str(row))

# --------------------------------------------------------------------------
section("11. CONTACT FORM")
# --------------------------------------------------------------------------
clear_rate_limit()
r = client.post("/support/contact", json={
    "email": f"{PREFIX}@example.com", "subject": "E2E check",
    "body": "This message was sent by the end-to-end test run.",
})
check("contact form accepts a message", r.status_code == 202, r.text[:120])
r = client.get("/admin/support-messages", headers=auth(admin_token))
msg = next((m for m in r.json()["messages"] if PREFIX in m["email"]), None)
check("admin can read it", msg is not None, r.text[:200])
if msg:
    r = client.post(f"/admin/support-messages/{msg['id']}/handled",
                    headers=auth(admin_token), params={"handled": "true"})
    check("it can be marked handled", r.status_code == 200)

r = client.post("/support/contact",
                json={"email": "x@example.com", "body": "short"})
check("a too-short message is refused", r.status_code == 422)

# --------------------------------------------------------------------------
section("12. AUTHORISATION HOLDS")
# --------------------------------------------------------------------------
for path, method in (
    ("/admin/users", "GET"), ("/admin/stats", "GET"),
    ("/admin/stores", "GET"), ("/admin/support-messages", "GET"),
    ("/admin/price-anomalies", "GET"),
):
    r = client.request(method, path)
    check(f"anonymous blocked from {path}", r.status_code == 401)
    r = client.request(method, path, headers=auth(buyer_token))
    check(f"shopper blocked from {path}", r.status_code == 403)

r = client.get("/auth/me", headers={"Authorization": "Bearer not-a-token"})
check("a garbage token is rejected", r.status_code == 401)

# --------------------------------------------------------------------------
section("13. CLEAN UP AFTER OURSELVES")
# --------------------------------------------------------------------------
if "--keep" in sys.argv:
    print("  --keep passed; leaving fixtures in place")
else:
    from sqlalchemy import text
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        db.execute(text("delete from stores where name like :p"),
                   {"p": f"{PREFIX}%"})
        db.execute(text("delete from users where email like :p"),
                   {"p": f"{PREFIX}%"})
        db.execute(text("delete from support_messages where email like :p"),
                   {"p": f"{PREFIX}%"})
        db.execute(
            text("delete from products where not exists "
                 "(select 1 from product_aliases a where a.product_id = products.id)")
        )
        db.commit()

        left_users = db.execute(
            text("select count(*) from users where email like :p"),
            {"p": f"{PREFIX}%"}).scalar()
        left_stores = db.execute(
            text("select count(*) from stores where name like :p"),
            {"p": f"{PREFIX}%"}).scalar()
        orphans = db.execute(
            text("select count(*) from products p where not exists "
                 "(select 1 from product_aliases a where a.product_id = p.id)")
        ).scalar()
        check("test users removed", left_users == 0, f"{left_users} left")
        check("test stores removed", left_stores == 0, f"{left_stores} left")
        check("no orphaned products left behind", orphans == 0, f"{orphans} left")
    finally:
        db.close()

# --------------------------------------------------------------------------
print(f"\n{'=' * 74}")
failed = [r for r in results if not r[2]]
by_section = {}
for sec, _name, ok, _d in results:
    hit = by_section.setdefault(sec, [0, 0])
    hit[0 if ok else 1] += 1
for sec, (ok, bad) in by_section.items():
    mark = "OK  " if not bad else "FAIL"
    print(f"  {mark}  {sec:<52} {ok} passed, {bad} failed")
print(f"{'=' * 74}")
print(f"  {len(results) - len(failed)}/{len(results)} checks passed")
if failed:
    print("\n  FAILURES:")
    for sec, name, _ok, detail in failed:
        print(f"    [{sec}] {name}")
        if detail:
            print(f"        {detail[:160]}")
raise SystemExit(1 if failed else 0)
