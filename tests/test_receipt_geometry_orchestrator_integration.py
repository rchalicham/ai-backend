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
        "receiptStructure", "receiptClassification",
    )) <= set(response)
    assert response["semantic"]["items"] == []
    assert response["llama"] is None
    assert response["receiptStructure"]["document_id"] == response["receiptDocument"]["metadata"]["document_id"]
    assert response["receiptStructure"]["diagnostics"]["affectsExtraction"] is False
    assert response["receiptClassification"]["document_id"] == response["receiptDocument"]["metadata"]["document_id"]
    assert response["receiptClassification"]["candidates"] == []
    assert response["receiptClassification"]["diagnostics"]["usesOcrText"] is False
    assert response["receiptClassification"]["diagnostics"]["affectsExtraction"] is False


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
