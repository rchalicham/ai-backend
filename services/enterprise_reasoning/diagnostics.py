from __future__ import annotations

from .models import ReasoningDiagnostics


class EnterpriseReasoningDiagnostics:
    def create(self, evidence_count: int, hypothesis_count: int, *,
               llm_used: bool = False, warnings=()) -> ReasoningDiagnostics:
        return ReasoningDiagnostics(
            warnings=tuple(warnings),
            information=(
                f"approved evidence items: {evidence_count}",
                f"candidate hypotheses: {hypothesis_count}",
                "deterministic enterprise evidence evaluated before optional LLM synthesis",
            ),
            llm_used=llm_used,
        )

    @staticmethod
    def failed(error: Exception) -> ReasoningDiagnostics:
        return ReasoningDiagnostics(errors=(f"enterprise_reasoning_failed:{error}",))
