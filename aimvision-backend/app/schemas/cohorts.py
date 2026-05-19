"""Cohort listing DTOs.

Cohorts (federation talent groups, club squads) — see
docs/architecture-overview.md. The federation dashboard already
has its own cohort serializer (TalentCohortOut) embedded in the
overview response; this module exposes the standalone listing
that club-coach + federation-admin UI flows consume.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CohortOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    org_id: str
    tenant_id: str
    athletes_count: int
