from dataclasses import FrozenInstanceError
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.intelligence_snapshot import (
    InMemorySnapshotRepository, ReceiptIntelligenceSnapshotEngine,
    SnapshotArchiver, SnapshotBuilder, SnapshotComparisonEngine,
    SnapshotLoader, SnapshotProjectionEngine, SnapshotReference,
    SnapshotSerializer, SnapshotValidator,
)


def orchestration(merchant="Luther Hopkins Honda", confidence=0.91, family="payment_slip"):
    return {
        "receiptAgent": {"schemaVersion": "receipt-agent-v2", "selectedAttempt": 1},
        "receiptDocument": {"id": "dom-1", "nodes": [{"id": "large-node"}]},
        "geometry": {"id": "geometry-1", "contours": [1, 2, 3]},
        "documentFamilyContext": {"activation": {"family": family, "confidence": confidence}, "profile": {"profile_id": "payment-v1"}},
        "receiptGrammar": {"schema_version": "grammar-v3", "family": family},
        "receiptConstraintResult": {"schema_version": "constraints-v2", "valid": True},
        "productIntelligence": {"schema_version": "products-v1", "products": []},
        "enterpriseKnowledgeGraph": {"graph_id": "graph-1", "nodes": [1, 2]},
        "crossDocumentIntelligence": {"schema_version": "cross-v1", "matches": []},
        "enterpriseLearning": {"id": "learning-1", "events": [1, 2]},
        "enterpriseReasoning": {"schema_version": "reasoning-v4", "merchant": merchant},
        "businessProjection": {
            "metadata": {"mode": "hybrid"},
            "overall_confidence": {"display": confidence},
            "fields": [{"key": "merchant", "displayed_value": merchant}],
        },
    }


def engine():
    return ReceiptIntelligenceSnapshotEngine(InMemorySnapshotRepository())


def test_snapshot_creation_is_immutable_and_parser_isolation_is_explicit():
    snapshot = engine().capture(orchestration(), receipt_id="receipt-1")
    assert snapshot.header.version.number == 1
    assert snapshot.metadata.document_family == "payment_slip"
    assert snapshot.diagnostics.parser_modified is False
    assert snapshot.diagnostics.receipt_modified is False
    with pytest.raises(FrozenInstanceError):
        snapshot.metadata.document_family = "retail_receipt"


def test_large_artifacts_are_references_and_not_embedded_in_context():
    snapshot = SnapshotBuilder().build(orchestration(), receipt_id="receipt-1")
    kinds = {item.artifact_type for item in snapshot.references}
    assert {"receipt_dom", "geometry", "enterprise_graph", "enterprise_learning"} <= kinds
    serialized = SnapshotSerializer().to_dict(snapshot)
    assert "receipt_document" not in serialized["context"]
    assert "enterprise_knowledge_graph" not in serialized["context"]
    assert snapshot.diagnostics.large_artifacts_embedded is False


def test_every_processing_run_appends_a_version_without_overwrite():
    service = engine()
    first = service.capture(orchestration(), receipt_id="receipt-1")
    second = service.capture(orchestration(confidence=0.95), receipt_id="receipt-1")
    assert (first.header.version.number, second.header.version.number) == (1, 2)
    assert second.header.version.supersedes_snapshot_id == first.header.snapshot_id
    assert service.latest("receipt-1") == second
    assert len(service.history("receipt-1").snapshots) == 2


def test_repository_rejects_duplicate_snapshot_identity():
    repository = InMemorySnapshotRepository()
    snapshot = SnapshotBuilder().build(orchestration(), receipt_id="receipt-1")
    repository.save(snapshot)
    with pytest.raises(ValueError, match="immutable"):
        repository.save(snapshot)


def test_snapshot_round_trip_loading_preserves_metadata_and_references():
    snapshot = engine().capture(orchestration(), receipt_id="receipt-1")
    loaded = SnapshotLoader().from_dict(SnapshotSerializer().to_dict(snapshot))
    assert loaded.header == snapshot.header
    assert loaded.metadata == snapshot.metadata
    assert loaded.references == snapshot.references


def test_comparison_reports_projection_confidence_reasoning_and_version_changes():
    service = engine()
    first = service.capture(orchestration(), receipt_id="receipt-1")
    second = service.capture(orchestration("Hopkins Honda", 0.98), receipt_id="receipt-1")
    comparison = SnapshotComparisonEngine().compare(first, second)
    assert comparison.projection_changes
    assert comparison.confidence_changes
    assert comparison.reasoning_changes
    assert comparison.version_changes


def test_projection_enables_only_available_snapshot_tabs_and_reference_tabs():
    snapshot = engine().capture(orchestration(), receipt_id="receipt-1")
    projection = SnapshotProjectionEngine().project(snapshot)
    assert "Pipeline" in projection.tabs
    assert "Document Family" in projection.tabs
    assert "Business Projection" in projection.tabs
    assert "Enterprise Knowledge Graph" in projection.tabs
    assert "Enterprise Learning" in projection.tabs


def test_retention_can_archive_or_delete_old_versions():
    service = engine()
    snapshots = [service.capture(orchestration(confidence=0.8 + index / 100), receipt_id="receipt-1") for index in range(4)]
    SnapshotArchiver().apply_retention(service.repository, "receipt-1", keep_last=2)
    assert [item.header.version.status for item in service.repository.history("receipt-1")] == ["archived", "archived", "active", "active"]
    SnapshotArchiver().apply_retention(service.repository, "receipt-1", keep_last=1, archive=False, delete=True)
    assert service.repository.history("receipt-1") == (snapshots[-1],)


def test_validator_guards_snapshot_contract():
    snapshot = SnapshotBuilder().build(orchestration(), receipt_id="receipt-1")
    assert SnapshotValidator().validate(snapshot) == ()


def test_reference_metadata_is_deeply_immutable():
    reference = SnapshotReference("geometry", "g-1", metadata={"pages": [1, 2]})
    assert isinstance(reference.metadata, tuple)
