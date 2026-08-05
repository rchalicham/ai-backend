from __future__ import annotations

from collections import defaultdict

from .models import GraphDiagnostic, GraphDiagnostics, GraphSubgraph
from .ontology import EnterpriseOntology


class EnterpriseGraphValidator:
    def __init__(self, ontology: EnterpriseOntology | None = None) -> None:
        self.ontology = ontology or EnterpriseOntology()

    def validate(self, graph: GraphSubgraph) -> GraphDiagnostics:
        errors: list[GraphDiagnostic] = []
        warnings: list[GraphDiagnostic] = []
        node_ids = [node.id for node in graph.nodes]
        duplicates = sorted({value for value in node_ids if node_ids.count(value) > 1})
        errors.extend(
            GraphDiagnostic("duplicate_node", "Graph contains a duplicate node identity.", "error", value)
            for value in duplicates
        )
        known = set(node_ids)
        node_types = {
            node.id: (
                node.entity.entity_type.value
                if hasattr(node.entity.entity_type, "value")
                else str(node.entity.entity_type)
            )
            for node in graph.nodes
        }
        edge_ids = set()
        acyclic_adjacency: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        for edge in graph.edges:
            relationship = edge.relationship
            if edge.id in edge_ids:
                errors.append(GraphDiagnostic(
                    "duplicate_edge", "Graph contains a duplicate relationship identity.", "error", edge.id,
                ))
            edge_ids.add(edge.id)
            source = str(relationship.source_id)
            target = str(relationship.target_id)
            if source not in known or target not in known:
                errors.append(GraphDiagnostic(
                    "dangling_edge", "Relationship references an entity absent from the graph.", "error", edge.id,
                ))
            definition = self.ontology.relationship_definition(relationship.relationship_type)
            if definition is None:
                errors.append(GraphDiagnostic(
                    "invalid_relationship_type", "Relationship is not defined by the active ontology.", "error", edge.id,
                ))
            elif source == target and not definition.allow_self_reference:
                errors.append(GraphDiagnostic(
                    "invalid_self_relationship", "Ontology prohibits this self relationship.", "error", edge.id,
                ))
            elif definition.source_types and node_types.get(source) not in definition.source_types:
                errors.append(GraphDiagnostic(
                    "invalid_relationship_source_type",
                    "Relationship source type violates the active ontology.",
                    "error",
                    edge.id,
                ))
            elif definition.target_types and node_types.get(target) not in definition.target_types:
                errors.append(GraphDiagnostic(
                    "invalid_relationship_target_type",
                    "Relationship target type violates the active ontology.",
                    "error",
                    edge.id,
                ))
            if definition and definition.acyclic:
                relationship_name = (
                    relationship.relationship_type.value
                    if hasattr(relationship.relationship_type, "value")
                    else str(relationship.relationship_type)
                )
                acyclic_adjacency[relationship_name][source].append(target)
            if not relationship.evidence_sources:
                warnings.append(GraphDiagnostic(
                    "relationship_missing_evidence", "Relationship has no evidence source.", "warning", edge.id,
                ))
            if not relationship.explanation:
                warnings.append(GraphDiagnostic(
                    "relationship_missing_explanation", "Relationship has no explanation.", "warning", edge.id,
                ))
        for node in graph.nodes:
            if not self.ontology.supports_entity(node.entity.entity_type):
                errors.append(GraphDiagnostic(
                    "invalid_entity_type", "Entity type is not defined by the active ontology.", "error", node.id,
                ))
        for relationship_name, adjacency in acyclic_adjacency.items():
            if self._has_cycle(adjacency):
                errors.append(GraphDiagnostic(
                    "prohibited_cycle",
                    f"A {relationship_name} relationship declared acyclic forms a cycle.",
                    "error",
                    relationship_name,
                ))
        return GraphDiagnostics(
            errors=tuple(errors),
            warnings=tuple(warnings),
            information=(GraphDiagnostic(
                "graph_validated",
                f"Validated {len(graph.nodes)} nodes and {len(graph.edges)} relationships.",
            ),),
        )

    @staticmethod
    def _has_cycle(adjacency: dict[str, list[str]]) -> bool:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> bool:
            if node in visiting:
                return True
            if node in visited:
                return False
            visiting.add(node)
            if any(visit(target) for target in adjacency.get(node, ())):
                return True
            visiting.remove(node)
            visited.add(node)
            return False

        return any(visit(node) for node in tuple(adjacency))
