# Engineering log — احسن سعر (Ahsan Se3r)

The project's engineering log: the detailed running record of its current
state, how the live site is operated, the decisions taken and why, what was
tried and rejected, and what comes next. It is updated as the work happens,
and it replaces the earlier session handoffs, folding in everything since.

**Repo:** https://github.com/SALEM501jo/price-comparison-platform (local
checkout `G:\Downloads\price-comparison-platform`) · **Branch:** all work is on
`main`, which the server tracks. A full-history secret scan came back clean on
2026-09-14. The old `frontend` branch is unused (see Next steps).

**Live at https://ahsanse3r.com** — see [Production](#production) below.

> **This repository is public.** So is this file. Never put a secret, a key, an
> SMTP login or anything from `deploy/.env` in it. What is here is already
> public by other means (the domain resolves to the server IP; the operator's
> contact address is on `/privacy`).

`README.md` is the short overview. This file carries what a README should not:
what was tried and rejected, the traps in this environment, and where to go
next.

---

## What this is

A price comparison platform for Jordanian retailers, built as a **real-world CV
project**, not a student exercise. The OWASP Top 10 is an explicit requirement.

**The core problem:** a shopper searches for a specific variant — *iPhone 15
128GB Black* — and must get the exact match first, then 85–99% matches, then
70–84%, each labelled with **why** it differs.

**The insight the whole project rests on:** fuzzy string matching cannot do
this, and it is not a tuning problem. Measured against a real catalogue, ranked
by `rapidfuzz.ratio`, the query "iPhone 11 Pro Black 128GB" put the correct
product **4th at 67.9** — tied with the 256GB model and below the Pro Max.
`128GB → 256GB` is a one-character edit that changes the product; word order is
a large edit that changes nothing. Edit distance sees that backwards.

The answer is structured attribute extraction plus weighted scoring. Keep that
argument — it is still the strongest thing in the project.

**The second idea:** most phone retail in Jordan happens through shops with no
website at all. So the platform has two supply sides — scraped stores, and
**merchants who submit their own prices and are reached by phone**. That is why
there is no checkout anywhere.

---

## Current state (verified, not recalled)

| | |
|---|---|
| Backend tests | **1,079** — `cd backend && pytest -q` |
| Frontend tests | **197** — `cd frontend && npm test` |
| End-to-end | **124/124** — `python scripts/e2e_test.py` (server must be up) |
| Attack probes | **41/41** — `python scripts/attack_probes.py` |
| Smoke checks | **57/57** — `python scripts/smoke_test.py` |
| Known CVEs | **0** — `pip-audit -r requirements.txt` |
| Migrations | **17**, head `c1e8a4b6d207`, run from empty to head on production |
| Working tree | clean |

