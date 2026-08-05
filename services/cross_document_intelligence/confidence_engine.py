from __future__ import annotations

from .models import Confidence


class CrossDocumentConfidenceEngine:
    WEIGHTS = {
        "graph": 0.25,
        "entity": 0.25,
        "evidence": 0.20,
        "temporal": 0.10,
        "relationship": 0.20,
    }

    def aggregate(
        self,
        *,
        graph: float,
        entity: float,
        evidence: float,
        temporal: float,
        relationship: float,
        upstream_values: tuple[tuple[str, float], ...] = (),
    ) -> Confidence:
        values = {
            "graph": graph,
            "entity": entity,
            "evidence": evidence,
            "temporal": temporal,
            "relationship": relationship,
        }
        clamped = {key: max(0.0, min(1.0, float(value or 0.0))) for key, value in values.items()}
        normalized = sum(clamped[key] * weight for key, weight in self.WEIGHTS.items())
        return Confidence(
            round(normalized, 6),
            **clamped,
            components=tuple((key, clamped[key]) for key in self.WEIGHTS),
            upstream_values=tuple(upstream_values),
        )

