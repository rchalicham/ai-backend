from __future__ import annotations

from collections import defaultdict

from .models import Expense, MerchantSummary


class MerchantExpenseEngine:
    def summarize(self, expenses: tuple[Expense, ...]) -> tuple[MerchantSummary, ...]:
        grouped = defaultdict(list)
        for item in expenses:
            if item.merchant:
                grouped[item.merchant.merchant_id].append(item)
        ranked = sorted(grouped.items(), key=lambda x: -sum(y.amount for y in x[1]))
        total_frequency = len(expenses) or 1
        return tuple(MerchantSummary(
            merchant_id,
            values[0].merchant.canonical_name or values[0].merchant.name,
            round(sum(x.amount for x in values), 2),
            len(values),
            round(sum(x.amount for x in values) / len(values), 2),
            index + 1,
            loyalty_score=round(len(values) / total_frequency, 6),
            currency=values[0].currency,
        ) for index, (merchant_id, values) in enumerate(ranked))

    def top_merchants(self, expenses, limit=10):
        return self.summarize(tuple(expenses))[:limit]

    def compare(self, expenses, left_id, right_id):
        values = {x.merchant_id: x for x in self.summarize(tuple(expenses))}
        return values.get(left_id), values.get(right_id)

    def frequency(self, expenses):
        return tuple((item.merchant_id, item.frequency) for item in self.summarize(tuple(expenses)))

    def average_spend(self, expenses):
        return tuple((item.merchant_id, item.average_spend) for item in self.summarize(tuple(expenses)))

    def rankings(self, expenses):
        return self.summarize(tuple(expenses))

    def price_changes(self, expenses):
        grouped = defaultdict(list)
        for item in expenses:
            if item.merchant:
                grouped[item.merchant.merchant_id].append(item)
        values = []
        for merchant, items in sorted(grouped.items()):
            ordered = sorted(items, key=lambda x: x.occurred_at)
            if len(ordered) >= 2 and ordered[0].amount:
                values.append((
                    merchant,
                    round((ordered[-1].amount - ordered[0].amount) / ordered[0].amount * 100, 2),
                ))
        return tuple(values)
