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


class LearningStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


@dataclass(frozen=True, slots=True)
class LearningEvidence:
    evidence_id: str
    source_type: str
    verified: bool
    quality: float
    confidence: float
    document_references: tuple[str, ...] = ()
    entity_references: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ()
    timestamp: str = field(default_factory=utc_now)
    version: str = "learning-evidence-v1"


@dataclass(frozen=True, slots=True)
class LearningEvent:
    event_id: str
    event_type: str
    source: str
    actor_id: str
    evidence_ids: tuple[str, ...] = ()
    payload: Any = None
    timestamp: str = field(default_factory=utc_now)
    version: str = "learning-event-v1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", freeze_value(self.payload))


@dataclass(frozen=True, slots=True)
class LearningFeedback:
    feedback_id: str
    actor_id: str
    actor_role: str
    feedback_type: str
    subject_id: str
    previous_value: Any = None
    proposed_value: Any = None
    reason: str = ""
    evidence_ids: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ()
    verified: bool = False
    timestamp: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "previous_value", freeze_value(self.previous_value))
        object.__setattr__(self, "proposed_value", freeze_value(self.proposed_value))


@dataclass(frozen=True, slots=True)
class LearningConfidence:
    current: float
    proposed: float
    delta: float
    repeated_confirmations: float = 0.0
    historical_consistency: float = 0.0
    evidence_quality: float = 0.0
    human_approval: float = 0.0
    cross_document_agreement: float = 0.0
    components: tuple[tuple[str, float], ...] = ()
    history: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True, slots=True)
class LearningQuality:
    score: float
    confirmation_count: int
    evidence_coverage: float
    conflict_count: int = 0
    low_confidence_count: int = 0
    acceptable: bool = False
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LearningRule:
    rule_id: str
    name: str
    minimum_confirmations: int = 2
    minimum_evidence_quality: float = 0.8
    minimum_confidence: float = 0.8
    requires_approval: bool = True
    allowed_source_types: tuple[str, ...] = (
        "approved_human_correction",
        "verified_alias",
        "verified_merchant_mapping",
        "verified_product_mapping",
        "verified_category_assignment",
        "verified_relationship",
        "verified_graph_update",
        "cross_document_confirmation",
        "historical_consistency",
        "repeated_evidence",
    )


@dataclass(frozen=True, slots=True)
class LearningCandidate:
    candidate_id: str
    candidate_type: str
    subject_id: str
    proposed_value: Any
    evidence_ids: tuple[str, ...]
    source: str
    confidence: LearningConfidence
    confirmation_count: int
    status: LearningStatus = LearningStatus.PENDING
    previous_value: Any = None
    version: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposed_value", freeze_value(self.proposed_value))
        object.__setattr__(self, "previous_value", freeze_value(self.previous_value))


@dataclass(frozen=True, slots=True)
class LearningExplanation:
    explanation_id: str
    subject_id: str
    summary: str
    evidence_ids: tuple[str, ...]
    supporting_documents: tuple[str, ...] = ()
    supporting_entities: tuple[str, ...] = ()
    historical_observations: tuple[str, ...] = ()
    confidence_components: tuple[tuple[str, float], ...] = ()
    approval_status: LearningStatus = LearningStatus.PENDING


@dataclass(frozen=True, slots=True)
class LearningProposal:
    proposal_id: str
    candidate: LearningCandidate
    quality: LearningQuality
    explanation: LearningExplanation
    status: LearningStatus = LearningStatus.PENDING
    created_at: str = field(default_factory=utc_now)
    expires_at: str = ""
    supersedes_proposal_id: str = ""


@dataclass(frozen=True, slots=True)
class LearningApproval:
    approval_id: str
    proposal_id: str
    status: LearningStatus
    approver_id: str
    approver_role: str
    reason: str
    timestamp: str = field(default_factory=utc_now)
    version: int = 1


@dataclass(frozen=True, slots=True)
class LearningDecision:
    decision_id: str
    proposal_id: str
    status: LearningStatus
    reason: str
    actor_id: str
    timestamp: str = field(default_factory=utc_now)
    version: int = 1


@dataclass(frozen=True, slots=True)
class LearningAudit:
    audit_id: str
    action: str
    subject_id: str
    actor_id: str
    source: str
    reason: str
    evidence_ids: tuple[str, ...]
    previous_value: Any = None
    new_value: Any = None
    timestamp: str = field(default_factory=utc_now)
    version: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "previous_value", freeze_value(self.previous_value))
        object.__setattr__(self, "new_value", freeze_value(self.new_value))


@dataclass(frozen=True, slots=True)
class LearningDiagnostics:
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    information: tuple[str, ...] = ()
    sidecar: bool = True
    affects_extraction: bool = False
    parser_authority_changed: bool = False
    production_knowledge_modified: bool = False
    automatic_approval_performed: bool = False
    machine_learning_used: bool = False
    raw_ocr_consumed: bool = False
    parser_output_consumed_directly: bool = False

    @property
    def valid(self) -> bool:
        return not self.errors


@dataclass(frozen=True, slots=True)
class LearningSnapshotVersion:
    entity_version: int = 1
    schema_version: str = "enterprise-learning-snapshot-v1"
    status: str = "active"
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    supersedes_version: int | None = None


@dataclass(frozen=True, slots=True)
class LearningSnapshot:
    snapshot_id: str
    events: tuple[LearningEvent, ...] = ()
    feedback: tuple[LearningFeedback, ...] = ()
    evidence: tuple[LearningEvidence, ...] = ()
    proposals: tuple[LearningProposal, ...] = ()
    decisions: tuple[LearningDecision, ...] = ()
    approvals: tuple[LearningApproval, ...] = ()
    audit: tuple[LearningAudit, ...] = ()
    version: LearningSnapshotVersion = field(default_factory=LearningSnapshotVersion)


@dataclass(frozen=True, slots=True)
class LearningSnapshotComparison:
    snapshot_id: str
    from_version: int
    to_version: int
    added_proposals: tuple[str, ...] = ()
    removed_proposals: tuple[str, ...] = ()
    changed_proposals: tuple[str, ...] = ()
    added_audit: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EnterpriseLearningResult:
    snapshot: LearningSnapshot
    diagnostics: LearningDiagnostics
    schema_version: str = "enterprise-learning-result-v1"

