# Local GoTrue ↔ AIMVISION dev stack

Stand up the full identity loop ([ADR-0010](adr/0010-identity-provider-supabase.md))
on one machine: Postgres + Supabase Auth (GoTrue) + the AIMVISION FastAPI
backend, configured to verify GoTrue-issued JWTs through `/auth/exchange`.

This stack is the bench the web + mobile clients point at when they
wire the GoTrue cutover. It's also the working reference for the Helm
chart change that lands in workstream H — service env vars, secret
sharing, and database layout map across one-to-one.

## What you get

```
┌─────────────┐    JWT (HS256)   ┌─────────────┐
│ GoTrue      │ ────────────────►│ AIMVISION   │
│ :9999       │                  │ backend     │
│ Supabase    │                  │ :8000       │
│ Auth v2     │                  │             │
└──────┬──────┘                  └──────┬──────┘
       │ shared JWT secret              │
       │ (signs vs. verifies)           │
       │                                │
       ▼                                ▼
   Postgres `gotrue` DB         Postgres `aimvision` DB
                ▲                        ▲
                └──── one cluster, two databases (port 5433)
```

Both services share a single Postgres cluster, two databases. Backend has
`AUTH_PROVIDER=gotrue` and the same `GOTRUE_JWT_SECRET` as the GoTrue
service, so it verifies the JWTs GoTrue issues.

## Prereqs

- Docker Desktop running (`docker info` succeeds).
- `curl`, `jq`, `psql` on the host (the smoke script's only host-side
  dependencies — Postgres client is bundled with `postgresql-client`
  on Linux or installed via `brew install libpq && brew link --force
libpq` on macOS).

## Up

From `aimvision-backend/`:

```bash
docker compose -f docker-compose.dev.yml up -d --build
docker compose -f docker-compose.dev.yml ps    # all three healthy?
```

First boot takes ~60 seconds: Postgres init + GoTrue migrations +
backend `alembic upgrade head` + first uvicorn boot.

## Smoke

The end-to-end smoke validates the full path a real client takes
(signup → login → exchange):

```bash
./scripts/smoke_gotrue_exchange.sh
```

What it does, top-to-bottom:

1. Waits for GoTrue + backend `/health` to be live.
2. `POST /signup` to GoTrue → returns the new user's UUID (`sub`).
3. `POST /token?grant_type=password` to GoTrue → returns an
   HS256-signed JWT.
4. Inserts an AIMVISION `users` row with `gotrue_sub` set to the
   UUID from step 2. In production this is the bulk-import script
   from ADR-0010 "Migration"; here it's a single SQL statement.
5. `POST /auth/exchange` to the AIMVISION backend with the GoTrue
   JWT in the body.
6. Asserts the response is the `LoginOut` shape (access token,
   principal, memberships) and that `principal.user_id` matches the
   provisioned AIMVISION user.

Successful output ends with:

```
[smoke] OK — GoTrue → AIMVISION /auth/exchange loop is healthy.
[smoke]   user_id     = smoke-1716559104-12345
[smoke]   gotrue_sub  = 8e7c95f2-...
[smoke]   tenant_id   = solo:smoke-1716559104-12345
```

The smoke is idempotent (each run generates a fresh email +
user-id suffix) — you don't need `docker compose down -v` between
runs to re-test.

## Down

```bash
docker compose -f docker-compose.dev.yml down       # keep data volume
docker compose -f docker-compose.dev.yml down -v    # nuke Postgres volume
```

## Iterating on the backend

The backend image rebuilds on `docker compose up --build`. For a
hot-reload loop during backend development, run the backend
_natively_ against the compose's Postgres + GoTrue:

```bash
# Terminal 1: keep Postgres + GoTrue up, but skip the backend service.
docker compose -f docker-compose.dev.yml up -d postgres gotrue

# Terminal 2: run the backend natively against them.
cd aimvision-backend
export AIMVISION_DATABASE_URL='postgresql+asyncpg://aimvision:aimvision-dev-only@localhost:5433/aimvision'
export AIMVISION_AUTH_PROVIDER=gotrue
export AIMVISION_GOTRUE_JWT_ALG=HS256
export AIMVISION_GOTRUE_JWT_SECRET=aimvision-dev-gotrue-jwt-secret-32bytes-plus
export AIMVISION_GOTRUE_ISSUER=http://localhost:9999
export AIMVISION_GOTRUE_AUDIENCE=authenticated
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --port 8000
```

The smoke script's `BACKEND_URL` defaults to `http://localhost:8000`,
so the same `./scripts/smoke_gotrue_exchange.sh` works against this
hot-reload backend.

## What this is _not_

- **Not production-shaped.** Real deployments use RS256 (asymmetric)
  with a key fetched from GoTrue's JWKS endpoint; dev uses HS256 with
  a shared symmetric secret. The verifier supports both; the Helm
  chart change in workstream H will flip the deployed mode to RS256.
- **Not the migration path for existing PBKDF2 users.** That's the
  bulk-import script described in ADR-0010 "Migration", landing in
  a separate PR.
- **Not the only auth surface.** The legacy `/auth/login` PBKDF2
  endpoint is still live in this dev stack (just dormant — clients
  call `/auth/exchange` once `AUTH_PROVIDER=gotrue`). It gets removed
  in a cleanup PR after both client cutovers.

## Troubleshooting

| Symptom                                                                | Fix                                                                                                                                                                       |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `docker compose up` hangs on `pulling gotrue`                          | First pull only; the image is ~50 MB.                                                                                                                                     |
| `smoke_gotrue_exchange.sh: ... GoTrue signup did not return a user id` | `docker compose logs gotrue` — usually the `GOTRUE_DB_DATABASE_URL` is wrong or the `gotrue` database wasn't created. `down -v` and retry.                                |
| `psql: connection refused`                                             | The smoke script targets the host-mapped port `5433`, not the in-container `5432`. Update `PG_PORT` env if you map differently.                                           |
| Backend container restart-loops on `alembic upgrade head`              | Pre-existing migration-chain bug (0003_rls_policies revision id) tracked separately. Workaround: comment out the alembic step and use `Base.metadata.create_all` for dev. |
