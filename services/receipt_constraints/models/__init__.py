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


class ConstraintCategory(str, Enum):
    ARITHMETIC = "arithmetic"
    STRUCTURAL = "structural"
    GRAMMAR = "grammar"
    ORDERING = "ordering"
    RELATIONSHIP = "relationship"
    TRANSITION = "transition"
    CARDINALITY = "cardinality"
    LOCALITY = "locality"
    CONFIDENCE = "confidence"
    KNOWLEDGE = "knowledge"
    CROSS_REFERENCE = "cross_reference"
    FUTURE_PRODUCT = "future_product"
    FUTURE_MERCHANT = "future_merchant"
    UNKNOWN = "unknown"


class ConstraintOutcome(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    VIOLATION = "violation"


class ConstraintDiagnosticSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class ConstraintVersion:
    entity_version: int = 1
    schema_version: str = "receipt-constraints-v1"
    status: str = "active"
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    supersedes_version: int | None = None


@dataclass(frozen=True, slots=True)
class ConstraintWeight:
    weight_id: str
    value: float
    category: ConstraintCategory = ConstraintCategory.UNKNOWN


@dataclass(frozen=True, slots=True)
class ConstraintPenalty:
    penalty_id: str
    value: float
    outcome: ConstraintOutcome = ConstraintOutcome.VIOLATION


@dataclass(frozen=True, slots=True)
class ConstraintRule:
    rule_id: str
    category: ConstraintCategory
    rule_type: str
    description: str
    weight_id: str = ""
    penalty_id: str = ""
    dependency_ids: tuple[str, ...] = ()
    parameters: tuple[tuple[str, Any], ...] = ()
    required: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "parameters",
            tuple((str(key), freeze_value(value)) for key, value in self.parameters),
        )


@dataclass(frozen=True, slots=True)
class ConstraintGroup:
    group_id: str
    name: str
    rule_ids: tuple[str, ...]
    aggregation: str = "all"
    required: bool = True


@dataclass(frozen=True, slots=True)
class ReceiptConstraint:
    constraint_set_id: str
    receipt_family: str
    name: str
    version: ConstraintVersion
    rules: tuple[ConstraintRule, ...]
    groups: tuple[ConstraintGroup, ...] = ()
    weights: tuple[ConstraintWeight, ...] = ()
    penalties: tuple[ConstraintPenalty, ...] = ()
    dependencies: tuple[str, ...] = ()
    description: str = ""


@dataclass(frozen=True, slots=True)
class ConstraintRepository:
    receipt_families: tuple[str, ...] = ()
    constraint_set_ids: tuple[str, ...] = ()
    versions: tuple[tuple[str, int], ...] = ()
    schema_version: str = "constraint-repository-index-v1"


@dataclass(frozen=True, slots=True)
class ConstraintCandidate:
    candidate_id: str
    interpretation: tuple[tuple[str, Any], ...]
    source: str = "supplied_hypothesis"
    base_confidence: float = 0.0
    grammar_compliance: float = 0.0
    knowledge_confidence: float = 0.0
    provenance: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "interpretation",
            tuple((str(key), freeze_value(value)) for key, value in self.interpretation),
        )


@dataclass(frozen=True, slots=True)
class ConstraintViolation:
    rule_id: str
    category: ConstraintCategory
    message: str
    penalty: float
    candidate_id: str


@dataclass(frozen=True, slots=True)
class ConstraintExplanation:
    rule_id: str
    candidate_id: str
    outcome: ConstraintOutcome
    message: str
    contribution: float = 0.0


@dataclass(frozen=True, slots=True)
class ConstraintEvaluation:
    rule_id: str
    candidate_id: str
    category: ConstraintCategory
    outcome: ConstraintOutcome
    penalty: float
    score: float
    explanation: str


@dataclass(frozen=True, slots=True)
class ConstraintConfidence:
    normalized: float
    grammar: float
    knowledge: float
    arithmetic: float
    structural: float
    constraint: float
    components: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True, slots=True)
class ConstraintScore:
    candidate_id: str
    constraint_score: float
    penalty_score: float
    arithmetic_score: float
    structural_score: float
    grammar_score: float
    knowledge_score: float
    overall_score: float
    confidence: ConstraintConfidence
    evaluations: tuple[ConstraintEvaluation, ...] = ()
    violations: tuple[ConstraintViolation, ...] = ()


@dataclass(frozen=True, slots=True)
class ConstraintDecision:
    best_candidate: ConstraintCandidate | None
    ranked_candidates: tuple[ConstraintCandidate, ...]
    rejected_candidates: tuple[ConstraintCandidate, ...]
    scores: tuple[ConstraintScore, ...]
    explanations: tuple[ConstraintExplanation, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class ConstraintDiagnostic:
    code: str
    message: str
    severity: ConstraintDiagnosticSeverity
    subject_id: str = ""


@dataclass(frozen=True, slots=True)
class ConstraintDiagnostics:
    errors: tuple[ConstraintDiagnostic, ...] = ()
    warnings: tuple[ConstraintDiagnostic, ...] = ()
    information: tuple[ConstraintDiagnostic, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.errors


@dataclass(frozen=True, slots=True)
class CompiledReceiptConstraints:
    constraint_set: ReceiptConstraint
    diagnostics: ConstraintDiagnostics
    ordered_rule_ids: tuple[str, ...] = ()
    rules_by_category: tuple[tuple[str, tuple[str, ...]], ...] = ()
    schema_version: str = "compiled-receipt-constraints-v1"

    @property
    def valid(self) -> bool:
        return self.diagnostics.valid


@dataclass(frozen=True, slots=True)
class ConstraintLearningSuggestion:
    suggestion_type: str
    receipt_family: str
    subject_id: str
    description: str
    proposed_value: Any = None
    evidence_references: tuple[str, ...] = ()
    confidence: float = 0.0
    requires_approval: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposed_value", freeze_value(self.proposed_value))


@dataclass(frozen=True, slots=True)
class ConstraintVersionComparison:
    constraint_set_id: str
    from_version: int
    to_version: int
    added_rules: tuple[str, ...] = ()
    removed_rules: tuple[str, ...] = ()
    changed_rules: tuple[str, ...] = ()
    changed_weights: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReceiptConstraintResult:
    receipt_family: str
    loaded: bool
    constraint_set: ReceiptConstraint | None = None
    compilation: CompiledReceiptConstraints | None = None
    candidates: tuple[ConstraintCandidate, ...] = ()
    decision: ConstraintDecision | None = None
    learning_suggestions: tuple[ConstraintLearningSuggestion, ...] = ()
    diagnostics: tuple[tuple[str, Any], ...] = ()
    schema_version: str = "receipt-constraint-result-v1"
