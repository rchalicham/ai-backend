import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.receipt_agent_orchestrator import ReceiptAgentOrchestrator
from services.receipt_agent_orchestrator import ReceiptAgentAttempt
from services.receipt_intelligence import ReceiptIntelligencePipeline


class _Stub:
    pass


def _agent() -> ReceiptAgentOrchestrator:
    llm = _Stub()
    llm.receipt_intelligence = ReceiptIntelligencePipeline()
    return ReceiptAgentOrchestrator(
        donut_receipt_service=_Stub(),
        receipt_image_isolation_service=_Stub(),
        receipt_ocr_service=_Stub(),
        llm_service=llm,
    )


def test_pass3_uses_receipt_item_count_and_rejects_payment_total_rows():
    semantic = {
        "items": [
            {"name": "BEEF LIVER", "qty": "1", "amount": "4.69", "confidence": 0.91},
            {"name": "PROT RO RED BEETS", "qty": "1", "amount": "2.99", "confidence": 0.9},
            {"name": "MLR BNLS BRSI", "qty": "1", "amount": "13.90", "confidence": 0.94},
            {"name": "BALANCE DUE", "qty": "1", "amount": "21.58", "confidence": 0.99},
            {"name": "VISA", "qty": "1", "amount": "21.58", "confidence": 0.99},
            {"name": "jot yspgn", "qty": "1", "amount": "2.58", "confidence": 0.62},
        ],
        "facts": {"total": "21.58", "tax": "0", "tip": "0"},
        "reconstructedLines": [{"text": "Total number of items sold 3"}],
        "validation": {"valid": False, "warnings": ["too_many_items"]},
    }

    reconciled = _agent()._reconcile_semantic_item_candidates(semantic)

    assert [(item["name"], item["amount"]) for item in reconciled["items"]] == [
        ("BEEF LIVER", "4.69"),
        ("PROT RO RED BEETS", "2.99"),
        ("MLR BNLS BRSI", "13.90"),
    ]
    pass3 = reconciled["receiptAgentPasses"]["pass3CandidateSelection"]
    assert pass3["applied"] is True
    assert pass3["expectedItemCount"] == 3
    assert pass3["selectedSum"] == "21.58"
    assert any(row["name"] == "BALANCE DUE" and "totals_payment_or_footer_row" in row["reasons"] for row in pass3["rejectedCandidates"])
    assert any(row["name"] == "VISA" and "totals_payment_or_footer_row" in row["reasons"] for row in pass3["rejectedCandidates"])


def test_pass3_selects_smallest_valid_set_when_item_count_is_missing():
    semantic = {
        "items": [
            {"name": "APPLES", "amount": "3.25", "confidence": 0.8},
            {"name": "BANANAS", "amount": "1.00", "confidence": 0.88},
            {"name": "CATERING ORDER", "amount": "4.25", "confidence": 0.82},
            {"name": "USD", "amount": "4.25", "confidence": 0.99},
        ],
        "facts": {"total": "4.25", "tax": "0", "tip": "0"},
    }

    reconciled = _agent()._reconcile_semantic_item_candidates(semantic)

    assert [(item["name"], item["amount"]) for item in reconciled["items"]] == [
        ("CATERING ORDER", "4.25"),
    ]
    pass3 = reconciled["receiptAgentPasses"]["pass3CandidateSelection"]
    assert pass3["selectedCount"] == 1
    assert pass3["selectedDelta"] == "0.00"
    assert any(row["name"] == "USD" and "totals_payment_or_footer_row" in row["reasons"] for row in pass3["rejectedCandidates"])


def test_pass3_prefers_subtotal_target_when_tax_is_present():
    semantic = {
        "items": [
            {"name": "MULCH BAG", "amount": "7.00", "confidence": 0.92},
            {"name": "WASHERS", "amount": "3.75", "confidence": 0.9},
            {"name": "TOTAL", "amount": "11.61", "confidence": 0.99},
        ],
        "facts": {"subtotal": "10.75", "tax": "0.86", "total": "11.61"},
    }

    reconciled = _agent()._reconcile_semantic_item_candidates(semantic)

    assert [(item["name"], item["amount"]) for item in reconciled["items"]] == [
        ("MULCH BAG", "7.00"),
        ("WASHERS", "3.75"),
    ]
    pass3 = reconciled["receiptAgentPasses"]["pass3CandidateSelection"]
    assert pass3["targetField"] == "subtotal"
    assert pass3["selectedSum"] == "10.75"


