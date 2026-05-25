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


def test_pipeline_reconstructs_aligned_ocr_table_and_rejects_orphan_money():
    semantic = ReceiptIntelligencePipeline().to_structured_json(
        raw_text="",
        ocr_blocks=[
            {"text": "MARKET", "x": 120, "y": 12, "width": 120, "height": 18, "confidence": 0.98},
            {"text": "QTY", "x": 20, "y": 52, "width": 30, "height": 12, "confidence": 0.96},
            {"text": "ITEM", "x": 92, "y": 52, "width": 46, "height": 12, "confidence": 0.96},
            {"text": "PRICE", "x": 300, "y": 52, "width": 48, "height": 12, "confidence": 0.96},
            {"text": "2", "x": 22, "y": 82, "width": 12, "height": 14, "confidence": 0.95},
            {"text": "APPLES", "x": 92, "y": 82, "width": 70, "height": 14, "confidence": 0.95},
            {"text": "4.00", "x": 312, "y": 82, "width": 42, "height": 14, "confidence": 0.95},
            {"text": "3.25", "x": 312, "y": 108, "width": 42, "height": 14, "confidence": 0.96},
            {"text": "BANANAS", "x": 92, "y": 134, "width": 78, "height": 14, "confidence": 0.94},
            {"text": "1.50", "x": 312, "y": 134, "width": 42, "height": 14, "confidence": 0.94},
            {"text": "SUBTOTAL", "x": 92, "y": 176, "width": 86, "height": 14, "confidence": 0.96},
            {"text": "5.50", "x": 312, "y": 176, "width": 42, "height": 14, "confidence": 0.96},
            {"text": "TOTAL", "x": 92, "y": 198, "width": 58, "height": 14, "confidence": 0.96},
            {"text": "5.50", "x": 312, "y": 198, "width": 42, "height": 14, "confidence": 0.96},
        ],
        ocr_engine="paddleocr",
    )

    assert [(item["name"], item["qty"], item["amount"]) for item in semantic["items"]] == [
        ("APPLES", "2", "4.00"),
        ("BANANAS", "1", "1.50"),
    ]
    reconstruction = semantic["tables"][0]["reconstruction"]
    assert reconstruction["schemaVersion"] == "receipt-aligned-table-reconstruction-v1"
    assert any(row["text"] == "3.25" and "orphan_monetary_value" in row["reason"] for row in reconstruction["rejectedRows"])
    assert semantic["validation"]["itemSum"] == "5.50"


def test_pipeline_uses_visual_saliency_to_reject_legal_disclaimer_merchant():
    result = ReceiptIntelligencePipeline().analyze(
        raw_text="",
        ocr_blocks=[
            {"text": "Void where prohibited", "x": 210, "y": 18, "width": 115, "height": 8, "confidence": 0.96},
            {"text": "BRIGHT MARKET", "x": 80, "y": 58, "width": 280, "height": 26, "confidence": 0.98},
            {"text": "APPLES", "x": 42, "y": 210, "width": 100, "height": 14, "confidence": 0.92},
            {"text": "3.25", "x": 310, "y": 210, "width": 40, "height": 14, "confidence": 0.92},
            {"text": "TOTAL", "x": 42, "y": 300, "width": 80, "height": 14, "confidence": 0.92},
            {"text": "3.25", "x": 310, "y": 300, "width": 40, "height": 14, "confidence": 0.92},
        ],
    )

    assert result.merchant == "BRIGHT MARKET"
    assert result.section_extraction["visualHierarchy"]["schemaVersion"] == "receipt-visual-hierarchy-v1"
    assert result.section_extraction["layoutGraph"]["nodes"][0]["visualImportance"] >= 0
    ranking = result.ontology["debug"]["merchantCandidateRanking"]
    assert ranking[0]["text"] == "BRIGHT MARKET"


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


