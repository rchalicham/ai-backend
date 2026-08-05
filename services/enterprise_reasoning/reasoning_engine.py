from __future__ import annotations

import hashlib
from typing import Any

from .diagnostics import EnterpriseReasoningDiagnostics
from .models import (
    QueryType,
    ReasoningExplanation,
    ReasoningPlan,
    ReasoningRequest,
    ReasoningResponse,
    ReasoningSession,
)
from .query_classifier import QueryClassifier
from .reasoning_pipeline import EnterpriseReasoningPipeline


class EnterpriseReasoningEngine:
    """Evidence-first, non-authoritative enterprise reasoning orchestrator."""

    def __init__(self, classifier=None, pipeline=None, diagnostics=None) -> None:
        self.classifier = classifier or QueryClassifier()
        self.pipeline = pipeline or EnterpriseReasoningPipeline()
        self.diagnostics = diagnostics or EnterpriseReasoningDiagnostics()

    def reason(self, request: ReasoningRequest, context) -> ReasoningResponse:
        if context.raw_ocr_present or context.parser_guesses_present:
            raise ValueError("enterprise_reasoning_forbidden_source")
        classified = (
            self.classifier.classify(request.question)
            if request.query_type == QueryType.UNKNOWN else request.query_type
        )
        if classified != request.query_type:
            request = ReasoningRequest(
                request.request_id, request.question, classified, request.subject_ids,
                request.allow_llm, request.timeout_ms, request.timestamp, request.version,
            )
        return self.pipeline.run(request, context)

    def safe_reason(self, request: ReasoningRequest, context) -> ReasoningResponse:
        try:
            return self.reason(request, context)
        except Exception as exc:
            plan = ReasoningPlan(f"plan:failed:{request.request_id}", request.query_type, ())
            session = ReasoningSession(
                f"session:failed:{request.request_id}", request, plan, (), "failed",
            )
            return ReasoningResponse(
                request, session, (), (), None,
                ReasoningExplanation(
                    f"explanation:failed:{request.request_id}",
                    "Enterprise reasoning failed without affecting extraction.",
                ),
                (), self.diagnostics.failed(exc),
            )

    @staticmethod
    def request(question: str, *, request_id: str = "", allow_llm: bool = False):
        identity = request_id or hashlib.sha256(question.encode()).hexdigest()[:24]
        return ReasoningRequest(identity, question, allow_llm=allow_llm)
