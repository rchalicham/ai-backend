import os
import sys
from dataclasses import FrozenInstanceError, replace

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.cross_document_intelligence import (
    AnomalyEngine,
    Confidence,
    ContextEntity,
    CorrelationEngine,
    Correlation,
    CrossDocumentLearningService,
    CrossDocumentConfidenceEngine,
    CrossDocumentIntelligenceEngine,
    CrossDocumentLoader,
    CrossDocumentQueryEngine,
    CrossDocumentRepository,
    CrossDocumentSerializer,
    DocumentReference,
    DocumentType,
    EnterpriseMemoryEngine,
    EnterpriseContext,
    EntityResolutionEngine,
    EvidenceEngine,
    MemorySnapshot,
    PatternEngine,
    SimilarityEngine,
    TimelineEngine,
)
from services.enterprise_graph import EnterpriseGraphBuilder, EnterpriseGraphEngine
from services.product_intelligence import (
    Brand,
    CanonicalProduct,
    Manufacturer,
    NutritionProfile,
    ProductAlias,
    ProductCategory,
    ProductDepartment,
    ProductIntelligenceEngine,
    ProductRepository,
)


def product_result(price="3.49"):
    repository = ProductRepository()
    repository.saveProducts(CanonicalProduct(
        product_id="milk",
        canonical_name="Milk",
        aliases=(ProductAlias("MLK 2%", "Milk 2 Percent"),),
        department=ProductDepartment("Grocery"),
        category=ProductCategory("Dairy"),
        brand=Brand("Great Value"),
        manufacturer=Manufacturer("Walmart"),
        nutrition=NutritionProfile(calories=120, source="approved"),
    ))
    return ProductIntelligenceEngine(repository=repository).enrich(
        ({"name": "MLK 2%", "price": price},),
        merchant_key="walmart",
        currency="USD",
    )


def graph_context(receipt_id, price="3.49"):
    return EnterpriseGraphEngine().build(
        product_result(price),
        receipt_id=receipt_id,
        merchant_key="walmart",
        receipt_context={"total": price},
    )


def document_graph(receipt_id, timestamp, price="3.49"):
    context = graph_context(receipt_id, price)
    return (
        DocumentReference(
            receipt_id,
            DocumentType.RECEIPT,
            context.graph.graph_id,
            timestamp,
            evidence_references=(f"document:{receipt_id}",),
        ),
        context.graph,
    )


def longitudinal_result():
    engine = CrossDocumentIntelligenceEngine()
    first = engine.analyze(
        graph_context("receipt-1"),
        document_id="receipt-1",
        timestamp="2026-01-01T10:00:00+00:00",
    )
    return engine.analyze(
        graph_context("receipt-2"),
        document_id="receipt-2",
        timestamp="2026-02-01T10:00:00+00:00",
        historical_memory=(first.memory,),
    )


def test_models_are_immutable_and_document_types_are_extensible():
    reference = DocumentReference("one", DocumentType.RECEIPT, "graph:one")
    with pytest.raises(FrozenInstanceError):
        reference.document_id = "changed"
    future = DocumentReference("future", "Healthcare Claim", "graph:future")
    assert future.document_type == "Healthcare Claim"


def test_entity_resolution_preserves_documents_and_canonical_identity():
    entities, similarities = EntityResolutionEngine().resolve((
        document_graph("receipt-1", "2026-01-01T00:00:00+00:00"),
        document_graph("receipt-2", "2026-02-01T00:00:00+00:00"),
    ))
    milk = next(item for item in entities if item.entity_id == "Product:milk")
    assert len(milk.document_references) == 2
    assert len(milk.graph_node_ids) == 1
    assert milk.provenance
    assert any(item.strategy == "exact" for item in similarities)


def test_similarity_supports_all_deterministic_strategies_and_embedding_adapter():
    values = SimilarityEngine(
        embedding_similarity=lambda _left, _right: 0.77,
    ).compare(
        "left", "right", "Milk 2 Percent", "Milk",
        aliases=("Milk",), historical_match=True, structural_score=0.8,
    )
    strategies = {item.strategy for item in values}
    assert {"alias", "semantic", "historical", "structural", "embedding"} <= strategies
    assert all(0 <= item.score <= 1 for item in values)