def test_semantic_json_handles_split_ocr_rows_without_merchant_or_item_hallucination():
    lines = [
        "Wow. FI Eshi Hye - Com/Sweepst Akes",
        "45760 WIUL AVENUE N, PLYMOULL, MN 59447",
        "Quantity",
        "Price",
        "BEEF LIVER",
        "1",
        "$4.69",
        "~ MLR BNLS BRS!",
        "1",
        "$43.90",
        "PROT RO RED BEETS ii",
        "1",
        "$2.99",
        "BAI ANCE DUE",
        "1",
        "$21.58",
        "MLR BNLS BRSI",
        "1",
        "$13.90",
        "USD",
        "1",
        "$21.58",
        "POO BNLS BRST",
        "1",
        "$43.90",
        "jot yspgn",
        "1",
        "$2.58",
        "Total number of items sold 3",
        "VISA",
    ]

    semantic = ReceiptIntelligencePipeline().to_structured_json(
        raw_text="\n".join(lines),
        lines=lines,
        ocr_engine="donut-rerun",
    )

    assert semantic["merchant"] == ""
    assert [(item["name"], item["qty"], item["amount"]) for item in semantic["items"]] == [
        ("BEEF LIVER", "1", "4.69"),
        ("PROT RO RED BEETS ii", "1", "2.99"),
        ("MLR BNLS BRSI", "1", "13.90"),
    ]
    assert semantic["facts"]["total"] == "21.58"
    assert semantic["validation"]["itemSum"] == "21.58"


def test_semantic_json_reconciles_split_rows_without_explicit_item_count():
    lines = [
        "Vord Whenre Prohibited.",
        "Quantity",
        "Price",
        "BEEF LIVER",
        "1",
        "$4.69",
        "~ MLR BNLS BRS!",
        "1",
        "$43.90",
        "PROT RO RED BEETS ii",
        "1",
        "$2.99",
        "MLR BNLS BRSI",
        "1",
        "$13.90",
        "BAI ANCE DUE",
        "1",
        "$21.58",
        "POO BNLS BRST",
        "1",
        "$43.90",
        "USD",
        "1",
        "$21.58",
        "jot yspgn",
        "1",
        "$2.58",
        "VISA",
    ]

    semantic = ReceiptIntelligencePipeline().to_structured_json(
        raw_text="\n".join(lines),
        lines=lines,
        ocr_engine="donut-rerun",
    )

    assert semantic["merchant"] == ""
    assert [(item["name"], item["amount"]) for item in semantic["items"]] == [
        ("BEEF LIVER", "4.69"),
        ("PROT RO RED BEETS ii", "2.99"),
        ("MLR BNLS BRSI", "13.90"),
    ]
    assert semantic["facts"]["total"] == "21.58"
    assert semantic["validation"]["itemSum"] == "21.58"
    assert semantic["sectionExtraction"]["financialReconciliation"]["expectedItemCount"] is None
    assert semantic["sectionExtraction"]["financialReconciliation"]["reason"] == "constraint_solver_selected_subset"


def test_semantic_json_rescues_items_from_noisy_multi_pass_receipt_ocr():
    lines = [
        "No purchase necessary:",
        "Vord whenre prohibited.",
        "View of ficeal rules at",
        "FRESH HYME .COM",
        "Total: USD$ 21.58",
        "MEE LIVER 4.69 NF",
        "MLR BNLS pRsI 43.90 N F",
        "PROT RO RED BEETS ii 2.99 NF",
        "BALANCE puE 21.58",
        "total numbel of {tells sold = 3",
        "BEEF LIVER 4.69 NF",
        "MLR BNLS BRSI 13.90 NF",
        "MLR BNLS BRSI 13.90 N E",
        "0 ORG RED BEETS 2.99 NF",
        "BAI ANCE DUE 21.58",
        "VISA 21.58",
        "MLR BNLS BRST 13.90 NF",
        "E 6 ORG RED BEETS 2.99 NF",
        "POO BNLS BRST 43.90 N F",
        "BEEF LIVER Le ur",
        "jot yspgn 2.58",
        "Total number of items sold = 3",
    ]

    semantic = ReceiptIntelligencePipeline().to_structured_json(
        raw_text="\n".join(lines),
        lines=lines,
        parser_json={"company": "view of ficeal rules at", "documentType": "receipt"},
        ocr_engine="donut-rerun",
    )

    assert semantic["merchant"] == "Fresh Hyme"
    assert [(item["name"], item["amount"]) for item in semantic["items"]] == [
        ("BEEF LIVER", "4.69"),
        ("MLR BNLS BRSI", "13.90"),
        ("ORG RED BEETS", "2.99"),
    ]
    assert semantic["facts"]["total"] == "21.58"
    assert semantic["validation"]["itemSum"] == "21.58"
    assert semantic["sectionExtraction"]["financialReconciliation"]["selectedCount"] == 3


