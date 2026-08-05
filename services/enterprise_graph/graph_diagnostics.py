from __future__ import annotations

from .models import GraphDiagnostic, GraphDiagnostics


class EnterpriseGraphDiagnostics:
    def runtime(self, diagnostics: GraphDiagnostics) -> GraphDiagnostics:
        return GraphDiagnostics(
            errors=diagnostics.errors,
            warnings=diagnostics.warnings,
            information=(
                *diagnostics.information,
                GraphDiagnostic(
                    "graph_sidecar_non_authoritative",
                    "Enterprise graph is request-scoped, storage-agnostic, and ignored by the parser.",
                ),
            ),
        )

    def failed(self, error: Exception) -> GraphDiagnostics:
        return GraphDiagnostics(errors=(GraphDiagnostic(
            "enterprise_graph_sidecar_failed",
            f"Enterprise graph construction failed safely: {error.__class__.__name__}.",
            "error",
        ),))

