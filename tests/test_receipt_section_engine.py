import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.receipt_row_consolidation import ReceiptRowConsolidationPipeline
from services.receipt_section_engine import ReceiptSectionExtractionEngine


def test_section_engine_extracts_totals_payment_and_items_from_lines():
    engine = ReceiptSectionExtractionEngine()

    result = engine.extract(lines=[
        "LOWE'S HOME CENTERS, LLC",
        "123 MAIN STREET",
        "2 EA MULCH BAG 7.00",
        "WASHERS 3.75",
        "SUBTOTAL 10.75",
        "TAX 0.86",
        "TOTAL 11.61",
        "VISA ************1234",
        "AUTH CODE 9A7B6C",
        "CHARGE 11.61",
        "THANK YOU",
    ])

    assert [item["name"] for item in result["items"]] == ["MULCH BAG", "WASHERS"]
    assert result["totals"]["fields"]["subtotal"] == "10.75"
    assert result["totals"]["fields"]["tax"] == "0.86"
    assert result["totals"]["fields"]["total"] == "11.61"
    assert result["payment"]["fields"]["paymentMethod"] == "card"
    assert result["payment"]["fields"]["cardUsed"] == "VISA"
    assert result["payment"]["fields"]["cardLast4"] == "1234"
    assert result["payment"]["fields"]["approvalCode"] == "9A7B6C"


def test_section_engine_extracts_last_four_from_split_payment_rows():
    result = ReceiptSectionExtractionEngine().extract(lines=[
        "FRESHTHYME.COM",
        "TOTAL 21.58",
        "CARD USED",
        "VISA",
        "LAST FOUR",
        "1234",
    ])

    assert result["payment"]["fields"]["cardUsed"] == "VISA"
    assert result["payment"]["fields"]["cardLast4"] == "1234"


def test_section_engine_groups_ocr_boxes_by_y_position_and_alignment():
    engine = ReceiptSectionExtractionEngine()
    boxes = [
        {"text": "LOWE'S", "x": 20, "y": 10, "width": 80, "height": 12, "confidence": 0.98},
        {"text": "MULCH BAG", "x": 20, "y": 54, "width": 90, "height": 12, "confidence": 0.93},
        {"text": "7.00", "x": 250, "y": 54, "width": 36, "height": 12, "confidence": 0.94},
        {"text": "SUBTOTAL", "x": 20, "y": 84, "width": 70, "height": 12, "confidence": 0.96},
        {"text": "7.00", "x": 250, "y": 84, "width": 36, "height": 12, "confidence": 0.96},
        {"text": "TAX", "x": 20, "y": 104, "width": 28, "height": 12, "confidence": 0.95},
        {"text": "0.56", "x": 250, "y": 104, "width": 36, "height": 12, "confidence": 0.95},
        {"text": "TOTAL", "x": 20, "y": 124, "width": 48, "height": 12, "confidence": 0.97},
        {"text": "7.56", "x": 250, "y": 124, "width": 36, "height": 12, "confidence": 0.97},
        {"text": "MASTERCARD", "x": 20, "y": 150, "width": 90, "height": 12, "confidence": 0.92},
        {"text": "ENDING IN 9876", "x": 145, "y": 150, "width": 110, "height": 12, "confidence": 0.92},
        {"text": "APPROVAL", "x": 20, "y": 170, "width": 70, "height": 12, "confidence": 0.91},
        {"text": "A1B2C3", "x": 145, "y": 170, "width": 65, "height": 12, "confidence": 0.91},
    ]

    result = engine.extract(ocr_blocks=boxes)

    assert result["items"][0]["name"] == "MULCH BAG"
    assert result["totals"]["fields"] == {"subtotal": "7.00", "tax": "0.56", "total": "7.56"}
    assert result["payment"]["fields"]["cardUsed"] == "MASTERCARD"
    assert result["payment"]["fields"]["cardLast4"] == "9876"
    assert result["payment"]["fields"]["approvalCode"] == "A1B2C3"


def test_totals_parser_extracts_tax_rate_amount_relationship_without_cross_mapping():
    result = ReceiptSectionExtractionEngine().extract(lines=[
        "GENERIC STORE",
        "LARGE ITEM 912.16",
        "SUBTOTAL 912.16",
        "Sales Tax 7.525% 68.64",
        "TOTAL 980.80",
    ])

    assert result["totals"]["fields"]["tax"] == "68.64"
    assert result["totals"]["fields"]["taxPercent"] == "7.525"
    assert result["totals"]["fields"]["taxAmount"] == "68.64"
    assert result["totals"]["taxRelationship"]["valid"] is True
    assert result["debug"]["taxRelationshipDiagnostics"]


