"""PII stripping: name/email/phone replacement, daily-stable pseudonyms."""

from __future__ import annotations

import re
from datetime import date

from aimvision_ml.llm.pii import pseudonym_for, strip_pii

_PSEUDONYM_RE = re.compile(r"^Athlete-\d{7}$")


def test_pseudonym_matches_schema_pattern() -> None:
    pseudo = pseudonym_for("athlete-uuid-1234")
    assert _PSEUDONYM_RE.match(pseudo), pseudo


def test_pseudonym_is_stable_within_a_day() -> None:
    today = date(2026, 5, 6)
    a = pseudonym_for("athlete-uuid-1234", today=today)
    b = pseudonym_for("athlete-uuid-1234", today=today)
    assert a == b


def test_pseudonym_changes_across_days() -> None:
    a = pseudonym_for("athlete-uuid-1234", today=date(2026, 5, 6))
    b = pseudonym_for("athlete-uuid-1234", today=date(2026, 5, 7))
    assert a != b


def test_pseudonym_differs_per_athlete() -> None:
    today = date(2026, 5, 6)
    a = pseudonym_for("athlete-A", today=today)
    b = pseudonym_for("athlete-B", today=today)
    assert a != b


def test_strip_pii_replaces_name_and_emails_and_phones() -> None:
    today = date(2026, 5, 6)
    text = "Yousef called from +20 100 123 4567 and emailed yousef@example.com."
    clean, pseudo = strip_pii(text, athlete_id="athlete-1", athlete_name="Yousef", today=today)
    assert "Yousef" not in clean
    assert pseudo in clean
    assert "@example.com" not in clean
    assert "100 123 4567" not in clean
    assert "[email-redacted]" in clean
    assert "[phone-redacted]" in clean


def test_strip_pii_is_stable_across_calls_same_day() -> None:
    today = date(2026, 5, 6)
    a, p_a = strip_pii("hi Maria", athlete_id="athlete-7", athlete_name="Maria", today=today)
    b, p_b = strip_pii("Maria again", athlete_id="athlete-7", athlete_name="Maria", today=today)
    assert p_a == p_b
    assert p_a in a and p_b in b


def test_strip_pii_handles_no_name() -> None:
    today = date(2026, 5, 6)
    clean, pseudo = strip_pii("call me at 555-867-5309", athlete_id="x", today=today)
    assert "[phone-redacted]" in clean
    assert _PSEUDONYM_RE.match(pseudo)


def test_strip_pii_does_not_redact_short_year_numbers() -> None:
    today = date(2026, 5, 6)
    clean, _ = strip_pii("year 2026 was good", athlete_id="x", today=today)
    assert "2026" in clean  # 4-digit standalone year is below the phone regex floor
