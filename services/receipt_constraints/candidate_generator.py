from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from services.receipt_grammar import ReceiptGrammarContext

from .models import ConstraintCandidate


class ConstraintCandidateGenerator:
    def generate(
        self,
        grammar_context: ReceiptGrammarContext,
        interpretations: Iterable[Mapping[str, Any]] = (),
    ) -> tuple[ConstraintCandidate, ...]:
        supplied = tuple(interpretations)
        if supplied:
            return tuple(
                ConstraintCandidate(
                    candidate_id=str(value.get("candidate_id") or value.get("candidateId") or f"candidate-{index + 1}"),
                    interpretation=self._pairs(value.get("interpretation", value)),
                    source=str(value.get("source") or "supplied_hypothesis"),
                    base_confidence=float(value.get("base_confidence", value.get("baseConfidence", 0.0))),
                    grammar_compliance=float(
                        value.get(
                            "grammar_compliance",
                            value.get(
                                "grammarCompliance",
                                grammar_context.compliance.overall_compliance
                                if grammar_context.compliance else 0.0,
                            ),
                        ),
                    ),
                    knowledge_confidence=float(value.get("knowledge_confidence", value.get("knowledgeConfidence", 0.0))),
                    provenance=tuple(str(item) for item in value.get("provenance", ())),
                )
                for index, value in enumerate(supplied)
            )
        compliance = grammar_context.compliance
        if compliance is None:
            return ()
        return (
            ConstraintCandidate(
                candidate_id="grammar-structure-candidate",
                interpretation=(
                    ("sections", compliance.matched_sections),
                    ("candidate_roles", tuple(
                        (role.role_id, role.role_type.value, role.section_id)
                        for role in compliance.candidate_roles
                    )),
                ),
                source="receipt_grammar_sidecar",
                base_confidence=compliance.overall_compliance,
                grammar_compliance=compliance.overall_compliance,
                provenance=(compliance.document_id, compliance.grammar_id),
            ),
        )

    def _pairs(self, value: Any) -> tuple[tuple[str, Any], ...]:
        if isinstance(value, Mapping):
            excluded = {
                "candidate_id", "candidateId", "interpretation", "source",
                "base_confidence", "baseConfidence", "grammar_compliance",
                "grammarCompliance", "knowledge_confidence", "knowledgeConfidence",
                "provenance",
            }
            return tuple((str(key), item) for key, item in value.items() if key not in excluded)
        return tuple((str(item[0]), item[1]) for item in (value or ()) if len(item) == 2)

