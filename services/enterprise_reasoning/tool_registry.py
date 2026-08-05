from __future__ import annotations

from .models import ReasoningTool


class EnterpriseToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, tuple[ReasoningTool, object | None]] = {}
        for tool in (
            ReasoningTool("constraint_solver", "constraint validation"),
            ReasoningTool("product_intelligence", "canonical product knowledge"),
            ReasoningTool("merchant_knowledge", "approved merchant knowledge"),
            ReasoningTool("enterprise_graph", "semantic graph traversal"),
            ReasoningTool("cross_document_intelligence", "historical context"),
            ReasoningTool("enterprise_learning", "approved learning evidence"),
            ReasoningTool("analytics", "future analytics", enabled=False, future=True),
            ReasoningTool("predictive_engine", "future prediction", enabled=False, future=True),
            ReasoningTool("agents", "future agents", enabled=False, future=True),
            ReasoningTool("llm", "optional language synthesis", deterministic=False),
        ):
            self.register(tool)

    def register(self, tool: ReasoningTool, executor: object | None = None) -> None:
        self._tools[tool.name] = (tool, executor)

    def get(self, name: str) -> tuple[ReasoningTool, object | None] | None:
        return self._tools.get(name)

    def list_tools(self, *, enabled_only: bool = False) -> tuple[ReasoningTool, ...]:
        values = tuple(value[0] for _, value in sorted(self._tools.items()))
        return tuple(x for x in values if x.enabled) if enabled_only else values
