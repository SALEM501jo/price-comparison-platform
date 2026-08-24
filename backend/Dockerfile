# Multi-stage: wheels are built with a compiler present, then copied into a
# runtime image that has none. psycopg2 and bcrypt need to compile; shipping
# gcc in the final image would add weight and attack surface for no benefit.

FROM python:3.12-slim AS builder

# Build-only dependencies. libpq-dev is needed to compile psycopg2.
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt


FROM python:3.12-slim

# libpq5 is the runtime half of libpq-dev: psycopg2 links against it, but the
# headers and compiler are not needed once the wheel exists.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

# Run as a non-root user. A container process running as root that is
# compromised is root inside the container, and closer to root outside it than
# anyone wants.
RUN useradd --create-home --shell /bin/bash app

WORKDIR /app

COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

COPY --chown=app:app . .

USER app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

# The platform's own health check may be enough; this makes the container
# self-describing regardless of where it runs.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# --no-server-header: the Server header cannot be removed from middleware,
# because uvicorn writes it at the ASGI protocol level after middleware has
# already returned. It has to be suppressed here.
#
# --forwarded-allow-ips is deliberately NOT set: this app resolves the client
# address itself from TRUSTED_PROXY_COUNT, and letting uvicorn rewrite
# request.client as well would mean two layers disagreeing about who the
# caller is.
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--no-server-header", "--proxy-headers"]