def test_semantic_json_reconstructs_split_table_and_corrects_impossible_tax_mapping():
    lines = [
        "KADAI INDIAN KITCHEN",
        "15755 61ST AVE N, PLYMOUTH, MN 55446",
        "06/29/2023 04:43:01 PM",
        "Quantity",
        "Price",
        "Custom Item",
        "1",
        "$120.00",
        "Custom Item",
        "2",
        "$130.00",
        "§0 Custom Item",
        "1",
        "$62.50",
        "Custom Item",
        "3",
        "$390.00",
        "CUSTOM ITEM",
        "1",
        "$420.00",
        "Garlic Naan",
        "30",
        "$120.00",
        "Butter Naan",
        "30",
        "$89.70",
        "Butter Naan",
        "30",
        "$89.76",
        "Sub Total",
        "$912.20",
        "Tax",
        "$980.84",
        "Tip",
        "$0",
        "Total",
        "$980.84",
        "Card Used",
        "AMEX",
        "Last Four",
        "****8007",
    ]

    semantic = ReceiptIntelligencePipeline().to_structured_json(raw_text="\n".join(lines), lines=lines)

    assert semantic["merchant"] == "KADAI INDIAN KITCHEN"
    assert semantic["facts"]["subtotal"] == "912.20"
    assert semantic["facts"]["tax"] == "68.64"
    assert semantic["facts"]["total"] == "980.84"
    assert [(item["name"], item["qty"], item["amount"]) for item in semantic["items"]] == [
        ("Custom Item", "1", "120.00"),
        ("Custom Item", "2", "130.00"),
        ("Custom Item", "1", "62.50"),
        ("Custom Item", "3", "390.00"),
        ("Garlic Naan", "30", "120.00"),
        ("Butter Naan", "30", "89.70"),
    ]
    assert semantic["validation"]["itemSum"] == "912.20"
    assert semantic["taxRelationship"]["inferredFromArithmetic"] is True
    assert semantic["sectionExtraction"]["financialReconciliation"]["delta"] == 0.0
    assert semantic["sectionExtraction"]["financialReconciliation"]["rejectedLineIndexes"] == [17]


def test_merchant_normalizer_leaves_item_like_header_candidate_unresolved():
    raw_text = """
EE LE a ee Ee
4140 ROAD 101 NORTH, PLYNQUTH, MM
PHARHACY: 478-4612 STORE:
1 SRTGA SPRK SPRNG Wi 282 2.89F
VISA CREDIT HHH HHH 3442
"""

    merchant = MerchantNormalizer().normalize(raw_text)

    assert merchant == ""


def test_merchant_normalizer_prefers_structural_business_identity_over_noisy_top_line():
    raw_text = """
pee
oat eam Gan See
coe
[ Lemos
1LNWE * 5
ROME
CENSFERS .
LEC
41205 VICKSBURG LAKE NORTH
PLYNUUTH>
(7635) 467-9000
[ Leoous's
LNWE'S HOME CRENSERS. LEC
PLYNQUTH, MN 55447 (7693 467-9000
Lawes
LNWE'S HOME CENTERS, LEC
1205 VICKSBURG LAKE NORTH
PLYNUUTH, MN 55447 (769) 367-9000
I Lowes
PNWE'S HOME CENFERS. LEE
4205 VICKSBURG LAKE NORTH
PLYNUUTH, MN 55447 (763) 3467-9000
"""

    merchant = MerchantNormalizer().normalize(raw_text)

    assert merchant == "LNWE'S HOME CENTERS, LLC"


def test_merchant_normalizer_recovers_short_pharmacy_acronym_from_policy_context():
    raw_text = """
EE LE a ee Ee
4140 ROAD 101 NORTH, PLYNQUTH, MM
PHARMACY: 978-4612 STORE: -
1 SRTGA SPRK SPRNG Wi 282 2,89F
cUS Return Policu, thry 07/13/2026
VISA CREDIT HHH HHH 3442
"""

    merchant = MerchantNormalizer().normalize(raw_text)

    assert merchant == "CVS"


def test_merchant_normalizer_rejects_ocr_policy_text_candidate_before_acronym_recovery():
    raw_text = """
EE LE a ee Ee
4140 ROAD 101 NORTH, PLYNQUTH, MM
PHARMACY: 978-4612 STORE: -
rt ulth reeelpt, sublect to
cUS Return Policu, thry 07/13/2026
VISA CREDIT HHH HHH 3442
"""

    merchant = MerchantNormalizer().normalize(raw_text, candidate="rt ulth reeelpt, sublect to")

    assert merchant == "CVS"


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


