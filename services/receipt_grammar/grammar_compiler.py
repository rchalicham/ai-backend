from __future__ import annotations

from collections import defaultdict, deque

from .grammar_diagnostics import ReceiptGrammarDiagnosticsService
from .models import (
    GrammarCompilation,
    GrammarRuleType,
    GrammarTransitionType,
    ReceiptGrammar,
)


class ReceiptGrammarCompiler:
    """Validates and compiles declarative receipt-language definitions."""

    def __init__(self, diagnostics: ReceiptGrammarDiagnosticsService | None = None) -> None:
        self.diagnostics = diagnostics or ReceiptGrammarDiagnosticsService()

    def compile(self, grammar: ReceiptGrammar) -> GrammarCompilation:
        findings = []
        section_ids = [section.section_id for section in grammar.sections]
        role_ids = [role.role_id for role in grammar.roles]
        rule_ids = [rule.rule_id for rule in grammar.rules]
        expectation_ids = [item.expectation_id for item in grammar.expectations]
        transition_ids = [item.transition_id for item in grammar.transitions]
        relationship_ids = [item.relationship_id for item in grammar.relationships]

        self._check_unique("section", section_ids, findings)
        self._check_unique("role", role_ids, findings)
        self._check_unique("rule", rule_ids, findings)
        self._check_unique("expectation", expectation_ids, findings)
        self._check_unique("transition", transition_ids, findings)
        self._check_unique("relationship", relationship_ids, findings)

        section_set = set(section_ids)
        role_set = set(role_ids)
        subject_set = section_set | role_set
        expectation_set = set(expectation_ids)

        if not grammar.sections:
            findings.append(self.diagnostics.error(
                "grammar_requires_sections", "A grammar must define at least one section.",
            ))
        if grammar.sections and not any(section.required for section in grammar.sections):
            findings.append(self.diagnostics.warning(
                "grammar_has_no_required_sections",
                "The grammar has no required sections and therefore expresses no minimum structure.",
            ))

        for section in grammar.sections:
            if section.minimum_occurrences < 0:
                findings.append(self.diagnostics.error(
                    "negative_minimum_occurrences", "Minimum occurrences cannot be negative.", section.section_id,
                ))
            if section.maximum_occurrences is not None and section.maximum_occurrences < section.minimum_occurrences:
                findings.append(self.diagnostics.error(
                    "invalid_occurrence_range", "Maximum occurrences cannot be below minimum occurrences.", section.section_id,
                ))
            if section.required and section.minimum_occurrences == 0:
                findings.append(self.diagnostics.warning(
                    "required_section_zero_minimum",
                    "A required section should declare at least one minimum occurrence.",
                    section.section_id,
                ))
            if not section.required and section.minimum_occurrences > 0:
                findings.append(self.diagnostics.warning(
                    "optional_section_positive_minimum",
                    "An optional section with a positive minimum is effectively required.",
                    section.section_id,
                ))
            if section.repeatable and section.maximum_occurrences == 1:
                findings.append(self.diagnostics.error(
                    "repeatable_section_single_maximum",
                    "A repeatable section cannot declare a maximum of one occurrence.",
                    section.section_id,
                ))
            for role_id in section.role_ids:
                if role_id not in role_set:
                    findings.append(self.diagnostics.error(
                        "unknown_section_role", f"Section references unknown role '{role_id}'.", section.section_id,
                    ))

        for role in grammar.roles:
            if role.section_id not in section_set:
                findings.append(self.diagnostics.error(
                    "unknown_role_section", f"Role references unknown section '{role.section_id}'.", role.role_id,
                ))
            for expectation_id in role.expectation_ids:
                if expectation_id not in expectation_set:
                    findings.append(self.diagnostics.error(
                        "unknown_role_expectation",
                        f"Role references unknown expectation '{expectation_id}'.",
                        role.role_id,
                    ))

        for transition in grammar.transitions:
            if transition.source_section_id not in section_set:
                findings.append(self.diagnostics.error(
                    "unknown_transition_source",
                    f"Transition source '{transition.source_section_id}' is not a section.",
                    transition.transition_id,
                ))
            if transition.target_section_id not in section_set:
                findings.append(self.diagnostics.error(
                    "unknown_transition_target",
                    f"Transition target '{transition.target_section_id}' is not a section.",
                    transition.transition_id,
                ))
            if (
                transition.source_section_id == transition.target_section_id
                and transition.transition_type is not GrammarTransitionType.REPEATING
            ):
                findings.append(self.diagnostics.error(
                    "non_repeating_self_transition",
                    "Only a repeating transition may target its source section.",
                    transition.transition_id,
                ))

        for relationship in grammar.relationships:
            if relationship.source_id not in subject_set:
                findings.append(self.diagnostics.error(
                    "unknown_relationship_source",
                    f"Relationship source '{relationship.source_id}' is not a section or role.",
                    relationship.relationship_id,
                ))
            if relationship.target_id not in subject_set:
                findings.append(self.diagnostics.error(
                    "unknown_relationship_target",
                    f"Relationship target '{relationship.target_id}' is not a section or role.",
                    relationship.relationship_id,
                ))

        for rule in grammar.rules:
            if rule.subject_id not in subject_set:
                findings.append(self.diagnostics.error(
                    "unknown_rule_subject",
                    f"Rule subject '{rule.subject_id}' is not a section or role.",
                    rule.rule_id,
                ))
            if rule.target_id and rule.target_id not in subject_set:
                findings.append(self.diagnostics.error(
                    "unknown_rule_target",
                    f"Rule target '{rule.target_id}' is not a section or role.",
                    rule.rule_id,
                ))
            if rule.rule_type is GrammarRuleType.FOLLOWS and not rule.target_id:
                findings.append(self.diagnostics.error(
                    "follows_requires_target", "A follows rule requires a target.", rule.rule_id,
                ))

        findings.extend(self._rule_conflicts(grammar))
        cycle_nodes = self._cycle_nodes(grammar)
        if cycle_nodes:
            findings.append(self.diagnostics.error(
                "transition_cycle",
                f"Non-repeating transitions contain a cycle: {', '.join(sorted(cycle_nodes))}.",
            ))

        order = self._topological_order(grammar) if not cycle_nodes else ()
        return GrammarCompilation(
            grammar=grammar,
            diagnostics=self.diagnostics.build(findings),
            ordered_section_ids=order,
        )

    def _check_unique(self, kind: str, values: list[str], findings: list) -> None:
        seen: set[str] = set()
        for value in values:
            if not value:
                findings.append(self.diagnostics.error(f"empty_{kind}_id", f"{kind.title()} ID cannot be empty."))
            elif value in seen:
                findings.append(self.diagnostics.error(
                    f"duplicate_{kind}_id", f"Duplicate {kind} ID '{value}'.", value,
                ))
            seen.add(value)

    def _rule_conflicts(self, grammar: ReceiptGrammar) -> tuple:
        by_subject: dict[str, set[GrammarRuleType]] = defaultdict(set)
        rule_ids: dict[tuple[str, GrammarRuleType], str] = {}
        for rule in grammar.rules:
            by_subject[rule.subject_id].add(rule.rule_type)
            rule_ids[(rule.subject_id, rule.rule_type)] = rule.rule_id
        findings = []
        for subject, rule_types in by_subject.items():
            if GrammarRuleType.REQUIRED in rule_types and GrammarRuleType.OPTIONAL in rule_types:
                findings.append(self.diagnostics.error(
                    "required_optional_conflict",
                    "A subject cannot be both required and optional.",
                    subject,
                ))
            if GrammarRuleType.OCCURS_ONCE in rule_types and GrammarRuleType.REPEATS in rule_types:
                findings.append(self.diagnostics.error(
                    "occurrence_rule_conflict",
                    "A subject cannot both occur once and repeat.",
                    subject,
                ))
        return tuple(findings)

    def _graph(self, grammar: ReceiptGrammar) -> dict[str, set[str]]:
        graph = {section.section_id: set() for section in grammar.sections}
        for transition in grammar.transitions:
            if transition.transition_type is GrammarTransitionType.REPEATING:
                continue
            if transition.source_section_id in graph and transition.target_section_id in graph:
                graph[transition.source_section_id].add(transition.target_section_id)
        return graph

    def _cycle_nodes(self, grammar: ReceiptGrammar) -> set[str]:
        graph = self._graph(grammar)
        visiting: set[str] = set()
        visited: set[str] = set()
        cycle: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                cycle.add(node)
                return
            if node in visited:
                return
            visiting.add(node)
            for target in graph.get(node, ()):
                if target in visiting:
                    cycle.update((node, target))
                else:
                    visit(target)
                    if target in cycle:
                        cycle.add(node)
            visiting.remove(node)
            visited.add(node)

        for node in graph:
            visit(node)
        return cycle

    def _topological_order(self, grammar: ReceiptGrammar) -> tuple[str, ...]:
        graph = self._graph(grammar)
        indegree = {node: 0 for node in graph}
        for targets in graph.values():
            for target in targets:
                indegree[target] += 1
        queue = deque(section.section_id for section in grammar.sections if indegree[section.section_id] == 0)
        order: list[str] = []
        while queue:
            node = queue.popleft()
            order.append(node)
            for target in graph[node]:
                indegree[target] -= 1
                if indegree[target] == 0:
                    queue.append(target)
        return tuple(order)
