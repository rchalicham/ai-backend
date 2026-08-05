from __future__ import annotations

from collections.abc import Iterable

from .models import (
    GrammarDiagnostic,
    GrammarDiagnosticSeverity,
    GrammarDiagnostics,
)


class ReceiptGrammarDiagnosticsService:
    def build(self, diagnostics: Iterable[GrammarDiagnostic]) -> GrammarDiagnostics:
        values = tuple(diagnostics)
        return GrammarDiagnostics(
            errors=tuple(item for item in values if item.severity is GrammarDiagnosticSeverity.ERROR),
            warnings=tuple(item for item in values if item.severity is GrammarDiagnosticSeverity.WARNING),
            information=tuple(item for item in values if item.severity is GrammarDiagnosticSeverity.INFO),
        )

    def error(self, code: str, message: str, subject_id: str = "") -> GrammarDiagnostic:
        return GrammarDiagnostic(code, message, GrammarDiagnosticSeverity.ERROR, subject_id)

    def warning(self, code: str, message: str, subject_id: str = "") -> GrammarDiagnostic:
        return GrammarDiagnostic(code, message, GrammarDiagnosticSeverity.WARNING, subject_id)

    def information(self, code: str, message: str, subject_id: str = "") -> GrammarDiagnostic:
        return GrammarDiagnostic(code, message, GrammarDiagnosticSeverity.INFO, subject_id)

