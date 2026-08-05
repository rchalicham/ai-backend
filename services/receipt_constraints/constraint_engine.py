from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from services.receipt_dom import ReceiptDocument
from services.receipt_grammar import ReceiptGrammarContext
from services.receipt_structure import ReceiptPhysicalStructure

from .candidate_generator import ConstraintCandidateGenerator
from .candidate_ranker import ConstraintCandidateRanker
from .constraint_compiler import ReceiptConstraintCompiler
from .constraint_learning import ConstraintLearningService
from .constraint_repository import ReceiptConstraintRepository
from .explanation_engine import ConstraintExplanationEngine
from .models import ReceiptConstraintResult
from .rule_evaluator import ConstraintRuleEvaluator


class ConstraintEngine:
    """Deterministically ranks hypotheses without creating Business Facts."""

    def __init__(
        self,
        repository: ReceiptConstraintRepository | None = None,
        compiler: ReceiptConstraintCompiler | None = None,
        candidate_generator: ConstraintCandidateGenerator | None = None,
        rule_evaluator: ConstraintRuleEvaluator | None = None,
        candidate_ranker: ConstraintCandidateRanker | None = None,
        explanation_engine: ConstraintExplanationEngine | None = None,
        learning: ConstraintLearningService | None = None,
    ) -> None:
        self.repository = repository or ReceiptConstraintRepository()
        self.compiler = compiler or ReceiptConstraintCompiler()
        self.candidate_generator = candidate_generator or ConstraintCandidateGenerator()
        self.rule_evaluator = rule_evaluator or ConstraintRuleEvaluator()
        self.candidate_ranker = candidate_ranker or ConstraintCandidateRanker()
        self.explanation_engine = explanation_engine or ConstraintExplanationEngine()
        self.learning = learning or ConstraintLearningService()

    def evaluate(
        self,
        document: ReceiptDocument,
        structure: ReceiptPhysicalStructure,
        grammar_context: ReceiptGrammarContext,
        candidate_interpretations: Iterable[Mapping[str, Any]] = (),
        document_family_context=None,
    ) -> ReceiptConstraintResult:
        family = grammar_context.receipt_family
        if not family:
            return ReceiptConstraintResult(
                receipt_family="",
                loaded=False,
                diagnostics=self._diagnostics("no_receipt_family_for_constraints"),
            )
        constraint_set = self.repository.load_constraints(family)
        if constraint_set is None:
            return ReceiptConstraintResult(
                receipt_family=family,
                loaded=False,
                diagnostics=self._diagnostics("matching_constraint_set_not_found"),
            )
        compilation = self.compiler.compile(constraint_set)
        if not compilation.valid:
            return ReceiptConstraintResult(
                receipt_family=family,
                loaded=True,
                constraint_set=constraint_set,
                compilation=compilation,
                diagnostics=self._diagnostics("constraint_compilation_failed"),
            )
        candidates = self.candidate_generator.generate(
            grammar_context, candidate_interpretations,
        )
        penalties = {item.penalty_id: item.value for item in constraint_set.penalties}
        weights = {item.weight_id: item.value for item in constraint_set.weights}
        rules = {rule.rule_id: rule for rule in constraint_set.rules}
        evaluations = tuple(
            self.rule_evaluator.evaluate(
                rules[rule_id],
                candidate,
                document,
                structure,
                grammar_context,
                penalty=penalties.get(rules[rule_id].penalty_id, 0.2),
            )
            for candidate in candidates
            for rule_id in compilation.ordered_rule_ids
        )
        rule_weights = {
            rule.rule_id: weights.get(rule.weight_id, 1.0)
            for rule in constraint_set.rules
        }
        scores = self.candidate_ranker.score(
            candidates, evaluations, constraint_set.rules, rule_weights,
        )
        decision = self.explanation_engine.decide(candidates, scores)
        suggestions = self.learning.suggest(constraint_set, decision, document.id)
        return ReceiptConstraintResult(
            receipt_family=family,
            loaded=True,
            constraint_set=constraint_set,
            compilation=compilation,
            candidates=candidates,
            decision=decision,
            learning_suggestions=suggestions,
            diagnostics=self._diagnostics("constraint_sidecar_evaluated", warning=False),
        )

    def safe_evaluate(
        self,
        document: ReceiptDocument | None,
        structure: ReceiptPhysicalStructure | None,
        grammar_context: ReceiptGrammarContext | None,
        candidate_interpretations: Iterable[Mapping[str, Any]] = (),
        document_family_context=None,
    ) -> ReceiptConstraintResult | None:
        if document is None or structure is None or grammar_context is None:
            return None
        try:
            return self.evaluate(
                document, structure, grammar_context, candidate_interpretations,
                document_family_context,
            )
        except Exception as exc:
            return ReceiptConstraintResult(
                receipt_family=grammar_context.receipt_family,
                loaded=False,
                diagnostics=self._diagnostics(
                    f"constraint_sidecar_failed:{exc.__class__.__name__}",
                ),
            )

    def _diagnostics(self, message: str, warning: bool = True) -> tuple[tuple[str, Any], ...]:
        values = [
            ("sidecar", True),
            ("affectsExtraction", False),
            ("parserAuthorityChanged", False),
            ("businessFactsGenerated", False),
            ("ocrModified", False),
            ("grammarModified", False),
            ("candidateDecisionAuthoritative", False),
        ]
        values.append(("warning" if warning else "status", message))
        return tuple(values)
