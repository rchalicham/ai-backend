import os
import sys
from dataclasses import FrozenInstanceError

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.enterprise_reasoning import (
    EnterpriseReasoningEngine,
    EnterpriseReasoningLoader,
    EnterpriseReasoningSerializer,
    EnterpriseToolRegistry,
    ExecutionPlanner,
    GraphRetriever,
    LLMAdapter,
    PromptBuilder,
    QueryClassifier,
    QueryType,
    ReasoningContextBuilder,
    ReasoningPlanner,
    ReasoningRequest,
)
from services.enterprise_reasoning.reasoning_pipeline import EnterpriseReasoningPipeline


def context():
    return ReasoningContextBuilder().build(
        "context-1",
        constraint_result={
            "decision": {"confidence": {"overall": .92}},
            "diagnostics": {"affects_extraction": False},
        },
        product_intelligence={
            "enrichments": [{"canonical_product": "Milk", "confidence": {"overall": .9}}],
        },
        enterprise_graph={
            "graph": {
                "nodes": [
                    {"entity": {"entity_id": {"value": "product:milk"}, "entity_type": "Product"}},
                    {"entity": {"entity_id": {"value": "category:dairy"}, "entity_type": "Category"}},
                ],
                "edges": [{
                    "edge_id": "edge-1",
                    "source_id": {"value": "product:milk"},
                    "target_id": {"value": "category:dairy"},
                    "relationship_type": "HAS_CATEGORY",
                    "provenance": ["receipt:1"],
                    "confidence": {"normalized": .95},
                }],
            },
        },
        cross_document_intelligence={
            "context": {
                "current_document": {"document_id": "receipt-1"},
                "evidence": [{"provenance": ["graph:1"], "confidence": {"normalized": .9}}],
            },
        },
        enterprise_learning={
            "snapshot": {"proposals": [], "evidence": []},
            "diagnostics": {"production_knowledge_modified": False},
        },
    )


def test_query_classification_and_planning_are_deterministic():
    classifier = QueryClassifier()
    assert classifier.classify("Show the purchase timeline") == QueryType.TIMELINE
    assert classifier.classify("Which products are related?") == QueryType.KNOWLEDGE_GRAPH
    request = ReasoningRequest("request-1", "What is on this receipt?", QueryType.RECEIPT)
    first = ReasoningPlanner().plan(request)
    second = ReasoningPlanner().plan(request)
    assert first == second
    assert first.deterministic_first
    assert first.llm_required is False
    assert "enterprise_learning" in {step.tool_name for step in first.steps}
    assert len(ExecutionPlanner().waves(first)) >= 2


def test_reasoning_fuses_evidence_validates_hypotheses_and_explains_decision():
    request = EnterpriseReasoningEngine.request(
        "What is known about this receipt?", request_id="request-1",
    )
    response = EnterpriseReasoningEngine().reason(request, context())
    assert response.diagnostics.valid
    assert response.diagnostics.llm_used is False
    assert response.decision is not None
    assert response.decision.authoritative is False
    assert response.evidence
    assert response.hypotheses
    assert response.provenance
    assert response.session.plan.deterministic_first
    assert response.explanation.tool_selection
    assert all(trace.status == "completed" for trace in response.session.traces)


def test_graph_retrieval_supports_neighborhood_path_and_ontology():
    graph = EnterpriseReasoningSerializer().to_dict(context())["enterprise_graph"]
    retriever = GraphRetriever()
    nodes, edges = retriever.neighborhood(graph, "product:milk")
    assert len(nodes) == 2
    assert edges[0]["relationship_type"] == "HAS_CATEGORY"
    assert retriever.shortest_path(graph, "product:milk", "category:dairy") == (
        "product:milk", "category:dairy",
    )
    assert len(retriever.ontology_aware(graph, "Product")) == 1


class StubLLM:
    def __init__(self):
        self.prompts = []

    def synthesize(self, prompt, *, timeout_ms):
        self.prompts.append(prompt)
        return "Evidence-bounded synthesis."


def test_llm_is_optional_and_receives_only_validated_evidence():
    provider = StubLLM()
    pipeline = EnterpriseReasoningPipeline(llm=LLMAdapter(provider))
    engine = EnterpriseReasoningEngine(pipeline=pipeline)
    response = engine.reason(
        ReasoningRequest("request-llm", "Explain this receipt", allow_llm=True),
        context(),
    )
    assert response.natural_language_response == "Evidence-bounded synthesis."
    assert response.diagnostics.llm_used is True
    assert provider.prompts
    assert "approvedEvidence" in provider.prompts[0]
    assert "raw_ocr" not in provider.prompts[0]
    assert "parser_guess" not in provider.prompts[0]


def test_forbidden_sources_are_rejected_and_safe_failure_is_non_authoritative():
    with pytest.raises(ValueError, match="rejects_raw_ocr"):
        ReasoningContextBuilder().build("bad", raw_ocr="untrusted")
    invalid = type(context())(
        "bad", raw_ocr_present=True,
    )
    response = EnterpriseReasoningEngine().safe_reason(
        ReasoningRequest("bad", "question"), invalid,
    )
    assert not response.diagnostics.valid
    assert response.diagnostics.affects_extraction is False
    assert response.diagnostics.parser_authority_changed is False
    assert response.decision is None


def test_models_serialize_round_trip_and_are_immutable():
    response = EnterpriseReasoningEngine().reason(
        ReasoningRequest("request-1", "receipt question"), context(),
    )
    with pytest.raises(FrozenInstanceError):
        response.request.question = "changed"
    payload = EnterpriseReasoningSerializer().to_json(response)
    restored = EnterpriseReasoningLoader().response_from_json(payload)
    assert restored.request == response.request
    assert restored.decision == response.decision
    assert restored.session.plan == response.session.plan


def test_registry_contains_deterministic_and_future_tools():
    registry = EnterpriseToolRegistry()
    assert registry.get("enterprise_graph")[0].deterministic
    assert registry.get("llm")[0].deterministic is False
    assert registry.get("predictive_engine")[0].future
    assert registry.get("predictive_engine")[0].enabled is False


def test_prompt_builder_rejects_forbidden_payloads():
    response = EnterpriseReasoningEngine().reason(
        ReasoningRequest("request-1", "receipt question"), context(),
    )
    assert response.decision
    bad = response.evidence[0].__class__(
        "bad", "enterprise_graph", "bad", {"raw_ocr": "forbidden"}, .9, .9,
    )
    with pytest.raises(ValueError, match="forbidden_source"):
        PromptBuilder().build(response.request, response.decision, (bad,))