def test_correlation_and_evidence_are_traceable():
    entities, _ = EntityResolutionEngine().resolve((
        document_graph("receipt-1", "2026-01-01T00:00:00+00:00"),
        document_graph("receipt-2", "2026-02-01T00:00:00+00:00"),
    ))
    correlations = CorrelationEngine().correlate(entities)
    evidence = EvidenceEngine().build(correlations)
    assert any(item.correlation_type == "purchase_correlation" for item in correlations)
    assert any(item.correlation_type == "merchant_correlation" for item in correlations)
    assert any(item.correlation_type == "document_correlation" for item in correlations)
    assert any(item.correlation_type == "temporal_correlation" for item in correlations)
    assert all(item.document_references and item.evidence_ids and item.reason for item in correlations)
    assert all(item.supporting_documents and item.evidence_references for item in evidence)


def test_timeline_orders_events_and_references_original_evidence():
    entities, _ = EntityResolutionEngine().resolve((
        document_graph("receipt-2", "2026-02-01T00:00:00+00:00"),
        document_graph("receipt-1", "2026-01-01T00:00:00+00:00"),
    ))
    correlations = CorrelationEngine().correlate(entities)
    evidence = EvidenceEngine().build(correlations)
    timelines = TimelineEngine().build(entities, evidence)
    milk = next(item for item in timelines if item.subject_entity_id == "Product:milk")
    assert [item.document_reference.document_id for item in milk.events] == ["receipt-1", "receipt-2"]
    assert all(item.evidence_ids for item in milk.events)


def test_pattern_detection_is_historical_only_and_never_predictive():
    entities, _ = EntityResolutionEngine().resolve((
        document_graph("receipt-1", "2026-01-01T00:00:00+00:00"),
        document_graph("receipt-2", "2026-02-01T00:00:00+00:00"),
        document_graph("receipt-3", "2026-03-04T00:00:00+00:00"),
    ))
    correlations = CorrelationEngine().correlate(entities)
    evidence = EvidenceEngine().build(correlations)
    timelines = TimelineEngine().build(entities, evidence)
    patterns = PatternEngine().detect(entities, timelines, evidence)
    assert any(item.pattern_type == "recurring_purchase" for item in patterns)
    assert any(item.pattern_type == "merchant_loyalty" for item in patterns)
    assert any(item.pattern_type == "subscription_pattern" for item in patterns)
    assert all(item.predictive is False for item in patterns)


def test_anomaly_detection_reports_duplicates_prices_and_never_corrects():
    documents = (
        document_graph("receipt-1", "2026-01-01T00:00:00+00:00", "3.49"),
        document_graph("receipt-2", "2026-02-01T00:00:00+00:00", "9.99"),
    )
    entities, _ = EntityResolutionEngine().resolve(documents)
    anomalies = AnomalyEngine().detect(documents, entities, ())
    types = {item.anomaly_type for item in anomalies}
    assert "duplicate_receipt" in types
    assert "price_anomaly" in types
    assert all(item.automatic_correction is False for item in anomalies)


def test_confidence_aggregates_without_overwriting_upstream_values():
    confidence = CrossDocumentConfidenceEngine().aggregate(
        graph=0.9,
        entity=1,
        evidence=0.8,
        temporal=0.7,
        relationship=0.6,
        upstream_values=(("graph", 0.9),),
    )
    assert confidence.normalized == pytest.approx(0.825)
    assert confidence.upstream_values == (("graph", 0.9),)


def test_intelligence_engine_builds_longitudinal_context_and_deterministic_memory():
    result = longitudinal_result()
    assert result.context.related_documents[0].document_id == "receipt-1"
    assert any(len(item.document_references) == 2 for item in result.context.entities)
    assert result.context.correlations
    assert result.context.timelines
    assert result.context.evidence
    assert result.context.patterns
    assert result.context.explanations
    assert result.memory.deterministic is True
    assert result.memory.llm_memory is False
    assert result.diagnostics.affects_extraction is False
    assert result.diagnostics.documents_modified is False
    assert result.diagnostics.graph_modified is False
    assert result.diagnostics.machine_learning_used is False
    assert result.diagnostics.memory_write_performed is False


def test_memory_engine_merges_without_modifying_history():
    first = longitudinal_result().memory
    original = first
    merged = EnterpriseMemoryEngine().merge_entities(first.entities, (first,))
    assert merged
    assert first == original


