"""Tests for the Ollama language + vision clients.

MockTransport-driven: no live host. Asserts the request shape (model,
JSON-mode, Bearer auth, base64 image payload), env-based config, and
LlmUnavailable on transport/HTTP errors. No API key is hardcoded —
tests use a dummy.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx
import pytest

from aimvision_ml.llm.client import (
    DEFAULT_LANGUAGE_MODEL,
    DEFAULT_VISION_MODEL,
    LlmUnavailable,
    OllamaClient,
    OllamaVisionClient,
)


def _capture(requests: list[httpx.Request], response: httpx.Response) -> httpx.MockTransport:
    def _route(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return response

    return httpx.MockTransport(_route)


def test_generate_sends_model_json_mode_and_bearer() -> None:
    reqs: list[httpx.Request] = []
    transport = _capture(reqs, httpx.Response(200, json={"response": '{"ok": true}'}))
    client = OllamaClient(api_key="dummy-key", transport=transport)
    out = client.generate("system", "prompt")

    assert out == '{"ok": true}'
    assert client.model == DEFAULT_LANGUAGE_MODEL  # kimi-k2.6
    req = reqs[0]
    assert req.url.path == "/api/generate"
    assert req.headers["Authorization"] == "Bearer dummy-key"
    body = json.loads(req.content)
    assert body["model"] == "kimi-k2.6"
    assert body["format"] == "json"
    assert body["stream"] is False


def test_no_api_key_means_no_auth_header() -> None:
    reqs: list[httpx.Request] = []
    transport = _capture(reqs, httpx.Response(200, json={"response": "{}"}))
    OllamaClient(transport=transport).generate("s", "p")
    assert "Authorization" not in reqs[0].headers


def test_from_env_reads_key_model_and_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIMVISION_OLLAMA_BASE_URL", "https://ollama.example")
    monkeypatch.setenv("AIMVISION_OLLAMA_API_KEY", "env-key")
    monkeypatch.setenv("AIMVISION_LLM_MODEL", "kimi-k2.6")
    reqs: list[httpx.Request] = []
    transport = _capture(reqs, httpx.Response(200, json={"response": "{}"}))
    client = OllamaClient.from_env(transport=transport)
    client.generate("s", "p")
    assert client.model == "kimi-k2.6"
    assert str(reqs[0].url) == "https://ollama.example/api/generate"
    assert reqs[0].headers["Authorization"] == "Bearer env-key"


def test_generate_raises_unavailable_on_http_error() -> None:
    transport = _capture([], httpx.Response(503, text="down"))
    with pytest.raises(LlmUnavailable):
        OllamaClient(transport=transport).generate("s", "p")


def test_generate_raises_unavailable_on_transport_error() -> None:
    def _boom(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(LlmUnavailable):
        OllamaClient(transport=httpx.MockTransport(_boom)).generate("s", "p")


def test_vision_client_default_model_and_base64_image() -> None:
    reqs: list[httpx.Request] = []
    transport = _capture(reqs, httpx.Response(200, json={"response": "a shooter mid-mount"}))
    client = OllamaVisionClient(api_key="k", transport=transport)
    assert client.model == DEFAULT_VISION_MODEL  # qwen3-vl:235b-instruct

    image = b"\x89PNG\r\n\x1a\nfake-bytes"
    out = client.describe_image("describe the stance", image)
    assert out == "a shooter mid-mount"

    body = json.loads(reqs[0].content)
    assert body["model"] == "qwen3-vl:235b-instruct"
    assert body["images"] == [base64.b64encode(image).decode("ascii")]
    # Plain prose by default (no JSON mode) for captions.
    assert "format" not in body


def test_vision_client_json_mode_opt_in() -> None:
    reqs: list[httpx.Request] = []
    transport = _capture(reqs, httpx.Response(200, json={"response": "{}"}))
    client = OllamaVisionClient(api_key="k", transport=transport)
    client.describe_image("structured", b"img", as_json=True)
    body: dict[str, Any] = json.loads(reqs[0].content)
    assert body["format"] == "json"


def test_vision_client_unavailable_on_error() -> None:
    transport = _capture([], httpx.Response(500, text="err"))
    with pytest.raises(LlmUnavailable):
        OllamaVisionClient(transport=transport).describe_image("p", b"img")
