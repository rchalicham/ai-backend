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


def test_merchant_confidence_rejects_noisy_centered_header_over_domain():
    semantic = {
        "merchant": "Freshifyme",
        "storeName": "Freshifyme",
        "merchantConfidenceTrace": {
            "rawMerchant": "Freshifyme",
            "confidence": 0.98,
            "source": "normalized",
            "selectedCandidate": {"merchant": "Freshifyme", "confidence": 0.98},
        },
        "reconstructedLines": [
            {"index": 0, "text": "eat Ma 15 Ue SEIN", "confidence": 0.98, "bbox": {"x": 0, "y": 20, "width": 1320, "height": 37}},
            {"index": 1, "text": "www. Freshifyme. com/Sweepstakes", "confidence": 0.82, "bbox": {"x": 575, "y": 492, "width": 268, "height": 14}},
        ],
        "sectionExtraction": {
            "visualHierarchy": {
                "lines": [
                    {"lineIndex": 0, "visualImportance": 0.96, "zone": "merchant_zone"},
                    {"lineIndex": 1, "visualImportance": 0.14, "zone": "item_table_zone"},
                ]
            }
        },
        "confidence": {"merchant": 0.98},
    }

    reconciled = _agent()._reconcile_merchant_confidence(semantic, parser_json={})

    assert reconciled["merchant"] == "Freshifyme"
    merchant_pass = reconciled["receiptAgentPasses"]["merchantConfidence"]
    assert merchant_pass["confidence"] == 0.98
    assert merchant_pass["source"] == "domain_name"
    assert all(candidate["merchant"] != "eat Ma 15 Ue SEIN" for candidate in merchant_pass["candidates"])


def test_merchant_confidence_recovers_cvs_from_return_policy_ocr_fragments():
    semantic = {
        "merchant": "Wore NE AS Ure RAE",
        "storeName": "Wore NE AS Ure RAE",
        "merchantConfidenceTrace": {
            "rawMerchant": "Wore NE AS Ure RAE",
            "confidence": 0.58,
            "source": "raw_ocr_preserved",
            "preservedRawOcr": True,
        },
        "reconstructedLines": [
            {"index": 0, "text": "wore NE AS Ure RAE", "confidence": 0.9, "bbox": {"x": 0, "y": 24, "width": 690, "height": 68}},
            {"index": 1, "text": "4140 ROAD 101 NORTH, PLYMOUTH, MN", "confidence": 0.9, "bbox": {"x": 80, "y": 130, "width": 550, "height": 22}},
            {"index": 2, "text": "PHARMACY: 9478-4612 STORE:", "confidence": 0.92, "bbox": {"x": 362, "y": 189, "width": 513, "height": 48}},
        ],
        "sectionExtraction": {
            "visualHierarchy": {
                "lines": [
                    {"lineIndex": 2, "visualImportance": 0.96, "zone": "merchant_zone"},
                ]
            }
        },
        "confidence": {"merchant": 0.58},
    }

    parser_json = {
        "documentUnderstanding": {
            "ocrFallback": {
                "rawLines": [
                    "with receipt, subject, to",
                    "ol {cus",
                    "VS Return Policu., thru",
                ]
            }
        }
    }

    reconciled = _agent()._reconcile_merchant_confidence(semantic, parser_json=parser_json)

    assert reconciled["merchant"] == "CVS"
    merchant_pass = reconciled["receiptAgentPasses"]["merchantConfidence"]
    assert merchant_pass["source"] == "return_policy_merchant_clue"
    assert any(candidate["source"] == "return_policy_merchant_clue" for candidate in merchant_pass["candidates"])
    assert all(candidate["merchant"] != "- :" for candidate in merchant_pass["candidates"])


def test_merchant_confidence_uses_generic_return_policy_named_merchant():
    semantic = {
        "merchant": "Official Rules",
        "storeName": "Official Rules",
        "merchantConfidenceTrace": {"rawMerchant": "", "confidence": 0.52, "source": "normalized_low_confidence"},
        "reconstructedLines": [
            {"index": 0, "text": "THANK YOU", "confidence": 0.9, "bbox": {"x": 20, "y": 20, "width": 160, "height": 16}},
            {"index": 1, "text": "Returns accepted under Bright Market return policy", "confidence": 0.94, "bbox": {"x": 20, "y": 250, "width": 440, "height": 16}},
        ],
        "confidence": {"merchant": 0.52},
    }

    reconciled = _agent()._reconcile_merchant_confidence(semantic, parser_json={})

    assert reconciled["merchant"] == "Bright Market"
    merchant_pass = reconciled["receiptAgentPasses"]["merchantConfidence"]
    assert merchant_pass["source"] == "return_policy_merchant_clue"


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


def test_attempt_scoring_penalizes_tiny_subset_when_receipt_item_count_exists():
    agent = _agent()
    tiny_subset = {
        "items": [{"name": "O/N", "amount": "14.99"}],
        "facts": {"total": "14.99", "tax": "1.44"},
        "confidence": {"overall": 0.91},
        "validation": {"valid": True, "warnings": []},
    }
    complete_but_noisy = {
        "items": [{"name": f"ITEM {index}", "amount": "1.00"} for index in range(14)],
        "facts": {"subtotal": "244.36", "tax": "1.44", "total": "245.80"},
        "confidence": {"overall": 0.70},
        "validation": {"valid": False, "warnings": ["item_sum_does_not_match_receipt_total"]},
    }
    donut = {"rowConsolidation": {"reconciliation": {"itemCountTarget": 14}}}

    assert agent._score_attempt(complete_but_noisy, None, donut) > agent._score_attempt(tiny_subset, None, donut)
