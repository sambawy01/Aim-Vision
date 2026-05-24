#!/usr/bin/env bash
# End-to-end smoke for the GoTrue ↔ AIMVISION identity loop (ADR-0010).
#
# Walks the full path a real client takes:
#   1. Sign up a user in GoTrue (POST /signup).
#   2. Log them in (POST /token?grant_type=password) to get a JWT.
#   3. Provision a matching AIMVISION users row (gotrue_sub = the GoTrue
#      user id) via psql. In production this is the bulk-import script
#      from ADR-0010 Migration; today it's a single SQL statement.
#   4. POST the GoTrue JWT to AIMVISION /auth/exchange.
#   5. Assert HTTP 200 + a LoginOut shape (access_token + principal +
#      memberships).
#
# Run after `docker compose -f docker-compose.dev.yml up -d` is
# healthy. Exits non-zero on any assertion failure.

set -euo pipefail

GOTRUE_URL="${GOTRUE_URL:-http://localhost:9999}"
BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
PG_HOST="${PG_HOST:-localhost}"
PG_PORT="${PG_PORT:-5433}"
PG_USER="${PG_USER:-aimvision}"
PG_PASSWORD="${PG_PASSWORD:-aimvision-dev-only}"
PG_DB="${PG_DB:-aimvision}"

# Random suffix so the script is rerunnable without `docker compose down -v`.
SUFFIX="$(date +%s)-$$"
EMAIL="smoke+${SUFFIX}@aimvision.test"
PASSWORD="SmokeTest-${SUFFIX}-Passw0rd!"

log() { printf '\033[36m[smoke]\033[0m %s\n' "$*"; }
fail() {
  printf '\033[31m[smoke] FAIL:\033[0m %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}
require_cmd curl
require_cmd jq
require_cmd psql

# ---------------------------------------------------------------------------
# 0. Liveness checks (gotrue + backend).
# ---------------------------------------------------------------------------
log "waiting for gotrue at $GOTRUE_URL/health"
for _ in $(seq 1 60); do
  if curl -fsS "$GOTRUE_URL/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl -fsS "$GOTRUE_URL/health" >/dev/null || fail "gotrue never came up at $GOTRUE_URL"

log "waiting for backend at $BACKEND_URL/health"
for _ in $(seq 1 60); do
  if curl -fsS "$BACKEND_URL/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl -fsS "$BACKEND_URL/health" >/dev/null || fail "backend never came up at $BACKEND_URL"

# ---------------------------------------------------------------------------
# 1. Sign up a user in GoTrue.
# ---------------------------------------------------------------------------
log "signing up $EMAIL via GoTrue"
signup_response=$(curl -fsS -X POST "$GOTRUE_URL/signup" \
  -H 'Content-Type: application/json' \
  -d "$(jq -nc --arg e "$EMAIL" --arg p "$PASSWORD" \
    '{email:$e, password:$p, data:{display_name:"Smoke Test"}}')")
gotrue_sub=$(jq -r '.id // .user.id // empty' <<<"$signup_response")
[ -n "$gotrue_sub" ] || fail "GoTrue signup did not return a user id; body=$signup_response"
log "  gotrue user id: $gotrue_sub"

# ---------------------------------------------------------------------------
# 2. Log the user in to obtain a JWT.
# ---------------------------------------------------------------------------
log "logging in to obtain a GoTrue JWT"
login_response=$(curl -fsS -X POST "$GOTRUE_URL/token?grant_type=password" \
  -H 'Content-Type: application/json' \
  -d "$(jq -nc --arg e "$EMAIL" --arg p "$PASSWORD" '{email:$e, password:$p}')")
access_token=$(jq -r '.access_token // empty' <<<"$login_response")
[ -n "$access_token" ] || fail "GoTrue login returned no access_token; body=$login_response"
log "  jwt acquired (${#access_token} chars)"

# Sanity-check the token's `sub` matches what we got from signup.
token_sub=$(printf '%s' "$access_token" \
  | awk -F. '{print $2}' \
  | {
    read -r p
    printf '%s' "$p"
    printf '%*s' $(((4 - ${#p} % 4) % 4)) '=' \
      | tr ' ' '='
  } \
  | base64 -d 2>/dev/null \
  | jq -r '.sub // empty')
[ "$token_sub" = "$gotrue_sub" ] || fail "JWT sub ($token_sub) != signup id ($gotrue_sub)"

# ---------------------------------------------------------------------------
# 3. Provision a matching AIMVISION users row + solo org.
# ---------------------------------------------------------------------------
log "linking AIMVISION users.gotrue_sub = $gotrue_sub"
user_id="smoke-${SUFFIX}"
account_id="acct-${SUFFIX}"
solo_tenant="solo:${user_id}"
solo_org_id="org-${SUFFIX}"
export PGPASSWORD="$PG_PASSWORD"
psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" -v ON_ERROR_STOP=1 <<SQL >/dev/null
INSERT INTO accounts (id, name, is_active, created_at, updated_at)
  VALUES ('$account_id', 'Smoke $SUFFIX', true, now(), now());
INSERT INTO users (id, account_id, email, password_hash, display_name, is_active,
                   gotrue_sub, created_at, updated_at)
  VALUES ('$user_id', '$account_id', '$EMAIL', '\$pbkdf2\$unused\$0\$0',
          'Smoke User', true, '$gotrue_sub', now(), now());
INSERT INTO orgs (id, kind, name, tenant_id, created_at, updated_at)
  VALUES ('$solo_org_id', 'solo', 'Smoke User (solo)', '$solo_tenant', now(), now());
SQL

# ---------------------------------------------------------------------------
# 4. Exchange the GoTrue JWT for an AIMVISION session.
# ---------------------------------------------------------------------------
log "POST $BACKEND_URL/auth/exchange"
exchange_response=$(curl -fsS -X POST "$BACKEND_URL/auth/exchange" \
  -H 'Content-Type: application/json' \
  -d "$(jq -nc --arg t "$access_token" '{gotrue_jwt:$t}')")

# ---------------------------------------------------------------------------
# 5. Assert LoginOut shape.
# ---------------------------------------------------------------------------
[ "$(jq -r '.token_type' <<<"$exchange_response")" = "bearer" ] \
  || fail "expected token_type=bearer; got $exchange_response"
[ -n "$(jq -r '.access_token // empty' <<<"$exchange_response")" ] \
  || fail "no access_token in response"
[ "$(jq -r '.principal.user_id' <<<"$exchange_response")" = "$user_id" ] \
  || fail "principal.user_id mismatch"
[ "$(jq -r '.principal.tenant_id' <<<"$exchange_response")" = "$solo_tenant" ] \
  || fail "principal.tenant_id mismatch"
tenant_ids=$(jq -r '.memberships[].tenant_id' <<<"$exchange_response")
grep -qx "$solo_tenant" <<<"$tenant_ids" \
  || fail "solo tenant not in memberships; got: $tenant_ids"

log "OK — GoTrue → AIMVISION /auth/exchange loop is healthy."
log "  user_id     = $user_id"
log "  gotrue_sub  = $gotrue_sub"
log "  tenant_id   = $solo_tenant"
