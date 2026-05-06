"""Sample-provenance tracking.

Cite docs/ml-architecture.md §10 ("continual learning + provenance"):
every training sample carries (athlete_id, session_id, source, captured_at,
consent_flags). Re-training jobs filter on consent flags at the data-loader
layer. This is a compliance hard requirement, not a feature toggle.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class ProvenanceRecord(BaseModel):
    """One sample's provenance + consent state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    athlete_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    sample_path: str = Field(min_length=1)
    sample_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{32,128}$")]
    consent_version: str = Field(min_length=1)
    ml_training_consent: bool
    captured_at: datetime
    source: str = Field(default="hero13", description='Capture source ("hero13", "phone_mic", ...)')


def filter_for_training(
    records: Sequence[ProvenanceRecord],
    excluded_hashes: Iterable[str] = (),
) -> list[ProvenanceRecord]:
    """Apply the consent + erasure filter.

    Drops records that:
      - have ``ml_training_consent=False`` (minor-data opt-out is the
        default per Compliance review), OR
      - have a ``sample_hash`` in the exclusion list (right-to-erasure).
    """
    excluded = set(excluded_hashes)
    return [r for r in records if r.ml_training_consent and r.sample_hash not in excluded]
