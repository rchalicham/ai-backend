from __future__ import annotations

from .llm_provider import LLMProvider
from .models import ReasoningDecision, ReasoningEvidence, ReasoningRequest
from .prompt_builder import PromptBuilder


class LLMAdapter:
    def __init__(self, provider: LLMProvider | None = None, prompt_builder=None) -> None:
        self.provider = provider
        self.prompt_builder = prompt_builder or PromptBuilder()

    @property
    def available(self) -> bool:
        return self.provider is not None

    def synthesize(
        self, request: ReasoningRequest, decision: ReasoningDecision,
        evidence: tuple[ReasoningEvidence, ...],
    ) -> str:
        if not request.allow_llm:
            return ""
        if not self.provider:
            return ""
        if not decision.evidence_ids:
            raise ValueError("llm_requires_validated_evidence")
        prompt = self.prompt_builder.build(request, decision, evidence)
        return self.provider.synthesize(prompt, timeout_ms=request.timeout_ms)
