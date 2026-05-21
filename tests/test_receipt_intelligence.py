import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.receipt_intelligence import ReceiptIntelligencePipeline, ReceiptLineReconstructor
from services.receipt_intelligence import MerchantNormalizer


def test_ocr_boxes_reconstruct_rows_left_to_right():
    reconstructor = ReceiptLineReconstructor()

    lines = reconstructor.reconstruct("", boxes=[
        {"text": "9.99", "x": 300, "y": 100, "width": 40, "height": 12, "confidence": 0.93},
        {"text": "PET", "x": 42, "y": 102, "width": 60, "height": 12, "confidence": 0.91},
        {"text": "LOWE'S", "x": 40, "y": 20, "width": 80, "height": 12, "confidence": 0.98},
    ])

    assert [line.text for line in lines] == ["LOWE'S", "PET 9.99"]
    assert lines[1].confidence == 0.92


def test_pipeline_suppresses_duplicate_later_ocr_passes_and_scores_validation():
    pipeline = ReceiptIntelligencePipeline()
    raw_text = """
KADAI INDIAN KITCHEN
3 Custom Item 390.00
2 Custom Item 130.00
Subtotal 520.00
Total 520.00
3 Custom ltem 390.00
2 Custom Item 130.00
"""

    result = pipeline.analyze(raw_text)

    assert result.merchant == "KADAI INDIAN KITCHEN"
    assert [(item["name"], item["qty"], item["amount"]) for item in result.items] == [
        ("Custom Item", "3", "390.00"),
        ("Custom Item", "2", "130.00"),
    ]
    assert result.facts["subtotal"] == "520.00"
    assert result.confidence["overall"] >= 0.8
    assert result.retry_plan == []


def test_pipeline_flags_subtotal_mismatch_for_ai_retry():
    pipeline = ReceiptIntelligencePipeline()
    raw_text = """
STORE
Item A 4.00
Item B 3.00
Subtotal 30.00
Total 30.00
"""

    result = pipeline.analyze(raw_text)

    assert "item_sum_does_not_match_subtotal" in result.warnings
    assert any(step["stage"] == "ai" for step in result.retry_plan)


def test_pipeline_builds_layout_blocks_tables_and_graph_from_boxes():
    pipeline = ReceiptIntelligencePipeline()

    result = pipeline.analyze(
        raw_text="",
        ocr_blocks=[
            {"text": "LOWE'S", "x": 42, "y": 20, "width": 80, "height": 14, "confidence": 0.98},
            {"text": "PET", "x": 42, "y": 90, "width": 80, "height": 14, "confidence": 0.92},
            {"text": "9.99", "x": 310, "y": 90, "width": 40, "height": 14, "confidence": 0.93},
            {"text": "SUBTOTAL", "x": 42, "y": 132, "width": 96, "height": 14, "confidence": 0.91},
            {"text": "9.99", "x": 310, "y": 132, "width": 40, "height": 14, "confidence": 0.92},
            {"text": "TOTAL", "x": 42, "y": 154, "width": 70, "height": 14, "confidence": 0.91},
            {"text": "9.99", "x": 310, "y": 154, "width": 40, "height": 14, "confidence": 0.92},
        ],
    )

    assert result.merchant == "LOWE'S"
    assert result.layout_json["schemaVersion"] == "receipt-layout-v1"
    assert result.layout_json["regions"]
    assert any(block.kind == "items" for block in result.semantic_blocks)
    assert result.tables[0]["kind"] == "items"
    assert result.tables[0]["rows"][0]["name"] == "PET"
    assert any(node["type"] == "ReceiptItem" for node in result.graph["nodes"])


