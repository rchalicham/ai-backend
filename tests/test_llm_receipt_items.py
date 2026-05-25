import json
import os
import importlib.util
import sys
from types import SimpleNamespace

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
SPEC = importlib.util.spec_from_file_location("actual_llm_service", os.path.join(ROOT, "services", "llm_service.py"))
actual_llm_service = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(actual_llm_service)
LLMService = actual_llm_service.LLMService


def test_receipt_item_postprocessing_dedupes_ocr_variants_and_removes_totals():
    service = LLMService()
    raw_text = """
ROCKFORD PLAZA
REGULAR SALE
22 ~ Pei 836656 $9.99 I
32 » GARDEN 303531 $16.99 J
32 — GARDEN 303367 $19.99 7
56 - Q LIN 489656 $2.49 I
54 GOURMET FOOD 319856 $3.49 N
Subtotal $52.95
MN 7.525% Sales Tax $3.72
Total $56.67
AMEX 7 $56.67
Sold Item Count = 5
22 PLA 836656 $9.99 I
32 - GARUIN 303531 $16.99 I
32 GARDEN 303367 $19.99 I
56 - Q LINE 489656 $2.49 I
54 - GOURMET FOOD 319856 $3.49 N
"""
    llm_content = json.dumps({
        "company": "ROCKFORD PLAZA",
        "subtotal": "52.95",
        "tax": "3.72",
        "total": "56.67",
        "items": [
            {"name": "22 ~ Pei 836656", "amount": "9.99"},
            {"name": "32 » GARDEN 303531", "amount": "16.99"},
            {"name": "56 - Q LIN 489656", "amount": "2.49"},
            {"name": "54 GOURMET FOOD 319856", "amount": "3.49"},
            {"name": "AMEX 7", "amount": "56.67"},
            {"name": "22 PLA 836656", "amount": "9.99"},
            {"name": "32 GARDEN 303367", "amount": "19.99"},
            {"name": "MN 7.525% Sales Tax", "amount": "3.72"},
        ],
    })

    receipt = service._normalize_receipt_response(llm_content, {}, raw_text)

    assert receipt["subtotal"] == "52.95"
    assert [item["amount"] for item in receipt["items"]] == ["9.99", "16.99", "19.99", "2.49", "3.49"]
    assert [item["name"] for item in receipt["items"]] == ["PET", "GARDEN", "GARDEN", "Q LINE", "GOURMET FOOD"]


def test_finalize_receipt_prefers_reconciled_intelligence_items_over_llm_duplicates():
    service = LLMService()
    intelligence = SimpleNamespace(
        merchant="CVS",
        items=[{"name": "SRTGA SPRK SPRNG Wi 282", "qty": "1", "amount": "2.89", "weight": 0.93}],
        facts={"total": "2.89", "subtotal": "", "tax": "0", "tip": "0"},
        lines=[],
        semantic_blocks=[],
        tables=[],
        graph={},
        layout_json={},
    )
    structured = {
        "company": "CVS",
        "subtotal": "0",
        "tax": "0",
        "tip": "0",
        "total": "2.89",
        "items": [
            {"name": "SRTGA SPRK SPRNG Wi 282", "qty": "1", "amount": "2.89"},
            {"name": "SRTGA SPRK SPRNG W 282", "qty": "1", "amount": "2.89"},
            {"name": "SRTGA SPRK SPRNG WW 282", "qty": "1", "amount": "2.89"},
        ],
    }

    receipt = service._finalize_receipt_intelligence(structured, intelligence)

    assert [(item["name"], item["qty"], item["amount"]) for item in receipt["items"]] == [
        ("SRTGA SPRK SPRNG Wi 282", "1", "2.89")
    ]
    assert receipt["receiptIntelligence"]["validation"]["itemSum"] == "2.89"


def test_receipt_company_uses_merchant_footer_clues_over_plaza_line():
    service = LLMService()
    raw_text = """
ROCKFORD PLAZA
4190 VINEWOOD LANE #134
PLYMOUTH, MN 55442
Fresh Thyme VALUES YOUR FEEDBACK!!!
THANK YOU FOR SHOPPING AT FRESH THYME
Visit www.FRESHTHYMEFEEDBACK.com
"""
    llm_content = json.dumps({
        "company": "ROCKFORD PLAZA",
        "storeName": "ROCKFORD PLAZA",
        "subtotal": "0",
        "tax": "0",
        "total": "0",
        "items": [],
    })

    receipt = service._normalize_receipt_response(llm_content, {}, raw_text)

    assert receipt["company"] == "Freshthyme"
    assert receipt["storeName"] == "Freshthyme"