**Data — the LOCAL database.** All test data was deleted before deploy. 4
accounts, 3 stores, 423 products, 455 prices, every one of them scraped.
Production got the catalogue only — no accounts (see [Production](#production)):

| | |
|---|---|
| Stores | iGeek Megastore 211 · SmartBuy 151 · AmmanCart 62 |
| Categories | phones 169 · monitors 135 · laptops 119 · **uncategorised 0** |
| Accounts | `salem-demo@example.com` (admin) + three of your own addresses |

**Language:** Arabic by default, English by toggle, RTL/LTR both. Search works
in Arabic. Nothing in the UI is English-only any more.

### ⚠️ The two things that are not ready, and neither is a code problem

1. **One product out of 423 has more than one price.** The site is a price
   comparison site that can currently compare one product (`iPhone 16 - 128GB`,
   two shops). This is what removing the invented prices left. It is honest,
   and it is the first thing anyone looking at the site will notice. The fix is
   **more real stores**, not more code.
2. **There are no merchants.** Every merchant store was a test and was deleted.
   The whole merchant half — contact buttons, tap analytics, used-phone
   disclosure — is fully built and tested but **invisible on the live site**
   until a real shop signs up. **The site is live now, so this is the next job,
   not a future one** — there is a real URL to send a shop.

---

## Production

**https://ahsanse3r.com** — deployed 2026-09-13. Everything below was verified
from outside the server, not assumed.

| | |
|---|---|
| Server | Hetzner **CX23** (2 vCPU x86, 4 GB), Falkenstein, Ubuntu 24.04, `2.28.103.13`, ~$7/mo |
| Code | `/opt/ahsan-se3r`, a git clone tracking **`main`**. Deployed and rebuilt at `e1ccbb5` on 2026-09-14 (search engines + brand icons), CI green first |
| Settings | `/opt/ahsan-se3r/deploy/.env` — mode `600`, root only. **Must be named exactly `.env`** (see traps) |
| Stack | `deploy/docker-compose.yml`: postgres, redis, one-shot `migrate`, api (serves the SPA too), worker, caddy |
| TLS | Caddy + Let's Encrypt, automatic renewal. `www` 301s to the bare domain |
| DNS | Cloudflare. `A @` and `A www` → server, **grey cloud / DNS only** |
| Firewall | Hetzner Cloud Firewall `web`: inbound TCP 22, 80, 443 and UDP 443 only |
| SSH | root, **key only**. Password auth off, verified refused |
| Email | Brevo SMTP relay, port 587 + STARTTLS. Domain authenticated: `brevo-code` TXT, two DKIM CNAMEs, DMARC `p=none` |
| Sign-in | Google, **published "In production"**. Apple not configured (needs a paid developer account) |
| Monitoring | Better Stack (free), every 3 min, email alerts. `/health` proves the app answers. The second monitor must be **`/health/catalogue`** ("URL becomes unavailable"): it touches Postgres and goes 503 when scraped prices have not been refreshed for 14 h, a day and a half before they would leave the site. It replaced `/products/483` contains `iPhone 16`, which now legitimately 404s whenever that product has no current offer. A deploy's rebuild can trip one alert |
| Account security | Two-factor login on Hetzner, Cloudflare, Brevo and Google (2026-09-14) |
| Admin | One admin: the operator's own account. Promoted by SQL, since nothing creates the first admin |
| Data | Catalogue imported: 3 stores, 423 products, 455 prices. **No accounts copied** |
| Backups | **OFF.** See Known limitations |

**Verified live:** HSTS with preload, CSP with no third-party origin and no
`unsafe-inline` scripts, TLS 1.0/1.1 refused, server header hidden, database /
cache / API ports unreachable from the internet, every SPA route survives a
hard refresh, fonts self-hosted with zero Google requests, the OAuth binding
cookie is `Secure; SameSite=None` in production, and an email sent through
Brevo landed in the Primary inbox, not spam.

### Operating it

Log in (the key is passphrase-protected; load it into the agent first):

```powershell
ssh-add $HOME\.ssh\id_ed25519
ssh root@2.28.103.13
```

Deploy a new commit:

```bash
cd /opt/ahsan-se3r && git pull && docker compose -f deploy/docker-compose.yml up -d --build
```

The frontend is baked into the image, so **any change — backend or frontend —
needs `--build`**. Caddy is not rebuilt, so it keeps its certificates.

Changed only `deploy/.env`? Recreate the two containers that read it:

```bash
docker compose -f deploy/docker-compose.yml up -d --force-recreate --no-deps api worker
```

**Stop the automatic scraping** (a retailer complains or blocks the bot): add
`SCRAPE_INTERVAL_HOURS=0` to `deploy/.env` and recreate the worker as above.
Never edit `docker-compose.yml` on the server -- the next `git pull` fails on
the local change. Job history: `/admin/scrape-jobs`, or
`docker compose -f deploy/docker-compose.yml logs worker`.
**Stopping it for more than ~2 days empties the site**: scraped prices not
re-read within 48 h stop being offers (see Current offers).

**Check every store link** (read the dry run before `--apply`; not while a
scrape runs):

```bash
docker compose -f deploy/docker-compose.yml exec worker python scripts/audit_store_links.py
docker compose -f deploy/docker-compose.yml exec worker python scripts/audit_store_links.py --apply
```

Status and logs:

```bash
docker compose -f deploy/docker-compose.yml ps
docker compose -f deploy/docker-compose.yml logs -f api
```

**Never `docker compose down -v`.** `-v` deletes the database volume *and*
`caddy_data`, which holds the certificates — Let's Encrypt allows five per
domain per week.

**Putting a secret on the server without it touching the screen, a chat or
shell history.** Paste the value at the prompt; `-s` hides it, and the `case`
refuses a double paste, which is easy to do when nothing appears:

```bash
cd /opt/ahsan-se3r/deploy
read -rsp "Secret (paste ONCE, Enter): " S && echo && case "$S" in *PREFIX*PREFIX*) echo "REFUSED: pasted twice" ;; PREFIX*) sed -i "s|^SETTING_NAME=.*|SETTING_NAME=$S|" .env && echo "SAVED: ${#S} chars" ;; *) echo "REFUSED: wrong value" ;; esac; unset S
```

Google secrets start `GOCSPX-`; Brevo SMTP keys start `xsmtpsib-` (an
`xkeysib-` key is an API key and will not authenticate SMTP).

Promote an account to admin (match id **and** email, so it cannot hit the
wrong row):

```bash
docker exec ahsan-se3r-postgres-1 psql -U ahsan -d price_comparison -c \
  "update users set role='admin' where id=<ID> and email='<EMAIL>' and role='user';"
```

---

## Environment traps (these cost real time)

1. **`uvicorn --reload` is unreliable here.** It logs "Reloading..." and does
   not restart. **Restart the backend manually after every backend edit.**
2. **Kill the old process first**, or the new one dies on "address already in
   use" and you silently keep testing old code:
   ```bash
   PID=$(netstat -ano | grep LISTENING | grep ":8000 " | awk '{print $5}' | head -1); taskkill //F //PID "$PID"
   ```
3. **Rate limiting is real** — 5 auth requests/min. Clear it:
   ```bash
   docker exec redis-local redis-cli FLUSHDB
   ```
4. **`| tail` swallows exit codes.** Capture it: `pytest -q > /tmp/o 2>&1; echo $?`
5. **Run pytest from `backend/`**, with `EMAIL_BACKEND=null`.
6. **Docker Desktop** needed `EnableDockerAI: false` in
   `%APPDATA%\Docker\settings-store.json`. Containers: `postgres-local`,
   `redis-local`.
7. **Windows console is cp1252.** Use `PYTHONIOENCODING=utf-8`. **curl mangles
   Arabic** on this shell — Arabic query strings arrive as `??????`. Test
   Arabic through Python/httpx, never through curl.
8. **Bash heredocs mangle regex backslashes.** `\b` became a literal backspace
   byte three separate times; `\r` in a Markdown path became a carriage return
   and produced `Dockerun`. **Write patch scripts to a file (Write tool)
   instead of `python - <<'EOF'` whenever backslashes are involved.**
9. **Vite caches a broken module graph.** After many edits the dev server
   serves stale modules — this cost an hour of "measuring" a bug that had
   already been fixed on disk. `rm -rf node_modules/.vite` and restart, or
   `preview_start` a fresh server. **When a browser measurement contradicts
   the source, suspect the dev server first.**
10. **Docker Desktop crashes on its own stale sockets.** It happened four times
    in one session. Two services do it — the Inference manager
    (`%LOCALAPPDATA%\Docker\run\dockerInference`) and the Secrets Engine
    (`%LOCALAPPDATA%\docker-secrets-engine\engine.sock`) — and clearing only one
    moves the crash to the other. The files are orphaned AF_UNIX reparse
    points: `Remove-Item`, `.NET Delete` and `del /f` all refuse them, but
    renaming the parent directory works. `EnableDockerAI` is already false and
    the Inference manager starts anyway; there is no setting for it in 4.78.

    ```powershell
    powershell -ExecutionPolicy Bypass -File scripts\repair-docker.ps1
    ```

    It clears both directories, restarts Docker Desktop, waits up to 8 minutes
    and starts the containers. It does **not** always work — twice the engine
    went into a deeper crash-loop that only a manual GUI start fixed.
11. **The browser pane reports `clientWidth: 0` when hidden**, which makes
    every `scrollWidth > clientWidth` overflow check trivially true. Set an
    explicit viewport with `resize_window` before believing any layout
    measurement.
12. **The browser pane's console buffer is sticky per tab.** It survives
    navigation, a dev-server restart and a cleared Vite cache, so a fixed
    error keeps being reported as though it were live — the message even
    keeps citing the *old* `?v=` dep hash, which is the tell. This is the
    mirror image of trap 9 and wastes time the same way: there, the browser
    was behind the source; here, only the log was. **Confirm against the DOM
    (`javascript_tool`) or a fresh tab before believing a console error**, and
    read the dep hash in the stack trace.
13. **Running commands on the server from this machine: use Windows'
    `ssh.exe` from Git Bash.** Git Bash's own `ssh` cannot see the Windows
    ssh-agent, so it prompts for the passphrase and hangs. PowerShell's `ssh`
    sees the agent but mangles quotes in a multi-line script. Windows' binary
    driven from Git Bash gets both right:
    ```bash
    /c/Windows/System32/OpenSSH/ssh.exe -o BatchMode=yes root@2.28.103.13 'bash -s' <<'EOF'
    ...
    EOF
    ```
    `BatchMode=yes` makes it fail immediately instead of hanging if the agent
    has lost the key. The agent service is disabled by default on Windows and
    enabling it needs an **Administrator** PowerShell.
14. **Give `ssh` exactly one stdin.** A pipe *and* a heredoc on the same
    command hung for five minutes with no output. Upload with a pipe alone,
    run with a heredoc alone, and wrap both in `timeout`.
15. **`| tail` swallowed an exit code again** — from the other direction.
    `cmd; echo "EXIT=$?"; tail log` captured pytest's code and then returned
    `tail`'s: a background task reported **exit 0 with 5 failures**. End with
    `exit $CODE` when the task's own status is what gets read.
16. **A test that passes proves nothing until it has failed.** Twice a test
    was written against a fix and only checked by switching the fix off: the
    login-CSRF binding (3 attack tests failed, 5 happy-path tests still
    passed) and the email escaping (4 failed, 2 unaffected). The split is the
    evidence. Checking by monkeypatching the fix away needs no file edits.
17. **The browser pane cannot screenshot while the app window is hidden** — it
    times out. `javascript_tool` and `read_page` still work; use them.
18. **Local Docker Desktop crashed again mid-deploy (trap 10).** Once the
    server existed, validation moved there instead — `caddy validate` ran in a
    container on the server. The server's Docker is the reliable one now.
19. **`curl` against the API is not a test of the site.** Every API call
    returned real data while the deployed page showed nothing, because the
    built bundle called `localhost:8000`. Only opening the page in a browser
    found it. The same outside-in page sweep then found `/merchant` returning
    a JSON 404 on refresh.

---

## How to run

```bash
docker start postgres-local redis-local
```
```bash
cd backend && .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-server-header
```
```bash
cd frontend && npm run dev
```
```bash
cd backend && .venv/Scripts/python.exe -m app.services.worker --loop
```

App at http://localhost:5173, API docs at http://localhost:8000/docs.

**Account:** a local demo account, `salem-demo@example.com` — **admin**,
deliberately unverified so the email banner shows. Its password is not written
here (this file is public). `scripts/e2e_test.py` signs in as this admin, so
its password must match the one that script uses. To set a new one locally, use
**Forgot password**: with `EMAIL_BACKEND=console` the reset link prints in the
backend terminal (redeeming it also marks the address verified). To make any
other local account an admin, register it and run
`docker exec postgres-local psql -U postgres -d price_comparison -c "update users set role='admin' where email='<EMAIL>';"`.
There is no merchant account any more;
register one through the UI to exercise that side, then delete it with
`scripts/cleanup_test_data.py --apply`.

Emails print to the **backend terminal** (`EMAIL_BACKEND=console`).

That is local development. For the live site, see
[Production → Operating it](#operating-it).

---

## Architecture — the parts that matter

### `app/matching/` — the engine

Six files, and **it imports nothing else from the app**. No database, no
config, no framework, and no third-party package either. That is why the same
parser runs at ingest and at query time, and why the whole scoring argument is
testable without a server.

- **`rules.py`** — categories as **DATA**. The only file to change for a new
  category. **Phones, laptops, monitors.**
- **`extractors.py`** — the only place regexes live.
- **`parser.py`** — generic, rules-driven.
- **`scorer.py`** — weighted scoring, brand gating, tiers, explanations.
- **`arabic.py`** — Arabic folded onto the English vocabulary (see below).
- **`spelling.py`** — typo correction against a closed vocabulary.

### Two matching problems, deliberately separated

| | Entity resolution (ingest) | Search relevance (query) |
|---|---|---|
| Question | Are these the same product? | Which products answer this query? |
| Output | Merge / don't — binary | Ranked tiers |
| Code | `services/deduplication.py` | `services/search.py` |

### Listings vs queries — the recurring principle

Two flags on `parse()`, both **on for ingest, off for search**:
`require_evidence` (a real laptop states storage or a processor; a bag states
neither) and `apply_defaults` (a *listing* called "iPhone 11" **is** the base
variant; a *query* means the shopper did not say).

### Scoring

A score starts at the category's **full weight** and loses only the weight of
attributes the shopper asked for and did not get. It deliberately does **not**
divide by how much the query mentioned.

Ladder: **100 exact / ≥85 close / ≥70 similar / below excluded**.
Phone weights: model 33, variant 28, storage 24, colour 10, memory 5.
Brand is a **gate** — a mismatch excludes outright.

When nothing clears 70, candidates are returned **unscored** in the lowest
tier rather than showing an empty page — a query naming only a brand
("iphone a16") has meaning and no score. Those render as "Name match", never
as "0% match".

### Arabic — `app/matching/arabic.py`

The engine stays **English-canonical**. An Arabic query is folded to the same
tokens a Latin one produces, so rules.py gains no Arabic column and the scorer
never learns there is a second language. A third language would be another
table here, not a rewrite.

Orthography is the hard part, not vocabulary: the same handset is written
ايفون / آيفون / أيفون, and capacities arrive as both `128` and `١٢٨`. Text is
**folded first** — digits unified, diacritics dropped, alef and ya families
collapsed — and the vocabulary is stored folded, so one entry covers every
spelling. The definite article `ال` is tolerated.

Folding lives in `normalize()`, the one point both ingest and query pass
through. Putting it in the search router would translate queries and not
listings, and a merchant typing Arabic would be invisible to Arabic search.

**Televisions are in the Arabic vocabulary on purpose.** `UNSUPPORTED_CATEGORIES`
is worthless if it only reads English — "تلفزيون سامسونج" would sail past it
into the phone rules, which is how TVs became phones once already.

### Spelling — `app/matching/spelling.py`

This does **not** contradict the scorer's rejection of string similarity.
"Which product does this query mean?" is the wrong job for edit distance;
"did they mean to type this word?" is exactly the right one.

Corrects tokens against a **closed vocabulary derived from rules.py at import
time**, so a brand added there is spell-checked for free. Separate Arabic and
English pools — script picks which. Guards, all load-bearing:

- **never correct a token containing a digit.** a15/a16 and s24/s23 are one
  edit apart and are different products.
- never correct on a tie **between different meanings** — but a tie between
  words meaning the same thing (شاشه / شاشات, both "monitor") is not a guess.
- the service accepts a correction only when it makes the query understood
  **more** — strictly more attributes extracted.
- the correction is always reported, and `?correct=false` searches the literal
  text.

### The store's classification is believed — including when it says no

**This is how accessories are kept out, and it is the subtlest thing here.**
An accessory names the product it fits: "IPHONE 15 PRO CASE" states a model
exactly as a handset does, and "Samsung microSD 256GB" states a capacity
exactly as one does. No tightening of `requires_any` separates them — every
piece of evidence a phone offers, a phone case offers too. A blocklist of
"case, cover, protector…" is the approach this project already rejected.

So `parse()` treats the store's `product_type` as authoritative in **both**
directions: it decides when it resolves, and it **refuses** when it resolves to
none of our categories. Previously the code consulted it and then guessed from
the title anyway — which is how a microwave oven, a Nintendo game, an SSD, a
motherboard and a refrigerator all became phones.

**The head noun decides.** A product_type is a LABEL, not prose: the last noun
says what the thing is and earlier words qualify it. A "Mobile Case" is a case;
a "Laptop Bag" is a bag. Scanning the whole label reads the qualifier as the
subject — three phone cases walked straight back in the moment "mobile" was
added as a category word. Trailing model numbers are dropped first, because
iGeek files real handsets under "iPhone 17".

`"Uncategorized"` is treated as **no statement**: it is the platform's own
filler for listings with no product_type, and believing it would let our
placeholder veto a real shop's phone.

Measured: 74 listings dropped, of which exactly **one** was a genuine handset
(a Samsung AmmanCart filed under "Connectivity").

**Residual:** a store supplying no product_type at all leaves only the title,
where an accessory naming a phone is genuinely indistinguishable. One row
survives on that basis.

### Merchants — `app/routers/merchant.py`

A shop registers, submits prices, and is contacted by phone or WhatsApp.
Listings reuse `ProductAlias` + `Price`, so search and dedup work unchanged.

**The access-control shape is the point.** Every route resolves the store from
`current_user`; there is deliberately **no `/merchant/stores/{id}/...` route
anywhere**, because an endpoint that cannot take a store id has nothing to
forget to check. Cross-tenant attempts return **404, not 403**.

**Unverified stores are filtered in the QUERY, not the template.**

Verification has **three** states, not two. `rejected_at` exists because
approve-or-ignore left fake claims in the pending queue forever, looking
exactly like ones nobody had reviewed. Declining does not delete — approving
clears the rejection, so a shop that later sends proof is not stuck.

### Contact taps — `app/models/contact_event.py`

There is no checkout, so a shopper tapping Call or WhatsApp is the **last thing
the platform can observe**. A merchant asked to pay will ask what they got for
it; this is the answer. Merchant dashboard and admin table read the same
figures from one query in `contact_stats.py`.

**It counts TAPS, and every label says so.** Whether the phone rang, was
answered, or led to a sale is not observable from a web page. Calling them
"calls" would inflate the one number a shop is billed against.

**No personal data**: a row is (shop, product, channel, when). No IP, no user
id, no session key — Jordan's PDPL covers exactly that, and counts do not
require identifying anybody. The cost is that duplicate taps cannot be
collapsed, which is another reason "taps" is the honest unit.

The endpoint always answers 202, including for unknown or unverified stores,
writing nothing — otherwise an anonymous endpoint taking a store id becomes a
way to enumerate which shops exist.

### Product photos — `app/services/images.py`, `photos.py`

**Every image on the site is new.** Before this, the frontend rendered no
`<img>` at all: 418 of 423 products already carried a scraped `image_url` and
not one was displayed. Rendering them is most of what changed visually.

**Merchant photos are per LISTING, not per product.** `Product.image_url` is
one scraped URL on the row every shop shares, which is right for a press shot
of a model and wrong for a merchant twice over: two shops selling the same
handset would compete for one column, and a merchant's photo is evidence about
ONE UNIT — the same reason battery health and damage live on the alias.

**Display order: scraped wins, then the oldest merchant photo, then a
placeholder.** Oldest is deliberate — the rule has to be deterministic, and it
must not reward re-uploading, or whose picture sits on a shared product
becomes something merchants compete over by spamming.

**The bytes are in Postgres**, in their own table. Same reasoning as the scrape
queue: object storage means a second service, a second set of credentials, a
bucket policy and a CORS rule to solve what is a few hundred rows here. A
re-encoded photo is 100–200KB, so a free 0.5GB database holds several
thousand. `photos.py` is the seam — the only module that touches the bytes —
so moving to R2 later is one file, not every caller. Its own table, not a
column on `product_aliases`, because every search query touches that table and
a bytea column gets dragged into any `SELECT *` that forgets to defer it.

#### The upload is re-encoded, never stored as sent

That single decision does most of the security work:

- **Polyglots die.** A file that is a valid JPEG *and* carries a script is
  still a valid JPEG — every header check passes it. Re-encoding writes a new
  file from a pixel buffer, so the passenger is not copied across. There is a
  test that builds exactly this file.
- **EXIF dies with it.** Shop photos are taken on phones and carry GPS, which
  is precisely the personal data this project stores nowhere else. Orientation
  is applied **before** the metadata is dropped — strip the rotation flag
  without acting on it and every portrait photo arrives on its side.
- **SVG is refused by name**, not decoded. It is a script container that
  executes on the origin serving it.
- **Decompression bombs are refused** at 50 megapixels. A 2MB PNG can decode
  to gigabytes; Pillow's own default only warns.
- **The declared Content-Type is never believed.** What the file is gets
  decided by decoding it.

Output is always WebP — roughly half the bytes of equivalent JPEG, which
matters when the budget is a free Postgres tier.

**A photo obeys the same visibility rule as a price**: an unverified shop's
photo is not served to shoppers, filtered in the query via
`Store.visible_to_shoppers()`. The shop can still see its own through the
authenticated route, or it could not tell a failed upload from a pending claim.

**Refusals carry a CODE, not a sentence** — `{code, message}` — and the client
writes the sentence. Same contract as the match explanations, for the same
reason.

**The merchant dashboard fetches its thumbnails as blobs**, not with an
`<img src>`. The access token lives in a module variable rather than a cookie,
so the browser cannot attach it to an image request it makes itself; an `<img>`
aimed at that route just 401s.

> **The trap that cost the most here:** `api/axios.js` sets
> `Content-Type: application/json` as an *instance default*, which overwrites
> the multipart boundary the browser needs to write. Every upload came back
> `file: Field required` and looked like a server bug. The interceptor now
> strips that header for `FormData` bodies, so the next upload endpoint cannot
> hit it.

### Condition — new and used never mix

A second-hand phone is not a cheaper new phone. New and used are tallied apart
everywhere a price is summarised. **Price alerts track new stock only.** Used
listings must disclose battery health and damage, and "no damage" must be
distinguishable from "the seller did not say".

### Services, split by concern

`search.py` used to be 487 lines covering three jobs. The callers gave it
away: the wishlist router and the alert notifier both imported
`price_summary()` from a module named "search".

- **`pricing.py`** — `price_summary`, `offers_for`. Arithmetic over money.
- **`deals.py`** — `best_savings`. The home page's savings query; nobody typed
  anything and nothing is scored.
- **`search.py`** — candidates, scoring, tiers. Relevance.

### Scrape queue — `app/services/jobs.py`, `worker.py`

`/admin/scrape` **enqueues a row**; a separate worker claims and runs it. The
claim is a conditional `UPDATE ... WHERE id=? AND status='queued'` — the
database decides, so two workers cannot both run one job. Portable on purpose:
no `SKIP LOCKED`, so SQLite tests exercise the production path. Stale jobs are
requeued; failures are written to the row, not just logged.

**The worker schedules itself** (added 2026-09-15): with
`SCRAPE_INTERVAL_HOURS` set -- `6` on the production worker in
`deploy/docker-compose.yml`, default `0` = off so a local worker never scrapes
by surprise -- each loop pass queues a full run if none is pending and the
last full run was queued that long ago (`jobs.enqueue_if_due`). Not a host
crontab (invisible to the repo, lost with the server) and not GitHub (cannot
reach Postgres). **A run isolates each store** (one down store, or one that
returns nothing, no longer fails the job), always bumps the catalogue version,
and sends price alerts only if every store refreshed -- capped at
`ALERT_EMAILS_PER_RUN` (100), each `notified_at` committed as its email goes
out. The alerts used to run only in the deleted GitHub scrape. **One full run
may be pending at a time**, enforced by a partial unique index (migration
`7d3b9e21c5a8`); a second admin "scrape all" gets 409. An admin's "scrape all"
is stored as empty `store_codes`, the same as a scheduled run, so it resets
the six-hour clock. Seeding a fresh database: stop the worker first
(`deploy/README.md`).

**Two timestamps on a price, on purpose.** `last_updated` = the price last
*changed* (sitemap lastmod, merchant staleness warning). `checked_at` = a
scraper last *read* it, changed or not (migration `9b4c2f7e1d63`); the product
page shows it for scraped stores. Without it the first production scrape left
"updated 19 days ago" beside prices it had just confirmed. Trap: setting
`checked_at` makes the row dirty and `onupdate=now()` would bump
`last_updated` too, so ingest re-sends `last_updated` unchanged
(`flag_modified`) when nothing visible changed.

**First production run, 2026-09-15 00:12 UTC:** succeeded in 7m22s --
SmartBuy 150 listings (18 price changes), iGeek 282 (10), AmmanCart 100 (1);
catalogue 423 -> 532 products, 455 -> 567 prices. Second run after
`checked_at` shipped: 0 price changes, **512 of 567 prices re-read**.

### Current offers and removed listings — fixed 2026-09-15

**The bug:** a listing a store removed simply stopped appearing in its feed and
kept its last price forever, winning "best price" beside a link to a 404 (iPhone
16 128GB at SmartBuy, `abj1501st0307`, 689 JOD). The per-store caps (150/400/100
kept variants) also cut off the OLDEST relevant listings, so they were never
re-read. Measured: SmartBuy 3,158 products (158 kept), iGeek 5,074 (284),
AmmanCart 5,431 (61 products / 110 variants); a full read is ~140 pages at 100
per page, about 5 minutes.

- **Complete reads.** `scrapers/base.py FeedRead`: a read is complete only if
  every target ended on an empty page. Any early stop (non-200 after retries,
  blocked/oversize page, bad JSON, robots, `MAX_PAGES`, `max_products` now 2000
  as a runaway guard) is logged and leaves it incomplete; `run_job` fails that
  store. Pages retry twice (5 s, 10 s) on 429/5xx/timeouts. `PAGE_SIZE` 100
  keeps pages ~1.4-1.6 MB under the 5 MB response cap.
- **Delisting** (`ingest.py _reconcile_listings`): only from a complete read that
  kept listings and where most listings ingested; only this store's scraped
  aliases; sets `ProductAlias.delisted_at` (migration `c1e8a4b6d207`), cleared when
  the listing reappears. **Safety valve:** one run may not delist more than
  `max(25, 25%)` of a store's *fresh* offers -- over that it delists only
  already-stale ones and records `delist_refused`, which fails the store. The
  feed's URL now overwrites a stale `store_product_url` (renamed handles).
- **One definition of an offer** (`app/services/offers.py current_offer()`):
  visible store AND not delisted AND (merchant store OR read within
  `SCRAPED_PRICE_MAX_AGE_HOURS`, 48). Applied to price_summary (search cards,
  best deal, wishlist, alerts), browse, deals, product detail (404 with no
  current offer), price history, sitemap; search candidates and suggestions only
  return products that have one (`pricing.has_current_offer`).
- **Alerts** go out only after a clean run of EVERY store (a one-store admin run
  sends none), and a product with no current offer no longer resets
  `notified_at` (it used to re-email the same drop).
- **Link audit** `scripts/audit_store_links.py`: GET `<url>.js` per current
  scraped link (hard 404 = gone), verdicts OK / RENAMED / GONE / VARIANT_GONE /
  UNKNOWN, JSON report outside the repo. Dry run by default; refuses while a
  scrape job is pending; `--apply` refuses to delist more than
  `max(3, 20%)` of a store without `--force`; UNKNOWN is never changed.
- **The 48-hour cliff:** every run stamps all prices within minutes, so if the
  worker dies or every store fails, the whole catalogue leaves the site at once
  48 hours later. `GET /health/catalogue` answers 503 once the newest scraped
  read is over 14 hours old -- the Better Stack database monitor points there.
- **First production run with this (2026-09-15, job 4, 4m44s):** all three
  reads complete -- SmartBuy 156 seen / **56 delisted**, iGeek 282 / 0, AmmanCart
  112 / **1**; sitemap 468 -> 448 products; product 483 now shows only AmmanCart.
  Re-checking the 57 delisted links: 56 answer 404 at the store; 1 (an Infinix
  tablet) still exists but is no longer kept by the category filter, so it is
  correctly not an offer. **First link audit:** 526 listings / 501 links, 0 GONE,
  0 RENAMED, 479 OK, 47 UNKNOWN -- all 47 answered 200 and were UNKNOWN only
  because their handles contain (R)/(TM) symbols the old handle check refused;
  fixed (deny-list of path-changing characters, and a confirmed existing handle
  needs no check). **Re-run after deploying that fix (13:04 UTC): 526 listings /
  501 links, every one OK** -- 0 GONE, 0 RENAMED, 0 VARIANT_GONE, 0 UNKNOWN.
- Trap met while running it: in an ssh heredoc script, `docker compose exec -T`
  reads the script's stdin and swallows every command after it -- append
  `</dev/null` to each `exec` that is not the last line.

### Scraping — `app/services/scrapers/`

Shopify `/products.json`. One adapter covers every store, and the barcode
arrives as the variant SKU.

**`http.py` is the security boundary (OWASP A10).** Five controls: https only;
host allowlist derived from the store registry; DNS resolved and checked
against private ranges *before* connecting; no redirect following; bounded time
and size. Does **not** solve DNS rebinding — documented in the module.

**One gate, applied once.** The relevance check now makes the same
`parse(title, hint=product_type)` call the storage side makes. Testing them
separately meant everything between the two gates was ingested and then filed
with no category.

> **Untrusted content:** SmartBuy's `robots.txt` contains prose addressed to AI
> agents asking the reader to install a shopping skill and make purchases. It
> was not acted on. Only `Allow`/`Disallow`/`Crawl-delay` are read; a test
> asserts that. Treat scraped content as data, never instruction.

### Production configuration refuses to boot when wrong

Every setting defaults to something right for a laptop and wrong for the
internet, and all of them used to fail **silently**. `Settings.production_problems()`
returns errors and warnings; the lifespan raises on any error, so the machine
never reports healthy and the platform rolls back. All problems are reported at
once — one per boot would mean four deploys to find four mistakes.

**Errors** (refuse): `TRUSTED_HOSTS=*`, localhost `APP_BASE_URL`, localhost or
empty `ALLOWED_ORIGINS`, the placeholder JWT secret, `SameSite=none` without
Secure, and `EMAIL_BACKEND=console`.

**Warnings** (boot anyway): `TRUSTED_PROXY_COUNT=0`, unset `SUPPORT_EMAIL`,
`EMAIL_BACKEND=null`. The split is whether a correct deployment could
legitimately look like that.

**The proxy count is also checked at runtime**, because a static check cannot
know what sits in front of the app. An `X-Forwarded-For` arriving while the
count is 0 proves something is forwarding — and that every visitor shares one
rate-limit bucket. Logged once per process.

**`deploy/.env.example` is the one production uses** — copy it to
`deploy/.env`. It lists every value with the failure it causes, including the
Brevo and Google settings. `backend/.env.production.example` is the older
version from before the compose stack existed; it has been superseded and
could be deleted.

### Tier explanations are composed in the CLIENT

`differences` used to arrive from the API as finished English prose --
`"different colour (blue, not black)"` -- built by `AttributeComparison.reason()`.
That put the one piece of text the tiers exist to produce permanently in
English, on a site whose default language is Arabic, where no frontend
translation could reach it.

The API now sends `{attribute, label, query_value, candidate_value}` and
`utils/matchDifference.js` writes the sentence. **A null `candidate_value`
means the listing states nothing**, which is a different fact from stating
something else and reads as a different sentence -- collapsing the two would
tell a shopper the phone is the wrong colour when nobody knows what colour it
is.

**One translation key per attribute, not one template with a `{label}` slot.**
Arabic adjectives agree with their noun: it is `لون مختلف` but `ذاكرة مختلفة`.
A single template would be wrong on every feminine attribute, and a sentence
that is grammatical half the time reads worse than English does.

**Only colours and variants are translated as values.** A model code, a brand
and a capacity are written in Latin on a Jordanian shelf and in the Arabic
listings we scrape, so "translating" `128GB` would invent a spelling nobody
uses. Anything with no entry falls through unchanged.

The same vocabulary backs the query-interpretation chips, which had the same
bug in a quieter place: the chip read `black` while the card under it read
`أسود`, and its tooltip named the attribute as the machine name `color`. Two
tests copy the colour, variant and attribute lists out of `rules.py` and fail
when the engine gains a value the table cannot say -- nothing else connects
Python vocabulary to a JavaScript table.

### i18n — `src/i18n/translations.js`

A plain lookup table, no dependency. Arabic is the **fallback locale**. Locale
and theme are applied in `index.html` **before React mounts**.

A test enforces key parity, identical `{placeholders}`, no empty strings, and
no untranslated English in the Arabic table.

### Search engines and the brand icon — added 2026-09-14

- **`/robots.txt` and `/sitemap.xml`** are real routes in `app/routers/seo.py`,
  registered before the SPA catch-all. They used to return `index.html` with
  200. The sitemap lists home, legal pages, non-empty categories and every
  product with an in-stock price from a `visible_to_shoppers()` store (same
  row), from `settings.app_base_url` -- never the Host header -- cached on the
  catalogue version. **robots.txt must never Disallow an API a public page
  fetches**: Googlebot renders the SPA and a blocked `/products` call renders
  an empty page. `test_seo.py` walks the frontend's real imports and asserts it.
- **A missing path that looks like a file** (`/x.png`, `/.env`) is a 404, not
  the app shell. A future client route with a dot in its last segment would
  404 on refresh.
- **Per-page `<title>`, description and `noindex`** via
  `src/hooks/useDocumentMeta.js`. noindex on every private page, on **all of
  `/results`** (a crafted `?q=` put arbitrary text in an indexable title),
  on unknown or empty `/browse/<x>` (the tab never echoes an unknown segment),
  and on a product that 404s or 422s. Values go in through `fillTemplate` /
  `t()`, both one-pass function replacers.
- **`GET /products/{id}` is a 404 when no visible store prices it.** It used
  to answer 200 with the name and an empty table, which published an
  unverified shop's own listing text on an indexable page.
- **`index.html`** carries both spellings in the title, Open Graph, and JSON-LD
  (`WebSite` + `Organization`, alternateName `أحسن سعر` / `Ahsan Se3r`). No
  static canonical (it would mark every route a duplicate of home) and no
  hreflang (both languages share URLs). JSON-LD is a data block, so
  `script-src 'self'` does not apply.
- **Icons** in `frontend/public/`: the header's price tag, white on brand green
  (`favicon.svg`, `.ico` 16/32/48, `apple-touch-icon.png`, `icon-192/512.png`
  for the manifest only -- they are full-bleed maskable squares and must not be
  `rel=icon`), `site.webmanifest`, and `og-image.png` rendered in headless
  Chrome with the self-hosted Cairo (Pillow on Windows has no raqm and breaks
  Arabic shaping). The generator scripts were not kept.
- **Link previews do not run JavaScript**, so every shared URL previews as the
  home page. Per-product previews need the server to write `og:*` into
  `index.html` per product.

---

## Decisions already made — don't redo these

- **PyJWT, not python-jose** — the latter is unmaintained with an unfixable
  advisory, and it signed every token.
- **Refresh token in an httpOnly cookie**, access token in a **module variable**.
- **Rotation with reuse detection** — rotation does not prevent theft, it makes
  theft *visible*.
- **Logout is authenticated.** It revokes every session the user holds, so the
  caller has to prove who they are; the cookie identifies a session, not a
  person.
- **Money is `Numeric(10,3)`** — JOD has three decimals. Convert via
  `Decimal(str(x))`, never `Decimal(float)`.
- **Attributes stored as JSON** — adding a category needs no migration.
- **Patterns, not enumerations** — the chip list said m1–m4 and an M5 was
  already in the catalogue.
- **Browse collapses COLOUR VARIANTS into one tile.** Measured: 151 phones are
  73 distinct handsets, and a 24-tile page was showing 14 — four Honor X5c,
  three Infinix Smart 20. The family key is attributes **plus the name's
  leading segment, used only when the model did not parse**. Both halves are
  load-bearing: attributes alone merged an Infinix Tab XPAD *tablet* into a
  Smart 20 phone (both parse to `infinix/None/base/128gb/4gb`), and the name
  alone split "VIVO Y02 Orchid Blue" from "VIVO Y02 Cosmic Grey" because
  neither has a comma. The colour is never stripped from the name — Honor
  writes "Tidal Blue" and "Midnight Black", so removing the colour word leaves
  "Tidal" and "Midnight". **`category_counts`, `total_in` and `browse` all
  count families**, or the tile promises a number the page cannot reach.
- **A CATEGORY IS NOT A QUERY.** The home page's category tiles link to
  `/browse/:category`, not to `/results?q=Phones`. They shipped doing the
  latter once: a text search for the word "Phones" matches no product, so a
  tile advertising 151 products led to "Nothing matched that search", and the
  Laptops tile returned a single monitor whose title contains "for Laptops".
  Search answers "which products match these words"; browse answers "show me
  what you filed under this" — no query, no scoring, no tiers. `Browse.jsx` is
  its own page for that reason. A test asserts the tiles never route through
  `/results` or carry a `q=`, because the broken version rendered perfectly
  and only failed when clicked.
- **Pagination is per tier** — paging a flattened list would push the exact
  match to page two.
- **Password reset is a LINK, never a mailed password.** Resetting revokes
  every session.
- **Merchant listing moderation is a separate admin route**, not an `if admin`
  branch inside the merchant route.
- **Two admin guards:** nobody changes their own role; the last admin cannot be
  demoted.
- **Televisions are not carried.** `UNSUPPORTED_CATEGORIES` is one word per
  out-of-scope category — a closed set, not a growing blocklist.
- **Cache invalidation is global** (one version counter). Correct and cheap at
  three shops.
- **Light mode is a TOKEN SYSTEM, not literal hexes.** Every colour that
  differs between themes is served through a CSS custom property; `:root`
  holds the light values and `html.dark` restores today's byte-identical dark
  ones. This is not decoration: almost every gray rung is used by both modes
  (gray-900 is 56 light text uses against 38 `dark:bg-` uses), so a literal
  override of the scale would have repainted dark mode. Two rules:
  **channel triplets, never hex** — `<alpha-value>` needs three numbers, and a
  hex makes every `/60`, `/30`, `/20` utility render transparent without
  erroring — and **`html.dark`, never `.dark`**, because `:root` is also
  specificity (0,1,0), so with `.dark` the firewall would depend on source
  order. Every colour added to `:root` needs an entry in both blocks.
- **Nothing in light mode is pure white.** The old palette put the page at
  #F9FAFB and cards at #FFFFFF — 1.05:1, below the threshold at which the eye
  accepts two regions as separate surfaces — so the screen was one flat field
  at maximum luminance with 17.74:1 near-black text on it. Measured, then
  fixed at both ends: ceiling 17.74 → 10.6:1, muted floor 2.54 → 5.5:1 (it
  FAILED WCAG before), page-to-card step 1.78 → 4.96 L*. The three photo
  letterboxes keep pure white via a `photo` token — they back product shots,
  and an off-white panel behind a white photo shows a seam.
- **Chart series colours are CATEGORICAL and selected per theme.** They encode
  identity — which shop — not rank, so hues are assigned in fixed order and
  never cycled: a shop keeps its colour when a filter removes the series above
  it. The dark column is the same five hues re-stepped for a dark ground, not
  a flip, because a hue clearing 3:1 on `#F8FAFC` does not on `#111827`. The
  light column is the reference palette stepped DOWN until every slot cleared
  3:1 — three of five failed at their published values. Validated with a
  script (lightness band, chroma floor, adjacent CVD separation, contrast),
  not eyeballed. Class names are written out in full in `PriceHistoryChart`
  because Tailwind extracts by scanning source: `stroke-series-${i}` generates
  nothing and every line renders strokeless.
- **Dark mode is fixed in `@layer base`, not per component.** Tailwind's
  preflight sets `color: inherit` on form controls, so in dark mode they
  inherited near-white text on a white background — 29 of 30 fields at 1.05:1
  contrast. Per-component classes would need remembering on every new field,
  which is exactly how it happened. `color-scheme: dark` is set too: it is what
  makes the caret, spinners, scrollbars and Chrome's autofill follow the theme.
- **Tap targets are 44px** across the shopper flow (Apple HIG; Material says
  48). Inline links inside a sentence are exempt — WCAG 2.5.8 says so, and
  blocking them out breaks the line.

### Deployment and auth — decided 2026-09-13

- **One origin.** The API serves the built SPA (`app/frontend.py`). The refresh
  token is an httpOnly cookie; across two registrable domains it becomes
  third-party and Safari blocks it, logging every iPhone user out on refresh.
- **The API owns what is BELOW a prefix, not the prefix itself.** `/merchant`
  and `/admin` are both an API prefix and a React page; the bare path serves the
  app. This shipped wrong and 404'd the merchant dashboard on refresh.
- **Production builds call the API same-origin** (`resolveApiBaseUrl` in
  `src/utils/constants.js`). The fallback used to be `localhost:8000`
  unconditionally, and nothing sets `VITE_API_URL` in the image.
- **No inline scripts.** Production CSP is `script-src 'self'`. The theme
  script lives in `public/theme-init.js`. A CSP hash was rejected: it breaks
  silently the first time someone edits a comment in the script.
- **Cairo is self-hosted.** It is a variable font — three files, 81 KB, not
  fifteen. `/fonts` caches a week and revalidates; not `immutable`, because the
  filenames are hand-written, not content-hashed.
- **Social sign-in is a server-side redirect, not an SDK.** No Google or Apple
  script ever loads, so the CSP stays `'self'`. Providers are config-gated:
  no credentials, no button.
- **The OAuth state is bound to the browser** with an httpOnly
  `oauth_binding` cookie. A server-side state alone proves the sign-in is ours,
  not whose it is — login CSRF worked against a healthy Redis. The cookie is
  `SameSite=None; Secure` because Apple's callback is a cross-site POST, which
  carries no Lax cookie.
- **Identity is keyed on the provider subject, never the email.** Linking a
  provider to an unverified local account clears that account's password and
  revokes its sessions: that password was set by someone who never proved they
  own the mailbox.
- **Email addresses are normalised at the schema boundary**
  (`EmailField` in `schemas/auth.py`). Registration was case-sensitive while
  linking was not, so one mailbox could hold two rows and eviction missed one.
- **Deleting an account retires a merchant's shop rather than deleting it.**
  Listings and price history are catalogue data. The retirement name carries a
  random suffix, because `stores.name` is unique and store ids are public — a
  predictable name let anyone veto a merchant's erasure.
- **Support-message addresses are replaced with a random value on deletion**,
  not a keyed HMAC. An HMAC under the app's own signing key is recoverable by
  anyone holding the key, which is not erasure.
- **Every dynamic value in email HTML is escaped** at the point of output.
  Product and store names come from merchants and scrapers; unescaped, the
  platform would deliver phishing DKIM-signed as its own domain.
- **Password-reset links expire in 1 hour**, confirmation links in 24. Brevo
  rewrites every link for click tracking and cannot turn it off below its
  Enterprise plan, so a copy of each link exists in Brevo's systems.
- **No cookie consent banner.** The only cookies are strictly necessary (the
  refresh token and the ten-minute OAuth binding). There is no analytics,
  pixel or session recording. The privacy policy explains this instead.
- **The Hetzner Cloud Firewall, not `ufw`.** Docker writes its own iptables
  rules that bypass `ufw`, so a port believed blocked can be open.
- **Cloudflare proxy OFF (grey cloud).** On: Caddy's certificate challenge
  becomes fragile, and every visitor arrives from Cloudflare's addresses — with
  `TRUSTED_PROXY_COUNT=1` they would all share one login rate limit. Turning it
  on later means `TRUSTED_PROXY_COUNT=2` and SSL mode Full (strict).
- **Hex, not base64, for the database password.** It is embedded in
  `DATABASE_URL`, where a base64 `/` is read as the start of the path.
- **The settings file is `deploy/.env`, named exactly that.** Compose's
  `env_file:` feeds containers, but `${VAR}` substitution in the compose file
  reads only a file called `.env`. Named `.env.production`, Postgres got a blank
  password and Caddy a blank domain.

---

## Tried and rejected — do not repeat

- **Scraping production from GitHub Actions (`scrape.yml`, deleted
  2026-09-14).** It needed the production `DATABASE_URL` in GitHub secrets and
  Postgres reachable from the internet; the server's firewall allows only
  22/80/443, and opening 5432 to feed a cron is the wrong trade. It had never
  run, and on `main` it would have failed every six hours on the missing
  secret. It also pasted a dispatch input straight into a `python -c` string.
- **CI filling its catalogue by scraping real stores.** CI's smoke step called
  `python -m app.services.scraper`, deleted with the dead pipeline, so **CI
  failed on every push from the first one until 2026-09-14** -- unit tests and
  migrations passed, the smoke step died on import, and the image build and
  dependency audit after it never ran. It now seeds a fixed, invented
  catalogue (`scripts/seed_ci_catalogue.py`); scraping for real would load
  real retailers' sites on every push and make the result depend on their
  stock. **Behind that was a second fault:** `alembic downgrade base` left
  the `userrole` enum type in Postgres, so the next `upgrade head` died on
  "type userrole already exists". "Migrations reverse cleanly" passed because
  a downgrade that leaves debris still exits 0; that step now goes down and
  back up. Only a downgrade path -- production never runs one.

- **UptimeRobot's free plan.** Its terms have restricted the free plan to
  personal, non-commercial use since late 2024, with suspension as the penalty.
  This is a business site. Better Stack's free plan is used instead.

- **Facebook scraping.** Their `robots.txt` prohibits automated collection,
  Meta litigates, and Jordan's PDPL No. 24 of 2023 covers the contact details.
  **The route in is the shop's permission, not Facebook's.**
- **OCR from store photos.** Mixed Arabic/English, decorative fonts, and
  storage/colour usually absent from the image. A wrong price is worse than a
  missing one.
- **A second real store via Playwright** — unnecessary. `smartbuy.jo` is
  SmartBuy's own second domain; `leaders.jo` 403s an identified bot;
  `citycenter.jo`, `jordantechnomall.com`, `os-jo.com`, `action.jo` are not
  Shopify; `ammanhardware.com` is Shopify but sells plumbing.
- **`beautifulsoup4` / `lxml`** — removed; the JSON feed needs neither.
- **Celery / RQ for the queue** — a broker and a second deployable to solve
  what one table solves at a handful of jobs a day.
- **Requiring both model AND storage to keep accessories out** — measured: it
  would have lost 84 real phones and kept 3 accessories. The store's own
  classification is the signal that works.
- **A native mobile app.** Measured at 375px: the web app is already
  mobile-first — no horizontal overflow, price table scrolls in its own
  container, RTL correct, all tap targets ≥44px. Distribution is the killer:
  discovery is Google, Instagram and word of mouth, all of which are *links*,
  and an app inserts an install step at the moment of purchase intent. The one
  real argument for an app is **push notifications for price alerts** — and a
  **PWA** delivers that from the existing codebase with no app store. Ladder:
  deploy → PWA → Web Push if alerts prove out → native only with retention
  data.
- **A load balancer.** Measured: 260–350 req/s for search on one worker on
  this laptop, with everything else running. 1000 visits/day is ~0.1 req/s —
  roughly 200× headroom. The thing that will actually take the site down is
  `TRUSTED_PROXY_COUNT`, not capacity.
- **Fly + Neon + Upstash.** The earlier plan. A single Hetzner VPS running the
  whole compose stack is cheaper, has one origin by construction, and has no
  managed-service free tier to expire underneath it.
- **Oracle Cloud's Always Free tier.** Free and large on paper; in practice
  capacity errors creating Arm instances, payment-verification suspensions, and
  reclaimed idle instances. Wrong for a site shown to shop owners.
- **Hetzner CAX11 (Arm).** Recommended, then sold out in the region. CX23
  (x86) was cheaper anyway, and nothing in the stack is architecture-specific.
- **Disabling Brevo click tracking.** Not possible on its plan — Brevo staff
  say "for security reasons", Enterprise only. Mitigated instead (short reset
  links, anonymous tracking, disclosure). A provider that allows tracking off,
  such as Resend, needs only SMTP settings and DNS records — no code.
- **Brevo's automatic Cloudflare authentication.** It asks for permission to
  edit all of the domain's DNS to add four records. Added by hand instead.

---

## Known limitations

1. **No backups.** Hetzner backups are off and nothing dumps the database. A
   lost disk, a mistaken command or a lapsed payment loses every account and
   every merchant listing. The biggest operational gap by far. **The owner
   decided on 2026-09-14 to enable them once there are customers and stores**,
   while the data is test accounts and a re-scrapable catalogue. Enable them
   before the first real shop signs up, not after.
2. **One product has more than one price.** See the warning at the top.
3. **No merchants at all.** See the warning at the top.
4. **Prices are refreshed every ~6 hours, not live** -- when a store's run
   succeeds. A scraped price not re-read for 48 h stops being shown at all. A store that blocks the bot or is down keeps its last prices
   until it answers again; the job row says `FAILED <store>` and **price
   alerts are held back for the whole run**, so nobody is emailed about a
   figure that was not re-checked. A store that fails every run therefore
   blocks alerts until it is fixed or removed from the registry. A deploy
   during a run requeues it (SIGTERM handler) and it restarts from the first
   store.
5. **Brevo rewrites every link** in outgoing email for click tracking and it
   cannot be switched off on this plan. Mitigated: reset links last 1 hour,
   anonymous tracking, disclosed in the privacy policy.
6. **Emails are English only** while the site is Arabic by default. A shopper
   who registers in Arabic gets an English confirmation.
7. **DMARC is `p=none`** — report only. Forged mail from the domain is not yet
   rejected. Tighten once Brevo's reports show real mail passing.
8. **Apple's Hide My Email forks one person into two accounts.** No shared
   verified identifier exists to join them safely; anything weaker would be a
   takeover path. Needs an authenticated "link another sign-in" feature.
9. **Deleting an account does not revoke the grant at Google.** Disclosed in
   the privacy policy rather than adding a network call that can fail midway
   through a deletion.
10. `Core 5-120U` parses, but **CPU generation is not captured** — an 8th-gen
    and a 14th-gen i7 both resolve to `i7`.
11. **Merchant photos are served from the API's own origin.** Re-encoding is
    the control that matters and it is in place; a separate origin is the
    defence in depth that is not.
12. **Merchant photos are not moderated.** Nothing stops a verified shop
    uploading something irrelevant.
13. **`smoke_test.py` and `attack_probes.py` leave their fixtures behind.**
    Running them re-pollutes the database. **Never point them at
    production.** `scripts/e2e_test.py` cleans up after itself; the other two
    do not. Run `scripts/cleanup_test_data.py --apply` afterwards, locally.
14. No email verification enforcement on *access* — gates outbound mail only
    (deliberate).
15. **The name is shared.** `ahsansaer.com` is a Palestinian price-comparison
    site called "أحسن سعر", Jordanian Facebook shops use "احسن سعر", and the
    phrase is generic ("best price"). The brand query that is realistically
    ownable is "Ahsan Se3r" / "ahsanse3r". Check trademark position in Jordan
    before spending on the name.
16. **Unknown dot-free paths (`/some-missing-page`) are soft 404s**: the server
    cannot tell them from client routes. The page sets noindex.

---

## Scripts

| | |
|---|---|
| `scripts/e2e_test.py` | 124 checks, real server, limiter ON, cleans up after itself |
| `scripts/attack_probes.py` | 41 active attack probes |
| `scripts/smoke_test.py` | 57 critical-path checks |
| `scripts/seed_ci_catalogue.py` | Invented 4-listing catalogue for CI's smoke test. **Refuses production** |
| `scripts/cleanup_test_data.py` | Deletes test accounts/stores. **Whitelist**, not blocklist — refuses to run if no admin would survive |
| `scripts/audit_store_links.py` | Checks every current store link still leads to the product (GET `.js`). Dry run by default; `--apply` delists GONE, relinks RENAMED, never touches UNKNOWN |
| `scripts/prune_unparseable_products.py` | Re-parses every product with current rules, deletes what they reject. Run after any `rules.py` change |
| `scripts/backfill_attributes.py` | Recomputes `match_category`/`match_attributes`. **Run after any rules change** — ingest never re-parses existing rows, so a rules improvement only reaches new listings |
| `../scripts/repair-docker.ps1` | Recovers Docker from the stale-socket crash |

---

## Next steps, in the order I would do them

### 1. Make the live site survivable

Deployment is done (see [Production](#production)). What is not done is the
part that matters the day something goes wrong:

- **Turn on backups** -- deferred by the owner until the first real shop
  signs up (see Known limitations). Hetzner server page → Backups → **Enable** (~$1.30/mo,
  daily, seven kept). Then add an **off-server** copy: a nightly `pg_dump` sent
  somewhere outside Hetzner. Hetzner's backups live in the same account as the
  server, so they do not survive losing the account.
- **`ssh-add -D`** on the laptop when not deploying, so the key goes back
  behind its passphrase. (Uptime monitoring, Brevo anonymous tracking and
  two-factor login are done, 2026-09-14.)
- **Image updates.** Ubuntu security updates apply automatically
  (`unattended-upgrades` is on); the Postgres, Redis and Caddy images do not.
  Pull and rebuild monthly.
- **Delete the `frontend` branch** on GitHub when convenient. Nothing uses it:
  the laptop and the server both track `main` (2026-09-14).

Later: tighten DMARC to `p=quarantine` once reports look clean; bilingual
emails; Apple sign-in if anyone asks for it ($99/yr, config only).

### 1b. Get found

Code side done 2026-09-14 (see Search engines and the brand icon). **Google
Search Console: domain property `ahsanse3r.com` verified 2026-09-14** through
Cloudflare's one-time authorization -- **never delete the
`google-site-verification` TXT record at the apex**, or ownership lapses.
Sitemap submitted the same day; "Couldn't fetch" on day one is Google's delay
for new properties (the file was checked as Googlebot: 200, application/xml,
371 URLs, valid lastmods). Home page indexing requested; Google's live test
rendered the full page on a phone (products, prices, no console errors; 1 of
21 resources failed, unidentified, harmless to the render). **Bing Webmaster
Tools**: property imported from Search Console and sitemap submitted
2026-09-15 (it imports from whichever Google account owns the property --
the first attempt picked the other account and found nothing). Still to do:
confirm both sitemaps read Success. Later: IndexNow (Bing supports it) so
price changes are pushed instead of waiting for a crawl. Social
profiles named "احسن سعر | Ahsan Se3r" linking to the site, and links from
shops once they join.

### 2. Get real supply

This is now the product's binding constraint, not the code. Two paths, and
they compound:

- **More scraped stores.** Every additional Shopify store in Jordan directly
  attacks the "one comparable product" problem.
- **Message the shops.** Jado 0791757546 · Flick +962 7 8608 0010 · Platinum
  (needs identifying). WhatsApp gets answered, email mostly doesn't. You could
  not do this before deploying; now you can.

### 3. Instrument what the taps tell you

The counting is built. Once shops are on, the pitch becomes *"you got 47 calls
last month, it's 10 JOD"*, which sells itself. **Make the free tier permanent**
rather than a two-month trial — an expiring trial shrinks supply, and supply is
the weakness. Sell unlimited listings, analytics and a verified badge instead.
**Avoid paid placement**: if a paying shop outranks a cheaper one, the
comparison is a lie, and that is the only thing being sold. Invoice by hand for
the first 50 shops.

### 4. Smaller, well-defined work

- **Split `Admin.jsx`** — 631 lines, now the largest file in the project. Same
  treatment the admin router got: stats, stores, listings, users.
- **Capture CPU generation** — needs a weight rebalance in `rules.py`.
- **PWA** — manifest, icons, service worker. Installable, and the honest
  version of "make a mobile app".
- **Serve photos from a separate origin.** Built, but they come from the
  API's own origin today. Re-encoding is the real control and it is in place;
  origin isolation is the defence in depth that is still missing, along with
  `Content-Security-Policy` on the app itself.
- **Moderate merchant photos.** Nothing stops a verified shop uploading
  something irrelevant. Listings already have a separate admin moderation
  route; photos should join it before the shop count gets past the point where
  you would notice by looking.

---

## Working style that produced good results

- **Drive the real UI against real data.** Almost every bug this session was
  invisible to the test suites: CORS blocking every merchant edit while 480
  tests passed, dark mode making 29 of 30 fields unreadable, "0% match" on
  every card. Green tests and a broken screen coexist happily.
- **Measure before claiming.** The accessory fix was designed from a
  measurement that killed the obvious approach (requiring model AND storage
  would have lost 84 real phones). The load-balancer question was answered with
  a load test. The mobile-app question was answered by driving the site at
  375px.
- **Verify the environment before believing a measurement.** An hour went into
  "finding" a tap-target bug that was already fixed on disk — Vite was serving
  stale modules. When a browser reading contradicts the source, suspect the
  server.
- **Attack your own server.** `scripts/attack_probes.py` — 41 probes.
- **Prefer rules over blocklists.** The head-noun rule is grammar, not a word
  list, so it covers labels nobody has seen yet.
- **Make a wrong configuration refuse to start.** Silent misconfiguration is
  the worst failure mode there is: it passes every health check.
- **Say what is not done.** The two warnings at the top of this file are more
  useful than anything else in it.
- **Deploy by running it, not by reading it.** The production stack was
  written carefully and still held seven bugs, every one invisible until the
  thing ran for real: a settings file compose half-ignored, a base64 password
  breaking a URL, no certificate for `www`, health checks that could never
  pass, a bundle calling `localhost`, a CSP-blocked inline script, and a
  merchant dashboard that 404'd on refresh.
- **Adversarial review earns its keep.** A four-lens audit with two skeptics
  per finding found a login-CSRF hole the module's own comments claimed to
  prevent. The test that "covered" it drove both halves through one client, so
  it could not see the bug.
- **Verify from outside.** Port probes told a firewall-blocked port (timeout)
  from an allowed one (refused); DNS checks against two public resolvers; every
  page requested by path. The server's own view is not the visitor's.