def test_section_engine_reconstructs_space_separated_cents_and_does_not_use_subtotal_as_item_price():
    result = ReceiptSectionExtractionEngine().extract(lines=[
        "KADAI INDIAN KITCHEN",
        "29-Jun-2023 4:43:01P",
        "3 Custom Item $390 00",
        "2 Custom Item $130.00",
        "1 Custom Item $120 00",
        "50 Custom Item $62.50",
        "30 Butter Naan $89.70",
        "30 Garlic Naan $120 00",
        "Subtotal $912.20",
        "Sales Tax 7.525% $68 64",
        "Total $980.84",
        "AMEX 8007",
        "30 Garlic Naan",
        "Subtotal",
        "$912.20",
    ])

    assert sorted((item["name"], item["amount"]) for item in result["items"]) == sorted([
        ("Custom Item", "390.00"),
        ("Custom Item", "130.00"),
        ("Custom Item", "120.00"),
        ("Custom Item", "62.50"),
        ("Butter Naan", "89.70"),
        ("Garlic Naan", "120.00"),
    ])
    assert result["totals"]["fields"]["tax"] == "68.64"
    assert result["financialReconciliation"]["selectedSum"] == "912.20"
    assert all(item["amount"] != "912.20" for item in result["items"])


def test_totals_parser_rejects_tax_equal_to_total_and_infers_arithmetic_tax():
    result = ReceiptSectionExtractionEngine().extract(lines=[
        "GENERIC STORE",
        "Custom Item",
        "1",
        "$120.00",
        "Sub Total",
        "$912.20",
        "Tax",
        "$980.84",
        "Tip",
        "$0",
        "Total",
        "$980.84",
    ])

    assert result["totals"]["fields"]["tax"] == "68.64"
    assert result["totals"]["fields"]["taxAmount"] == "68.64"
    assert result["totals"]["taxRelationship"]["inferredFromArithmetic"] is True
    assert result["totals"]["taxRelationship"]["rejectedTaxCandidate"] == "980.84"


def test_section_engine_emits_financial_table_graph_for_reconstructed_rows():
    result = ReceiptSectionExtractionEngine().extract(lines=[
        "GENERIC STORE",
        "2 EA MULCH BAG 7.00",
        "WASHERS 3 @ 1.25 3.75",
        "SUBTOTAL 10.75",
        "TAX 0.86",
        "TOTAL 11.61",
    ])

    table_graph = result["tableGraph"]
    assert table_graph["schemaVersion"] == "receipt-table-graph-v1"
    assert [(row["quantity"], row["description"], row["unitPrice"], row["extendedPrice"]) for row in table_graph["rows"]] == [
        ("2", "MULCH BAG", "3.50", "7.00"),
        ("3", "WASHERS", "1.25", "3.75"),
    ]
    assert any(edge["type"] == "HAS_EXTENDEDPRICE" for edge in table_graph["edges"])
    assert result["debug"]["rowReconstructionVisualization"]


def test_row_consolidation_uses_section_fields_and_section_item_candidates():
    pipeline = ReceiptRowConsolidationPipeline()
    normalized = pipeline.normalize(
        {"available": True, "merchant": "", "items": [], "raw": {}},
        lines=[
            "LOWE'S HOME CENTERS, LLC",
            "2 EA MULCH BAG 7.00",
            "WASHERS 3.75",
            "SUBTOTAL 10.75",
            "TAX 0.86",
            "TOTAL 11.61",
            "VISA ************1234",
            "AUTH CODE 9A7B6C",
            "CHARGE 11.61",
        ],
    )

    assert [(item["name"], item["amount"]) for item in normalized["items"]] == [
        ("MULCH BAG", "7.00"),
        ("WASHERS", "3.75"),
    ]
    assert normalized["subtotal"] == "10.75"
    assert normalized["tax"] == "0.86"
    assert normalized["total"] == "11.61"
    assert normalized["charge"] == "11.61"
    assert normalized["paymentMethod"] == "card"
    assert normalized["cardUsed"] == "VISA"
    assert normalized["cardLast4"] == "1234"
    assert normalized["approvalCode"] == "9A7B6C"
    assert normalized["sectionExtraction"]["schemaVersion"] == "receipt-sections-v1"


def test_item_parser_rejects_mutated_totals_payment_and_survey_rows():
    pipeline = ReceiptRowConsolidationPipeline()
    normalized = pipeline.normalize(
        {
            "available": True,
            "merchant": "",
            "items": [
                {"name": "GATT", "amount": "11.61", "confidence": 0.91},
                {"name": "HARGE", "amount": "11.61", "confidence": 0.91},
                {"name": "SURVEY 123456789012", "amount": "1.00", "confidence": 0.8},
            ],
            "raw": {},
        },
        lines=[
            "LOWE'S HOME CENTERS, LLC",
            "MULCH BAG 7.00",
            "WASHERS 3.75",
            "SUBTOTAL 10.75",
            "TAX 0.86",
            "GATT 11.61",
            "VISA ************1234",
            "HARGE 11.61",
            "SURVEY 123456789012",
        ],
    )

    assert [(item["name"], item["amount"]) for item in normalized["items"]] == [
        ("MULCH BAG", "7.00"),
        ("WASHERS", "3.75"),
    ]
    rejected = normalized["rowConsolidation"]["rejectedRows"]
    assert any(row["name"] == "GATT" and "ocr_mutation_of_receipt_level_term" in row["reasons"] for row in rejected)
    assert any(row["name"] == "HARGE" and "ocr_mutation_of_receipt_level_term" in row["reasons"] for row in rejected)
    debug_rejections = normalized["sectionExtraction"]["debug"]["rejectedItemRows"]
    assert any("locked_non_item_region" in row["reason"] for row in debug_rejections)
    assert any("survey_or_barcode" in row["reason"] for row in debug_rejections)


