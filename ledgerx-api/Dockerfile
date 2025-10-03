# ---- Base with uv + Python ----
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# ---- Dependency resolution layer (cacheable) ----
FROM base AS deps
# Only copy files that affect deps to maximize cache hits
COPY pyproject.toml uv.lock* ./
# Create venv with production deps only
RUN uv sync --frozen --no-dev

# ---- Runtime image ----
FROM base AS runtime
# Non-root user
RUN useradd -m -u 10001 appuser
WORKDIR /app

# Bring in the virtualenv from deps stage
COPY --from=deps /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH="/app"

# Copy the application code last (better layer caching)
COPY . .

# Optional: if you keep .env for local dev only, don't bake secrets into image
# Ensure you have a .dockerignore that excludes .env, .venv, notebooks, etc.

EXPOSE 8000

# Basic healthcheck (adjust route if you have a /health)
HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD \
  wget -qO- http://localhost:8000/docs >/dev/null || exit 1

# Uvicorn entrypoint
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
