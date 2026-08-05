from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


def frozen_map(value: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    def freeze(item):
        if isinstance(item, Mapping):
            return MappingProxyType({key: freeze(nested) for key, nested in item.items()})
        if isinstance(item, (list, tuple)):
            return tuple(freeze(nested) for nested in item)
        return item
    return freeze(value or {})


@dataclass(frozen=True)
class FamilyReviewPolicy:
    family: str
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...]
    expected_sections: tuple[str, ...]
    minimum_items: int | None
    maximum_items: int | None
    minimum_completeness: float
    minimum_confidence: float
    configuration: Mapping[str, Any] = field(default_factory=frozen_map)


@dataclass(frozen=True)
class SemanticCompleteness:
    score: float
    required_score: float
    optional_score: float
    section_score: float
    missing_required_fields: tuple[str, ...]
    missing_optional_fields: tuple[str, ...]
    missing_sections: tuple[str, ...]
    item_expectation_satisfied: bool
    grammar_compliance: float
    constraint_compliance: float
    projection_completeness: float


@dataclass(frozen=True)
class ResolvedQuality:
    passed: bool
    score: float | None
    unresolved_warnings: tuple[Mapping[str, Any], ...]
    resolved_warnings: tuple[Mapping[str, Any], ...]
    fallback_used: str
    confidence: float


@dataclass(frozen=True)
class ReviewConfidence:
    overall: float
    family: float
    semantic: float
    projection: float
    reasoning: float
    quality: float


@dataclass(frozen=True)
class ReviewRecommendation:
    code: str
    message: str
    reason: str
    priority: str


@dataclass(frozen=True)
class ReviewExplanation:
    title: str
    message: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class ReviewDecision:
    key: str
    label: str
    processing_state: str
    requires_human_review: bool
    confidence: float
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class ReviewDiagnostics:
    policy_source: str
    inputs_consumed: tuple[str, ...]
    parser_modified: bool = False
    projection_modified: bool = False
    enterprise_intelligence_modified: bool = False


@dataclass(frozen=True)
class DocumentReviewResult:
    family: str
    policy: FamilyReviewPolicy
    semantic_completeness: SemanticCompleteness
    resolved_quality: ResolvedQuality
    confidence: ReviewConfidence
    decision: ReviewDecision
    recommendations: tuple[ReviewRecommendation, ...]
    explanation: ReviewExplanation
    diagnostics: ReviewDiagnostics
    configuration_id: str
    configuration_version: str
