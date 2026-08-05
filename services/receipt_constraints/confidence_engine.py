from __future__ import annotations

from .models import ConstraintConfidence


class ConstraintConfidenceEngine:
    DEFAULT_WEIGHTS = {
        "grammar": 0.20,
        "knowledge": 0.15,
        "arithmetic": 0.25,
        "structural": 0.20,
        "constraint": 0.20,
    }

    def combine(
        self,
        *,
        grammar: float,
        knowledge: float,
        arithmetic: float,
        structural: float,
        constraint: float,
        weights: dict[str, float] | None = None,
    ) -> ConstraintConfidence:
        configured = weights or self.DEFAULT_WEIGHTS
        components = {
            "grammar": self._bound(grammar),
            "knowledge": self._bound(knowledge),
            "arithmetic": self._bound(arithmetic),
            "structural": self._bound(structural),
            "constraint": self._bound(constraint),
        }
        total_weight = sum(max(0.0, float(configured.get(name, 0.0))) for name in components)
        normalized = (
            sum(
                components[name] * max(0.0, float(configured.get(name, 0.0)))
                for name in components
            ) / total_weight
            if total_weight else 0.0
        )
        return ConstraintConfidence(
            normalized=round(self._bound(normalized), 6),
            grammar=components["grammar"],
            knowledge=components["knowledge"],
            arithmetic=components["arithmetic"],
            structural=components["structural"],
            constraint=components["constraint"],
            components=tuple((name, value) for name, value in components.items()),
        )

    def _bound(self, value: float) -> float:
        return round(max(0.0, min(1.0, float(value))), 6)

