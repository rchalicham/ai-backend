from __future__ import annotations

from typing import Any

from .models import ReasoningContext


class RetrievalEngine:
    FIELDS = {
        "constraint_solver": "constraint_result",
        "product_intelligence": "product_intelligence",
        "merchant_knowledge": "enterprise_graph",
        "enterprise_graph": "enterprise_graph",
        "cross_document_intelligence": "cross_document_intelligence",
        "enterprise_learning": "enterprise_learning",
    }

    def retrieve(self, source: str, context: ReasoningContext) -> Any:
        field = self.FIELDS.get(source)
        return getattr(context, field, None) if field else None

    def document(self, context): return self.retrieve("cross_document_intelligence", context)
    def knowledge(self, context): return self.retrieve("enterprise_graph", context)
    def historical(self, context): return self.retrieve("cross_document_intelligence", context)
    def timeline(self, context): return self.retrieve("cross_document_intelligence", context)
    def evidence(self, context): return self.retrieve("cross_document_intelligence", context)
