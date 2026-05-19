"""Federation-tier dashboard DTOs — Sprint 4 EPIC 4.5 backend pair to
the web `/app/federation` route (PR #38).

The web client (aimvision-web/src/services/federation.ts) expects
camelCase keys on the wire. We keep snake_case in Python and serialize
via pydantic's `to_camel` alias generator with `populate_by_name=True`
so model code can construct instances using natural Python identifiers.
The FastAPI router emits aliases by passing `response_model_by_alias=True`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Out(BaseModel):
    """Shared base: explicit camelCase aliases on output, snake_case in
    Python. We don't use `alias_generator=to_camel` because its `.title()`
    pass turns ``30d`` into ``30D``; the web client's wire contract
    (aimvision-web/src/services/federation.ts) uses lowercase-`d`.
    """

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class TalentCohortOut(_Out):
    id: str
    name: str
    athletes_count: int = Field(serialization_alias="athletesCount")
    # Median sessions per athlete in the cohort, last 30 days. Used by
    # the dashboard to flag cohorts that are under-training.
    median_sessions_per_30d: float = Field(serialization_alias="medianSessionsPer30d")


class FederationOverviewOut(_Out):
    federation_id: str = Field(serialization_alias="federationId")
    federation_name: str = Field(serialization_alias="federationName")
    athletes_total: int = Field(serialization_alias="athletesTotal")
    clubs_active: int = Field(serialization_alias="clubsActive")
    sessions_last_30d: int = Field(serialization_alias="sessionsLast30d")
    # Average sessions per athlete in the last 30 days; the headline
    # activity number on the dashboard card. Zero when no athletes are
    # registered (avoids a divide-by-zero leak).
    engagement_rate: float = Field(serialization_alias="engagementRate")
    talent_cohorts: list[TalentCohortOut] = Field(serialization_alias="talentCohorts")


ClubStatus = Literal["active", "paused", "pending_setup"]


class ClubMembershipOut(_Out):
    club_id: str = Field(serialization_alias="clubId")
    club_name: str = Field(serialization_alias="clubName")
    athletes_count: int = Field(serialization_alias="athletesCount")
    coaches_count: int = Field(serialization_alias="coachesCount")
    # ISO-8601 timestamp of the most recent session captured by this
    # club, or null if the club has never recorded one.
    last_session_at: datetime | None = Field(serialization_alias="lastSessionAt")
    status: ClubStatus
