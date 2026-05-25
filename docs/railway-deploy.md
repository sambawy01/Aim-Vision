# Deploying the AIMVISION backend to Railway

Staging-grade deploy for testing the mobile + web clients against a real
URL (no Mac-on-LAN dependency). This is **not** the federation on-prem
GA path per [ADR-0012](adr/0012-on-prem-first-ga.md); that's the Helm
chart in workstream H. Railway is for staging, design-partner demos,
and the cloud-tier Solo/Club rollout that follows GA.

## What gets deployed

- One Railway **service** running the FastAPI backend image
  (`aimvision-backend/Dockerfile`).
- One Railway **Postgres add-on** the service connects to via
  `DATABASE_URL` (Railway-injected).
- `boot.sh` runs `alembic upgrade head` on every cold start, then
  hands off to uvicorn bound to Railway's `$PORT`.

## Prereqs

- Railway account + Railway CLI (`brew install railwayapp/tap/railway`).
- Repo cloned locally with the working tree clean for the
  `aimvision-backend/` directory.

## One-time setup

```bash
# Authenticate (opens browser).
railway login

# Create a new Railway project. Pick a name like "aimvision-staging".
cd aimvision-backend
railway init

# Attach a managed Postgres add-on. Railway injects DATABASE_URL,
# PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE into the service
# environment automatically.
railway add --plugin postgresql
```

## Required environment variables

Set with `railway variables --set KEY=value` or via the Railway dashboard.

| Variable | Why | How to generate |
|---|---|---|
| `AIMVISION_ENV` | Drives env-conditional code paths (cookie `Secure`, log format) | `railway variables --set AIMVISION_ENV=staging` |
| `AIMVISION_JWT_SECRET` | Signs AIMVISION-side session tokens | `openssl rand -base64 48 \| tr -d '+/=\n' \| head -c 64` |
| `AIMVISION_DATA_ENCRYPTION_KEK` | Wraps per-tenant DEKs ([right-to-erasure](compliance/right-to-erasure-architecture.md)) | `openssl rand -base64 48 \| tr -d '+/=\n' \| head -c 64` |
| `AIMVISION_IP_HASH_SALT` | Salt for audit-log IP hashing | `openssl rand -hex 32` |
| `AIMVISION_CORS_ORIGINS` | JSON list (pydantic-settings v2 parses as JSON) | `'["https://your-web.up.railway.app"]'` — set after the web is deployed; omit for mobile-only |

Optional, only when flipping on the GoTrue identity-provider path ([ADR-0010](adr/0010-identity-provider-supabase.md)):

| Variable | Why |
|---|---|
| `AIMVISION_AUTH_PROVIDER=gotrue` | Enable the `/auth/exchange` route |
| `AIMVISION_GOTRUE_ISSUER` | GoTrue's `iss` claim |
| `AIMVISION_GOTRUE_JWT_SECRET` | HS256 shared secret with the GoTrue process |
| `AIMVISION_GOTRUE_AUDIENCE` | Default `authenticated`; override only if you changed it |

Railway-injected (do not set yourself):

- `DATABASE_URL` — `boot.sh` translates `postgresql://…` →
  `postgresql+asyncpg://…` and exports as `AIMVISION_DATABASE_URL`.
- `PORT` — uvicorn binds to this.

## Deploy

```bash
railway up                # build + deploy current working tree
railway logs              # follow logs as `boot.sh` migrates + starts
railway open              # open the service URL in your browser
```

A clean cold start prints:

```
[boot] AIMVISION backend starting
[boot]   env       = staging
[boot]   database  = postgresql+asyncpg://postgres:<redacted>@<redacted>
[boot]   port      = 8080
[boot] running alembic upgrade head
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 0001_federation, ...
INFO  [alembic.runtime.migration] Running upgrade 0014_erasure -> 0015_users_gotrue_sub, ...
[boot] handing off to uvicorn
INFO:     Uvicorn running on http://0.0.0.0:8080
```

## Seed staging data

```bash
# Run the local seed script against the Railway database. `railway run`
# injects the project's env vars into the local process.
railway run --service aimvision-backend bash -c \
  'export AIMVISION_DATABASE_URL="${DATABASE_URL/postgresql:/postgresql+asyncpg:}"; \
   .venv/bin/python -m scripts.seed_dev'
```

Outputs the demo coach login (`coach@example.com` / `demopassword123`).

## Verify

```bash
URL=$(railway domain --service aimvision-backend)
curl -fsS "https://$URL/health"
curl -fsS "https://$URL/version"
curl -fsS -X POST "https://$URL/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"email":"coach@example.com","password":"demopassword123"}' | jq
```

Last command returns the `LoginOut` shape (access token + principal +
memberships) → the deploy is healthy end-to-end.

## Point the mobile app at the deployed URL

In `aimvision-mobile/.env`:

```bash
API_BASE_URL=https://<your-railway-domain>
APP_ENV=staging
```

Then `pnpm ios --device "<UDID>"` (physical device) or `pnpm ios`
(simulator). The app now talks to Railway, not your Mac.

## Cost

Railway's free tier covers ~$5/mo of usage. AIMVISION backend's
idle footprint (one Postgres connection pool, no background workers)
is small; expect ≤$3/mo at staging traffic levels. Postgres add-on
adds ~$5/mo for the smallest instance.

## Not in this deploy

- **No GoTrue container.** `AUTH_PROVIDER` stays at `stub` until the
  web + mobile clients are cut over per [ADR-0010](adr/0010-identity-provider-supabase.md).
- **No Temporal worker.** Post-session orchestration runs in-process on
  the API service for now; the `arq` worker and Temporal split
  (per [ADR-0007](adr/0007-temporal-orchestration.md)) come with the
  Helm chart.
- **No ML pipeline.** Audio/pose/diagnostic models are not invoked from
  this service; the smoke covers auth + tenancy + CRUD only.
- **No MinIO / S3 object storage.** Recording uploads go to local
  ephemeral storage on the Railway container (resets on redeploy).
  Wire object storage before any production-tier rollout.
