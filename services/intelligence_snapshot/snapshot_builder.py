from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import uuid4

from .models import (
    ReceiptIntelligenceSnapshot, SnapshotConfidence, SnapshotContext,
    SnapshotDiagnostics, SnapshotExplanation, SnapshotHeader, SnapshotMetadata,
    SnapshotReference, SnapshotSummary, SnapshotVersion, utc_now,
)


def _nested(value: dict[str, Any] | None, *path: str, default: Any = "") -> Any:
    current: Any = value or {}
    for key in path:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return default if current is None else current


def _artifact_reference(kind: str, payload: Any, receipt_id: str) -> SnapshotReference | None:
    if not payload:
        return None
    identity = ""
    if isinstance(payload, dict):
        identity = str(payload.get("id") or payload.get("graph_id") or payload.get("context_id") or "")
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    return SnapshotReference(kind, identity or f"{receipt_id}:{kind}", loader=f"{kind}_repository", checksum=digest)


class SnapshotBuilder:
    LARGE_ARTIFACTS = {
        "geometry": "geometry",
        "receiptDocument": "receipt_dom",
        "enterpriseKnowledgeGraph": "enterprise_graph",
        "enterpriseLearning": "enterprise_learning",
    }

    def build(
        self,
        orchestration: dict[str, Any],
        *,
        receipt_id: str,
        version: int = 1,
        supersedes_snapshot_id: str = "",
        tenant_id: str = "default",
        execution_time_ms: float = 0.0,
    ) -> ReceiptIntelligenceSnapshot:
        snapshot_id = f"snapshot:{receipt_id}:{version}:{uuid4().hex[:12]}"
        family = str(
            _nested(orchestration, "documentFamilyContext", "activation", "family", default="")
            or _nested(orchestration, "documentFamilyContext", "family", default="unknown")
        )
        projection = orchestration.get("businessProjection") or {}
        projection_mode = str(_nested(projection, "metadata", "mode", default="hybrid"))
        confidence = float(
            _nested(projection, "overall_confidence", "display", default=0.0)
            or _nested(orchestration, "documentFamilyContext", "activation", "confidence", default=0.0)
            or 0.0
        )
        references = tuple(filter(None, (
            _artifact_reference(kind, orchestration.get(key), receipt_id)
            for key, kind in self.LARGE_ARTIFACTS.items()
        )))
        context = SnapshotContext(
            pipeline=orchestration.get("receiptAgent") or {},
            document_family=orchestration.get("documentFamilyContext") or {},
            grammar=orchestration.get("receiptGrammar") or {},
            constraints=orchestration.get("receiptConstraintResult") or {},
            product_intelligence=orchestration.get("productIntelligence") or {},
            cross_document_intelligence=orchestration.get("crossDocumentIntelligence") or {},
            enterprise_reasoning=orchestration.get("enterpriseReasoning") or {},
            business_projection=projection,
            document_review=orchestration.get("documentReview") or {},
        )
        metadata = SnapshotMetadata(
            pipeline_version=str(_nested(orchestration, "receiptAgent", "schemaVersion", default="enterprise-receipt-pipeline-v1")),
            grammar_version=str(_nested(orchestration, "receiptGrammar", "schema_version", default="")),
            constraint_version=str(_nested(orchestration, "receiptConstraintResult", "schema_version", default="")),
            learning_version=str(_nested(orchestration, "enterpriseLearning", "schema_version", default="")),
            reasoning_version=str(_nested(orchestration, "enterpriseReasoning", "schema_version", default="")),
            document_family=family,
            projection_mode=projection_mode,
            processing_profile=str(_nested(orchestration, "documentFamilyContext", "profile", "profile_id", default="default")),
            execution_time_ms=execution_time_ms,
            tenant_id=tenant_id,
        )
        version_value = SnapshotVersion(version, supersedes_snapshot_id=supersedes_snapshot_id)
        header = SnapshotHeader(snapshot_id, receipt_id, version_value)
        component_confidence = tuple((name, float(value)) for name, value in (
            ("document_family", _nested(orchestration, "documentFamilyContext", "activation", "confidence", default=0.0)),
            ("projection", confidence),
        ) if isinstance(value, (int, float)))
        snapshot_confidence = SnapshotConfidence(confidence, component_confidence)
        summary = SnapshotSummary(snapshot_id, receipt_id, version, header.created_at, family, confidence, projection_mode)
        warnings = tuple(str(item) for item in _nested(orchestration, "receiptAgent", "warnings", default=[]) or [])
        return ReceiptIntelligenceSnapshot(
            header, metadata, context, references, snapshot_confidence,
            (SnapshotExplanation("Immutable enterprise intelligence processing snapshot"),),
            SnapshotDiagnostics(warnings, orchestration.get("receiptAgent") or {}),
            summary,
        )
