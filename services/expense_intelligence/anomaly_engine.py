from __future__ import annotations

import hashlib
from collections import defaultdict

from .models import ExpenseAnomaly


class ExpenseAnomalyEngine:
    def detect(self, expenses) -> tuple[ExpenseAnomaly, ...]:
        if not expenses:
            return ()
        anomalies = []
        average = sum(x.amount for x in expenses) / len(expenses)
        for item in expenses:
            if len(expenses) >= 3 and item.amount > average * 3:
                anomalies.append(self._anomaly(
                    "large_purchase", "medium",
                    f"{item.expense_id} is more than three times average spend.",
                    (item,),
                ))
            if str(getattr(item.category, "value", item.category)) == "Unknown":
                anomalies.append(self._anomaly(
                    "unexpected_spending", "low",
                    f"{item.expense_id} has no supported expense category.",
                    (item,),
                ))
            if not item.document_ids:
                anomalies.append(self._anomaly(
                    "missing_receipt", "medium",
                    f"{item.expense_id} has no supporting document reference.",
                    (item,),
                ))
        duplicates = defaultdict(list)
        for item in expenses:
            key = (
                item.merchant.merchant_id if item.merchant else "",
                round(item.amount, 2), item.occurred_at[:10],
            )
            duplicates[key].append(item)
        for values in duplicates.values():
            if len(values) > 1:
                anomalies.append(self._anomaly(
                    "duplicate_purchase", "high",
                    "Multiple expenses share merchant, amount, and date.",
                    tuple(values),
                ))
        document_groups = defaultdict(list)
        for item in expenses:
            for document_id in item.document_ids:
                document_groups[document_id].append(item)
        for document_id, values in document_groups.items():
            if len(values) > 1:
                anomalies.append(self._anomaly(
                    "duplicate_receipt", "high",
                    f"Document {document_id} supports multiple duplicate expense candidates.",
                    tuple(values),
                ))
        return tuple(anomalies)

    @staticmethod
    def _anomaly(kind, severity, description, expenses):
        ids = tuple(item.expense_id for item in expenses)
        token = hashlib.sha256(f"{kind}|{ids}".encode()).hexdigest()[:20]
        return ExpenseAnomaly(
            f"anomaly:{token}", kind, severity, description, ids,
            tuple(dict.fromkeys(x for item in expenses for x in item.evidence_ids)),
            .9 if kind == "duplicate_purchase" else .75, False,
        )
