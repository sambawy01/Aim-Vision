"""Coaching-note DTOs.

The post-session worker generates a structured note (validated
against docs/llm-coaching-notes-schema.md by the ML verifier) and
POSTs the whole object here. The backend stores it verbatim in
`note_json` and denormalizes a few fields for list views; it does
not re-run the full JSON-Schema validation (that's the producer's
job — re-validating would couple the backend to the schema doc).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Top-level keys the backend reads off the note to denormalize. The
# producer guarantees these (the schema marks them required); we
# validate their presence at the endpoint and 422 if missing.
REQUIRED_NOTE_KEYS = (
    "session_id",
    "headline",
    "tone_mode",
    "language",
    "verifier_passed",
    "degraded",
    "confidence_overall",
    "model_version",
    "taxonomy_version",
    "generated_at",
)


class CoachingNoteIn(BaseModel):
    """Payload for POST .../coaching-note: the full structured note.

    Accepted as a free-form object (the producer already validated it
    against the JSON Schema). The endpoint checks the required keys are
    present and that `session_id` matches the path before storing.
    """

    note: dict[str, Any] = Field(
        ...,
        description="The complete structured coaching note (coaching-notes schema v1).",
    )


class CoachingNoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    headline: str
    tone_mode: str
    language: str
    verifier_passed: bool
    degraded: bool
    confidence_overall: float
    model_version: str
    taxonomy_version: str
    generated_at: datetime
    created_at: datetime
    # The full structured note, returned under `note` (mapped from the
    # ORM `note_json` column via the validation alias).
    note: dict[str, Any] = Field(validation_alias="note_json")
