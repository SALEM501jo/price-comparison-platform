# The production image: the API and the built SPA in one artefact.
#
# WHY THEY SHIP TOGETHER. app/frontend.py serves frontend/dist from the API's
# own origin, because the refresh token is an httpOnly cookie and splitting the
# app across registrable domains makes it third-party -- which Safari blocks by
# default, silently logging every iPhone user out on each page refresh. One
# origin removes that whole class of problem, and it means one image, one
# certificate and one thing to roll back.
#
# BUILD CONTEXT IS THE REPO ROOT, not backend/, because this needs both halves.
# Build with:  docker compose -f deploy/docker-compose.yml build

# --- 1. The SPA -------------------------------------------------------------
FROM node:22-slim AS web

WORKDIR /web

# package files alone first: this layer is what gets cached, and it only
# invalidates when a dependency actually changes rather than on every source
# edit.
COPY frontend/package.json frontend/package-lock.json ./
# `npm ci`, not `npm install`: it installs exactly the lockfile and fails if
# the two disagree, so a deploy cannot quietly pick up a different dependency
# tree from the one the tests ran against.
RUN npm ci

COPY frontend/ ./
RUN npm run build


# --- 2. Python wheels -------------------------------------------------------
FROM python:3.12-slim AS wheels

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY backend/requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt


# --- 3. Runtime -------------------------------------------------------------
FROM python:3.12-slim

# libpq5 is the runtime half of libpq-dev; curl is for the health check. The
# compiler stays in the build stage -- shipping gcc would add weight and attack
# surface to a container that never compiles anything.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash app

WORKDIR /app

COPY --from=wheels /wheels /wheels
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

COPY --chown=app:app backend/ /app/

# THE PATH IS NOT ARBITRARY. app/frontend.py resolves dist as
# <this file>/../../../frontend/dist -- from /app/app/frontend.py that is
# /frontend/dist. Put the build anywhere else and the API serves the JSON API
# only, with every page route 404ing, and nothing in the logs explains why.
COPY --from=web --chown=app:app /web/dist /frontend/dist

USER app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# --no-server-header: uvicorn writes the Server header at the ASGI protocol
# level, after middleware has returned, so it cannot be removed anywhere else.
#
# --proxy-headers lets uvicorn read X-Forwarded-Proto so the app knows the
# request arrived over TLS. --forwarded-allow-ips is deliberately NOT set: the
# app resolves the client address itself from TRUSTED_PROXY_COUNT, and two
# layers rewriting request.client would disagree about who the caller is.
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--no-server-header", "--proxy-headers"]
