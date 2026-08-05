from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from services.product_intelligence import ProductIntelligenceResult

from .models import (
    EnterpriseEntity,
    EntityId,
    EntityMetadata,
    EntityProperty,
    EntityType,
    GraphConfidence,
    GraphEdge,
    GraphNode,
    GraphSubgraph,
    Relationship,
    RelationshipType,
    RelationshipWeight,
)


class EnterpriseGraphBuilder:
    """Builds a request-scoped semantic graph without writing storage."""

    def build(
        self,
        product_intelligence: ProductIntelligenceResult,
        *,
        receipt_id: str,
        merchant_key: str = "",
        receipt_context: Mapping[str, Any] | None = None,
    ) -> GraphSubgraph:
        context = dict(receipt_context or {})
        graph_id = f"receipt-graph:{receipt_id or 'unknown'}"
        nodes: dict[str, GraphNode] = {}
        edges: dict[str, GraphEdge] = {}

        receipt = self._node(
            receipt_id or "unknown",
            EntityType.RECEIPT,
            receipt_id or "Unknown Receipt",
            {
                "date": context.get("transactionDate") or context.get("date") or "",
                "total": context.get("total") or (context.get("facts") or {}).get("total", ""),
            },
            "current_parser_read_only_view",
            (f"receipt:{receipt_id or 'unknown'}",),
        )
        nodes[receipt.id] = receipt

        merchant = None
        if merchant_key:
            merchant = self._node(
                merchant_key, EntityType.MERCHANT, merchant_key,
                {}, "explicit_merchant_context", (f"merchant-knowledge:{merchant_key}",),
            )
            nodes[merchant.id] = merchant
            self._connect(
                edges, receipt, merchant, RelationshipType.PURCHASED_FROM,
                1.0, ("explicit merchant knowledge key",),
                "Receipt is associated with the explicitly supplied merchant context.",
            )

        for enrichment in product_intelligence.enrichments:
            line = self._node(
                f"{receipt_id or 'unknown'}:line:{enrichment.item_index}",
                EntityType.LINE_ITEM,
                enrichment.original_description or f"Line Item {enrichment.item_index}",
                {
                    "itemIndex": enrichment.item_index,
                    "originalDescription": enrichment.original_description,
                    "normalizedDescription": enrichment.normalized_description,
                    "matchStrategy": enrichment.match_strategy,
                },
                "product_intelligence",
                (f"receipt-item:{enrichment.item_index}",),
            )
            nodes[line.id] = line
            self._connect(
                edges, receipt, line, RelationshipType.CONTAINS, 1.0,
                (f"receipt-item:{enrichment.item_index}",),
                "Receipt contains the extracted line item at its stable item position.",
            )

            product = None
            if enrichment.canonical_product is not None:
                value = enrichment.canonical_product
                product = self._node(
                    value.product_id, EntityType.PRODUCT, value.canonical_name,
                    {"productVersion": value.version.entity_version},
                    "approved_product_repository",
                    (f"canonical-product:{value.product_id}",),
                )
                nodes[product.id] = product
                self._connect(
                    edges, line, product, RelationshipType.RELATED_TO,
                    enrichment.confidence.product_match,
                    (f"receipt-item:{enrichment.item_index}", *enrichment.explanation.knowledge_sources),
                    enrichment.explanation.summary,
                    upstream=(("productMatch", enrichment.confidence.product_match),),
                )

            department = self._knowledge_node(
                nodes, EntityType.DEPARTMENT, enrichment.department.name,
            )
            category = self._knowledge_node(
                nodes, EntityType.CATEGORY, enrichment.category.name,
            )
            if category and department:
                self._connect(
                    edges, category, department, RelationshipType.BELONGS_TO,
                    enrichment.confidence.category_match,
                    ("product category assignment",),
                    f"Category '{category.entity.label}' belongs to department '{department.entity.label}'.",
                )
            if product and category:
                self._connect(
                    edges, product, category, RelationshipType.HAS_CATEGORY,
                    enrichment.confidence.category_match,
                    tuple(enrichment.explanation.knowledge_sources) or ("product classification",),
                    enrichment.explanation.category_reason,
                )

            brand = self._knowledge_node(
                nodes, EntityType.BRAND, enrichment.brand.name, unknown="Unknown Brand",
            )
            manufacturer = self._knowledge_node(
                nodes, EntityType.MANUFACTURER, enrichment.manufacturer.name,
            )
            if product and brand:
                self._connect(
                    edges, product, brand, RelationshipType.HAS_BRAND,
                    enrichment.confidence.brand_match,
                    tuple(enrichment.explanation.knowledge_sources) or ("brand engine",),
                    enrichment.explanation.brand_reason,
                )
            if product and manufacturer:
                self._connect(
                    edges, product, manufacturer, RelationshipType.HAS_MANUFACTURER,
                    enrichment.confidence.brand_match,
                    tuple(enrichment.explanation.knowledge_sources) or ("brand engine",),
                    f"Approved Product knowledge associates '{product.entity.label}' with '{manufacturer.entity.label}'.",
                )
            if merchant and product:
                self._connect(
                    edges, product, merchant, RelationshipType.SOLD_BY,
                    enrichment.confidence.merchant_match,
                    ("explicit merchant context",),
                    "Canonical Product was observed on a receipt with explicit merchant context.",
                )

            if enrichment.pricing.observed_price is not None:
                price = self._node(
                    f"{receipt_id or 'unknown'}:price:{enrichment.item_index}",
                    EntityType.PRICE,
                    str(enrichment.pricing.observed_price),
                    {"value": enrichment.pricing.observed_price},
                    "product_intelligence_pricing",
                    (f"receipt-item:{enrichment.item_index}",),
                )
                nodes[price.id] = price
                self._connect(
                    edges, line, price, RelationshipType.RELATED_TO, 1.0,
                    (f"receipt-item:{enrichment.item_index}",),
                    "Line item carries the observed, unmodified receipt price.",
                )
                if enrichment.pricing.currency:
                    currency = self._knowledge_node(
                        nodes, EntityType.CURRENCY, enrichment.pricing.currency,
                    )
                    if currency:
                        self._connect(
                            edges, price, currency, RelationshipType.USES, 1.0,
                            ("receipt currency",),
                            "Observed price uses the receipt currency.",
                        )

            nutrition_values = {
                key: value for key, value in (
                    ("calories", enrichment.nutrition.calories),
                    ("protein", enrichment.nutrition.protein),
                    ("fat", enrichment.nutrition.fat),
                    ("carbohydrates", enrichment.nutrition.carbohydrates),
                    ("sugar", enrichment.nutrition.sugar),
                    ("fiber", enrichment.nutrition.fiber),
                    ("sodium", enrichment.nutrition.sodium),
                ) if value is not None
            }
            if product and nutrition_values:
                nutrition = self._node(
                    f"{product.entity.entity_id.value}:nutrition",
                    EntityType.NUTRITION,
                    f"{product.entity.label} Nutrition",
                    nutrition_values,
                    enrichment.nutrition.source or "approved_product_repository",
                    tuple(enrichment.explanation.knowledge_sources),
                )
                nodes[nutrition.id] = nutrition
                self._connect(
                    edges, product, nutrition, RelationshipType.RELATED_TO,
                    enrichment.confidence.knowledge_match,
                    tuple(enrichment.explanation.knowledge_sources),
                    "Canonical Product has an approved nutrition profile.",
                )

        return GraphSubgraph(
            graph_id=graph_id,
            nodes=tuple(nodes[key] for key in sorted(nodes)),
            edges=tuple(edges[key] for key in sorted(edges)),
        )

    def _knowledge_node(
        self,
        nodes: dict[str, GraphNode],
        entity_type: EntityType,
        label: str,
        *,
        unknown: str = "Unknown",
    ) -> GraphNode | None:
        if not label or label == unknown:
            return None
        node = self._node(label, entity_type, label, {}, "product_intelligence", ())
        nodes[node.id] = node
        return node

    def _node(
        self,
        value: str,
        entity_type: EntityType,
        label: str,
        properties: Mapping[str, Any],
        source: str,
        provenance: tuple[str, ...],
    ) -> GraphNode:
        entity_id = EntityId(self._slug(value), entity_type.value.lower())
        return GraphNode(EnterpriseEntity(
            entity_id,
            entity_type,
            label,
            tuple(
                EntityProperty(str(key), value, source)
                for key, value in properties.items() if value is not None and value != ""
            ),
            EntityMetadata(provenance=provenance, source=source),
        ))

    def _connect(
        self,
        edges: dict[str, GraphEdge],
        source: GraphNode,
        target: GraphNode,
        relationship_type: RelationshipType,
        confidence: float,
        evidence: tuple[str, ...],
        explanation: str,
        *,
        upstream: tuple[tuple[str, float], ...] = (),
    ) -> None:
        key = f"{source.id}|{relationship_type.value}|{target.id}"
        relationship_id = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
        value = max(0.0, min(1.0, float(confidence or 0.0)))
        edges[relationship_id] = GraphEdge(Relationship(
            relationship_id,
            relationship_type,
            source.entity.entity_id,
            target.entity.entity_id,
            RelationshipWeight(value, "semantic_evidence"),
            GraphConfidence(value, (("relationship", value),), upstream),
            tuple(evidence),
            (source.id, target.id),
            explanation=explanation,
        ))

    @staticmethod
    def _slug(value: str) -> str:
        normalized = "-".join(str(value).strip().casefold().split())
        if normalized:
            return normalized
        return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:16]
