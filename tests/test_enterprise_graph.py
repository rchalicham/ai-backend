import os
import sys
from dataclasses import FrozenInstanceError, replace

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.enterprise_graph import (
    EnterpriseEntity,
    EnterpriseGraphBuilder,
    EnterpriseGraphEngine,
    EnterpriseGraphLearningService,
    EnterpriseGraphLoader,
    EnterpriseGraphQueryEngine,
    EnterpriseGraphRepository,
    EnterpriseGraphSerializer,
    EnterpriseGraphValidator,
    EnterpriseOntology,
    EntityDefinition,
    EntityId,
    EntityProperty,
    EntityType,
    GraphConfidence,
    GraphEdge,
    GraphNode,
    GraphQuery,
    GraphSubgraph,
    Relationship,
    RelationshipDefinition,
    RelationshipType,
)
from services.product_intelligence import (
    Brand,
    CanonicalProduct,
    Manufacturer,
    NutritionProfile,
    PricingProfile,
    ProductAlias,
    ProductCategory,
    ProductDepartment,
    ProductIntelligenceEngine,
    ProductRepository,
)


def product_result():
    repository = ProductRepository()
    repository.saveProducts(CanonicalProduct(
        product_id="milk",
        canonical_name="Milk",
        aliases=(ProductAlias("MLK 2%", "Milk 2 Percent", merchant_key="walmart"),),
        department=ProductDepartment("Grocery"),
        category=ProductCategory("Dairy", parent="Grocery"),
        brand=Brand("Great Value", store_brand=True),
        manufacturer=Manufacturer("Walmart"),
        nutrition=NutritionProfile(calories=120, protein=8, source="approved-nutrition"),
        pricing=PricingProfile(historical_prices=(3.29, 3.39), currency="USD"),
    ))
    return ProductIntelligenceEngine(repository=repository).enrich(
        ({"name": "MLK 2%", "price": "3.49"},),
        merchant_key="walmart",
        currency="USD",
    )


def graph():
    return EnterpriseGraphBuilder().build(
        product_result(),
        receipt_id="receipt-1",
        merchant_key="walmart",
        receipt_context={"transactionDate": "2026-07-27", "total": "3.49"},
    )


def test_graph_models_are_immutable_and_properties_are_deeply_frozen():
    entity = EnterpriseEntity(
        EntityId("one", "test"),
        "CustomEntity",
        "One",
        (EntityProperty("nested", {"value": [1, 2]}),),
    )
    with pytest.raises(FrozenInstanceError):
        entity.label = "Changed"
    assert entity.properties[0].value == (("value", (1, 2)),)


def test_ontology_contains_initial_contract_and_supports_extensions():
    ontology = EnterpriseOntology(
        entity_definitions=(EntityDefinition("HealthcareClaim", "A normalized claim."),),
        relationship_definitions=(RelationshipDefinition("ADJUDICATES", "Claim adjudication."),),
        domain_extensions=("healthcare-v1",),
    )
    assert ontology.supports_entity(EntityType.PRODUCT)
    assert ontology.supports_relationship(RelationshipType.PURCHASED_FROM)
    assert ontology.supports_entity("HealthcareClaim")
    assert ontology.supports_relationship("ADJUDICATES")
    assert ontology.schema.domain_extensions == ("healthcare-v1",)


def test_builder_constructs_canonical_entities_and_provenance_edges():
    value = graph()
    types = {node.entity.entity_type for node in value.nodes}
    assert {
        EntityType.RECEIPT,
        EntityType.LINE_ITEM,
        EntityType.PRODUCT,
        EntityType.MERCHANT,
        EntityType.CATEGORY,
        EntityType.DEPARTMENT,
        EntityType.BRAND,
        EntityType.MANUFACTURER,
        EntityType.PRICE,
        EntityType.CURRENCY,
        EntityType.NUTRITION,
    } <= types
    assert all(edge.relationship.evidence_sources for edge in value.edges)
    assert all(edge.relationship.provenance for edge in value.edges)
    assert all(edge.relationship.timestamp for edge in value.edges)
    assert all(edge.relationship.version for edge in value.edges)
    assert all(edge.relationship.explanation for edge in value.edges)
    product_edge = next(
        edge for edge in value.edges
        if edge.relationship.relationship_type == RelationshipType.RELATED_TO
        and str(edge.relationship.target_id) == "product:milk"
    )
    assert product_edge.relationship.confidence.upstream_values


def test_graph_engine_validates_and_never_persists():
    repository = EnterpriseGraphRepository()
    context = EnterpriseGraphEngine().build(
        product_result(), receipt_id="receipt-1", merchant_key="walmart",
    )
    assert context.diagnostics.valid
    assert context.diagnostics.sidecar is True
    assert context.diagnostics.affects_extraction is False
    assert context.diagnostics.parser_authority_changed is False
    assert context.diagnostics.storage_write_performed is False
    assert repository.loadGraph(context.graph.graph_id) is None


def test_validator_detects_duplicates_dangling_edges_and_invalid_ontology():
    valid = graph()
    node = valid.nodes[0]
    dangling = GraphEdge(Relationship(
        "dangling",
        "NOT_IN_ONTOLOGY",
        node.entity.entity_id,
        EntityId("missing", "unknown"),
        confidence=GraphConfidence(0.5),
    ))
    diagnostics = EnterpriseGraphValidator().validate(replace(
        valid, nodes=(*valid.nodes, node), edges=(*valid.edges, dangling),
    ))
    codes = {item.code for item in diagnostics.errors}
    assert "duplicate_node" in codes
    assert "dangling_edge" in codes
    assert "invalid_relationship_type" in codes


