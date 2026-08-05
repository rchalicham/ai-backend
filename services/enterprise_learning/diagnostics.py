from __future__ import annotations

from .models import LearningDiagnostics, LearningEvidence, LearningProposal


class EnterpriseLearningDiagnostics:
    def create(
        self,
        evidence: tuple[LearningEvidence, ...],
        proposals: tuple[LearningProposal, ...],
        governance_warnings: tuple[str, ...] = (),
    ) -> LearningDiagnostics:
        verified = sum(item.verified for item in evidence)
        return LearningDiagnostics(
            warnings=governance_warnings,
            information=(
                f"verified semantic evidence: {verified}/{len(evidence)}",
                f"pending governed proposals: {len(proposals)}",
                "production activation requires an explicit approval workflow",
            ),
        )

    @staticmethod
    def failed(error: Exception) -> LearningDiagnostics:
        return LearningDiagnostics(errors=(f"enterprise_learning_failed:{error}",))
