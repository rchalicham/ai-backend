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


class QueryType(str, Enum):
    RECEIPT = "receipt_question"
    PRODUCT = "product_question"
    MERCHANT = "merchant_question"
    TIMELINE = "timeline_question"
    BUDGET = "budget_question"
    HEALTH = "health_question"
    EXPENSE = "expense_question"
    CROSS_DOCUMENT = "cross_document_question"
    KNOWLEDGE_GRAPH = "knowledge_graph_question"
    ANALYTICS = "analytics_question"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ReasoningRequest:
    request_id: str
    question: str
    query_type: QueryType = QueryType.UNKNOWN
    subject_ids: tuple[str, ...] = ()
    allow_llm: bool = False
    timeout_ms: int = 1000
    timestamp: str = field(default_factory=utc_now)
    version: str = "reasoning-request-v1"


@dataclass(frozen=True, slots=True)
class ReasoningContext:
    context_id: str
    constraint_result: Any = None
    product_intelligence: Any = None
    enterprise_graph: Any = None
    cross_document_intelligence: Any = None
    enterprise_learning: Any = None
    approved_evidence_only: bool = True
    raw_ocr_present: bool = False
    parser_guesses_present: bool = False

    def __post_init__(self) -> None:
        for name in (
            "constraint_result", "product_intelligence", "enterprise_graph",
            "cross_document_intelligence", "enterprise_learning",
        ):
            object.__setattr__(self, name, freeze_value(getattr(self, name)))


@dataclass(frozen=True, slots=True)
class ReasoningStep:
    step_id: str
    operation: str
    tool_name: str
    depends_on: tuple[str, ...] = ()
    condition: str = "always"
    required: bool = True
    timeout_ms: int = 500
    retry_count: int = 0


@dataclass(frozen=True, slots=True)
class ReasoningPlan:
    plan_id: str
    query_type: QueryType
    steps: tuple[ReasoningStep, ...]
    rationale: tuple[str, ...] = ()
    llm_required: bool = False
    deterministic_first: bool = True
    version: str = "reasoning-plan-v1"


@dataclass(frozen=True, slots=True)
class ReasoningTool:
    name: str
    capability: str
    deterministic: bool = True
    enabled: bool = True
    future: bool = False
    timeout_ms: int = 500


@dataclass(frozen=True, slots=True)
class ReasoningEvidence:
    evidence_id: str
    source_tool: str
    evidence_type: str
    content: Any
    confidence: float
    quality: float
    supporting_entities: tuple[str, ...] = ()
    supporting_documents: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ()
    version: str = "reasoning-evidence-v1"
    timestamp: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "content", freeze_value(self.content))


@dataclass(frozen=True, slots=True)
class ReasoningHypothesis:
    hypothesis_id: str
    statement: str
    evidence_ids: tuple[str, ...]
    confidence: float
    supported: bool = True
    rejection_reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReasoningConfidence:
    overall: float
    constraint: float = 0.0
    graph: float = 0.0
    learning: float = 0.0
    evidence: float = 0.0
    historical: float = 0.0
    llm: float = 0.0
    components: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True, slots=True)
class ReasoningDecision:
    decision_id: str
    selected_hypothesis_id: str
    answer: str
    confidence: ReasoningConfidence
    evidence_ids: tuple[str, ...]
    rejected_hypothesis_ids: tuple[str, ...] = ()
    authoritative: bool = False


@dataclass(frozen=True, slots=True)
class ReasoningExplanation:
    explanation_id: str
    summary: str
    tool_selection: tuple[str, ...] = ()
    trusted_evidence: tuple[str, ...] = ()
    rejected_hypotheses: tuple[str, ...] = ()
    confidence_method: str = ""


@dataclass(frozen=True, slots=True)
class ReasoningTrace:
    trace_id: str
    step_id: str
    tool_name: str
    status: str
    attempt: int = 1
    duration_ms: float = 0.0
    evidence_ids: tuple[str, ...] = ()
    message: str = ""
    timestamp: str = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class ReasoningSession:
    session_id: str
    request: ReasoningRequest
    plan: ReasoningPlan
    traces: tuple[ReasoningTrace, ...] = ()
    status: str = "completed"
    started_at: str = field(default_factory=utc_now)
    completed_at: str = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class ReasoningDiagnostics:
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    information: tuple[str, ...] = ()
    sidecar: bool = True
    affects_extraction: bool = False
    parser_authority_changed: bool = False
    production_knowledge_modified: bool = False
    raw_ocr_consumed: bool = False
    parser_guesses_consumed: bool = False
    llm_bypassed_evidence: bool = False
    llm_used: bool = False

    @property
    def valid(self) -> bool:
        return not self.errors


@dataclass(frozen=True, slots=True)
class ReasoningResponse:
    request: ReasoningRequest
    session: ReasoningSession
    evidence: tuple[ReasoningEvidence, ...]
    hypotheses: tuple[ReasoningHypothesis, ...]
    decision: ReasoningDecision | None
    explanation: ReasoningExplanation
    provenance: tuple[str, ...]
    diagnostics: ReasoningDiagnostics
    natural_language_response: str = ""
    schema_version: str = "enterprise-reasoning-response-v1"
