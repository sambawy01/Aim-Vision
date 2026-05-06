"""Load + validate the LLM coaching-notes JSON Schema.

The schema source of truth is the embedded ```json``` block in
``docs/llm-coaching-notes-schema.md``. This module parses the markdown,
extracts the schema, and exposes a `validate()` that uses `jsonschema`.
This way the markdown spec stays the single source the LLM sees and we
don't risk drift between docs and code.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema

# The schema lives in the monorepo; this constant is the canonical path.
# Repo layout: <monorepo-root>/aimvision-ml/src/aimvision_ml/llm/schema.py
# so the docs dir is four parents up from this file.
_DEFAULT_SCHEMA_DOC = Path(__file__).resolve().parents[4] / "docs" / "llm-coaching-notes-schema.md"

_FENCED_JSON_RE = re.compile(r"```json\s*\n(?P<body>.*?)\n```", re.DOTALL)


def schema_doc_path() -> Path:
    """Return the canonical path to the markdown schema doc."""
    return _DEFAULT_SCHEMA_DOC


@lru_cache(maxsize=4)
def load_schema(doc_path: Path | None = None) -> dict[str, Any]:
    """Parse the markdown and return the first ```json``` block as a dict.

    The convention in `docs/llm-coaching-notes-schema.md` is that the very
    first fenced JSON block is the schema, and any subsequent blocks are
    examples. We rely on that ordering and assert the parsed object has
    `"$schema"` set to a JSON-Schema URI.
    """
    p = (doc_path or _DEFAULT_SCHEMA_DOC).resolve()
    if not p.exists():
        raise FileNotFoundError(f"schema doc not found: {p}")
    text = p.read_text(encoding="utf-8")
    match = _FENCED_JSON_RE.search(text)
    if match is None:
        raise ValueError(f"no ```json``` block found in {p}")
    schema = json.loads(match.group("body"))
    if not isinstance(schema, dict):
        raise ValueError("schema block did not parse to an object")
    if "$schema" not in schema or "json-schema.org" not in str(schema.get("$schema", "")):
        raise ValueError("first JSON block in schema doc is not a JSON Schema")
    return schema


def validate(output: dict[str, Any], doc_path: Path | None = None) -> None:
    """Validate an LLM output against the schema.

    Raises `jsonschema.ValidationError` on failure, exactly as the verifier
    pass expects. Caller catches and triggers regeneration / degradation.
    """
    schema = load_schema(doc_path)
    jsonschema.validate(instance=output, schema=schema)
