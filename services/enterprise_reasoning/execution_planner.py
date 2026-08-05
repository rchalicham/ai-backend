from __future__ import annotations

from .models import ReasoningPlan, ReasoningStep


class ExecutionPlanner:
    def waves(self, plan: ReasoningPlan) -> tuple[tuple[ReasoningStep, ...], ...]:
        remaining = list(plan.steps)
        completed: set[str] = set()
        waves = []
        while remaining:
            ready = tuple(step for step in remaining if set(step.depends_on) <= completed)
            if not ready:
                raise ValueError("reasoning_plan_contains_cycle_or_missing_dependency")
            waves.append(ready)
            completed.update(step.step_id for step in ready)
            remaining = [step for step in remaining if step not in ready]
        return tuple(waves)
