from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def freeze_value(value: Any) -> Any:
    if isinstance(value, dict):
        return tuple((str(key), freeze_value(item)) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return tuple(freeze_value(item) for item in value)
    if isinstance(value, set):
        return tuple(sorted((freeze_value(item) for item in value), key=str))
    return value


class EntityType(str, Enum):
    MERCHANT = "Merchant"
    STORE = "Store"
    PRODUCT = "Product"
    BRAND = "Brand"
    MANUFACTURER = "Manufacturer"
    CATEGORY = "Category"
    DEPARTMENT = "Department"
    RECEIPT = "Receipt"
    LINE_ITEM = "LineItem"
    NUTRITION = "Nutrition"
    INGREDIENT = "Ingredient"
    UNIT_OF_MEASURE = "UnitOfMeasure"
    CURRENCY = "Currency"
    LOCATION = "Location"
    CUSTOMER = "Customer"
    PURCHASE = "Purchase"
    PRICE = "Price"
    TAX = "Tax"
    PAYMENT_METHOD = "PaymentMethod"
    DOCUMENT = "Document"
    UNKNOWN = "Unknown"


class RelationshipType(str, Enum):
    BELONGS_TO = "BELONGS_TO"
    PART_OF = "PART_OF"
    PURCHASED_FROM = "PURCHASED_FROM"
    HAS_BRAND = "HAS_BRAND"
    HAS_CATEGORY = "HAS_CATEGORY"
    HAS_MANUFACTURER = "HAS_MANUFACTURER"
    HAS_PARENT = "HAS_PARENT"
    HAS_CHILD = "HAS_CHILD"
    CONTAINS = "CONTAINS"
    RELATED_TO = "RELATED_TO"
    PURCHASED_WITH = "PURCHASED_WITH"
    SIMILAR_TO = "SIMILAR_TO"
    SOLD_BY = "SOLD_BY"
    LOCATED_AT = "LOCATED_AT"
    USES = "USES"
    SUPPORTS = "SUPPORTS"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class EntityId:
    value: str
    namespace: str = "opengrit"

    def __str__(self) -> str:
        return f"{self.namespace}:{self.value}"


@dataclass(frozen=True, slots=True)
class EntityProperty:
    name: str
    value: Any
    source: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", freeze_value(self.value))


@dataclass(frozen=True, slots=True)
class EntityMetadata:
    created_at: str = field(default_factory=utc_now)
    version: str = "enterprise-graph-v1"
    provenance: tuple[str, ...] = ()
    source: str = ""


@dataclass(frozen=True, slots=True)
class EnterpriseEntity:
    entity_id: EntityId
    entity_type: EntityType | str
    label: str
    properties: tuple[EntityProperty, ...] = ()
    metadata: EntityMetadata = field(default_factory=EntityMetadata)


@dataclass(frozen=True, slots=True)
class RelationshipWeight:
    value: float = 1.0
    basis: str = "direct_evidence"


@dataclass(frozen=True, slots=True)
class GraphConfidence:
    value: float
    components: tuple[tuple[str, float], ...] = ()
    upstream_values: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True, slots=True)
class Relationship:
    relationship_id: str
    relationship_type: RelationshipType | str
    source_id: EntityId
    target_id: EntityId
    weight: RelationshipWeight = field(default_factory=RelationshipWeight)
    confidence: GraphConfidence = field(default_factory=lambda: GraphConfidence(1.0))
    evidence_sources: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ()
    timestamp: str = field(default_factory=utc_now)
    version: str = "enterprise-graph-relationship-v1"
    explanation: str = ""
    creation_source: str = "enterprise_graph_builder"


@dataclass(frozen=True, slots=True)
class GraphNode:
    entity: EnterpriseEntity

    @property
    def id(self) -> str:
        return str(self.entity.entity_id)


@dataclass(frozen=True, slots=True)
class GraphEdge:
    relationship: Relationship

    @property
    def id(self) -> str:
        return self.relationship.relationship_id


@dataclass(frozen=True, slots=True)
class GraphVersion:
    entity_version: int = 1
    schema_version: str = "enterprise-knowledge-graph-v1"
    status: str = "active"
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    supersedes_version: int | None = None


@dataclass(frozen=True, slots=True)
class GraphSubgraph:
    graph_id: str
    nodes: tuple[GraphNode, ...] = ()
    edges: tuple[GraphEdge, ...] = ()
    version: GraphVersion = field(default_factory=GraphVersion)
    ontology_version: str = "enterprise-ontology-v1"


@dataclass(frozen=True, slots=True)
class GraphQuery:
    query_type: str
    entity_id: str = ""
    entity_type: EntityType | str = EntityType.UNKNOWN
    relationship_type: RelationshipType | str = RelationshipType.UNKNOWN
    value: str = ""
    max_depth: int = 1
    limit: int = 100


@dataclass(frozen=True, slots=True)
class GraphResult:
    query: GraphQuery
    nodes: tuple[GraphNode, ...] = ()
    edges: tuple[GraphEdge, ...] = ()
    paths: tuple[tuple[str, ...], ...] = ()
    explanations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GraphDiagnostic:
    code: str
    message: str
    severity: str = "info"
    subject_id: str = ""


@dataclass(frozen=True, slots=True)
class GraphDiagnostics:
    errors: tuple[GraphDiagnostic, ...] = ()
    warnings: tuple[GraphDiagnostic, ...] = ()
    information: tuple[GraphDiagnostic, ...] = ()
    sidecar: bool = True
    affects_extraction: bool = False
    parser_authority_changed: bool = False
    storage_write_performed: bool = False

    @property
    def valid(self) -> bool:
        return not self.errors


@dataclass(frozen=True, slots=True)
class GraphLearningSuggestion:
    suggestion_type: str
    description: str
    proposed_value: Any = None
    evidence_references: tuple[str, ...] = ()
    confidence: float = 0.0
    requires_approval: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposed_value", freeze_value(self.proposed_value))


@dataclass(frozen=True, slots=True)
class GraphVersionComparison:
    graph_id: str
    from_version: int
    to_version: int
    added_nodes: tuple[str, ...] = ()
    removed_nodes: tuple[str, ...] = ()
    changed_nodes: tuple[str, ...] = ()
    added_edges: tuple[str, ...] = ()
    removed_edges: tuple[str, ...] = ()
    changed_edges: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EnterpriseGraphContext:
    graph: GraphSubgraph
    diagnostics: GraphDiagnostics
    learning_suggestions: tuple[GraphLearningSuggestion, ...] = ()
    explanations: tuple[str, ...] = ()
    schema_version: str = "enterprise-graph-context-v1"

