from __future__ import annotations

import json
from typing import Any

from .models import (
    EnterpriseEntity,
    EntityId,
    EntityMetadata,
    EntityProperty,
    GraphConfidence,
    GraphEdge,
    GraphNode,
    GraphSubgraph,
    GraphVersion,
    Relationship,
    RelationshipWeight,
)


class EnterpriseGraphLoader:
    def from_json(self, payload: str) -> GraphSubgraph:
        return self.from_dict(json.loads(payload))

    def from_dict(self, data: dict[str, Any]) -> GraphSubgraph:
        nodes = tuple(GraphNode(EnterpriseEntity(
            EntityId(**item["entity"]["entity_id"]),
            item["entity"]["entity_type"],
            item["entity"]["label"],
            tuple(EntityProperty(**value) for value in item["entity"].get("properties", ())),
            EntityMetadata(**item["entity"].get("metadata", {})),
        )) for item in data.get("nodes", ()))
        edges = tuple(GraphEdge(Relationship(
            relationship_id=item["relationship"]["relationship_id"],
            relationship_type=item["relationship"]["relationship_type"],
            source_id=EntityId(**item["relationship"]["source_id"]),
            target_id=EntityId(**item["relationship"]["target_id"]),
            weight=RelationshipWeight(**item["relationship"].get("weight", {})),
            confidence=GraphConfidence(
                value=item["relationship"].get("confidence", {}).get("value", 0.0),
                components=self._pairs(
                    item["relationship"].get("confidence", {}).get("components", {}),
                ),
                upstream_values=self._pairs(
                    item["relationship"].get("confidence", {}).get("upstream_values", {}),
                ),
            ),
            evidence_sources=tuple(item["relationship"].get("evidence_sources", ())),
            provenance=tuple(item["relationship"].get("provenance", ())),
            timestamp=item["relationship"].get("timestamp", ""),
            version=item["relationship"].get("version", "enterprise-graph-relationship-v1"),
            explanation=item["relationship"].get("explanation", ""),
            creation_source=item["relationship"].get("creation_source", "enterprise_graph_builder"),
        )) for item in data.get("edges", ()))
        return GraphSubgraph(
            graph_id=data["graph_id"],
            nodes=nodes,
            edges=edges,
            version=GraphVersion(**data.get("version", {})),
            ontology_version=data.get("ontology_version", "enterprise-ontology-v1"),
        )

    @staticmethod
    def _pairs(value: Any) -> tuple[tuple[str, float], ...]:
        items = value.items() if isinstance(value, dict) else value
        return tuple((str(key), float(item)) for key, item in items)