def test_receipt_address_prefers_city_state_zip_after_street_over_feedback_text_code():
    service = LLMService()
    raw_text = """
KADAI INDIAN KITCHEN
PLY
15755 61ST AVE N
PLYMOUTH, MN 55446
6124238463
ORDER: 07
Text "skicit" to 73752
to send us your feedback
"""
    llm_content = json.dumps({
        "company": "KADAI INDIAN KITCHEN",
        "storeAddress": "15755 61ST AVE N, TEXT “SKICIT” TO 73752",
        "subtotal": "0",
        "tax": "0",
        "total": "0",
        "items": [],
    })

    receipt = service._normalize_receipt_response(llm_content, {}, raw_text)

    assert receipt["storeAddress"] == "15755 61ST AVE N, PLYMOUTH, MN 55446"


def test_receipt_items_preserve_quantity_before_or_after_name_and_fix_truncated_item():
    service = LLMService()
    raw_text = """
KADAI INDIAN KITCHEN
3 Custom Item 390 00
2 Custom tem 130.00
Butter Naan 30 89.76
Garlic Naan
120 00
Subtotal 729.76
Total 729.76
"""
    llm_content = json.dumps({
        "company": "KADAI INDIAN KITCHEN",
        "subtotal": "729.76",
        "total": "729.76",
        "items": [
            {"name": "3 Custom Item", "amount": "390.00"},
            {"name": "2 Custom tem", "amount": "130.00"},
        ],
    })

    receipt = service._normalize_receipt_response(llm_content, {}, raw_text)

    assert [
        (item["name"], item["qty"], item["amount"])
        for item in receipt["items"]
    ] == [
        ("Custom Item", "3", "390.00"),
        ("CUSTOM ITEM", "2", "130.00"),
        ("Butter Naan", "30", "89.76"),
        ("Garlic Naan", "1", "120.00"),
    ]


def test_lowes_shelving_corrects_ocr_s_tier_to_5_tier():
    service = LLMService()
    raw_text = """
LOWE'S HOME CENTERS, LLC
21av74 S-TIER BLACK WIRE SHELUIN 94,96
SUBTOTAL: 94.98
TOTAL: 103.08
"""
    llm_content = json.dumps({
        "company": "LOWE'S HOME CENTERS, LLC",
        "subtotal": "94.98",
        "total": "103.08",
        "items": [
            {"name": "21av74 S-TIER BLACK WIRE SHELUIN", "amount": "94.96"},
        ],
    })

    receipt = service._normalize_receipt_response(llm_content, {}, raw_text)

    assert receipt["items"][0]["name"] == "5-TIER BLACK WIRE SHELVING"


def test_lowes_tax_prefers_inferred_tax_when_llm_copies_total():
    service = LLMService()
    raw_text = """
LOWE'S HOME CENTERS, LLC
21av74 S-TIER BLACK WIRE SHELUIN 94,96
SUBTOTAL: 94.98
TCTAL fAXK: 8.10
INVOICE TOTAL: 103.08
AMEX: 103.08
"""
    llm_content = json.dumps({
        "company": "LOWE'S HOME CENTERS, LLC",
        "subtotal": "94.98",
        "tax": "103.08",
        "total": "103.08",
        "items": [
            {"name": "21av74 S-TIER BLACK WIRE SHELUIN", "amount": "94.96"},
        ],
    })

    receipt = service._normalize_receipt_response(llm_content, {}, raw_text)

    assert receipt["tax"] == "8.10"
    assert receipt["total"] == "103.08"


def test_company_preserves_uncertain_ocr_variant_without_merchant_specific_correction():
    service = LLMService()
    raw_text = """
PENT COP
HOME CENFERS, LLC
21av74 S-TIER BLACK WIRE SHELUIN 94,96
SUBTOTAL: 94.98
TOTAL: 103.08
"""
    llm_content = json.dumps({
        "company": "PENT COP",
        "subtotal": "94.98",
        "total": "103.08",
        "items": [
            {"name": "21av74 S-TIER BLACK WIRE SHELUIN", "amount": "94.96"},
        ],
    })

    receipt = service._normalize_receipt_response(llm_content, {}, raw_text)

    assert receipt["company"] == "PENT COP"
    assert receipt["storeName"] == "PENT COP"


