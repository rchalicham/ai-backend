from __future__ import annotations

from .models import HouseholdProfile


class HouseholdProfileEngine:
    def build(self, household, *, members=(), relationships=(), ownership=(),
              responsibilities=(), consumption=(), preferences=(), goals=(),
              assets=(), vehicles=(), properties=(), pets=(), expense_intelligence=None):
        expense = expense_intelligence or {}
        summary = expense.get("summary") or {}
        merchants = summary.get("merchants") or ()
        categories = summary.get("categories") or ()
        habits = tuple((
            *(f"Frequently shops at {item.get('merchant_name')}" for item in merchants[:3]),
            *(f"Spending includes {item.get('category')}" for item in categories[:3]),
        ))
        monthly = (summary.get("monthly") or ())
        monthly_spending = float(monthly[-1].get("total") or 0) if monthly else 0.0
        return HouseholdProfile(
            household, tuple(members), tuple(relationships), tuple(ownership),
            tuple(responsibilities), tuple(consumption), tuple(preferences),
            tuple(goals), tuple(assets), tuple(vehicles), tuple(properties),
            tuple(pets), monthly_spending, habits, (),
        )
