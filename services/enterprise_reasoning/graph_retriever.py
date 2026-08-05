from __future__ import annotations

from typing import Any


class GraphRetriever:
    """Storage-neutral traversal over a serialized graph contract."""

    def nodes(self, graph: dict[str, Any] | None) -> tuple[dict[str, Any], ...]:
        if not graph:
            return ()
        value = graph.get("graph", graph)
        return tuple(value.get("nodes", ()))

    def edges(self, graph: dict[str, Any] | None) -> tuple[dict[str, Any], ...]:
        if not graph:
            return ()
        value = graph.get("graph", graph)
        return tuple(value.get("edges", ()))

    def neighborhood(self, graph, entity_id: str):
        edges = tuple(x for x in self.edges(graph) if entity_id in (
            self._identity(x.get("source_id")), self._identity(x.get("target_id")),
        ))
        ids = {entity_id}
        for edge in edges:
            ids.update((self._identity(edge.get("source_id")), self._identity(edge.get("target_id"))))
        return tuple(x for x in self.nodes(graph) if self._node_id(x) in ids), edges

    def subgraph(self, graph, entity_ids):
        wanted = set(entity_ids)
        return (
            tuple(x for x in self.nodes(graph) if self._node_id(x) in wanted),
            tuple(x for x in self.edges(graph) if self._identity(x.get("source_id")) in wanted
                  and self._identity(x.get("target_id")) in wanted),
        )

    def traverse(self, graph, start_id: str, relationship_type: str = ""):
        return tuple(x for x in self.edges(graph)
                     if self._identity(x.get("source_id")) == start_id
                     and (not relationship_type or x.get("relationship_type") == relationship_type))

    def shortest_path(self, graph, start_id: str, end_id: str):
        adjacency: dict[str, set[str]] = {}
        for edge in self.edges(graph):
            left, right = self._identity(edge.get("source_id")), self._identity(edge.get("target_id"))
            adjacency.setdefault(left, set()).add(right)
            adjacency.setdefault(right, set()).add(left)
        queue = [(start_id, (start_id,))]
        seen = {start_id}
        while queue:
            node, path = queue.pop(0)
            if node == end_id:
                return path
            for child in sorted(adjacency.get(node, ())):
                if child not in seen:
                    seen.add(child)
                    queue.append((child, (*path, child)))
        return ()

    def expand_evidence(self, graph, edge_ids):
        wanted = set(edge_ids)
        return tuple(x for x in self.edges(graph) if x.get("edge_id") in wanted)

    def ontology_aware(self, graph, entity_type: str):
        return tuple(x for x in self.nodes(graph)
                     if x.get("entity", {}).get("entity_type") == entity_type)

    @staticmethod
    def _identity(value):
        return value.get("value", "") if isinstance(value, dict) else str(value or "")

    def _node_id(self, node):
        return self._identity(node.get("entity", {}).get("entity_id"))
