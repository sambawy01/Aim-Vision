"""5%-shadow-routing helper.

Cite docs/ml-architecture.md §13. Predictions from the candidate model
are stored separately and never surfaced to athletes; the win condition
is sustained beat over 2 weeks (or ~1000 production shots, whichever is
later) on stratified macro-F1, with no single-class regression > 0.02 and
calibration + bias gates passing.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

DEFAULT_SHADOW_FRACTION = 0.05


@dataclass(frozen=True)
class RoutingDecision:
    """Outcome of `should_shadow` for one shot."""

    run_shadow: bool
    bucket: int  # 0–999, for stratified analysis later


def should_shadow(
    shot_id: str,
    *,
    fraction: float = DEFAULT_SHADOW_FRACTION,
    salt: str = "shadow_v1",
) -> RoutingDecision:
    """Deterministic 5% sampling keyed off (shot_id, salt).

    Determinism matters: the same shot must route the same way on retry
    so the registry comparison is apples-to-apples. Hash bucket modulo
    1000 gives 0.1% resolution; default fraction maps to bucket < 50.
    """
    if not 0.0 <= fraction <= 1.0:
        raise ValueError("fraction must be in [0, 1]")
    h = hashlib.blake2b(f"{salt}:{shot_id}".encode(), digest_size=8).digest()
    bucket = int.from_bytes(h, "big") % 1000
    threshold = int(round(fraction * 1000))
    return RoutingDecision(run_shadow=bucket < threshold, bucket=bucket)
