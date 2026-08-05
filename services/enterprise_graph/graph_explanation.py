from __future__ import annotations

from .models import GraphEdge, GraphSubgraph


class EnterpriseGraphExplanationEngine:
    def explain_edge(self, edge: GraphEdge) -> str:
        relationship = edge.relationship
        return (
            f"{relationship.relationship_type.value if hasattr(relationship.relationship_type, 'value') else relationship.relationship_type}: "
            f"{relationship.source_id} → {relationship.target_id}; "
            f"{relationship.explanation or 'no explanation'} "
            f"(confidence {relationship.confidence.value:.3f}, "
            f"source {relationship.creation_source})."
        )

    def explain_graph(self, graph: GraphSubgraph) -> tuple[str, ...]:
        return tuple(self.explain_edge(edge) for edge in graph.edges)