def test_layout_quality_flags_blurry_receipts_for_retry_context():
    pipeline = ReceiptIntelligencePipeline()

    result = pipeline.analyze(
        raw_text="",
        ocr_blocks=[
            {"text": "STORE", "x": 40, "y": 20, "width": 90, "height": 12, "confidence": 0.45},
            {"text": "ITEM", "x": 40, "y": 80, "width": 90, "height": 12, "confidence": 0.42},
            {"text": "4.00", "x": 250, "y": 80, "width": 40, "height": 12, "confidence": 0.44},
            {"text": "TOTAL", "x": 40, "y": 128, "width": 90, "height": 12, "confidence": 0.41},
            {"text": "4.00", "x": 250, "y": 128, "width": 40, "height": 12, "confidence": 0.43},
        ],
    )

    assert result.layout_json["quality"]["indicators"]["likelyBlurry"] is True
    assert any(step["stage"] == "ocr" for step in result.retry_plan)


def test_semantic_json_extracts_quantities_totals_and_confidence():
    pipeline = ReceiptIntelligencePipeline()

    semantic = pipeline.to_structured_json(
        raw_text="""
LOWE'S HOME CENTERS, LLC
2 EA MULCH BAG 7.00
WASHERS 3 @ 1.25 3.75
SUBTOTAL 10.75
TAX 0.86
TOTAL 11.61
""",
        ocr_engine="paddleocr",
    )

    assert semantic["schemaVersion"] == "receipt-semantic-v1"
    assert semantic["documentType"] == "receipt"
    assert semantic["ocrEngine"] == "paddleocr"
    assert semantic["merchant"] == "LOWE'S HOME CENTERS, LLC"
    assert [(item["name"], item["qty"], item["amount"]) for item in semantic["items"]] == [
        ("MULCH BAG", "2", "7.00"),
        ("WASHERS", "3", "3.75"),
    ]
    assert semantic["facts"] == {
        "subtotal": "10.75",
        "tax": "0.86",
        "tip": "",
        "total": "11.61",
    }
    assert semantic["validation"]["valid"] is True
    assert semantic["confidence"]["overall"] > 0.7
    assert semantic["reconstructedLines"]
    assert semantic["tables"]


def test_semantic_json_uses_ocr_bounding_boxes_for_line_grouping():
    pipeline = ReceiptIntelligencePipeline()

    semantic = pipeline.to_structured_json(
        raw_text="",
        ocr_blocks=[
            {"text": "KADAI", "x": 40, "y": 20, "width": 70, "height": 14, "confidence": 0.97},
            {"text": "INDIAN", "x": 118, "y": 20, "width": 70, "height": 14, "confidence": 0.97},
            {"text": "KITCHEN", "x": 196, "y": 20, "width": 85, "height": 14, "confidence": 0.97},
            {"text": "2", "x": 40, "y": 80, "width": 12, "height": 14, "confidence": 0.94},
            {"text": "Custom", "x": 64, "y": 80, "width": 70, "height": 14, "confidence": 0.94},
            {"text": "Item", "x": 142, "y": 80, "width": 45, "height": 14, "confidence": 0.94},
            {"text": "130.00", "x": 310, "y": 80, "width": 60, "height": 14, "confidence": 0.94},
            {"text": "SUBTOTAL", "x": 40, "y": 118, "width": 90, "height": 14, "confidence": 0.95},
            {"text": "130.00", "x": 310, "y": 118, "width": 60, "height": 14, "confidence": 0.95},
            {"text": "TOTAL", "x": 40, "y": 142, "width": 60, "height": 14, "confidence": 0.95},
            {"text": "130.00", "x": 310, "y": 142, "width": 60, "height": 14, "confidence": 0.95},
        ],
        ocr_engine="paddleocr",
    )

    assert semantic["merchant"] == "KADAI INDIAN KITCHEN"
    assert semantic["items"][0]["name"] == "Custom Item"
    assert semantic["items"][0]["qty"] == "2"
    assert semantic["items"][0]["amount"] == "130.00"
    assert semantic["reconstructedLines"][0]["bbox"]["width"] > 200
    assert any(node["type"] == "ReceiptItem" for node in semantic["graph"]["nodes"])


