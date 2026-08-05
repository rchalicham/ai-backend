from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .models import (
    GrammarConfidence,
    GrammarExpectation,
    GrammarMetadata,
    GrammarRelationship,
    GrammarRelationshipType,
    GrammarRole,
    GrammarRoleType,
    GrammarRule,
    GrammarRuleType,
    GrammarSection,
    GrammarSectionType,
    GrammarTransition,
    GrammarTransitionType,
    GrammarVersion,
    ReceiptGrammar,
)


class ReceiptGrammarLoader:
    """Loads declarative grammar data without compiling or executing parsing."""

    def from_json(self, payload: str) -> ReceiptGrammar:
        value = json.loads(payload)
        if not isinstance(value, dict):
            raise ValueError("receipt_grammar_definition_must_be_an_object")
        return self.from_dict(value)

    def from_file(self, path: str | Path) -> ReceiptGrammar:
        return self.from_json(Path(path).read_text(encoding="utf-8"))

    def from_dict(self, payload: Mapping[str, Any]) -> ReceiptGrammar:
        metadata = self._mapping(payload.get("metadata"))
        version = self._mapping(payload.get("version"))
        confidence = self._mapping(payload.get("confidence"))
        return ReceiptGrammar(
            metadata=GrammarMetadata(
                grammar_id=str(metadata.get("grammar_id") or metadata.get("grammarId") or ""),
                receipt_family=str(metadata.get("receipt_family") or metadata.get("receiptFamily") or ""),
                name=str(metadata.get("name") or ""),
                description=str(metadata.get("description") or ""),
                source=str(metadata.get("source") or "authored"),
                tags=self._strings(metadata.get("tags")),
            ),
            version=GrammarVersion(
                entity_version=int(version.get("entity_version") or version.get("entityVersion") or 1),
                schema_version=str(version.get("schema_version") or version.get("schemaVersion") or "receipt-grammar-v1"),
                status=str(version.get("status") or "active"),
                created_at=str(version.get("created_at") or version.get("createdAt") or GrammarVersion().created_at),
                updated_at=str(version.get("updated_at") or version.get("updatedAt") or GrammarVersion().updated_at),
                supersedes_version=self._optional_int(version.get("supersedes_version", version.get("supersedesVersion"))),
            ),
            sections=tuple(self._section(item) for item in self._mappings(payload.get("sections"))),
            roles=tuple(self._role(item) for item in self._mappings(payload.get("roles"))),
            relationships=tuple(self._relationship(item) for item in self._mappings(payload.get("relationships"))),
            transitions=tuple(self._transition(item) for item in self._mappings(payload.get("transitions"))),
            rules=tuple(self._rule(item) for item in self._mappings(payload.get("rules"))),
            expectations=tuple(self._expectation(item) for item in self._mappings(payload.get("expectations"))),
            confidence=GrammarConfidence(
                overall=float(confidence.get("overall", 1.0)),
                components=self._pairs(confidence.get("components")),
            ),
        )

    def _section(self, value: Mapping[str, Any]) -> GrammarSection:
        section_id = str(value.get("section_id") or value.get("sectionId") or "")
        section_type = value.get("section_type") or value.get("sectionType") or "unknown"
        return GrammarSection(
            section_id=section_id,
            section_type=GrammarSectionType(str(section_type)),
            name=str(value.get("name") or section_id),
            role_ids=self._strings(value.get("role_ids", value.get("roleIds"))),
            required=bool(value.get("required", False)),
            repeatable=bool(value.get("repeatable", False)),
            minimum_occurrences=int(value.get("minimum_occurrences", value.get("minimumOccurrences", 0))),
            maximum_occurrences=self._optional_int(
                value.get("maximum_occurrences", value.get("maximumOccurrences", 1)),
            ),
        )

    def _role(self, value: Mapping[str, Any]) -> GrammarRole:
        return GrammarRole(
            role_id=str(value.get("role_id") or value.get("roleId") or ""),
            role_type=GrammarRoleType(str(value.get("role_type") or value.get("roleType") or "unknown")),
            section_id=str(value.get("section_id") or value.get("sectionId") or ""),
            required=bool(value.get("required", False)),
            repeatable=bool(value.get("repeatable", False)),
            expectation_ids=self._strings(value.get("expectation_ids", value.get("expectationIds"))),
        )

    def _relationship(self, value: Mapping[str, Any]) -> GrammarRelationship:
        return GrammarRelationship(
            relationship_id=str(value.get("relationship_id") or value.get("relationshipId") or ""),
            source_id=str(value.get("source_id") or value.get("sourceId") or ""),
            target_id=str(value.get("target_id") or value.get("targetId") or ""),
            relationship_type=GrammarRelationshipType(
                str(value.get("relationship_type") or value.get("relationshipType") or "adjacent"),
            ),
            required=bool(value.get("required", False)),
        )

    def _transition(self, value: Mapping[str, Any]) -> GrammarTransition:
        return GrammarTransition(
            transition_id=str(value.get("transition_id") or value.get("transitionId") or ""),
            source_section_id=str(value.get("source_section_id") or value.get("sourceSectionId") or ""),
            target_section_id=str(value.get("target_section_id") or value.get("targetSectionId") or ""),
            transition_type=GrammarTransitionType(
                str(value.get("transition_type") or value.get("transitionType") or "optional"),
            ),
        )

    def _rule(self, value: Mapping[str, Any]) -> GrammarRule:
        return GrammarRule(
            rule_id=str(value.get("rule_id") or value.get("ruleId") or ""),
            rule_type=GrammarRuleType(str(value.get("rule_type") or value.get("ruleType") or "optional")),
            subject_id=str(value.get("subject_id") or value.get("subjectId") or ""),
            target_id=str(value.get("target_id") or value.get("targetId") or ""),
            description=str(value.get("description") or ""),
            required=bool(value.get("required", True)),
        )

    def _expectation(self, value: Mapping[str, Any]) -> GrammarExpectation:
        attributes = value.get("attributes")
        return GrammarExpectation(
            expectation_id=str(value.get("expectation_id") or value.get("expectationId") or ""),
            subject_id=str(value.get("subject_id") or value.get("subjectId") or ""),
            description=str(value.get("description") or ""),
            required=bool(value.get("required", False)),
            confidence=float(value.get("confidence", 1.0)),
            attributes=self._pairs(attributes),
        )

    def _mapping(self, value: Any) -> Mapping[str, Any]:
        return value if isinstance(value, Mapping) else {}

    def _mappings(self, value: Any) -> tuple[Mapping[str, Any], ...]:
        return tuple(item for item in (value or ()) if isinstance(item, Mapping))

    def _strings(self, value: Any) -> tuple[str, ...]:
        return tuple(str(item) for item in (value or ()))

    def _pairs(self, value: Any) -> tuple[tuple[str, Any], ...]:
        if isinstance(value, Mapping):
            return tuple((str(key), item) for key, item in value.items())
        return tuple((str(item[0]), item[1]) for item in (value or ()) if len(item) == 2)

    def _optional_int(self, value: Any) -> int | None:
        return None if value is None else int(value)

