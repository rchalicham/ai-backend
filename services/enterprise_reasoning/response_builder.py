from __future__ import annotations

from .models import (
    ReasoningDecision,
    ReasoningDiagnostics,
    ReasoningEvidence,
    ReasoningExplanation,
    ReasoningHypothesis,
    ReasoningRequest,
    ReasoningResponse,
    ReasoningSession,
)


class ReasoningResponseBuilder:
    def build(self, request: ReasoningRequest, session: ReasoningSession,
              evidence: tuple[ReasoningEvidence, ...],
              hypotheses: tuple[ReasoningHypothesis, ...],
              decision: ReasoningDecision | None,
              explanation: ReasoningExplanation, provenance: tuple[str, ...],
              diagnostics: ReasoningDiagnostics, synthesis: str = "") -> ReasoningResponse:
        return ReasoningResponse(
            request, session, evidence, hypotheses, decision, explanation,
            provenance, diagnostics, synthesis or (decision.answer if decision else ""),
        )
