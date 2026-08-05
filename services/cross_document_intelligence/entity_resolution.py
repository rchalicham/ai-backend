from __future__ import annotations

from collections import defaultdict

from services.enterprise_graph import GraphSubgraph

from .confidence_engine import CrossDocumentConfidenceEngine
from .models import ContextEntity, DocumentReference, Similarity
from .similarity_engine import SimilarityEngine


class EntityResolutionEngine:
    """Resolves only evidence-supported canonical identities; source graphs remain unchanged."""

    def __init__(
        self,
        similarity: SimilarityEngine | None = None,
        confidence: CrossDocumentConfidenceEngine | None = None,
    ) -> None:
        self.similarity = similarity or SimilarityEngine()
        self.confidence = confidence or CrossDocumentConfidenceEngine()

    def resolve(
        self,
        documents: tuple[tuple[DocumentReference, GraphSubgraph], ...],
    ) -> tuple[tuple[ContextEntity, ...], tuple[Similarity, ...]]:
        groups: dict[tuple[str, str], list[tuple[DocumentReference, object]]] = defaultdict(list)
        similarities: list[Similarity] = []
        label_to_key: dict[tuple[str, str], tuple[str, str]] = {}
        for reference, graph in documents:
            for node in graph.nodes:
                entity_type = self._value(node.entity.entity_type)
                exact = (entity_type, node.entity.entity_id.value)
                label_key = (entity_type, self._normalize(node.entity.label))
                key = exact if exact in groups else label_to_key.get(label_key, exact)
                label_to_key.setdefault(label_key, key)
                groups[key].append((reference, node))
        entities = []
        for key in sorted(groups):
            values = groups[key]
            reference_nodes = tuple(values)
            labels = tuple(dict.fromkeys(node.entity.label for _, node in reference_nodes))
            confidence = self.confidence.aggregate(
                graph=1.0,
                entity=1.0 if len({node.entity.entity_id.value for _, node in values}) == 1 else 0.9,
                evidence=1.0 if all(node.entity.metadata.provenance for _, node in values) else 0.7,
                temporal=1.0 if len(values) > 1 else 0.5,
                relationship=0.8,
                upstream_values=tuple(
                    (f"entity:{index}", 1.0)
                    for index, _ in enumerate(reference_nodes)
                ),
            )
            entity_id = f"{key[0]}:{key[1]}"
            entities.append(ContextEntity(
                entity_id,
                key[0],
                labels[0],
                labels[1:],
                tuple(dict.fromkeys(reference for reference, _ in values)),
                tuple(dict.fromkeys(node.id for _, node in values)),
                confidence,
                tuple(dict.fromkeys(
                    item for _, node in values for item in node.entity.metadata.provenance
                )),
            ))
            for index, (_, left) in enumerate(values):
                for _, right in values[index + 1:]:
                    similarities.extend(self.similarity.compare(
                        left.id, right.id, left.entity.label, right.entity.label,
                        historical_match=left.entity.entity_id == right.entity.entity_id,
                    ))
        return tuple(entities), tuple(similarities)

    @staticmethod
    def _value(value) -> str:
        return value.value if hasattr(value, "value") else str(value)

    @staticmethod
    def _normalize(value: str) -> str:
        return "-".join(str(value).casefold().split())
