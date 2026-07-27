from __future__ import annotations

from .models import BlueprintComparison, ReceiptFamilyCandidate


class ReceiptCandidateRanker:
    def rank(
        self,
        comparisons: tuple[BlueprintComparison, ...],
        *,
        top_n: int = 3,
    ) -> tuple[ReceiptFamilyCandidate, ...]:
        ordered = sorted(comparisons, key=lambda item: (-item.confidence, item.receipt_family))
        candidates = []
        for index, comparison in enumerate(ordered[:max(0, top_n)], 1):
            strongest = sorted(
                ((key, value) for key, value in comparison.confidence_breakdown if key not in {"strategy", "coverage", "agreement"}),
                key=lambda item: -item[1],
            )[:3]
            reason = ", ".join(name.replace("_", " ").title() for name, value in strongest if value > 0) or "Physical feature similarity"
            candidates.append(ReceiptFamilyCandidate(
                receipt_family=comparison.receipt_family,
                confidence=comparison.confidence,
                rank=index,
                reason=reason,
                confidence_breakdown=comparison.confidence_breakdown,
                blueprint_reference=comparison.blueprint_reference,
            ))
        return tuple(candidates)
