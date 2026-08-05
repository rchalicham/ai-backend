from __future__ import annotations

from collections import defaultdict

from .expense_classifier import ExpenseClassifier
from .models import Expense


class ExpenseCategoryEngine:
    def __init__(self, classifier=None) -> None:
        self.classifier = classifier or ExpenseClassifier()

    def classify(self, expense: Expense):
        if str(getattr(expense.category, "value", expense.category)) != "Unknown":
            return expense.category
        return self.classifier.classify(
            expense.description, expense.merchant.name if expense.merchant else "",
        )

    def group(self, expenses):
        grouped = defaultdict(list)
        for item in expenses:
            grouped[str(getattr(self.classify(item), "value", self.classify(item)))].append(item)
        return tuple((key, tuple(values)) for key, values in sorted(grouped.items()))
