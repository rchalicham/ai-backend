from __future__ import annotations

from .models import GrammarCompliance, GrammarLearningSuggestion, ReceiptGrammar


class ReceiptGrammarLearningService:
    """Creates approval-only proposals and never writes production grammar."""

    def suggest(
        self,
        grammar: ReceiptGrammar,
        compliance: GrammarCompliance,
    ) -> tuple[GrammarLearningSuggestion, ...]:
        suggestions: list[GrammarLearningSuggestion] = []
        for violation in compliance.violations:
            suggestion_type = {
                "required_section_missing": "possible_optional_section",
                "required_relationship_not_observed": "possible_relationship",
                "grammar_rule_not_satisfied": "possible_new_rule",
            }.get(violation.code, "possible_grammar_revision")
            suggestions.append(GrammarLearningSuggestion(
                suggestion_type=suggestion_type,
                receipt_family=grammar.metadata.receipt_family,
                subject_id=violation.subject_id,
                description=f"Review observed non-compliance: {violation.message}",
                evidence_references=(compliance.document_id,),
                confidence=max(0.0, min(1.0, 1.0 - compliance.overall_compliance)),
            ))
        matched = set(compliance.matched_sections)
        for transition in grammar.transitions:
            if (
                transition.source_section_id in matched
                and transition.target_section_id not in matched
            ):
                suggestions.append(GrammarLearningSuggestion(
                    suggestion_type="possible_transition",
                    receipt_family=grammar.metadata.receipt_family,
                    subject_id=transition.transition_id,
                    description="Review whether the target transition is optional for this receipt family.",
                    evidence_references=(compliance.document_id,),
                    confidence=0.5,
                ))
        return tuple(suggestions)