def test_state_machine_isolates_totals_payment_footer_from_item_parser():
    result = ReceiptSectionExtractionEngine().extract(lines=[
        "GENERIC MARKET",
        "APPLES 3.25",
        "USD 3.25",
        "BALANCE DUE 3.25",
        "VISA ************2222",
        "THANK YOU",
        "BANANAS 1.00",
    ])

    assert [item["name"] for item in result["items"]] == ["APPLES"]
    assert result["documentStateMachine"]["states"] == ["HEADER", "ITEMS", "TOTALS", "PAYMENT", "FOOTER"]
    assert result["parserIsolation"]["itemsParserActiveOnlyIn"] == ["ITEMS"]
    rejected = result["debug"]["rejectedItemRows"]
    assert any(row["line"] == "USD 3.25" and "locked_non_item_region" in row["reason"] for row in rejected)
    assert any(row["line"] == "BALANCE DUE 3.25" and "locked_non_item_region" in row["reason"] for row in rejected)
    assert any(row["line"] == "BANANAS 1.00" and "after_item_region_boundary" in row["reason"] for row in rejected)
    assert result["debug"]["regionOverlays"]
    assert result["debug"]["arithmeticValidationLogs"]
    assert set(["ocr", "arithmetic", "semantic", "merchant"]).issubset(result["confidence"].keys())


def test_section_engine_emits_layout_graph_and_collapses_duplicate_item_candidates():
    result = ReceiptSectionExtractionEngine().extract(lines=[
        "GENERIC MARKET",
        "MLR BNLS BRST 13.90",
        "MLR BNLS BRSI 13.90",
        "TOTAL 13.90",
        "VISA ************4444",
    ])

    assert [(item["name"], item["amount"]) for item in result["items"]] == [("MLR BNLS BRST", "13.90")]
    assert result["layoutGraph"]["schemaVersion"] == "receipt-layout-graph-v1"
    assert any(node["type"] == "ITEMS" for node in result["layoutGraph"]["nodes"])
    assert any(edge["type"] == "NEXT_REGION" for edge in result["layoutGraph"]["edges"])
    rejected = result["debug"]["rejectedItemRows"]
    assert any(row["reason"] == "duplicate_item_candidate_suppressed" for row in rejected)
    assert result["debug"]["duplicateSuppressionDiagnostics"]


def test_item_cardinality_and_financial_solver_select_consistent_subset():
    result = ReceiptSectionExtractionEngine().extract(lines=[
        "GENERIC MARKET",
        "BEEF LIVER 4.69",
        "MLR BNLS BRS! 43.90",
        "ORG RED BEETS 2.99",
        "MLR BNLS BRSI 13.90",
        "jot yspgn 2.58",
        "Total number of items sold 3",
        "TOTAL 21.58",
        "VISA",
    ])

    assert [(item["name"], item["amount"]) for item in result["items"]] == [
        ("BEEF LIVER", "4.69"),
        ("ORG RED BEETS", "2.99"),
        ("MLR BNLS BRSI", "13.90"),
    ]
    assert result["itemCardinality"]["count"] == 3
    assert result["financialReconciliation"]["selectedCount"] == 3
    assert result["financialReconciliation"]["selectedSum"] == "21.58"
    assert result["itemCandidateGraph"]["schemaVersion"] == "receipt-item-candidate-graph-v1"
    rejected = result["debug"]["rejectedItemRows"]
    assert any(row["line"] == "jot yspgn" and row["reason"] == "global_financial_reconciliation_rejected" for row in rejected)


def test_split_ocr_rows_use_cardinality_and_total_to_reject_payment_footer_noise():
    result = ReceiptSectionExtractionEngine().extract(lines=[
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
    ])

    assert [(item["name"], item["amount"]) for item in result["items"]] == [
        ("BEEF LIVER", "4.69"),
        ("PROT RO RED BEETS ii", "2.99"),
        ("MLR BNLS BRSI", "13.90"),
    ]
    assert result["totals"]["fields"]["total"] == "21.58"
    assert result["itemCardinality"]["count"] == 3
    assert result["financialReconciliation"]["selectedCount"] == 3
    assert result["financialReconciliation"]["selectedSum"] == "21.58"
    rejected = result["debug"]["rejectedItemRows"]
    assert any(row["line"] == "jot yspgn" and row["reason"] == "global_financial_reconciliation_rejected" for row in rejected)
