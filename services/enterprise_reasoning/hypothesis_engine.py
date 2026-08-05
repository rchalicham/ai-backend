from __future__ import annotations

import hashlib

from .models import ReasoningEvidence, ReasoningHypothesis, ReasoningRequest


class ReasoningHypothesisEngine:
    def generate(
        self, request: ReasoningRequest, evidence: tuple[ReasoningEvidence, ...],
    ) -> tuple[ReasoningHypothesis, ...]:
        if not evidence:
            return (ReasoningHypothesis(
                "hypothesis:insufficient-evidence",
                "The available approved enterprise evidence is insufficient to answer the question.",
                (), 0.0, False, ("no approved evidence",),
            ),)
        result = []
        for item in evidence:
            token = hashlib.sha256(
                f"{request.request_id}|{item.evidence_id}".encode(),
            ).hexdigest()[:24]
            result.append(ReasoningHypothesis(
                f"hypothesis:{token}",
                f"{item.source_tool} provides evidence relevant to: {request.question}",
                (item.evidence_id,), item.confidence,
                item.quality >= 0.5,
                () if item.quality >= 0.5 else ("evidence quality below minimum",),
            ))
        if len(evidence) > 1:
            confidence = sum(item.confidence for item in evidence) / len(evidence)
            result.append(ReasoningHypothesis(
                "hypothesis:fused-enterprise-evidence",
                f"Multiple enterprise sources support a fused response to: {request.question}",
                tuple(item.evidence_id for item in evidence), round(confidence, 6),
            ))
        return tuple(result)
