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
