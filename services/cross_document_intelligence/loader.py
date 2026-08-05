from __future__ import annotations

import json
from typing import Any

from .models import (
    Confidence,
    ContextEntity,
    ContextRelationship,
    Correlation,
    DocumentReference,
    EvidenceRecord,
    MemorySnapshot,
    MemoryVersion,
    Pattern,
    Timeline,
    TimelineEvent,
)


class CrossDocumentLoader:
    def memory_from_json(self, payload: str) -> MemorySnapshot:
        return self.memory_from_dict(json.loads(payload))

    def memory_from_dict(self, data: dict[str, Any]) -> MemorySnapshot:
        documents = tuple(self._document(item) for item in data.get("documents", ()))
        entities = tuple(ContextEntity(
            item["entity_id"],
            item["entity_type"],
            item["label"],
            tuple(item.get("aliases", ())),
            tuple(self._document(value) for value in item.get("document_references", ())),
            tuple(item.get("graph_node_ids", ())),
            self._confidence(item.get("confidence", {})),
            tuple(item.get("provenance", ())),
        ) for item in data.get("entities", ()))
        relationships = tuple(ContextRelationship(
            item["relationship_id"],
            item["relationship_type"],
            item["source_entity_id"],
            item["target_entity_id"],
            tuple(self._document(value) for value in item.get("document_references", ())),
            tuple(item.get("evidence_ids", ())),
            self._confidence(item.get("confidence", {})),
            tuple(item.get("provenance", ())),
            item.get("explanation", ""),
        ) for item in data.get("relationships", ()))
        evidence = tuple(self._evidence(item) for item in data.get("evidence", ()))
        timelines = tuple(Timeline(
            item["timeline_id"],
            item["subject_entity_id"],
            tuple(TimelineEvent(
                event["event_id"],
                event["event_type"],
                event["timestamp"],
                self._document(event["document_reference"]),
                tuple(event.get("entity_ids", ())),
                tuple(event.get("evidence_ids", ())),
                event.get("description", ""),
                self._confidence(event.get("confidence", {})),
            ) for event in item.get("events", ())),
            item.get("version", "cross-document-timeline-v1"),
        ) for item in data.get("timelines", ()))
        patterns = tuple(Pattern(
            item["pattern_id"],
            item["pattern_type"],
            tuple(item.get("subject_entity_ids", ())),
            tuple(self._document(value) for value in item.get("document_references", ())),
            tuple(item.get("evidence_ids", ())),
            item.get("occurrences", 0),
            item.get("description", ""),
            self._confidence(item.get("confidence", {})),
            item.get("predictive", False),
        ) for item in data.get("patterns", ()))
        correlations = tuple(Correlation(
            item["correlation_id"],
            item["correlation_type"],
            tuple(item.get("entity_ids", ())),
            tuple(self._document(value) for value in item.get("document_references", ())),
            tuple(item.get("evidence_ids", ())),
            item.get("reason", ""),
            self._confidence(item.get("confidence", {})),
            item.get("timestamp", ""),
            item.get("version", "cross-document-correlation-v1"),
        ) for item in data.get("correlations", ()))
        return MemorySnapshot(
            data["memory_id"],
            documents,
            entities,
            relationships,
            timelines,
            evidence,
            patterns,
            correlations,
            MemoryVersion(**data.get("version", {})),
            data.get("deterministic", True),
            data.get("llm_memory", False),
        )

    def _evidence(self, item: dict[str, Any]) -> EvidenceRecord:
        return EvidenceRecord(
            item["evidence_id"],
            tuple(self._document(value) for value in item.get("supporting_documents", ())),
            tuple(item.get("evidence_references", ())),
            tuple(item.get("source_entity_ids", ())),
            item.get("reason", ""),
            self._confidence(item.get("confidence", {})),
            item.get("timestamp", ""),
            item.get("version", "cross-document-evidence-v1"),
        )

    @staticmethod
    def _document(item: dict[str, Any]) -> DocumentReference:
        return DocumentReference(
            item["document_id"],
            item.get("document_type", "Unknown"),
            item.get("graph_id", ""),
            item.get("timestamp", ""),
            item.get("version", "document-reference-v1"),
            tuple(item.get("evidence_references", ())),
        )

    @staticmethod
    def _confidence(item: dict[str, Any]) -> Confidence:
        return Confidence(
            item.get("normalized", 0.0),
            item.get("graph", 0.0),
            item.get("entity", 0.0),
            item.get("evidence", 0.0),
            item.get("temporal", 0.0),
            item.get("relationship", 0.0),
            CrossDocumentLoader._pairs(item.get("components", {})),
            CrossDocumentLoader._pairs(item.get("upstream_values", {})),
        )

    @staticmethod
    def _pairs(value: Any) -> tuple[tuple[str, float], ...]:
        items = value.items() if isinstance(value, dict) else value
        return tuple((str(key), float(item)) for key, item in items)

