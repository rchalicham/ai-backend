from __future__ import annotations

from .models import Diagnostic, Diagnostics, EnterpriseContext


class CrossDocumentDiagnostics:
    def create(self, context: EnterpriseContext) -> Diagnostics:
        return Diagnostics(information=(
            Diagnostic(
                "cross_document_sidecar_evaluated",
                (
                    f"Resolved {len(context.entities)} entities across "
                    f"{1 + len(context.related_documents)} document(s), with "
                    f"{len(context.correlations)} supported correlations."
                ),
            ),
            Diagnostic(
                "enterprise_memory_is_deterministic",
                "Semantic memory is deterministic and is not LLM memory.",
            ),
        ))

    def failed(self, error: Exception) -> Diagnostics:
        return Diagnostics(errors=(Diagnostic(
            "cross_document_sidecar_failed",
            f"Cross-document intelligence failed safely: {error.__class__.__name__}.",
            "error",
        ),))

