"""Tests for the coaching-note generation orchestrator.

No live LLM host: a fake `LlmClient` returns canned JSON. Asserts the
retry-then-degrade policy, server-field stamping, schema validity of
both the happy and degraded paths, and the no-host gate.
"""

from __future__ import annotations

import json
from typing import Any

import jsonschema
import pytest

from aimvision_ml.llm import (
    PromptInputs,
    build_degraded_note,
    generate_coaching_note,
)
from aimvision_ml.llm.client import LlmUnavailable
from aimvision_ml.llm.schema import validate as validate_schema

VALID_SHOT_IDS = ["shot_12", "shot_19", "shot_22"]
VALID_DRILL_IDS = ["drill_bead_stare", "drill_swing_through"]


def _inputs() -> PromptInputs:
    return PromptInputs(
        athlete_id="athlete-xyz",
        athlete_name="Real Name",
        session_id="8b1f0b7a-2c5a-4f1f-9d9b-3e9b1f0b7a2c",
        feature_summary_json="{}",
        athlete_goal_input="break more clays on station 4",
        retrieved_notes=[],
        tone_mode="coach",
        language="en-US",
    )


def _good_note() -> dict[str, Any]:
    """A note the LLM might return — references only valid shot/drill ids.
    Server fields are deliberately wrong/garbage to prove the orchestrator
    overwrites them."""
    return {
        "schema_version": "9.9",  # wrong on purpose
        "session_id": "ffffffff-ffff-ffff-ffff-ffffffffffff",  # wrong on purpose
        "athlete_pseudonym": "Athlete-0000",  # wrong on purpose
        "headline": "Solid session — head lift is the next thing to fix on the left stations.",
        "top_diagnostics": [
            {
                "category": "head_lift",
                "confidence": 0.81,
                "evidence_shot_ids": ["shot_12", "shot_19"],
                "coaching_action": "Cheek to the stock through the break; 10 bead-stare reps.",
            }
        ],
        "notable_shots": [
            {"shot_id": "shot_22", "reason": "outlier_outcome", "caption": "Stopped the gun here."}
        ],
        "compared_to_history": {"sessions_compared": 3, "deltas": {}},
        "recommended_drills": ["drill_bead_stare"],
        "tone_mode": "coach",
        "language": "en-US",
        "confidence_overall": 0.74,
        "verifier_passed": False,  # the model's guess; orchestrator decides
        "model_version": "fabricated",  # wrong on purpose
        "taxonomy_version": "fabricated",  # wrong on purpose
        "generated_at": "2000-01-01T00:00:00Z",  # wrong on purpose
        "degraded": True,  # wrong on purpose
    }


class _FakeClient:
    """Returns a queued sequence of raw responses (or raises)."""

    def __init__(self, responses: list[str | Exception]) -> None:
        self._responses = responses
        self.calls = 0

    def generate(self, system: str, prompt: str) -> str:
        self.calls += 1
        r = self._responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def test_no_client_returns_degraded_note() -> None:
    note = generate_coaching_note(
        _inputs(),
        None,
        valid_shot_ids=VALID_SHOT_IDS,
        valid_drill_ids=VALID_DRILL_IDS,
        model_version="m1",
        taxonomy_version="t1",
    )
    validate_schema(note)  # must be schema-valid
    assert note["degraded"] is True
    assert note["verifier_passed"] is False
    assert note["tone_mode"] == "silent"
    assert note["top_diagnostics"] == []
    # Server fields are stamped from the call, not the (absent) model.
    assert note["session_id"] == _inputs().session_id
    assert note["model_version"] == "m1"
    assert note["athlete_pseudonym"].startswith("Athlete-")


def test_happy_path_validates_verifies_and_stamps_server_fields() -> None:
    client = _FakeClient([json.dumps(_good_note())])
    note = generate_coaching_note(
        _inputs(),
        client,
        valid_shot_ids=VALID_SHOT_IDS,
        valid_drill_ids=VALID_DRILL_IDS,
        model_version="deepseek-14b@7",
        taxonomy_version="taxonomy@2026-05-06",
    )
    validate_schema(note)
    assert client.calls == 1
    assert note["verifier_passed"] is True
    assert note["degraded"] is False
    # Server-authoritative fields overwrote the model's garbage.
    assert note["schema_version"] == "1.0"
    assert note["session_id"] == _inputs().session_id
    assert note["model_version"] == "deepseek-14b@7"
    assert note["taxonomy_version"] == "taxonomy@2026-05-06"
    assert note["generated_at"] != "2000-01-01T00:00:00Z"
    # The real diagnostics survived.
    assert note["top_diagnostics"][0]["category"] == "head_lift"


