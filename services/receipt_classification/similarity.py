from __future__ import annotations

from math import sqrt
from typing import Protocol

from .models import ReceiptFamilyFeatureProfile, ReceiptFeatureVector, StrategyScore


class SimilarityStrategy(Protocol):
    name: str

    def score(self, current: dict[str, float], target: dict[str, float], weights: dict[str, float]) -> float: ...


def _shared(current: dict[str, float], target: dict[str, float]) -> tuple[str, ...]:
    return tuple(sorted(set(current).intersection(target)))


class WeightedEuclideanSimilarity:
    name = "weighted_euclidean"

    def score(self, current: dict[str, float], target: dict[str, float], weights: dict[str, float]) -> float:
        keys = _shared(current, target)
        if not keys:
            return 0.0
        weighted = [
            weights.get(key, 1.0) * ((current[key] - target[key]) / max(abs(current[key]), abs(target[key]), 1.0)) ** 2
            for key in keys
        ]
        return max(0.0, 1.0 - sqrt(sum(weighted) / max(sum(weights.get(key, 1.0) for key in keys), 1e-9)))


class CosineSimilarity:
    name = "cosine"

    def score(self, current: dict[str, float], target: dict[str, float], weights: dict[str, float]) -> float:
        keys = _shared(current, target)
        if not keys:
            return 0.0
        dot = sum(weights.get(key, 1.0) * current[key] * target[key] for key in keys)
        left = sqrt(sum(weights.get(key, 1.0) * current[key] ** 2 for key in keys))
        right = sqrt(sum(weights.get(key, 1.0) * target[key] ** 2 for key in keys))
        return max(0.0, min(1.0, dot / (left * right))) if left and right else float(left == right)


class NormalizedFeatureDistance:
    name = "normalized_feature_distance"

    def score(self, current: dict[str, float], target: dict[str, float], weights: dict[str, float]) -> float:
        keys = _shared(current, target)
        if not keys:
            return 0.0
        total_weight = sum(weights.get(key, 1.0) for key in keys)
        distance = sum(
            weights.get(key, 1.0) * abs(current[key] - target[key]) / max(abs(current[key]), abs(target[key]), 1.0)
            for key in keys
        ) / max(total_weight, 1e-9)
        return max(0.0, 1.0 - distance)


class ReceiptSimilarityEngine:
    def __init__(self, strategies: tuple[SimilarityStrategy, ...] | None = None) -> None:
        self.strategies = strategies or (
            WeightedEuclideanSimilarity(), CosineSimilarity(), NormalizedFeatureDistance(),
        )

    def compare(
        self,
        vector: ReceiptFeatureVector,
        profile: ReceiptFamilyFeatureProfile,
    ) -> tuple[tuple[StrategyScore, ...], tuple[tuple[str, float], ...], float]:
        current, target = dict(vector.flatten()), dict(profile.feature_metrics)
        weights = dict(profile.weights)
        common = _shared(current, target)
        coverage = len(common) / max(len(target), 1)
        scores = tuple(
            StrategyScore(strategy.name, strategy.score(current, target, weights), coverage)
            for strategy in self.strategies
        )
        deltas = tuple(
            (key, round(current[key] - target[key], 8))
            for key in common
        )
        return scores, deltas, coverage
