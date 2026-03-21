# ---- Base with uv + Python ----
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# Copy the entire project code into the container
COPY . /app

# Install dependencies with uv
RUN uv sync --frozen --no-dev

# Optional: if you keep .env for local dev only, don't bake secrets into image
# Ensure you have a .dockerignore that excludes .env, .venv, notebooks, etc.

EXPOSE 8000

# Uvicorn entrypoint
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
