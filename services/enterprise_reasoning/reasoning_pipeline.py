from __future__ import annotations

from .decision_engine import ReasoningDecisionEngine
from .diagnostics import EnterpriseReasoningDiagnostics
from .explanation_engine import ReasoningExplanationEngine
from .hypothesis_engine import ReasoningHypothesisEngine
from .llm_adapter import LLMAdapter
from .orchestration_engine import ReasoningOrchestrationEngine
from .provenance_engine import ReasoningProvenanceEngine
from .reasoning_planner import ReasoningPlanner
from .reasoning_session import ReasoningSessionManager
from .response_builder import ReasoningResponseBuilder
from .validation_engine import ReasoningValidationEngine


class EnterpriseReasoningPipeline:
    def __init__(
        self, planner=None, orchestration=None, hypotheses=None, validation=None,
        decisions=None, explanations=None, provenance=None, llm=None,
        sessions=None, diagnostics=None, responses=None,
    ) -> None:
        self.planner = planner or ReasoningPlanner()
        self.orchestration = orchestration or ReasoningOrchestrationEngine()
        self.hypotheses = hypotheses or ReasoningHypothesisEngine()
        self.validation = validation or ReasoningValidationEngine()
        self.decisions = decisions or ReasoningDecisionEngine()
        self.explanations = explanations or ReasoningExplanationEngine()
        self.provenance = provenance or ReasoningProvenanceEngine()
        self.llm = llm or LLMAdapter()
        self.sessions = sessions or ReasoningSessionManager()
        self.diagnostics = diagnostics or EnterpriseReasoningDiagnostics()
        self.responses = responses or ReasoningResponseBuilder()

    def run(self, request, context):
        plan = self.planner.plan(request)
        evidence, traces = self.orchestration.execute(plan, context)
        hypotheses = self.hypotheses.generate(request, evidence)
        validated = self.validation.validate(hypotheses, evidence)
        decision = self.decisions.decide(validated, evidence)
        synthesis = self.llm.synthesize(request, decision, evidence) if decision else ""
        llm_used = bool(synthesis)
        session = self.sessions.create(request, plan, traces)
        explanation = self.explanations.explain(plan, evidence, validated, decision)
        provenance = self.provenance.build(evidence, plan, traces)
        diagnostics = self.diagnostics.create(
            len(evidence), len(validated), llm_used=llm_used,
            warnings=(
                ("LLM requested but no provider was configured",)
                if request.allow_llm and not self.llm.available else ()
            ),
        )
        return self.responses.build(
            request, session, evidence, validated, decision, explanation,
            provenance, diagnostics, synthesis,
        )
