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


def test_receipt_item_count_overrides_stale_fallback_totals_from_ocr_lines():
    pipeline = ReceiptRowConsolidationPipeline()
    lines = [
        "ah \\ Ey 1962714 KS ORG A2 FR 12.99 2!",
        "E+ 1098148 BIENA EDNAME =| 7.59 ae",
        "96716 ORG SPINACH 5.99",
        "1158 ORG ARUGULA 4.79",
        "F] 1368591 O/N 14.99",
        "1960751 GAR PARM BAG 7.99 Pt",
        "7113 6.99 fer",
        "Sh OE 131 ONG BRUSSELS 5.69",
        "he E 35410 THIGH MEAT 27.69",
        "2 921485 NUBZ Dog CHY 18159 ae",
        "sa E+ 1993061 SPINDRIFT 18.99",
        "Ey 175106 PART SHREDS 11.99",
        "E 1655404 GOATCUBEISLB 79.99",
        "SUBTOTAL - 244,36",
        "TAX 1.44",
        "Items Sold: 14",
    ]
    stale_fallback = {
        "available": True,
        "merchant": "Receipt Fallback",
        "items": [
            {"name": "GAR PRAM BAGI", "amount": "6.99"},
            {"name": "ORG BRUSSELS", "amount": "5.89"},
            {"name": "PAM SHREDI", "amount": "5.20"},
        ],
        "subtotal": "18.08",
        "tax": "0.00",
        "total": "18.08",
        "raw": {},
    }

    normalized = pipeline.normalize(stale_fallback, raw_text="\n".join(lines), lines=lines)

    assert len(normalized["items"]) == 14
    assert normalized["subtotal"] == "244.36"
    assert normalized["tax"] == "1.44"
    assert normalized["total"] == "245.80"
    assert normalized["rowConsolidation"]["reconciliation"]["matched"] is False
    assert normalized["rowConsolidation"]["reconciliation"]["itemCountTarget"] == 14
    assert "item_sum_does_not_match_receipt_total" in normalized["rowConsolidation"]["reconciliation"]["warnings"]
    assert {item["name"] for item in normalized["items"]} >= {"GOATCUBEISLB", "PART SHREDS", "THIGH MEAT"}


def test_standalone_minus_lines_attach_as_previous_item_discounts_and_address_survives():
    pipeline = ReceiptRowConsolidationPipeline()
    lines = [
        "MAPLE GROVE #648",
        "11330 FOUNTAINS DRIVE N",
        "MAPLE GROVE MN 55369",
        "E+ 1098148 BIENA EDMAME 7.59",
        "2% E 0000379064 /)1898148 > 2.30-",
        "E+ 1993061 SPINDRIFT 18.99",
        "E 0000380456 /1953061 5.20-",
        "Items Sold: 2",
        "AMOUNT? $19.08",
    ]

    normalized = pipeline.normalize(
        {"available": True, "merchant": "Maple Grove", "items": [], "raw": {}},
        raw_text="\n".join(lines),
        lines=lines,
    )

    items = {item["name"]: item for item in normalized["items"]}
    assert normalized["storeAddress"] == "11330 FOUNTAINS DRIVE N, MAPLE GROVE, MN 55369"
    assert items["BIENA EDMAME"]["amount"] == "7.59"
    assert items["BIENA EDMAME"]["discount"] == "2.30"
    assert items["BIENA EDMAME"]["netAmount"] == "5.29"
    assert items["SPINDRIFT"]["discount"] == "5.20"
    assert items["SPINDRIFT"]["netAmount"] == "13.79"
    assert all(not item["name"].endswith("-") for item in normalized["items"])


def test_fresh_thyme_department_rows_survive_legal_header_and_weighted_produce():
    pipeline = ReceiptRowConsolidationPipeline()
    lines = [
        "FRESHTHYME. COM",
        "AMERICAN EXPRESS Entry Method: Chip",
        "01/16/2025 11:10:18",
        "Total: USD$ 37.07",
        "APPROVED 887973",
        "DATiny",
        "0 EGGS PSTURE RSD 6.99 NF",
        "GROCERY",
        "O BROWN RICE LONG GR 2.19 N f",
        "O MARUCHAN RAMEN CHT 0.39 NF",
        "O MARUCHAN RAMEN CHT 0.39 NF",
        "0 ORG COCNT MILK 2.59 NF",
        "PRODUCE",
        "OCUCUMBERS GREEN 1.99 N f",
        "O CUCUMBERS GREEN 1.99 N F",
        "O ORG BUNCH CARRO 2.99 NF",
        "O RED ONION 2LB 2.99 N |",
        "0 RED ONION 2LB 2.99 N F",
        "O RED ONION 2LB 2.99 .N.F",
        "O-RED ROSE POTATO x",
        "2.02 lb @ 0.77/ lb 1.56 NF",
        "You saved 1.05",
        "0 SPICY GUACAMOLE 4.99 tIF",
        "O SWEET POTATO",
        "1.26 lb @ 1.29/ lb 1.63 Nf",
        "BALANCE DUE 37.07",
        "American Express 37.07",
        "CHANGE 0.00",
        "TAX-CODE TAXABLE-VAL TAX-VALUE",
        "Tax 1 4.99 0.06",
        "Tax 2 4.99 0.34",
        "TOTAL TAX 0.40",
        "TOTAL DISCOUNTS 1 1.05",
        "Total number of items sold = 14",
        "STORE:00508 REGISTER:012 CASHIER:0912",
        "TICKET#:9646 16JAN2025 11:10:20",
        "NO PURCHASE NECESSARY TO ENTER SWEEPSTAKES",
    ]

    normalized = pipeline.normalize(
        {"available": True, "merchant": "FRESHTHYME", "items": [], "raw": {}},
        raw_text="\n".join(lines),
        lines=lines,
        parser_json={"company": "FRESHTHYME"},
    )

    item_names = [item["name"] for item in normalized["items"]]
    amounts = {item["name"]: item["amount"] for item in normalized["items"]}

    assert len(normalized["items"]) == 14
    assert normalized["total"] == "37.07"
    assert normalized["tax"] == "0.40"
    assert normalized["rowConsolidation"]["reconciliation"]["matched"] is True
    assert normalized["rowConsolidation"]["reconciliation"]["itemCountTarget"] == 14
    assert item_names.count("MARUCHAN RAMEN CHT") == 2
    assert item_names.count("RED ONION 2LB") == 3
    assert amounts["RED ROSE POTATO x"] == "1.56"
    assert amounts["SWEET POTATO"] == "1.63"
    assert not any("SWEEPSTAKES" in name.upper() or "YOU SAVED" in name.upper() or "TOTAL DISCOUNTS" in name.upper() for name in item_names)
