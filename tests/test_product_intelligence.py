import os
import sys
from dataclasses import FrozenInstanceError, replace

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.product_intelligence import (
    Brand,
    CanonicalProduct,
    Manufacturer,
    ProductAlias,
    ProductBrandEngine,
    ProductCategory,
    ProductConfidenceEngine,
    ProductDepartment,
    ProductIntelligenceEngine,
    ProductIntelligenceSerializer,
    ProductLearningService,
    ProductLoader,
    ProductMatcher,
    ProductNormalizer,
    ProductRepository,
)


def milk() -> CanonicalProduct:
    return CanonicalProduct(
        product_id="milk",
        canonical_name="Milk",
        aliases=(
            ProductAlias("MLK 2%", "Milk 2 Percent", source="global-alias"),
            ProductAlias("GV 2P MLK", "Great Value 2P Milk", merchant_key="walmart", source="merchant-alias"),
        ),
        department=ProductDepartment("Food"),
        category=ProductCategory("Dairy", parent="Grocery", path=("Grocery", "Dairy")),
        subcategory=ProductCategory("Milk", parent="Dairy"),
        brand=Brand("Great Value", store_brand=True, merchant_keys=("walmart",)),
        manufacturer=Manufacturer("Walmart"),
        metadata=(("source", {"repository": "approved"}),),
    )


def repository() -> ProductRepository:
    value = ProductRepository()
    value.saveProducts(milk())
    value.saveProducts(CanonicalProduct(
        product_id="eggs",
        canonical_name="Eggs",
        aliases=(ProductAlias("WMT EGGS", "Eggs", merchant_key="walmart"),),
        department=ProductDepartment("Food"),
        category=ProductCategory("Dairy"),
    ))
    return value


def test_models_are_immutable_and_nested_metadata_is_frozen():
    product = milk()
    with pytest.raises(FrozenInstanceError):
        product.canonical_name = "Changed"
    assert product.metadata == (("source", (("repository", "approved"),)),)


def test_normalization_preserves_original_outside_normalizer():
    normalizer = ProductNormalizer()
    assert normalizer.normalize("MLK 2%") == "Milk 2 Percent"
    assert normalizer.normalize("  WMT   EGGS ") == "Eggs"
    assert normalizer.normalize("0IL") == "Oil"


def test_matcher_supports_exact_normalized_alias_merchant_fuzzy_and_historical():
    products = repository().loadProducts()
    matcher = ProductMatcher(fuzzy_threshold=0.7)
    assert matcher.match("Milk", "Milk", products).strategy == "exact"
    assert matcher.match("milk", "Milk", products).strategy == "normalized"
    assert matcher.match("MLK 2%", "Milk 2 Percent", products).strategy == "alias"
    assert matcher.match("GV 2P MLK", "Great Value 2P Milk", products, "walmart").strategy == "merchant_specific"
    assert matcher.match("Milkk", "Milkk", products).strategy == "fuzzy"
    historical = matcher.match("Mylk", "Mylk", products, historical_product_ids=("milk",))
    assert historical.strategy == "historical"
    embedding = ProductMatcher(
        fuzzy_threshold=1.0,
        embedding_matcher=lambda _text, _products: ("milk", 0.88),
    ).match("Dairy Beverage", "Dairy Beverage", products)
    assert embedding.strategy == "embedding"


def test_engine_enriches_without_mutating_extracted_items():
    items = [{"name": "MLK 2%", "price": "$3.49", "quantity": 1}]
    before = [dict(item) for item in items]
    result = ProductIntelligenceEngine(repository=repository()).enrich(
        items, merchant_key="walmart", currency="USD",
    )
    assert items == before
    enrichment = result.enrichments[0]
    assert enrichment.original_description == "MLK 2%"
    assert enrichment.normalized_description == "Milk 2 Percent"
    assert enrichment.canonical_product.canonical_name == "Milk"
    assert enrichment.category.name == "Dairy"
    assert enrichment.brand.name == "Great Value"
    assert enrichment.pricing.observed_price == 3.49
    assert enrichment.explanation.product_id == "milk"
    assert result.diagnostics.affects_extraction is False
    assert result.diagnostics.parser_authority_changed is False


