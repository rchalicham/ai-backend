from __future__ import annotations

from .models import ProductEnrichment, ProductLearningSuggestion


class ProductLearningService:
    def suggest(self, enrichments: tuple[ProductEnrichment, ...]) -> tuple[ProductLearningSuggestion, ...]:
        return tuple(
            ProductLearningSuggestion(
                suggestion_type="new_product",
                description="Review this unmatched description as a possible Product or Alias.",
                original_description=item.original_description,
                proposed_value={"normalized": item.normalized_description},
                evidence_references=(f"receipt-item:{item.item_index}",),
                confidence=item.confidence.overall,
                requires_approval=True,
            )
            for item in enrichments if item.canonical_product is None
        )

