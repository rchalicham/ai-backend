from __future__ import annotations

from .models import ProjectionExplanation, ProjectionSource


class ProjectionExplainer:
    def explain(self, field_key: str, source: ProjectionSource, reason: str, evidence=()) -> ProjectionExplanation:
        return ProjectionExplanation(
            f"{field_key.replace('_', ' ').title()} displayed from {source.value}.",
            (reason,), tuple(evidence),
        )

