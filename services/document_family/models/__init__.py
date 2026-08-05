from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DocumentFamily(str, Enum):
    RETAIL_RECEIPT = "retail_receipt"
    RESTAURANT_RECEIPT = "restaurant_receipt"
    FUEL_RECEIPT = "fuel_receipt"
    PHARMACY_RECEIPT = "pharmacy_receipt"
    PAYMENT_SLIP = "payment_slip"
    CREDIT_CARD_SLIP = "credit_card_slip"
    REFUND_RECEIPT = "refund_receipt"
    RETURN_RECEIPT = "return_receipt"
    INVOICE = "invoice"
    STATEMENT = "statement"
    WARRANTY = "warranty"
    DONATION_RECEIPT = "donation_receipt"
    UNKNOWN = "unknown"


class SemanticZoneType(str, Enum):
    MERCHANT = "merchant_zone"
    ADDRESS = "address_zone"
    ITEM = "item_zone"
    FINANCIAL = "financial_zone"
    PAYMENT = "payment_zone"
    REFERENCE = "reference_zone"
    FOOTER = "footer_zone"
    UNKNOWN = "unknown_zone"


class EntityType(str, Enum):
    MERCHANT = "merchant"
    ADDRESS = "address"
    PAYMENT_BRAND = "payment_brand"
    MASKED_PAN = "masked_pan"
    APPROVAL_CODE = "approval_code"
    AUTHORIZATION_CODE = "authorization_code"
    ENTRY_METHOD = "entry_method"
    REFERENCE_NUMBER = "reference_number"
    PAYMENT_IDENTIFIER = "payment_identifier"
    FINANCIAL_AMOUNT = "financial_amount"
    DATE = "date"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class FamilyEvidence:
    source: str
    value: str
    weight: float
    reason: str
    node_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SemanticZone:
    zone_id: str
    zone_type: SemanticZoneType
    node_ids: tuple[str, ...]
    confidence: float
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EntityCandidate:
    candidate_id: str
    entity_type: EntityType
    value: str
    confidence: float
    zone_id: str
    evidence: tuple[FamilyEvidence, ...]
    reason: str
    status: str = "candidate"


@dataclass(frozen=True, slots=True)
class KeyValueRelationship:
    relationship_id: str
    key: str
    value: str
    key_node_id: str
    value_node_id: str
    confidence: float
    strategy: str
    zone_id: str = ""
    evidence: tuple[FamilyEvidence, ...] = ()


@dataclass(frozen=True, slots=True)
class FamilyProfile:
    family: DocumentFamily
    profile_id: str
    version: int
    grammar_id: str
    constraint_set_id: str
    expected_zones: tuple[SemanticZoneType, ...]
    required_entities: tuple[EntityType, ...]
    item_table_expected: bool
    activation_terms: tuple[str, ...] = ()
    key_value_labels: tuple[str, ...] = ()
    entity_resolution_rules: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FamilyActivation:
    family: DocumentFamily
    confidence: float
    profile_id: str
    evidence: tuple[FamilyEvidence, ...]
    alternatives: tuple[tuple[str, float], ...] = ()
    reason: str = "deterministic_evidence_ranking"


@dataclass(frozen=True, slots=True)
class DocumentFamilyContext:
    document_id: str
    activation: FamilyActivation
    profile: FamilyProfile
    semantic_zones: tuple[SemanticZone, ...]
    entity_candidates: tuple[EntityCandidate, ...]
    merchant_candidates: tuple[EntityCandidate, ...]
    payment_candidates: tuple[EntityCandidate, ...]
    address_candidates: tuple[EntityCandidate, ...]
    key_value_relationships: tuple[KeyValueRelationship, ...]
    activated_grammar: str
    activated_constraints: str
    activated_rules: tuple[str, ...]
    diagnostics: tuple[tuple[str, Any], ...] = ()
    schema_version: str = "document-family-context-v1"


@dataclass(frozen=True, slots=True)
class FamilyDiagnostic:
    code: str
    message: str
    severity: str = "info"
    subject_id: str = ""


@dataclass(frozen=True, slots=True)
class RegressionFixture:
    fixture_id: str
    lines: tuple[tuple[str, float, float, float, float], ...]
    expected_family: DocumentFamily
    expected_entities: tuple[tuple[EntityType, str], ...] = ()
    expected_item_table: bool = False
    metadata: tuple[tuple[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class RegressionResult:
    fixture_id: str
    passed: bool
    checks: tuple[tuple[str, bool], ...]
    context: DocumentFamilyContext | None = None
    parser_unchanged: bool = True
