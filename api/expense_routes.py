from __future__ import annotations

from fastapi import APIRouter, HTTPException

from services.expense_intelligence import (
    BudgetDefinition,
    ExpenseIntelligenceEngine,
    ExpenseIntelligenceLoader,
    ExpenseIntelligenceSerializer,
)


router = APIRouter(prefix="/expense-intelligence", tags=["expense-intelligence"])
engine = ExpenseIntelligenceEngine()
loader = ExpenseIntelligenceLoader()
serializer = ExpenseIntelligenceSerializer()


def analyze_payload(payload: dict):
    reasoning = payload.get("enterprise_reasoning")
    if not isinstance(reasoning, dict):
        raise HTTPException(
            status_code=400,
            detail="enterprise_reasoning is required; raw parser or OCR input is not accepted.",
        )
    expenses = loader.expenses_from_dict(payload.get("expenses", ()))
    budgets = tuple(BudgetDefinition(**item) for item in payload.get("budgets", ()))
    return engine.analyze(reasoning, expenses, budgets)


def attach_expense_intelligence(orchestration_result: dict) -> dict:
    """Composition-root integration; the platform orchestrator remains unchanged."""
    result = dict(orchestration_result)
    reasoning = result.get("enterpriseReasoning")
    if isinstance(reasoning, dict):
        expense_result = engine.safe_analyze(reasoning)
        result["expenseIntelligence"] = serializer.to_dict(expense_result)
    return result


@router.post("/dashboard")
def expense_dashboard(payload: dict):
    return serializer.to_dict(analyze_payload(payload))


@router.post("/summary")
def expense_summary(payload: dict):
    return serializer.to_dict(analyze_payload(payload).summary)


@router.post("/merchants")
def merchant_summary(payload: dict):
    result = analyze_payload(payload)
    return {"merchants": [serializer.to_dict(item) for item in result.summary.merchants]}


@router.post("/categories")
def category_summary(payload: dict):
    result = analyze_payload(payload)
    return {"categories": [serializer.to_dict(item) for item in result.summary.categories]}


@router.post("/monthly")
def monthly_summary(payload: dict):
    result = analyze_payload(payload)
    return {"monthly": [serializer.to_dict(item) for item in result.summary.monthly]}


@router.post("/yearly")
def yearly_summary(payload: dict):
    result = analyze_payload(payload)
    return {"yearly": [serializer.to_dict(item) for item in result.summary.yearly]}


@router.post("/budgets")
def budget_summary(payload: dict):
    result = analyze_payload(payload)
    return {"budgets": [serializer.to_dict(item) for item in result.budgets]}


@router.post("/savings")
def savings(payload: dict):
    result = analyze_payload(payload)
    values = tuple(
        item for item in result.recommendations
        if item.recommendation_type in {"cheaper_merchant", "savings"}
    )
    return {"savings": [serializer.to_dict(item) for item in values]}


@router.post("/recommendations")
def recommendations(payload: dict):
    result = analyze_payload(payload)
    return {"recommendations": [serializer.to_dict(item) for item in result.recommendations]}


@router.post("/recurring")
def recurring_expenses(payload: dict):
    result = analyze_payload(payload)
    return {"recurring_expenses": [
        serializer.to_dict(item) for item in result.recurring_expenses
    ]}


@router.post("/anomalies")
def anomalies(payload: dict):
    result = analyze_payload(payload)
    return {"anomalies": [serializer.to_dict(item) for item in result.anomalies]}
