from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


def immutable_mapping(value: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    return MappingProxyType(dict(value or {}))


@dataclass(frozen=True)
class QualityFactor:
    name: str
    score: float
    confidence: float
    passed: bool
    measured_value: float | str | bool | None = None
    threshold: float | str | bool | None = None
    diagnostics: Mapping[str, Any] = field(default_factory=immutable_mapping)


@dataclass(frozen=True)
class QualityRecommendation:
    code: str
    message: str
    severity: str
    factor: str


@dataclass(frozen=True)
class OrientationResult:
    degrees: int
    confidence: float
    normalized: bool


@dataclass(frozen=True)
class ReceiptQualityResult:
    status: str
    passed: bool
    overall_score: float
    confidence: float
    factors: tuple[QualityFactor, ...]
    recommendations: tuple[QualityRecommendation, ...]
    orientation: OrientationResult
    policy_id: str
    policy_version: str
    normalized_image_bytes: bytes = field(repr=False, compare=False)
    diagnostics: Mapping[str, Any] = field(default_factory=immutable_mapping)
    geometry_validation: Mapping[str, Any] = field(default_factory=immutable_mapping)

    def to_dict(self, *, include_image: bool = False) -> dict[str, Any]:
        payload = {
            "schemaVersion": "receipt-capture-quality-v1",
            "status": self.status,
            "passed": self.passed,
            "overallScore": self.overall_score,
            "confidence": self.confidence,
            "orientation": self.orientation.__dict__,
            "policy": {"id": self.policy_id, "version": self.policy_version},
            "factors": [{**factor.__dict__, "diagnostics": dict(factor.diagnostics)} for factor in self.factors],
            "recommendations": [item.__dict__ for item in self.recommendations],
            "diagnostics": dict(self.diagnostics),
            "geometryValidation": dict(self.geometry_validation),
        }
        if include_image:
            payload["normalizedImageBytes"] = self.normalized_image_bytes
        return payload


@dataclass(frozen=True)
class CaptureQualityPolicy:
    policy_id: str
    version: str
    minimum_overall_score: float
    minimum_factor_scores: Mapping[str, float]
    scoring_ranges: Mapping[str, Mapping[str, float]]
    weights: Mapping[str, float]
    minimum_family_confidence: float
    minimum_semantic_confidence: float
    minimum_enterprise_confidence: float
    recommendations: Mapping[str, str]
