from __future__ import annotations

from services.cross_document_intelligence import IntelligenceResult


class MerchantLearningEngine:
    def suggest(self, context: IntelligenceResult):
        return tuple(
            {
                "candidate_type": "merchant_metadata_improvement",
                "subject_id": entity.entity_id,
                "proposed_value": {
                    "canonicalName": entity.label,
                    "namingVariations": entity.aliases,
                    "observationCount": len(entity.document_references),
                },
                "source": "verified_merchant_mapping",
                "confirmation_count": len(entity.document_references),
                "current_confidence": entity.confidence.normalized,
                "evidence_ids": tuple(
                    evidence.evidence_id for evidence in context.context.evidence
                    if entity.entity_id in evidence.source_entity_ids
                ),
            }
            for entity in context.context.entities
            if entity.entity_type in {"Merchant", "Store"}
            and len(entity.document_references) >= 2
            and entity.confidence.normalized >= 0.8
        )