def test_receipt_items_ignore_duplicate_later_ocr_passes_after_first_subtotal():
    service = LLMService()
    raw_text = """
KADAI INDIAN KITCHEN
3 Custom Item 390 00
2 Custom Item 130.00
1 Custom Item 120 00
50 Custom Item 62.50
30 Butter Naan 89.76
30 Garlic Naan 120 00
Subtotal 912.20
Total 980.84
2 Custom tem 130.00
1 Custom ltem 420 00
30 Butter Naan 89.70
Subtotall 912.20
Total of 980.84
"""
    llm_content = json.dumps({
        "company": "KADAI INDIAN KITCHEN",
        "subtotal": "912.20",
        "total": "980.84",
        "items": [
            {"name": "3 Custom Item", "amount": "390.00"},
            {"name": "2 Custom Item", "amount": "130.00"},
            {"name": "1 Custom Item", "amount": "120.00"},
            {"name": "50 Custom Item", "amount": "62.50"},
            {"name": "30 Butter Naan", "amount": "89.76"},
            {"name": "30 Garlic Naan", "amount": "120.00"},
            {"name": "1 Custom ltem", "amount": "420.00"},
            {"name": "30 Butter Naan", "amount": "89.70"},
        ],
    })

    receipt = service._normalize_receipt_response(llm_content, {}, raw_text)

    assert [
        (item["name"], item["qty"], item["amount"])
        for item in receipt["items"]
    ] == [
        ("Custom Item", "3", "390.00"),
        ("Custom Item", "2", "130.00"),
        ("Custom Item", "1", "120.00"),
        ("Custom Item", "50", "62.50"),
        ("Butter Naan", "30", "89.76"),
        ("Garlic Naan", "30", "120.00"),
    ]


def test_receipt_date_reconciles_month_day_and_year_from_noisy_ocr_variants():
    service = LLMService()
    raw_text = """
SALES@: FSTLANOD 13871084 TRASH: 272915742 11-05-25
CHIP REF IM: 1955294655934 11/65/23 17:35:12
STGRE: 195>D TERMINAL: 29 91/05/23 17-35-22
21av74 S-TIER BLACK WIRE SHELUIN 94,96
"""
    llm_content = json.dumps({
        "company": "LOWE'S HOME CENTERS, LLC",
        "date": "11/05/25 17:35:12",
        "purchaseDate": "11/05/25 17:35:12",
        "items": [],
    })

    receipt = service._normalize_receipt_response(llm_content, {}, raw_text)

    assert receipt["purchaseDate"].startswith("11/05/2023")


def test_llm_receipt_postprocess_rejects_cvs_mutated_totals_and_bad_subtotal():
    service = LLMService()
    raw_text = """
1 Srtga SPRK Sprng Wi 282 2,89F
A179 9484 0417 347 13, NO PETPEIEE (ER TAED IE 28000
07/13/2026
SRTGA SPRK SPRNG Wi 282
1
$2.89
GATT
1
$347.13
HARGE
1
$2.89
"""
    llm_content = json.dumps({
        "company": "",
        "subtotal": "347",
        "tax": "0",
        "total": "2.89",
        "items": [
            {"name": "SRTGA SPRK SPRNG Wi 282", "qty": "1", "amount": "2.89"},
            {"name": "GATT", "qty": "1", "amount": "347.13"},
            {"name": "HARGE", "qty": "1", "amount": "2.89"},
        ],
    })

    receipt = service._normalize_receipt_response(llm_content, {}, raw_text)

    assert receipt["subtotal"] == ""
    assert receipt["total"] == "2.89"
    assert [(item["name"], item["qty"], item["amount"]) for item in receipt["items"]] == [
        ("SRTGA SPRK SPRNG Wi", "1", "2.89")
    ]


def test_llm_finalize_prefers_reconciled_table_items_over_single_subtotal_item():
    service = LLMService()
    structured = {
        "subtotal": "912.20",
        "total": "980.84",
        "items": [
            {"name": "Garlic Naan", "qty": "1", "amount": "912.20"},
        ],
    }
    intelligence_items = [
        {"name": "Custom Item", "qty": "3", "amount": "390.00", "confidence": 1.0},
        {"name": "Custom Item", "qty": "2", "amount": "130.00", "confidence": 1.0},
        {"name": "Custom Item", "qty": "1", "amount": "120.00", "confidence": 1.0},
        {"name": "Custom Item", "qty": "50", "amount": "62.50", "confidence": 1.0},
        {"name": "Butter Naan", "qty": "30", "amount": "89.70", "confidence": 1.0},
        {"name": "Garlic Naan", "qty": "30", "amount": "120.00", "confidence": 1.0},
    ]

    selected = service._prefer_reconciled_intelligence_items(
        structured,
        service._normalize_intelligence_items(intelligence_items),
    )

    assert len(selected) == 6
    assert sum(float(item["amount"]) for item in selected) == 912.2
    assert all(item["amount"] != "912.20" for item in selected)
