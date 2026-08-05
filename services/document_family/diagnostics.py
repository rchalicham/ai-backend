from __future__ import annotations

from .models import FamilyDiagnostic


class DocumentFamilyDiagnostics:
    @staticmethod
    def sidecar() -> tuple[tuple[str, object], ...]:
        return (
            ("sidecar", True), ("affectsExtraction", False),
            ("parserAuthorityChanged", False), ("ocrModified", False),
            ("domModified", False), ("classificationModified", False),
        )

    @staticmethod
    def warning(code: str, subject_id: str = "") -> FamilyDiagnostic:
        return FamilyDiagnostic(code, code.replace("_", " "), "warning", subject_id)
