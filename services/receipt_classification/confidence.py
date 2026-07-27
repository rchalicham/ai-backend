from __future__ import annotations

from statistics import fmean, pstdev

from .models import StrategyScore


class ReceiptConfidenceEngine:
    GROUP_WEIGHTS = {
        "geometry": 0.20, "layout": 0.20, "alignment": 0.15,
        "density": 0.15, "table": 0.15, "reading": 0.15,
    }

    def calculate(
        self,
        scores: tuple[StrategyScore, ...],
        deltas: tuple[tuple[str, float], ...],
        profile_confidence: float,
    ) -> tuple[float, tuple[tuple[str, float], ...]]:
        strategy_mean = fmean(score.score for score in scores) if scores else 0.0
        coverage = fmean(score.coverage for score in scores) if scores else 0.0
        agreement = 1.0 - min(1.0, pstdev(score.score for score in scores)) if len(scores) > 1 else 1.0
        grouped: list[tuple[str, float]] = []
        for group, weight in self.GROUP_WEIGHTS.items():
            values = [abs(value) for key, value in deltas if key.startswith(f"{group}.")]
            similarity = max(0.0, 1.0 - fmean(min(1.0, value / max(abs(value), 1.0)) for value in values)) if values else 0.0
            grouped.append((group, similarity))
        confidence = strategy_mean * (0.65 + 0.20 * coverage + 0.15 * agreement) * max(0.0, min(1.0, profile_confidence))
        breakdown = tuple(grouped + [("strategy", strategy_mean), ("coverage", coverage), ("agreement", agreement)])
        return max(0.0, min(1.0, confidence)), breakdown
