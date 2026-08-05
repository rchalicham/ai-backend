from __future__ import annotations

import hashlib
from collections import defaultdict

from .models import ExpenseRecommendation


class ExpenseSavingsEngine:
    def identify(self, expenses) -> tuple[ExpenseRecommendation, ...]:
        grouped = defaultdict(lambda: defaultdict(list))
        for item in expenses:
            category = str(getattr(item.category, "value", item.category))
            merchant = item.merchant.merchant_id if item.merchant else ""
            if merchant:
                grouped[category][merchant].append(item)
        results = []
        for category, merchants in sorted(grouped.items()):
            if len(merchants) < 2:
                continue
            averages = {
                merchant: sum(x.amount for x in values) / len(values)
                for merchant, values in merchants.items()
            }
            expensive = max(averages, key=averages.get)
            cheaper = min(averages, key=averages.get)
            savings = averages[expensive] - averages[cheaper]
            if savings <= 0:
                continue
            evidence = tuple(dict.fromkeys(
                x for merchant in (expensive, cheaper)
                for item in merchants[merchant] for x in item.evidence_ids
            ))
            token = hashlib.sha256(f"{category}|{expensive}|{cheaper}".encode()).hexdigest()[:20]
            results.append(ExpenseRecommendation(
                f"savings:{token}", "cheaper_merchant",
                f"Compare {category} purchases across merchants",
                f"Observed average spend is lower at {cheaper} than {expensive}.",
                round(savings, 2), next(iter(merchants[cheaper])).currency,
                evidence, .75, True,
            ))
        return tuple(results)
