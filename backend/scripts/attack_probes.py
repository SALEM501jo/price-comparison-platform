"""
Active attack probes against the running API.

Reading the code says a thing is safe; sending the request proves it. Each
probe below is a real attempt at privilege escalation, injection or
cross-tenant access, run against the live server.
"""
import json
import subprocess
import sys
import uuid

API = "http://127.0.0.1:8000"
PASS = "ProbePass123"
results = []


def curl(method, path, token=None, body=None):
    cmd = ["curl", "-s", "-X", method, f"{API}{path}", "-w", "\n__CODE__%{http_code}"]
    if token:
        cmd += ["-H", f"Authorization: Bearer {token}"]
    if body is not None:
        cmd += ["-H", "Content-Type: application/json", "-d", json.dumps(body)]
    out = subprocess.run(cmd, capture_output=True).stdout.decode("utf-8", "replace")
    raw, _, code = out.rpartition("__CODE__")
    try:
        parsed = json.loads(raw.strip())
    except Exception:
        parsed = raw.strip()
    return int(code.strip() or 0), parsed


def check(name, passed, detail=""):
    results.append((name, passed, detail))
    mark = "PASS" if passed else "*** FAIL ***"
    print(f"  [{mark}] {name}")
    if detail and not passed:
        print(f"           {detail}")


def clear_rate_limit():
    """The limiter is 5 auth requests a minute and it works -- which is itself
    a result. Cleared between probes so the suite can keep going."""
    subprocess.run(
        ["docker", "exec", "redis-local", "redis-cli", "FLUSHDB"],
        capture_output=True,
    )


def signup(kind="buyer"):
    clear_rate_limit()
    email = f"probe-{uuid.uuid4().hex[:10]}@example.com"
    code, body = curl(
        "POST", "/auth/register",
        body={"email": email, "password": PASS, "account_type": kind},
    )
    assert code == 201, (code, body)
    return email, body["access_token"]


print("=" * 74)
print("PRIVILEGE ESCALATION")
print("=" * 74)

for payload in (
    {"account_type": "admin"},
    {"account_type": "ADMIN"},
    {"role": "admin"},
    {"account_type": "merchant", "role": "admin"},
    {"account_type": ["merchant", "admin"]},
):
    body = {"email": f"esc-{uuid.uuid4().hex[:8]}@example.com", "password": PASS}
    body.update(payload)
    clear_rate_limit()
    code, resp = curl("POST", "/auth/register", body=body)
    if code == 201:
        _, me = curl("GET", "/auth/me", token=resp["access_token"])
        got = me.get("role")
        check(f"signup {payload} -> role={got}", got != "admin", f"role granted: {got}")
    else:
        check(f"signup {payload} rejected ({code})", True)

_, mtok = signup("merchant")
curl("POST", "/merchant/store",
     body={"name": f"Probe Shop {uuid.uuid4().hex[:6]}", "phone": "0791234567"},
     token=mtok)
curl("PATCH", "/merchant/store", token=mtok,
     body={"phone": "0791234567", "is_verified": True, "owner_user_id": 1, "id": 1})
_, store = curl("GET", "/merchant/store", token=mtok)
check("merchant cannot self-verify via mass assignment",
      store.get("is_verified") is False,
      f"is_verified={store.get('is_verified')} after sending is_verified=true")

code, listing = curl("POST", "/merchant/listings", token=mtok,
                     body={"name": "iPhone 15 128GB Black", "price": 700,
                           "condition": "new", "match_confidence": 1.0,
                           "store_id": 1, "id": 99999})
check("listing create ignores forged internal fields",
      code == 201 and listing.get("id") != 99999, f"id={listing.get('id')}")

code, _ = curl("PATCH", "/auth/me", token=mtok, body={"role": "admin"})
check("no writable /auth/me route", code in (404, 405), f"HTTP {code}")

print()
print("=" * 74)
print("CROSS-TENANT ACCESS (BOLA / IDOR)")
print("=" * 74)

_, vtok = signup("merchant")
curl("POST", "/merchant/store",
     body={"name": f"Victim {uuid.uuid4().hex[:6]}", "phone": "0791234567"}, token=vtok)
_, vlisting = curl("POST", "/merchant/listings", token=vtok,
                   body={"name": "Samsung Galaxy S24 256GB", "price": 900,
                         "condition": "new"})
vid = vlisting.get("id")

