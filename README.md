# PriceCompare

A price comparison platform for Jordanian retailers. Search for a specific
product variant — *iPhone 15 128GB Black* — and get the exact match first, then
close variants, then similar products, each labelled with **why** it differs.

```
$ search "iPhone 15 128GB Black"
Looking for:  [iphone 15] [128gb] [black]

EXACT MATCH · Everything you asked for
  100%  Apple iPhone 15 128GB 5G Smartphone - Black    877.50 JOD · SmartBuy · 4 stores

$ search "iPhone 15 256GB Black"
Looking for:  [iphone 15] [256gb] [black]

CLOSE · Same product, one detail differs
   90%  Apple iPhone 15 256GB 5G - Blue          different colour (blue, not black)

SIMILAR · Related, but not what you searched for
   75%  Apple iPhone 15 128GB 5G Smartphone      different storage (128gb, not 256gb)
```

Four stores list that first handset under four different names — including
Carrefour's *"Midnight"*, which is Apple's name for the black colourway. All
four collapse into one row with one price comparison.

---

## The problem this solves

Four stores sell the same phone under four different names:

| Store | Listing |
|---|---|
| DNA Jordan | `Apple iPhone 15 128GB 5G Smartphone - Black` |
| SmartBuy | `iPhone 15 128GB Black (5G)` |
| Carrefour Jordan | `Apple iPhone 15 128GB 5G - Midnight` |
| City Center | `Apple iPhone 15 128GB Black` |

Same product. Four names. A comparison site has to recognise that — and it has
to do the reverse too: recognise that `iPhone 15 256GB Black` is a *different*
product that must not be presented as a match.

### Why fuzzy string matching cannot do this

The obvious approach is string similarity. It fails badly, and the failure is
structural rather than a tuning problem.

Searching `"iPhone 11 Pro Black 128GB"` against a real catalogue, ranked by
`rapidfuzz.ratio` over normalised names:

```
1.  94.34  iPhone 11 Pro Black 128GB Smartphone 5G   [exact, reworded]
2.  70.00  Apple iPhone 11 Pro Max 128GB Black       [WRONG MODEL]
3.  67.86  Apple iPhone 11 Pro 256GB Black           [WRONG STORAGE]
4.  67.86  Apple iPhone 11 Pro 128GB Black           <-- what the user asked for
5.  64.29  Apple iPhone 12 Pro 128GB Black           [WRONG GENERATION]
```

The correct product ranks **fourth**, tied exactly with the 256GB model — a
different phone at a different price — and below the Pro Max.

The reason: **edit distance counts characters, not meaning.** `128GB → 256GB`
is a one-character edit that changes which product you receive. `Black 128GB →
128GB Black` is a large edit that changes nothing. Levenshtein sees these
backwards, and no threshold value reorders them.

### What this does instead

Both the query and every listing are parsed into **structured attributes**, then
scored on weighted attribute agreement:

```python
"iPhone 11 Pro Black 128GB"
  -> {brand: apple, model: iphone 11, variant: pro, storage: 128gb, color: black}
```

| Attribute | Weight | Rationale |
|---|---|---|
| brand | *gate* | An Apple result must never be offered for a Samsung query |
| model | 33 | Generation defines the product |
| variant | 28 | Pro / Pro Max / base are different phones |
| storage | 24 | Different SKU, different price |
| colour | 10 | Cosmetic |
| memory | 5 | Real listings specify it (`4GB & 128GB`); minor next to storage |

Same query, same catalogue:

```
100.0%  EXACT     Apple iPhone 11 Pro 128GB Black
100.0%  EXACT     iPhone 11 Pro Black 128GB Smartphone 5G
 89.5%  CLOSE     Apple iPhone 11 Pro 128GB Midnight Green   different colour
 74.7%  SIMILAR   Apple iPhone 11 Pro 256GB Black            different storage
 70.5%  SIMILAR   Apple iPhone 11 Pro Max 128GB Black        different variant
 65.3%  excluded  Apple iPhone 12 Pro 128GB Black            different model
  0.0%  excluded  Samsung Galaxy S24 128GB Black             different brand
```

Every score is **explainable**. The UI can say *"90% — same model and storage,
different colour"* rather than showing an opaque number.

### Categories are data, not code

`app/matching/rules.py` holds the rules; the parser and scorer never mention a
product type. Supporting washing machines means adding a `CategoryRules` entry
with `capacity_kg` and `energy_rating` — no engine changes, and no migration,
because attributes are stored as JSON rather than one column each.

---

## Architecture

Two matching problems that look alike and are not:

|  | Entity resolution (ingest) | Search relevance (query) |
|---|---|---|
| Question | Are these two listings the same product? | Which products answer this query? |
| Output | Merge / don't — binary | Ranked tiers |
| Needs | High precision — a wrong merge shows one phone's price under another | Good ordering plus explainability |
| Code | `services/deduplication.py` | `services/search.py` |

