from __future__ import annotations

from dataclasses import dataclass

from .models import ExpenseBudget


@dataclass(frozen=True, slots=True)
class BudgetDefinition:
    budget_id: str
    name: str
    period: str
    limit: float
    category: str = "Unknown"
    currency: str = "USD"
    warning_threshold: float = .8


class ExpenseBudgetEngine:
    def track(self, expenses, definitions: tuple[BudgetDefinition, ...]):
        results = []
        for definition in definitions:
            relevant = tuple(
                item for item in expenses
                if definition.category == "Unknown"
                or str(getattr(item.category, "value", item.category)) == definition.category
            )
            spent = round(sum(item.amount for item in relevant), 2)
            utilization = spent / definition.limit if definition.limit else 0.0
            results.append(ExpenseBudget(
                definition.budget_id, definition.name, definition.period,
                definition.limit, spent, round(definition.limit - spent, 2),
                round(utilization, 6), definition.category, spent > definition.limit,
                utilization >= definition.warning_threshold, definition.currency,
            ))
        return tuple(results)
