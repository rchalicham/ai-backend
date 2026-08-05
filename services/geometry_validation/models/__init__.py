from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


def frozen_map(value: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    return MappingProxyType(dict(value or {}))


@dataclass(frozen=True)
class GeometryObservation:
    measurement: Any
    confidence: float
    reliable: bool
    reason: str
    diagnostics: Mapping[str, Any] = field(default_factory=frozen_map)


@dataclass(frozen=True)
class RejectedContour:
    boundary: tuple[tuple[float, float], ...]
    reasons: tuple[str, ...]
    confidence: float


@dataclass(frozen=True)
class GeometryConfidence:
    contour: float
    boundary: float
    perspective: float
    skew: float
    coverage: float
    overall: float
    reliable: bool


@dataclass(frozen=True)
class GeometryValidationResult:
    raw_geometry: Any
    validated_geometry: Any
    effective_geometry: Any
    raw_contour: tuple[tuple[float, float], ...]
    validated_contour: tuple[tuple[float, float], ...]
    fallback_contour: tuple[tuple[float, float], ...]
    rejected_contours: tuple[RejectedContour, ...]
    confidence: GeometryConfidence
    reliability: str
    reason: str
    fallback_source: str
    observations: Mapping[str, GeometryObservation]
    timeline: tuple[Mapping[str, Any], ...]
    configuration_id: str
    configuration_version: str


@dataclass(frozen=True)
class GeometryValidationPolicy:
    configuration_id: str
    version: str
    contour_limits: Mapping[str, float]
    confidence_thresholds: Mapping[str, float]
    confidence_weights: Mapping[str, float]
    fallback_order: tuple[str, ...]
    perspective_limits: Mapping[str, float]
    skew_limits: Mapping[str, float]
    page_detection: Mapping[str, float]
    critical_factors: tuple[str, ...]
    advisory_factors: tuple[str, ...]
