import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.receipt_row_consolidation import ReceiptRowConsolidationPipeline


def test_consolidates_duplicate_donut_rows_and_excludes_totals_payment_rows():
    pipeline = ReceiptRowConsolidationPipeline()
    donut = {
        "available": True,
        "merchant": "LOWES",
        "items": [
            {"name": "MULCH BAG", "qty": "2", "amount": "7.00", "confidence": 0.88},
            {"name": "Mulch Bag 331222", "qty": "2", "amount": "7.00", "confidence": 0.81},
            {"name": "TOTAL", "amount": "11.61", "confidence": 0.93},
            {"name": "VISA APPROVED", "amount": "11.61", "confidence": 0.9},
        ],
        "subtotal": "10.75",
        "tax": "0.86",
        "total": "11.61",
        "raw": {},
    }

    normalized = pipeline.normalize(
        donut,
        raw_text="""
LOWE'S HOME CENTERS, LLC
2 EA MULCH BAG 7.00
WASHERS 3.75
SUBTOTAL 10.75
TAX 0.86
TOTAL 11.61
VISA APPROVED 11.61
""",
        lines=[
            "LOWE'S HOME CENTERS, LLC",
            "2 EA MULCH BAG 7.00",
            "WASHERS 3.75",
            "SUBTOTAL 10.75",
            "TAX 0.86",
            "TOTAL 11.61",
            "VISA APPROVED 11.61",
        ],
    )

    assert normalized["merchant"] == "LOWE'S HOME CENTERS, LLC"
    assert [(item["name"], item["amount"]) for item in normalized["items"]] == [
        ("MULCH BAG", "7.00"),
        ("WASHERS", "3.75"),
    ]
    assert normalized["rowConsolidation"]["candidateCount"] >= 4
    assert any("receipt_level_term" in row["reasons"] for row in normalized["rowConsolidation"]["rejectedRows"])


def test_rejects_serialized_hallucinated_donut_names_from_cvs_sample():
    pipeline = ReceiptRowConsolidationPipeline()
    donut = {
        "available": True,
        "merchant": "",
        "items": [
            {
                "name": "['ROAD 101 NORTH PLYMOUTH, MN PHARMACY: 478-4612 STORE: -', '<s_nm> REG#04 TRN#5652 CSHR#2827889 STR#68']",
                "qty": "1",
                "amount": "2.89",
                "confidence": 0.82,
            }
        ],
        "subtotal": "347",
        "tax": "",
        "total": "2.89",
        "raw": {
            "menu": {
                "nm": [
                    "ROAD 101 NORTH PLYMOUTH, MN PHARMACY: 478-4612 STORE: -",
                    "<s_nm> REG#04 TRN#5652 CSHR#2827889 STR#68",
                ],
                "price": "2.89F",
            }
        },
    }

    normalized = pipeline.normalize(donut)

    assert normalized["items"] == []
    assert normalized["rowConsolidation"]["rejectedCandidateCount"] >= 1
    assert any("serialized_or_tagged_text" in row["reasons"] for row in normalized["rowConsolidation"]["rejectedRows"])
    assert normalized["rowConsolidation"]["retryPlan"]


def test_subtotal_reconciliation_selects_matching_subset():
    pipeline = ReceiptRowConsolidationPipeline()
    donut = {
        "available": True,
        "merchant": "KADAI INDIAN KITCHEN",
        "items": [
            {"name": "Custom Item", "amount": "390.00", "confidence": 0.9},
            {"name": "Custom ltem duplicate", "amount": "390.00", "confidence": 0.7},
            {"name": "Custom Item", "amount": "130.00", "confidence": 0.9},
            {"name": "Change Due", "amount": "10.00", "confidence": 0.8},
        ],
        "subtotal": "520.00",
        "tax": "0.00",
        "total": "520.00",
        "raw": {},
    }

    normalized = pipeline.normalize(donut)

    assert [(item["amount"]) for item in normalized["items"]] == ["390.00", "130.00"]
    assert normalized["rowConsolidation"]["reconciliation"]["matched"] is True


def test_discards_implausible_no_cents_subtotal_from_donut():
    pipeline = ReceiptRowConsolidationPipeline()
    donut = {
        "available": True,
        "merchant": "",
        "items": [],
        "subtotal": "347",
        "tax": "",
        "total": "2.89",
        "raw": {},
    }

    normalized = pipeline.normalize(donut)

    assert normalized["subtotal"] == ""
    assert normalized["total"] == "2.89"


def test_clusters_same_visual_line_ocr_candidates_by_price_and_y_position():
    pipeline = ReceiptRowConsolidationPipeline()
    donut = {
        "available": True,
        "merchant": "FRESHTHYME.COM",
        "items": [
            {"name": "MLR BNLS BRST", "amount": "8.99", "confidence": 0.83, "bbox": {"x": 42, "y": 220, "width": 190, "height": 18}},
            {"name": "MLR BNLS BRSI", "amount": "8.99", "confidence": 0.72, "bbox": {"x": 43, "y": 224, "width": 188, "height": 18}},
            {"name": "POO BNLS BRST", "amount": "8.99", "confidence": 0.66, "bbox": {"x": 41, "y": 221, "width": 192, "height": 18}},
            {"name": "ORGANIC BANANAS", "amount": "2.49", "confidence": 0.88, "bbox": {"x": 42, "y": 260, "width": 190, "height": 18}},
        ],
        "subtotal": "11.48",
        "total": "11.48",
        "itemCount": "2",
        "raw": {},
    }

    normalized = pipeline.normalize(donut)

    assert [(item["name"], item["amount"]) for item in normalized["items"]] == [
        ("MLR BNLS BRST", "8.99"),
        ("ORGANIC BANANAS", "2.49"),
    ]
    assert normalized["rowConsolidation"]["duplicateClusterCount"] == 1
    duplicate_cluster = normalized["rowConsolidation"]["duplicateRows"][0]
    assert duplicate_cluster["selected"]["name"] == "MLR BNLS BRST"
    assert {row["name"] for row in duplicate_cluster["duplicates"]} == {"MLR BNLS BRSI", "POO BNLS BRST"}
    assert normalized["rowConsolidation"]["reconciliation"]["itemCountTarget"] == 2
    assert normalized["rowConsolidation"]["reconciliation"]["matched"] is True


def test_rejects_low_confidence_hallucinated_duplicate_rows():
    pipeline = ReceiptRowConsolidationPipeline()
    donut = {
        "available": True,
        "merchant": "",
        "items": [
            {"name": "REAL PRODUCT", "amount": "4.99", "confidence": 0.86},
            {"name": "R3AL PR0DUCT", "amount": "4.99", "confidence": 0.31},
        ],
        "subtotal": "4.99",
        "total": "4.99",
        "raw": {},
    }

    normalized = pipeline.normalize(donut)

    assert [(item["name"], item["amount"]) for item in normalized["items"]] == [("REAL PRODUCT", "4.99")]
    assert any("low_source_confidence" in row["reasons"] for row in normalized["rowConsolidation"]["rejectedRows"])
