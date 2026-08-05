from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return tuple((str(key), freeze(item)) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return tuple(freeze(item) for item in value)
    if isinstance(value, set):
        return tuple(sorted((freeze(item) for item in value), key=str))
    return value


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProjectionMode(str, Enum):
    PARSER_ONLY = "parser_only"
    ENTERPRISE_ONLY = "enterprise_only"
    HYBRID = "hybrid"
    SHADOW = "shadow"
    COMPARE = "compare"


class ProjectionSource(str, Enum):
    PARSER = "parser"
    ENTERPRISE = "enterprise"
    HYBRID = "hybrid"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class ProjectionConfidence:
    display: float
    parser: float = 0.0
    enterprise: float = 0.0
    grammar: float = 0.0
    constraint: float = 0.0
    learning: float = 0.0
    graph: float = 0.0
    components: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True, slots=True)
class ProjectionConflict:
    field_key: str
    parser_value: Any
    enterprise_value: Any
    selected_source: ProjectionSource
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "parser_value", freeze(self.parser_value))
        object.__setattr__(self, "enterprise_value", freeze(self.enterprise_value))


@dataclass(frozen=True, slots=True)
class ProjectionDecision:
    field_key: str
    selected_source: ProjectionSource
    reason: str
    mode: ProjectionMode


@dataclass(frozen=True, slots=True)
class ProjectionExplanation:
    summary: str
    reasons: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProjectionField:
    key: str
    label: str
    parser_value: Any
    enterprise_value: Any
    displayed_value: Any
    source: ProjectionSource
    confidence: ProjectionConfidence
    evidence: tuple[str, ...]
    decision: ProjectionDecision
    explanation: ProjectionExplanation

    def __post_init__(self) -> None:
        for name in ("parser_value", "enterprise_value", "displayed_value"):
            object.__setattr__(self, name, freeze(getattr(self, name)))


@dataclass(frozen=True, slots=True)
class ProjectionSection:
    key: str
    title: str
    fields: tuple[ProjectionField, ...]
    visible: bool = True
    empty_message: str = ""


@dataclass(frozen=True, slots=True)
class ProjectionMetadata:
    projection_id: str
    document_id: str
    document_family: str
    business_view: str
    profile_id: str
    mode: ProjectionMode
    version: int = 1
    created_time: str = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class ProjectionDiagnostics:
    sidecar: bool = True
    affects_extraction: bool = False
    parser_modified: bool = False
    enterprise_intelligence_modified: bool = False
    parser_authority_changed: bool = False
    ui_projection_only: bool = True
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProjectionProfile:
    profile_id: str
    family: str
    business_view: str
    sections: tuple[tuple[str, tuple[str, ...]], ...]
    prefer_enterprise_fields: tuple[str, ...] = ()
    items_expected: bool = True


@dataclass(frozen=True, slots=True)
class BusinessProjection:
    metadata: ProjectionMetadata
    sections: tuple[ProjectionSection, ...]
    fields: tuple[ProjectionField, ...]
    conflicts: tuple[ProjectionConflict, ...]
    overall_confidence: ProjectionConfidence
    diagnostics: ProjectionDiagnostics
    schema_version: str = "business-projection-v1"

