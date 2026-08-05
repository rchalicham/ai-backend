from __future__ import annotations

from .document_context_engine import DocumentContextEngine


class DocumentFamilyEngine(DocumentContextEngine):
    """Public DFSF facade retained separately from its context coordinator."""

    evaluate = DocumentContextEngine.build
    safe_evaluate = DocumentContextEngine.safe_build
