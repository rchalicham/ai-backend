from __future__ import annotations

import hashlib

from .confidence_engine import CrossDocumentConfidenceEngine
from .models import ContextEntity, ContextRelationship, Correlation


class CorrelationEngine:
    TYPES_BY_ENTITY = {
        "Product": "purchase_correlation",
        "Merchant": "merchant_correlation",
        "Customer": "customer_correlation",
        "Location": "geographic_correlation",
        "Category": "category_correlation",
    }

    def __init__(self, confidence: CrossDocumentConfidenceEngine | None = None) -> None:
        self.confidence = confidence or CrossDocumentConfidenceEngine()

    def correlate(
        self,
        entities: tuple[ContextEntity, ...],
        relationships: tuple[ContextRelationship, ...] = (),
    ) -> tuple[Correlation, ...]:
        values = []
        document_pairs: dict[tuple[str, str], tuple[object, object, set[str]]] = {}
        for entity in entities:
            documents = tuple(dict.fromkeys(entity.document_references))
            if len(documents) < 2:
                continue
            document_types = {self._value(item.document_type) for item in documents}
            correlation_type = self.TYPES_BY_ENTITY.get(entity.entity_type, "entity_correlation")
            if len(document_types) > 1:
                correlation_type = "cross_domain_correlation"
            correlation_id = self._id(correlation_type, entity.entity_id, *(item.document_id for item in documents))
            evidence_id = f"evidence:{correlation_id}"
            confidence = self.confidence.aggregate(
                graph=entity.confidence.graph,
                entity=entity.confidence.entity,
                evidence=min(1.0, len(documents) / 2),
                temporal=1.0 if all(item.timestamp for item in documents) else 0.5,
                relationship=entity.confidence.relationship,
                upstream_values=(("entity", entity.confidence.normalized),),
            )
            values.append(Correlation(
                correlation_id,
                correlation_type,
                (entity.entity_id,),
                documents,
                (evidence_id,),
                f"Canonical {entity.entity_type} '{entity.label}' appears in {len(documents)} independent documents.",
                confidence,
            ))
            for index, left in enumerate(documents):
                for right in documents[index + 1:]:
                    pair = tuple(sorted((left.document_id, right.document_id)))
                    previous = document_pairs.get(pair)
                    shared = previous[2] if previous else set()
                    shared.add(entity.entity_id)
                    document_pairs[pair] = (left, right, shared)
            if all(item.timestamp for item in documents):
                temporal_id = self._id("temporal_correlation", entity.entity_id)
                values.append(Correlation(
                    temporal_id,
                    "temporal_correlation",
                    (entity.entity_id,),
                    documents,
                    (f"evidence:{temporal_id}",),
                    f"Chronological references for {entity.label} can be ordered without changing source evidence.",
                    confidence,
                ))
        for _, (left, right, shared) in sorted(document_pairs.items()):
            correlation_id = self._id("document_correlation", left.document_id, right.document_id)
            values.append(Correlation(
                correlation_id,
                "document_correlation",
                tuple(sorted(shared)),
                (left, right),
                (f"evidence:{correlation_id}",),
                f"Documents share {len(shared)} resolved canonical entities.",
                self.confidence.aggregate(
                    graph=1.0, entity=min(1.0, len(shared) / 2),
                    evidence=1.0, temporal=0.8, relationship=0.8,
                ),
            ))
        for relationship in relationships:
            if len(relationship.document_references) < 2:
                continue
            correlation_id = self._id("relationship_correlation", relationship.relationship_id)
            values.append(Correlation(
                correlation_id,
                "relationship_correlation",
                (relationship.source_entity_id, relationship.target_entity_id),
                relationship.document_references,
                (f"evidence:{correlation_id}",),
                f"Relationship {relationship.relationship_type} recurs across independent documents.",
                relationship.confidence,
            ))
        return tuple(values)

    @staticmethod
    def _id(*values: str) -> str:
        return hashlib.sha256("|".join(values).encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def _value(value) -> str:
        return value.value if hasattr(value, "value") else str(value)
