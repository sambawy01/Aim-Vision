# aimvision-backend

The AIMVISION control-plane backend. **Python 3.12 + FastAPI + SQLAlchemy 2.0 + Pydantic v2 + Alembic + Arq + Uvicorn** per [ADR-0001](../docs/adr/0001-backend-python-fastapi.md).

Multi-tenancy is enforced by Postgres Row-Level Security keyed on `app.current_principal`, with an application-layer scope filter as defense-in-depth (see [ADR-0004](../docs/adr/0004-multi-tenancy-rls.md) and [`docs/security/multi-tenant-isolation.md`](../docs/security/multi-tenant-isolation.md)). Audit events are append-only and hash-chained per tenant per [`docs/security/audit-logging-spec.md`](../docs/security/audit-logging-spec.md).

## Quick start

```bash
# install (uv preferred, pip works too)
uv sync                              # or: python -m venv .venv && .venv/bin/pip install -e '.[dev]'

# migrate
export AIMVISION_DATABASE_URL=postgresql+asyncpg://aimvision:aimvision@localhost:5432/aimvision
uv run alembic upgrade head

# run
uv run uvicorn app.main:app --reload

# tests
uv run pytest -v
```

The default test DB is in-memory SQLite. RLS-enforcement tests are gated behind a real Postgres URL:

```bash
AIMVISION_TEST_POSTGRES_URL=postgresql+asyncpg://aimvision:aimvision@localhost:5432/aimvision_test \
  uv run pytest -m postgres -v
```

## Endpoints

| Path             | Purpose                                         |
| ---------------- | ----------------------------------------------- |
| `GET /health`    | Liveness                                        |
| `GET /version`   | Build identity (version + git SHA + env)        |
| `GET /openapi.json` | OpenAPI 3 schema (drives frontend codegen)   |
| `POST /auth/signup` | Create account + user + solo tenant          |
| `POST /auth/login`  | Issue stub JWT (Sprint 1; PASETO at Sprint 4) |
| `POST /consent/grant` / `POST /consent/revoke` | GDPR Art. 7/9 |
| `GET /sessions` / `GET /sessions/{id}`         | Tenant-scoped reads          |

## Layout

See `pyproject.toml` for tool configuration (`ruff`, `mypy --strict`, `pytest-asyncio`).

```
app/
  main.py        FastAPI factory, lifespan, middleware wiring
  config.py      Pydantic Settings
  db.py          async engines + tenant_session(...) RLS context
  deps.py        FastAPI dependencies
  models/        SQLAlchemy models (tenancy, consent, session, annotation, audit)
  schemas/       Pydantic v2 DTOs
  routers/       HTTP endpoints
  services/      auth (JWT), audit (hash chain), tenancy (principal helpers)
  middleware/    tenant_context, audit emission

alembic/versions/
  0001_federation_first_schema.py   accounts/users/orgs/memberships/sessions/...
  0002_audit_log.py                 audit_events + role grants
  0003_rls_policies.py              ENABLE/FORCE RLS + tenant_iso policies
```
