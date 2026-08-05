from __future__ import annotations

import hashlib

from .models import ContextEntity, EvidenceRecord, Timeline, TimelineEvent


class TimelineEngine:
    def build(
        self,
        entities: tuple[ContextEntity, ...],
        evidence: tuple[EvidenceRecord, ...],
    ) -> tuple[Timeline, ...]:
        evidence_by_entity: dict[str, tuple[str, ...]] = {
            entity.entity_id: tuple(
                item.evidence_id for item in evidence
                if entity.entity_id in item.source_entity_ids
            )
            for entity in entities
        }
        timelines = []
        for entity in entities:
            if not entity.document_references:
                continue
            events = tuple(sorted((
                TimelineEvent(
                    self._id(entity.entity_id, reference.document_id, reference.timestamp),
                    self._event_type(entity.entity_type),
                    reference.timestamp,
                    reference,
                    (entity.entity_id,),
                    evidence_by_entity.get(entity.entity_id, ()),
                    f"{entity.label} referenced by {self._value(reference.document_type)} {reference.document_id}.",
                    entity.confidence,
                )
                for reference in entity.document_references
            ), key=lambda item: (item.timestamp, item.event_id)))
            timelines.append(Timeline(
                f"timeline:{entity.entity_id}",
                entity.entity_id,
                events,
            ))
        return tuple(timelines)

    @staticmethod
    def _event_type(entity_type: str) -> str:
        return {
            "Product": "product_purchase",
            "Merchant": "merchant_interaction",
            "Warranty": "warranty_lifecycle",
            "MedicalRecord": "medical_treatment",
            "Price": "expense_observation",
            "Location": "travel_or_location",
        }.get(entity_type, "document_reference")

    @staticmethod
    def _id(*values: str) -> str:
        return hashlib.sha256("|".join(values).encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def _value(value) -> str:
        return value.value if hasattr(value, "value") else str(value)

