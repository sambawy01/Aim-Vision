"""Athlete longitudinal-progress DTOs.

Rolls up per-session diagnostic-atom rates from the shot-event stream
across an athlete's recent sessions. Feeds the coaching note's
`compared_to_history` and an athlete-progress view. Computed on demand
(the ADR-0007 TimescaleDB projection is a later optimisation).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class SessionProgressOut(BaseModel):
    """One session's rolled-up metrics."""

    session_id: str
    started_at: datetime
    shot_count: int
    # Per diagnostic atom: fraction of shots in the session whose
    # diagnostic event flagged that atom (prob >= threshold). Only
    # atoms that fired in the session appear.
    diagnostic_rates: dict[str, float]


class AtomDelta(BaseModel):
    """Latest-session value vs the prior-sessions baseline for one atom."""

    current: float
    baseline: float
    delta_vs_baseline: float


class AthleteProgressOut(BaseModel):
    athlete_id: str
    sessions_analyzed: int
    # Oldest -> newest within the analysed window.
    sessions: list[SessionProgressOut]
    # Per atom present in the latest session: current rate, the mean
    # over prior sessions (baseline), and the delta. Empty when there's
    # only one session (no baseline to compare against).
    deltas: dict[str, AtomDelta]