Both parse names with `app/matching/parse()` — one code path, which is what
makes their attributes comparable. They differ in what they do with the score:
ingest merges only on an **exact, symmetric** attribute match, because scoring
one direction over-merges (a bare `iPhone 15` scores 100% against
`iPhone 15 128GB Black`, since unspecified attributes are not penalised — correct
for search, wrong for deciding two listings are the same object).

Search runs in two stages: cheap candidate generation in Postgres on the indexed
`(match_category, brand)` pair, then reranking in Python where the weights live.

**Data model.** `products` are canonical items; `product_aliases` map each
store's name/SKU/URL onto one; `prices` and `price_history` hang off aliases.
That indirection is what lets four differently-named listings show as one row
with four prices.

---

## Security

The OWASP Top 10 is a design requirement here, not an afterthought.

| Category | What is done |
|---|---|
| **A01 Access control** | Centralised auth dependencies; `require_admin` for RBAC; wishlist and alerts scoped by `user_id`; 401 vs 403 distinguished correctly |
| **A02 Cryptographic failures** | Refresh token in an httpOnly cookie, unreadable by JavaScript; access token in memory only, never in storage; bcrypt cost 12; `JWT_SECRET_KEY` minimum 32 chars enforced at boot |
| **A03 Injection** | SQLAlchemy parameterises everything; `ILIKE` wildcards in user input escaped, so `%%%%` cannot force a table scan |
| **A04 Insecure design** | Redis rate limiting (5/min on auth, 100/min elsewhere), per IP and per endpoint; limits are not client-controllable |
| **A05 Misconfiguration** | CSP, HSTS, `X-Frame-Options`, `nosniff`, Referrer-Policy, Permissions-Policy; `Server` header suppressed; strict CORS allow-list; docs disabled in production |
| **A06 Vulnerable components** | `pip-audit` in CI, failing the build on any known CVE, and running weekly as well as on push |
| **A07 Authentication failures** | Refresh token rotation with automatic reuse detection; `POST /auth/logout` revokes every session; timing-safe login; password policy; email verification with single-use, hashed, expiring tokens |
| **A08 Integrity failures** | CI runs tests, applies **and reverses** migrations from an empty database, runs the smoke test, and audits dependencies |
| **A09 Logging failures** | Structured JSON audit log of every auth and admin action; email addresses stored as keyed-HMAC tags rather than plaintext |
| **A10 SSRF** | Live scraping fetches remote URLs. Scheme and host allowlists, DNS resolution checked against private/loopback/link-local ranges, no redirect following, bounded time and size — see *Scraping* |

### Email verification

Free to run: `EMAIL_BACKEND=console` prints the message to the server log, so
the whole flow works with **no provider account, no domain and no DNS records**.
Switching to `smtp` and filling in credentials is a config change — the backend
uses stdlib SMTP, which every free-tier provider speaks, so there is no vendor
SDK and nothing extra for `pip-audit` to find a CVE in.

Only the token's SHA-256 hash is stored; the token exists in the email and
nowhere else, so a database dump yields no working links. (SHA-256 is correct
here and bcrypt is not: these are 256 bits of CSPRNG output, so there is nothing
to brute-force and the hash only has to be one-way and fast.)

The security shape of the feature is the unauthenticated endpoints:

- **`/auth/resend-verification` always returns 202** — whether the address
  exists, is already verified, or is throttled. A 404 for unknown addresses
  would make it a membership check anyone could run.
- **Resending is throttled per account**, not only per IP. An IP limit alone
  still lets someone rotate addresses and bury a stranger's inbox using our
  sending reputation.
- **Every redemption failure returns one message.** Distinguishing "expired"
  from "already used" from "never existed" informs an attacker holding a stale
  link and helps a real user not at all.
- **Alert emails are never sent to an unverified address.** Anyone can type a
  stranger's email at signup; that is precisely how a notification feature
  becomes a way to mail someone who never asked.

Verification gates outbound email, not access — browsing needs no confirmed
address, and locking a new user out over an unclicked link would lose them for
no security gain.

### Price alert notifications

Alerts were previously only evaluated when a user happened to open the page,
which made "tell me when it drops" a promise the system never kept. They now
run at the end of each scrape. `notified_at` prevents re-sending on every run
while a price stays low, and is cleared when it rises back above target so a
later drop notifies again.

### Refresh token rotation

Every use of a refresh token burns it and issues a new one. This does not
prevent theft; it makes theft **visible**. A one-time credential presented twice
means two parties hold it — so the entire token chain is revoked and both must
reauthenticate. The pattern is from the OAuth 2.0 Security BCP.

Only the token's `jti` is stored, never the token, so a database dump is not a
set of working credentials.

