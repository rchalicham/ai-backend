from __future__ import annotations

import json

from .models import Expense, ExpenseCategory, ExpenseMerchant


class ExpenseIntelligenceLoader:
    def expense_from_json(self, payload):
        return self.expense_from_dict(json.loads(payload))

    def expense_from_dict(self, data):
        merchant_data = data.get("merchant")
        merchant = ExpenseMerchant(**merchant_data) if merchant_data else None
        category_value = data.get("category", "Unknown")
        try:
            category = ExpenseCategory(category_value)
        except ValueError:
            category = category_value
        return Expense(
            data["expense_id"], float(data["amount"]), data.get("currency", "USD"),
            data["occurred_at"], category, merchant, data.get("person_id", ""),
            data.get("household_id", ""), tuple(data.get("product_ids", ())),
            tuple(data.get("document_ids", ())), tuple(data.get("evidence_ids", ())),
            data.get("reasoning_request_id", ""), data.get("description", ""),
            float(data.get("confidence", 0)), data.get("metadata"),
        )

    def expenses_from_dict(self, values):
        return tuple(self.expense_from_dict(item) for item in values)
