from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def freeze_value(value: Any) -> Any:
    if isinstance(value, dict):
        return tuple((str(key), freeze_value(item)) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return tuple(freeze_value(item) for item in value)
    if isinstance(value, set):
        return tuple(sorted((freeze_value(item) for item in value), key=str))
    return value


class ExpenseCategory(str, Enum):
    GROCERIES = "Groceries"
    RESTAURANTS = "Restaurants"
    FUEL = "Fuel"
    TRAVEL = "Travel"
    HEALTHCARE = "Healthcare"
    PHARMACY = "Pharmacy"
    INSURANCE = "Insurance"
    MORTGAGE = "Mortgage"
    RENT = "Rent"
    UTILITIES = "Utilities"
    ENTERTAINMENT = "Entertainment"
    EDUCATION = "Education"
    SHOPPING = "Shopping"
    AUTOMOTIVE = "Automotive"
    HOUSEHOLD = "Household"
    PETS = "Pets"
    ELECTRONICS = "Electronics"
    TAXES = "Taxes"
    BUSINESS = "Business"
    UNKNOWN = "Unknown"


@dataclass(frozen=True, slots=True)
class ExpenseMerchant:
    merchant_id: str
    name: str
    canonical_name: str = ""
    confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class Expense:
    expense_id: str
    amount: float
    currency: str
    occurred_at: str
    category: ExpenseCategory | str = ExpenseCategory.UNKNOWN
    merchant: ExpenseMerchant | None = None
    person_id: str = ""
    household_id: str = ""
    product_ids: tuple[str, ...] = ()
    document_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    reasoning_request_id: str = ""
    description: str = ""
    confidence: float = 0.0
    metadata: Any = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", freeze_value(self.metadata))


@dataclass(frozen=True, slots=True)
class ExpenseTrend:
    trend_id: str
    trend_type: str
    subject: str
    direction: str
    current_value: float
    previous_value: float
    change_percent: float
    period: str
    evidence_ids: tuple[str, ...] = ()
    confidence: float = 0.0
    predictive: bool = False


@dataclass(frozen=True, slots=True)
class ExpenseInsight:
    insight_id: str
    insight_type: str
    title: str
    value: float | str
    period: str
    explanation_id: str
    evidence_ids: tuple[str, ...] = ()
    confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class ExpenseRecommendation:
    recommendation_id: str
    recommendation_type: str
    title: str
    description: str
    estimated_savings: float
    currency: str
    evidence_ids: tuple[str, ...]
    confidence: float
    requires_human_decision: bool = True


@dataclass(frozen=True, slots=True)
class ExpenseBudget:
    budget_id: str
    name: str
    period: str
    limit: float
    spent: float
    remaining: float
    utilization: float
    category: ExpenseCategory | str = ExpenseCategory.UNKNOWN
    exceeded: bool = False
    warning: bool = False
    currency: str = "USD"


@dataclass(frozen=True, slots=True)
class ExpenseForecast:
    forecast_id: str
    enabled: bool = False
    reason: str = "Forecasting is outside the current Expense Intelligence scope."


@dataclass(frozen=True, slots=True)
class ExpenseAnomaly:
    anomaly_id: str
    anomaly_type: str
    severity: str
    description: str
    expense_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    confidence: float
    automatic_correction: bool = False


@dataclass(frozen=True, slots=True)
class RecurringExpense:
    recurring_id: str
    merchant_id: str
    category: ExpenseCategory | str
    cadence: str
    average_amount: float
    occurrences: int
    expense_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    confidence: float


@dataclass(frozen=True, slots=True)
class ExpenseConfidence:
    overall: float
    product: float = 0.0
    knowledge: float = 0.0
    cross_document: float = 0.0
    reasoning: float = 0.0
    learning: float = 0.0
    expense: float = 0.0
    components: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True, slots=True)
class ExpenseExplanation:
    explanation_id: str
    subject_id: str
    summary: str
    why: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    document_ids: tuple[str, ...] = ()
    reasoning_steps: tuple[str, ...] = ()
    confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class ExpenseDiagnostics:
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    information: tuple[str, ...] = ()
    business_capability: bool = True
    platform_services_modified: bool = False
    parser_modified: bool = False
    extraction_modified: bool = False
    enterprise_knowledge_modified: bool = False
    graph_modified: bool = False
    learning_modified: bool = False
    reasoning_modified: bool = False
    prediction_performed: bool = False
    automatic_correction_performed: bool = False

    @property
    def valid(self) -> bool:
        return not self.errors


@dataclass(frozen=True, slots=True)
class MonthlySummary:
    month: str
    total: float
    transaction_count: int
    average: float
    currency: str
    category_totals: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True, slots=True)
class YearlySummary:
    year: int
    total: float
    transaction_count: int
    average_monthly: float
    currency: str
    monthly_totals: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True, slots=True)
class MerchantSummary:
    merchant_id: str
    merchant_name: str
    total: float
    frequency: int
    average_spend: float
    rank: int
    trend_percent: float = 0.0
    loyalty_score: float = 0.0
    currency: str = "USD"


@dataclass(frozen=True, slots=True)
class CategorySummary:
    category: ExpenseCategory | str
    total: float
    frequency: int
    average_spend: float
    share: float
    growth_percent: float = 0.0
    currency: str = "USD"


@dataclass(frozen=True, slots=True)
class HouseholdSummary:
    household_id: str
    total: float
    transaction_count: int
    person_totals: tuple[tuple[str, float], ...] = ()
    currency: str = "USD"


@dataclass(frozen=True, slots=True)
class ExpenseSummary:
    summary_id: str
    total: float
    transaction_count: int
    average: float
    currency: str
    period_start: str
    period_end: str
    monthly: tuple[MonthlySummary, ...] = ()
    yearly: tuple[YearlySummary, ...] = ()
    merchants: tuple[MerchantSummary, ...] = ()
    categories: tuple[CategorySummary, ...] = ()
    households: tuple[HouseholdSummary, ...] = ()


@dataclass(frozen=True, slots=True)
class ExpenseIntelligenceResult:
    expenses: tuple[Expense, ...]
    summary: ExpenseSummary
    trends: tuple[ExpenseTrend, ...] = ()
    insights: tuple[ExpenseInsight, ...] = ()
    recommendations: tuple[ExpenseRecommendation, ...] = ()
    budgets: tuple[ExpenseBudget, ...] = ()
    recurring_expenses: tuple[RecurringExpense, ...] = ()
    anomalies: tuple[ExpenseAnomaly, ...] = ()
    explanations: tuple[ExpenseExplanation, ...] = ()
    confidence: ExpenseConfidence = field(default_factory=lambda: ExpenseConfidence(0.0))
    forecast: ExpenseForecast = field(default_factory=lambda: ExpenseForecast("forecast:disabled"))
    diagnostics: ExpenseDiagnostics = field(default_factory=ExpenseDiagnostics)
    generated_at: str = field(default_factory=utc_now)
    schema_version: str = "expense-intelligence-result-v1"
