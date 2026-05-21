"""Coaching-note generation orchestrator (ml-architecture.md §11).

Ties together the existing pieces — `prompt.build_prompt`,
`schema.validate`, `verifier.deterministic_verify`,
`pii.pseudonym_for` — behind one entry point, with the
retry-then-degrade policy the spec requires:

  generate → schema-validate → deterministic-verify
    → on failure, regenerate (max 2 retries)
    → still failing (or no LLM host): return a schema-valid
      DEGRADED note (verifier_passed=false, tone_mode=silent,
      empty top_diagnostics, degraded=true)

Server-authoritative fields (session_id, athlete_pseudonym,
model_version, taxonomy_version, generated_at, degraded) are stamped
by this orchestrator, never trusted from the model output — so a
hallucinated session id or version can't slip through.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

import jsonschema

from aimvision_ml.llm.client import LlmClient, LlmUnavailable
from aimvision_ml.llm.pii import pseudonym_for
from aimvision_ml.llm.prompt import _SYSTEM_PROMPT, PromptInputs, build_prompt
from aimvision_ml.llm.schema import validate as validate_schema
from aimvision_ml.llm.verifier import deterministic_verify

SCHEMA_VERSION = "1.0"


def _now_iso(now: datetime | None) -> str:
    return (now or datetime.now(UTC)).isoformat()


def build_degraded_note(
    *,
    session_id: str,
    athlete_pseudonym: str,
    language: str,
    model_version: str,
    taxonomy_version: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """A schema-valid note carrying no diagnostics.

    Used when no LLM host is available or generation fails the
    verifier twice. Satisfies the schema's `allOf`: verifier_passed
    False ⇒ tone_mode silent + empty top_diagnostics.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id,
        "athlete_pseudonym": athlete_pseudonym,
        "headline": (
            "Session recorded. Detailed coaching analysis is unavailable for this session."
        ),
        "top_diagnostics": [],
        "notable_shots": [],
        "compared_to_history": {"sessions_compared": 0, "deltas": {}},
        "recommended_drills": [],
        "tone_mode": "silent",
        "language": language,
        "confidence_overall": 0.0,
        "verifier_passed": False,
        "model_version": model_version,
        "taxonomy_version": taxonomy_version,
        "generated_at": _now_iso(now),
        "degraded": True,
    }


def _stamp_server_fields(
    note: dict[str, Any],
    *,
    session_id: str,
    athlete_pseudonym: str,
    model_version: str,
    taxonomy_version: str,
    now: datetime | None,
) -> None:
    """Overwrite fields the model must not be trusted to set."""
    note["schema_version"] = SCHEMA_VERSION
    note["session_id"] = session_id
    note["athlete_pseudonym"] = athlete_pseudonym
    note["model_version"] = model_version
    note["taxonomy_version"] = taxonomy_version
    note["generated_at"] = _now_iso(now)
    note["degraded"] = False


def generate_coaching_note(
    inputs: PromptInputs,
    client: LlmClient | None,
    *,
    valid_shot_ids: Iterable[str],
    valid_drill_ids: Iterable[str],
    model_version: str,
    taxonomy_version: str,
    max_retries: int = 2,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Generate a verified coaching note, or a degraded one.

    `client=None` (no model host) → degraded immediately. Otherwise
    generate + validate + verify, retrying up to `max_retries` times,
    then degrade. The returned note always passes `schema.validate`.
    """
    pseudonym = pseudonym_for(inputs.athlete_id)
    shot_ids = set(valid_shot_ids)
    drill_ids = set(valid_drill_ids)

    def _degraded() -> dict[str, Any]:
        return build_degraded_note(
            session_id=inputs.session_id,
            athlete_pseudonym=pseudonym,
            language=inputs.language,
            model_version=model_version,
            taxonomy_version=taxonomy_version,
            now=now,
        )

    if client is None:
        return _degraded()

    prompt = build_prompt(inputs)
    for _ in range(max_retries + 1):
        try:
            raw = client.generate(_SYSTEM_PROMPT, prompt)
        except LlmUnavailable:
            return _degraded()

        try:
            note = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(note, dict):
            continue

        _stamp_server_fields(
            note,
            session_id=inputs.session_id,
            athlete_pseudonym=pseudonym,
            model_version=model_version,
            taxonomy_version=taxonomy_version,
            now=now,
        )

        # The deterministic gate — not the model — owns verifier_passed.
        # Set it True provisionally so a note WITH diagnostics is
        # schema-valid: the schema's allOf only constrains the False
        # case (verifier_passed=false ⇒ tone_mode=silent + empty
        # top_diagnostics). The reference-integrity check below then
        # confirms the note or rejects it (→ retry/degrade).
        note["verifier_passed"] = True
        try:
            validate_schema(note)
        except jsonschema.ValidationError:
            continue

        report = deterministic_verify(note, valid_shot_ids=shot_ids, valid_drill_ids=drill_ids)
        if report.passed:
            return note
        # else: regenerate

    # Exhausted retries → honest degraded note.
    return _degraded()
