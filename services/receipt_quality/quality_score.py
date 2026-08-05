from __future__ import annotations

from .models import CaptureQualityPolicy, QualityFactor


def range_score(value: float, limits: dict | object, *, inverse: bool = False) -> float:
    low = float(limits["poor"])
    high = float(limits["good"])
    if high == low:
        return 1.0 if value >= high else 0.0
    score = (value - low) / (high - low)
    score = min(1.0, max(0.0, score))
    return round(1.0 - score if inverse else score, 4)


class QualityScoreEngine:
    def aggregate(self, factors: tuple[QualityFactor, ...], policy: CaptureQualityPolicy) -> tuple[float, float]:
        weighted = [(factor.score, float(policy.weights.get(factor.name, 0.0))) for factor in factors]
        total_weight = sum(weight for _, weight in weighted)
        if total_weight <= 0:
            raise ValueError("enterprise_configuration_invalid:quality_weights")
        score = sum(value * weight for value, weight in weighted) / total_weight
        confidence = sum(factor.confidence * weight for factor, weight in zip(factors, [weight for _, weight in weighted])) / total_weight
        return round(score, 4), round(confidence, 4)

