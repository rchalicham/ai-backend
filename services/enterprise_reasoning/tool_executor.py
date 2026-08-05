from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event

from .models import ReasoningContext, ReasoningPlan, ReasoningTrace
from .retrieval_engine import RetrievalEngine
from .tool_registry import EnterpriseToolRegistry


class ToolExecutor:
    def __init__(self, registry=None, retrieval=None) -> None:
        self.registry = registry or EnterpriseToolRegistry()
        self.retrieval = retrieval or RetrievalEngine()

    def execute_retrieval(
        self, plan: ReasoningPlan, context: ReasoningContext,
        cancellation: Event | None = None,
    ):
        cancellation = cancellation or Event()
        steps = tuple(x for x in plan.steps if x.operation == "retrieve_evidence")
        collected, traces = [], []
        with ThreadPoolExecutor(max_workers=max(1, len(steps))) as pool:
            futures = {
                step: pool.submit(self.retrieval.retrieve, step.tool_name, context)
                for step in steps
            }
            for step, future in futures.items():
                started = time.perf_counter()
                if cancellation.is_set():
                    traces.append(ReasoningTrace(
                        f"trace:{step.step_id}", step.step_id, step.tool_name,
                        "cancelled", message="execution cancelled",
                    ))
                    continue
                value, status, message = None, "completed", ""
                for attempt in range(step.retry_count + 1):
                    try:
                        value = future.result(timeout=step.timeout_ms / 1000)
                        break
                    except TimeoutError:
                        status, message = "timeout", "tool execution timed out"
                    except Exception as exc:
                        status, message = "failed", str(exc)
                if value is not None:
                    collected.append((step.tool_name, value))
                traces.append(ReasoningTrace(
                    f"trace:{step.step_id}", step.step_id, step.tool_name, status,
                    step.retry_count + 1,
                    round((time.perf_counter() - started) * 1000, 3),
                    message=message,
                ))
        return tuple(collected), tuple(traces)
