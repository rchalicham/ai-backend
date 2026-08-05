from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def freeze_value(value: Any) -> Any:
    if isinstance(value, dict):
        return tuple((str(k), freeze_value(v)) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return tuple(freeze_value(v) for v in value)
    if isinstance(value, set):
        return tuple(sorted((freeze_value(v) for v in value), key=str))
    return value


class HouseholdRole(str, Enum):
    ADULT = "Adult"
    CHILD = "Child"
    SENIOR = "Senior"
    GUEST = "Guest"
    PET = "Pet"
    UNKNOWN = "Unknown"


@dataclass(frozen=True, slots=True)
class HouseholdMember:
    member_id: str
    display_name: str
    role: HouseholdRole | str
    household_id: str
    evidence_ids: tuple[str, ...] = ()
    history: tuple[str, ...] = ()
    confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class Relationship:
    relationship_id: str
    source_member_id: str
    target_member_id: str
    relationship_type: str
    evidence_ids: tuple[str, ...]
    confidence: float


@dataclass(frozen=True, slots=True)
class Ownership:
    ownership_id: str
    subject_id: str
    owner_member_ids: tuple[str, ...]
    ownership_type: str
    status: str = "active"
    evidence_ids: tuple[str, ...] = ()
    confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class Responsibility:
    responsibility_id: str
    member_ids: tuple[str, ...]
    responsibility_type: str
    subject_id: str = ""
    shared: bool = False
    evidence_ids: tuple[str, ...] = ()
    confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class ConsumptionRecord:
    consumption_id: str
    consumer_ids: tuple[str, ...]
    subject_id: str
    consumption_type: str
    quantity: float = 0.0
    unit: str = ""
    occurred_at: str = ""
    evidence_ids: tuple[str, ...] = ()
    confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class Preference:
    preference_id: str
    subject_member_ids: tuple[str, ...]
    preference_type: str
    value: str
    evidence_ids: tuple[str, ...]
    confidence: float


@dataclass(frozen=True, slots=True)
class Goal:
    goal_id: str
    owner_ids: tuple[str, ...]
    goal_type: str
    title: str
    target: str = ""
    status: str = "informational"
    evidence_ids: tuple[str, ...] = ()
    predictive: bool = False


@dataclass(frozen=True, slots=True)
class HouseholdAsset:
    asset_id: str
    household_id: str
    asset_type: str
    name: str
    owner_member_ids: tuple[str, ...] = ()
    acquired_at: str = ""
    status: str = "active"
    warranty_id: str = ""
    evidence_ids: tuple[str, ...] = ()
    confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class Vehicle:
    vehicle_id: str
    household_id: str
    name: str
    owner_member_ids: tuple[str, ...] = ()
    registration: str = ""
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Property:
    property_id: str
    household_id: str
    name: str
    property_type: str
    owner_member_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Pet:
    pet_id: str
    household_id: str
    name: str
    species: str
    breed: str = ""
    owner_member_ids: tuple[str, ...] = ()
    food_product_ids: tuple[str, ...] = ()
    medication_ids: tuple[str, ...] = ()
    supply_product_ids: tuple[str, ...] = ()
    veterinarian: str = ""
    insurance_id: str = ""
    expense_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Household:
    household_id: str
    name: str
    member_ids: tuple[str, ...] = ()
    asset_ids: tuple[str, ...] = ()
    pet_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    version: int = 1


@dataclass(frozen=True, slots=True)
class HouseholdInsight:
    insight_id: str
    insight_type: str
    title: str
    value: str | float
    subject_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    explanation_id: str
    confidence: float


@dataclass(frozen=True, slots=True)
class HouseholdRecommendation:
    recommendation_id: str
    recommendation_type: str
    title: str
    description: str
    subject_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    confidence: float
    requires_human_decision: bool = True


@dataclass(frozen=True, slots=True)
class HouseholdConfidence:
    overall: float
    reasoning: float = 0.0
    learning: float = 0.0
    cross_document: float = 0.0
    knowledge_graph: float = 0.0
    expense: float = 0.0
    household_evidence: float = 0.0
    components: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True, slots=True)
class HouseholdExplanation:
    explanation_id: str
    subject_id: str
    summary: str
    evidence_ids: tuple[str, ...]
    receipt_ids: tuple[str, ...] = ()
    product_ids: tuple[str, ...] = ()
    relationship_ids: tuple[str, ...] = ()
    history_references: tuple[str, ...] = ()
    reasoning_steps: tuple[str, ...] = ()
    confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class HouseholdDiagnostics:
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    information: tuple[str, ...] = ()
    business_capability: bool = True
    authentication_logic_used: bool = False
    identity_management_used: bool = False
    platform_services_modified: bool = False
    expense_intelligence_modified: bool = False
    parser_modified: bool = False
    extraction_modified: bool = False
    enterprise_knowledge_modified: bool = False
    graph_modified: bool = False
    learning_modified: bool = False
    reasoning_modified: bool = False
    prediction_performed: bool = False

    @property
    def valid(self):
        return not self.errors


@dataclass(frozen=True, slots=True)
class HouseholdProfile:
    household: Household
    members: tuple[HouseholdMember, ...] = ()
    relationships: tuple[Relationship, ...] = ()
    ownership: tuple[Ownership, ...] = ()
    responsibilities: tuple[Responsibility, ...] = ()
    consumption: tuple[ConsumptionRecord, ...] = ()
    preferences: tuple[Preference, ...] = ()
    goals: tuple[Goal, ...] = ()
    assets: tuple[HouseholdAsset, ...] = ()
    vehicles: tuple[Vehicle, ...] = ()
    properties: tuple[Property, ...] = ()
    pets: tuple[Pet, ...] = ()
    monthly_spending: float = 0.0
    shopping_habits: tuple[str, ...] = ()
    health_indicators: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HouseholdIntelligenceResult:
    profile: HouseholdProfile
    insights: tuple[HouseholdInsight, ...] = ()
    recommendations: tuple[HouseholdRecommendation, ...] = ()
    explanations: tuple[HouseholdExplanation, ...] = ()
    confidence: HouseholdConfidence = field(default_factory=lambda: HouseholdConfidence(0.0))
    diagnostics: HouseholdDiagnostics = field(default_factory=HouseholdDiagnostics)
    generated_at: str = field(default_factory=utc_now)
    schema_version: str = "household-intelligence-result-v1"
