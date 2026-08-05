from __future__ import annotations

import json

from .models import (
    QueryType, ReasoningConfidence, ReasoningDecision, ReasoningDiagnostics,
    ReasoningEvidence, ReasoningExplanation, ReasoningHypothesis, ReasoningPlan,
    ReasoningRequest, ReasoningResponse, ReasoningSession, ReasoningStep,
    ReasoningTrace,
)


class EnterpriseReasoningLoader:
    def response_from_json(self, payload: str) -> ReasoningResponse:
        return self.response_from_dict(json.loads(payload))

    def response_from_dict(self, data):
        request = self._request(data["request"])
        plan = self._plan(data["session"]["plan"])
        traces = tuple(ReasoningTrace(**x) for x in data["session"].get("traces", ()))
        session = ReasoningSession(
            data["session"]["session_id"], request, plan, traces,
            data["session"].get("status", "completed"),
            data["session"].get("started_at", ""), data["session"].get("completed_at", ""),
        )
        evidence = tuple(ReasoningEvidence(
            x["evidence_id"], x["source_tool"], x["evidence_type"], x.get("content"),
            x["confidence"], x["quality"], tuple(x.get("supporting_entities", ())),
            tuple(x.get("supporting_documents", ())), tuple(x.get("provenance", ())),
            x.get("version", "reasoning-evidence-v1"), x.get("timestamp", ""),
        ) for x in data.get("evidence", ()))
        hypotheses = tuple(ReasoningHypothesis(
            x["hypothesis_id"], x["statement"], tuple(x.get("evidence_ids", ())),
            x["confidence"], x.get("supported", True), tuple(x.get("rejection_reasons", ())),
        ) for x in data.get("hypotheses", ()))
        decision = self._decision(data.get("decision"))
        explanation_data = data["explanation"]
        explanation = ReasoningExplanation(
            explanation_data["explanation_id"], explanation_data["summary"],
            tuple(explanation_data.get("tool_selection", ())),
            tuple(explanation_data.get("trusted_evidence", ())),
            tuple(explanation_data.get("rejected_hypotheses", ())),
            explanation_data.get("confidence_method", ""),
        )
        diagnostics_data = dict(data.get("diagnostics", {}))
        diagnostics_data.pop("valid", None)
        for key in ("errors", "warnings", "information"):
            diagnostics_data[key] = tuple(diagnostics_data.get(key, ()))
        return ReasoningResponse(
            request, session, evidence, hypotheses, decision, explanation,
            tuple(data.get("provenance", ())), ReasoningDiagnostics(**diagnostics_data),
            data.get("natural_language_response", ""),
            data.get("schema_version", "enterprise-reasoning-response-v1"),
        )

    @staticmethod
    def _request(data):
        return ReasoningRequest(
            data["request_id"], data["question"], QueryType(data.get("query_type", "unknown")),
            tuple(data.get("subject_ids", ())), data.get("allow_llm", False),
            data.get("timeout_ms", 1000), data.get("timestamp", ""),
            data.get("version", "reasoning-request-v1"),
        )

    @staticmethod
    def _plan(data):
        return ReasoningPlan(
            data["plan_id"], QueryType(data["query_type"]),
            tuple(ReasoningStep(
                x["step_id"], x["operation"], x["tool_name"], tuple(x.get("depends_on", ())),
                x.get("condition", "always"), x.get("required", True),
                x.get("timeout_ms", 500), x.get("retry_count", 0),
            ) for x in data.get("steps", ())),
            tuple(data.get("rationale", ())), data.get("llm_required", False),
            data.get("deterministic_first", True),
            data.get("version", "reasoning-plan-v1"),
        )

    @staticmethod
    def _decision(data):
        if not data:
            return None
        c = data["confidence"]
        components = c.get("components", ())
        confidence = ReasoningConfidence(
            c["overall"], c.get("constraint", 0), c.get("graph", 0),
            c.get("learning", 0), c.get("evidence", 0), c.get("historical", 0),
            c.get("llm", 0),
            tuple(components.items()) if isinstance(components, dict)
            else tuple(tuple(x) for x in components),
        )
        return ReasoningDecision(
            data["decision_id"], data["selected_hypothesis_id"], data["answer"],
            confidence, tuple(data.get("evidence_ids", ())),
            tuple(data.get("rejected_hypothesis_ids", ())),
            data.get("authoritative", False),
        )
