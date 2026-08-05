from __future__ import annotations

from dataclasses import replace
from typing import Protocol, runtime_checkable

from .models import GraphSubgraph, GraphVersionComparison, utc_now


@runtime_checkable
class EnterpriseGraphRepositoryProtocol(Protocol):
    def load_graph(self, graph_id: str, version: int | None = None) -> GraphSubgraph | None: ...
    def save_graph(self, graph: GraphSubgraph) -> GraphSubgraph: ...
    def version_graph(self, graph: GraphSubgraph, expected_version: int | None = None) -> GraphSubgraph: ...
    def archive_graph(self, graph_id: str, version: int | None = None) -> GraphSubgraph: ...
    def compare_graph_versions(
        self, graph_id: str, from_version: int, to_version: int,
    ) -> GraphVersionComparison: ...


class EnterpriseGraphRepository:
    """In-memory reference repository behind a storage-agnostic graph contract."""

    def __init__(self) -> None:
        self._graphs: dict[str, list[GraphSubgraph]] = {}

    def load_graph(self, graph_id: str, version: int | None = None) -> GraphSubgraph | None:
        history = self._graphs.get(graph_id, ())
        if version is None:
            return next((item for item in reversed(history) if item.version.status == "active"), None)
        return next((item for item in history if item.version.entity_version == version), None)

    def save_graph(self, graph: GraphSubgraph) -> GraphSubgraph:
        if not graph.graph_id:
            raise ValueError("enterprise_graph_requires_identity")
        if self._graphs.get(graph.graph_id):
            raise ValueError("enterprise_graph_already_exists_use_version_graph")
        saved = replace(graph, version=replace(
            graph.version, entity_version=1, status="active",
            updated_at=utc_now(), supersedes_version=None,
        ))
        self._graphs[graph.graph_id] = [saved]
        return saved

    def version_graph(
        self, graph: GraphSubgraph, expected_version: int | None = None,
    ) -> GraphSubgraph:
        history = self._graphs.get(graph.graph_id, [])
        current = history[-1] if history else None
        current_version = current.version.entity_version if current else 0
        if expected_version is not None and expected_version != current_version:
            raise ValueError("enterprise_graph_version_conflict")
        saved = replace(graph, version=replace(
            graph.version,
            entity_version=current_version + 1,
            status="active",
            created_at=current.version.created_at if current else graph.version.created_at,
            updated_at=utc_now(),
            supersedes_version=current_version or None,
        ))
        self._graphs.setdefault(graph.graph_id, []).append(saved)
        return saved

    def archive_graph(self, graph_id: str, version: int | None = None) -> GraphSubgraph:
        history = self._graphs.get(graph_id, [])
        value = self.load_graph(graph_id, version)
        if value is None:
            raise KeyError("enterprise_graph_not_found")
        archived = replace(value, version=replace(
            value.version, status="archived", updated_at=utc_now(),
        ))
        history[history.index(value)] = archived
        return archived

    def compare_graph_versions(
        self, graph_id: str, from_version: int, to_version: int,
    ) -> GraphVersionComparison:
        before = self.load_graph(graph_id, from_version)
        after = self.load_graph(graph_id, to_version)
        if before is None or after is None:
            raise KeyError("enterprise_graph_version_not_found")
        before_nodes = {item.id: item for item in before.nodes}
        after_nodes = {item.id: item for item in after.nodes}
        before_edges = {item.id: item for item in before.edges}
        after_edges = {item.id: item for item in after.edges}
        return GraphVersionComparison(
            graph_id,
            from_version,
            to_version,
            tuple(sorted(set(after_nodes) - set(before_nodes))),
            tuple(sorted(set(before_nodes) - set(after_nodes))),
            tuple(sorted(
                key for key in set(before_nodes) & set(after_nodes)
                if before_nodes[key] != after_nodes[key]
            )),
            tuple(sorted(set(after_edges) - set(before_edges))),
            tuple(sorted(set(before_edges) - set(after_edges))),
            tuple(sorted(
                key for key in set(before_edges) & set(after_edges)
                if before_edges[key] != after_edges[key]
            )),
        )

    loadGraph = load_graph
    saveGraph = save_graph
    versionGraph = version_graph
    archiveGraph = archive_graph
    compareGraphVersions = compare_graph_versions
