"""Drill — the global coaching-drill catalog.

The LLM coaching note's `recommended_drills` reference `drill_id`s
that the verifier checks against this catalog (the model cannot
invent drills — see docs/llm-coaching-notes-schema.md "Verifier
pass"). Drills are a *global* reference catalog, not tenant-scoped:
the same canonical drill library is shared across all tenants, so
this table has no `tenant_id` and no RLS policy.

`id` matches the schema's drill pattern `^drill_[a-z0-9_]{3,40}$`.
`target_categories` lists the diagnostic-taxonomy atoms a drill
addresses, so a coach (or the LLM) can pick drills relevant to a
shot's diagnosis.
"""

from __future__ import annotations

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Drill(Base, TimestampMixin):
    """One coaching drill in the global catalog."""

    __tablename__ = "drills"

    # Stable slug id, e.g. "drill_bead_stare". Matches the coaching-note
    # schema's drill_id pattern so notes can reference it directly.
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Discipline this drill applies to: "trap" / "skeet" / "sporting" /
    # "all". A flat string keeps the catalog queryable without a join.
    discipline: Mapped[str] = mapped_column(String(32), nullable=False, default="all")
    # Diagnostic-taxonomy atoms this drill targets (DiagnosticCategory
    # values). JSON list; used to surface drills relevant to a diagnosis.
    target_categories: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
