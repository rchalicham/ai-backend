import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.receipt_entity_extraction import ReceiptEntityExtractionEngine
from services.receipt_intelligence import ReceiptIntelligencePipeline
from services.receipt_row_consolidation import ReceiptRowConsolidationPipeline


def test_entity_engine_extracts_cvs_address_and_multiline_payment():
    raw_text = """
CVS/pharmacy
4140 ROAD 101 NORTH
PLYMOUTH, MN
952-555-1212
SRTGA SPRK SPRNG WI 282
1
$2.89
VISA CREDIT
************3442
AUTH CODE 014417
TOTAL 2.89
"""

    result = ReceiptEntityExtractionEngine().extract(raw_text=raw_text)
    fields = result["fields"]

    assert fields["merchant"] == "CVS Pharmacy"
    assert fields["address"] == "4140 ROAD 101 NORTH, PLYMOUTH, MN"
    assert fields["phone"] == "952-555-1212"
    assert fields["paymentMethod"] == "credit"
    assert fields["cardType"] == "VISA"
    assert fields["lastFour"] == "3442"
    assert fields["approvalCode"] == "014417"
    assert result["confidence"]["address"] >= 0.8
    assert result["confidence"]["lastFour"] >= 0.9


def test_semantic_json_surfaces_receipt_entities():
    raw_text = """
CVS
4140 ROAD 101 NORTH
PLYMOUTH, MN
SRTGA SPRK SPRNG WI 282
1
$2.89
VISA CREDIT
************3442
AUTH 014417
"""

    semantic = ReceiptIntelligencePipeline().to_structured_json(raw_text=raw_text)

    assert semantic["merchant"] == "CVS Pharmacy"
    assert semantic["address"] == "4140 ROAD 101 NORTH, PLYMOUTH, MN"
    assert semantic["cardUsed"] == "VISA"
    assert semantic["cardType"] == "VISA"
    assert semantic["cardLast4"] == "3442"
    assert semantic["lastFour"] == "3442"
    assert semantic["approvalCode"] == "014417"
    assert semantic["receiptEntities"]["schemaVersion"] == "receipt-entities-v1"


def test_row_consolidation_surfaces_receipt_entities():
    raw_text = """
CVS
4140 ROAD 101 NORTH
PLYMOUTH, MN
SRTGA SPRK SPRNG WI 282 2.89
VISA CREDIT
************3442
AUTH 014417
TOTAL 2.89
"""

    normalized = ReceiptRowConsolidationPipeline().normalize(
        {"available": True, "merchant": "", "items": [], "raw": {}, "total": "2.89"},
        raw_text=raw_text,
    )

    assert normalized["merchant"] == "CVS Pharmacy"
    assert normalized["address"] == "4140 ROAD 101 NORTH, PLYMOUTH, MN"
    assert normalized["cardUsed"] == "VISA"
    assert normalized["cardLast4"] == "3442"
    assert normalized["approvalCode"] == "014417"
    assert normalized["receiptEntities"]["schemaVersion"] == "receipt-entities-v1"


def test_address_heuristics_support_zip_units_and_city_state_without_comma():
    raw_text = """
CVS
Store #1234
4140 Road 101 N Suite 8
Plymouth MN 55447
VISA CREDIT
************3442
"""

    fields = ReceiptEntityExtractionEngine().extract(raw_text=raw_text)["fields"]

    assert fields["address"] == "4140 ROAD 101 N SUITE 8, PLYMOUTH, MN 55447"
    assert fields["cardLast4"] == "3442"


def test_address_heuristics_do_not_treat_transaction_numbers_as_address():
    raw_text = """
CVS
REG#04 TRN#5652 CSHR#2827889 STR#68
AUTH CODE 014417
VISA CREDIT
************3442
"""

    fields = ReceiptEntityExtractionEngine().extract(raw_text=raw_text)["fields"]

    assert fields["address"] == ""
