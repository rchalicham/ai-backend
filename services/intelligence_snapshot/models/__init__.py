from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return tuple((str(key), freeze(item)) for key, item in sorted(value.items(), key=lambda item: str(item[0])))
    if isinstance(value, (list, tuple)):
        return tuple(freeze(item) for item in value)
    if isinstance(value, set):
        return tuple(sorted((freeze(item) for item in value), key=str))
    return value


def thaw(value: Any) -> Any:
    if isinstance(value, tuple):
        if all(isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str) for item in value):
            return {key: thaw(item) for key, item in value}
        return [thaw(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class SnapshotVersion:
    number: int
    schema_version: str = "receipt-intelligence-snapshot-v1"
    status: str = "active"
    supersedes_snapshot_id: str = ""


@dataclass(frozen=True, slots=True)
class SnapshotReference:
    artifact_type: str
    artifact_id: str
    version: str = ""
    loader: str = ""
    checksum: str = ""
    metadata: Any = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", freeze(self.metadata))


@dataclass(frozen=True, slots=True)
class SnapshotConfidence:
    overall: float = 0.0
    components: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True, slots=True)
class SnapshotExplanation:
    summary: str = ""
    evidence_ids: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SnapshotDiagnostics:
    warnings: tuple[str, ...] = ()
    execution_trace: Any = ()
    parser_modified: bool = False
    receipt_modified: bool = False
    large_artifacts_embedded: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "execution_trace", freeze(self.execution_trace))


@dataclass(frozen=True, slots=True)
class SnapshotMetadata:
    processing_time: str = field(default_factory=utc_now)
    pipeline_version: str = "enterprise-receipt-pipeline-v1"
    grammar_version: str = ""
    constraint_version: str = ""
    learning_version: str = ""
    reasoning_version: str = ""
    document_family: str = "unknown"
    projection_mode: str = "hybrid"
    processing_profile: str = "default"
    execution_time_ms: float = 0.0
    model_versions: tuple[tuple[str, str], ...] = ()
    tenant_id: str = "default"


@dataclass(frozen=True, slots=True)
class SnapshotHeader:
    snapshot_id: str
    receipt_id: str
    version: SnapshotVersion
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class SnapshotContext:
    pipeline: Any = ()
    document_family: Any = ()
    grammar: Any = ()
    constraints: Any = ()
    product_intelligence: Any = ()
    cross_document_intelligence: Any = ()
    enterprise_reasoning: Any = ()
    business_projection: Any = ()
    document_review: Any = ()

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, freeze(getattr(self, name)))


@dataclass(frozen=True, slots=True)
class SnapshotSummary:
    snapshot_id: str
    receipt_id: str
    version: int
    created_at: str
    document_family: str
    confidence: float
    projection_mode: str
    status: str = "active"


@dataclass(frozen=True, slots=True)
class SnapshotHistory:
    receipt_id: str
    snapshots: tuple[SnapshotSummary, ...]


@dataclass(frozen=True, slots=True)
class SnapshotComparison:
    receipt_id: str
    from_snapshot_id: str
    to_snapshot_id: str
    version_changes: Any = ()
    field_changes: Any = ()
    confidence_changes: Any = ()
    reasoning_changes: Any = ()
    knowledge_changes: Any = ()
    projection_changes: Any = ()
    grammar_changes: Any = ()
    constraint_changes: Any = ()
    learning_changes: Any = ()

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            if name.endswith("_changes"):
                object.__setattr__(self, name, freeze(getattr(self, name)))


@dataclass(frozen=True, slots=True)
class SnapshotProjection:
    snapshot_id: str
    receipt_id: str
    version: int
    tabs: tuple[str, ...]
    context: SnapshotContext
    metadata: SnapshotMetadata
    confidence: SnapshotConfidence
    references: tuple[SnapshotReference, ...] = ()


@dataclass(frozen=True, slots=True)
class ReceiptIntelligenceSnapshot:
    header: SnapshotHeader
    metadata: SnapshotMetadata
    context: SnapshotContext
    references: tuple[SnapshotReference, ...]
    confidence: SnapshotConfidence
    explanations: tuple[SnapshotExplanation, ...]
    diagnostics: SnapshotDiagnostics
    summary: SnapshotSummary
    schema_version: str = "receipt-intelligence-snapshot-v1"
