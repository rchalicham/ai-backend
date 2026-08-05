from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GrammarSectionType(str, Enum):
    HEADER = "header"
    MERCHANT_AREA = "merchant_area"
    ADDRESS_AREA = "address_area"
    BODY = "body"
    ITEMS = "items"
    FINANCIAL_SUMMARY = "financial_summary"
    PAYMENT = "payment"
    FOOTER = "footer"
    UNKNOWN = "unknown"


class GrammarRoleType(str, Enum):
    MERCHANT = "merchant"
    ADDRESS = "address"
    ITEM = "item"
    FINANCIAL = "financial"
    PAYMENT = "payment"
    REFERENCE = "reference"
    METADATA = "metadata"
    UNKNOWN = "unknown"


class GrammarRelationshipType(str, Enum):
    PARENT = "parent"
    CHILD = "child"
    SIBLING = "sibling"
    BEFORE = "before"
    AFTER = "after"
    CONTAINS = "contains"
    ADJACENT = "adjacent"
    OPTIONAL = "optional"
    REQUIRED = "required"


class GrammarTransitionType(str, Enum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    ALTERNATIVE = "alternative"
    REPEATING = "repeating"


class GrammarRuleType(str, Enum):
    OCCURS_ONCE = "occurs_once"
    REQUIRED = "required"
    OPTIONAL = "optional"
    REPEATS = "repeats"
    FOLLOWS = "follows"
    ENDS_DOCUMENT = "ends_document"
    RELATIONSHIP = "relationship"


class GrammarDiagnosticSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class GrammarVersion:
    entity_version: int = 1
    schema_version: str = "receipt-grammar-v1"
    status: str = "active"
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    supersedes_version: int | None = None


@dataclass(frozen=True, slots=True)
class GrammarMetadata:
    grammar_id: str
    receipt_family: str
    name: str
    description: str = ""
    source: str = "authored"
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GrammarConfidence:
    overall: float = 1.0
    components: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True, slots=True)
class GrammarExpectation:
    expectation_id: str
    subject_id: str
    description: str
    required: bool = False
    confidence: float = 1.0
    attributes: tuple[tuple[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class GrammarRole:
    role_id: str
    role_type: GrammarRoleType
    section_id: str
    required: bool = False
    repeatable: bool = False
    expectation_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GrammarSection:
    section_id: str
    section_type: GrammarSectionType
    name: str
    role_ids: tuple[str, ...] = ()
    required: bool = False
    repeatable: bool = False
    minimum_occurrences: int = 0
    maximum_occurrences: int | None = 1


@dataclass(frozen=True, slots=True)
class GrammarRelationship:
    relationship_id: str
    source_id: str
    target_id: str
    relationship_type: GrammarRelationshipType
    required: bool = False


@dataclass(frozen=True, slots=True)
class GrammarTransition:
    transition_id: str
    source_section_id: str
    target_section_id: str
    transition_type: GrammarTransitionType


@dataclass(frozen=True, slots=True)
class GrammarRule:
    rule_id: str
    rule_type: GrammarRuleType
    subject_id: str
    target_id: str = ""
    description: str = ""
    required: bool = True


@dataclass(frozen=True, slots=True)
class GrammarDiagnostic:
    code: str
    message: str
    severity: GrammarDiagnosticSeverity
    subject_id: str = ""


@dataclass(frozen=True, slots=True)
class GrammarDiagnostics:
    errors: tuple[GrammarDiagnostic, ...] = ()
    warnings: tuple[GrammarDiagnostic, ...] = ()
    information: tuple[GrammarDiagnostic, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.errors


@dataclass(frozen=True, slots=True)
class ReceiptGrammar:
    metadata: GrammarMetadata
    version: GrammarVersion
    sections: tuple[GrammarSection, ...]
    roles: tuple[GrammarRole, ...] = ()
    relationships: tuple[GrammarRelationship, ...] = ()
    transitions: tuple[GrammarTransition, ...] = ()
    rules: tuple[GrammarRule, ...] = ()
    expectations: tuple[GrammarExpectation, ...] = ()
    confidence: GrammarConfidence = field(default_factory=GrammarConfidence)


@dataclass(frozen=True, slots=True)
class GrammarCompilation:
    grammar: ReceiptGrammar
    diagnostics: GrammarDiagnostics
    ordered_section_ids: tuple[str, ...] = ()
    schema_version: str = "receipt-grammar-compilation-v1"

    @property
    def valid(self) -> bool:
        return self.diagnostics.valid


@dataclass(frozen=True, slots=True)
class CandidateGrammarRole:
    role_id: str
    role_type: GrammarRoleType
    section_id: str
    source_node_ids: tuple[str, ...]
    confidence: float
    basis: str = "physical_structure_compatibility"


@dataclass(frozen=True, slots=True)
class GrammarCompliance:
    document_id: str
    grammar_id: str
    grammar_version: int
    overall_compliance: float
    matched_rules: tuple[str, ...] = ()
    missing_rules: tuple[str, ...] = ()
    violations: tuple[GrammarDiagnostic, ...] = ()
    warnings: tuple[GrammarDiagnostic, ...] = ()
    candidate_roles: tuple[CandidateGrammarRole, ...] = ()
    matched_sections: tuple[str, ...] = ()
    schema_version: str = "receipt-grammar-compliance-v1"


@dataclass(frozen=True, slots=True)
class GrammarLearningSuggestion:
    suggestion_type: str
    receipt_family: str
    subject_id: str
    description: str
    evidence_references: tuple[str, ...] = ()
    confidence: float = 0.0
    requires_approval: bool = True


@dataclass(frozen=True, slots=True)
class GrammarVersionComparison:
    grammar_id: str
    from_version: int
    to_version: int
    added_sections: tuple[str, ...] = ()
    removed_sections: tuple[str, ...] = ()
    added_rules: tuple[str, ...] = ()
    removed_rules: tuple[str, ...] = ()
    changed_transitions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReceiptGrammarContext:
    receipt_family: str
    loaded: bool
    grammar: ReceiptGrammar | None = None
    compilation: GrammarCompilation | None = None
    compliance: GrammarCompliance | None = None
    learning_suggestions: tuple[GrammarLearningSuggestion, ...] = ()
    diagnostics: tuple[tuple[str, Any], ...] = ()
    schema_version: str = "receipt-grammar-context-v1"

