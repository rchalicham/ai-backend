from __future__ import annotations

from collections import defaultdict

from .confidence_engine import ConstraintConfidenceEngine
from .models import (
    ConstraintCandidate,
    ConstraintCategory,
    ConstraintEvaluation,
    ConstraintOutcome,
    ConstraintRule,
    ConstraintScore,
    ConstraintViolation,
)


class ConstraintCandidateRanker:
    def __init__(self, confidence_engine: ConstraintConfidenceEngine | None = None) -> None:
        self.confidence_engine = confidence_engine or ConstraintConfidenceEngine()

    def score(
        self,
        candidates: tuple[ConstraintCandidate, ...],
        evaluations: tuple[ConstraintEvaluation, ...],
        rules: tuple[ConstraintRule, ...],
        rule_weights: dict[str, float],
    ) -> tuple[ConstraintScore, ...]:
        by_candidate: dict[str, list[ConstraintEvaluation]] = defaultdict(list)
        for evaluation in evaluations:
            by_candidate[evaluation.candidate_id].append(evaluation)
        rule_map = {rule.rule_id: rule for rule in rules}
        results = []
        for candidate in candidates:
            values = tuple(by_candidate.get(candidate.candidate_id, ()))
            weighted_total = 0.0
            total_weight = 0.0
            for evaluation in values:
                weight = max(0.0, rule_weights.get(evaluation.rule_id, 1.0))
                weighted_total += evaluation.score * weight
                total_weight += weight
            constraint_score = weighted_total / total_weight if total_weight else 1.0
            penalty_score = min(1.0, sum(item.penalty for item in values))
            arithmetic = self._category(values, {ConstraintCategory.ARITHMETIC})
            structural = self._category(values, {
                ConstraintCategory.STRUCTURAL,
                ConstraintCategory.ORDERING,
                ConstraintCategory.CARDINALITY,
                ConstraintCategory.LOCALITY,
            })
            grammar = self._category(values, {
                ConstraintCategory.GRAMMAR,
                ConstraintCategory.RELATIONSHIP,
                ConstraintCategory.TRANSITION,
            }, candidate.grammar_compliance)
            knowledge = self._category(values, {ConstraintCategory.KNOWLEDGE}, candidate.knowledge_confidence)
            confidence = self.confidence_engine.combine(
                grammar=grammar,
                knowledge=knowledge,
                arithmetic=arithmetic,
                structural=structural,
                constraint=constraint_score,
            )
            overall = max(
                0.0,
                min(1.0, (confidence.normalized * 0.8) + (candidate.base_confidence * 0.2) - penalty_score),
            )
            violations = tuple(
                ConstraintViolation(
                    evaluation.rule_id,
                    evaluation.category,
                    evaluation.explanation,
                    evaluation.penalty,
                    candidate.candidate_id,
                )
                for evaluation in values
                if evaluation.outcome is ConstraintOutcome.VIOLATION
            )
            results.append(ConstraintScore(
                candidate_id=candidate.candidate_id,
                constraint_score=round(constraint_score, 6),
                penalty_score=round(penalty_score, 6),
                arithmetic_score=arithmetic,
                structural_score=structural,
                grammar_score=grammar,
                knowledge_score=knowledge,
                overall_score=round(overall, 6),
                confidence=confidence,
                evaluations=values,
                violations=violations,
            ))
        return tuple(sorted(results, key=lambda item: (-item.overall_score, item.candidate_id)))

    def _category(
        self,
        evaluations: tuple[ConstraintEvaluation, ...],
        categories: set[ConstraintCategory],
        fallback: float = 1.0,
    ) -> float:
        values = [item.score for item in evaluations if item.category in categories]
        return round(sum(values) / len(values), 6) if values else max(0.0, min(1.0, fallback))

