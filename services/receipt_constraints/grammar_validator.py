from __future__ import annotations

from services.receipt_grammar import ReceiptGrammarContext

from .models import (
    ConstraintCandidate,
    ConstraintEvaluation,
    ConstraintOutcome,
    ConstraintRule,
)


class GrammarConstraintValidator:
    """Consumes Receipt Grammar output; it does not duplicate Grammar validation."""

    def evaluate(
        self,
        rule: ConstraintRule,
        candidate: ConstraintCandidate,
        grammar_context: ReceiptGrammarContext,
        *,
        penalty: float,
    ) -> ConstraintEvaluation:
        compliance = grammar_context.compliance
        if compliance is None:
            return ConstraintEvaluation(
                rule.rule_id,
                candidate.candidate_id,
                rule.category,
                ConstraintOutcome.WARNING,
                penalty * 0.5,
                0.5,
                "Receipt Grammar produced no compliance result.",
            )
        parameters = dict(rule.parameters)
        threshold = float(parameters.get("minimum", 0.0))
        if rule.rule_type == "grammar_compliance":
            passed = compliance.overall_compliance >= threshold
            detail = (
                f"Grammar compliance {compliance.overall_compliance:.3f} "
                f"was evaluated against minimum {threshold:.3f}."
            )
        elif rule.rule_type == "transition_compliance":
            transition_id = str(parameters.get("transition_id", ""))
            passed = f"transition:{transition_id}" not in compliance.missing_rules
            detail = f"Consumed Grammar transition outcome '{transition_id}'."
        elif rule.rule_type == "relationship_compliance":
            relationship_id = str(parameters.get("relationship_id", ""))
            passed = f"relationship:{relationship_id}" not in compliance.missing_rules
            detail = f"Consumed Grammar relationship outcome '{relationship_id}'."
        elif rule.rule_type == "role_expectation":
            role_type = str(parameters.get("role_type", ""))
            passed = any(item.role_type.value == role_type for item in compliance.candidate_roles)
            detail = f"Consumed Grammar candidate role expectation '{role_type}'."
        elif rule.rule_type == "section_compliance":
            section_id = str(parameters.get("section_id", parameters.get("subject", "")))
            passed = section_id in compliance.matched_sections
            detail = f"Consumed Grammar matched-section outcome '{section_id}'."
        else:
            passed = False
            detail = f"Grammar constraint type '{rule.rule_type}' is not supported."
        outcome = ConstraintOutcome.PASS if passed else (
            ConstraintOutcome.VIOLATION if rule.required else ConstraintOutcome.WARNING
        )
        return ConstraintEvaluation(
            rule.rule_id,
            candidate.candidate_id,
            rule.category,
            outcome,
            0.0 if passed else penalty if rule.required else penalty * 0.5,
            1.0 if passed else 0.0,
            detail,
        )

