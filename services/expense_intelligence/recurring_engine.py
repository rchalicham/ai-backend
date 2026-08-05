from __future__ import annotations

import hashlib
from collections import defaultdict

from .models import RecurringExpense
from .spending_engine import expense_date


class RecurringExpenseEngine:
    def detect(self, expenses) -> tuple[RecurringExpense, ...]:
        grouped = defaultdict(list)
        for item in expenses:
            merchant_id = item.merchant.merchant_id if item.merchant else ""
            if merchant_id:
                grouped[(merchant_id, str(getattr(item.category, "value", item.category)))].append(item)
        results = []
        for (merchant_id, category), values in sorted(grouped.items()):
            ordered = sorted(values, key=lambda x: x.occurred_at)
            if len(ordered) < 2:
                continue
            intervals = [
                (expense_date(right.occurred_at) - expense_date(left.occurred_at)).days
                for left, right in zip(ordered, ordered[1:])
            ]
            average_interval = sum(intervals) / len(intervals)
            cadence = (
                "weekly" if 5 <= average_interval <= 9
                else "monthly" if 25 <= average_interval <= 35
                else "quarterly" if 80 <= average_interval <= 100
                else "recurring"
            )
            amount_average = sum(item.amount for item in ordered) / len(ordered)
            amount_variance = max(abs(item.amount - amount_average) for item in ordered)
            consistency = 1 - min(1.0, amount_variance / amount_average) if amount_average else 0
            confidence = min(1.0, .45 + len(ordered) * .1 + consistency * .25)
            token = hashlib.sha256(f"{merchant_id}|{category}".encode()).hexdigest()[:20]
            results.append(RecurringExpense(
                f"recurring:{token}", merchant_id, category, cadence,
                round(amount_average, 2), len(ordered),
                tuple(item.expense_id for item in ordered),
                tuple(dict.fromkeys(x for item in ordered for x in item.evidence_ids)),
                round(confidence, 6),
            ))
        return tuple(results)
