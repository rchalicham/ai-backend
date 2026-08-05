from __future__ import annotations

from collections.abc import Iterable

from .models import (
    ConstraintDiagnostic,
    ConstraintDiagnostics,
    ConstraintDiagnosticSeverity,
)


class ConstraintDiagnosticsService:
    def build(self, values: Iterable[ConstraintDiagnostic]) -> ConstraintDiagnostics:
        diagnostics = tuple(values)
        return ConstraintDiagnostics(
            errors=tuple(item for item in diagnostics if item.severity is ConstraintDiagnosticSeverity.ERROR),
            warnings=tuple(item for item in diagnostics if item.severity is ConstraintDiagnosticSeverity.WARNING),
            information=tuple(item for item in diagnostics if item.severity is ConstraintDiagnosticSeverity.INFO),
        )

    def error(self, code: str, message: str, subject_id: str = "") -> ConstraintDiagnostic:
        return ConstraintDiagnostic(code, message, ConstraintDiagnosticSeverity.ERROR, subject_id)

    def warning(self, code: str, message: str, subject_id: str = "") -> ConstraintDiagnostic:
        return ConstraintDiagnostic(code, message, ConstraintDiagnosticSeverity.WARNING, subject_id)

    def information(self, code: str, message: str, subject_id: str = "") -> ConstraintDiagnostic:
        return ConstraintDiagnostic(code, message, ConstraintDiagnosticSeverity.INFO, subject_id)

