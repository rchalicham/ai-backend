from __future__ import annotations

from .models import (
    LearningCandidate,
    LearningEvidence,
    LearningExplanation,
    LearningStatus,
)


class LearningExplanationEngine:
    def explain(
        self,
        candidate: LearningCandidate,
        evidence: tuple[LearningEvidence, ...],
        status: LearningStatus = LearningStatus.PENDING,
    ) -> LearningExplanation:
        relevant = tuple(item for item in evidence if item.evidence_id in candidate.evidence_ids)
        documents = tuple(dict.fromkeys(
            value for item in relevant for value in item.document_references
        ))
        entities = tuple(dict.fromkeys(
            value for item in relevant for value in item.entity_references
        ))
        observations = tuple(
            f"{item.source_type}: quality {item.quality:.3f}, confidence {item.confidence:.3f}"
            for item in relevant
        )
        return LearningExplanation(
            f"explanation:{candidate.candidate_id}",
            candidate.candidate_id,
            (
                f"Proposal exists because {candidate.confirmation_count} verified semantic "
                f"confirmations support {candidate.candidate_type}; it remains {status.value}."
            ),
            candidate.evidence_ids,
            documents,
            entities,
            observations,
            candidate.confidence.components,
            status,
        )

