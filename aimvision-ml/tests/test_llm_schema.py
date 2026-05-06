"""Validate the LLM-output JSON Schema parsed from the markdown spec."""

from __future__ import annotations

import copy

import jsonschema
import pytest

from aimvision_ml.llm.schema import load_schema, validate


def _valid_note() -> dict[str, object]:
    """Mirrors the example block in docs/llm-coaching-notes-schema.md."""
    return {
        "schema_version": "1.0",
        "session_id": "8b1f0b7a-2c5a-4f1f-9d9b-3e9b1f0b7a2c",
        "athlete_pseudonym": "Athlete-7421",
        "headline": "Solid skeet session — hit rate up four points. Stay on the gun longer.",
        "top_diagnostics": [
            {
                "category": "head_lift",
                "confidence": 0.81,
                "evidence_shot_ids": ["shot_12", "shot_19"],
                "coaching_action": "Cheek to the stock through the break.",
            }
        ],
        "notable_shots": [
            {
                "shot_id": "shot_07",
                "reason": "exemplar_form",
                "caption": "Clean mount, sustained swing, decisive break.",
            }
        ],
        "compared_to_history": {
            "sessions_compared": 5,
            "deltas": {
                "outcome_hit_rate": {"current": 0.78, "delta_vs_baseline": 0.04},
                "head_lift_rate": {"current": 0.12, "delta_vs_baseline": 0.03},
                "stopped_gun_rate": {"current": 0.06, "delta_vs_baseline": -0.02},
                "mount_jerk_p50": {"current": 14.2, "delta_vs_baseline": -1.1},
                "swing_velocity_p50": {"current": 42.7, "delta_vs_baseline": 0.8},
            },
        },
        "recommended_drills": ["drill_bead_stare_station_1"],
        "tone_mode": "athlete",
        "language": "en-US",
        "confidence_overall": 0.74,
        "verifier_passed": True,
        "model_version": "deepseek-14b-q4km+lora-franco-v0.7",
        "taxonomy_version": "0.9-draft",
        "generated_at": "2026-05-06T18:42:11Z",
        "degraded": False,
    }


def test_schema_loads_from_doc() -> None:
    schema = load_schema()
    assert schema["$id"].startswith("https://aimvision.app/")
    assert "headline" in schema["required"]
    # The category enum mirrors the taxonomy doc.
    cat_enum = schema["properties"]["top_diagnostics"]["items"]["properties"]["category"]["enum"]
    assert "head_lift" in cat_enum
    assert "stopped_gun" in cat_enum


def test_valid_note_passes_validation() -> None:
    note = _valid_note()
    validate(note)  # should not raise


def test_missing_headline_fails() -> None:
    note = _valid_note()
    del note["headline"]
    with pytest.raises(jsonschema.ValidationError):
        validate(note)


def test_unknown_category_fails() -> None:
    note = _valid_note()
    diagnostics = copy.deepcopy(note["top_diagnostics"])
    assert isinstance(diagnostics, list)
    diagnostics[0]["category"] = "bogus_category"
    note["top_diagnostics"] = diagnostics
    with pytest.raises(jsonschema.ValidationError):
        validate(note)


def test_verifier_failed_must_be_silent() -> None:
    # If verifier_passed=false, the schema's allOf forces tone_mode=silent
    # and top_diagnostics empty. A note that violates the conditional fails.
    note = _valid_note()
    note["verifier_passed"] = False
    # tone_mode is still "athlete" → must fail.
    with pytest.raises(jsonschema.ValidationError):
        validate(note)


def test_athlete_pseudonym_pattern_enforced() -> None:
    note = _valid_note()
    note["athlete_pseudonym"] = "RealName"
    with pytest.raises(jsonschema.ValidationError):
        validate(note)
