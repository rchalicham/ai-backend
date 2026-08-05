from __future__ import annotations

import hashlib

from .models import ExpenseRecommendation


class ExpenseRecommendationEngine:
    def generate(self, *, budgets=(), recurring=(), anomalies=(), savings=()):
        results = list(savings)
        for budget in budgets:
            if budget.warning:
                token = hashlib.sha256(budget.budget_id.encode()).hexdigest()[:20]
                results.append(ExpenseRecommendation(
                    f"recommendation:{token}", "budget",
                    f"Review {budget.name}",
                    f"Budget utilization is {budget.utilization:.1%}; review remaining purchases.",
                    0.0, budget.currency, (), .95, True,
                ))
        for item in recurring:
            if item.occurrences >= 3:
                results.append(ExpenseRecommendation(
                    f"recommendation:{item.recurring_id}", "subscription_cleanup",
                    f"Review recurring charge from {item.merchant_id}",
                    f"{item.occurrences} {item.cadence} charges were observed.",
                    0.0, "USD", item.evidence_ids, item.confidence, True,
                ))
        for anomaly in anomalies:
            results.append(ExpenseRecommendation(
                f"recommendation:{anomaly.anomaly_id}", "review_anomaly",
                "Review unusual spending",
                anomaly.description, 0.0, "USD", anomaly.evidence_ids,
                anomaly.confidence, True,
            ))
        return tuple(results)
