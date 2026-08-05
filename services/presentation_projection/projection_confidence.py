from __future__ import annotations

from .models import ProjectionConfidence, ProjectionSource


class ProjectionConfidenceEngine:
    def calculate(self, source: ProjectionSource, *, parser=0.0, enterprise=0.0, grammar=0.0,
                  constraint=0.0, learning=0.0, graph=0.0) -> ProjectionConfidence:
        values = {"parser": parser, "enterprise": enterprise, "grammar": grammar,
                  "constraint": constraint, "learning": learning, "graph": graph}
        selected = parser if source is ProjectionSource.PARSER else enterprise if source is ProjectionSource.ENTERPRISE else max(parser, enterprise)
        support = sum(value for key, value in values.items() if key not in {"parser", "enterprise"}) / 4
        display = min(1.0, max(0.0, selected * .82 + support * .18))
        return ProjectionConfidence(round(display, 3), parser, enterprise, grammar, constraint,
                                    learning, graph, tuple(values.items()))

