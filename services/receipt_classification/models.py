from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class FeatureMetricGroup:
    metrics: tuple[tuple[str, float], ...] = ()

    def as_dict(self) -> dict[str, float]:
        return dict(self.metrics)


@dataclass(frozen=True, slots=True)
class ReceiptFeatureVector:
    document_id: str
    page_metrics: FeatureMetricGroup
    layout_metrics: FeatureMetricGroup
    table_metrics: FeatureMetricGroup
    spacing_metrics: FeatureMetricGroup
    alignment_metrics: FeatureMetricGroup
    reading_metrics: FeatureMetricGroup
    density_metrics: FeatureMetricGroup
    geometry_metrics: FeatureMetricGroup
    version: int = 1
    schema_version: str = "receipt-feature-vector-v1"

    def flatten(self) -> tuple[tuple[str, float], ...]:
        values: list[tuple[str, float]] = []
        for group_name in (
            "page_metrics", "layout_metrics", "table_metrics", "spacing_metrics",
            "alignment_metrics", "reading_metrics", "density_metrics", "geometry_metrics",
        ):
            group = getattr(self, group_name)
            prefix = group_name.removesuffix("_metrics")
            values.extend((f"{prefix}.{name}", value) for name, value in group.metrics)
        return tuple(values)


@dataclass(frozen=True, slots=True)
class ReceiptFamilyFeatureProfile:
    receipt_family: str
    feature_metrics: tuple[tuple[str, float], ...]
    profile_version: int = 1
    blueprint_reference: str = ""
    confidence: float = 1.0
    weights: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True, slots=True)
class StrategyScore:
    strategy: str
    score: float
    coverage: float


@dataclass(frozen=True, slots=True)
class BlueprintComparison:
    receipt_family: str
    profile_version: int
    similarity_scores: tuple[StrategyScore, ...]
    confidence_breakdown: tuple[tuple[str, float], ...]
    feature_deltas: tuple[tuple[str, float], ...]
    coverage: float
    confidence: float
    blueprint_reference: str = ""


@dataclass(frozen=True, slots=True)
class ReceiptFamilyCandidate:
    receipt_family: str
    confidence: float
    rank: int
    reason: str
    confidence_breakdown: tuple[tuple[str, float], ...] = ()
    blueprint_reference: str = ""


@dataclass(frozen=True, slots=True)
class BlueprintLearningSuggestion:
    receipt_family: str
    proposed_metrics: tuple[tuple[str, float], ...]
    confidence: float
    suggestion_type: str = "feature_distribution_observation"
    requires_approval: bool = True


@dataclass(frozen=True, slots=True)
class ReceiptClassification:
    document_id: str
    feature_vector: ReceiptFeatureVector
    candidates: tuple[ReceiptFamilyCandidate, ...]
    comparisons: tuple[BlueprintComparison, ...]
    learning_suggestions: tuple[BlueprintLearningSuggestion, ...] = ()
    diagnostics: tuple[tuple[str, Any], ...] = ()
    schema_version: str = "receipt-classification-v1"
