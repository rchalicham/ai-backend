from __future__ import annotations

from .models import LearningConfidence


class ConfidenceCalibrationEngine:
    WEIGHTS = {
        "repeated_confirmations": 0.20,
        "historical_consistency": 0.20,
        "evidence_quality": 0.25,
        "human_approval": 0.20,
        "cross_document_agreement": 0.15,
    }

    def calibrate(
        self,
        current: float,
        *,
        repeated_confirmations: float,
        historical_consistency: float,
        evidence_quality: float,
        human_approval: float = 0.0,
        cross_document_agreement: float,
        history: tuple[tuple[str, float], ...] = (),
    ) -> LearningConfidence:
        values = {
            "repeated_confirmations": repeated_confirmations,
            "historical_consistency": historical_consistency,
            "evidence_quality": evidence_quality,
            "human_approval": human_approval,
            "cross_document_agreement": cross_document_agreement,
        }
        clamped = {key: max(0.0, min(1.0, float(value or 0.0))) for key, value in values.items()}
        support = sum(clamped[key] * weight for key, weight in self.WEIGHTS.items())
        proposed = max(0.0, min(1.0, current + (1.0 - current) * support * 0.5))
        return LearningConfidence(
            max(0.0, min(1.0, current)),
            round(proposed, 6),
            round(proposed - current, 6),
            **clamped,
            components=tuple((key, clamped[key]) for key in self.WEIGHTS),
            history=tuple(history),
        )

