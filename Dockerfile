FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md alembic.ini ./
COPY *.py ./
COPY api ./api
COPY tools ./tools
COPY prompts ./prompts
COPY infra ./infra
COPY migrations ./migrations

RUN uv sync --frozen --no-dev --no-install-project

EXPOSE 8200

CMD ["/app/.venv/bin/uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8200"]
