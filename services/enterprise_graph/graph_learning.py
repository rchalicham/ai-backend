from __future__ import annotations

from .models import EntityType, GraphLearningSuggestion, GraphSubgraph


class EnterpriseGraphLearningService:
    """Creates proposals only; it never changes ontology or graph knowledge."""

    def suggest(self, graph: GraphSubgraph) -> tuple[GraphLearningSuggestion, ...]:
        return tuple(
            GraphLearningSuggestion(
                "ontology_entity_review",
                "Review an unknown entity for a governed ontology extension.",
                {"entityId": node.id, "label": node.entity.label},
                tuple(node.entity.metadata.provenance),
                0.5,
                True,
            )
            for node in graph.nodes
            if (
                node.entity.entity_type == EntityType.UNKNOWN
                or str(node.entity.entity_type) == EntityType.UNKNOWN.value
            )
        )

