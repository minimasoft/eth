FROM python:3.11-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src/ /app/src/
RUN uv sync --frozen --no-dev

FROM python:3.11-slim
COPY --from=builder /bin/uv /bin/uvx /bin/
COPY --from=builder /app /app
COPY scripts/ /app/scripts/
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
CMD ["uv", "run", "python", "scripts/run_api.py"]