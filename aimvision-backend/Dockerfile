FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

RUN pip install --no-cache-dir uv==0.5.4

WORKDIR /build
COPY pyproject.toml ./
COPY README.md ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

RUN uv venv /opt/venv && \
    . /opt/venv/bin/activate && \
    uv pip install -e .

# ---- runtime ----
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN useradd --system --uid 1001 --create-home --home-dir /home/aimvision aimvision

COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --from=builder /build/app ./app
COPY --from=builder /build/alembic ./alembic
COPY --from=builder /build/alembic.ini ./alembic.ini
COPY scripts/boot.sh ./boot.sh
RUN chmod +x ./boot.sh

USER aimvision

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys,os; port=os.environ.get('PORT','8000'); \
sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=3).status==200 else 1)"

# `boot.sh` translates Railway / Heroku / Fly's $DATABASE_URL → asyncpg
# shape, runs `alembic upgrade head`, then execs uvicorn bound to $PORT.
# Dev's docker-compose overrides this command with its own.
CMD ["./boot.sh"]
