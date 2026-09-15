# Deploying احسن سعر

One server, one domain, one command. The API serves the built SPA from its own
origin, so there is no second static host and no CORS to configure.

## Before you start

**A server.** 2 vCPU / 4 GB is comfortable; 2 GB works. Postgres, Redis, the
API, the worker and Caddy all fit. Ubuntu 24.04 with Docker installed.

**A domain pointing at it.** An `A` record for `ahsanse3r.com` (and `www` if you
want it) resolving to the server's IP, *before* you start the stack. Caddy
proves control of the domain over port 80 to get a certificate; if DNS has not
propagated the challenge fails and you get no HTTPS.

**Ports 80 and 443 open.** Nothing else needs to be. Postgres and Redis are
deliberately not published — they are reachable only from inside the compose
network.

## First deploy

```bash
git clone <your remote> ahsan-se3r && cd ahsan-se3r
cp deploy/.env.example deploy/.env
```

Fill in `deploy/.env`. **It must be named exactly `.env`** — see the note at
the top of `docker-compose.yml`; any other name silently blanks the database
password and the domain.

Generate the two secrets rather than inventing them:

```bash
openssl rand -hex 32   # JWT_SECRET_KEY
openssl rand -hex 32   # POSTGRES_PASSWORD — paste into DATABASE_URL too
```

**Hex for the database password, not base64.** It goes inside
`postgresql://ahsan:PASSWORD@postgres:5432/...`, and base64 can contain `/`, `+`
and `=` — a `/` there is read as the start of the URL path, so the app cannot
reach its own database. It fails for some generated passwords and not others,
which is the hardest way to diagnose it.

Then:

```bash
docker compose -f deploy/docker-compose.yml up -d --build
```

The first build takes a few minutes — it compiles Python wheels and runs a Vite
build. `migrate` runs `alembic upgrade head` and must exit 0 before the API
starts, so a broken migration stops the deploy rather than starting an app
against a schema it does not match.

## Check it actually worked

```bash
docker compose -f deploy/docker-compose.yml ps          # all healthy
curl -fsS https://YOUR_DOMAIN/health                    # {"status":"ok"}
curl -fsS https://YOUR_DOMAIN/auth/providers            # which buttons render
curl -sI https://YOUR_DOMAIN | grep -i content-security # CSP present
```

Open the site. Check the wordmark renders in Cairo rather than a fallback (that
proves the self-hosted fonts are being served), and that `/privacy` no longer
shows the amber "This page is not finished" panel.

**If the app refuses to start, read the log — that is the feature.** Several
settings default to something correct for a laptop and wrong for the internet,
and each fails silently, so the app checks them at boot and refuses rather than
coming up misconfigured and passing a health check. The message names the
variable and says what breaks.

## Updating

```bash
git pull
docker compose -f deploy/docker-compose.yml up -d --build
```

Rolling back is `git checkout <previous tag>` and the same command. The image
carries the SPA, so the frontend and backend can never be a version apart.

## Backups — not automated, and you need this

Nothing here backs the database up. Postgres holds every account, every
merchant listing and every uploaded photo.

```bash
docker compose -f deploy/docker-compose.yml exec -T postgres \
  pg_dump -U ahsan price_comparison | gzip > backup-$(date +%F).sql.gz
```

Put that in cron and copy the result off the server. A backup on the same disk
is not a backup.

**Never `docker compose down -v`.** The `-v` destroys the volumes: the database
*and* `caddy_data`, which holds your certificates. Let's Encrypt allows five
per domain per week, so a couple of careless cycles lock the site out of HTTPS
for days.

## Roughly what it costs

| | |
|---|---|
| Hetzner CX23 (2 vCPU x86, 4 GB) + IPv4 | ~$7/month |
| Domain | ~€10–15/year |
| TLS certificate | free (Let's Encrypt, automatic) |
| Sign in with Google | free |
| Sign in with Apple | **USD 99/year** — Apple Developer Program |

Apple is the only real cost decision. Leave `APPLE_*` blank and that button
simply does not render; `/auth/providers` advertises only what is credentialed,
so the site ships complete on Google alone.

## Email — Brevo

`EMAIL_BACKEND=console` is refused in production: it logs messages and sends
nothing, so verification links never arrive and signups silently never
complete. The settings are pre-filled for Brevo in `.env.example`;
you supply the SMTP login and key.

**The credentials are not your Brevo login.** In Brevo go to **SMTP & API →
SMTP**. It shows a dedicated SMTP username and lets you generate a key. Using
your account email and password instead fails authentication, and the symptom
is "the email never arrived" rather than an error.

**Authenticate the domain before you rely on it.** Brevo gives you DKIM and
SPF records to add at Cloudflare (as **DNS only**, grey cloud). A brand-new
domain sending without them goes to spam at Gmail, and because every account
here is confirmed by an emailed link, that means **signups fail silently** —
the user sees a normal "check your email" screen and nothing ever comes. This
is the single most likely way a working deploy still looks broken.

Check it end to end after deploying: register with a real address and confirm
the link arrives in the inbox, not spam.

## Seeding the catalogue

**A fresh database is empty**, and a price-comparison site with no prices is
not something to show a merchant. Export the catalogue from a working
instance — tables only, no accounts:

```bash
for t in stores products product_aliases prices price_history; do
  docker exec postgres-local pg_dump -U postgres -d price_comparison \
    --data-only --no-owner --no-privileges -t "$t"
done > catalogue-seed.sql
```

One table per call, in that order, deliberately: `pg_dump -t a -t b` emits
tables in its own internal order rather than the order of the flags, so a
single call can write `prices` before the `product_aliases` they reference and
the restore dies on a foreign key.

Never dump the whole database. It contains user accounts — including any demo
account with a known password — and restoring those to a public server
publishes them.

Load it after the stack is up and `migrate` has run, **with the worker
stopped**. On an empty database the worker queues a full scrape within seconds
of starting, and the stores and products that scrape writes collide with the
seed's ids and store names -- `ON_ERROR_STOP` then aborts the whole restore:

```bash
scp catalogue-seed.sql root@YOUR_SERVER:/tmp/
docker compose -f deploy/docker-compose.yml stop worker
docker compose -f deploy/docker-compose.yml exec -T postgres \
  psql -U ahsan -d price_comparison --set ON_ERROR_STOP=1 < /tmp/catalogue-seed.sql
docker compose -f deploy/docker-compose.yml start worker
```

The sequences travel with the data, so the first merchant listing does not
collide with an existing id.

A seed shows NO scraped prices if they were last read more than 48 hours
before it is loaded (`SCRAPED_PRICE_MAX_AGE_HOURS`): an offer nobody has
re-checked is not shown as current. That is expected -- starting the worker
queues a full scrape at once, and the prices appear when it finishes (about
five minutes).

## What this does not do

- **No continuous deployment.** GitHub Actions (`.github/workflows/ci.yml`)
  tests every push, but deploying is still the manual `git pull` and
  `docker compose up -d --build` above.
- **No log aggregation.** `docker compose logs -f api` is the whole story.
- **No second replica.** One API container. Fine at this size; the stack is
  shaped so adding one is a `--scale`, because migrations are a separate
  one-shot rather than part of the API's startup.
- **No automatic backups.** See above. This is the gap most likely to hurt.