def test_visual_logo_candidate_can_supply_merchant_without_brand_template():
    semantic = ReceiptIntelligencePipeline().to_structured_json(
        raw_text="""
41205 VICKSBURG LAKE NORTH
S-TIER BLACK WIRE SHELVING 94.98
TOTAL 103.08
""",
        parser_json={
            "logoCandidates": [
                {
                    "merchant": "ACME HOME CENTERS",
                    "confidence": 0.84,
                    "source": "logo_header_crop",
                    "evidence": [{"type": "visual_logo_crop", "value": "ACME HOME CENTERS"}],
                }
            ]
        },
        ocr_engine="donut+ocr",
    )

    assert semantic["merchant"] == "ACME HOME CENTERS"
    assert semantic["confidence"]["merchant"] == 0.84
    assert semantic["confidenceTrace"]["merchant"]["source"] == "visual_logo_crop"


def test_purchase_date_resolver_uses_transaction_date_and_skips_policy_date():
    lines = [
        "LOWE'S HOME CENTERS, LLC",
        "SALES: FSTLAHOGS 13710h4 IRAUSH: 972915742 11-05-25",
        "CHIP REF IM: 1955294965534 10/05/25 17:35:12",
        "Return Policy thru 07/13/2026",
        "TOTAL 103.08",
    ]

    semantic = ReceiptIntelligencePipeline().to_structured_json(raw_text="\n".join(lines), lines=lines)

    assert semantic["date"] == "11/05/2025"
    assert semantic["purchaseDate"] == "11/05/2025"
    assert semantic["receiptEntities"]["confidence"]["date"] >= 0.7


def test_temporal_engine_extracts_named_month_dates_and_payment_times():
    lines = [
        "GENERIC STORE",
        "ORDER 05-Nov-2025 4:31 PM",
        "CARD PAYMENT 4:32 PM",
        "SUBTOTAL 10.00",
        "TAX 0.80",
        "TOTAL 10.80",
    ]

    semantic = ReceiptIntelligencePipeline().to_structured_json(raw_text="\n".join(lines), lines=lines)

    assert semantic["date"] == "11/05/2025 04:31 PM"
    assert semantic["orderDate"] == "11/05/2025 04:31 PM"
    assert semantic["transactionTime"] == ""
    assert semantic["paymentTime"] == "04:32 PM"
    assert semantic["temporalEntities"]["schemaVersion"] == "receipt-temporal-entities-v1"


def test_temporal_engine_extracts_mmddyyyy_transaction_timestamp_and_payment_time():
    lines = [
        "MARKET",
        "SALE 11/05/2025 4:31:07 PM",
        "VISA CREDIT AUTH 4:32 PM",
        "TOTAL 10.80",
    ]

    semantic = ReceiptIntelligencePipeline().to_structured_json(raw_text="\n".join(lines), lines=lines)

    assert semantic["transactionDate"] == "11/05/2025 04:31:07 PM"
    assert semantic["date"] == "11/05/2025 04:31:07 PM"
    assert semantic["transactionTime"] == "04:31:07 PM"
    assert semantic["paymentTime"] == "04:32 PM"
    assert semantic["temporalEntities"]["transactionDate"]["kind"] == "transactionDate"
    assert semantic["temporalEntities"]["paymentTime"]["kind"] == "paymentTime"


def test_temporal_engine_classifies_payment_context_timestamp_without_transaction_date():
    lines = [
        "MARKET",
        "CARD PAYMENT 05-Nov-2025 4:32 PM",
        "TOTAL 10.80",
    ]

    semantic = ReceiptIntelligencePipeline().to_structured_json(raw_text="\n".join(lines), lines=lines)

    assert semantic["transactionDate"] == ""
    assert semantic["date"] == ""
    assert semantic["paymentTime"] == "04:32 PM"
    assert semantic["temporalEntities"]["paymentTime"]["source"] == "receipt.payment_temporal_context"


def test_purchase_date_resolver_does_not_use_return_policy_date_only():
    lines = [
        "PHARMACY: 978-4612 STORE:",
        "SRTGA SPRK SPRNG 2.89",
        "Return Policy thru 07/13/2026",
        "VISA CREDIT ****3442",
    ]

    semantic = ReceiptIntelligencePipeline().to_structured_json(raw_text="\n".join(lines), lines=lines)

    assert semantic["date"] == ""
    assert semantic["purchaseDate"] == ""


