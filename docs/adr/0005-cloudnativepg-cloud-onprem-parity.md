# ADR-0005: CloudNativePG + Single Helm Chart for Cloud↔On-Prem Parity

**Status:** Accepted · **Date:** 2026-05-06 · **Owner:** Software Architect

## Context

AIMVISION must run in two materially different environments: managed cloud (Railway-managed Kubernetes for Solo/Club, eventual move to GKE/EKS as we scale) and federation on-prem (a k3s appliance inside a federation's network with no outbound dependency on the cloud control plane). The original V1 sprint plan listed Postgres on Railway as the persistence story, with on-prem deployment deferred to Sprint 17 as a separate effort.

The [Software Architect review §Top 3 #3](../reviews/03-software-architect.md) flagged this as a Sprint 17 cliff: any architecture that ships a cloud-shaped Postgres in Sprints 1–16 and tries to retrofit on-prem deployment in Sprint 17 will discover that managed-Postgres assumptions (provider-specific backups, provider-specific HA failover, provider-specific connection pooling) do not transfer. The fix is to pick a Postgres operator that runs the same way in both environments and to ship one Helm chart for the entire stack.

[Embedded review §Outdoor Failure Modes](../reviews/05-embedded-firmware-engineer.md) and [Compliance review](../reviews/07-compliance-auditor.md) add federation-specific constraints: federations cannot operate Docker-compose; federations require local backup with 30-day retention as a procurement floor; federations need offline operation for days at a time; federation IT staff are not Kubernetes experts. The deployment must be operable by a coach with a runbook, not by an SRE.

The candidates for the Postgres layer are CloudNativePG (active development, Postgres-version parity, declarative HA via the operator), Crunchy PGO (mature, more enterprise-flavored, occasionally lags Postgres releases), Zalando postgres-operator (oldest, slower release cadence), and managed-only (Railway/RDS/Cloud SQL — not portable to on-prem). The candidates for the deployment layer are a single Helm chart, separate Helm charts per environment, Docker Compose (rejected on operability grounds), and Nomad (rejected on team-skill grounds — we are committing to Kubernetes).

## Decision

**CloudNativePG operator + a single Helm chart that deploys the entire AIMVISION stack — API, workers, Postgres, Redis, MinIO/S3, Ollama, Temporal — and runs identically on Railway-managed Kubernetes (cloud) and a federation k3s appliance (on-prem).** Specifically:

### Database layer

- **CloudNativePG** as the Postgres operator. Reasons: declarative HA (write a `Cluster` resource, get a primary plus replicas with synchronous replication, automatic failover, automatic certificate management); operator-driven backups (`Backup` and `ScheduledBackup` resources); native support for streaming replication, logical decoding, and PITR; tracks Postgres minor versions promptly.
- **Postgres 16** as the engine version, with **TimescaleDB extension** enabled for V1 longitudinal analytics (per [Software Architect review §Missing Concerns](../reviews/03-software-architect.md), TimescaleDB is the no-infra-change path for time-series). **ClickHouse is deferred to V2** for federation cohort analytics.
- **`pgvector` extension** enabled for the RAG retrieval layer over per-athlete coach notes (LLM coaching report pipeline, ADR-0007).
- **Row-Level Security** enabled per ADR-0004.
- **Backups:**
  - **Cloud:** Litestream sidecar replicates the WAL to S3 continuously for point-in-time recovery; full base backups via CloudNativePG to S3 nightly.
  - **On-prem:** pgBackRest (operator-integrated) writes to a local NFS or attached storage; nightly full + 4× daily incremental + continuous WAL archive. Optional encrypted off-site sync to a federation-controlled S3-compatible target.
- **Connection pooling:** PgBouncer in transaction-pool mode, deployed by the operator. Compatible with the `SET LOCAL app.current_org_id` pattern from ADR-0004.

### Helm chart

- **One chart**, `charts/aimvision`, with environment-specific values files (`values-cloud.yaml`, `values-federation.yaml`, `values-dev.yaml`).
- **Sub-charts** for each runtime component: `api`, `workers`, `cnpg` (depends on the CloudNativePG operator chart, installed cluster-wide), `redis`, `minio`, `ollama`, `temporal`. Each sub-chart is independently bumpable.
- **Container images** are the same in both environments. Differences are environment variables, secrets, replica counts, ingress class, and which storage class is requested. There is no `if cloud else on_prem` branch in any container.
- **Federation on-prem appliance** is a single Bash installer script that installs k3s, applies the CloudNativePG operator manifest, and `helm install`s the chart with the federation values file. Total wall-clock install time on a 16-core/64GB appliance: target ≤ 30 minutes from bare metal to first session uploaded.
- **Air-gapped install** is supported: the chart is published to a private OCI registry and the federation appliance bundle ships with a tarball of all images; the installer loads the tarball into k3s's containerd before applying the chart.

### Object storage

- **Cloud:** S3 (with Cloudflare in front for video CDN — never proxy video through the API, ADR-0008).
- **On-prem:** MinIO, configured as a stand-in for S3. The application code uses `boto3` and treats both identically. Federation may bring their own S3-compatible target (Wasabi, Backblaze, or the federation's existing object store) by overriding the values file.

### Object-storage layout

- `recordings/{organization_id}/{session_id}/{recording_id}.mp4` (raw video)
- `derived/{organization_id}/{session_id}/{recording_id}/keypoints.parquet` (pose tensors)
- `reports/{organization_id}/{session_id}/{recording_id}.pdf`
- `models/{model_name}/{model_version}/{artifact}` (registry-controlled, see `docs/ml/model-registry-and-shadow-eval.md`)

Lifecycle: raw recordings on cloud move to Glacier Instant Retrieval after 90 days; on-prem retention is per-federation contract.

### Observability hooks

CloudNativePG exports Prometheus metrics for Postgres state and operator state. We forward these to Grafana Cloud (cloud) or the on-appliance Grafana (on-prem). The same dashboards work in both environments because the metrics are operator-defined, not provider-defined.

## Consequences

**Easier:**

- Sprint 17's "validate on-prem deployment" becomes a one-day acceptance test instead of a two-week port. The deployment shape was the same all along.
- A bug in the cloud database layer reproduces on the federation appliance and vice versa — same operator, same Postgres version, same extensions.
- Federation procurement objections on data residency and operability are answered by demonstrating an air-gapped install.
- The Helm chart is the artifact that QA, ops, and the federation IT contact all share. There is no "but in production we use…" gap.

**Harder:**

- We commit to Kubernetes everywhere. Railway's Kubernetes posture is acceptable today; if Railway changes that we migrate to GKE/EKS without code changes (the chart is portable).
- CloudNativePG is younger than Crunchy and Zalando; we accept that operational maturity is on us to verify with chaos testing and a documented runbook in `docs/operations/runbooks/`.
- A federation appliance is a hardware SKU we have to spec, ship, and support. We pick a reference appliance (a small fanless 16-core/64GB box with NVMe RAID-1) and certify only that.
- Litestream's S3-streaming approach has a known recovery-window cost (typically 10–30 seconds of writes can be lost on catastrophic primary failure). We accept this trade for cloud DR and use synchronous replication within the cluster to reduce the realistic loss window to milliseconds.

**Reversibility:** Medium. The CloudNativePG choice is reversible (we could swap to Crunchy with a few weeks of migration work). The single-Helm-chart deployment shape is the harder commitment to undo and the highest-leverage architectural decision.

## Alternatives Considered

1. **Managed Postgres only (Railway / Supabase / RDS) for cloud, separate ad-hoc Postgres on the federation appliance.** Rejected because it forces two deployment shapes, two backup stories, two failover stories, and a Sprint 17 retrofit cliff.
2. **Crunchy PGO.** Mature but more enterprise-flavored and occasionally lags Postgres minor releases. Acceptable second choice; CloudNativePG wins on release cadence and operator UX.
3. **Zalando postgres-operator.** Oldest of the three, slower release cadence. Rejected.
4. **Docker Compose for the federation appliance.** Rejected per [Software Architect review §Top 3 #3](../reviews/03-software-architect.md) — clubs and federations cannot operate it. k3s is not as friendly as compose but is operable through a Helm chart with a runbook and a small admin web UI.
5. **HashiCorp Nomad instead of Kubernetes.** Rejected on team-skill grounds.

## References

- [Software Architect review §Top 3 #3](../reviews/03-software-architect.md) — original recommendation for CloudNativePG and the single-Helm-chart parity model.
- [Embedded review §Outdoor Failure Modes](../reviews/05-embedded-firmware-engineer.md) — operability constraints for federation deployment.
- [Compliance review](../reviews/07-compliance-auditor.md) — data-residency and backup-retention obligations.
- [ADR-0004: Multi-tenancy via RLS](0004-multi-tenancy-rls.md) — schema requirements satisfied by both deployment shapes.
- CloudNativePG: <https://cloudnative-pg.io/>
- TimescaleDB: <https://docs.timescale.com/>
- Litestream: <https://litestream.io/>
- pgBackRest: <https://pgbackrest.org/>
- `docs/operations/runbooks/` — operational runbooks for cloud and on-prem (predicted directory, owned by SRE).
