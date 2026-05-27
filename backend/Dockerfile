# syntax=docker/dockerfile:1
FROM python:3.13-slim

# uv binary from the official image.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Install dependencies first (cached unless the lockfile changes).
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev

# App code + committed fixtures.
COPY app ./app
COPY data ./data

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
