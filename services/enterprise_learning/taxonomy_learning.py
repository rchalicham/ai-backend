from __future__ import annotations

from services.cross_document_intelligence import IntelligenceResult


class TaxonomyLearningEngine:
    def suggest(self, context: IntelligenceResult):
        return tuple(
            {
                "candidate_type": "taxonomy_improvement",
                "subject_id": entity.entity_id,
                "proposed_value": {
                    "entityType": entity.entity_type,
                    "label": entity.label,
                    "aliases": entity.aliases,
                },
                "source": "verified_category_assignment",
                "confirmation_count": len(entity.document_references),
                "current_confidence": entity.confidence.normalized,
                "evidence_ids": tuple(
                    evidence.evidence_id for evidence in context.context.evidence
                    if entity.entity_id in evidence.source_entity_ids
                ),
            }
            for entity in context.context.entities
            if entity.entity_type in {"Category", "Department"}
            and len(entity.document_references) >= 2
            and entity.confidence.normalized >= 0.8
        )

