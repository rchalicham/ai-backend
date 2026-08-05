import os
import sys
from dataclasses import FrozenInstanceError, replace

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.cross_document_intelligence.models import (
    Confidence,
    Diagnostics,
    DocumentReference,
    EnterpriseContext,
    EvidenceRecord,
    IntelligenceResult,
    MemorySnapshot,
    Pattern,
)
from services.enterprise_learning import (
    ConfidenceCalibrationEngine,
    EnterpriseFeedbackEngine,
    EnterpriseLearningEngine,
    EnterpriseLearningLoader,
    EnterpriseLearningRepository,
    EnterpriseLearningSerializer,
    LearningApprovalEngine,
    LearningAuditEngine,
)


def semantic_context():
    first = DocumentReference("receipt-1", "Receipt", "graph-1")
    second = DocumentReference("receipt-2", "Receipt", "graph-2")
    confidence = Confidence(.95, evidence=.95, entity=.9)
    evidence = EvidenceRecord(
        "evidence-1", (first, second), ("graph:1",), ("product:milk",),
        "confirmed across documents", confidence,
    )
    pattern = Pattern(
        "pattern-1", "recurring_purchase", ("product:milk",), (first, second),
        ("evidence-1",), 2, "Milk recurred", confidence,
    )
    context = EnterpriseContext(
        "context-1", first, (second,), evidence=(evidence,), patterns=(pattern,),
    )
    return IntelligenceResult(context, MemorySnapshot("memory-1"), Diagnostics())


def test_learning_generates_only_pending_governed_semantic_proposals():
    source = semantic_context()
    original_context = source.context
    result = EnterpriseLearningEngine().evaluate(source)
    assert result.diagnostics.valid
    assert result.snapshot.proposals
    assert all(item.status.value == "pending" for item in result.snapshot.proposals)
    assert result.snapshot.approvals == ()
    assert result.snapshot.decisions == ()
    assert result.diagnostics.production_knowledge_modified is False
    assert result.diagnostics.automatic_approval_performed is False
    assert result.diagnostics.raw_ocr_consumed is False
    assert source.context is original_context
    assert source.context.evidence[0].reason == "confirmed across documents"


def test_unverified_low_confidence_evidence_produces_no_proposal():
    source = semantic_context()
    weak = replace(
        source.context.evidence[0],
        supporting_documents=(source.context.current_document,),
        confidence=Confidence(.4, evidence=.4),
    )
    result = EnterpriseLearningEngine().evaluate(
        replace(source, context=replace(source.context, evidence=(weak,), patterns=())),
    )
    assert result.snapshot.proposals == ()
    assert result.snapshot.evidence[0].verified is False


def test_verified_feedback_has_provenance_and_requires_explicit_approval():
    feedback = EnterpriseFeedbackEngine().create(
        actor_id="architect-1", actor_role="administrator",
        feedback_type="product_alias", subject_id="product:milk",
        proposed_value={"alias": "MLK 2%"}, reason="verified correction",
        provenance=("review:42",), verified=True,
    )
    result = EnterpriseLearningEngine().evaluate(semantic_context(), feedback=(feedback,))
    proposal = next(
        item for item in result.snapshot.proposals
        if item.candidate.candidate_type == "new_product_alias"
    )
    updated, approval, decision = LearningApprovalEngine().approve(
        proposal, approver_id="chief-architect", approver_role="administrator",
        reason="evidence reviewed",
    )
    assert updated.status.value == approval.status.value == decision.status.value == "approved"
    audit = LearningAuditEngine().decision_recorded(updated, approval)
    assert audit.actor_id == "chief-architect"
    assert audit.evidence_ids


def test_models_are_immutable_and_confidence_keeps_history():
    result = EnterpriseLearningEngine().evaluate(semantic_context())
    with pytest.raises(FrozenInstanceError):
        result.snapshot.snapshot_id = "changed"
    confidence = ConfidenceCalibrationEngine().calibrate(
        .6, repeated_confirmations=1, historical_consistency=.9,
        evidence_quality=.9, cross_document_agreement=.9,
        history=(("upstream", .6),),
    )
    assert confidence.current == .6
    assert confidence.history == (("upstream", .6),)
    assert confidence.proposed > confidence.current


def test_repository_serialization_versioning_and_comparison():
    result = EnterpriseLearningEngine().evaluate(semantic_context())
    repository = EnterpriseLearningRepository()
    first = repository.save(result.snapshot)
    second = repository.version(
        replace(first, proposals=()), expected_version=1,
    )
    comparison = repository.compare(first.snapshot_id, 1, 2)
    assert second.version.entity_version == 2
    assert comparison.removed_proposals
    payload = EnterpriseLearningSerializer().to_json(first)
    restored = EnterpriseLearningLoader().snapshot_from_json(payload)
    assert restored.snapshot_id == first.snapshot_id
    assert restored.proposals == first.proposals
    assert repository.archive(first.snapshot_id, 2).version.status == "archived"
