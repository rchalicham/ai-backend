from __future__ import annotations

from collections import defaultdict, deque

from .diagnostics import ConstraintDiagnosticsService
from .models import CompiledReceiptConstraints, ReceiptConstraint


class ReceiptConstraintCompiler:
    def __init__(self, diagnostics: ConstraintDiagnosticsService | None = None) -> None:
        self.diagnostics = diagnostics or ConstraintDiagnosticsService()

    def compile(self, constraint_set: ReceiptConstraint) -> CompiledReceiptConstraints:
        findings = []
        rule_ids = [rule.rule_id for rule in constraint_set.rules]
        weight_ids = [weight.weight_id for weight in constraint_set.weights]
        penalty_ids = [penalty.penalty_id for penalty in constraint_set.penalties]
        self._duplicates("rule", rule_ids, findings)
        self._duplicates("weight", weight_ids, findings)
        self._duplicates("penalty", penalty_ids, findings)

        rule_set = set(rule_ids)
        weight_set = set(weight_ids)
        penalty_set = set(penalty_ids)
        external_dependencies = set(constraint_set.dependencies)
        for rule in constraint_set.rules:
            if rule.weight_id and rule.weight_id not in weight_set:
                findings.append(self.diagnostics.error(
                    "invalid_weight_reference", f"Unknown weight '{rule.weight_id}'.", rule.rule_id,
                ))
            if rule.penalty_id and rule.penalty_id not in penalty_set:
                findings.append(self.diagnostics.error(
                    "invalid_penalty_reference", f"Unknown penalty '{rule.penalty_id}'.", rule.rule_id,
                ))
            for dependency in rule.dependency_ids:
                if dependency not in rule_set and dependency not in external_dependencies:
                    findings.append(self.diagnostics.error(
                        "missing_rule_dependency", f"Unknown dependency '{dependency}'.", rule.rule_id,
                    ))
        for group in constraint_set.groups:
            if group.aggregation not in {"all", "any"}:
                findings.append(self.diagnostics.error(
                    "invalid_group_aggregation", "Group aggregation must be 'all' or 'any'.", group.group_id,
                ))
            for rule_id in group.rule_ids:
                if rule_id not in rule_set:
                    findings.append(self.diagnostics.error(
                        "invalid_group_rule_reference", f"Unknown rule '{rule_id}'.", group.group_id,
                    ))
        for weight in constraint_set.weights:
            if not 0 <= weight.value <= 1:
                findings.append(self.diagnostics.error(
                    "invalid_constraint_weight", "Constraint weights must be between zero and one.", weight.weight_id,
                ))
        for penalty in constraint_set.penalties:
            if not 0 <= penalty.value <= 1:
                findings.append(self.diagnostics.error(
                    "invalid_constraint_penalty", "Constraint penalties must be between zero and one.", penalty.penalty_id,
                ))

        findings.extend(self._conflicts(constraint_set))
        cycle = self._dependency_cycle(constraint_set)
        if cycle:
            findings.append(self.diagnostics.error(
                "circular_rule_dependency",
                f"Rule dependencies contain a cycle: {', '.join(sorted(cycle))}.",
            ))
        order = self._ordered_rules(constraint_set) if not cycle else ()
        categories: dict[str, list[str]] = defaultdict(list)
        for rule_id in order:
            rule = next(item for item in constraint_set.rules if item.rule_id == rule_id)
            categories[rule.category.value].append(rule_id)
        return CompiledReceiptConstraints(
            constraint_set=constraint_set,
            diagnostics=self.diagnostics.build(findings),
            ordered_rule_ids=order,
            rules_by_category=tuple(
                (category, tuple(rule_ids)) for category, rule_ids in sorted(categories.items())
            ),
        )

    def _duplicates(self, kind: str, values: list[str], findings: list) -> None:
        seen = set()
        for value in values:
            if not value:
                findings.append(self.diagnostics.error(f"empty_{kind}_id", f"{kind.title()} ID cannot be empty."))
            elif value in seen:
                findings.append(self.diagnostics.error(
                    f"duplicate_{kind}_id", f"Duplicate {kind} ID '{value}'.", value,
                ))
            seen.add(value)

    def _conflicts(self, constraint_set: ReceiptConstraint) -> tuple:
        signatures: dict[tuple[str, str], list] = defaultdict(list)
        for rule in constraint_set.rules:
            subject = str(dict(rule.parameters).get("subject", ""))
            signatures[(rule.category.value, subject)].append(rule)
        findings = []
        for rules in signatures.values():
            required_types = {rule.rule_type for rule in rules if rule.required}
            if {"required", "forbidden"} <= required_types:
                findings.append(self.diagnostics.error(
                    "conflicting_constraint_rules",
                    "The same subject cannot be both required and forbidden.",
                    rules[0].rule_id,
                ))
        return tuple(findings)

    def _graph(self, constraint_set: ReceiptConstraint) -> dict[str, set[str]]:
        rule_ids = {rule.rule_id for rule in constraint_set.rules}
        return {
            rule.rule_id: {dependency for dependency in rule.dependency_ids if dependency in rule_ids}
            for rule in constraint_set.rules
        }

    def _dependency_cycle(self, constraint_set: ReceiptConstraint) -> set[str]:
        graph = self._graph(constraint_set)
        visiting: set[str] = set()
        visited: set[str] = set()
        cycle: set[str] = set()

        def visit(node: str) -> None:
            if node in visited:
                return
            visiting.add(node)
            for dependency in graph[node]:
                if dependency in visiting:
                    cycle.update((node, dependency))
                else:
                    visit(dependency)
                    if dependency in cycle:
                        cycle.add(node)
            visiting.remove(node)
            visited.add(node)

        for node in graph:
            visit(node)
        return cycle

    def _ordered_rules(self, constraint_set: ReceiptConstraint) -> tuple[str, ...]:
        graph = self._graph(constraint_set)
        indegree = {node: len(dependencies) for node, dependencies in graph.items()}
        dependants: dict[str, set[str]] = defaultdict(set)
        for rule_id, dependencies in graph.items():
            for dependency in dependencies:
                dependants[dependency].add(rule_id)
        queue = deque(rule.rule_id for rule in constraint_set.rules if indegree[rule.rule_id] == 0)
        order = []
        while queue:
            node = queue.popleft()
            order.append(node)
            for dependant in sorted(dependants[node]):
                indegree[dependant] -= 1
                if indegree[dependant] == 0:
                    queue.append(dependant)
        return tuple(order)
