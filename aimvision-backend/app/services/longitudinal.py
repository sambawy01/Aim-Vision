"""On-demand longitudinal rollups for an athlete.

Computes per-session diagnostic-atom rates from the shot-event stream
(the `diagnostic.head_inference` events the post-session pipeline
posts, whose payload is `{atom: probability}`). A shot is counted as
exhibiting an atom when its probability meets `ATOM_PRESENT_THRESHOLD`.

This is computed in Python after fetching rows rather than in SQL, so
it stays portable across SQLite (tests) and Postgres (prod) without
JSON-operator differences. Volumes are modest (a session is ~tens to
low-hundreds of shots), so this is fine for V1; the ADR-0007
TimescaleDB projection is the scale path.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session as SessionModel
from app.models.session import Shot, ShotEvent

# Event kind the diagnostic head posts per shot (see
# aimvision_ml.ingest.post_session).
DIAGNOSTIC_EVENT_KIND = "diagnostic.head_inference"
# A shot exhibits an atom when its predicted probability is at least
# this. A single fixed threshold keeps the rollup simple; per-atom
# abstention thresholds live in the taxonomy and can refine this later.
ATOM_PRESENT_THRESHOLD = 0.5


@dataclass(frozen=True, slots=True)
class _SessionRollup:
    session_id: str
    started_at: object
    shot_count: int
    diagnostic_rates: dict[str, float]


async def compute_athlete_progress(
    db: AsyncSession,
    *,
    tenant_id: str,
    athlete_id: str,
    last_n: int,
) -> list[_SessionRollup]:
    """Return per-session rollups for the athlete's most-recent
    `last_n` sessions, ordered oldest -> newest. Empty list if the
    athlete has no sessions in the tenant."""
    # Most-recent N sessions for the athlete in this tenant.
    sess_rows = (
        (
            await db.execute(
                select(SessionModel)
                .where(
                    SessionModel.tenant_id == tenant_id,
                    SessionModel.athlete_user_id == athlete_id,
                )
                .order_by(SessionModel.started_at.desc())
                .limit(max(1, min(last_n, 50)))
            )
        )
        .scalars()
        .all()
    )
    if not sess_rows:
        return []

    session_ids = [s.id for s in sess_rows]

    # All shots for those sessions.
    shots = (await db.execute(select(Shot).where(Shot.session_id.in_(session_ids)))).scalars().all()
    shots_by_session: dict[str, list[Shot]] = defaultdict(list)
    for sh in shots:
        shots_by_session[sh.session_id].append(sh)
    shot_ids = [sh.id for sh in shots]

    # Diagnostic events for those shots, keyed by shot_id.
    diag_by_shot: dict[str, dict[str, float]] = {}
    if shot_ids:
        events = (
            (
                await db.execute(
                    select(ShotEvent).where(
                        ShotEvent.shot_id.in_(shot_ids),
                        ShotEvent.event_kind == DIAGNOSTIC_EVENT_KIND,
                    )
                )
            )
            .scalars()
            .all()
        )
        for ev in events:
            payload = ev.payload if isinstance(ev.payload, dict) else {}
            # If a shot has multiple diagnostic events, keep the latest
            # by produced_at.
            prev = diag_by_shot.get(ev.shot_id)
            if prev is None:
                diag_by_shot[ev.shot_id] = {
                    k: float(v) for k, v in payload.items() if isinstance(v, int | float)
                }

    rollups: list[_SessionRollup] = []
    # sess_rows is newest-first; emit oldest-first.
    for s in reversed(sess_rows):
        sh_list = shots_by_session.get(s.id, [])
        shot_count = len(sh_list)
        atom_hits: dict[str, int] = defaultdict(int)
        for sh in sh_list:
            probs = diag_by_shot.get(sh.id, {})
            for atom, prob in probs.items():
                if prob >= ATOM_PRESENT_THRESHOLD:
                    atom_hits[atom] += 1
        rates = (
            {atom: hits / shot_count for atom, hits in atom_hits.items()} if shot_count > 0 else {}
        )
        rollups.append(
            _SessionRollup(
                session_id=s.id,
                started_at=s.started_at,
                shot_count=shot_count,
                diagnostic_rates=rates,
            )
        )
    return rollups


def compute_deltas(rollups: list[_SessionRollup]) -> dict[str, tuple[float, float, float]]:
    """For each atom present in the latest session, return
    (current, baseline_mean_of_prior, delta). Empty if <2 sessions."""
    if len(rollups) < 2:
        return {}
    latest = rollups[-1]
    prior = rollups[:-1]
    out: dict[str, tuple[float, float, float]] = {}
    for atom, current in latest.diagnostic_rates.items():
        prior_vals = [r.diagnostic_rates.get(atom, 0.0) for r in prior]
        baseline = sum(prior_vals) / len(prior_vals)
        out[atom] = (current, baseline, current - baseline)
    return out