def test_query_engine_exposes_storage_neutral_context_queries():
    result = longitudinal_result()
    queries = CrossDocumentQueryEngine()
    assert len(queries.find_all_purchases_of_product(result, "milk")) == 2
    assert len(queries.find_all_receipts_for_merchant(result, "walmart")) == 2
    assert queries.find_purchase_history(result, "milk").events
    assert queries.find_all_documents_referencing_entity(result, "milk")
    assert queries.find_related_documents(result, "receipt-2")
    assert queries.find_evidence(result, "Product:milk")
    assert queries.find_patterns(result)
    assert isinstance(queries.find_anomalies(result), tuple)


def test_repository_version_archive_compare_and_storage_contract():
    repository = CrossDocumentRepository()
    first = repository.save(longitudinal_result().memory)
    extra = DocumentReference("receipt-3", DocumentType.RECEIPT, "graph:3")
    second = repository.version(
        replace(first, documents=(*first.documents, extra)), expected_version=1,
    )
    comparison = repository.compare(first.memory_id, 1, 2)
    assert comparison.added_documents == ("receipt-3",)
    assert second.version.entity_version == 2
    assert repository.archive(first.memory_id, 2).version.status == "archived"
    assert repository.load(first.memory_id).version.entity_version == 1


def test_repository_rejects_duplicate_save_and_version_conflict():
    repository = CrossDocumentRepository()
    memory = repository.save(longitudinal_result().memory)
    with pytest.raises(ValueError, match="already_exists"):
        repository.save(memory)
    with pytest.raises(ValueError, match="version_conflict"):
        repository.version(memory, expected_version=9)


def test_runtime_reads_repository_memory_without_writing_it():
    repository = CrossDocumentRepository()
    first = CrossDocumentIntelligenceEngine().analyze(
        graph_context("receipt-1"),
        document_id="receipt-1",
        timestamp="2026-01-01T00:00:00+00:00",
    )
    repository.save(first.memory)
    before = repository.list_memory()
    second = CrossDocumentIntelligenceEngine(repository=repository).analyze(
        graph_context("receipt-2"),
        document_id="receipt-2",
        timestamp="2026-02-01T00:00:00+00:00",
    )
    assert second.context.related_documents[0].document_id == "receipt-1"
    assert repository.list_memory() == before
    assert second.diagnostics.memory_write_performed is False


def test_learning_suggestions_are_approval_only_and_do_not_change_context():
    reference = DocumentReference("one", DocumentType.RECEIPT, "graph:one")
    confidence = Confidence(0.4, entity=0.4)
    correlation = Correlation(
        "low", "entity_correlation", ("Product:milk",), (reference,),
        ("evidence:low",), "Low confidence supported correlation.", confidence,
    )
    context = EnterpriseContext(
        "context:one", reference, correlations=(correlation,),
    )
    before = context
    suggestions = CrossDocumentLearningService().suggest(context)
    assert suggestions[0].requires_approval is True
    assert context == before


def test_serialization_and_loader_round_trip_memory():
    memory = longitudinal_result().memory
    serializer = CrossDocumentSerializer()
    loaded = CrossDocumentLoader().memory_from_json(serializer.to_json(memory))
    assert loaded.memory_id == memory.memory_id
    assert loaded.documents == memory.documents
    assert {item.entity_id for item in loaded.entities} == {
        item.entity_id for item in memory.entities
    }
    payload = serializer.to_dict(longitudinal_result())
    assert payload["schema_version"] == "cross-document-intelligence-v1"
    assert payload["diagnostics"]["valid"] is True


def test_explanations_cover_linking_evidence_confidence_timeline_and_patterns():
    explanations = longitudinal_result().context.explanations
    assert explanations
    assert all("Documents were linked because" in item.summary for item in explanations)
    assert all(item.evidence_ids for item in explanations)
    assert all(item.confidence_contributions for item in explanations)
    assert all(item.timeline_reasoning and item.pattern_reasoning and item.relationship_reasoning for item in explanations)


def test_safe_analysis_degrades_without_document_or_graph_mutation():
    class BrokenResolution(EntityResolutionEngine):
        def resolve(self, documents):
            raise RuntimeError("broken")

    graph = graph_context("receipt-1")
    before = CrossDocumentSerializer().to_dict(graph)
    result = CrossDocumentIntelligenceEngine(
        entity_resolution=BrokenResolution(),
    ).safe_analyze(graph, document_id="receipt-1")
    assert result.diagnostics.errors[0].code == "cross_document_sidecar_failed"
    assert result.diagnostics.affects_extraction is False
    assert result.diagnostics.documents_modified is False
    assert result.diagnostics.graph_modified is False
    assert CrossDocumentSerializer().to_dict(graph) == before