def test_pipeline_uses_state_machine_to_keep_currency_balance_and_footer_out_of_items():
    semantic = ReceiptIntelligencePipeline().to_structured_json(
        raw_text="""
MARKET
APPLES 3.25
USD 3.25
BALANCE DUE 3.25
VISA ************2222
THANK YOU
BANANAS 1.00
""",
        ocr_engine="paddleocr",
    )

    assert [(item["name"], item["amount"]) for item in semantic["items"]] == [("APPLES", "3.25")]
    assert semantic["documentStateMachine"]["schemaVersion"] == "receipt-state-machine-v1"
    assert semantic["sectionExtraction"]["parserIsolation"]["footerIgnoredForItems"] is True
    assert any(
        row["line"] == "USD 3.25" and "locked_non_item_region" in row["reason"]
        for row in semantic["sectionExtraction"]["debug"]["rejectedItemRows"]
    )
    item_blocks = [block for block in semantic["semanticBlocks"] if block["kind"] == "items"]
    assert item_blocks
    assert all("USD" not in block["text"] and "BALANCE DUE" not in block["text"] for block in item_blocks)
    assert any(block["kind"] == "totals" and "BALANCE DUE" in block["text"] for block in semantic["semanticBlocks"])
    assert any(block["kind"] == "footer" and "BANANAS" in block["text"] for block in semantic["semanticBlocks"])
    assert semantic["confidenceTrace"]["arithmetic"]


def test_retail_multiline_row_stitches_description_to_pricing_pattern_with_graph():
    semantic = ReceiptIntelligencePipeline().to_structured_json(
        raw_text="",
        ocr_blocks=[
            {"text": "BLACK", "x": 30, "y": 20, "width": 44, "height": 12, "confidence": 0.96},
            {"text": "VELVET", "x": 80, "y": 20, "width": 55, "height": 12, "confidence": 0.96},
            {"text": "JEWELRY", "x": 142, "y": 20, "width": 68, "height": 12, "confidence": 0.95},
            {"text": "ORGANIZER", "x": 218, "y": 20, "width": 82, "height": 12, "confidence": 0.95},
            {"text": "Reg", "x": 48, "y": 38, "width": 28, "height": 12, "confidence": 0.94},
            {"text": "14.99", "x": 84, "y": 38, "width": 42, "height": 12, "confidence": 0.94},
            {"text": "5", "x": 164, "y": 38, "width": 10, "height": 12, "confidence": 0.96},
            {"text": "@", "x": 180, "y": 38, "width": 10, "height": 12, "confidence": 0.96},
            {"text": "14.99", "x": 196, "y": 38, "width": 42, "height": 12, "confidence": 0.96},
            {"text": "74.95", "x": 315, "y": 38, "width": 48, "height": 12, "confidence": 0.97},
            {"text": "SUBTOTAL", "x": 210, "y": 70, "width": 70, "height": 12, "confidence": 0.98},
            {"text": "74.95", "x": 315, "y": 70, "width": 48, "height": 12, "confidence": 0.98},
            {"text": "TOTAL", "x": 230, "y": 88, "width": 48, "height": 12, "confidence": 0.98},
            {"text": "74.95", "x": 315, "y": 88, "width": 48, "height": 12, "confidence": 0.98},
        ],
    )

    assert [(item["name"], item["qty"], item["unitPrice"], item["amount"]) for item in semantic["items"]] == [
        ("BLACK VELVET JEWELRY ORGANIZER", "5", "14.99", "74.95")
    ]
    retail = semantic["layout"]["retailRowReconstruction"]
    assert retail["schemaVersion"] == "receipt-retail-row-reconstruction-v1"
    assert retail["mergedRows"][0]["descriptionLineIndexes"] == [0]
    assert retail["mergedRows"][0]["pricingLineIndex"] == 1
    assert retail["arithmeticTraces"][0]["valid"] is True
    assert any(edge["type"] == "HAS_DESCRIPTION_LINE" for edge in retail["rowGraph"]["edges"])
    assert any("pending_description" in row for row in retail["visualization"])


