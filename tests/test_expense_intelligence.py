import os
import sys
from dataclasses import FrozenInstanceError

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api.expense_routes import (
    anomalies, budget_summary, category_summary, expense_dashboard,
    expense_summary, merchant_summary, monthly_summary, recommendations,
    recurring_expenses, savings, yearly_summary,
)
from services.expense_intelligence import (
    BudgetDefinition, Expense, ExpenseCategory, ExpenseClassifier,
    ExpenseIntelligenceEngine, ExpenseIntelligenceLoader,
    ExpenseIntelligenceSerializer, ExpenseMerchant, ExpenseRepository,
    SpendingEngine,
)


def reasoning():
    return {
        "request": {"request_id": "reasoning-1"},
        "decision": {"confidence": {"overall": .94}},
        "evidence": [
            {"source_tool": "product_intelligence", "confidence": .9},
            {"source_tool": "enterprise_graph", "confidence": .92},
            {"source_tool": "cross_document_intelligence", "confidence": .93},
            {"source_tool": "enterprise_learning", "confidence": .88},
        ],
        "session": {"traces": [{"tool_name": "enterprise_graph", "status": "completed"}]},
    }


def sample_expenses():
    market = ExpenseMerchant("merchant:market", "Market", "Neighborhood Market", .95)
    discount = ExpenseMerchant("merchant:discount", "Discount Foods", "Discount Foods", .9)
    gym = ExpenseMerchant("merchant:gym", "Gym", "Community Gym", .9)
    return (
        Expense("e1", 80, "USD", "2026-01-05", ExpenseCategory.GROCERIES, market,
                "person:1", "household:1", ("milk",), ("receipt:1",), ("ev:1",),
                "reasoning-1", "grocery purchase", .95),
        Expense("e2", 70, "USD", "2026-02-05", ExpenseCategory.GROCERIES, market,
                "person:1", "household:1", ("eggs",), ("receipt:2",), ("ev:2",),
                "reasoning-1", "grocery purchase", .94),
        Expense("e3", 55, "USD", "2026-02-12", ExpenseCategory.GROCERIES, discount,
                "person:2", "household:1", ("bread",), ("receipt:3",), ("ev:3",),
                "reasoning-1", "grocery purchase", .9),
        Expense("e4", 30, "USD", "2026-01-01", ExpenseCategory.ENTERTAINMENT, gym,
                "person:1", "household:1", (), ("receipt:4",), ("ev:4",),
                "reasoning-1", "gym membership", .9),
        Expense("e5", 30, "USD", "2026-02-01", ExpenseCategory.ENTERTAINMENT, gym,
                "person:1", "household:1", (), ("receipt:5",), ("ev:5",),
                "reasoning-1", "gym membership", .9),
        Expense("e6", 600, "USD", "2026-02-20", ExpenseCategory.SHOPPING, market,
                "person:1", "household:1", (), ("receipt:6",), ("ev:6",),
                "reasoning-1", "large household purchase", .9),
    )


def test_category_classification_is_extensible():
    classifier = ExpenseClassifier()
    assert classifier.classify("weekly food", "Corner Grocery Market") == ExpenseCategory.GROCERIES
    custom = ExpenseClassifier(((ExpenseCategory.PETS, ("custom kennel",)),))
    assert custom.classify("Custom Kennel charge") == ExpenseCategory.PETS


def test_expense_engine_produces_explainable_business_intelligence():
    result = ExpenseIntelligenceEngine().analyze(
        reasoning(), sample_expenses(),
        (BudgetDefinition("budget:grocery", "Grocery budget", "monthly", 180, "Groceries"),),
    )
    assert result.summary.total == 865
    assert result.summary.monthly
    assert result.summary.yearly
    assert result.summary.merchants[0].rank == 1
    assert result.summary.categories[0].share > 0
    assert result.summary.households[0].household_id == "household:1"
    assert result.trends
    assert all(item.predictive is False for item in result.trends)
    assert result.recurring_expenses
    assert result.anomalies
    assert result.recommendations
    assert result.insights
    assert result.explanations[0].evidence_ids
    assert result.confidence.overall > .8
    assert result.forecast.enabled is False


