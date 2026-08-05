from __future__ import annotations

from collections import defaultdict, deque

from .models import (
    EntityType,
    GraphEdge,
    GraphNode,
    GraphQuery,
    GraphResult,
    GraphSubgraph,
    RelationshipType,
)


class EnterpriseGraphQueryEngine:
    """Traverses the semantic contract without exposing repository technology."""

    def execute(self, graph: GraphSubgraph, query: GraphQuery) -> GraphResult:
        handlers = {
            "find_entity": lambda: self.find_entity(graph, query.entity_id or query.value),
            "find_neighbors": lambda: self.find_neighbors(graph, query.entity_id, query.relationship_type),
            "find_related_products": lambda: self.find_related_products(graph, query.entity_id, query.max_depth),
            "find_products_by_category": lambda: self.find_products_by_category(graph, query.value or query.entity_id),
            "find_merchants_selling_product": lambda: self.find_merchants_selling_product(graph, query.entity_id),
            "find_purchases_containing_product": lambda: self.find_purchases_containing_product(graph, query.entity_id),
            "find_brand_hierarchy": lambda: self.find_brand_hierarchy(graph, query.entity_id, query.max_depth),
            "find_nutrition_relationships": lambda: self.find_nutrition_relationships(graph, query.entity_id),
            "subgraph": lambda: self.subgraph(graph, query.entity_id, query.max_depth, query.limit),
        }
        result = handlers.get(query.query_type, lambda: GraphResult(query, explanations=("Unsupported graph query.",)))()
        return GraphResult(query, result.nodes[:query.limit], result.edges[:query.limit], result.paths, result.explanations)

    def find_entity(self, graph: GraphSubgraph, value: str) -> GraphResult:
        query = GraphQuery("find_entity", entity_id=value)
        folded = value.casefold()
        nodes = tuple(
            node for node in graph.nodes
            if node.id.casefold() == folded
            or node.entity.entity_id.value.casefold() == folded
            or node.entity.label.casefold() == folded
        )
        return GraphResult(query, nodes, explanations=(f"Found {len(nodes)} matching entities.",))

    def find_neighbors(
        self,
        graph: GraphSubgraph,
        entity_id: str,
        relationship_type: RelationshipType | str = RelationshipType.UNKNOWN,
    ) -> GraphResult:
        query = GraphQuery("find_neighbors", entity_id=entity_id, relationship_type=relationship_type)
        resolved = self._resolve_id(graph, entity_id)
        requested = self._value(relationship_type)
        edges = tuple(
            edge for edge in graph.edges
            if resolved in {str(edge.relationship.source_id), str(edge.relationship.target_id)}
            and (requested == RelationshipType.UNKNOWN.value or self._value(edge.relationship.relationship_type) == requested)
        )
        ids = {
            value for edge in edges
            for value in (str(edge.relationship.source_id), str(edge.relationship.target_id))
            if value != resolved
        }
        nodes = tuple(node for node in graph.nodes if node.id in ids)
        return GraphResult(query, nodes, edges, explanations=(f"Found {len(nodes)} neighbors.",))

    def shortest_path(self, graph: GraphSubgraph, source_id: str, target_id: str) -> GraphResult:
        query = GraphQuery("shortest_path", entity_id=source_id, value=target_id)
        source = self._resolve_id(graph, source_id)
        target = self._resolve_id(graph, target_id)
        adjacency, edge_lookup = self._adjacency(graph)
        queue = deque([(source, (source,))])
        visited = {source}
        while queue:
            current, path = queue.popleft()
            if current == target:
                edges = tuple(edge_lookup[(path[index], path[index + 1])] for index in range(len(path) - 1))
                nodes = tuple(node for node in graph.nodes if node.id in set(path))
                return GraphResult(query, nodes, edges, (path,), ("Shortest unweighted semantic path.",))
            for neighbor in sorted(adjacency[current]):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, (*path, neighbor)))
        return GraphResult(query, explanations=("No semantic path found.",))

    def find_related_products(self, graph: GraphSubgraph, entity_id: str, max_depth: int = 2) -> GraphResult:
        result = self.subgraph(graph, entity_id, max_depth)
        return GraphResult(
            GraphQuery("find_related_products", entity_id=entity_id, max_depth=max_depth),
            tuple(node for node in result.nodes if self._value(node.entity.entity_type) == EntityType.PRODUCT.value),
            result.edges,
            result.paths,
            ("Products connected within the requested traversal depth.",),
        )

    def find_products_by_category(self, graph: GraphSubgraph, category: str) -> GraphResult:
        category_nodes = self._nodes(graph, EntityType.CATEGORY, category)
        category_ids = {node.id for node in category_nodes}
        edges = tuple(
            edge for edge in graph.edges
            if self._value(edge.relationship.relationship_type) == RelationshipType.HAS_CATEGORY.value
            and str(edge.relationship.target_id) in category_ids
        )
        product_ids = {str(edge.relationship.source_id) for edge in edges}
        return GraphResult(
            GraphQuery("find_products_by_category", value=category),
            tuple(node for node in graph.nodes if node.id in product_ids),
            edges,
            explanations=(f"Products classified in category '{category}'.",),
        )

    def find_merchants_selling_product(self, graph: GraphSubgraph, product_id: str) -> GraphResult:
        return self._typed_neighbors(graph, product_id, RelationshipType.SOLD_BY, EntityType.MERCHANT, "find_merchants_selling_product")

    def find_purchases_containing_product(self, graph: GraphSubgraph, product_id: str) -> GraphResult:
        related_lines = self.find_neighbors(graph, product_id, RelationshipType.RELATED_TO)
        purchase_nodes: dict[str, GraphNode] = {}
        edges = list(related_lines.edges)
        for line in related_lines.nodes:
            if self._value(line.entity.entity_type) != EntityType.LINE_ITEM.value:
                continue
            receipts = self.find_neighbors(graph, line.id, RelationshipType.CONTAINS)
            edges.extend(receipts.edges)
            for node in receipts.nodes:
                if self._value(node.entity.entity_type) in {EntityType.RECEIPT.value, EntityType.PURCHASE.value}:
                    purchase_nodes[node.id] = node
        return GraphResult(
            GraphQuery("find_purchases_containing_product", entity_id=product_id),
            tuple(purchase_nodes.values()), tuple(edges),
            explanations=("Purchases connected through extracted line items.",),
        )

    def find_brand_hierarchy(self, graph: GraphSubgraph, brand_id: str, max_depth: int = 3) -> GraphResult:
        result = self.subgraph(graph, brand_id, max_depth)
        allowed = {RelationshipType.HAS_PARENT.value, RelationshipType.HAS_CHILD.value, RelationshipType.BELONGS_TO.value}
        return GraphResult(
            GraphQuery("find_brand_hierarchy", entity_id=brand_id, max_depth=max_depth),
            result.nodes,
            tuple(edge for edge in result.edges if self._value(edge.relationship.relationship_type) in allowed),
            result.paths,
            ("Brand hierarchy traversal.",),
        )

    def find_nutrition_relationships(self, graph: GraphSubgraph, product_id: str) -> GraphResult:
        result = self.find_neighbors(graph, product_id, RelationshipType.RELATED_TO)
        return GraphResult(
            GraphQuery("find_nutrition_relationships", entity_id=product_id),
            tuple(node for node in result.nodes if self._value(node.entity.entity_type) in {EntityType.NUTRITION.value, EntityType.INGREDIENT.value}),
            result.edges,
            explanations=("Nutrition and ingredient relationships for the Product.",),
        )

    def subgraph(self, graph: GraphSubgraph, entity_id: str, max_depth: int = 1, limit: int = 100) -> GraphResult:
        query = GraphQuery("subgraph", entity_id=entity_id, max_depth=max_depth, limit=limit)
        start = self._resolve_id(graph, entity_id)
        adjacency, _ = self._adjacency(graph)
        visited = {start}
        frontier = {start}
        for _ in range(max(0, max_depth)):
            frontier = {
                neighbor for node in frontier for neighbor in adjacency[node]
                if neighbor not in visited
            }
            visited.update(frontier)
            if not frontier or len(visited) >= limit:
                break
        nodes = tuple(node for node in graph.nodes if node.id in visited)[:limit]
        selected = {node.id for node in nodes}
        edges = tuple(
            edge for edge in graph.edges
            if str(edge.relationship.source_id) in selected and str(edge.relationship.target_id) in selected
        )[:limit]
        return GraphResult(query, nodes, edges, explanations=(f"Subgraph through depth {max_depth}.",))

    def traverse(self, graph: GraphSubgraph, entity_id: str, max_depth: int = 1, limit: int = 100) -> GraphResult:
        return self.subgraph(graph, entity_id, max_depth, limit)

    def _typed_neighbors(self, graph, entity_id, relationship_type, entity_type, query_type):
        result = self.find_neighbors(graph, entity_id, relationship_type)
        return GraphResult(
            GraphQuery(query_type, entity_id=entity_id),
            tuple(node for node in result.nodes if self._value(node.entity.entity_type) == entity_type.value),
            result.edges,
            explanations=(query_type.replace("_", " ").capitalize() + ".",),
        )

    @staticmethod
    def _value(value) -> str:
        return value.value if hasattr(value, "value") else str(value)

    def _nodes(self, graph, entity_type, label):
        return tuple(
            node for node in graph.nodes
            if self._value(node.entity.entity_type) == entity_type.value
            and (not label or node.entity.label.casefold() == label.casefold() or node.entity.entity_id.value.casefold() == label.casefold())
        )

    @staticmethod
    def _resolve_id(graph: GraphSubgraph, value: str) -> str:
        return next((
            node.id for node in graph.nodes
            if node.id == value or node.entity.entity_id.value == value or node.entity.label.casefold() == value.casefold()
        ), value)

    @staticmethod
    def _adjacency(graph: GraphSubgraph):
        adjacency: dict[str, set[str]] = defaultdict(set)
        edges: dict[tuple[str, str], GraphEdge] = {}
        for edge in graph.edges:
            source = str(edge.relationship.source_id)
            target = str(edge.relationship.target_id)
            adjacency[source].add(target)
            adjacency[target].add(source)
            edges[(source, target)] = edge
            edges[(target, source)] = edge
        return adjacency, edges