def test_unmatched_product_classifies_and_generates_approval_only_suggestion():
    result = ProductIntelligenceEngine(repository=repository()).enrich(
        ({"description": "Laundry Detergent", "lineTotal": "8.99"},),
    )
    enrichment = result.enrichments[0]
    assert enrichment.canonical_product is None
    assert enrichment.department.name == "Household"
    assert enrichment.match_strategy == "unmatched"
    assert result.diagnostics.warnings[0].code == "canonical_product_not_matched"
    assert result.learning_suggestions[0].requires_approval is True


def test_brand_engine_supports_store_brands_and_unknown():
    engine = ProductBrandEngine()
    brand, manufacturer, confidence, _ = engine.identify(None, "Kirkland Olive Oil", "costco")
    assert brand.name == "Kirkland"
    assert brand.store_brand is True
    assert manufacturer.name == "Costco"
    assert confidence == 0.85
    assert engine.identify(None, "Generic Item")[0].name == "Unknown Brand"


def test_confidence_aggregates_without_overwriting_inputs():
    confidence = ProductConfidenceEngine().aggregate(
        product_match=1.0,
        category_match=0.8,
        brand_match=0.6,
        merchant_match=0.4,
        knowledge_match=1.0,
        constraint_confidence=0.9,
    )
    assert confidence.overall == pytest.approx(0.855)
    assert confidence.constraint_confidence == 0.9
    assert dict(confidence.components)["product_match"] == 1.0


def test_repository_version_archive_compare_and_index():
    repo = ProductRepository()
    first = repo.saveProducts(milk())[0]
    second = repo.versionProducts(replace(first, canonical_name="Milk 2 Percent"), expected_version=1)
    assert second.version.entity_version == 2
    comparison = repo.compareProducts("milk", 1, 2)
    assert comparison.changed_fields == ("canonical_name",)
    assert repo.index().versions == (("milk", 2),)
    archived = repo.archiveProducts("milk", 2)
    assert archived.version.status == "archived"
    assert repo.loadProducts("milk") == (first,)


def test_repository_rejects_identity_and_version_conflicts():
    repo = ProductRepository()
    repo.saveProducts(milk())
    with pytest.raises(ValueError, match="already_exists"):
        repo.saveProducts(milk())
    with pytest.raises(ValueError, match="version_conflict"):
        repo.versionProducts(milk(), expected_version=9)


def test_serialization_and_loading_round_trip_core_knowledge():
    serializer = ProductIntelligenceSerializer()
    loader = ProductLoader()
    payload = serializer.to_json(milk())
    loaded = loader.from_json(payload)
    assert loaded.product_id == "milk"
    assert loaded.aliases[0].value == "MLK 2%"
    result_payload = serializer.to_dict(ProductIntelligenceEngine(repository=repository()).enrich(({"name": "Milk"},)))
    assert result_payload["diagnostics"]["valid"] is True
    assert result_payload["diagnostics"]["affects_extraction"] is False


def test_learning_never_applies_a_suggestion():
    result = ProductIntelligenceEngine().enrich(({"name": "Mystery SKU"},))
    suggestions = ProductLearningService().suggest(result.enrichments)
    assert suggestions
    assert all(item.requires_approval for item in suggestions)
    assert ProductIntelligenceEngine().repository.loadProducts() == ()


def test_safe_enrich_degrades_without_touching_extraction():
    class BrokenRepository(ProductRepository):
        def load_products(self, *args, **kwargs):
            raise RuntimeError("unavailable")

    items = [{"name": "Milk"}]
    result = ProductIntelligenceEngine(repository=BrokenRepository()).safe_enrich(items)
    assert result.enrichments == ()
    assert result.diagnostics.errors[0].code == "product_sidecar_failed"
    assert items == [{"name": "Milk"}]
