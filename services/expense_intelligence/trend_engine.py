from __future__ import annotations

import hashlib
from collections import defaultdict

from .models import ExpenseTrend
from .spending_engine import expense_date


class ExpenseTrendEngine:
    def analyze(self, expenses) -> tuple[ExpenseTrend, ...]:
        grouped = defaultdict(lambda: defaultdict(float))
        evidence = defaultdict(lambda: defaultdict(list))
        for item in expenses:
            month = expense_date(item.occurred_at).strftime("%Y-%m")
            category = str(getattr(item.category, "value", item.category))
            grouped[category][month] += item.amount
            evidence[category][month].extend(item.evidence_ids)
        trends = []
        for category, periods in sorted(grouped.items()):
            ordered = sorted(periods.items())
            if len(ordered) < 2:
                continue
            previous_period, previous = ordered[-2]
            current_period, current = ordered[-1]
            change = ((current - previous) / previous * 100) if previous else 0.0
            token = hashlib.sha256(f"{category}|{current_period}".encode()).hexdigest()[:20]
            trends.append(ExpenseTrend(
                f"trend:{token}", "category_growth", category,
                "increasing" if change > 0 else "decreasing" if change < 0 else "stable",
                round(current, 2), round(previous, 2), round(change, 2),
                f"{previous_period} to {current_period}",
                tuple(dict.fromkeys((*evidence[category][previous_period],
                                     *evidence[category][current_period]))),
                min(1.0, .6 + len(ordered) * .05), False,
            ))
        return tuple(trends)
