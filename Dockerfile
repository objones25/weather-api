# syntax=docker/dockerfile:1

# ── Stage 1: install dependencies ────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:0.6-python3.13-bookworm-slim AS builder

WORKDIR /app

# Enable bytecode compilation and link mode for faster startup and smaller layers
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Install dependencies first (cached unless pyproject.toml / uv.lock changes)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,id=s/00186f69-74f6-4121-92aa-bb2f5b815b71-/root/.cache/uv,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Copy source and install the project itself
COPY . .
RUN --mount=type=cache,id=s/00186f69-74f6-4121-92aa-bb2f5b815b71-/root/.cache/uv,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ── Stage 2: runtime image ────────────────────────────────────────────────────
FROM python:3.13-slim AS runtime

WORKDIR /app

RUN mkdir -p /data

# Copy the virtual environment, source, and migration files from the builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/app /app/app
COPY --from=builder /app/alembic /app/alembic
COPY --from=builder /app/alembic.ini /app/alembic.ini

# Prepend venv to PATH so `python` and `fastapi` resolve without activation
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

# /metrics is unauthenticated — suitable for an internal liveness probe.
# --start-period gives the app time to run migrations before checks begin.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/metrics')" || exit 1

CMD ["sh", "-c", "alembic upgrade head && fastapi run app/main.py --host 0.0.0.0 --port 8000"]
