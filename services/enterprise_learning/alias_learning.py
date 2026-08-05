from __future__ import annotations

from services.cross_document_intelligence import IntelligenceResult


class AliasLearningEngine:
    def suggest(self, context: IntelligenceResult):
        return tuple(
            {
                "candidate_type": (
                    "new_merchant_alias" if entity.entity_type == "Merchant"
                    else "new_brand_alias" if entity.entity_type == "Brand"
                    else "new_category_alias" if entity.entity_type == "Category"
                    else "new_store_alias" if entity.entity_type == "Store"
                    else "new_product_alias"
                ),
                "subject_id": entity.entity_id,
                "proposed_value": alias,
                "source": "verified_alias",
                "confirmation_count": len(entity.document_references),
                "current_confidence": entity.confidence.normalized,
                "evidence_ids": tuple(
                    evidence.evidence_id for evidence in context.context.evidence
                    if entity.entity_id in evidence.source_entity_ids
                ),
            }
            for entity in context.context.entities
            if entity.entity_type in {"Merchant", "Brand", "Category", "Store", "Product"}
            and len(entity.document_references) >= 2
            and entity.confidence.normalized >= 0.8
            for alias in entity.aliases
        )