Access tokens are deliberately stateless and non-revocable: verifying them
against a table would mean a database read on every request, which is the cost
the design exists to avoid. Their 15-minute lifetime bounds the damage instead.

---

## Getting started

**Requires** Python 3.12, Node 20+, Docker.

```bash
docker compose up -d          # Postgres + Redis
```

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate    # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env          # then set JWT_SECRET_KEY: openssl rand -hex 32
alembic upgrade head
python -m app.services.scraper                    # seed mock store data
uvicorn app.main:app --reload --port 8000 --no-server-header
```

```bash
cd frontend
npm install
npm run dev
```

App at http://localhost:5173, API docs at http://localhost:8000/docs.

On Windows, `start-dev.ps1` starts all of it in one go.

> `--no-server-header` matters: the `Server: uvicorn` header cannot be removed
> from middleware, because uvicorn writes it at the ASGI protocol level after
> middleware has returned.

---

## Testing

```bash
cd backend && pytest -q                    # 217 unit tests
```

```bash
cd backend && python scripts/smoke_test.py # 52 checks against a running stack
```

The unit suite uses SQLite and stubs the rate limiter for determinism. The smoke
test drives the real thing — real Postgres, real Redis, real HTTP — and is what
catches the things unit tests structurally cannot. It found three bugs that 56
passing unit tests did not, including a `Server` header that middleware could
never have removed.

Checks that depend on Redis report **SKIP**, never PASS, when it is unreachable,
so an unverified control is never mistaken for a working one.

```bash
cd frontend && npm run lint && npm run build
```

### Maintenance scripts

| Script | Purpose |
|---|---|
| `scripts/backfill_attributes.py` | Populate matching attributes on existing products; repairs legacy display names |
| `scripts/merge_duplicates.py` | Merge canonical products the old engine split apart |
| `scripts/smoke_test.py` | End-to-end verification against a running stack |

The two that modify data support `--dry-run`.

---

## API

| Method | Path | |
|---|---|---|
| POST | `/auth/register` | Sets refresh cookie |
| POST | `/auth/login` | Sets refresh cookie |
| POST | `/auth/refresh` | Rotates; reuse revokes the chain |
| POST | `/auth/logout` | Revokes every session |
| POST | `/auth/verify-email` | Redeems a link; single use |
| POST | `/auth/resend-verification` | Always 202 — never reveals who has an account |
| GET | `/auth/me` | |
| GET | `/products/search?q=` | **Tiered results** |
| GET | `/products/{id}` | All store prices, cheapest total first |
| GET | `/products/{id}/history` | Price history |
| GET/POST/DELETE | `/prices/wishlist` | Authenticated |
| GET/POST/DELETE | `/prices/alerts` | Authenticated |
| GET | `/admin/*` | Admin only |
| GET | `/mock/{store}/search` | Simulated store feeds |

`GET /products/search?q=iPhone 15 256GB Black` — an actual response, trimmed to
the interesting fields:

```json
{
  "interpretation": {
    "query": "iPhone 15 256GB Black",
    "category": "phones",
    "attributes": {"brand": "apple", "model": "iphone 15",
                   "variant": "base", "storage": "256gb", "color": "black"},
    "structured": true
  },
  "exact": [],
  "close": [{
    "canonical_name": "Apple iPhone 15 256GB 5G - Blue",
    "match_score": 90.0,
    "differences": ["different colour (blue, not black)"],
    "lowest_total_cost": 977.5, "best_deal_store": "SmartBuy", "store_count": 2
  }],
  "similar": [{
    "canonical_name": "Apple iPhone 15 128GB 5G Smartphone - Black",
    "match_score": 75.0,
    "differences": ["different storage (128gb, not 256gb)"],
    "lowest_total_cost": 877.5, "best_deal_store": "SmartBuy", "store_count": 4
  }],
  "total": 2
}
```

`lowest_total_cost` is price **plus delivery** — a store with a lower sticker
price and dearer delivery is not the better deal.

`interpretation` echoes what the server understood the query to mean. When a
search surprises someone, the difference between *"we don't stock it"* and
*"it read 128GB and you meant 256"* is otherwise invisible.

---

## Scraping

Live data comes from **SmartBuy** (`smartbuy-me.com`) via the Shopify
storefront feed at `/products.json` — the same catalogue the site renders, as
structured data. Parsing HTML instead would mean guessing CSS selectors that
break whenever the merchant edits their theme, per store. The JSON shape is
Shopify's, so one adapter covers every store on the platform. It also carries
the barcode as the variant SKU, which is what makes Layer 1 of the matching
engine — exact SKU match — work on real identifiers.

```bash
cd backend && python -m app.services.ingest
```

Also runs on a six-hourly cron (`.github/workflows/scrape.yml`) and from
`POST /admin/scrape`.

Money is stored as `Numeric(10,3)`, not `Float`. JOD has three decimal places,
the feeds return `"136.000"`, and these values are summed and then *compared* —
to pick the cheapest store and to decide whether a price alert has been met.
Binary floating point cannot represent most decimal fractions, so two stores a
thousandth of a dinar apart could be ordered wrongly.

### SSRF defences (OWASP A10)

A scraper is a server-side URL fetcher, which is the exact shape of an SSRF
vulnerability. Point it at `169.254.169.254` and it reads cloud instance
metadata; at `localhost:6379` and it reads this app's own Redis. Five controls,
in `app/services/scrapers/http.py`:

1. **Scheme allowlist** — https only; `file://`, `gopher://` and friends refused
2. **Host allowlist** — derived from the store registry, so a host cannot be
   fetched without first being declared as a store
3. **DNS resolution before connecting**, with every returned address checked
   against private, loopback, link-local and reserved ranges. An allowlisted
   host that resolves to `127.0.0.1` is still refused, and one private answer
   among several is enough to refuse
4. **No redirect following** — a redirect is a URL chosen by the remote server,
   exactly the input we are not trusting. Each hop is re-validated explicitly
5. **Bounded time and response size**, so a slow or enormous response cannot
   exhaust the worker

Not solved: DNS rebinding, which needs the connection pinned to the validated
IP. The host allowlist is what makes that gap acceptable.

`robots.txt` is honoured, requests are spaced (and a site's `Crawl-delay`
raises that spacing, never lowers it), and the client identifies itself
honestly rather than impersonating a browser.

> **Note on untrusted content.** A store's `robots.txt` was found to contain
> prose addressed to AI agents, asking the reader to install a shopping skill
> and make purchases on the user's behalf. The parser reads only
> `Allow` / `Disallow` / `Crawl-delay`; everything else in a fetched document
> is data, never instruction. There is a test asserting exactly that.

### What real data broke

The mock catalogue was clean. Real titles are not, and two things failed on
first contact:

| Real listing | Problem |
|---|---|
| `Hp Intel I7 -8550U, 16GB DDR4 & 512GB SSD, 15.6Inch` | No word identifies it as a laptop — the store files that under `product_type: Notebook`. Every such listing was uncategorised. |
| `Xiaomi Redmi 17 4G, 4GB & 128GB, 6.9Inch` | Storage took **4GB** — the memory. Real titles never say "RAM", so a keyword lookahead finds nothing. |

Fixed by passing the store's own category as a parse hint, and by splitting
capacities on size rather than keyword: between two figures on one device the
larger is storage and the smaller is memory. Both are regression-tested against
the exact strings that broke them.

## Limitations

**Only one store is scraped for real.** The other three (DNA, Carrefour Jordan,
City Center) remain mock data in `app/services/scraper.py` — real retailer
names, invented prices. Adding a real store means appending a `StoreConfig`;
adding a non-Shopify one also means writing an adapter.

**Each retailer's terms of service govern what is actually permitted.** Reading
public catalogue endpoints politely is the courteous baseline, not a legal
opinion.

**Also outstanding:**

- `POST /admin/scrape` runs the real ingest, but via `BackgroundTasks` — the
  work dies with a restart and does not spread across replicas. A real
  deployment wants a task queue. The scheduled path does not depend on it.
- The matching rules cover phones and laptops only
- `/admin/price-anomalies` is still N+1

---

## Project structure

```
backend/
  app/
    matching/        parse names into attributes, score them
      rules.py       CATEGORY RULES AS DATA -- the extension point
      extractors.py  the only place regexes live
      parser.py      generic, rules-driven
      scorer.py      weighted scoring, gates, tiers, explanations
    services/
      search.py      candidate generation + reranking
      deduplication.py  entity resolution at ingest
      tokens.py      refresh rotation, revocation, replay detection
      verification.py   email verification: issue, send, redeem
      notifications.py  price alert emails
      email/         sender interface; console (free) and SMTP backends
      ingest.py      scrape -> canonical products -> prices
      scraper.py     mock store feeds (the three unscraped stores)
      scrapers/      REAL scraping
        http.py      SSRF-hardened fetch -- the security boundary
        robots.py    robots.txt parsing and compliance
        shopify.py   Shopify storefront adapter
        registry.py  store configs; the host allowlist derives from these
    security/        JWT, password hashing, cookies, rate limiting
    routers/         auth, products, prices, admin, mock stores
    models/          SQLAlchemy models
  alembic/versions/  5 migrations
  tests/             217 tests
  scripts/           smoke test + maintenance tooling
frontend/src/
  components/search/ tiered results, match badges, query interpretation
  components/prices/ per-store price table
  pages/             Home, Results, ProductDetail, Login, Register
  api/               axios instance with token refresh
```
