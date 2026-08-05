from __future__ import annotations

import hashlib

from .models import ReasoningPlan, ReasoningRequest, ReasoningSession, ReasoningTrace


class ReasoningSessionManager:
    def create(
        self, request: ReasoningRequest, plan: ReasoningPlan,
        traces: tuple[ReasoningTrace, ...] = (), status: str = "completed",
    ) -> ReasoningSession:
        token = hashlib.sha256(f"{request.request_id}|{plan.plan_id}".encode()).hexdigest()[:24]
        return ReasoningSession(f"session:{token}", request, plan, traces, status)
