FROM python:3.12-slim AS base

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev --no-install-project 2>/dev/null || uv sync --no-dev --no-install-project

COPY app ./app
RUN uv sync --no-dev

ENV PORT=8080
EXPOSE 8080

CMD uv run uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
