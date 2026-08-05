from .confidence_engine import ProcessingConfidenceEngine
from .diagnostics import processing_diagnostics
from .explanation_engine import ProcessingExplanationEngine
from .guidance_engine import GuidanceEngine
from .models import ProcessingSummary, ReceiptProcessingStatus, frozen_map
from .recommendation_engine import ProcessingRecommendationEngine
from .recoverability_engine import RecoverabilityEngine
from .stage_engine import ProcessingStageEngine
from .status_engine import ProcessingStatusEngine


class ReceiptProcessingExperienceEngine:
    def __init__(self, configuration_loader):
        self.configuration_loader = configuration_loader
        self.status = ProcessingStatusEngine()
        self.stages = ProcessingStageEngine()
        self.recoverability = RecoverabilityEngine()
        self.recommendations = ProcessingRecommendationEngine()
        self.explanations = ProcessingExplanationEngine()
        self.confidence = ProcessingConfidenceEngine()
        self.guidance = GuidanceEngine()

    def build(self, enterprise_context):
        context = dict(enterprise_context or {})
        configuration = self.configuration_loader.load()
        state = self.status.resolve(context, configuration)
        explanation = self.explanations.explain(context, state, configuration)
        recoverability = self.recoverability.resolve(context, state, configuration)
        recommendations = self.recommendations.build(context, state, configuration)
        timeline = self.stages.build(context, type("Status", (), {"state": state})(), configuration)
        confidence = self.confidence.calculate(context)
        family = ((context.get("documentFamilyContext") or {}).get("activation") or {}).get("family", "")
        quality_score = (context.get("receiptQuality") or {}).get("overallScore")
        review_decision = ((context.get("documentReview") or {}).get("decision") or {})
        human_review = review_decision.get("requiresHumanReview")
        if human_review is None:
            human_review = bool((context.get("receiptAgent") or {}).get("humanReview", {}).get("required"))
        summary = ProcessingSummary(timeline.current_stage, state.key, quality_score, str(family or ""), bool(context.get("businessProjection")), bool(human_review), recoverability, recommendations, self.guidance.business_summary(state, explanation, recoverability))
        return ReceiptProcessingStatus(state, summary, timeline, explanation, confidence, processing_diagnostics(context), configuration["configurationId"], str(configuration["version"]), frozen_map(configuration["actions"]), frozen_map(configuration["labels"]))
