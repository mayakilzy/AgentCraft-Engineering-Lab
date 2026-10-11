# AgentCraft Engineering Lab — Backend image.
# Pinned to Python 3.12 slim. Non-root user, minimal layers.

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps: libpq5 for psycopg2-binary runtime; curl for healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first (better layer caching).
COPY backend/pyproject.toml backend/alembic.ini ./backend/
COPY backend/alembic ./backend/alembic
COPY backend/app ./backend/app

RUN pip install --no-compile --no-cache-dir \
    "fastapi==0.128.0" \
    "uvicorn[standard]>=0.30.0" \
    "pydantic>=2.9.0" \
    "pydantic-settings==2.7.1" \
    "SQLAlchemy==2.0.36" \
    "alembic==1.14.1" \
    "psycopg2-binary==2.9.10" \
    "asyncpg==0.30.0" \
    "httpx==0.28.1"

# Non-root user.
RUN useradd --create-home --uid 1000 ac && \
    mkdir -p /app && chown -R ac:ac /app
USER ac
WORKDIR /app/backend

ENV PYTHONPATH=/app/backend

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD curl -fsS http://localhost:8000/api/v1/health/live || exit 1

# Run migrations then start the API. Compose overrides if needed.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
