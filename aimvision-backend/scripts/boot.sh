#!/usr/bin/env sh
# Container entrypoint for AIMVISION backend.
#
# Translates platform-injected DATABASE_URL (Railway, Heroku, Fly) into
# the asyncpg-shaped AIMVISION_DATABASE_URL the app expects, runs
# `alembic upgrade head`, then execs uvicorn bound to $PORT.
#
# Dev (docker-compose.dev.yml) has its own command and skips this file.

set -eu

# Railway / Heroku / Fly inject DATABASE_URL=postgresql://user:pw@host:port/db.
# AIMVISION runtime uses asyncpg; alembic env.py translates to psycopg for
# sync migrations. Both paths are derived from one canonical URL here so
# operators only set one env var.
if [ -n "${DATABASE_URL:-}" ] && [ -z "${AIMVISION_DATABASE_URL:-}" ]; then
  # postgres:// (legacy) and postgresql:// → postgresql+asyncpg://
  asyncpg_url=$(printf '%s' "$DATABASE_URL" \
    | sed -e 's|^postgres://|postgresql+asyncpg://|' \
      -e 's|^postgresql://|postgresql+asyncpg://|')
  export AIMVISION_DATABASE_URL="$asyncpg_url"
fi

# Audit log shares the same database by default. Override with
# AIMVISION_AUDIT_DATABASE_URL if the audit chain needs a separate
# logical or physical database.
if [ -z "${AIMVISION_AUDIT_DATABASE_URL:-}" ]; then
  export AIMVISION_AUDIT_DATABASE_URL="${AIMVISION_DATABASE_URL:-}"
fi

# Platforms inject the port to bind to (Railway sets PORT). Default
# matches the Dockerfile EXPOSE for local docker run.
PORT="${PORT:-8000}"

echo "[boot] AIMVISION backend starting"
echo "[boot]   env       = ${AIMVISION_ENV:-development}"
echo "[boot]   database  = ${AIMVISION_DATABASE_URL%%@*}@<redacted>"
echo "[boot]   port      = ${PORT}"

# Migrations are mandatory on boot: a deployed image must always finish
# at the schema HEAD before serving traffic. Fail-loud if alembic
# crashes (set -e takes care of the exit).
echo "[boot] running alembic upgrade head"
alembic upgrade head

echo "[boot] handing off to uvicorn"
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
