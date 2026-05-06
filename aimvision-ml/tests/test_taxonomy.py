"""Sanity tests for the diagnostic taxonomy module."""

from __future__ import annotations

from aimvision_ml.taxonomy import (
    BRANCH_OF,
    DEFAULT_ABSTENTION_THRESHOLDS,
    Branch,
    DiagnosticCategory,
    all_categories,
    categories_for,
    to_athlete_tone,
    to_coach_tone,
)


def test_every_atom_has_a_branch() -> None:
    for cat in DiagnosticCategory:
        assert cat in BRANCH_OF, f"{cat} missing from BRANCH_OF"


def test_branch_categories_cover_taxonomy() -> None:
    seen: set[DiagnosticCategory] = set()
    for branch in Branch:
        for cat in categories_for(branch):
            assert cat not in seen, f"{cat} appears in two branches"
            seen.add(cat)
    assert seen == set(DiagnosticCategory)


def test_default_thresholds_are_in_unit_interval() -> None:
    for cat, t in DEFAULT_ABSTENTION_THRESHOLDS.items():
        assert 0.0 < t < 1.0, f"threshold for {cat} out of bounds: {t}"


def test_tone_helpers_return_non_empty_strings() -> None:
    for cat in all_categories():
        coach = to_coach_tone(cat)
        athlete = to_athlete_tone(cat)
        assert isinstance(coach, str) and coach
        assert isinstance(athlete, str) and athlete
        # Coach + athlete tone differ for the working canonical wording —
        # final lock is post-card-sort but they should never be identical
        # for a real coaching atom.
        assert coach != athlete, f"coach/athlete tone identical for {cat}"


def test_stopped_gun_in_swing_lead_branch() -> None:
    # Sprint-9 card-sort canonical-token decision is parked; whatever the
    # token is, the branch assignment is fixed.
    assert BRANCH_OF[DiagnosticCategory.STOPPED_GUN] == Branch.SWING_LEAD
