from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    def synthesize(self, prompt: str, *, timeout_ms: int) -> str: ...


class DisabledLLMProvider:
    def synthesize(self, prompt: str, *, timeout_ms: int) -> str:
        raise RuntimeError("enterprise_reasoning_llm_provider_not_configured")