def test_retail_multiline_michaels_layout_keeps_description_not_reg_price_line():
    lines = [
        "Michaels",
        "MICHAELS STORE #6717 (763) 519-2739",
        "3215 Vicksburg Ln N",
        "Plymouth,MN,55447-1317",
        "100 SALE 0769 6717 052 08/17/24 10:44",
        "ITEM INFORMATION",
        "Order NO.8117253604739854",
        "Black Velvet Jewelry... 00886946589751",
        "Reg 14.99 5 @ 14.99 74.95",
        "Black Velvet Jewelry... 00886946589836",
        "Reg 9.99 1 @ 9.99 9.99",
        "12” Triple Bar Black ... 00082676800658",
        "Reg 29.99 1 @ 29.99 29.99",
        "YOU SAVED .00",
        "PURCHASE SUMMARY",
        "SUBTOTAL 114.93",
        "SALES TAX 8.525% 9.80",
        "TOTAL 124.73",
    ]

    semantic = ReceiptIntelligencePipeline().to_structured_json(raw_text="\n".join(lines), lines=lines)

    assert [(item["name"], item["qty"], item["unitPrice"], item["amount"], item["sku"]) for item in semantic["items"]] == [
        ("Black Velvet Jewelry...", "5", "14.99", "74.95", "00886946589751"),
        ("Black Velvet Jewelry...", "1", "9.99", "9.99", "00886946589836"),
        ("12” Triple Bar Black ...", "1", "29.99", "29.99", "00082676800658"),
    ]
    assert semantic["validation"]["valid"] is True
    assert semantic["validation"]["itemSum"] == "114.93"
    assert all(not item["name"].lower().startswith(("reg", "req", "es reg")) for item in semantic["items"])


def test_retail_multiline_infers_extended_price_when_ocr_omits_final_amount():
    lines = [
        "ee MICHAELS SH va 6717 (763) 919-7739",
        "TEM INFORMATION eevee",
        "ee Black Velvet Jewelry... 0088694659975) ve",
        "eS Reg 1499 5@ 14.99",
        "SSS lack Velvet Jewelry... 00886946589836 3 Se",
        "Se Reg 999 1@ 9.99 999",
        "12\" Bar Black... 0082676800658",
        "Req 29.99 1@ 29.99 29.99 Mts",
        "So ae SUBTOTAL 114.93 iy",
        "a es SALES TAX 8.525% 9.80 pes",
        "TOTAL 124.73 es fo",
        "ee This receipt expires at 60 days on 10/16/24 ee",
        "See 08/17/24 10:44",
    ]

    semantic = ReceiptIntelligencePipeline().to_structured_json(raw_text="\n".join(lines), lines=lines)

    assert [(item["name"], item["qty"], item["unitPrice"], item["amount"], item.get("sku")) for item in semantic["items"]] == [
        ("ee Black Velvet Jewelry...", "5", "14.99", "74.95", "0088694659975"),
        ("SSS lack Velvet Jewelry...", "1", "9.99", "9.99", "00886946589836"),
        ('12" Bar Black...', "1", "29.99", "29.99", "0082676800658"),
    ]
    assert semantic["validation"]["valid"] is True
    assert semantic["validation"]["itemSum"] == "114.93"
    assert semantic["date"] == "08/17/2024 10:44"


def test_pipeline_rejects_policy_header_fuzzy_totals_and_impossible_item_rows():
    lines = [
        "No Purchase Necessary",
        "45760 {INT AVENUE N",
        "95/09/2026",
        "BEEF LIVER 4.69",
        "~ MLR BNLS BRS! 43.90",
        "PROT RO RED BEETS ii 2.99",
        "MLR BNLS BRSI 13.90",
        "BAI ANCE DUE 21.58",
        "POO BNLS BRST 43.90",
        "USD 21.58",
        "jot yspgn 2.58",
        "VISA",
    ]

    semantic = ReceiptIntelligencePipeline().to_structured_json(raw_text="\n".join(lines), lines=lines)

    assert semantic["merchant"] == ""
    assert semantic["address"] == ""
    assert semantic["lastFour"] == ""
    assert [(item["name"], item["amount"]) for item in semantic["items"]] == [
        ("BEEF LIVER", "4.69"),
        ("PROT RO RED BEETS ii", "2.99"),
        ("MLR BNLS BRSI", "13.90"),
    ]
    assert semantic["facts"]["total"] == "21.58"
    rejected = semantic["sectionExtraction"]["debug"]["rejectedItemRows"]
    assert any(row["line"] == "BAI ANCE DUE 21.58" and "locked_non_item_region" in row["reason"] for row in rejected)
    assert any(row["line"] == "USD 21.58" and "locked_non_item_region" in row["reason"] for row in rejected)
    assert any(row["line"] == "~ MLR BNLS BRS!" and row["reason"] == "item_amount_exceeds_receipt_total" for row in rejected)
    assert any(row["line"] == "POO BNLS BRST 43.90" and "after_item_region_boundary" in row["reason"] for row in rejected)
