from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
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


@dataclass(frozen=True, slots=True)
class ProductVersion:
    entity_version: int = 1
    schema_version: str = "product-intelligence-v1"
    status: str = "active"
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    supersedes_version: int | None = None


@dataclass(frozen=True, slots=True)
class ProductAlias:
    value: str
    normalized_value: str = ""
    merchant_key: str = ""
    source: str = "approved_alias"
    confidence: float = 1.0


@dataclass(frozen=True, slots=True)
class ProductCategory:
    name: str
    parent: str = ""
    path: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProductDepartment:
    name: str
    code: str = ""


@dataclass(frozen=True, slots=True)
class Brand:
    name: str
    aliases: tuple[str, ...] = ()
    store_brand: bool = False
    merchant_keys: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Manufacturer:
    name: str
    identifier: str = ""


@dataclass(frozen=True, slots=True)
class PackageType:
    name: str = ""
    count: float | None = None


@dataclass(frozen=True, slots=True)
class UnitOfMeasure:
    code: str = ""
    quantity: float | None = None


@dataclass(frozen=True, slots=True)
class NutritionProfile:
    calories: float | None = None
    protein: float | None = None
    fat: float | None = None
    carbohydrates: float | None = None
    sugar: float | None = None
    fiber: float | None = None
    sodium: float | None = None
    serving_size: str = ""
    food_group: str = ""
    diet_tags: tuple[str, ...] = ()
    source: str = ""


@dataclass(frozen=True, slots=True)
class PricingProfile:
    observed_price: float | None = None
    historical_prices: tuple[float, ...] = ()
    average_price: float | None = None
    typical_range: tuple[float, float] | tuple[()] = ()
    price_variance: float | None = None
    currency: str = ""


@dataclass(frozen=True, slots=True)
class ProductConfidence:
    overall: float
    product_match: float = 0.0
    category_match: float = 0.0
    brand_match: float = 0.0
    merchant_match: float = 0.0
    knowledge_match: float = 0.0
    constraint_confidence: float = 0.0
    components: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True, slots=True)
class ProductExplanation:
    product_id: str
    summary: str
    match_reasons: tuple[str, ...] = ()
    category_reason: str = ""
    brand_reason: str = ""
    knowledge_sources: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CanonicalProduct:
    product_id: str
    canonical_name: str
    aliases: tuple[ProductAlias, ...] = ()
    department: ProductDepartment = field(default_factory=lambda: ProductDepartment("Unknown"))
    category: ProductCategory = field(default_factory=lambda: ProductCategory("Unknown"))
    subcategory: ProductCategory | None = None
    brand: Brand = field(default_factory=lambda: Brand("Unknown Brand"))
    manufacturer: Manufacturer = field(default_factory=lambda: Manufacturer("Unknown"))
    package_type: PackageType = field(default_factory=PackageType)
    unit_of_measure: UnitOfMeasure = field(default_factory=UnitOfMeasure)
    nutrition: NutritionProfile = field(default_factory=NutritionProfile)
    pricing: PricingProfile = field(default_factory=PricingProfile)
    metadata: tuple[tuple[str, Any], ...] = ()
    version: ProductVersion = field(default_factory=ProductVersion)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "metadata",
            tuple((str(key), freeze_value(value)) for key, value in self.metadata),
        )


@dataclass(frozen=True, slots=True)
class ProductMatch:
    product: CanonicalProduct | None
    strategy: str
    score: float
    matched_value: str = ""
    knowledge_source: str = ""


@dataclass(frozen=True, slots=True)
class ProductEnrichment:
    item_index: int
    original_description: str
    normalized_description: str
    canonical_product: CanonicalProduct | None
    match_strategy: str
    department: ProductDepartment
    category: ProductCategory
    subcategory: ProductCategory | None
    brand: Brand
    manufacturer: Manufacturer
    nutrition: NutritionProfile
    pricing: PricingProfile
    confidence: ProductConfidence
    explanation: ProductExplanation


@dataclass(frozen=True, slots=True)
class ProductDiagnostic:
    code: str
    message: str
    severity: str = "info"
    item_index: int | None = None


@dataclass(frozen=True, slots=True)
class ProductDiagnostics:
    errors: tuple[ProductDiagnostic, ...] = ()
    warnings: tuple[ProductDiagnostic, ...] = ()
    information: tuple[ProductDiagnostic, ...] = ()
    sidecar: bool = True
    affects_extraction: bool = False
    parser_authority_changed: bool = False
    extracted_values_replaced: bool = False

    @property
    def valid(self) -> bool:
        return not self.errors


@dataclass(frozen=True, slots=True)
class ProductLearningSuggestion:
    suggestion_type: str
    description: str
    original_description: str
    proposed_value: Any = None
    evidence_references: tuple[str, ...] = ()
    confidence: float = 0.0
    requires_approval: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposed_value", freeze_value(self.proposed_value))


@dataclass(frozen=True, slots=True)
class ProductVersionComparison:
    product_id: str
    from_version: int
    to_version: int
    changed_fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProductRepositoryIndex:
    product_ids: tuple[str, ...] = ()
    versions: tuple[tuple[str, int], ...] = ()
    schema_version: str = "product-repository-index-v1"


@dataclass(frozen=True, slots=True)
class ProductIntelligenceResult:
    enrichments: tuple[ProductEnrichment, ...] = ()
    diagnostics: ProductDiagnostics = field(default_factory=ProductDiagnostics)
    learning_suggestions: tuple[ProductLearningSuggestion, ...] = ()
    repository_version: str = "product-intelligence-v1"
    schema_version: str = "product-intelligence-result-v1"
