from __future__ import annotations

import hashlib

from services.cross_document_intelligence import IntelligenceResult

from .alias_learning import AliasLearningEngine
from .confidence_calibration import ConfidenceCalibrationEngine
from .merchant_learning import MerchantLearningEngine
from .models import LearningCandidate, LearningEvidence, LearningFeedback
from .pattern_learning import PatternLearningEngine
from .relationship_learning import RelationshipLearningEngine
from .taxonomy_learning import TaxonomyLearningEngine


class LearningCandidateGenerator:
    def __init__(
        self,
        alias_learning: AliasLearningEngine | None = None,
        taxonomy_learning: TaxonomyLearningEngine | None = None,
        relationship_learning: RelationshipLearningEngine | None = None,
        merchant_learning: MerchantLearningEngine | None = None,
        pattern_learning: PatternLearningEngine | None = None,
        calibration: ConfidenceCalibrationEngine | None = None,
    ) -> None:
        self.alias_learning = alias_learning or AliasLearningEngine()
        self.taxonomy_learning = taxonomy_learning or TaxonomyLearningEngine()
        self.relationship_learning = relationship_learning or RelationshipLearningEngine()
        self.merchant_learning = merchant_learning or MerchantLearningEngine()
        self.pattern_learning = pattern_learning or PatternLearningEngine()
        self.calibration = calibration or ConfidenceCalibrationEngine()

    def generate(
        self,
        context: IntelligenceResult,
        evidence: tuple[LearningEvidence, ...],
        feedback: tuple[LearningFeedback, ...] = (),
    ) -> tuple[LearningCandidate, ...]:
        drafts = (
            *self.alias_learning.suggest(context),
            *self.taxonomy_learning.suggest(context),
            *self.relationship_learning.suggest(context),
            *self.merchant_learning.suggest(context),
            *self.pattern_learning.suggest(context),
            *self._graph_candidates(context),
            *self._feedback_candidates(feedback),
        )
        by_id: dict[str, LearningCandidate] = {}
        evidence_by_id = {item.evidence_id: item for item in evidence}
        for draft in drafts:
            relevant = tuple(
                evidence_by_id[item]
                for item in draft.get("evidence_ids", ())
                if item in evidence_by_id and evidence_by_id[item].verified
            )
            if not relevant:
                continue
            quality = sum(item.quality for item in relevant) / len(relevant)
            agreement = sum(item.confidence for item in relevant) / len(relevant)
            current = float(draft.get("current_confidence", 0.0) or 0.0)
            confirmation_count = int(draft.get("confirmation_count", len(relevant)))
            confidence = self.calibration.calibrate(
                current,
                repeated_confirmations=min(1.0, confirmation_count / 3),
                historical_consistency=agreement,
                evidence_quality=quality,
                human_approval=1.0 if draft["source"] == "approved_human_correction" else 0.0,
                cross_document_agreement=agreement,
                history=(("upstream", current),),
            )
            candidate_id = self._id(
                draft["candidate_type"],
                draft["subject_id"],
                repr(draft["proposed_value"]),
            )
            by_id[candidate_id] = LearningCandidate(
                candidate_id,
                draft["candidate_type"],
                draft["subject_id"],
                draft["proposed_value"],
                tuple(item.evidence_id for item in relevant),
                draft["source"],
                confidence,
                confirmation_count,
                previous_value=draft.get("previous_value"),
            )
        return tuple(by_id[key] for key in sorted(by_id))

    def _graph_candidates(self, context: IntelligenceResult):
        return tuple(
            {
                "candidate_type": "knowledge_graph_improvement",
                "subject_id": correlation.correlation_id,
                "proposed_value": {
                    "correlationType": correlation.correlation_type,
                    "entityIds": correlation.entity_ids,
                },
                "source": "verified_graph_update",
                "confirmation_count": len(correlation.document_references),
                "current_confidence": correlation.confidence.normalized,
                "evidence_ids": correlation.evidence_ids,
            }
            for correlation in context.context.correlations
            if len(correlation.document_references) >= 2
            and correlation.confidence.normalized >= 0.8
        )

    @staticmethod
    def _feedback_candidates(feedback: tuple[LearningFeedback, ...]):
        supported = {
            "product_alias": "new_product_alias",
            "merchant_alias": "new_merchant_alias",
            "category_assignment": "new_category",
            "relationship": "new_relationship",
            "confidence": "confidence_adjustment",
            "taxonomy": "taxonomy_improvement",
            "grammar": "grammar_improvement_suggestion",
            "constraint": "constraint_improvement_suggestion",
            "knowledge_graph": "knowledge_graph_improvement",
        }
        return tuple(
            {
                "candidate_type": supported.get(item.feedback_type, "knowledge_improvement"),
                "subject_id": item.subject_id,
                "proposed_value": item.proposed_value,
                "previous_value": item.previous_value,
                "source": "approved_human_correction",
                "confirmation_count": 1,
                "current_confidence": 0.8,
                "evidence_ids": (f"feedback-evidence:{item.feedback_id}",),
            }
            for item in feedback if item.verified
        )

    @staticmethod
    def _id(*values: str) -> str:
        return hashlib.sha256("|".join(values).encode("utf-8")).hexdigest()[:24]

