from __future__ import annotations

import hashlib

from services.cross_document_intelligence import IntelligenceResult

from .models import LearningEvent, LearningEvidence, LearningFeedback


class LearningEventProcessor:
    """Accepts normalized verified semantic evidence only."""

    def process(
        self,
        context: IntelligenceResult,
        feedback: tuple[LearningFeedback, ...] = (),
    ) -> tuple[tuple[LearningEvent, ...], tuple[LearningEvidence, ...]]:
        events: list[LearningEvent] = []
        evidence: list[LearningEvidence] = []
        for item in context.context.evidence:
            verified = (
                len(item.supporting_documents) >= 2
                and item.confidence.normalized >= 0.8
            )
            source_type = "cross_document_confirmation"
            evidence.append(LearningEvidence(
                item.evidence_id,
                source_type,
                verified,
                item.confidence.evidence or item.confidence.normalized,
                item.confidence.normalized,
                tuple(value.document_id for value in item.supporting_documents),
                item.source_entity_ids,
                item.evidence_references,
                item.timestamp,
                item.version,
            ))
            events.append(LearningEvent(
                self._id("semantic_evidence", item.evidence_id),
                "semantic_evidence_observed",
                "cross_document_intelligence",
                "system",
                (item.evidence_id,),
                {"verified": verified, "reason": item.reason},
            ))
        for pattern in context.context.patterns:
            evidence_id = f"pattern-evidence:{pattern.pattern_id}"
            verified = pattern.occurrences >= 2 and pattern.confidence.normalized >= 0.8
            evidence.append(LearningEvidence(
                evidence_id,
                "repeated_evidence",
                verified,
                pattern.confidence.evidence or pattern.confidence.normalized,
                pattern.confidence.normalized,
                tuple(value.document_id for value in pattern.document_references),
                pattern.subject_entity_ids,
                pattern.evidence_ids,
            ))
            events.append(LearningEvent(
                self._id("pattern", pattern.pattern_id),
                "historical_pattern_observed",
                "cross_document_intelligence",
                "system",
                (evidence_id,),
                {"patternType": pattern.pattern_type, "predictive": False},
            ))
        for item in feedback:
            events.append(LearningEvent(
                self._id("feedback", item.feedback_id),
                "feedback_submitted",
                "human_feedback",
                item.actor_id,
                item.evidence_ids,
                {
                    "feedbackId": item.feedback_id,
                    "verified": item.verified,
                    "actorRole": item.actor_role,
                },
                item.timestamp,
            ))
            if item.verified:
                evidence.append(LearningEvidence(
                    f"feedback-evidence:{item.feedback_id}",
                    "approved_human_correction",
                    True,
                    1.0,
                    1.0,
                    (),
                    (item.subject_id,),
                    (*item.evidence_ids, *item.provenance),
                    item.timestamp,
                ))
        return tuple(events), tuple(evidence)

    @staticmethod
    def _id(*values: str) -> str:
        return hashlib.sha256("|".join(values).encode("utf-8")).hexdigest()[:24]

