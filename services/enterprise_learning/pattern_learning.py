from __future__ import annotations

from services.cross_document_intelligence import IntelligenceResult


class PatternLearningEngine:
    def suggest(self, context: IntelligenceResult):
        return tuple(
            {
                "candidate_type": "pattern_observation",
                "subject_id": pattern.pattern_id,
                "proposed_value": {
                    "patternType": pattern.pattern_type,
                    "occurrences": pattern.occurrences,
                    "description": pattern.description,
                    "predictive": False,
                },
                "source": "historical_consistency",
                "confirmation_count": pattern.occurrences,
                "current_confidence": pattern.confidence.normalized,
                "evidence_ids": pattern.evidence_ids,
            }
            for pattern in context.context.patterns
            if pattern.occurrences >= 2
            and pattern.confidence.normalized >= 0.8
            and pattern.predictive is False
        )

