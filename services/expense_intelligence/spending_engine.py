from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from .models import (
    CategorySummary, Expense, ExpenseSummary, HouseholdSummary,
    MonthlySummary, YearlySummary,
)


def expense_date(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.strptime(value[:10], "%Y-%m-%d")


class SpendingEngine:
    def summarize(self, expenses: tuple[Expense, ...]) -> ExpenseSummary:
        ordered = tuple(sorted(expenses, key=lambda x: (x.occurred_at, x.expense_id)))
        currency = ordered[0].currency if ordered else "USD"
        total = round(sum(x.amount for x in ordered), 2)
        dates = tuple(expense_date(x.occurred_at) for x in ordered)
        monthly_values: dict[str, list[Expense]] = defaultdict(list)
        yearly_values: dict[int, list[Expense]] = defaultdict(list)
        category_values: dict[str, list[Expense]] = defaultdict(list)
        household_values: dict[str, list[Expense]] = defaultdict(list)
        for item, date in zip(ordered, dates):
            monthly_values[date.strftime("%Y-%m")].append(item)
            yearly_values[date.year].append(item)
            category_values[str(getattr(item.category, "value", item.category))].append(item)
            if item.household_id:
                household_values[item.household_id].append(item)
        monthly = tuple(self._month(key, values, currency)
                        for key, values in sorted(monthly_values.items()))
        yearly = tuple(self._year(key, values, currency)
                       for key, values in sorted(yearly_values.items()))
        categories = self.category_summaries(category_values, total, currency)
        households = tuple(self._household(key, values, currency)
                           for key, values in sorted(household_values.items()))
        return ExpenseSummary(
            "expense-summary:all", total, len(ordered),
            round(total / len(ordered), 2) if ordered else 0.0, currency,
            dates[0].date().isoformat() if dates else "",
            dates[-1].date().isoformat() if dates else "",
            monthly, yearly, (), categories, households,
        )

    def daily(self, expenses): return self._period(expenses, "%Y-%m-%d")
    def weekly(self, expenses): return self._period(expenses, "%G-W%V")
    def monthly(self, expenses): return self._period(expenses, "%Y-%m")
    def quarterly(self, expenses):
        values = defaultdict(float)
        for item in expenses:
            date = expense_date(item.occurred_at)
            values[f"{date.year}-Q{((date.month - 1) // 3) + 1}"] += item.amount
        return tuple((key, round(value, 2)) for key, value in sorted(values.items()))
    def yearly(self, expenses): return self._period(expenses, "%Y")

    def rolling_average(self, expenses, window=3):
        values = self.monthly(expenses)
        return tuple((
            key, round(sum(value for _, value in values[max(0, index-window+1):index+1])
                       / min(index + 1, window), 2),
        ) for index, (key, _) in enumerate(values))

    moving_average = rolling_average

    def person_spending(self, expenses):
        return self._dimension(expenses, lambda item: item.person_id or "unassigned")

    def household_spending(self, expenses):
        return self._dimension(expenses, lambda item: item.household_id or "unassigned")

    def store_spending(self, expenses):
        return self._dimension(
            expenses,
            lambda item: item.merchant.merchant_id if item.merchant else "unknown",
        )

    def product_spending(self, expenses):
        values = defaultdict(float)
        for item in expenses:
            for product_id in item.product_ids:
                values[product_id] += item.amount / max(1, len(item.product_ids))
        return tuple((key, round(value, 2)) for key, value in sorted(values.items()))

    @staticmethod
    def category_summaries(values, grand_total, currency):
        rows = []
        for category, expenses in values.items():
            total = sum(x.amount for x in expenses)
            rows.append(CategorySummary(
                category, round(total, 2), len(expenses), round(total / len(expenses), 2),
                round(total / grand_total, 6) if grand_total else 0.0,
                currency=currency,
            ))
        return tuple(sorted(rows, key=lambda x: (-x.total, str(x.category))))

    @staticmethod
    def _period(expenses, pattern):
        values = defaultdict(float)
        for item in expenses:
            values[expense_date(item.occurred_at).strftime(pattern)] += item.amount
        return tuple((key, round(value, 2)) for key, value in sorted(values.items()))

    @staticmethod
    def _dimension(expenses, identity):
        values = defaultdict(float)
        for item in expenses:
            values[identity(item)] += item.amount
        return tuple((key, round(value, 2)) for key, value in sorted(values.items()))

    def _month(self, key, values, currency):
        total = sum(x.amount for x in values)
        categories = defaultdict(float)
        for item in values:
            categories[str(getattr(item.category, "value", item.category))] += item.amount
        return MonthlySummary(
            key, round(total, 2), len(values), round(total / len(values), 2),
            currency, tuple((name, round(value, 2)) for name, value in sorted(categories.items())),
        )

    def _year(self, key, values, currency):
        total = sum(x.amount for x in values)
        months = dict(self._period(tuple(values), "%Y-%m"))
        return YearlySummary(
            key, round(total, 2), len(values), round(total / len(months), 2) if months else 0,
            currency, tuple(months.items()),
        )

    @staticmethod
    def _household(key, values, currency):
        total = sum(x.amount for x in values)
        people = defaultdict(float)
        for item in values:
            people[item.person_id or "unassigned"] += item.amount
        return HouseholdSummary(
            key, round(total, 2), len(values),
            tuple((name, round(value, 2)) for name, value in sorted(people.items())),
            currency,
        )
