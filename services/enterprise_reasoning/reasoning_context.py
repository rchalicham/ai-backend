from __future__ import annotations

from .models import ReasoningContext


class ReasoningContextBuilder:
    """Builds reasoning context exclusively from normalized sidecar contracts."""

    def build(self, context_id: str, **sources) -> ReasoningContext:
        if sources.get("raw_ocr") is not None or sources.get("parser_guesses") is not None:
            raise ValueError("reasoning_context_rejects_raw_ocr_and_parser_guesses")
        allowed = {
            key: value for key, value in sources.items()
            if key in {
                "constraint_result", "product_intelligence", "enterprise_graph",
                "cross_document_intelligence", "enterprise_learning",
            }
        }
        return ReasoningContext(context_id, **allowed)
