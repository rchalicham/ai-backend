import os
import sys
import asyncio
from types import SimpleNamespace

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.receipt_agent_orchestrator import ReceiptAgentOrchestrator
from services.receipt_geometry import Dimensions, Geometry, Point
from services.merchant_intelligence import (
    InMemoryMerchantIntelligenceRepository,
    MerchantBlueprintService,
)
from services.receipt_grammar import (
    GrammarMetadata,
    GrammarSection,
    GrammarSectionType,
    GrammarVersion,
    ReceiptGrammar,
    ReceiptGrammarEngine,
    ReceiptGrammarRepository,
)
from services.receipt_constraints import (
    ConstraintCategory,
    ConstraintEngine,
    ConstraintRule,
    ConstraintVersion,
    ReceiptConstraint,
    ReceiptConstraintRepository,
)
from services.product_intelligence import (
    CanonicalProduct,
    ProductAlias,
    ProductIntelligenceEngine,
    ProductRepository,
)


class _Geometry:
    def to_dict(self):
        return {"geometric_confidence": 0.91}


class _GeometryEngine:
    def safe_analyze(self, image_bytes):
        assert image_bytes == b"source"
        return _Geometry()


class _Isolation:
    def isolate(self, image_bytes):
        return SimpleNamespace(image_bytes=b"isolated", diagnostics={"applied": True})


class _NoImageVariantsAgent(ReceiptAgentOrchestrator):
    def _narrow_receipt_crop_variant(self, image_bytes):
        return None

    def _opencv_retry_variants(self, image_bytes):
        return []


def test_orchestrator_adds_geometry_as_sidecar_without_changing_image_sources():
    agent = _NoImageVariantsAgent(
        donut_receipt_service=object(),
        receipt_image_isolation_service=_Isolation(),
        receipt_ocr_service=object(),
        llm_service=object(),
        receipt_geometry_engine=_GeometryEngine(),
    )

    sources = agent._image_sources(b"source")

    assert [(source["source"], source["imageBytes"]) for source in sources] == [
        ("isolated_receipt", b"isolated"),
        ("uploaded_image", b"source"),
    ]
    assert sources[0]["diagnostics"]["geometry"] == {"geometric_confidence": 0.91}
    assert sources[1]["diagnostics"] == {}


