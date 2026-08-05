from __future__ import annotations

from .models import ReasoningEvidence, ReasoningPlan, ReasoningTrace


class ReasoningProvenanceEngine:
    def build(
        self, evidence: tuple[ReasoningEvidence, ...],
        plan: ReasoningPlan, traces: tuple[ReasoningTrace, ...],
    ) -> tuple[str, ...]:
        return tuple(dict.fromkeys((
            f"plan:{plan.plan_id}",
            *(f"tool:{trace.tool_name}:{trace.status}" for trace in traces),
            *(f"evidence:{item.evidence_id}" for item in evidence),
            *(value for item in evidence for value in item.provenance),
            *(f"document:{value}" for item in evidence for value in item.supporting_documents),
            *(f"entity:{value}" for item in evidence for value in item.supporting_entities),
        )))
