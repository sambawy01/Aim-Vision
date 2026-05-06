# ADR-0007: Temporal for Long-Running Workflow Orchestration

**Status:** Accepted · **Date:** 2026-05-06 · **Owner:** Software Architect

## Context

AIMVISION has at least four classes of workflow that share a common shape — long-running, multi-step, with retries, idempotency requirements, observability requirements, and the occasional human-in-the-loop pause:

1. **Post-session pipeline.** Triggered when a session recording is uploaded. Activities: refetch from S3, decode + frame extraction, full-resolution pose (HRNet/RTMPose-x on GPU), barrel detection, per-shot diagnostic ensemble, pattern detection, LLM coaching report generation (Ollama queued, fallback Anthropic), PDF render, notify athlete. Target: p50 ≤ 90 s, p95 ≤ 150 s, hard cap 180 s with degraded fallback ([Performance review](../reviews/10-performance-benchmarker.md)).
2. **Longitudinal pipeline.** Periodic projection refresh over the shot-event log into TimescaleDB hypertables (ADR-0006). Daily plus on-demand.
3. **Erasure pipeline.** GDPR / Egypt PDPL right-to-be-forgotten. Fan out to every owned data store: Postgres (shot events, recordings, annotations, sessions, athletes), S3 (raw recordings, derived artifacts, reports), MLflow training-data lineage (mark-and-flag, not delete), vector store (`pgvector` per-athlete RAG corpus), search index, and external services (Sentry, PostHog, Mux/Cloudflare Stream). Idempotent, audited, must complete within the regulatory window. Detail in `docs/compliance/gdpr-erasure-flow.md`.
4. **ML retraining pipeline.** Active-learning loop: query lowest-confidence shots, push to CVAT for Franco's labels, retrain LoRA adapter, evaluate against held-out set with calibration metrics (ECE, Brier, conformal coverage per [AI Engineer review §Critical gaps](../reviews/01-ai-engineer.md)), promote in MLflow registry on pass.

Plus a long tail of smaller workflows: subscription lifecycle (Stripe + RevenueCat reconciliation), federation appliance health check, scheduled backups (cloud Litestream verification, on-prem pgBackRest), QR check-in token cleanup, model shadow-routing A/B sample collection.

The original V1 sprint plan implies a "queue + worker" pattern (Arq or similar). The [Software Architect review §Missing Concerns](../reviews/03-software-architect.md) flagged this as a Sprint 14 cliff: "a plain queue + worker rebuilds Temporal badly by Sprint 14." Specifically, when you start needing retry policies with exponential backoff, idempotency keys, distributed cancellation, in-progress visibility, child workflows, signals, timers, versioning ("don't break workflows that are already running while I deploy a new version"), and a UI to see why a workflow is stuck — you have rebuilt Temporal, but with bugs.

## Decision

**Temporal is the workflow orchestrator for AIMVISION.** Specifically:

- **Self-hosted Temporal** in cloud and on-prem. The cluster is part of the single Helm chart (ADR-0005). Temporal's storage backend is Postgres, which we already operate.
- **Python SDK** (`temporalio`) for workflows and activities, matching the backend language (ADR-0001).
- **Temporal Web UI** exposed on the internal admin domain, gated by Clerk/WorkOS auth. Operators see in-flight workflows, replay history, and signal/cancel/terminate from the UI.
- **Workflow versioning is mandatory.** Every workflow uses `workflow.patched()` for non-backward-compatible changes; we do not deploy a workflow change that would crash in-flight executions.
- **Activities are idempotent.** Every activity takes an idempotency key (typically `workflow_id` + `activity_step`) and writes its output to a result table keyed on the idempotency key before returning. Re-execution returns the cached result. This is non-negotiable: Temporal retries activities, and a non-idempotent activity will write side effects N times.
- **Retry policies are explicit.** Defaults: `initial_interval=1s`, `backoff_coefficient=2.0`, `maximum_interval=60s`, `maximum_attempts=10`. Activities that touch external services (Anthropic API, Stripe, S3) override with longer maxima.
- **The four named pipelines are first-class.** Each is a single workflow type with a documented input schema, observable progress signals, and a runbook in `docs/operations/runbooks/`.
- **Inngest is the documented serverless alternative.** If self-hosted Temporal becomes an operational burden — specifically, if the federation on-prem appliance struggles with the Temporal-cluster footprint — we move cloud workflows to Inngest. The workflow code is portable: the Temporal/Inngest activity-and-workflow shape is similar enough that a wrapper layer would isolate the migration. We do not pre-build the wrapper; we let Inngest stay an off-ramp, not a hedge.

### Workflow library

```
aimvision-backend/workflows/
  process_session.py         # post-session pipeline
  refresh_longitudinal.py    # daily TimescaleDB projection refresh
  erase_subject.py           # GDPR/PDPL erasure
  retrain_diagnostic.py      # ML retraining loop
  reconcile_subscription.py  # Stripe + RevenueCat
  check_appliance.py         # federation appliance health
  ...
```

### Activities

Activities are short, idempotent, side-effect-explicit functions:

