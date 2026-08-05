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
class ProcessingExplanation:
    title: str
    message: str
    reason_code: str


@dataclass(frozen=True)
class ProcessingRecommendation:
    code: str
    label: str
    why: str
    action: str
    priority: str


@dataclass(frozen=True)
class Recoverability:
    kind: str
    score: float
    confidence: float
    recommendation: str


@dataclass(frozen=True)
class ProcessingConfidence:
    overall: float
    quality: float | None = None
    family: float | None = None
    projection: float | None = None


@dataclass(frozen=True)
class ProcessingStage:
    key: str
    label: str
    state: str
    duration_ms: int | None
    confidence: float | None
    explanation: str
    order: int
    color: str
    icon: str


@dataclass(frozen=True)
class ProcessingState:
    key: str
    label: str
    color: str
    icon: str


@dataclass(frozen=True)
class ProcessingTimeline:
    stages: tuple[ProcessingStage, ...]
    current_stage: str


@dataclass(frozen=True)
class ProcessingDiagnostics:
    source_signals: Mapping[str, Any] = field(default_factory=frozen_map)
    parser_modified: bool = False
    enterprise_intelligence_modified: bool = False
    projection_modified: bool = False


@dataclass(frozen=True)
class ProcessingSummary:
    current_stage: str
    overall_status: str
    quality_score: float | None
    family: str
    projection_available: bool
    human_review: bool
    recoverability: Recoverability
    recommendations: tuple[ProcessingRecommendation, ...]
    business_summary: str


@dataclass(frozen=True)
class ReceiptProcessingStatus:
    state: ProcessingState
    summary: ProcessingSummary
    timeline: ProcessingTimeline
    explanation: ProcessingExplanation
    confidence: ProcessingConfidence
    diagnostics: ProcessingDiagnostics
    configuration_id: str
    configuration_version: str
    actions: Mapping[str, Any] = field(default_factory=frozen_map)
    labels: Mapping[str, str] = field(default_factory=frozen_map)