class _PhysicalGeometryEngine:
    def safe_analyze(self, image_bytes):
        return Geometry(
            receipt_boundary=[Point(0, 0), Point(399, 0), Point(399, 799), Point(0, 799)],
            page_dimensions=Dimensions(400, 800),
            source_dimensions=Dimensions(400, 800),
            rotation=0,
            skew=0,
            perspective_matrix=[[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            geometric_confidence=0.9,
        )


def test_orchestrator_builds_request_scoped_dom_after_ocr_artifacts_are_available():
    agent = _NoImageVariantsAgent(
        donut_receipt_service=object(),
        receipt_image_isolation_service=_Isolation(),
        receipt_ocr_service=object(),
        llm_service=object(),
        receipt_geometry_engine=_PhysicalGeometryEngine(),
    )

    document = agent._build_receipt_document(
        image_bytes=b"ocr-image",
        lines=["ALPHA BETA"],
        ocr_blocks=[
            {"text": "ALPHA", "x": 20, "y": 30, "width": 60, "height": 15, "block": 1, "line": 1},
            {"text": "BETA", "x": 90, "y": 30, "width": 50, "height": 15, "block": 1, "line": 1},
        ],
        ocr_engine="test-ocr",
        source_image_id="image-1",
        source_filename="fixture.jpg",
    )

    assert document is not None
    assert document.metadata.source_filename == "fixture.jpg"
    assert document.pages[0].regions[0].blocks[0].lines[0].text == "ALPHA BETA"


class _SingleSourceAgent(ReceiptAgentOrchestrator):
    def _image_sources(self, image_bytes):
        return [{"source": "uploaded_image", "strategy": "baseline_document_understanding", "imageBytes": image_bytes, "diagnostics": {}}]


class _Donut:
    async def analyze_image_bytes(self, image_bytes):
        return {"available": True}

    def consolidate_receipt_rows(self, payload, **kwargs):
        return payload


class _PhysicalPipeline:
    def to_structured_json(self, **kwargs):
        return {"items": [], "facts": {}, "confidence": {"overall": 0.5}}

    @property
    def validator(self):
        return SimpleNamespace(validate=lambda *args, **kwargs: {})


class _Llm:
    receipt_intelligence = _PhysicalPipeline()


def test_process_exposes_physical_sidecars_without_replacing_existing_result_keys():
    agent = _SingleSourceAgent(
        donut_receipt_service=_Donut(),
        receipt_image_isolation_service=_Isolation(),
        receipt_ocr_service=object(),
        llm_service=_Llm(),
        receipt_geometry_engine=_PhysicalGeometryEngine(),
    )

    response = asyncio.run(agent.process(
        image_bytes=b"source",
        raw_text="ALPHA BETA",
        lines=["ALPHA BETA"],
        ocr_blocks=[
            {"text": "ALPHA", "x": 20, "y": 30, "width": 60, "height": 15, "block": 1, "line": 1},
            {"text": "BETA", "x": 90, "y": 30, "width": 50, "height": 15, "block": 1, "line": 1},
        ],
        run_llama=False,
    ))

    assert set((
        "donut", "semantic", "llama", "receiptAgent", "receiptDocument",
        "receiptStructure", "receiptClassification", "documentFamilyContext", "receiptGrammar",
        "receiptConstraintResult",
        "productIntelligence",
        "enterpriseKnowledgeGraph",
        "crossDocumentIntelligence",
        "enterpriseLearning",
        "enterpriseReasoning",
        "businessProjection",
        "receiptIntelligenceSnapshot",
        "snapshotProjection",
        "snapshotHistory",
    )) <= set(response)
    assert response["semantic"]["items"] == []
    assert response["llama"] is None
    assert response["receiptStructure"]["document_id"] == response["receiptDocument"]["metadata"]["document_id"]
    assert response["receiptStructure"]["diagnostics"]["affectsExtraction"] is False
    assert response["receiptClassification"]["document_id"] == response["receiptDocument"]["metadata"]["document_id"]
    assert response["receiptClassification"]["candidates"] == []
    assert response["receiptClassification"]["diagnostics"]["usesOcrText"] is False
    assert response["receiptClassification"]["diagnostics"]["affectsExtraction"] is False
    assert response["documentFamilyContext"]["schema_version"] == "document-family-context-v1"
    assert response["documentFamilyContext"]["diagnostics"]["affectsExtraction"] is False
    assert response["documentFamilyContext"]["diagnostics"]["parserAuthorityChanged"] is False
    assert response["semantic"]["items"] == []
    assert response["receiptGrammar"]["loaded"] is False
    assert response["receiptGrammar"]["diagnostics"]["affectsExtraction"] is False
    assert response["receiptGrammar"]["diagnostics"]["parserAuthorityChanged"] is False
    assert response["receiptConstraintResult"]["loaded"] is False
    assert response["receiptConstraintResult"]["diagnostics"]["affectsExtraction"] is False
    assert response["receiptConstraintResult"]["diagnostics"]["parserAuthorityChanged"] is False
    assert response["productIntelligence"]["enrichments"] == []
    assert response["productIntelligence"]["diagnostics"]["affects_extraction"] is False
    assert response["productIntelligence"]["diagnostics"]["parser_authority_changed"] is False
    assert response["enterpriseKnowledgeGraph"]["diagnostics"]["affects_extraction"] is False
    assert response["enterpriseKnowledgeGraph"]["diagnostics"]["parser_authority_changed"] is False
    assert response["enterpriseKnowledgeGraph"]["diagnostics"]["storage_write_performed"] is False
    assert response["crossDocumentIntelligence"]["diagnostics"]["affects_extraction"] is False
    assert response["crossDocumentIntelligence"]["diagnostics"]["parser_authority_changed"] is False
    assert response["crossDocumentIntelligence"]["diagnostics"]["documents_modified"] is False
    assert response["crossDocumentIntelligence"]["diagnostics"]["graph_modified"] is False
    assert response["enterpriseLearning"]["diagnostics"]["affects_extraction"] is False
    assert response["enterpriseLearning"]["diagnostics"]["parser_authority_changed"] is False
    assert response["enterpriseLearning"]["diagnostics"]["production_knowledge_modified"] is False
    assert response["enterpriseLearning"]["diagnostics"]["automatic_approval_performed"] is False
    assert response["enterpriseLearning"]["diagnostics"]["raw_ocr_consumed"] is False
    assert response["enterpriseLearning"]["snapshot"]["approvals"] == []
    assert response["enterpriseReasoning"]["diagnostics"]["affects_extraction"] is False
    assert response["enterpriseReasoning"]["diagnostics"]["parser_authority_changed"] is False
    assert response["businessProjection"]["schema_version"] == "business-projection-v1"
    assert response["businessProjection"]["diagnostics"]["parser_modified"] is False
    assert response["businessProjection"]["diagnostics"]["parser_authority_changed"] is False
    assert response["receiptIntelligenceSnapshot"]["schema_version"] == "receipt-intelligence-snapshot-v1"
    assert response["receiptIntelligenceSnapshot"]["diagnostics"]["parser_modified"] is False
    assert response["receiptIntelligenceSnapshot"]["diagnostics"]["receipt_modified"] is False
    assert response["snapshotProjection"]["version"] == 1
    assert len(response["snapshotHistory"]["snapshots"]) == 1
    assert response["enterpriseReasoning"]["diagnostics"]["raw_ocr_consumed"] is False
    assert response["enterpriseReasoning"]["diagnostics"]["parser_guesses_consumed"] is False
    assert response["enterpriseReasoning"]["diagnostics"]["llm_bypassed_evidence"] is False
    assert response["enterpriseReasoning"]["diagnostics"]["llm_used"] is False
    assert response["enterpriseReasoning"]["decision"]["authoritative"] is False


def test_explicit_merchant_knowledge_is_request_context_only_and_does_not_change_semantic_result():
    repository = InMemoryMerchantIntelligenceRepository()
    blueprints = MerchantBlueprintService(repository)
    blueprints.create_blueprint("merchant-knowledge-1", "Knowledge Fixture")
    agent = _SingleSourceAgent(
        donut_receipt_service=_Donut(),
        receipt_image_isolation_service=_Isolation(),
        receipt_ocr_service=object(),
        llm_service=_Llm(),
        receipt_geometry_engine=_PhysicalGeometryEngine(),
        merchant_blueprint_service=blueprints,
    )

    request = dict(
        image_bytes=b"source",
        raw_text="ALPHA",
        lines=["ALPHA"],
        ocr_blocks=[{"text": "ALPHA", "x": 20, "y": 30, "width": 60, "height": 15, "block": 1, "line": 1}],
        run_llama=False,
    )
    baseline = asyncio.run(agent.process(**request))
    response = asyncio.run(agent.process(**request, merchant_knowledge_key="merchant-knowledge-1"))

    assert response["semantic"] == baseline["semantic"]
    assert response["donut"] == baseline["donut"]
    assert response["llama"] == baseline["llama"]
    assert response["merchantIntelligence"]["loaded"] is True
    assert response["merchantIntelligence"]["merchant_key"] == "merchant-knowledge-1"
    assert response["merchantIntelligence"]["blueprint"]["identity"]["canonical_name"] == "Knowledge Fixture"
    assert response["merchantIntelligence"]["diagnostics"]["detectionPerformed"] is False
    assert response["merchantIntelligence"]["diagnostics"]["affectsExtraction"] is False


def test_matching_receipt_grammar_is_additive_and_does_not_change_existing_extraction():
    knowledge_repository = InMemoryMerchantIntelligenceRepository()
    blueprints = MerchantBlueprintService(knowledge_repository)
    blueprints.create_blueprint("merchant-grammar-1", "Grammar Fixture")
    blueprints.add_receipt_family(
        "merchant-grammar-1",
        "family-grammar-1",
        "Grammar Family",
        confidence=1.0,
        attributes=(("physical_features", {"page": {"width": 400.0, "height": 800.0}}),),
    )
    grammar_repository = ReceiptGrammarRepository()
    grammar_repository.save_grammar(ReceiptGrammar(
        metadata=GrammarMetadata(
            "grammar-family-grammar-1",
            "family-grammar-1",
            "Grammar Family Definition",
        ),
        version=GrammarVersion(),
        sections=(
            GrammarSection(
                "header",
                GrammarSectionType.HEADER,
                "Header",
                required=True,
                minimum_occurrences=1,
            ),
        ),
    ))
    constraint_repository = ReceiptConstraintRepository()
    constraint_repository.save_constraints(ReceiptConstraint(
        constraint_set_id="constraints-family-grammar-1",
        receipt_family="family-grammar-1",
        name="Grammar Family Constraints",
        version=ConstraintVersion(),
        rules=(
            ConstraintRule(
                "grammar-compliance",
                ConstraintCategory.GRAMMAR,
                "grammar_compliance",
                "Grammar compliance must be structurally supported.",
                parameters=(("minimum", 0.0),),
            ),
        ),
    ))
    agent = _SingleSourceAgent(
        donut_receipt_service=_Donut(),
        receipt_image_isolation_service=_Isolation(),
        receipt_ocr_service=object(),
        llm_service=_Llm(),
        receipt_geometry_engine=_PhysicalGeometryEngine(),
        merchant_blueprint_service=blueprints,
        receipt_grammar_engine=ReceiptGrammarEngine(repository=grammar_repository),
        receipt_constraint_engine=ConstraintEngine(repository=constraint_repository),
    )
    request = dict(
        image_bytes=b"source",
        raw_text="ALPHA",
        lines=["ALPHA"],
        ocr_blocks=[
            {
                "text": "ALPHA",
                "x": 20,
                "y": 30,
                "width": 60,
                "height": 15,
                "block": 1,
                "line": 1,
            },
        ],
        run_llama=False,
    )

    baseline = asyncio.run(agent.process(**request))
    response = asyncio.run(
        agent.process(**request, merchant_knowledge_key="merchant-grammar-1"),
    )

    assert response["semantic"] == baseline["semantic"]
    assert response["donut"] == baseline["donut"]
    assert response["llama"] == baseline["llama"]
    assert response["receiptGrammar"]["loaded"] is True
    assert response["receiptGrammar"]["receipt_family"] == "family-grammar-1"
    assert response["receiptGrammar"]["grammar"]["metadata"]["grammar_id"] == "grammar-family-grammar-1"
    assert response["receiptGrammar"]["compilation"]["diagnostics"]["valid"] is True
    assert response["receiptGrammar"]["diagnostics"]["affectsExtraction"] is False
    assert response["receiptGrammar"]["diagnostics"]["parserAuthorityChanged"] is False
    assert response["receiptConstraintResult"]["loaded"] is True
    assert response["receiptConstraintResult"]["receipt_family"] == "family-grammar-1"
    assert response["receiptConstraintResult"]["decision"]["best_candidate"]["candidate_id"] == "grammar-structure-candidate"
    assert response["receiptConstraintResult"]["diagnostics"]["affectsExtraction"] is False
    assert response["receiptConstraintResult"]["diagnostics"]["parserAuthorityChanged"] is False
    assert response["receiptConstraintResult"]["diagnostics"]["businessFactsGenerated"] is False


def test_product_intelligence_enriches_a_copy_and_does_not_change_parser_output():
    class _ItemPipeline(_PhysicalPipeline):
        def to_structured_json(self, **kwargs):
            return {
                "items": [{"name": "MLK 2%", "price": "3.49", "quantity": 1}],
                "facts": {"total": "3.49"},
                "confidence": {"overall": 0.9},
            }

    class _ItemLlm:
        receipt_intelligence = _ItemPipeline()

    products = ProductRepository()
    products.saveProducts(CanonicalProduct(
        product_id="milk",
        canonical_name="Milk",
        aliases=(ProductAlias("MLK 2%", "Milk 2 Percent"),),
    ))
    agent = _SingleSourceAgent(
        donut_receipt_service=_Donut(),
        receipt_image_isolation_service=_Isolation(),
        receipt_ocr_service=object(),
        llm_service=_ItemLlm(),
        receipt_geometry_engine=_PhysicalGeometryEngine(),
        product_intelligence_engine=ProductIntelligenceEngine(repository=products),
    )

    response = asyncio.run(agent.process(
        image_bytes=b"source",
        raw_text="MLK 2% 3.49",
        lines=["MLK 2% 3.49"],
        ocr_blocks=[{
            "text": "MLK 2% 3.49", "x": 20, "y": 30,
            "width": 100, "height": 15, "block": 1, "line": 1,
        }],
        run_llama=False,
    ))

    assert response["semantic"]["items"] == [
        {"name": "MLK 2%", "price": "3.49", "quantity": 1},
    ]
    context = response["crossDocumentIntelligence"]
    assert context["schema_version"] == "cross-document-intelligence-v1"
    assert context["memory"]["deterministic"] is True
    assert context["memory"]["llm_memory"] is False
    assert context["diagnostics"]["machine_learning_used"] is False
    assert context["diagnostics"]["memory_write_performed"] is False
    enrichment = response["productIntelligence"]["enrichments"][0]
    assert enrichment["original_description"] == "MLK 2%"
    assert enrichment["normalized_description"] == "Milk 2 Percent"
    assert enrichment["canonical_product"]["canonical_name"] == "Milk"
    assert response["productIntelligence"]["diagnostics"]["affects_extraction"] is False
    assert response["productIntelligence"]["diagnostics"]["extracted_values_replaced"] is False
    graph = response["enterpriseKnowledgeGraph"]
    assert graph["schema_version"] == "enterprise-graph-context-v1"
    assert any(
        node["entity"]["entity_type"] == "Product"
        and node["entity"]["label"] == "Milk"
        for node in graph["graph"]["nodes"]
    )
    assert all(edge["relationship"]["explanation"] for edge in graph["graph"]["edges"])
    assert response["semantic"]["items"] == [
        {"name": "MLK 2%", "price": "3.49", "quantity": 1},
    ]
