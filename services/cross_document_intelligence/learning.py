from __future__ import annotations

from .models import EnterpriseContext, LearningSuggestion


class CrossDocumentLearningService:
    def suggest(self, context: EnterpriseContext) -> tuple[LearningSuggestion, ...]:
        return tuple(
            LearningSuggestion(
                "correlation_review",
                "Review a low-confidence cross-document correlation before knowledge activation.",
                {"correlationId": item.correlation_id, "type": item.correlation_type},
                item.evidence_ids,
                item.confidence.normalized,
                True,
            )
            for item in context.correlations if item.confidence.normalized < 0.8
        )

