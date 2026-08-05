from __future__ import annotations

from collections import defaultdict

from services.receipt_dom import ReceiptDocument
from services.receipt_structure import PageRegionClass, ReceiptPhysicalStructure

from .grammar_diagnostics import ReceiptGrammarDiagnosticsService
from .models import (
    CandidateGrammarRole,
    GrammarCompliance,
    GrammarDiagnostic,
    GrammarRelationshipType,
    GrammarRuleType,
    GrammarSectionType,
    GrammarTransitionType,
    ReceiptGrammar,
)


class ReceiptGrammarValidator:
    """Measures structural compliance without parsing or detecting business values."""

    def __init__(self, diagnostics: ReceiptGrammarDiagnosticsService | None = None) -> None:
        self.diagnostics = diagnostics or ReceiptGrammarDiagnosticsService()

    def validate(
        self,
        document: ReceiptDocument,
        structure: ReceiptPhysicalStructure,
        grammar: ReceiptGrammar,
    ) -> GrammarCompliance:
        evidence = self._physical_evidence(structure)
        node_positions = self._physical_positions(structure)
        section_matches: dict[str, tuple[str, ...]] = {}
        for section in grammar.sections:
            nodes = evidence.get(section.section_type, ())
            if nodes:
                section_matches[section.section_id] = nodes

        matched_rules: list[str] = []
        missing_rules: list[str] = []
        violations: list[GrammarDiagnostic] = []
        warnings: list[GrammarDiagnostic] = []

        explicit_subject_rules = defaultdict(list)
        for rule in grammar.rules:
            explicit_subject_rules[rule.subject_id].append(rule)
            matched = self._rule_matches(rule, section_matches, node_positions, grammar)
            if matched:
                matched_rules.append(rule.rule_id)
            elif rule.required:
                missing_rules.append(rule.rule_id)
                violations.append(self.diagnostics.error(
                    "grammar_rule_not_satisfied",
                    rule.description or f"Required rule '{rule.rule_id}' was not satisfied.",
                    rule.subject_id,
                ))
            else:
                warnings.append(self.diagnostics.warning(
                    "optional_grammar_rule_not_observed",
                    rule.description or f"Optional rule '{rule.rule_id}' was not observed.",
                    rule.subject_id,
                ))

        for section in grammar.sections:
            if section.required and section.section_id not in section_matches:
                synthetic_id = f"required-section:{section.section_id}"
                if not any(
                    rule.rule_type is GrammarRuleType.REQUIRED
                    for rule in explicit_subject_rules.get(section.section_id, ())
                ):
                    missing_rules.append(synthetic_id)
                    violations.append(self.diagnostics.error(
                        "required_section_missing",
                        f"Required section '{section.name}' has no compatible physical evidence.",
                        section.section_id,
                    ))

        for transition in grammar.transitions:
            transition_id = f"transition:{transition.transition_id}"
            transition_matches = self._transition_matches(
                transition, section_matches, node_positions,
            )
            if transition_matches:
                matched_rules.append(transition_id)
            elif transition.transition_type is GrammarTransitionType.REQUIRED:
                missing_rules.append(transition_id)
                violations.append(self.diagnostics.error(
                    "required_transition_not_observed",
                    f"Required transition '{transition.transition_id}' lacks ordered structural support.",
                    transition.transition_id,
                ))

        for relationship in grammar.relationships:
            relationship_id = f"relationship:{relationship.relationship_id}"
            relationship_matches = self._relationship_matches(
                relationship, section_matches, node_positions, grammar,
            )
            if relationship_matches:
                matched_rules.append(relationship_id)
            elif relationship.required:
                missing_rules.append(relationship_id)
                violations.append(self.diagnostics.error(
                    "required_relationship_not_observed",
                    f"Required relationship '{relationship.relationship_id}' lacks structural support.",
                    relationship.relationship_id,
                ))

        candidate_roles = tuple(
            CandidateGrammarRole(
                role_id=role.role_id,
                role_type=role.role_type,
                section_id=role.section_id,
                source_node_ids=section_matches[role.section_id],
                confidence=self._candidate_confidence(section_matches[role.section_id], structure),
            )
            for role in grammar.roles
            if role.section_id in section_matches
        )

        required_count = len(matched_rules) + len(missing_rules)
        compliance = len(matched_rules) / required_count if required_count else 1.0
        return GrammarCompliance(
            document_id=document.id,
            grammar_id=grammar.metadata.grammar_id,
            grammar_version=grammar.version.entity_version,
            overall_compliance=round(max(0.0, min(1.0, compliance)), 4),
            matched_rules=tuple(matched_rules),
            missing_rules=tuple(missing_rules),
            violations=tuple(violations),
            warnings=tuple(warnings),
            candidate_roles=candidate_roles,
            matched_sections=tuple(section.section_id for section in grammar.sections if section.section_id in section_matches),
        )

    def _physical_evidence(
        self,
        structure: ReceiptPhysicalStructure,
    ) -> dict[GrammarSectionType, tuple[str, ...]]:
        values: dict[GrammarSectionType, list[str]] = defaultdict(list)
        for region in structure.region_annotations:
            if region.page_region is PageRegionClass.HEADER:
                values[GrammarSectionType.HEADER].append(region.node_id)
            elif region.page_region is PageRegionClass.BODY:
                values[GrammarSectionType.BODY].append(region.node_id)
            elif region.page_region is PageRegionClass.FOOTER:
                values[GrammarSectionType.FOOTER].append(region.node_id)
            else:
                values[GrammarSectionType.UNKNOWN].append(region.node_id)
        for table in structure.candidate_tables:
            values[GrammarSectionType.ITEMS].append(table.id)
        return {key: tuple(value) for key, value in values.items()}

    def _physical_positions(self, structure: ReceiptPhysicalStructure) -> dict[str, float]:
        positions = {
            annotation.node_id: float(annotation.geometry.y)
            for annotation in structure.region_annotations
        }
        positions.update({
            table.id: float(table.geometry.y)
            for table in structure.candidate_tables
        })
        return positions

    def _transition_matches(
        self,
        transition,
        section_matches: dict[str, tuple[str, ...]],
        node_positions: dict[str, float],
    ) -> bool:
        source = section_matches.get(transition.source_section_id, ())
        target = section_matches.get(transition.target_section_id, ())
        if transition.transition_type is GrammarTransitionType.REPEATING:
            return bool(source)
        if not source or not target:
            return transition.transition_type is GrammarTransitionType.OPTIONAL
        return self._position(source, node_positions) <= self._position(target, node_positions)

    def _relationship_matches(
        self,
        relationship,
        section_matches: dict[str, tuple[str, ...]],
        node_positions: dict[str, float],
        grammar: ReceiptGrammar,
    ) -> bool:
        source_section = self._subject_section(relationship.source_id, grammar)
        target_section = self._subject_section(relationship.target_id, grammar)
        source = section_matches.get(source_section, ())
        target = section_matches.get(target_section, ())
        if relationship.relationship_type is GrammarRelationshipType.OPTIONAL:
            return True
        if not source or not target:
            return False
        source_position = self._position(source, node_positions)
        target_position = self._position(target, node_positions)
        if relationship.relationship_type is GrammarRelationshipType.BEFORE:
            return source_position <= target_position
        if relationship.relationship_type is GrammarRelationshipType.AFTER:
            return source_position >= target_position
        if relationship.relationship_type is GrammarRelationshipType.ADJACENT:
            observed = sorted(
                (self._position(nodes, node_positions), section_id)
                for section_id, nodes in section_matches.items()
            )
            order = [section_id for _, section_id in observed]
            return source_section in order and target_section in order and abs(
                order.index(source_section) - order.index(target_section)
            ) == 1
        if relationship.relationship_type in {
            GrammarRelationshipType.PARENT,
            GrammarRelationshipType.CONTAINS,
        }:
            target_role = next(
                (role for role in grammar.roles if role.role_id == relationship.target_id),
                None,
            )
            return bool(target_role and target_role.section_id == source_section)
        if relationship.relationship_type is GrammarRelationshipType.CHILD:
            source_role = next(
                (role for role in grammar.roles if role.role_id == relationship.source_id),
                None,
            )
            return bool(source_role and source_role.section_id == target_section)
        if relationship.relationship_type is GrammarRelationshipType.SIBLING:
            source_role = next(
                (role for role in grammar.roles if role.role_id == relationship.source_id),
                None,
            )
            target_role = next(
                (role for role in grammar.roles if role.role_id == relationship.target_id),
                None,
            )
            return bool(source_role and target_role and source_role.section_id == target_role.section_id)
        return True

    def _subject_section(self, subject_id: str, grammar: ReceiptGrammar) -> str:
        if any(section.section_id == subject_id for section in grammar.sections):
            return subject_id
        role = next((item for item in grammar.roles if item.role_id == subject_id), None)
        return role.section_id if role else ""

    def _position(self, node_ids: tuple[str, ...], node_positions: dict[str, float]) -> float:
        values = [node_positions[node_id] for node_id in node_ids if node_id in node_positions]
        return min(values) if values else float("inf")

    def _rule_matches(
        self,
        rule,
        section_matches: dict[str, tuple[str, ...]],
        node_positions: dict[str, float],
        grammar: ReceiptGrammar,
    ) -> bool:
        present = rule.subject_id in section_matches or self._role_section_matched(
            rule.subject_id, section_matches, grammar,
        )
        if rule.rule_type is GrammarRuleType.REQUIRED:
            return present
        if rule.rule_type is GrammarRuleType.OCCURS_ONCE:
            # Multiple physical nodes may support one semantic section
            # expectation; the Grammar sidecar does not parse section instances.
            return present
        if rule.rule_type is GrammarRuleType.OPTIONAL:
            return True
        if rule.rule_type is GrammarRuleType.REPEATS:
            section = next(
                (item for item in grammar.sections if item.section_id == rule.subject_id),
                None,
            )
            role = next((item for item in grammar.roles if item.role_id == rule.subject_id), None)
            return present and bool((section and section.repeatable) or (role and role.repeatable))
        if rule.rule_type is GrammarRuleType.FOLLOWS:
            subject_section = self._subject_section(rule.subject_id, grammar)
            target_section = self._subject_section(rule.target_id, grammar)
            subject_nodes = section_matches.get(subject_section, ())
            target_nodes = section_matches.get(target_section, ())
            if not subject_nodes or not target_nodes:
                return False
            return self._position(subject_nodes, node_positions) >= self._position(target_nodes, node_positions)
        if rule.rule_type is GrammarRuleType.ENDS_DOCUMENT:
            subject_section = self._subject_section(rule.subject_id, grammar)
            subject_nodes = section_matches.get(subject_section, ())
            if not subject_nodes:
                return False
            positions = [
                self._position(nodes, node_positions)
                for nodes in section_matches.values()
                if nodes
            ]
            return bool(positions) and self._position(subject_nodes, node_positions) == max(positions)
        if rule.rule_type is GrammarRuleType.RELATIONSHIP:
            return present and (
                not rule.target_id
                or rule.target_id in section_matches
                or self._role_section_matched(rule.target_id, section_matches, grammar)
            )
        return False

    def _role_section_matched(
        self,
        role_id: str,
        section_matches: dict[str, tuple[str, ...]],
        grammar: ReceiptGrammar,
    ) -> bool:
        role = next((item for item in grammar.roles if item.role_id == role_id), None)
        return bool(role and role.section_id in section_matches)

    def _candidate_confidence(
        self,
        node_ids: tuple[str, ...],
        structure: ReceiptPhysicalStructure,
    ) -> float:
        confidence_by_id = {
            annotation.node_id: annotation.confidence for annotation in structure.region_annotations
        }
        confidence_by_id.update({table.id: table.confidence for table in structure.candidate_tables})
        values = [confidence_by_id[node_id] for node_id in node_ids if node_id in confidence_by_id]
        return round(sum(values) / len(values), 4) if values else 0.0
