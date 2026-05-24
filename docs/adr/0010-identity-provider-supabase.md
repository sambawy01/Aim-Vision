# ADR-0010: Identity Provider = Supabase Auth (GoTrue), Self-Hosted

**Status:** Accepted · **Date:** 2026-05-24 · **Owner:** Backend lead

## Context

The current backend auth (`aimvision-backend/app/services/auth.py`) is
explicitly a stub: PBKDF2-SHA256 password hashing, HS256 JWT with a
`dev-secret-change-me-in-production` default, no refresh, no password
reset, no email verification, no rate limiting. The service file even
comments "Stub for the production PASETO/OIDC path."

Per ADR-0012, GA targets the on-prem federation tier first — every
chosen integration must have a credible self-hosted story. The
candidates evaluated were Auth0 (lowest setup, no self-host), WorkOS
(strong SSO for federations later, no self-host), self-hosted Keycloak
(most flexible, heavy ops), and Supabase Auth / GoTrue (Postgres-native,
self-hostable via docker-compose or Helm).

The web client already runs against the refresh-cookie flow that PR #89
introduced; the mobile client just learned to read `principal` from
the login response (PR #90). The principal / tenancy / RLS layer in
the AIMVISION backend is well-developed and not something we want to
hand to an external identity provider.

## Decision

**Supabase Auth (GoTrue), self-hosted, is the identity layer. The
AIMVISION backend keeps tenancy, memberships, and RLS.**

Concretely:

- GoTrue runs as part of the AIMVISION Helm chart (ADR-0005),
  alongside its own Postgres schema (in the same CloudNativePG cluster
  or a dedicated one — operator-level decision).
- GoTrue is the source of truth for: users, password hashes (argon2id),
  email verification state, password resets, refresh tokens, MFA (when
  we enable it), and OIDC SSO when federations request it.
- The AIMVISION backend keeps: `accounts`, `users` (mirror linked by
  GoTrue user id), `memberships`, `orgs`, all RLS policies, the
  principal-resolution + tenant-switch endpoints from PR #89.
- The backend validates GoTrue-issued JWTs (HS256 today, RS256 when
  GoTrue runs in production), extracts the user id (`sub`), and runs
  the existing `_resolve_memberships` to mint an AIMVISION-style
  principal + memberships tuple in the login response.
- The web + mobile clients call **GoTrue** for `/auth/signup`,
  `/auth/login`, `/auth/refresh`, `/auth/recover`, `/auth/verify` and
  call the **AIMVISION backend** for `/auth/switch-tenant` and the
  principal-attached endpoints.

### Migration

Existing PBKDF2 users get bulk-imported into GoTrue's `auth.users`
table with `encrypted_password = '$pbkdf2$200000$<salt>$<hash>'` —
GoTrue supports verifying legacy PBKDF2 hashes and re-hashing as
argon2id on next login. The cutover is a one-shot script run during
a brief maintenance window.

## Consequences

**Positive.**
- Self-hostable — no vendor lock-in on the on-prem federation deploy.
- argon2id, email verification, password reset, rate limiting are
  features of GoTrue we get for free.
- OIDC SSO becomes a config flip when federations request it (some
  federations require SAML — Keycloak in front of GoTrue covers that
  in a later wave).
- The AIMVISION backend stops carrying half-built auth code; we delete
  `hash_password`/`verify_password`/`issue_token`/`verify_refresh_token`
  and replace with GoTrue JWT verification only.
- Supabase Auth is open-source (MIT); no commercial license required.

**Negative.**
- Two services to operate (GoTrue + AIMVISION backend) instead of one.
- One more Postgres database (GoTrue's `auth` schema) — the
  CloudNativePG operator handles this fine.
- Email deliverability is now a federation-tier concern (federations
  must BYO SMTP or accept the default we ship).
- The `auth_database_url` separation we already have for the audit
  schema works fine here — no new pattern.

## Alternatives considered

- **Auth0** — easiest setup, but no self-host story. Cost
  ($0.023/MAU) is fine for a Solo-tier consumer flow but federations
  routinely contractually disallow customer data leaving the
  premises. Rejected on ADR-0012 alignment.
- **WorkOS** — best SSO + Directory Sync story; we may revisit when
  federations demand SAML/SCIM. Today their pricing model is per-MAU
  and they have no on-prem deployment.
- **Self-hosted Keycloak** — most powerful, most enterprise; ops
  burden is much higher than GoTrue, the admin UI is dated, and we
  don't need its enterprise SSO features in Phase 1. We can layer
  Keycloak in front of GoTrue later if a federation requires SAML
  before Supabase ships SAML support.
- **Continue with the in-house stub** — rejected; the security debt
  is too high for any pilot, let alone GA.
