from __future__ import annotations

from .models import ExpenseConfidence


class ExpenseConfidenceEngine:
    def aggregate(self, expenses, reasoning=None):
        reasoning = reasoning or {}
        decision = reasoning.get("decision") or {}
        reasoning_value = float((decision.get("confidence") or {}).get("overall") or 0)
        expense_value = (
            sum(item.confidence for item in expenses) / len(expenses) if expenses else 0.0
        )
        evidence = reasoning.get("evidence") or ()
        values = {
            "product": self._source(evidence, "product_intelligence"),
            "knowledge": self._source(evidence, "enterprise_graph"),
            "cross_document": self._source(evidence, "cross_document_intelligence"),
            "reasoning": reasoning_value,
            "learning": self._source(evidence, "enterprise_learning"),
            "expense": expense_value,
        }
        present = [value for value in values.values() if value > 0]
        overall = sum(present) / len(present) if present else 0.0
        return ExpenseConfidence(round(overall, 6), **values, components=tuple(values.items()))

    @staticmethod
    def _source(evidence, source):
        values = [float(x.get("confidence") or 0) for x in evidence
                  if x.get("source_tool") == source]
        return max(values, default=0.0)
