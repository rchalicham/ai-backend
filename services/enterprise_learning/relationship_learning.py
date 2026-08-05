from __future__ import annotations

from services.cross_document_intelligence import IntelligenceResult


class RelationshipLearningEngine:
    def suggest(self, context: IntelligenceResult):
        return tuple(
            {
                "candidate_type": "relationship_confidence_update",
                "subject_id": relationship.relationship_id,
                "proposed_value": {
                    "relationshipType": relationship.relationship_type,
                    "source": relationship.source_entity_id,
                    "target": relationship.target_entity_id,
                    "direction": "strengthen",
                },
                "source": "verified_relationship",
                "confirmation_count": len(relationship.document_references),
                "current_confidence": relationship.confidence.normalized,
                "evidence_ids": relationship.evidence_ids,
            }
            for relationship in context.context.relationships
            if len(relationship.document_references) >= 2
            and relationship.confidence.normalized >= 0.8
        )

