from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def freeze_value(value: Any) -> Any:
    if isinstance(value, dict):
        return tuple((str(key), freeze_value(item)) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return tuple(freeze_value(item) for item in value)
    if isinstance(value, set):
        return tuple(sorted((freeze_value(item) for item in value), key=str))
    return value


class DocumentType(str, Enum):
    RECEIPT = "Receipt"
    INVOICE = "Invoice"
    PURCHASE_ORDER = "Purchase Order"
    WARRANTY = "Warranty"
    MANUAL = "Manual"
    MEDICAL_RECORD = "Medical Record"
    INSURANCE_DOCUMENT = "Insurance Document"
    BILL = "Bill"
    STATEMENT = "Statement"
    CONTRACT = "Contract"
    IDENTITY_DOCUMENT = "Identity Document"
    UNKNOWN = "Unknown"


@dataclass(frozen=True, slots=True)
class DocumentReference:
    document_id: str
    document_type: DocumentType | str
    graph_id: str
    timestamp: str = field(default_factory=utc_now)
    version: str = "document-reference-v1"
    evidence_references: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Confidence:
    normalized: float
    graph: float = 0.0
    entity: float = 0.0
    evidence: float = 0.0
    temporal: float = 0.0
    relationship: float = 0.0
    components: tuple[tuple[str, float], ...] = ()
    upstream_values: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True, slots=True)
class ContextEntity:
    entity_id: str
    entity_type: str
    label: str
    aliases: tuple[str, ...] = ()
    document_references: tuple[DocumentReference, ...] = ()
    graph_node_ids: tuple[str, ...] = ()
    confidence: Confidence = field(default_factory=lambda: Confidence(0.0))
    provenance: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ContextRelationship:
    relationship_id: str
    relationship_type: str
    source_entity_id: str
    target_entity_id: str
    document_references: tuple[DocumentReference, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    confidence: Confidence = field(default_factory=lambda: Confidence(0.0))
    provenance: tuple[str, ...] = ()
    explanation: str = ""


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    evidence_id: str
    supporting_documents: tuple[DocumentReference, ...]
    evidence_references: tuple[str, ...]
    source_entity_ids: tuple[str, ...]
    reason: str
    confidence: Confidence
    timestamp: str = field(default_factory=utc_now)
    version: str = "cross-document-evidence-v1"


@dataclass(frozen=True, slots=True)
class TimelineEvent:
    event_id: str
    event_type: str
    timestamp: str
    document_reference: DocumentReference
    entity_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    description: str = ""
    confidence: Confidence = field(default_factory=lambda: Confidence(0.0))


@dataclass(frozen=True, slots=True)
class Timeline:
    timeline_id: str
    subject_entity_id: str
    events: tuple[TimelineEvent, ...] = ()
    version: str = "cross-document-timeline-v1"


@dataclass(frozen=True, slots=True)
class Correlation:
    correlation_id: str
    correlation_type: str
    entity_ids: tuple[str, ...]
    document_references: tuple[DocumentReference, ...]
    evidence_ids: tuple[str, ...]
    reason: str
    confidence: Confidence
    timestamp: str = field(default_factory=utc_now)
    version: str = "cross-document-correlation-v1"


@dataclass(frozen=True, slots=True)
class Similarity:
    similarity_id: str
    left_id: str
    right_id: str
    strategy: str
    score: float
    evidence_references: tuple[str, ...] = ()
    explanation: str = ""


@dataclass(frozen=True, slots=True)
class Anomaly:
    anomaly_id: str
    anomaly_type: str
    severity: str
    document_references: tuple[DocumentReference, ...]
    entity_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    reason: str = ""
    confidence: Confidence = field(default_factory=lambda: Confidence(0.0))
    automatic_correction: bool = False


@dataclass(frozen=True, slots=True)
class Pattern:
    pattern_id: str
    pattern_type: str
    subject_entity_ids: tuple[str, ...]
    document_references: tuple[DocumentReference, ...]
    evidence_ids: tuple[str, ...] = ()
    occurrences: int = 0
    description: str = ""
    confidence: Confidence = field(default_factory=lambda: Confidence(0.0))
    predictive: bool = False


@dataclass(frozen=True, slots=True)
class Explanation:
    explanation_id: str
    subject_id: str
    summary: str
    evidence_ids: tuple[str, ...] = ()
    confidence_contributions: tuple[tuple[str, float], ...] = ()
    timeline_reasoning: str = ""
    pattern_reasoning: str = ""
    relationship_reasoning: str = ""


@dataclass(frozen=True, slots=True)
class EnterpriseContext:
    context_id: str
    current_document: DocumentReference
    related_documents: tuple[DocumentReference, ...] = ()
    entities: tuple[ContextEntity, ...] = ()
    relationships: tuple[ContextRelationship, ...] = ()
    correlations: tuple[Correlation, ...] = ()
    timelines: tuple[Timeline, ...] = ()
    evidence: tuple[EvidenceRecord, ...] = ()
    similarities: tuple[Similarity, ...] = ()
    patterns: tuple[Pattern, ...] = ()
    anomalies: tuple[Anomaly, ...] = ()
    explanations: tuple[Explanation, ...] = ()


@dataclass(frozen=True, slots=True)
class MemoryVersion:
    entity_version: int = 1
    schema_version: str = "cross-document-memory-v1"
    status: str = "active"
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    supersedes_version: int | None = None


@dataclass(frozen=True, slots=True)
class MemorySnapshot:
    memory_id: str
    documents: tuple[DocumentReference, ...] = ()
    entities: tuple[ContextEntity, ...] = ()
    relationships: tuple[ContextRelationship, ...] = ()
    timelines: tuple[Timeline, ...] = ()
    evidence: tuple[EvidenceRecord, ...] = ()
    patterns: tuple[Pattern, ...] = ()
    correlations: tuple[Correlation, ...] = ()
    version: MemoryVersion = field(default_factory=MemoryVersion)
    deterministic: bool = True
    llm_memory: bool = False


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    message: str
    severity: str = "info"
    subject_id: str = ""


@dataclass(frozen=True, slots=True)
class Diagnostics:
    errors: tuple[Diagnostic, ...] = ()
    warnings: tuple[Diagnostic, ...] = ()
    information: tuple[Diagnostic, ...] = ()
    sidecar: bool = True
    affects_extraction: bool = False
    parser_authority_changed: bool = False
    documents_modified: bool = False
    graph_modified: bool = False
    machine_learning_used: bool = False
    memory_write_performed: bool = False

    @property
    def valid(self) -> bool:
        return not self.errors


@dataclass(frozen=True, slots=True)
class LearningSuggestion:
    suggestion_type: str
    description: str
    proposed_value: Any = None
    evidence_references: tuple[str, ...] = ()
    confidence: float = 0.0
    requires_approval: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposed_value", freeze_value(self.proposed_value))


@dataclass(frozen=True, slots=True)
class IntelligenceResult:
    context: EnterpriseContext
    memory: MemorySnapshot
    diagnostics: Diagnostics
    learning_suggestions: tuple[LearningSuggestion, ...] = ()
    schema_version: str = "cross-document-intelligence-v1"


@dataclass(frozen=True, slots=True)
class MemoryComparison:
    memory_id: str
    from_version: int
    to_version: int
    added_documents: tuple[str, ...] = ()
    removed_documents: tuple[str, ...] = ()
    added_entities: tuple[str, ...] = ()
    removed_entities: tuple[str, ...] = ()
    changed_entities: tuple[str, ...] = ()