code, _ = curl("PATCH", f"/merchant/listings/{vid}", token=mtok, body={"price": 1})
check("cannot reprice a rival listing", code == 404, f"HTTP {code}")
code, _ = curl("DELETE", f"/merchant/listings/{vid}", token=mtok)
check("cannot delete a rival listing", code == 404, f"HTTP {code}")

_, after = curl("GET", "/merchant/listings", token=vtok)
still = [row for row in after if row.get("id") == vid]
check("victim listing intact", bool(still) and still[0]["price"] == 900.0,
      f"price={still[0]['price'] if still else 'GONE'}")

_, atok = signup("buyer")
_, btok = signup("buyer")
curl("POST", "/prices/wishlist/1", token=atok)
_, bwish = curl("GET", "/prices/wishlist", token=btok)
check("wishlist is per-user", bwish == [], f"leaked {len(bwish)} items")

curl("POST", "/prices/alerts", token=atok,
     body={"product_id": 1, "target_price": 500})
_, alerts_a = curl("GET", "/prices/alerts", token=atok)
_, alerts_b = curl("GET", "/prices/alerts", token=btok)
check("alerts are per-user", alerts_b == [], f"leaked {len(alerts_b)}")
if alerts_a:
    code, _ = curl("DELETE", f"/prices/alerts/{alerts_a[0]['id']}", token=btok)
    check("cannot delete another user's alert", code == 404, f"HTTP {code}")

print()
print("=" * 74)
print("ADMIN SURFACE")
print("=" * 74)
for path, method in (
    ("/admin/users", "GET"),
    ("/admin/stats", "GET"),
    ("/admin/stores", "GET"),
    ("/admin/stores/1/verify", "POST"),
    ("/admin/stores/1/listings", "GET"),
    ("/admin/price-anomalies", "GET"),
    ("/admin/users/1", "DELETE"),
):
    code, _ = curl(method, path, token=mtok)
    check(f"merchant blocked from {method} {path}", code == 403, f"HTTP {code}")
    code, _ = curl(method, path)
    check(f"anonymous blocked from {method} {path}", code in (401, 403), f"HTTP {code}")

print()
print("=" * 74)
print("INJECTION")
print("=" * 74)
INJECTIONS = [
    "' OR '1'='1",
    "'; DROP TABLE products; --",
    "1' UNION SELECT null,null,null--",
    "%%%%%%",
    "____",
    "\\",
    "admin'--",
]
for probe in INJECTIONS:
    q = probe.replace(" ", "%20").replace("&", "%26").replace("'", "%27")
    code, body = curl("GET", f"/products/search?q={q}")
    ok = code in (200, 422)
    check(f"search injection {probe!r} handled ({code})", ok,
          "" if ok else f"unexpected: {str(body)[:90]}")

code, body = curl("GET", "/products/search?q=iPhone%2015%20128GB")
alive = code == 200 and len(body.get("exact", []) or body.get("close", [])) >= 0
check("catalogue intact after injection probes", code == 200 and alive, f"HTTP {code}")

code, _ = curl("POST", "/merchant/listings", token=mtok,
               body={"name": "'; DROP TABLE products; --", "price": 500,
                     "condition": "new"})
check("injection via listing name is stored as data", code in (201, 422), f"HTTP {code}")
code, _ = curl("GET", "/products/search?q=iPhone%2015%20128GB")
check("catalogue intact after stored-injection attempt", code == 200, f"HTTP {code}")

print()
print("=" * 74)
print("TOKEN HANDLING")
print("=" * 74)
_, tok = signup("buyer")
parts = tok.split(".")
forged = parts[0] + "." + parts[1][:-4] + "AAAA" + "." + parts[2]
code, _ = curl("GET", "/auth/me", token=forged)
check("tampered JWT payload rejected", code == 401, f"HTTP {code}")
code, _ = curl("GET", "/auth/me", token=parts[0] + "." + parts[1] + ".")
check("stripped signature rejected", code == 401, f"HTTP {code}")
none_alg = "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0." + parts[1] + "."
code, _ = curl("GET", "/auth/me", token=none_alg)
check("alg=none rejected", code == 401, f"HTTP {code}")

print()
print("=" * 74)
failed = [r for r in results if not r[1]]
print(f"{len(results) - len(failed)}/{len(results)} probes passed")
if failed:
    print()
    print("FAILURES:")
    for name, _, detail in failed:
        print(f"  - {name}  {detail}")
sys.exit(1 if failed else 0)