def test_validator_detects_prohibited_hierarchy_cycles():
    a = GraphNode(EnterpriseEntity(EntityId("a", "category"), EntityType.CATEGORY, "A"))
    b = GraphNode(EnterpriseEntity(EntityId("b", "category"), EntityType.CATEGORY, "B"))
    graph_value = GraphSubgraph(
        "cycle",
        (a, b),
        (
            GraphEdge(Relationship(
                "a-b", RelationshipType.HAS_PARENT,
                a.entity.entity_id, b.entity.entity_id,
                evidence_sources=("test",), explanation="A parent B.",
            )),
            GraphEdge(Relationship(
                "b-a", RelationshipType.HAS_PARENT,
                b.entity.entity_id, a.entity.entity_id,
                evidence_sources=("test",), explanation="B parent A.",
            )),
        ),
    )
    assert "prohibited_cycle" in {
        item.code for item in EnterpriseGraphValidator().validate(graph_value).errors
    }


def test_repository_save_version_archive_and_compare():
    repository = EnterpriseGraphRepository()
    first = repository.saveGraph(graph())
    added = GraphNode(EnterpriseEntity(
        EntityId("store-1", "store"), EntityType.STORE, "Store One",
    ))
    second = repository.versionGraph(
        replace(first, nodes=(*first.nodes, added)), expected_version=1,
    )
    assert second.version.entity_version == 2
    comparison = repository.compareGraphVersions(first.graph_id, 1, 2)
    assert comparison.added_nodes == ("store:store-1",)
    assert repository.archiveGraph(first.graph_id, 2).version.status == "archived"
    assert repository.loadGraph(first.graph_id).version.entity_version == 1


def test_repository_rejects_duplicate_save_and_version_conflict():
    repository = EnterpriseGraphRepository()
    value = repository.saveGraph(graph())
    with pytest.raises(ValueError, match="already_exists"):
        repository.saveGraph(value)
    with pytest.raises(ValueError, match="version_conflict"):
        repository.versionGraph(value, expected_version=9)


def test_serialization_and_loading_preserve_graph_contract():
    serializer = EnterpriseGraphSerializer()
    payload = serializer.to_json(graph())
    loaded = EnterpriseGraphLoader().from_json(payload)
    assert loaded.graph_id == "receipt-graph:receipt-1"
    assert {node.id for node in loaded.nodes} == {node.id for node in graph().nodes}
    assert len(loaded.edges) == len(graph().edges)
    assert serializer.to_dict(
        EnterpriseGraphEngine().build(product_result(), receipt_id="receipt-1"),
    )["diagnostics"]["valid"] is True


def test_query_find_entity_neighbors_shortest_path_and_subgraph():
    value = graph()
    queries = EnterpriseGraphQueryEngine()
    assert queries.find_entity(value, "Milk").nodes[0].id == "product:milk"
    neighbors = queries.find_neighbors(value, "product:milk")
    assert any(node.entity.entity_type == EntityType.BRAND for node in neighbors.nodes)
    path = queries.shortest_path(value, "receipt:receipt-1", "product:milk")
    assert path.paths
    assert path.paths[0][0] == "receipt:receipt-1"
    assert queries.subgraph(value, "product:milk", max_depth=2).nodes
    assert queries.traverse(value, "product:milk", max_depth=1).nodes


def test_domain_queries_are_storage_agnostic():
    value = graph()
    queries = EnterpriseGraphQueryEngine()
    assert [node.entity.label for node in queries.find_products_by_category(value, "Dairy").nodes] == ["Milk"]
    assert [node.entity.label for node in queries.find_merchants_selling_product(value, "milk").nodes] == ["walmart"]
    assert queries.find_purchases_containing_product(value, "milk").nodes[0].entity.entity_type == EntityType.RECEIPT
    assert queries.find_nutrition_relationships(value, "milk").nodes[0].entity.entity_type == EntityType.NUTRITION
    assert queries.execute(value, GraphQuery("find_related_products", entity_id="milk", max_depth=2)).nodes


def test_explanations_include_relationship_source_and_confidence():
    context = EnterpriseGraphEngine().build(
        product_result(), receipt_id="receipt-1", merchant_key="walmart",
    )
    assert context.explanations
    assert all("confidence" in item and "source" in item and "→" in item for item in context.explanations)


def test_learning_suggestions_require_approval_and_never_modify_graph():
    unknown = GraphNode(EnterpriseEntity(
        EntityId("future", "custom"), EntityType.UNKNOWN, "Future Entity",
    ))
    value = GraphSubgraph("learning", (unknown,), ())
    before = value
    suggestions = EnterpriseGraphLearningService().suggest(value)
    assert suggestions[0].requires_approval is True
    assert value == before


def test_safe_build_degrades_without_parser_effect():
    class BrokenBuilder(EnterpriseGraphBuilder):
        def build(self, *args, **kwargs):
            raise RuntimeError("broken")

    context = EnterpriseGraphEngine(builder=BrokenBuilder()).safe_build(
        product_result(), receipt_id="receipt-1",
    )
    assert context.diagnostics.errors[0].code == "enterprise_graph_sidecar_failed"
    assert context.diagnostics.affects_extraction is False
    assert context.diagnostics.parser_authority_changed is False
