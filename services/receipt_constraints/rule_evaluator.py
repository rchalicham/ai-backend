from __future__ import annotations

from typing import Any

from services.receipt_dom import ReceiptDocument
from services.receipt_grammar import ReceiptGrammarContext
from services.receipt_structure import ReceiptPhysicalStructure

from .arithmetic_validator import ArithmeticConstraintValidator
from .grammar_validator import GrammarConstraintValidator
from .models import (
    ConstraintCandidate,
    ConstraintCategory,
    ConstraintEvaluation,
    ConstraintOutcome,
    ConstraintRule,
)
from .structural_validator import StructuralConstraintValidator


class ConstraintRuleEvaluator:
    def __init__(
        self,
        arithmetic: ArithmeticConstraintValidator | None = None,
        structural: StructuralConstraintValidator | None = None,
        grammar: GrammarConstraintValidator | None = None,
    ) -> None:
        self.arithmetic = arithmetic or ArithmeticConstraintValidator()
        self.structural = structural or StructuralConstraintValidator()
        self.grammar = grammar or GrammarConstraintValidator()

    def evaluate(
        self,
        rule: ConstraintRule,
        candidate: ConstraintCandidate,
        document: ReceiptDocument,
        structure: ReceiptPhysicalStructure,
        grammar_context: ReceiptGrammarContext,
        *,
        penalty: float,
    ) -> ConstraintEvaluation:
        if rule.category is ConstraintCategory.ARITHMETIC:
            return self.arithmetic.evaluate(rule, candidate, penalty=penalty)
        if rule.category in {
            ConstraintCategory.STRUCTURAL,
            ConstraintCategory.ORDERING,
            ConstraintCategory.CARDINALITY,
            ConstraintCategory.LOCALITY,
        }:
            return self.structural.evaluate(
                rule, candidate, document, structure, penalty=penalty,
            )
        if rule.category in {
            ConstraintCategory.GRAMMAR,
            ConstraintCategory.RELATIONSHIP,
            ConstraintCategory.TRANSITION,
        }:
            return self.grammar.evaluate(
                rule, candidate, grammar_context, penalty=penalty,
            )
        return self._generic(rule, candidate, penalty)

    def _generic(
        self,
        rule: ConstraintRule,
        candidate: ConstraintCandidate,
        penalty: float,
    ) -> ConstraintEvaluation:
        values = dict(candidate.interpretation)
        parameters = dict(rule.parameters)
        passed: bool | None
        if rule.category is ConstraintCategory.CONFIDENCE:
            minimum = float(parameters.get("minimum", 0.0))
            passed = candidate.base_confidence >= minimum
            detail = f"Candidate confidence {candidate.base_confidence:.3f} evaluated against {minimum:.3f}."
        elif rule.category is ConstraintCategory.KNOWLEDGE:
            minimum = float(parameters.get("minimum", 0.0))
            passed = candidate.knowledge_confidence >= minimum
            detail = f"Knowledge confidence {candidate.knowledge_confidence:.3f} evaluated against {minimum:.3f}."
        elif rule.category is ConstraintCategory.CROSS_REFERENCE:
            left = str(parameters.get("left", ""))
            right = str(parameters.get("right", ""))
            if left not in values or right not in values:
                passed = None
            else:
                passed = values[left] == values[right]
            detail = f"Compared supplied candidate references '{left}' and '{right}'."
        elif rule.category in {ConstraintCategory.FUTURE_PRODUCT, ConstraintCategory.FUTURE_MERCHANT}:
            passed = None
            detail = f"{rule.category.value} evidence is reserved for a future sidecar."
        else:
            passed = None
            detail = f"Constraint category '{rule.category.value}' has no registered evaluator."
        if passed is None:
            outcome = ConstraintOutcome.WARNING
            score = 0.5
            applied_penalty = penalty * 0.5
        elif passed:
            outcome = ConstraintOutcome.PASS
            score = 1.0
            applied_penalty = 0.0
        else:
            outcome = ConstraintOutcome.VIOLATION if rule.required else ConstraintOutcome.WARNING
            score = 0.0
            applied_penalty = penalty if rule.required else penalty * 0.5
        return ConstraintEvaluation(
            rule.rule_id,
            candidate.candidate_id,
            rule.category,
            outcome,
            round(applied_penalty, 6),
            score,
            detail,
        )

