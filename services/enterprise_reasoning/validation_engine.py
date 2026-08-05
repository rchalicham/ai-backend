from __future__ import annotations

from dataclasses import replace

from .models import ReasoningEvidence, ReasoningHypothesis


class ReasoningValidationEngine:
    def validate(
        self,
        hypotheses: tuple[ReasoningHypothesis, ...],
        evidence: tuple[ReasoningEvidence, ...],
    ) -> tuple[ReasoningHypothesis, ...]:
        known = {item.evidence_id: item for item in evidence}
        validated = []
        for hypothesis in hypotheses:
            relevant = tuple(known[x] for x in hypothesis.evidence_ids if x in known)
            reasons = list(hypothesis.rejection_reasons)
            if not relevant:
                reasons.append("hypothesis has no traceable evidence")
            if any(item.quality < 0.5 for item in relevant):
                reasons.append("hypothesis relies on low-quality evidence")
            if any(not item.provenance and not item.supporting_documents
                   and item.source_tool not in {"constraint_solver", "product_intelligence"}
                   for item in relevant):
                reasons.append("semantic evidence lacks provenance")
            validated.append(replace(
                hypothesis, supported=not reasons,
                rejection_reasons=tuple(dict.fromkeys(reasons)),
            ))
        return tuple(validated)
