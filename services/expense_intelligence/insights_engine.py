from __future__ import annotations

from .models import ExpenseInsight


class ExpenseInsightsEngine:
    def generate(self, summary, expenses, confidence):
        insights = []
        if summary.monthly:
            latest = summary.monthly[-1]
            insights.append(ExpenseInsight(
                "insight:monthly-spending", "monthly_spending", "Monthly spending",
                latest.total, latest.month,
                "explanation:insight:monthly_spending",
                tuple(dict.fromkeys(x for item in expenses for x in item.evidence_ids)),
                confidence,
            ))
        if summary.categories:
            top = summary.categories[0]
            insights.append(ExpenseInsight(
                "insight:biggest-category", "biggest_category", "Biggest category",
                str(getattr(top.category, "value", top.category)), summary.period_end,
                "explanation:insight:biggest_category", confidence=confidence,
            ))
        if summary.merchants:
            top = summary.merchants[0]
            insights.append(ExpenseInsight(
                "insight:biggest-merchant", "biggest_merchant", "Biggest merchant",
                top.merchant_name, summary.period_end,
                "explanation:insight:biggest_merchant", confidence=confidence,
            ))
        if expenses:
            largest = max(expenses, key=lambda x: x.amount)
            groceries = tuple(
                x for x in expenses
                if str(getattr(x.category, "value", x.category)) == "Groceries"
            )
            insights.append(ExpenseInsight(
                "insight:largest-purchase", "largest_purchase", "Largest purchase",
                largest.amount, largest.occurred_at[:10],
                "explanation:insight:largest_purchase", largest.evidence_ids, confidence,
            ))
            if groceries:
                insights.append(ExpenseInsight(
                    "insight:average-grocery", "average_grocery_bill", "Average grocery bill",
                    round(sum(x.amount for x in groceries) / len(groceries), 2),
                    summary.period_end, "explanation:insight:average_grocery",
                    tuple(dict.fromkeys(x for item in groceries for x in item.evidence_ids)),
                    confidence,
                ))
        return tuple(insights)
