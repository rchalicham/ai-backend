from __future__ import annotations

import hashlib

from .confidence_engine import ReasoningConfidenceEngine
from .models import ReasoningDecision, ReasoningEvidence, ReasoningHypothesis


class ReasoningDecisionEngine:
    def __init__(self, confidence_engine=None) -> None:
        self.confidence_engine = confidence_engine or ReasoningConfidenceEngine()

    def decide(
        self,
        hypotheses: tuple[ReasoningHypothesis, ...],
        evidence: tuple[ReasoningEvidence, ...],
    ) -> ReasoningDecision | None:
        supported = tuple(x for x in hypotheses if x.supported)
        if not supported:
            return None
        winner = max(
            supported,
            key=lambda x: (x.confidence, len(x.evidence_ids), x.hypothesis_id),
        )
        rejected = tuple(x.hypothesis_id for x in hypotheses if x.hypothesis_id != winner.hypothesis_id)
        token = hashlib.sha256(winner.hypothesis_id.encode()).hexdigest()[:24]
        return ReasoningDecision(
            f"decision:{token}", winner.hypothesis_id, winner.statement,
            self.confidence_engine.aggregate(evidence), winner.evidence_ids, rejected,
        )
