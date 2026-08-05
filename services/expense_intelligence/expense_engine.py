from __future__ import annotations

from dataclasses import replace

from .anomaly_engine import ExpenseAnomalyEngine
from .budget_engine import ExpenseBudgetEngine
from .category_engine import ExpenseCategoryEngine
from .confidence_engine import ExpenseConfidenceEngine
from .diagnostics import ExpenseIntelligenceDiagnostics
from .explanation_engine import ExpenseExplanationEngine
from .insights_engine import ExpenseInsightsEngine
from .merchant_engine import MerchantExpenseEngine
from .models import ExpenseIntelligenceResult, ExpenseSummary
from .recommendation_engine import ExpenseRecommendationEngine
from .recurring_engine import RecurringExpenseEngine
from .savings_engine import ExpenseSavingsEngine
from .spending_engine import SpendingEngine
from .trend_engine import ExpenseTrendEngine


class ExpenseIntelligenceEngine:
    """Business capability consuming platform contracts without modifying them."""

    def __init__(
        self, classifier=None, spending=None, merchants=None, trends=None,
        budgets=None, recurring=None, anomalies=None, savings=None,
        recommendations=None, insights=None, explanations=None, confidence=None,
        diagnostics=None,
    ) -> None:
        self.classifier = classifier or ExpenseCategoryEngine()
        self.spending = spending or SpendingEngine()
        self.merchants = merchants or MerchantExpenseEngine()
        self.trends = trends or ExpenseTrendEngine()
        self.budgets = budgets or ExpenseBudgetEngine()
        self.recurring = recurring or RecurringExpenseEngine()
        self.anomalies = anomalies or ExpenseAnomalyEngine()
        self.savings = savings or ExpenseSavingsEngine()
        self.recommendations = recommendations or ExpenseRecommendationEngine()
        self.insights = insights or ExpenseInsightsEngine()
        self.explanations = explanations or ExpenseExplanationEngine()
        self.confidence = confidence or ExpenseConfidenceEngine()
        self.diagnostics = diagnostics or ExpenseIntelligenceDiagnostics()

    def analyze(self, reasoning, expenses=(), budget_definitions=()):
        reasoning_payload = reasoning or {}
        normalized = tuple(
            replace(item, category=self.classifier.classify(item)) for item in expenses
        )
        summary = self.spending.summarize(normalized)
        summary = replace(summary, merchants=self.merchants.summarize(normalized))
        confidence = self.confidence.aggregate(normalized, reasoning_payload)
        trends = self.trends.analyze(normalized)
        budgets = self.budgets.track(normalized, tuple(budget_definitions))
        recurring = self.recurring.detect(normalized)
        anomalies = self.anomalies.detect(normalized)
        savings = self.savings.identify(normalized)
        recommendations = self.recommendations.generate(
            budgets=budgets, recurring=recurring, anomalies=anomalies, savings=savings,
        )
        insights = self.insights.generate(summary, normalized, confidence.overall)
        explanations = (
            self.explanations.for_summary(summary, normalized, reasoning_payload),
            *(self.explanations.for_insight(
                item.insight_type, item.title, item.value, normalized, item.confidence,
            ) for item in insights),
        )
        return ExpenseIntelligenceResult(
            normalized, summary, trends, insights, recommendations, budgets,
            recurring, anomalies, tuple(explanations), confidence,
            diagnostics=self.diagnostics.create(normalized),
        )

    def safe_analyze(self, reasoning, expenses=(), budget_definitions=()):
        try:
            return self.analyze(reasoning, tuple(expenses), tuple(budget_definitions))
        except Exception as exc:
            return ExpenseIntelligenceResult(
                (), ExpenseSummary("expense-summary:failed", 0, 0, 0, "USD", "", ""),
                diagnostics=self.diagnostics.failed(exc),
            )