def test_unknown_shot_id_fails_verifier_then_degrades() -> None:
    """A note citing a shot not in the ledger fails deterministic verify
    every attempt → degraded after retries."""
    bad = _good_note()
    bad["top_diagnostics"][0]["evidence_shot_ids"] = ["shot_9999"]  # not in ledger
    client = _FakeClient([json.dumps(bad)] * 3)  # 1 + 2 retries
    note = generate_coaching_note(
        _inputs(),
        client,
        valid_shot_ids=VALID_SHOT_IDS,
        valid_drill_ids=VALID_DRILL_IDS,
        model_version="m",
        taxonomy_version="t",
        max_retries=2,
    )
    validate_schema(note)
    assert client.calls == 3  # exhausted retries
    assert note["degraded"] is True
    assert note["tone_mode"] == "silent"


def test_retries_then_succeeds_on_second_attempt() -> None:
    """First response is unparseable; second is a good note."""
    client = _FakeClient(["this is not json", json.dumps(_good_note())])
    note = generate_coaching_note(
        _inputs(),
        client,
        valid_shot_ids=VALID_SHOT_IDS,
        valid_drill_ids=VALID_DRILL_IDS,
        model_version="m",
        taxonomy_version="t",
    )
    validate_schema(note)
    assert client.calls == 2
    assert note["verifier_passed"] is True
    assert note["degraded"] is False


def test_llm_unavailable_mid_generation_degrades() -> None:
    client = _FakeClient([LlmUnavailable("host down")])
    note = generate_coaching_note(
        _inputs(),
        client,
        valid_shot_ids=VALID_SHOT_IDS,
        valid_drill_ids=VALID_DRILL_IDS,
        model_version="m",
        taxonomy_version="t",
    )
    validate_schema(note)
    assert note["degraded"] is True


def test_unknown_drill_id_fails_verifier() -> None:
    bad = _good_note()
    bad["recommended_drills"] = ["drill_does_not_exist"]
    client = _FakeClient([json.dumps(bad)] * 3)
    note = generate_coaching_note(
        _inputs(),
        client,
        valid_shot_ids=VALID_SHOT_IDS,
        valid_drill_ids=VALID_DRILL_IDS,
        model_version="m",
        taxonomy_version="t",
    )
    assert note["degraded"] is True


def test_build_degraded_note_is_schema_valid() -> None:
    note = build_degraded_note(
        session_id="8b1f0b7a-2c5a-4f1f-9d9b-3e9b1f0b7a2c",
        athlete_pseudonym="Athlete-1234",
        language="ar-EG",
        model_version="none",
        taxonomy_version="t1",
    )
    validate_schema(note)
    assert note["degraded"] is True


def test_garbage_note_that_never_validates_degrades() -> None:
    """If the model returns valid JSON that never passes the schema, the
    orchestrator degrades rather than emitting an invalid note."""
    client = _FakeClient([json.dumps({"not": "a note"})] * 3)
    note = generate_coaching_note(
        _inputs(),
        client,
        valid_shot_ids=VALID_SHOT_IDS,
        valid_drill_ids=VALID_DRILL_IDS,
        model_version="m",
        taxonomy_version="t",
    )
    # Must still return something schema-valid.
    validate_schema(note)
    assert note["degraded"] is True


def test_returned_note_never_violates_schema_invariants() -> None:
    """Property-ish: across paths, a verifier-failed note must be silent
    with no diagnostics (the schema allOf)."""
    note = generate_coaching_note(
        _inputs(),
        None,
        valid_shot_ids=VALID_SHOT_IDS,
        valid_drill_ids=VALID_DRILL_IDS,
        model_version="m",
        taxonomy_version="t",
    )
    if note["verifier_passed"] is False:
        assert note["tone_mode"] == "silent"
        assert note["top_diagnostics"] == []
    # And it always validates.
    try:
        validate_schema(note)
    except jsonschema.ValidationError as e:  # pragma: no cover
        pytest.fail(f"degraded note failed schema: {e}")
