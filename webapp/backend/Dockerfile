# =============================================================================
# Backend — multi-stage Docker image
#
# Build context: monorepo root (caries-seg/).
# This lets us COPY src/ (ML model definitions) into the image alongside
# the webapp/backend/ application code.
#
# Stage 1 (builder): resolve and install all Python deps with uv into a
#   project-local .venv, using bind-mount cache so layer invalidation only
#   happens when pyproject.toml / uv.lock change.
# Stage 2 (runtime): copy only the .venv + application code.
#
# To install inference extras in Phase 3, pass --extra inference to uv sync
# in the final RUN command below.
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1 — builder
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

# Pull in the official uv binary from Astral's image (avoids pip overhead).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Do not download a managed Python — use the image's system Python.
    UV_PYTHON_DOWNLOADS=0 \
    # Copy files instead of hard-linking so the cache mount and the
    # target venv can live on different filesystems.
    UV_LINK_MODE=copy

# System packages needed to compile asyncpg's C-extension.
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# All uv commands run from /app so the .venv lands at /app/.venv.
WORKDIR /app

# ------------------------------------------------------------------
# Layer A — install dependencies only (no project source code yet).
#
# pyproject.toml and uv.lock are bind-mounted for this step so they
# do not become a separate COPY layer.  This layer is only rebuilt
# when the lockfile changes, not on every code edit.
# ------------------------------------------------------------------
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=webapp/backend/pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=webapp/backend/uv.lock,target=uv.lock \
    uv sync --frozen --extra inference --no-install-project --no-dev --no-editable

# ------------------------------------------------------------------
# Layer B — copy application code and install the project itself.
# ------------------------------------------------------------------
# ML model definitions shared from the monorepo src/ package.
COPY src/ ./src/

# Backend application code (includes pyproject.toml and uv.lock).
COPY webapp/backend/ ./

# Install the project in non-editable mode so the .venv is
# self-contained and can be copied to the runtime stage.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --extra inference --no-dev --no-editable

# ---------------------------------------------------------------------------
# Stage 2 — runtime image
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Put the venv's bin directory first so uvicorn / python resolve from it.
    PATH="/app/.venv/bin:$PATH"

# Minimal runtime libraries for asyncpg's libpq dependency.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgl1 \
    libpq5 \
    libxcb1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the entire /app tree from builder (includes .venv, src/, app/ etc.).
COPY --from=builder /app /app

EXPOSE 8000

# Apply schema migrations on container start so a fresh Compose database has
# the tables required by the lifespan startup queries before uvicorn boots.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
