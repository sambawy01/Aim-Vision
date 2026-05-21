"""LLM + vision clients for the coaching pipeline (ml-architecture.md §11).

Production runs against an Ollama-compatible endpoint. Two deployment
shapes are supported by the same client:

  * **Self-hosted Ollama** (the Helm `ollama` Deployment) — no API key.
  * **Hosted Ollama Cloud** (`https://ollama.com`) — Bearer API key.

The language/coaching model defaults to **kimi-k2.6**; the vision
model defaults to **qwen3-vl:235b-instruct** (Qwen3-VL, the strongest
purpose-built VLM available on the hosted catalog). Both are
overridable via env / constructor.

# Secrets

The API key is read from `AIMVISION_OLLAMA_API_KEY` (or passed
explicitly) and sent as a Bearer header. It is NEVER logged, defaulted
in code, or committed. In-cluster it comes from a Kubernetes secret
(see the Helm `llm` values).

# No model host ships in the repo

When the host is unreachable the client raises `LlmUnavailable` and the
generator degrades to a schema-valid note rather than crashing.
"""

from __future__ import annotations

import base64
import os
from typing import Protocol, runtime_checkable

import httpx

# Hosted Ollama Cloud endpoint. Override with AIMVISION_OLLAMA_BASE_URL
# (e.g. the in-cluster self-hosted service URL).
DEFAULT_BASE_URL = "https://ollama.com"
# Language / coaching-note model. Kimi K2.6 — strong structured-output
# instruction following; confirmed JSON-mode capable on the hosted catalog.
DEFAULT_LANGUAGE_MODEL = "kimi-k2.6"
# Vision-language model for shot-image understanding. Qwen3-VL 235B
# (instruct, FP8, 262k ctx) — the best-fit VLM in the hosted catalog.
DEFAULT_VISION_MODEL = "qwen3-vl:235b-instruct"

_API_KEY_ENV = "AIMVISION_OLLAMA_API_KEY"
_BASE_URL_ENV = "AIMVISION_OLLAMA_BASE_URL"
_LANGUAGE_MODEL_ENV = "AIMVISION_LLM_MODEL"
_VISION_MODEL_ENV = "AIMVISION_VISION_MODEL"


class LlmUnavailable(RuntimeError):
    """Raised when the LLM/vision host is unreachable or errors out.

    The generator catches this and degrades; callers above it never
    see it.
    """


@runtime_checkable
class LlmClient(Protocol):
    """Minimal generate interface. Implementations MUST request
    structured/JSON output — the coaching note is a grammar-constrained
    JSON object, never free prose."""

    def generate(self, system: str, prompt: str) -> str:
        """Return the model's raw JSON string for (system, prompt)."""
        ...


def _auth_headers(api_key: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


class OllamaClient:
    """Ollama-compatible language client (POST /api/generate, format=json).

    Synchronous on purpose: the generator runs inside a Temporal
    activity / worker that provides concurrency at the workflow level,
    and a coaching-note generation is a single long call.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_LANGUAGE_MODEL,
        *,
        api_key: str | None = None,
        timeout_s: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.Client(
            timeout=timeout_s,
            transport=transport,
            headers=_auth_headers(api_key),
        )

    @classmethod
    def from_env(cls, *, transport: httpx.BaseTransport | None = None) -> OllamaClient:
        """Build from AIMVISION_OLLAMA_* env vars. The API key is read
        here and never logged."""
        return cls(
            base_url=os.environ.get(_BASE_URL_ENV, DEFAULT_BASE_URL),
            model=os.environ.get(_LANGUAGE_MODEL_ENV, DEFAULT_LANGUAGE_MODEL),
            api_key=os.environ.get(_API_KEY_ENV),
            transport=transport,
        )

    @property
    def model(self) -> str:
        return self._model

    def generate(self, system: str, prompt: str) -> str:
        try:
            resp = self._client.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": self._model,
                    "system": system,
                    "prompt": prompt,
                    # `format: json` is the floor guaranteeing parseable
                    # JSON; grammar-constrained decoding (Outlines/Guidance)
                    # tightens this to the exact schema in a later slice.
                    "format": "json",
                    "stream": False,
                },
            )
        except httpx.HTTPError as e:
            raise LlmUnavailable(f"Ollama request failed: {e}") from e
        if resp.status_code != 200:
            raise LlmUnavailable(f"Ollama returned HTTP {resp.status_code}")
        try:
            body = resp.json()
        except ValueError as e:
            raise LlmUnavailable("Ollama response was not JSON") from e
        response_text = body.get("response")
        if not isinstance(response_text, str):
            raise LlmUnavailable("Ollama response missing 'response' field")
        return response_text

    def close(self) -> None:
        self._client.close()


class OllamaVisionClient:
    """Vision-language client for shot-image understanding.

    Wraps the same /api/generate endpoint with the `images` field
    (base64-encoded). Used to caption / describe notable-shot frames
    that augment the coaching note; the specialized CV pipeline
    (RTMPose / barrel YOLO / diagnostic head) remains the primary
    analysis path — this VLM is supplementary, not a replacement.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_VISION_MODEL,
        *,
        api_key: str | None = None,
        timeout_s: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.Client(
            timeout=timeout_s,
            transport=transport,
            headers=_auth_headers(api_key),
        )

    @classmethod
    def from_env(cls, *, transport: httpx.BaseTransport | None = None) -> OllamaVisionClient:
        return cls(
            base_url=os.environ.get(_BASE_URL_ENV, DEFAULT_BASE_URL),
            model=os.environ.get(_VISION_MODEL_ENV, DEFAULT_VISION_MODEL),
            api_key=os.environ.get(_API_KEY_ENV),
            transport=transport,
        )

    @property
    def model(self) -> str:
        return self._model

    def describe_image(self, prompt: str, image: bytes, *, as_json: bool = False) -> str:
        """Run the VLM over one image. `image` is raw bytes (PNG/JPEG);
        we base64-encode it for the Ollama `images` field."""
        b64 = base64.b64encode(image).decode("ascii")
        payload: dict[str, object] = {
            "model": self._model,
            "prompt": prompt,
            "images": [b64],
            "stream": False,
        }
        if as_json:
            payload["format"] = "json"
        try:
            resp = self._client.post(f"{self._base_url}/api/generate", json=payload)
        except httpx.HTTPError as e:
            raise LlmUnavailable(f"Vision request failed: {e}") from e
        if resp.status_code != 200:
            raise LlmUnavailable(f"Vision model returned HTTP {resp.status_code}")
        try:
            body = resp.json()
        except ValueError as e:
            raise LlmUnavailable("Vision response was not JSON") from e
        response_text = body.get("response")
        if not isinstance(response_text, str):
            raise LlmUnavailable("Vision response missing 'response' field")
        return response_text

    def close(self) -> None:
        self._client.close()
