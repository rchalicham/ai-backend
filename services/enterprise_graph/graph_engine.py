from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from services.product_intelligence import ProductIntelligenceResult

from .graph_builder import EnterpriseGraphBuilder
from .graph_diagnostics import EnterpriseGraphDiagnostics
from .graph_explanation import EnterpriseGraphExplanationEngine
from .graph_learning import EnterpriseGraphLearningService
from .graph_validator import EnterpriseGraphValidator
from .models import (
    EnterpriseGraphContext,
    GraphDiagnostics,
    GraphSubgraph,
)


class EnterpriseGraphEngine:
    """Builds and validates a request graph without persistence or parser feedback."""

    def __init__(
        self,
        builder: EnterpriseGraphBuilder | None = None,
        validator: EnterpriseGraphValidator | None = None,
        diagnostics: EnterpriseGraphDiagnostics | None = None,
        explanation: EnterpriseGraphExplanationEngine | None = None,
        learning: EnterpriseGraphLearningService | None = None,
    ) -> None:
        self.builder = builder or EnterpriseGraphBuilder()
        self.validator = validator or EnterpriseGraphValidator()
        self.diagnostics = diagnostics or EnterpriseGraphDiagnostics()
        self.explanation = explanation or EnterpriseGraphExplanationEngine()
        self.learning = learning or EnterpriseGraphLearningService()

    def build(
        self,
        product_intelligence: ProductIntelligenceResult,
        *,
        receipt_id: str,
        merchant_key: str = "",
        receipt_context: Mapping[str, Any] | None = None,
    ) -> EnterpriseGraphContext:
        graph = self.builder.build(
            product_intelligence,
            receipt_id=receipt_id,
            merchant_key=merchant_key,
            receipt_context=receipt_context,
        )
        validation = self.validator.validate(graph)
        return EnterpriseGraphContext(
            graph,
            self.diagnostics.runtime(validation),
            self.learning.suggest(graph),
            self.explanation.explain_graph(graph),
        )

    def safe_build(
        self,
        product_intelligence: ProductIntelligenceResult | None,
        **kwargs: Any,
    ) -> EnterpriseGraphContext | None:
        if product_intelligence is None:
            return None
        try:
            return self.build(product_intelligence, **kwargs)
        except Exception as exc:
            return EnterpriseGraphContext(
                GraphSubgraph(graph_id=f"receipt-graph:{kwargs.get('receipt_id') or 'unknown'}"),
                self.diagnostics.failed(exc),
            )

