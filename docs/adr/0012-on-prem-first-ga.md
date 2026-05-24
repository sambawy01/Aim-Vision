# ADR-0012: First GA Target = On-Prem (Federation Tier)

**Status:** Accepted · **Date:** 2026-05-24 · **Owner:** Founder/CEO

## Context

The product has three tiers (Solo, Club, Federation) and the V2 sprint
plan calls federation the design-partner customer (Egypt National Team
per CLAUDE.md). ADR-0005 commits to one Helm chart that runs identically
in cloud and on-prem. The pilot venue per ADR-0016 is the Egypt
National Team facility — a federation customer.

Cloud-first GA would prioritize Solo + Club rollout to multiple
geographies on managed infra; on-prem-first GA prioritizes the
federation tier as the first paying customer, with cloud Solo/Club
following once the federation deploy is hardened.

The Phase-0 work already biases on-prem-friendly: CloudNativePG for
Postgres, MinIO available as the S3 alternative, the audit log is
hash-chained without external dependencies, and ADR-0005 explicitly
calls out a 30-minute bare-metal-to-running-stack installer target
for federation appliances.

## Decision

**First GA is the federation-tier on-prem deploy. Cloud-tier Solo +
Club rollout follows.**

Concretely:

- Every Phase-1 vendor choice defaults to a self-hostable option
  (Supabase Auth per ADR-0010, MinIO, GlitchTip self-hosted, Vault).
  Managed-cloud equivalents (Auth0, S3, Sentry SaaS, AWS KMS) become
  optional `values-cloud.yaml` knobs in the Helm chart, not required.
- The first paying customer Egypt National Team installs the Helm
  chart inside their own network. Internet egress is permitted but
  _minimised_ — only the hosted LLM endpoint per ADR-0014 (with
  documented PII strip) and Stripe per ADR-0011 leave the network.
- The post-pilot cloud-tier rollout reuses the same Helm chart with
  `values-cloud.yaml`.

## Consequences

**Positive.**

- Aligns the first customer's procurement model (on-prem) with the
  first GA path (no platform-shape change at launch).
- Forces every dependency to be self-hostable, which removes the
  "cloud-only feature that breaks on-prem" risk class that the
  Software Architect review (`docs/reviews/03-software-architect.md`)
  flagged.
- The single Helm chart per ADR-0005 stays the operational
  source-of-truth; nothing about cloud-first design retrofits on-prem
  later.

**Negative.**

- Per-customer rollout is heavier (each federation needs an installer
  walkthrough). The 30-min installer target in ADR-0005 is
  load-bearing.
- The cloud-tier Solo/Club waitlist gets longer; we lose the smaller
  per-customer revenue stream until Phase 2.
- Some Phase-1 observability tooling (GlitchTip, Grafana self-host,
  Loki) is operationally heavier than the SaaS equivalents. Acceptable
  because the federation already accepts the same operational
  surface for Postgres / Ollama-equivalent / MinIO.

## Alternatives considered

- **Cloud-first GA, on-prem at Sprint 17** — the original V1 plan;
  rejected in ADR-0005 because of the "cloud-shaped Postgres
  retrofitted on-prem" problem.
- **Cloud + on-prem simultaneous GA** — too much surface to harden
  in Phase 1. Push cloud to a Phase-2 follow-on.
