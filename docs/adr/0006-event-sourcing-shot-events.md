# ADR-0006: Event Sourcing for Shot Events with CQRS Projections

**Status:** Accepted · **Date:** 2026-05-06 · **Owner:** Software Architect

## Context

A shot event in AIMVISION is the single most important data primitive: it represents one trigger pull, with audio-detected timestamp, video frame range, on-device pose features, on-device YOLO barrel detection, on-device diagnostic classifier output, and references to backend-rebuilt diagnostic ensembles. A 50-shot session produces 50 shot events. The session-record document, the live coach feed, the post-session report, the longitudinal analytics, and the federation talent-ID derived dataset are all functions of the shot-event stream.

The original V1 sprint plan (EPIC 8.2) describes "local event store + sync" without specifying append-only semantics, conflict resolution, or projection rebuild. The [Software Architect review §Missing Concerns](../reviews/03-software-architect.md) recommends making this explicit: shot events as immutable facts with `(session_id, monotonic_seq, device_clock, server_clock, payload)`, with no edit operation. The [Mobile review §Sync engine](../reviews/04-mobile-app-builder.md) confirms the right CRDT shape for the _only_ mutable surface (coach annotations) and explicitly names Automerge 2.0.

The cost of getting this wrong is the conflict-resolution cliff in EPIC 12.1: any "shot can be edited" model requires merge logic across athlete-app, coach-app, and backend writes, plus reconciliation when the device reconnects after offline use. Event sourcing eliminates 80% of this work because there is no edit — there is only "append a correction event." Linear's sync engine, ElectricSQL, and Riffle all reach the same conclusion for the same reason.

The architecture must serve four distinct read shapes:

1. **Live feed** — coach in the field, viewing shots as they happen. Reads from the event stream directly; latency-sensitive.
2. **Post-session report** — generated 90 seconds after session end, includes GPU-rebuilt diagnostics. A projection rebuilt by the Temporal pipeline (ADR-0007) from the event stream + GPU re-analysis.
3. **Longitudinal analytics** — per-athlete trends over months. A second projection over the same event log, materialized into TimescaleDB hypertables.
4. **Federation cohort analytics / talent-ID** — anonymized aggregates across affiliated clubs inside one federation. A third projection populated by a `@cross_tenant` Temporal activity (ADR-0004).

CQRS — Command Query Responsibility Segregation — describes this shape exactly: writes go to the event log; reads come from purpose-built projections.

## Decision

**Shot events are append-only immutable facts. The event stream is the system of record. Every read shape is a CQRS projection. Coach annotations, the only legitimately mutable surface, use Automerge 2.0 CRDT — and are the only CRDT in the system.**

### Event schema

```sql
CREATE TABLE shot_events (
    organization_id UUID NOT NULL,
    session_id UUID NOT NULL,
    monotonic_seq BIGINT NOT NULL,            -- per-device, per-session, dense, monotonic
    event_id UUID NOT NULL,                    -- globally unique, idempotency key
    device_id UUID NOT NULL,
    device_clock_ns BIGINT NOT NULL,           -- HCT capture-side timestamp (ns since epoch)
    server_clock_ns BIGINT NOT NULL,           -- assigned at backend ingestion
    event_type TEXT NOT NULL,                  -- 'shot.detected.audio' | 'shot.diagnosed.local' | etc.
    schema_version SMALLINT NOT NULL,          -- payload schema version
    model_version_ref TEXT,                    -- foreign key into MLflow registry, nullable
    payload JSONB NOT NULL,                    -- versioned, validated against pydantic schema
    PRIMARY KEY (organization_id, session_id, monotonic_seq)
);

ALTER TABLE shot_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY shot_events_isolation ON shot_events
    USING (organization_id = current_setting('app.current_org_id')::uuid);

-- Ingestion is INSERT-only. There is no UPDATE policy. There is a DELETE policy
-- only for the GDPR/PDPL erasure pipeline, gated on a service role.
```

`monotonic_seq` is dense and per-device-per-session: the device assigns 1, 2, 3, … as it produces events. Gaps indicate dropped events; duplicates are idempotently absorbed via `event_id` deduplication. The combination `(device_clock_ns, server_clock_ns)` lets the backend reason about clock skew and per-device offset; multi-camera sync ([Embedded review §Multi-Camera Sync](../reviews/05-embedded-firmware-engineer.md)) writes a `clock_offset_ms` per camera per shot into a separate normalized table that is itself derived from these timestamps.

### Event types (V1 catalog)