```python
@activity.defn(name="generate_llm_report")
async def generate_llm_report(
    session_id: UUID,
    shot_summaries: list[ShotSummary],
    athlete_ctx: AthleteContext,
    idempotency_key: str,
) -> LLMReport:
    # 1. Look up cached output by idempotency_key; if present, return it.
    # 2. Construct structured prompt with RAG retrieval over prior coach notes.
    # 3. Call Ollama queue worker (or Anthropic fallback per feature flag).
    # 4. Verify structured output against pydantic schema; reject and retry if invalid.
    # 5. Cache and return.
```

The verifier pass (per [AI Engineer review §Accuracy improvements #5](../reviews/01-ai-engineer.md)) is its own activity that the workflow runs after `generate_llm_report` and rejects-and-retries the report activity if the LLM cited features that don't match the data.

### Concurrency and queues

- **Activity workers** are per-task-queue. We define `gpu-pool`, `llm-pool`, `default-pool`. GPU activities (HRNet, YOLOv8x server-side, full-res pose) run only on the GPU pool with worker concurrency tuned to the GPU count.
- **Ollama is queued.** A single Ollama worker pool with 3–4 GPU workers ([Software Architect review §Scaling Cliffs #3](../reviews/03-software-architect.md)) consumes from the `llm-pool` task queue. The fallback to Anthropic is a feature-flag-gated branch inside `generate_llm_report`.

### Telemetry

OpenTelemetry traces are propagated through Temporal contexts (workflow → activity span hierarchy). Every workflow exports a span; every activity exports a child span. The post-session pipeline's per-stage histograms (`pose_lag`, `barrel_lag`, `llm_lag`, `pdf_lag`) are emitted by activity instrumentation and visible in Grafana. This is the foundation for [Performance review §Instrumentation](../reviews/10-performance-benchmarker.md) backend telemetry.

## Consequences

**Easier:**

- Visibility into stuck workflows is built-in (Temporal Web UI, history replay, search attributes).
- Retries, timeouts, idempotency, and cancellation are framework concerns, not application concerns.
- Long-running workflows (an erasure that fans out to 12 services and takes 6 hours) are first-class — there is no "did this finish or did the worker die" question.
- The post-session pipeline's progressive disclosure ("Shot detected" → "Diagnostic ready" → "Report ready" per [Performance review](../reviews/10-performance-benchmarker.md)) is implemented as workflow signals; the UI subscribes and renders state transitions.
- Workflow versioning lets us deploy without draining in-flight executions.

**Harder:**

- Running Temporal on the federation appliance adds a stateful service plus its Postgres tables. We mitigate by sharing the CloudNativePG cluster with the application (Temporal lives in its own database within the same cluster).
- Activities that are already idempotent in the application (most CRUD) feel pedantic when wrapped in idempotency-key bookkeeping. We accept the friction; the whole point is uniform behavior under retry.
- Engineers new to Temporal need a ramp. We mitigate with a starter workflow template, a code-review checklist for idempotency, and a "no Temporal in tests for non-workflow code" rule (Temporal's testing harness is for workflow tests; everything else is mocked at the activity boundary).

**Reversibility:** Medium. Replacing Temporal later means rewriting the four named pipelines. Inngest is the documented off-ramp; ad-hoc queue+worker is not, because it would be a regression.

## Alternatives Considered

1. **Ad-hoc queue + worker (Arq, Celery, Sidekiq, BullMQ).** Rejected per [Software Architect review §Missing Concerns](../reviews/03-software-architect.md) — rebuilds Temporal badly by Sprint 14.
2. **Inngest (serverless workflow engine).** Strong product, very ergonomic. Rejected for V1 because (a) the federation on-prem appliance cannot depend on a hosted SaaS, and (b) cloud lock-in is a meaningful concern. **Held as off-ramp** if self-hosted Temporal becomes a burden in cloud.
3. **AWS Step Functions.** Cloud lock-in; on-prem path becomes "rewrite as something else." Rejected.
4. **Airflow / Prefect / Dagster.** These are batch-data orchestrators, not transactional workflow engines. Wrong shape for the post-session pipeline; right shape for analytics ETL only. We use neither for V1.
5. **Hand-rolled state machine on Postgres with `SELECT ... FOR UPDATE SKIP LOCKED`.** Tempting, lightweight, and we already operate Postgres. Rejected on the same grounds as #1: by Sprint 14 we will have rebuilt Temporal's history table, retry policies, signaling, versioning, and Web UI.

## References

- [Software Architect review §Missing Concerns (long-running job orchestration)](../reviews/03-software-architect.md)
- [Performance review §Post-Session 90s Feasibility Check](../reviews/10-performance-benchmarker.md) — pipeline budget the post-session workflow must hit.
- [AI Engineer review §Accuracy improvements #5](../reviews/01-ai-engineer.md) — LLM verifier pass as a workflow step.
- [ADR-0006: Event sourcing](0006-event-sourcing-shot-events.md) — projections are rebuilt by Temporal workflows.
- [ADR-0001: Backend Python](0001-backend-python-fastapi.md) — Temporal Python SDK matches.
- Temporal: <https://temporal.io/>
- Temporal Python SDK: <https://github.com/temporalio/sdk-python>
- Inngest (off-ramp): <https://www.inngest.com/>
