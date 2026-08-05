from __future__ import annotations

from .models import Correlation, EvidenceRecord


class EvidenceEngine:
    def build(self, correlations: tuple[Correlation, ...]) -> tuple[EvidenceRecord, ...]:
        return tuple(
            EvidenceRecord(
                f"evidence:{correlation.correlation_id}",
                correlation.document_references,
                tuple(dict.fromkeys(
                    reference
                    for document in correlation.document_references
                    for reference in (
                        *document.evidence_references,
                        f"document:{document.document_id}",
                        f"graph:{document.graph_id}",
                    )
                )),
                correlation.entity_ids,
                correlation.reason,
                correlation.confidence,
                correlation.timestamp,
            )
            for correlation in correlations
        )

