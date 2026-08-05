from __future__ import annotations

from .models import GeometryConfidence


class GeometryConfidenceEngine:
    def calculate(self, observations, policy):
        values={key:float(observations[key].confidence) for key in ("contour","boundary","perspective","skew","coverage")}
        weights=policy.confidence_weights
        total=sum(float(weights.get(k,0)) for k in values)
        overall=sum(values[k]*float(weights.get(k,0)) for k in values)/max(total,0.001)
        reliable=overall >= float(policy.confidence_thresholds["overall"])
        return GeometryConfidence(**values,overall=round(overall,4),reliable=reliable)
