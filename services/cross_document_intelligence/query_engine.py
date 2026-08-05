from __future__ import annotations

from .models import IntelligenceResult


class CrossDocumentQueryEngine:
    """Storage-neutral semantic memory queries."""

    def find_all_purchases_of_product(self, result: IntelligenceResult, product_id: str):
        return self._documents_for_entity(result, product_id, {"Receipt", "Invoice", "Purchase Order"})

    def find_all_receipts_for_merchant(self, result: IntelligenceResult, merchant_id: str):
        return self._documents_for_entity(result, merchant_id, {"Receipt"})

    def find_all_warranties_for_product(self, result: IntelligenceResult, product_id: str):
        return self._documents_for_entity(result, product_id, {"Warranty"})

    def find_purchase_history(self, result: IntelligenceResult, entity_id: str):
        return self.find_timeline(result, entity_id)

    def find_recurring_expenses(self, result: IntelligenceResult):
        return tuple(
            item for item in result.context.patterns
            if item.pattern_type in {"recurring_purchase", "subscription_pattern", "expense_trend", "price_change"}
        )

    def find_all_documents_referencing_entity(self, result: IntelligenceResult, entity_id: str):
        return self._documents_for_entity(result, entity_id, None)

    def find_related_documents(self, result: IntelligenceResult, document_id: str):
        correlations = tuple(
            item for item in result.context.correlations
            if any(reference.document_id == document_id for reference in item.document_references)
        )
        return tuple(dict.fromkeys(
            reference for item in correlations for reference in item.document_references
            if reference.document_id != document_id
        ))

    def find_timeline(self, result: IntelligenceResult, entity_id: str):
        return next((
            item for item in result.context.timelines
            if self._matches(item.subject_entity_id, entity_id)
        ), None)

    def find_evidence(self, result: IntelligenceResult, subject_id: str):
        return tuple(
            item for item in result.context.evidence
            if subject_id in item.source_entity_ids or item.evidence_id == subject_id
        )

    def find_anomalies(self, result: IntelligenceResult):
        return result.context.anomalies

    def find_patterns(self, result: IntelligenceResult):
        return result.context.patterns

    def _documents_for_entity(self, result, entity_id, allowed_types):
        entity = next((
            item for item in result.context.entities
            if self._matches(item.entity_id, entity_id)
        ), None)
        if entity is None:
            return ()
        if allowed_types is None:
            return entity.document_references
        return tuple(
            item for item in entity.document_references
            if self._value(item.document_type) in allowed_types
        )

    @staticmethod
    def _matches(value: str, expected: str) -> bool:
        return value.casefold() == expected.casefold() or value.rsplit(":", 1)[-1].casefold() == expected.casefold()

    @staticmethod
    def _value(value) -> str:
        return value.value if hasattr(value, "value") else str(value)