def test_budget_tracking_is_observational_and_does_not_forecast():
    result = ExpenseIntelligenceEngine().analyze(
        reasoning(), sample_expenses(),
        (BudgetDefinition("budget:all", "Household", "monthly", 800),),
    )
    assert result.budgets[0].exceeded
    assert result.budgets[0].remaining == -65
    assert result.diagnostics.prediction_performed is False


def test_spending_dimensions_cover_person_household_store_and_product():
    engine = SpendingEngine()
    expenses = sample_expenses()
    assert dict(engine.person_spending(expenses))["person:1"] > 0
    assert dict(engine.household_spending(expenses))["household:1"] == 865
    assert dict(engine.store_spending(expenses))["merchant:market"] == 750
    assert dict(engine.product_spending(expenses))["milk"] == 80


def test_recurring_anomaly_savings_and_recommendations_keep_evidence():
    result = ExpenseIntelligenceEngine().analyze(reasoning(), sample_expenses())
    assert any(item.merchant_id == "merchant:gym" for item in result.recurring_expenses)
    assert any(item.anomaly_type == "large_purchase" for item in result.anomalies)
    assert any(item.recommendation_type == "cheaper_merchant"
               for item in result.recommendations)
    assert all(item.requires_human_decision for item in result.recommendations)
    assert any(item.evidence_ids for item in result.recommendations)


def test_models_are_immutable_and_repository_is_capability_owned():
    expense = sample_expenses()[0]
    with pytest.raises(FrozenInstanceError):
        expense.amount = 10
    repository = ExpenseRepository()
    assert repository.save(expense) == expense
    assert repository.load("e1") == expense
    with pytest.raises(ValueError, match="already_exists"):
        repository.save(expense)


def test_serialization_and_loading_preserve_expense_contract():
    expense = sample_expenses()[0]
    serializer = ExpenseIntelligenceSerializer()
    loader = ExpenseIntelligenceLoader()
    restored = loader.expense_from_json(serializer.to_json(expense))
    assert restored == expense


def api_payload():
    serializer = ExpenseIntelligenceSerializer()
    return {
        "enterprise_reasoning": reasoning(),
        "expenses": [serializer.to_dict(item) for item in sample_expenses()],
        "budgets": [{
            "budget_id": "budget:all", "name": "Household",
            "period": "monthly", "limit": 800,
        }],
    }


def test_dashboard_and_summary_apis():
    dashboard = expense_dashboard(api_payload())
    assert dashboard["schema_version"] == "expense-intelligence-result-v1"
    assert expense_summary(api_payload())["total"] == 865
    assert merchant_summary(api_payload())["merchants"]
    assert category_summary(api_payload())["categories"]
    assert monthly_summary(api_payload())["monthly"]
    assert yearly_summary(api_payload())["yearly"]
    assert budget_summary(api_payload())["budgets"]


def test_actionable_api_collections():
    assert recommendations(api_payload())["recommendations"]
    assert recurring_expenses(api_payload())["recurring_expenses"]
    assert anomalies(api_payload())["anomalies"]
    assert savings(api_payload())["savings"]


def test_rest_routes_are_registered_for_api_and_future_clients():
    from main import app

    paths = {route.path for route in app.routes}
    expected = {
        "/expense-intelligence/dashboard",
        "/api/expense-intelligence/summary",
        "/api/expense-intelligence/merchants",
        "/api/expense-intelligence/categories",
        "/api/expense-intelligence/monthly",
        "/api/expense-intelligence/yearly",
        "/api/expense-intelligence/budgets",
        "/api/expense-intelligence/savings",
        "/api/expense-intelligence/recommendations",
        "/api/expense-intelligence/recurring",
        "/api/expense-intelligence/anomalies",
    }
    assert expected <= paths


def test_platform_isolation_diagnostics_are_constitutional():
    result = ExpenseIntelligenceEngine().analyze(reasoning(), sample_expenses())
    diagnostics = result.diagnostics
    assert diagnostics.platform_services_modified is False
    assert diagnostics.parser_modified is False
    assert diagnostics.extraction_modified is False
    assert diagnostics.enterprise_knowledge_modified is False
    assert diagnostics.graph_modified is False
    assert diagnostics.learning_modified is False
    assert diagnostics.reasoning_modified is False
    assert diagnostics.automatic_correction_performed is False
