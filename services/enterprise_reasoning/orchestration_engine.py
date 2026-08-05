from __future__ import annotations

from .evidence_fusion import EvidenceFusionEngine
from .tool_executor import ToolExecutor


class ReasoningOrchestrationEngine:
    def __init__(self, executor=None, fusion=None) -> None:
        self.executor = executor or ToolExecutor()
        self.fusion = fusion or EvidenceFusionEngine()

    def execute(self, plan, context):
        collected, traces = self.executor.execute_retrieval(plan, context)
        return self.fusion.fuse(collected), traces
