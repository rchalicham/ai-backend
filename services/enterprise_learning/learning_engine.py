from __future__ import annotations

from typing import Any

from services.cross_document_intelligence import IntelligenceResult

from .diagnostics import EnterpriseLearningDiagnostics
from .learning_pipeline import EnterpriseLearningPipeline
from .models import (
    EnterpriseLearningResult,
    LearningFeedback,
    LearningSnapshot,
)


class EnterpriseLearningEngine:
    """Generates governed pending proposals from normalized semantic evidence."""

    def __init__(
        self,
        pipeline: EnterpriseLearningPipeline | None = None,
        diagnostics: EnterpriseLearningDiagnostics | None = None,
    ) -> None:
        self.pipeline = pipeline or EnterpriseLearningPipeline()
        self.diagnostics = diagnostics or EnterpriseLearningDiagnostics()

    def evaluate(
        self,
        context: IntelligenceResult,
        *,
        feedback: tuple[LearningFeedback, ...] = (),
    ) -> EnterpriseLearningResult:
        snapshot, warnings = self.pipeline.run(context, feedback)
        return EnterpriseLearningResult(
            snapshot,
            self.diagnostics.create(snapshot.evidence, snapshot.proposals, warnings),
        )

    def safe_evaluate(
        self,
        context: IntelligenceResult | None,
        **kwargs: Any,
    ) -> EnterpriseLearningResult | None:
        if context is None:
            return None
        try:
            return self.evaluate(context, **kwargs)
        except Exception as exc:
            document_id = context.context.current_document.document_id
            return EnterpriseLearningResult(
                LearningSnapshot(f"enterprise-learning:{document_id}"),
                self.diagnostics.failed(exc),
            )
