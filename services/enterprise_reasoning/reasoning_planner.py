from __future__ import annotations

import hashlib

from .models import QueryType, ReasoningPlan, ReasoningRequest, ReasoningStep


class ReasoningPlanner:
    TOOL_MAP = {
        QueryType.RECEIPT: (
            "constraint_solver", "product_intelligence", "enterprise_graph",
            "cross_document_intelligence", "enterprise_learning",
        ),
        QueryType.PRODUCT: ("product_intelligence", "enterprise_graph"),
        QueryType.MERCHANT: ("merchant_knowledge", "enterprise_graph"),
        QueryType.TIMELINE: ("cross_document_intelligence", "enterprise_graph"),
        QueryType.BUDGET: ("cross_document_intelligence", "enterprise_graph"),
        QueryType.HEALTH: ("product_intelligence", "enterprise_graph"),
        QueryType.EXPENSE: ("constraint_solver", "cross_document_intelligence"),
        QueryType.CROSS_DOCUMENT: ("cross_document_intelligence", "enterprise_graph"),
        QueryType.KNOWLEDGE_GRAPH: ("enterprise_graph",),
        QueryType.ANALYTICS: ("cross_document_intelligence",),
        QueryType.UNKNOWN: ("enterprise_graph", "cross_document_intelligence"),
    }

    def plan(self, request: ReasoningRequest) -> ReasoningPlan:
        tools = self.TOOL_MAP[request.query_type]
        steps = tuple(
            ReasoningStep(f"step-{index + 1}", "retrieve_evidence", tool)
            for index, tool in enumerate(tools)
        )
        validate_depends = tuple(step.step_id for step in steps)
        steps += (
            ReasoningStep("step-fuse", "fuse_evidence", "evidence_fusion", validate_depends),
            ReasoningStep("step-hypotheses", "generate_hypotheses", "hypothesis_engine", ("step-fuse",)),
            ReasoningStep("step-validate", "validate_hypotheses", "validation_engine", ("step-hypotheses",)),
            ReasoningStep("step-decide", "select_decision", "decision_engine", ("step-validate",)),
        )
        if request.allow_llm:
            steps += (ReasoningStep(
                "step-synthesize", "synthesize_language", "llm",
                ("step-decide",), "validated_decision_exists", False,
            ),)
        token = hashlib.sha256(
            f"{request.request_id}|{request.query_type.value}|{tools}".encode(),
        ).hexdigest()[:24]
        return ReasoningPlan(
            f"plan:{token}", request.query_type, steps,
            tuple(f"{tool} selected for {request.query_type.value}" for tool in tools),
            llm_required=False,
        )