- `shot.detected.audio` — on-device audio shot detector fired (~30 ms p95).
- `shot.detected.imu` — V1.5; gun-mounted IMU (per [AI Engineer review §Accuracy improvements #1](../reviews/01-ai-engineer.md)) fired.
- `shot.diagnosed.local` — on-device diagnostic classifier output for this shot.
- `shot.outcome.recorded` — hit/miss/not-observed, set by athlete or backend pattern recognizer.
- `shot.diagnosed.server` — backend GPU-rebuilt diagnostic ensemble output, written by the post-session pipeline.
- `shot.corrected` — a correction event referencing an earlier event. Never overwrites; appends.
- `session.started`, `session.ended`, `recording.uploaded`, `recording.processed` — session lifecycle markers.

Each event type has a Pydantic schema with a `schema_version`. Schema evolution is additive only; breaking changes require a new event type.

### Projections

- **Live-feed projection.** Materialized in WatermelonDB on the device; reads stream directly from the event log via WebSocket subscription. The list view of shots in the active session is `SELECT * FROM shot_events WHERE session_id = ? ORDER BY monotonic_seq` filtered through a small in-memory aggregator.
- **Post-session report projection.** Built by the Temporal `ProcessSessionWorkflow` (ADR-0007). It reads the entire event stream for the session, joins with the GPU-rebuilt diagnostics (themselves written as `shot.diagnosed.server` events), runs the LLM coaching pass, renders the PDF, and writes the report row. The report is a derived artifact; if the model version changes, we replay the workflow.
- **Longitudinal analytics projection.** A Temporal-driven incremental projection populates TimescaleDB hypertables (`shots_per_day`, `pattern_features`, `regime_changes`). The projection consumes new events with a cursor over `(organization_id, server_clock_ns)` and is idempotent — replay from any cursor produces the same hypertable rows.
- **Federation cohort projection.** A `@cross_tenant` Temporal activity reads anonymized aggregates from the longitudinal hypertables for affiliated clubs and writes federation-owned summary rows.

### Sync engine

The on-device WatermelonDB instance maintains a per-session `last_synced_seq` cursor. Sync is "stream new events with `monotonic_seq > last_synced_seq` to the backend over the WebSocket; backend echoes server-assigned timestamps and the client advances the cursor." This is the pattern Linear's sync engine uses; it produces no merge conflicts because there is no merge — events are append-only.

### Coach annotations (the only CRDT)

Coach annotations on a session (text notes on a shot, drawn telestrations on a video frame, voice memos) are mutable and edited concurrently by the coach and the athlete. We use **Automerge 2.0** for the `annotations` document only:

- One Automerge document per session.
- Automerge's Rust core lives inside `aimvision-camera-core` and is exposed via UniFFI (control-plane FFI; this is not a hot path).
- The document is synced as opaque binary blobs; the backend stores blobs and rebroadcasts.
- We do **not** CRDT the entire database. CRDT-everywhere is the trap; CRDT-on-the-mutable-document is the right scalpel ([Mobile review §Sync engine](../reviews/04-mobile-app-builder.md)).

## Consequences

**Easier:**

- Sync is a streaming append — no merge, no conflict resolution, no LWW gymnastics.
- The post-session pipeline is a pure function of the event stream + model versions; rerunning with a new model is "replay the workflow."
- Audit and compliance are baked in: the event log is the audit log for shot-level activity.
- Longitudinal analytics is a second projection over the same data, not a separate ETL.
- Schema evolution is structurally safe: new event types and additive payload fields do not break old consumers.

**Harder:**

- Storage is monotonic — events accumulate. We mitigate with TimescaleDB compression on `shot_events` after 90 days (event payloads compress 10-20× under TimescaleDB's columnar compression).
- Developers used to mutable rows must learn the projection-rebuild idiom. We mitigate by writing the projection-rebuild workflow once (in Temporal) and treating it as a library.
- Erasure (GDPR/PDPL right-to-be-forgotten) requires a hard-delete path on the event log, which violates the "append-only" pure form. We accept the violation: the `ErasureWorkflow` is the only DELETE-capable code path, gated on a service role with audit logging. Detail in `docs/compliance/gdpr-erasure-flow.md`.
- Schema migrations on event payloads must remain backward-compatible at read time. We enforce this by versioning every payload schema and never mutating an old event.

**Reversibility:** Low. Removing event sourcing later means rebuilding the projection layer as the source of truth, which is a multi-quarter project. The choice is bounded by being made in Sprint 5 (per [Mobile review §Sprint resequencing](../reviews/04-mobile-app-builder.md)) before the schema solidifies.

## Alternatives Considered

1. **Mutable rows + LWW conflict resolution.** Rejected because shot events are facts: a "shot detected at t=12.3 with audio confidence 0.97" is not an opinion someone can edit. Edits as new events are semantically clearer and operationally simpler.
2. **CRDT on the entire database (Yjs / Automerge over every table).** Rejected per [Mobile review §Sync engine](../reviews/04-mobile-app-builder.md) — overkill, expensive, and the rules for shot events are LWW-trivial because they are facts.
3. **Kafka or Pulsar as the event log.** Rejected on operability grounds for V1. Postgres-as-event-log is sufficient at our event rate (estimated 1M events/day at 10k DAU) and avoids running another stateful service. Re-evaluate if event volume exceeds 100M/day.
4. **Materialize/RisingWave for incremental projections.** Interesting but premature. TimescaleDB hypertable refresh policies plus Temporal workflows give us the same shape with less operational surface.

## References

- [Software Architect review §Missing Concerns (event sourcing) and §High-Leverage Redesigns #2](../reviews/03-software-architect.md)
- [Mobile App Builder review §Sync engine](../reviews/04-mobile-app-builder.md) — Automerge for annotations only.
- [ADR-0007: Temporal orchestration](0007-temporal-orchestration.md) — projection-rebuild workflows live here.
- [ADR-0004: Multi-tenancy via RLS](0004-multi-tenancy-rls.md) — RLS on the event table.
- Greg Young, "CQRS Documents": <https://cqrs.files.wordpress.com/2010/11/cqrs_documents.pdf>
- Linear sync engine: <https://linear.app/blog/scaling-the-linear-sync-engine>
- ElectricSQL: <https://electric-sql.com/>
- Riffle: <https://riffle.systems/essays/prelude/>
- Automerge 2.0: <https://automerge.org/>
