from __future__ import annotations

from .models import LearningCandidate, LearningEvidence, LearningQuality


class LearningQualityEngine:
    def assess(
        self,
        candidate: LearningCandidate,
        evidence: tuple[LearningEvidence, ...],
    ) -> LearningQuality:
        relevant = tuple(item for item in evidence if item.evidence_id in candidate.evidence_ids)
        verified = tuple(item for item in relevant if item.verified)
        low = sum(item.confidence < 0.8 or item.quality < 0.8 for item in relevant)
        score = (
            sum(item.quality * item.confidence for item in verified) / len(verified)
            if verified else 0.0
        )
        coverage = len(verified) / len(relevant) if relevant else 0.0
        acceptable = (
            (
                candidate.confirmation_count >= 2
                or candidate.source == "approved_human_correction"
            )
            and bool(verified)
            and score >= 0.8
            and low == 0
        )
        reasons = []
        if candidate.confirmation_count < 2 and candidate.source != "approved_human_correction":
            reasons.append("minimum confirmations not met")
        if not verified:
            reasons.append("no verified semantic evidence")
        if score < 0.8:
            reasons.append("evidence quality below threshold")
        if low:
            reasons.append("low-confidence evidence excluded")
        return LearningQuality(
            round(score, 6),
            candidate.confirmation_count,
            round(coverage, 6),
            0,
            low,
            acceptable,
            tuple(reasons),
        )
