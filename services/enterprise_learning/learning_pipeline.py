from __future__ import annotations

import hashlib

from services.cross_document_intelligence import IntelligenceResult

from .audit_engine import LearningAuditEngine
from .explanation_engine import LearningExplanationEngine
from .governance_engine import LearningGovernanceEngine
from .learning_candidate_generator import LearningCandidateGenerator
from .learning_event_processor import LearningEventProcessor
from .models import (
    LearningFeedback,
    LearningProposal,
    LearningSnapshot,
)
from .quality_engine import LearningQualityEngine


class EnterpriseLearningPipeline:
    def __init__(
        self,
        event_processor: LearningEventProcessor | None = None,
        candidate_generator: LearningCandidateGenerator | None = None,
        quality_engine: LearningQualityEngine | None = None,
        explanation_engine: LearningExplanationEngine | None = None,
        governance_engine: LearningGovernanceEngine | None = None,
        audit_engine: LearningAuditEngine | None = None,
    ) -> None:
        self.event_processor = event_processor or LearningEventProcessor()
        self.candidate_generator = candidate_generator or LearningCandidateGenerator()
        self.quality_engine = quality_engine or LearningQualityEngine()
        self.explanation_engine = explanation_engine or LearningExplanationEngine()
        self.governance_engine = governance_engine or LearningGovernanceEngine()
        self.audit_engine = audit_engine or LearningAuditEngine()

    def run(
        self,
        context: IntelligenceResult,
        feedback: tuple[LearningFeedback, ...] = (),
        existing: tuple[LearningProposal, ...] = (),
    ) -> tuple[LearningSnapshot, tuple[str, ...]]:
        events, evidence = self.event_processor.process(context, feedback)
        candidates = self.candidate_generator.generate(context, evidence, feedback)
        proposals = tuple(
            LearningProposal(
                "proposal:" + candidate.candidate_id,
                candidate,
                self.quality_engine.assess(candidate, evidence),
                self.explanation_engine.explain(candidate, evidence),
            )
            for candidate in candidates
        )
        governed, warnings = self.governance_engine.govern(
            proposals, evidence, existing,
        )
        audit = tuple(self.audit_engine.proposal_created(item) for item in governed)
        document_id = context.context.current_document.document_id
        snapshot_id = "enterprise-learning:" + hashlib.sha256(
            document_id.encode(),
        ).hexdigest()[:24]
        return (
            LearningSnapshot(
                snapshot_id,
                events,
                feedback,
                evidence,
                governed,
                audit=audit,
            ),
            warnings,
        )
