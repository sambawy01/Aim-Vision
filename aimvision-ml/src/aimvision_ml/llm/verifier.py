"""Second-pass LLM verifier.

Cite docs/ml-architecture.md §11 ("Verifier pass") and
docs/llm-coaching-notes-schema.md ("Verifier pass"). The verifier:

1. Validates the structured note against the JSON Schema.
2. Cross-checks every ``shot_id`` against the session ledger.
3. Cross-checks every ``drill_id`` against the drill library.
4. Asks a second LLM call: "do the cited features actually support each
   diagnostic at the stated confidence?" — that LLM call lives in the
   backend service; this module is the deterministic pre-LLM check.

If any deterministic check fails, the note is rejected without calling the
verifier LLM at all — saves tokens + latency.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import jsonschema

from aimvision_ml.llm.schema import validate as validate_schema


@dataclass(frozen=True)
class VerifierFailure:
    """One reason the note failed verification."""

    code: str
    detail: str


@dataclass(frozen=True)
class VerifierReport:
    """Outcome of the deterministic verifier checks."""

    passed: bool
    failures: list[VerifierFailure]


def deterministic_verify(
    note: dict[str, Any],
    *,
    valid_shot_ids: Iterable[str],
    valid_drill_ids: Iterable[str],
) -> VerifierReport:
    """Run schema + reference-integrity checks. No LLM call here.

    The backend wraps this; on failure (non-empty `failures`), the
    backend regenerates (max 2 retries) before falling back to the
    silent/degraded note.
    """
    failures: list[VerifierFailure] = []

    try:
        validate_schema(note)
    except jsonschema.ValidationError as exc:
        failures.append(VerifierFailure(code="schema", detail=exc.message))
        return VerifierReport(passed=False, failures=failures)

    shot_ids = set(valid_shot_ids)
    drill_ids = set(valid_drill_ids)

    for diag in note.get("top_diagnostics", []):
        for sid in diag.get("evidence_shot_ids", []):
            if sid not in shot_ids:
                failures.append(
                    VerifierFailure(code="unknown_shot_id", detail=f"{sid!r} not in session ledger")
                )

    for n in note.get("notable_shots", []):
        sid = n.get("shot_id")
        if sid not in shot_ids:
            failures.append(
                VerifierFailure(code="unknown_shot_id", detail=f"{sid!r} not in session ledger")
            )

    for did in note.get("recommended_drills", []):
        if did not in drill_ids:
            failures.append(
                VerifierFailure(code="unknown_drill_id", detail=f"{did!r} not in drill library")
            )

    return VerifierReport(passed=not failures, failures=failures)
