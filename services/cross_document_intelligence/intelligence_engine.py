from __future__ import annotations

from typing import Any

from services.enterprise_graph import EnterpriseGraphContext

from .anomaly_engine import AnomalyEngine
from .correlation_engine import CorrelationEngine
from .diagnostics import CrossDocumentDiagnostics
from .document_linker import DocumentLinker
from .entity_resolution import EntityResolutionEngine
from .evidence_engine import EvidenceEngine
from .explanation_engine import CrossDocumentExplanationEngine
from .learning import CrossDocumentLearningService
from .memory_engine import EnterpriseMemoryEngine
from .models import (
    DocumentReference,
    DocumentType,
    EnterpriseContext,
    IntelligenceResult,
    MemorySnapshot,
    utc_now,
)
from .pattern_engine import PatternEngine
from .repository import CrossDocumentRepository, CrossDocumentRepositoryProtocol
from .timeline_engine import TimelineEngine


class CrossDocumentIntelligenceEngine:
    """Creates longitudinal semantic context without modifying documents or graphs."""

    def __init__(
        self,
        repository: CrossDocumentRepositoryProtocol | None = None,
        entity_resolution: EntityResolutionEngine | None = None,
        document_linker: DocumentLinker | None = None,
        correlation_engine: CorrelationEngine | None = None,
        evidence_engine: EvidenceEngine | None = None,
        timeline_engine: TimelineEngine | None = None,
        pattern_engine: PatternEngine | None = None,
        anomaly_engine: AnomalyEngine | None = None,
        memory_engine: EnterpriseMemoryEngine | None = None,
        explanation_engine: CrossDocumentExplanationEngine | None = None,
        diagnostics: CrossDocumentDiagnostics | None = None,
        learning: CrossDocumentLearningService | None = None,
    ) -> None:
        self.repository = repository or CrossDocumentRepository()
        self.entity_resolution = entity_resolution or EntityResolutionEngine()
        self.document_linker = document_linker or DocumentLinker()
        self.correlation_engine = correlation_engine or CorrelationEngine()
        self.evidence_engine = evidence_engine or EvidenceEngine()
        self.timeline_engine = timeline_engine or TimelineEngine()
        self.pattern_engine = pattern_engine or PatternEngine()
        self.anomaly_engine = anomaly_engine or AnomalyEngine()
        self.memory_engine = memory_engine or EnterpriseMemoryEngine()
        self.explanation_engine = explanation_engine or CrossDocumentExplanationEngine()
        self.diagnostics_engine = diagnostics or CrossDocumentDiagnostics()
        self.learning = learning or CrossDocumentLearningService()

    def analyze(
        self,
        graph_context: EnterpriseGraphContext,
        *,
        document_id: str,
        document_type: DocumentType | str = DocumentType.RECEIPT,
        timestamp: str = "",
        historical_memory: tuple[MemorySnapshot, ...] | None = None,
    ) -> IntelligenceResult:
        graph = graph_context.graph
        current_document = DocumentReference(
            document_id,
            document_type,
            graph.graph_id,
            timestamp or graph.version.created_at or utc_now(),
            graph.version.schema_version,
            (f"graph:{graph.graph_id}", f"document:{document_id}"),
        )
        histories = (
            tuple(historical_memory)
            if historical_memory is not None
            else self._repository_memory()
        )
        current_documents = ((current_document, graph),)
        current_entities, similarities = self.entity_resolution.resolve(current_documents)
        entities = self.memory_engine.merge_entities(current_entities, histories)
        current_relationships = self.memory_engine.relationships(current_documents, entities)
        relationships = self._merge_relationships(current_relationships, histories)
        related_documents = self.document_linker.link(current_document, entities)
        correlations = self.correlation_engine.correlate(entities, relationships)
        evidence = self.evidence_engine.build(correlations)
        timelines = self.timeline_engine.build(entities, evidence)
        patterns = self.pattern_engine.detect(entities, timelines, evidence)
        anomalies = self.anomaly_engine.detect(current_documents, entities, evidence)
        explanations = self.explanation_engine.explain(correlations, timelines, patterns)
        context = EnterpriseContext(
            f"context:{document_id}",
            current_document,
            related_documents,
            entities,
            relationships,
            correlations,
            timelines,
            evidence,
            similarities,
            patterns,
            anomalies,
            explanations,
        )
        all_documents = tuple(dict.fromkeys((
            current_document,
            *related_documents,
            *(document for history in histories for document in history.documents),
        )))
        memory = self.memory_engine.snapshot(
            f"enterprise-memory:{document_id}",
            all_documents,
            entities,
            relationships,
            timelines,
            evidence,
            patterns,
            correlations,
        )
        return IntelligenceResult(
            context,
            memory,
            self.diagnostics_engine.create(context),
            self.learning.suggest(context),
        )

    def safe_analyze(
        self,
        graph_context: EnterpriseGraphContext | None,
        **kwargs: Any,
    ) -> IntelligenceResult | None:
        if graph_context is None:
            return None
        try:
            return self.analyze(graph_context, **kwargs)
        except Exception as exc:
            document_id = str(kwargs.get("document_id") or "unknown")
            reference = DocumentReference(
                document_id, DocumentType.UNKNOWN, graph_context.graph.graph_id,
            )
            context = EnterpriseContext(f"context:{document_id}", reference)
            return IntelligenceResult(
                context,
                MemorySnapshot(f"enterprise-memory:{document_id}"),
                self.diagnostics_engine.failed(exc),
            )

    def _repository_memory(self) -> tuple[MemorySnapshot, ...]:
        list_method = getattr(self.repository, "list_memory", None)
        return tuple(list_method()) if callable(list_method) else ()

    @staticmethod
    def _merge_relationships(current, histories):
        values = {}
        for item in (
            *(value for history in histories for value in history.relationships),
            *current,
        ):
            previous = values.get(item.relationship_id)
            if previous is None:
                values[item.relationship_id] = item
                continue
            values[item.relationship_id] = type(item)(
                item.relationship_id,
                item.relationship_type,
                item.source_entity_id,
                item.target_entity_id,
                tuple(dict.fromkeys((*previous.document_references, *item.document_references))),
                tuple(dict.fromkeys((*previous.evidence_ids, *item.evidence_ids))),
                max(
                    (previous.confidence, item.confidence),
                    key=lambda value: value.normalized,
                ),
                tuple(dict.fromkeys((*previous.provenance, *item.provenance))),
                item.explanation or previous.explanation,
            )
        return tuple(values[key] for key in sorted(values))
