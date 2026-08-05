from __future__ import annotations

import hashlib
from collections import defaultdict

from services.enterprise_graph import GraphSubgraph

from .models import (
    Confidence,
    ContextEntity,
    ContextRelationship,
    Correlation,
    DocumentReference,
    EvidenceRecord,
    MemorySnapshot,
    Pattern,
    Timeline,
)


class EnterpriseMemoryEngine:
    """Builds deterministic semantic memory; this is not LLM memory."""

    def merge_entities(
        self,
        current: tuple[ContextEntity, ...],
        historical: tuple[MemorySnapshot, ...],
    ) -> tuple[ContextEntity, ...]:
        groups: dict[str, list[ContextEntity]] = defaultdict(list)
        for entity in current:
            groups[entity.entity_id].append(entity)
        for snapshot in historical:
            for entity in snapshot.entities:
                groups[entity.entity_id].append(entity)
        values = []
        for entity_id in sorted(groups):
            entries = groups[entity_id]
            values.append(ContextEntity(
                entity_id,
                entries[0].entity_type,
                entries[0].label,
                tuple(dict.fromkeys(
                    value for item in entries for value in (item.label, *item.aliases)
                    if value != entries[0].label
                )),
                tuple(dict.fromkeys(
                    reference for item in entries for reference in item.document_references
                )),
                tuple(dict.fromkeys(
                    node_id for item in entries for node_id in item.graph_node_ids
                )),
                max(entries, key=lambda item: item.confidence.normalized).confidence,
                tuple(dict.fromkeys(
                    value for item in entries for value in item.provenance
                )),
            ))
        return tuple(values)

    def relationships(
        self,
        documents: tuple[tuple[DocumentReference, GraphSubgraph], ...],
        entities: tuple[ContextEntity, ...],
    ) -> tuple[ContextRelationship, ...]:
        node_to_entity = {
            node_id: entity.entity_id
            for entity in entities for node_id in entity.graph_node_ids
        }
        values: dict[str, ContextRelationship] = {}
        for reference, graph in documents:
            for edge in graph.edges:
                relationship = edge.relationship
                source = node_to_entity.get(str(relationship.source_id))
                target = node_to_entity.get(str(relationship.target_id))
                if not source or not target:
                    continue
                relationship_type = self._value(relationship.relationship_type)
                key = f"{source}|{relationship_type}|{target}"
                relationship_id = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
                previous = values.get(relationship_id)
                references = tuple(dict.fromkeys((
                    *(previous.document_references if previous else ()),
                    reference,
                )))
                evidence = tuple(dict.fromkeys((
                    *(previous.evidence_ids if previous else ()),
                    *relationship.evidence_sources,
                )))
                confidence_value = relationship.confidence.value
                values[relationship_id] = ContextRelationship(
                    relationship_id,
                    relationship_type,
                    source,
                    target,
                    references,
                    evidence,
                    Confidence(
                        confidence_value,
                        graph=confidence_value,
                        relationship=confidence_value,
                        upstream_values=(("graphRelationship", confidence_value),),
                    ),
                    tuple(dict.fromkeys((
                        *(previous.provenance if previous else ()),
                        *relationship.provenance,
                    ))),
                    relationship.explanation,
                )
        return tuple(values[key] for key in sorted(values))

    def snapshot(
        self,
        memory_id: str,
        documents: tuple[DocumentReference, ...],
        entities: tuple[ContextEntity, ...],
        relationships: tuple[ContextRelationship, ...],
        timelines: tuple[Timeline, ...],
        evidence: tuple[EvidenceRecord, ...],
        patterns: tuple[Pattern, ...],
        correlations: tuple[Correlation, ...],
    ) -> MemorySnapshot:
        return MemorySnapshot(
            memory_id,
            tuple(dict.fromkeys(documents)),
            entities,
            relationships,
            timelines,
            evidence,
            patterns,
            correlations,
            deterministic=True,
            llm_memory=False,
        )

    @staticmethod
    def _value(value) -> str:
        return value.value if hasattr(value, "value") else str(value)