def test_merchant_confidence_prioritizes_domain_names_over_hallucinated_current():
    semantic = {
        "merchant": "Official Rules",
        "storeName": "Official Rules",
        "merchantConfidenceTrace": {"rawMerchant": "", "confidence": 0.52, "source": "normalized_low_confidence"},
        "reconstructedLines": [
            {"index": 0, "text": "No purchase necessary", "confidence": 0.98, "bbox": {"x": 20, "y": 10, "width": 220, "height": 12}},
            {"index": 1, "text": "Visit freshhyme.com for details", "confidence": 0.97, "bbox": {"x": 30, "y": 28, "width": 260, "height": 12}},
        ],
        "confidence": {"merchant": 0.52},
    }

    reconciled = _agent()._reconcile_merchant_confidence(semantic, parser_json={})

    assert reconciled["merchant"] == "Freshhyme"
    merchant_pass = reconciled["receiptAgentPasses"]["merchantConfidence"]
    assert merchant_pass["confidence"] == 0.98
    assert merchant_pass["source"] == "domain_name"
    assert merchant_pass["overrideApplied"] is True


def test_merchant_confidence_uses_centered_visual_header_when_high_confidence():
    semantic = {
        "merchant": "",
        "storeName": "",
        "merchantConfidenceTrace": {"rawMerchant": "", "confidence": 0.0},
        "reconstructedLines": [
            {"index": 0, "text": "BRIGHT MARKET", "confidence": 0.98, "bbox": {"x": 70, "y": 20, "width": 240, "height": 28}},
            {"index": 1, "text": "123 LAKE STREET", "confidence": 0.96, "bbox": {"x": 35, "y": 58, "width": 180, "height": 14}},
            {"index": 2, "text": "APPLES 3.25", "confidence": 0.94, "bbox": {"x": 35, "y": 130, "width": 335, "height": 14}},
        ],
        "sectionExtraction": {
            "visualHierarchy": {
                "lines": [
                    {"lineIndex": 0, "visualImportance": 0.96, "zone": "merchant_zone"},
                    {"lineIndex": 1, "visualImportance": 0.42, "zone": "header_zone"},
                ]
            }
        },
        "confidence": {"merchant": 0.0},
    }

    reconciled = _agent()._reconcile_merchant_confidence(semantic, parser_json={})

    assert reconciled["merchant"] == "Bright Market"
    merchant_pass = reconciled["receiptAgentPasses"]["merchantConfidence"]
    assert merchant_pass["confidence"] > 0.9
    assert merchant_pass["source"] == "visual_hierarchy_centered_header"
    assert "centered_header_text" in merchant_pass["candidates"][0]["reasons"]


def test_merchant_confidence_uses_visual_spelling_when_domain_ocr_is_near_match():
    semantic = {
        "merchant": "Michacls",
        "storeName": "Michacls",
        "merchantConfidenceTrace": {"rawMerchant": "Michacls", "confidence": 0.68},
        "reconstructedLines": [
            {"index": 0, "text": "ee MICHAELS STORE #6717 (763) 919-7739", "confidence": 0.96, "bbox": {"x": 0, "y": 20, "width": 360, "height": 24}},
            {"index": 1, "text": "Shop michacls.com today", "confidence": 0.92, "bbox": {"x": 30, "y": 240, "width": 260, "height": 12}},
        ],
        "sectionExtraction": {
            "visualHierarchy": {
                "lines": [
                    {"lineIndex": 0, "visualImportance": 0.94, "zone": "merchant_zone"},
                ]
            }
        },
        "confidence": {"merchant": 0.68},
    }

    reconciled = _agent()._reconcile_merchant_confidence(semantic, parser_json={})

    assert reconciled["merchant"] == "Michaels"
    merchant_pass = reconciled["receiptAgentPasses"]["merchantConfidence"]
    assert merchant_pass["confidence"] > 0.9
    assert merchant_pass["source"] == "domain_visual_fuzzy_consensus"


