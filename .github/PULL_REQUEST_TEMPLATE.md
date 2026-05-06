<!--
  AIMVISION pull request template. Fill out every section. Sections that don't
  apply: write "N/A — <reason>" rather than deleting them — reviewers grep for
  these labels to triage.
-->

## Summary

<!-- One or two sentences. What does this PR do? Why now? -->

## Scope

<!-- Tick the subrepos this PR touches. Cross-cutting? Tick more than one. -->

- [ ] `aimvision-backend`
- [ ] `aimvision-camera-core`
- [ ] `aimvision-mobile`
- [ ] `aimvision-web`
- [ ] `aimvision-ml`
- [ ] `aimvision-infra`
- [ ] `docs/`
- [ ] Repo root (CI, tooling, monorepo config)

## ADR

<!--
  Link the ADR this PR implements, or "N/A — not architectural".
  If this PR makes an architectural change without an ADR, file the ADR first.
  See CONTRIBUTING.md §"When to file an ADR".
-->

- ADR cited: <!-- e.g. ADR-0005, or "N/A — not architectural" -->

## Test plan

<!--
  Concrete commands you ran locally + what CI is expected to cover.
  Examples:
   - `cd aimvision-backend && uv run pytest tests/test_rls.py -k cohort`
   - `make helm-lint && make helm-template-cloud`
   - `make ci-local`
-->

- [ ] Unit tests added / updated
- [ ] Integration tests added / updated
- [ ] Manual QA performed (describe)
- [ ] Helm chart re-rendered + diffed (if `aimvision-infra/**` changed)

## Risk + rollout

<!--
  Migration, secret rotation, schema change, multi-tenant boundary change, etc.
  Include the rollback procedure.
-->

- Risk level: low / medium / high
- Schema migration: yes / no — if yes, link Alembic revision
- Secret rotation: yes / no
- Cross-tenant data flow change: yes / no — if yes, ticket in compliance review
- Rollback plan:

## Required reviews

- [ ] **Security review** required? <!-- yes if auth, RLS, secrets, network policy -->
- [ ] **Compliance review** required? <!-- yes if changes a data-flow that crosses tenants or regions -->
- [ ] **Platform/SRE review** required? <!-- yes for any aimvision-infra/** change -->
- [ ] **ML model review** required? <!-- yes for any model registry / artifact change -->

## Reviewer checklist

<!-- Reviewers tick these as they go. Authors leave them blank. -->

- [ ] Code matches the cited ADR (or this PR doesn't need one)
- [ ] No tier-branching (`if cloud else on_prem`) added — uses values overlays instead
- [ ] No secrets in diff (gitleaks green confirms, but skim anyway)
- [ ] Multi-tenant boundary not weakened — RLS + app-layer scope filter both enforced
- [ ] Tests cover the failure mode that motivated the change
- [ ] Observability: new spans/metrics/logs land in dashboards
- [ ] Docs updated (README, runbook, ADR if applicable)
