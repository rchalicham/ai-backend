from __future__ import annotations

from .models import (
    ReasoningDecision,
    ReasoningEvidence,
    ReasoningExplanation,
    ReasoningHypothesis,
    ReasoningPlan,
)


class ReasoningExplanationEngine:
    def explain(self, plan: ReasoningPlan, evidence: tuple[ReasoningEvidence, ...],
                hypotheses: tuple[ReasoningHypothesis, ...],
                decision: ReasoningDecision | None) -> ReasoningExplanation:
        rejected = tuple(
            f"{item.hypothesis_id}: {', '.join(item.rejection_reasons) or 'lower-ranked evidence'}"
            for item in hypotheses
            if decision is None or item.hypothesis_id != decision.selected_hypothesis_id
        )
        return ReasoningExplanation(
            f"explanation:{plan.plan_id}",
            (
                f"Selected {decision.selected_hypothesis_id} from validated deterministic evidence."
                if decision else "No hypothesis had sufficient validated enterprise evidence."
            ),
            plan.rationale,
            tuple(
                f"{item.evidence_id} trusted at quality {item.quality:.3f} "
                f"from {item.source_tool}"
                for item in evidence
            ),
            rejected,
            "Weighted deterministic source confidence; optional LLM contribution is capped at 10%.",
        )
