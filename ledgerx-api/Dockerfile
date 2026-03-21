FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# copy only dependency file first
COPY requirements.txt /app/requirements.txt

RUN uv venv /app/.venv
RUN uv pip install --python /app/.venv/bin/python -r /app/requirements.txt

# now copy app source
COPY . /app

EXPOSE 8000

CMD ["/app/.venv/bin/uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]