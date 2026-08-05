from __future__ import annotations

from dataclasses import replace

from .models import (
    GrammarVersionComparison,
    ReceiptGrammar,
    utc_now,
)


class ReceiptGrammarRepository:
    """Append-only in-memory repository keyed by receipt family and version."""

    def __init__(self) -> None:
        self._grammars: dict[str, list[ReceiptGrammar]] = {}

    def load_grammar(self, receipt_family: str, version: int | None = None) -> ReceiptGrammar | None:
        history = self._grammars.get(receipt_family, ())
        if version is None:
            return next((grammar for grammar in reversed(history) if grammar.version.status == "active"), None)
        return next((grammar for grammar in history if grammar.version.entity_version == version), None)

    def save_grammar(self, grammar: ReceiptGrammar, expected_version: int | None = None) -> ReceiptGrammar:
        family = grammar.metadata.receipt_family
        if not family:
            raise ValueError("receipt_grammar_requires_receipt_family")
        history = self._grammars.setdefault(family, [])
        current_version = history[-1].version.entity_version if history else 0
        if expected_version is not None and expected_version != current_version:
            raise ValueError("receipt_grammar_version_conflict")
        if history:
            raise ValueError("receipt_grammar_already_exists_use_version_grammar")
        saved = replace(
            grammar,
            version=replace(
                grammar.version,
                entity_version=current_version + 1,
                status="active",
                updated_at=utc_now(),
                supersedes_version=current_version or None,
            ),
        )
        history.append(saved)
        return saved

    def version_grammar(self, grammar: ReceiptGrammar, expected_version: int | None = None) -> ReceiptGrammar:
        family = grammar.metadata.receipt_family
        history = self._grammars.setdefault(family, [])
        current = history[-1] if history else None
        current_version = current.version.entity_version if current else 0
        if expected_version is not None and expected_version != current_version:
            raise ValueError("receipt_grammar_version_conflict")
        if current and current.metadata.grammar_id != grammar.metadata.grammar_id:
            raise ValueError("receipt_grammar_identity_conflict")
        saved = replace(
            grammar,
            version=replace(
                grammar.version,
                entity_version=current_version + 1,
                status="active",
                created_at=current.version.created_at if current else grammar.version.created_at,
                updated_at=utc_now(),
                supersedes_version=current_version or None,
            ),
        )
        history.append(saved)
        return saved

    def archive_grammar(self, receipt_family: str, version: int | None = None) -> ReceiptGrammar:
        history = self._grammars.get(receipt_family, [])
        grammar = self.load_grammar(receipt_family, version)
        if grammar is None:
            raise KeyError("receipt_grammar_not_found")
        archived = replace(grammar, version=replace(grammar.version, status="archived", updated_at=utc_now()))
        index = history.index(grammar)
        history[index] = archived
        return archived

    def list_grammars(self, receipt_family: str = "", include_archived: bool = False) -> tuple[ReceiptGrammar, ...]:
        values = (
            tuple(self._grammars.get(receipt_family, ()))
            if receipt_family
            else tuple(grammar for history in self._grammars.values() for grammar in history)
        )
        if include_archived:
            return values
        return tuple(grammar for grammar in values if grammar.version.status == "active")

    def compare_grammar_versions(
        self,
        receipt_family: str,
        from_version: int,
        to_version: int,
    ) -> GrammarVersionComparison:
        before = self.load_grammar(receipt_family, from_version)
        after = self.load_grammar(receipt_family, to_version)
        if before is None or after is None:
            raise KeyError("receipt_grammar_version_not_found")
        before_sections = {item.section_id for item in before.sections}
        after_sections = {item.section_id for item in after.sections}
        before_rules = {item.rule_id for item in before.rules}
        after_rules = {item.rule_id for item in after.rules}
        before_transitions = {
            item.transition_id: (item.source_section_id, item.target_section_id, item.transition_type)
            for item in before.transitions
        }
        after_transitions = {
            item.transition_id: (item.source_section_id, item.target_section_id, item.transition_type)
            for item in after.transitions
        }
        return GrammarVersionComparison(
            grammar_id=after.metadata.grammar_id,
            from_version=from_version,
            to_version=to_version,
            added_sections=tuple(sorted(after_sections - before_sections)),
            removed_sections=tuple(sorted(before_sections - after_sections)),
            added_rules=tuple(sorted(after_rules - before_rules)),
            removed_rules=tuple(sorted(before_rules - after_rules)),
            changed_transitions=tuple(sorted(
                key for key in set(before_transitions) | set(after_transitions)
                if before_transitions.get(key) != after_transitions.get(key)
            )),
        )

    # Architecture vocabulary aliases retained for callers that use the names
    # from the framework contract.
    loadGrammar = load_grammar
    saveGrammar = save_grammar
    versionGrammar = version_grammar
    archiveGrammar = archive_grammar
    listGrammars = list_grammars
    compareGrammarVersions = compare_grammar_versions