def test_semantic_parser_rejects_cvs_mutated_totals_and_dedupes_item_variants():
    raw_text = """
1 Srtga SPRK Sprng Wi 282 2,89F
A179 9484 0417 347 13, NO 'PETPEIEE (ER TAED IE 28000
07/13/2026
SRTGA SPRK SPRNG Wi 282
1
$2.89
SRTGA SPRK SPRNG W 282
1
$2.89
GATT
1
$347.13
SRTGA SPRK SPRNG WW 282
1
$2.89
HARGE
1
$2.89
"""
    semantic = ReceiptIntelligencePipeline().to_structured_json(
        raw_text=raw_text,
        lines=raw_text.splitlines(),
        parser_json={"subtotal": "347", "tax": "0", "tip": "0", "total": "2.89"},
        ocr_engine="donut-rerun",
    )

    assert [(item["name"], item["qty"], item["amount"]) for item in semantic["items"]] == [
        ("Srtga SPRK Sprng Wi 282", "1", "2.89")
    ]
    assert semantic["validation"]["itemSum"] == "2.89"


def test_merchant_normalizer_preserves_raw_header_without_address_context_canonicalization():
    raw_text = """
EE LE a ee Ee
4140 ROAD 101 NORTH, PLYNQUTH, MM
PHARHACY: 478-4612 STORE:
1 SRTGA SPRK SPRNG Wi 282 2.89F
VISA CREDIT HHH HHH 3442
"""

    merchant = MerchantNormalizer().normalize(raw_text)

    assert merchant == "1 SRTGA SPRK SPRNG Wi 282 2.89F"


def test_receipt_pipeline_preserves_ocr_merchant_without_fuzzy_canonicalization():
    raw_text = """
CV5 pharma
4140 ROAD 101 NORTH
PLYMOUTH, MN
1 SRTGA SPRK SPRNG Wi 282 2.89F
TOTAL 2.89
"""

    semantic = ReceiptIntelligencePipeline().to_structured_json(raw_text=raw_text, lines=raw_text.splitlines())

    assert semantic["merchant"] == "CV5 Pharma"


def test_merchant_normalizer_scores_domain_ocr_with_qdrant_payload():
    raw_text = """
    TARGET.COM
    TOTAL 2.89
    """

    candidates = MerchantNormalizer().candidates(raw_text)

    assert candidates[0]["merchant"] == "Target"
    assert candidates[0]["confidence"] >= 0.9
    assert "qdrantPayload" in candidates[0]
    assert candidates[0]["qdrantPayload"]["normalizedMerchant"] == "Target"


def test_domain_merchant_evidence_prevents_parser_overcorrection():
    raw_text = """
    FRESHTHYME.COM
    VALUES YOUR FEEDBACK
    ORGANIC BANANAS 2.49
    TOTAL 2.49
    """

    resolution = MerchantNormalizer().resolve(raw_text)

    assert resolution["merchant"] == "Freshthyme"
    assert resolution["confidence"] >= 0.95
    assert any(item["type"] == "domain_ocr" for item in resolution["evidence"])
    assert resolution["merchant"] != "Madeup Mart"


def test_low_confidence_fuzzy_candidate_preserves_raw_ocr_merchant():
    raw_text = """
    NEIGHBORHOOD MARKET
    VALUES YOUR FEEDBACK
    TOTAL 8.25
    """

    resolution = MerchantNormalizer().resolve(raw_text)

    assert resolution["merchant"] == "NEIGHBORHOOD MARKET"
    assert resolution["source"] == "raw_ocr_preserved"


def test_hallucinated_parser_candidate_cannot_override_domain_ocr():
    raw_text = """
    FRESHTHYME.COM
    ORGANIC BANANAS 2.49
    TOTAL 2.49
    """

    resolution = MerchantNormalizer().resolve(raw_text, candidate="MADEUP MART")

    assert resolution["merchant"] == "Freshthyme"
    assert resolution["selectedCandidate"]["merchant"] == "Freshthyme"
