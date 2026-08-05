from __future__ import annotations

from .models import CaptureQualityPolicy, QualityFactor, immutable_mapping
from .quality_score import range_score


def factor(name: str, value: float, policy: CaptureQualityPolicy, *, inverse: bool = False, diagnostics=None) -> QualityFactor:
    ranges = policy.scoring_ranges.get(name)
    if not ranges:
        raise ValueError(f"enterprise_configuration_missing:scoringRanges.{name}")
    score = range_score(value, ranges, inverse=inverse)
    threshold = policy.minimum_factor_scores.get(name)
    if threshold is None:
        raise ValueError(f"enterprise_configuration_missing:minimumFactorScores.{name}")
    return QualityFactor(name, score, 1.0, score >= float(threshold), round(value, 4), float(threshold), immutable_mapping(diagnostics))

