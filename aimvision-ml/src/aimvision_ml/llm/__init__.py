"""LLM coaching-notes pipeline: schema, prompt, verifier, PII, generation."""

from aimvision_ml.llm.client import (
    DEFAULT_LANGUAGE_MODEL,
    DEFAULT_VISION_MODEL,
    LlmClient,
    LlmUnavailable,
    OllamaClient,
    OllamaVisionClient,
)
from aimvision_ml.llm.generate import (
    build_degraded_note,
    generate_coaching_note,
)
from aimvision_ml.llm.prompt import PromptInputs, RetrievedNote, build_prompt

__all__ = [
    "DEFAULT_LANGUAGE_MODEL",
    "DEFAULT_VISION_MODEL",
    "LlmClient",
    "LlmUnavailable",
    "OllamaClient",
    "OllamaVisionClient",
    "PromptInputs",
    "RetrievedNote",
    "build_degraded_note",
    "build_prompt",
    "generate_coaching_note",
]