def test_merchant_confidence_penalizes_disclaimer_and_preserves_raw_ocr_when_uncertain():
    semantic = {
        "merchant": "Official Rules",
        "storeName": "Official Rules",
        "merchantConfidenceTrace": {
            "rawMerchant": "Corner Market",
            "confidence": 0.74,
            "source": "normalized",
            "selectedCandidate": {"merchant": "Official Rules", "confidence": 0.86},
        },
        "reconstructedLines": [
            {"index": 0, "text": "NO PURCHASE NECESSARY OFFICIAL RULES", "confidence": 0.99, "bbox": {"x": 30, "y": 10, "width": 300, "height": 12}},
        {"index": 1, "text": "CORNER MARKET", "confidence": 0.76, "bbox": {"x": 10, "y": 42, "width": 130, "height": 14}},
            {"index": 2, "text": "APPLES 3.25", "confidence": 0.94, "bbox": {"x": 35, "y": 130, "width": 300, "height": 14}},
        ],
        "sectionExtraction": {
            "visualHierarchy": {
                "lines": [
                    {"lineIndex": 0, "visualImportance": 0.98, "zone": "merchant_zone"},
                {"lineIndex": 1, "visualImportance": 0.4, "zone": "header_zone"},
                ]
            }
        },
        "confidence": {"merchant": 0.74},
    }

    reconciled = _agent()._reconcile_merchant_confidence(semantic, parser_json={})

    assert reconciled["merchant"] == "Corner Market"
    merchant_pass = reconciled["receiptAgentPasses"]["merchantConfidence"]
    assert merchant_pass["source"] == "raw_ocr_preserved_uncertain_agent_merchant"
    assert merchant_pass["preservedRawOcr"] is True
    disclaimer_candidates = [
        candidate for candidate in merchant_pass["candidates"]
        if candidate["merchant"] == "No Purchase Necessary Official Rules"
    ]
    assert not disclaimer_candidates or disclaimer_candidates[0]["confidence"] <= 0.9


def test_human_review_task_prioritizes_extraction_risk_with_actions():
    attempt = ReceiptAgentAttempt(
        index=0,
        strategy="test",
        source="test",
        score=0.62,
        semantic={
            "merchant": "Corner Market",
            "items": [{"name": "APPLES", "amount": "3.25"}],
            "validation": {"warnings": ["item_sum_does_not_match_subtotal"]},
            "confidence": {"merchant": 0.71},
            "receiptAgentPasses": {
                "merchantConfidence": {"confidence": 0.71},
                "pass3CandidateSelection": {"expectedItemCount": 3, "selectedCount": 1},
            },
        },
    )

    review = _agent()._human_review_task(attempt)

    assert review["required"] is True
    assert review["priority"] == "urgent"
    assert review["riskScore"] >= 75
    assert [reason["reason"] for reason in review["reasons"][:3]] == [
        "item_sum_does_not_match_subtotal",
        "low_confidence_merchant",
        "item_count_mismatch",
    ]
    assert any("Verify subtotal" in action for action in review["actionableExplanations"])


def test_human_review_task_adds_image_quality_risk():
    attempt = ReceiptAgentAttempt(
        index=0,
        strategy="test",
        source="test",
        score=0.81,
        semantic={
            "merchant": "Corner Market",
            "items": [{"name": "APPLES", "amount": "3.25"}],
            "validation": {"warnings": []},
            "confidence": {"merchant": 0.93},
            "layoutQuality": {
                "indicators": {
                    "likelyBlurry": True,
                    "weakAlignment": True,
                }
            },
        },
    )

    review = _agent()._human_review_task(attempt)

    assert review["required"] is True
    assert any(reason["reason"] == "image_quality_risk" for reason in review["reasons"])
    assert review["riskScore"] >= 24
