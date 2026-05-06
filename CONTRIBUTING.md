# Contributing to AIMVISION

> **Repository scope:** this is a polyrepo-shaped monorepo. Each `aimvision-*`
> directory is an independently versioned project with its own CI, README, and
> conventions. The top-level repo binds them together with shared tooling
> (pre-commit, dependabot, CI orchestrator, security scans).

Welcome — this guide covers branching, signed commits, PR conventions, and the
review checklist. ADRs and architecture docs are the source of truth for
design; this doc only covers process.

---

## Quick start (first-time setup)

```sh
# 1. Clone
git clone git@github.com:sambawy01/aimvision.git
cd aimvision

# 2. Install hooks + tools
make setup

# 3. Run the same checks CI runs, locally
make ci-local
```

`make setup` installs pre-commit (and its hooks) and runs each subrepo's own
`make setup` if it exists. After this, every commit is gitleaks-scanned and
auto-formatted; pushing without running `make ci-local` is fine, but expect
CI to catch formatting and lint issues.

---

## Branching model

- `main` is **always deployable**. Protected by the `ci-success` aggregate gate.
- Feature work goes on a branch named `<type>/<sprint>-<topic>`:
  - `feat/06-temporal-process-session`
  - `fix/04-rls-bypass-cohort-aggregator`
  - `chore/infra-cnpg-0.22-bump`
  - `docs/adr-0009-event-replay`
- One PR per change. Long-running branches are an antipattern — split them.
- Sprint number prefix is mandatory so the retrospective tooling can attribute
  work to the right sprint without consulting the issue tracker.

### When to file an ADR

File an ADR (in `docs/adr/`) **before** opening a PR if the change:

- Introduces a new runtime dependency, language, or operator.
- Alters the multi-tenant boundary or auth surface.
- Changes the data shape of `shot_events` or any other event-sourced table.
- Reshapes the deployment topology or breaks cloud↔on-prem parity.

PRs that should have an ADR but don't will be returned with "needs ADR" and
no further review until one lands.

---

## Signed commits

All commits must be signed (GPG or SSH). The `verified` checkmark in GitHub is
how we audit who shipped what — branch protection rejects unsigned commits on
`main`.

```sh
# One-time SSH commit signing setup
git config --global gpg.format ssh
git config --global user.signingkey ~/.ssh/id_ed25519.pub
git config --global commit.gpgsign true
git config --global tag.gpgsign true
```

---

## Commit messages

Conventional Commits. Examples:

```
feat(backend): add per-tenant rate limiter on session-start endpoint
fix(camera-core): release Wi-Fi AP on transport drop instead of leaking
chore(infra): bump CNPG operator to 0.22.1
docs(adr): ADR-0009 — event replay for ML model rollouts
```

Allowed types: `feat`, `fix`, `chore`, `docs`, `refactor`, `perf`, `test`,
`build`, `ci`, `revert`. The optional scope is the subrepo (`backend`, `mobile`,
`infra`, `ml`, `web`, `camera-core`) or `repo` for top-level changes.

---

## Pull requests

The PR template is in `.github/PULL_REQUEST_TEMPLATE.md` and is auto-populated.
Required sections:

- **Summary** — what changed, in a sentence.
- **ADR cited** — link to the ADR this PR implements (or "N/A; not architectural").
- **Test plan** — what you ran locally, what CI ran, what you expect ops to
  watch in production.
- **Risk** — multi-tenant safety, schema migration, secret rotation, etc.
- **Reviewer checklist** — ticked by reviewers, not the author.

PRs touching `aimvision-backend/` or `aimvision-infra/` automatically request
the security and platform code-owners. Cross-tenant data flow changes
additionally require compliance review (see `docs/compliance/`).

### Required CI gates

Before merge, the PR must show green on:

- `gitleaks`
- `pre-commit`
- `helm-lint` (if `aimvision-infra/**` changed)
- The subrepo CI for every changed subrepo
- The aggregated `ci-success` job

The aggregate gate is the only one configured as required in branch protection;
the others are dependencies of it.

---

## Monorepo conventions

- **No cross-repo Python/JS imports.** Each subrepo is independent. If you need
  shared code, factor it into a package and publish it (private registry) —
  don't symlink across subrepos.
- **Pydantic schemas in `aimvision-backend/` are the source of truth** for API
  DTOs. The web/mobile clients consume generated TypeScript via
  `openapi-typescript` (see `aimvision-web/Makefile`).
- **Container images are built per subrepo** and tagged with the subrepo's own
  SemVer (e.g. `ghcr.io/sambawy01/aimvision-backend:0.4.2`). The Helm chart's
  `appVersion` tracks the backend image since that's the most user-facing
  component.
- **Helm chart bumps are independent** — `aimvision-infra/helm/aimvision/Chart.yaml`
  has its own SemVer. Bump it whenever templates change in a non-trivial way.
- **The cloud↔on-prem parity rule is hard.** Any code that branches on the tier
  string is wrong. Use values overlays. See ADR-0005.

---

## Security disclosure

Security issues go to `security@aimvision.io`, not GitHub Issues. We follow a
90-day coordinated-disclosure timeline. See `SECURITY.md` (TODO) for details.
