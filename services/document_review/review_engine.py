from .diagnostics import review_diagnostics
from .explanation_engine import DocumentReviewExplanationEngine
from .models import DocumentReviewResult
from .policy_registry import DocumentFamilyReviewPolicyRegistry
from .quality_filter import ResolvedQualityFilter
from .recommendation_engine import DocumentReviewRecommendationEngine
from .review_confidence import ReviewConfidenceEngine
from .review_decision import ReviewDecisionEngine
from .semantic_completeness import SemanticCompletenessEngine


class DocumentFamilyReviewEngine:
    def __init__(self, configuration_loader):
        self.loader = configuration_loader
        self.completeness = SemanticCompletenessEngine()
        self.quality = ResolvedQualityFilter()
        self.confidence = ReviewConfidenceEngine()
        self.decisions = ReviewDecisionEngine()
        self.recommendations = DocumentReviewRecommendationEngine()
        self.explanations = DocumentReviewExplanationEngine()

    def review(self, enterprise_context):
        context = dict(enterprise_context or {})
        configuration = self.loader.load()
        family = str((((context.get("documentFamilyContext") or {}).get("activation") or {}).get("family")) or "unknown")
        policy = DocumentFamilyReviewPolicyRegistry(configuration).resolve(family)
        completeness = self.completeness.evaluate(context, policy, configuration)
        quality = self.quality.resolve(context, configuration)
        confidence = self.confidence.calculate(context, completeness, quality, configuration)
        decision = self.decisions.decide(policy, completeness, quality, confidence, configuration)
        recommendations = self.recommendations.build(decision, completeness, quality, configuration)
        explanation = self.explanations.explain(family, decision, completeness, quality, configuration)
        return DocumentReviewResult(
            family, policy, completeness, quality, confidence, decision, recommendations,
            explanation, review_diagnostics(context), configuration["configurationId"], str(configuration["version"]),
        )
