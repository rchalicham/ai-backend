from __future__ import annotations

from .models import ConstraintDecision, ConstraintLearningSuggestion, ReceiptConstraint


class ConstraintLearningService:
    def suggest(
        self,
        constraint_set: ReceiptConstraint,
        decision: ConstraintDecision,
        document_id: str,
    ) -> tuple[ConstraintLearningSuggestion, ...]:
        suggestions = []
        for score in decision.scores:
            for violation in score.violations:
                suggestion_type = {
                    "arithmetic": "new_arithmetic_rule",
                    "structural": "new_structural_rule",
                    "grammar": "new_grammar_dependency",
                }.get(violation.category.value, "new_constraint")
                suggestions.append(ConstraintLearningSuggestion(
                    suggestion_type=suggestion_type,
                    receipt_family=constraint_set.receipt_family,
                    subject_id=violation.rule_id,
                    description=f"Review repeated violation: {violation.message}",
                    evidence_references=(document_id, score.candidate_id),
                    confidence=min(1.0, violation.penalty + (1.0 - score.overall_score)),
                ))
            if score.penalty_score > 0.5:
                suggestions.append(ConstraintLearningSuggestion(
                    suggestion_type="constraint_weight_adjustment",
                    receipt_family=constraint_set.receipt_family,
                    subject_id=score.candidate_id,
                    description="Review constraint weights because aggregate penalties exceeded 0.5.",
                    proposed_value=max(0.0, 1.0 - score.penalty_score),
                    evidence_references=(document_id, score.candidate_id),
                    confidence=score.penalty_score,
                ))
        return tuple(suggestions)

