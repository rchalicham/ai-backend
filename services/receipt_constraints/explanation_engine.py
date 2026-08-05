from __future__ import annotations

from .models import (
    ConstraintCandidate,
    ConstraintDecision,
    ConstraintExplanation,
    ConstraintOutcome,
    ConstraintScore,
)


class ConstraintExplanationEngine:
    def decide(
        self,
        candidates: tuple[ConstraintCandidate, ...],
        scores: tuple[ConstraintScore, ...],
    ) -> ConstraintDecision:
        candidate_map = {candidate.candidate_id: candidate for candidate in candidates}
        ranked = tuple(
            candidate_map[score.candidate_id] for score in scores if score.candidate_id in candidate_map
        )
        best = ranked[0] if ranked else None
        rejected = ranked[1:] if ranked else ()
        explanations = tuple(
            ConstraintExplanation(
                evaluation.rule_id,
                evaluation.candidate_id,
                evaluation.outcome,
                evaluation.explanation,
                contribution=round(evaluation.score - evaluation.penalty, 6),
            )
            for score in scores
            for evaluation in score.evaluations
        )
        if not best or not scores:
            reason = "No candidate interpretation was available for deterministic constraint reasoning."
        else:
            winner = scores[0]
            reason = (
                f"Candidate {best.candidate_id} selected with overall score "
                f"{winner.overall_score:.3f}; arithmetic {winner.arithmetic_score:.3f}, "
                f"grammar {winner.grammar_score:.3f}, structural {winner.structural_score:.3f}, "
                f"penalty {winner.penalty_score:.3f}, and normalized confidence "
                f"{winner.confidence.normalized:.3f}."
            )
        return ConstraintDecision(best, ranked, rejected, scores, explanations, reason)

