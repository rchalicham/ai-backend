from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime

from services.enterprise_graph import GraphSubgraph

from .models import Anomaly, Confidence, ContextEntity, DocumentReference, EvidenceRecord


class AnomalyEngine:
    """Produces diagnostics only; no anomaly can correct a source artifact."""

    def detect(
        self,
        documents: tuple[tuple[DocumentReference, GraphSubgraph], ...],
        entities: tuple[ContextEntity, ...],
        evidence: tuple[EvidenceRecord, ...],
    ) -> tuple[Anomaly, ...]:
        values: list[Anomaly] = []
        signatures: dict[tuple[str, ...], list[DocumentReference]] = defaultdict(list)
        prices_by_product: dict[str, list[tuple[float, DocumentReference]]] = defaultdict(list)
        for reference, graph in documents:
            signature = tuple(sorted(
                node.id for node in graph.nodes
                if self._type(node.entity.entity_type) in {"Product", "Merchant"}
            ))
            if signature:
                signatures[signature].append(reference)
            if not self._valid_timestamp(reference.timestamp):
                values.append(self._anomaly(
                    "timeline_inconsistency", (reference,), (),
                    f"Document {reference.document_id} has an invalid timeline timestamp.", 1.0,
                ))
            product_ids = {
                str(edge.relationship.source_id)
                for edge in graph.edges
                if self._type(edge.relationship.relationship_type) == "HAS_CATEGORY"
            }
            for node in graph.nodes:
                if self._type(node.entity.entity_type) == "Product" and node.id not in product_ids:
                    values.append(self._anomaly(
                        "missing_relationship", (reference,), (node.id,),
                        f"Product {node.entity.label} has no supported category relationship.", 0.8,
                    ))
            nodes_by_id = {node.id: node for node in graph.nodes}
            line_links: dict[str, list[str]] = defaultdict(list)
            for edge in graph.edges:
                if self._type(edge.relationship.relationship_type) == "RELATED_TO":
                    line_links[str(edge.relationship.source_id)].append(
                        str(edge.relationship.target_id),
                    )
            for targets in line_links.values():
                products = [
                    nodes_by_id[target] for target in targets
                    if target in nodes_by_id and self._type(nodes_by_id[target].entity.entity_type) == "Product"
                ]
                prices = [
                    nodes_by_id[target] for target in targets
                    if target in nodes_by_id and self._type(nodes_by_id[target].entity.entity_type) == "Price"
                ]
                for product in products:
                    for price in prices:
                        try:
                            prices_by_product[product.id].append((float(price.entity.label), reference))
                        except (TypeError, ValueError):
                            continue
        for references in signatures.values():
            if len(references) > 1:
                document_type = self._type(references[0].document_type).casefold()
                anomaly_type = "duplicate_invoice" if "invoice" in document_type else "duplicate_receipt"
                values.append(self._anomaly(
                    anomaly_type, tuple(references), (),
                    "Independent documents contain the same canonical Product and Merchant signature.",
                    0.9,
                ))
        for entity in entities:
            if len(set(entity.aliases)) > 1 and entity.confidence.entity < 0.8:
                values.append(self._anomaly(
                    "conflicting_entities",
                    entity.document_references,
                    (entity.entity_id,),
                    "Resolved entity retains conflicting low-confidence labels.",
                    1.0 - entity.confidence.entity,
                ))
        for product_id, prices in prices_by_product.items():
            amounts = [amount for amount, _ in prices]
            if len(amounts) > 1 and min(amounts) > 0 and max(amounts) / min(amounts) >= 1.5:
                values.append(self._anomaly(
                    "price_anomaly",
                    tuple(dict.fromkeys(reference for _, reference in prices)),
                    (product_id,),
                    f"Observed price range {min(amounts):.2f}–{max(amounts):.2f} exceeds deterministic variance threshold.",
                    0.85,
                ))
        return tuple(values)

    def _anomaly(
        self,
        anomaly_type: str,
        documents: tuple[DocumentReference, ...],
        entity_ids: tuple[str, ...],
        reason: str,
        confidence: float,
    ) -> Anomaly:
        key = "|".join((anomaly_type, *(item.document_id for item in documents), *entity_ids))
        return Anomaly(
            hashlib.sha256(key.encode("utf-8")).hexdigest()[:24],
            anomaly_type,
            "warning",
            documents,
            entity_ids,
            (),
            reason,
            Confidence(confidence, evidence=confidence),
            False,
        )

    @staticmethod
    def _valid_timestamp(value: str) -> bool:
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            return True
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _type(value) -> str:
        return value.value if hasattr(value, "value") else str(value)
