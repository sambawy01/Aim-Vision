"""PII stripping for LLM prompts.

Cite docs/llm-coaching-notes-schema.md ("Prompt-injection defense" #1)
and docs/ml-architecture.md §11 ("Privacy. Athlete name and direct
identifiers are stripped before prompts and replaced with stable
per-session pseudonyms"). The LLM never sees PII.

The pseudonym is a BLAKE2b digest of (athlete_id, daily_salt) — stable
within a day for retrieval-augmented context, fresh across days so we
don't leak long-lived linkable identifiers across sessions.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, date

# Email + phone patterns. Conservative: false positives are fine (we'd
# rather over-redact); false negatives are not (the LLM would see PII).
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# Matches typical international, dashed, dotted, paren-grouped numbers.
# Requires at least 7 digits so it doesn't redact bare years.
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?\d{1,3}[\s\-.]?)?(?:\(\d{1,4}\)[\s\-.]?)?(?:\d[\s\-.]?){6,12}\d(?!\d)"
)
_EMAIL_PLACEHOLDER = "[email-redacted]"
_PHONE_PLACEHOLDER = "[phone-redacted]"

_PSEUDONYM_PREFIX = "Athlete-"


def daily_salt(today: date | None = None) -> str:
    """Salt rotated daily; same day = same pseudonym. UTC for stability."""
    d = today if today is not None else date.today()  # noqa: DTZ011 (UTC handled below)
    return d.isoformat()


def pseudonym_for(athlete_id: str, today: date | None = None) -> str:
    """Stable per-day pseudonym matching the schema pattern.

    Schema constraint: ``^Athlete-[0-9]{4,8}$``. We hash (id, daily_salt)
    with BLAKE2b and reduce to a 7-digit decimal in [1_000_000, 9_999_999].
    """
    d = today if today is not None else _utc_today()
    digest = hashlib.blake2b(
        f"{athlete_id}|{daily_salt(d)}".encode(),
        digest_size=8,
    ).digest()
    n = int.from_bytes(digest, "big") % 9_000_000 + 1_000_000  # 7 digits
    return f"{_PSEUDONYM_PREFIX}{n}"


def _utc_today() -> date:
    """UTC today; isolates from local-timezone clock skew."""
    from datetime import datetime

    return datetime.now(UTC).date()


def strip_pii(
    text: str,
    *,
    athlete_id: str,
    athlete_name: str | None = None,
    today: date | None = None,
) -> tuple[str, str]:
    """Replace athlete name + emails + phones; return ``(clean, pseudonym)``.

    The pseudonym is also the substitute for the athlete's name in the
    text; consistency is what makes RAG over the athlete's prior notes
    work without actually exposing PII.
    """
    pseudonym = pseudonym_for(athlete_id, today=today)
    # Order matters: redact emails + phones BEFORE substituting the name.
    # Otherwise the digits in the pseudonym (Athlete-XXXXXXX) would be
    # re-matched by the phone regex on the second pass.
    cleaned = _EMAIL_RE.sub(_EMAIL_PLACEHOLDER, text)
    cleaned = _PHONE_RE.sub(_PHONE_PLACEHOLDER, cleaned)
    if athlete_name:
        # Word-boundary replace; case-insensitive.
        pattern = re.compile(rf"\b{re.escape(athlete_name)}\b", re.IGNORECASE)
        cleaned = pattern.sub(pseudonym, cleaned)
    return cleaned, pseudonym
