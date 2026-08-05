from dataclasses import FrozenInstanceError
from pathlib import Path
from copy import deepcopy

import pytest

from services.document_review import (
    DocumentFamilyReviewEngine, DocumentReviewConfigurationLoader,
    DocumentReviewSerializer,
)
from services.receipt_processing import ProcessingExperienceConfigurationLoader, ReceiptProcessingExperienceEngine
from services.receipt_quality import FileEnterpriseConfigurationProvider


CONFIG = Path(__file__).parents[1] / "config" / "receipt_capture_quality.json"


def review_engine():
    provider = FileEnterpriseConfigurationProvider(CONFIG)
    return DocumentFamilyReviewEngine(DocumentReviewConfigurationLoader(provider))


def context(family, fields, *, items=None, quality_passed=True):
    zones = {
        "payment_slip": ("merchant_zone", "financial_zone", "payment_zone"),
        "credit_card_slip": ("merchant_zone", "financial_zone", "payment_zone"),
        "retail_receipt": ("merchant_zone", "item_zone", "financial_zone"),
        "restaurant_receipt": ("merchant_zone", "item_zone", "financial_zone"),
        "invoice": ("merchant_zone", "item_zone", "financial_zone", "reference_zone"),
    }.get(family, ("merchant_zone", "financial_zone"))
    values = dict(fields)
    if items is not None:
        values["items"] = items
    return {
        "semantic": {"items": [{"name": "legacy parser value"}]},
        "documentFamilyContext": {"activation": {"family": family, "confidence": .88}, "semantic_zones": [{"zone_type": zone} for zone in zones]},
        "receiptGrammar": {"confidence": .86},
        "receiptConstraintResult": {"confidence": .84},
        "enterpriseReasoning": {"confidence": .82},
        "businessProjection": {"overall_confidence": {"display": .86}, "fields": [{"key": key, "displayed_value": value} for key, value in values.items()]},
        "receiptQuality": {"passed": quality_passed, "overallScore": .84, "factors": []},
    }


def test_payment_slip_zero_items_is_complete_and_filters_legacy_item_heuristic():
    payload = context("payment_slip", {
        "merchant": "Luther Hopkins Honda", "total": 310.76, "payment_method": "Credit Card",
        "card_brand": "American Express", "card_last_four": "8007", "approval_code": "841286",
    })
    result = review_engine().review(payload)
    assert result.decision.key == "completed"
    assert result.decision.requires_human_review is False
    assert result.semantic_completeness.item_expectation_satisfied is True


def test_retail_receipt_without_projected_items_requires_review():
    result = review_engine().review(context("retail_receipt", {"merchant": "Store", "total": 12.34}))
    assert result.decision.requires_human_review is True
    assert "items" in result.semantic_completeness.missing_required_fields


def test_reliable_geometry_fallback_resolves_advisory_warning():
    payload = context("payment_slip", {"merchant":"Store","total":10,"payment_method":"Card","card_brand":"Visa","card_last_four":"1234","approval_code":"A1"})
    payload["receiptQuality"]["passed"] = False
    payload["receiptQuality"]["factors"] = [{"name":"edge_clipping","passed":False,"score":.1}]
    payload["receiptQuality"]["geometryValidation"] = {"reliability":"fallback_reliable","selectedSource":"page_boundary","overallConfidence":.8}
    result = review_engine().review(payload)
    assert result.resolved_quality.passed is True
    assert result.resolved_quality.unresolved_warnings == ()
    assert result.resolved_quality.resolved_warnings[0]["code"] == "edge_clipping"


def test_critical_quality_failure_needs_user_action_not_human_review():
    payload = context("unknown", {}, quality_passed=False)
    payload["receiptQuality"]["factors"] = [{"name":"blur","passed":False,"score":.1}]
    result = review_engine().review(payload)
    assert result.decision.key == "needs_user_action"
    assert result.decision.requires_human_review is False


@pytest.mark.parametrize("family", ["fuel_receipt","pharmacy_receipt","refund_receipt","return_receipt","statement","donation_receipt","unknown"])
def test_configured_family_policies_are_resolvable(family):
    result = review_engine().review(context(family, {"merchant":"Business","total":10,"date":"2026-08-05"}))
    assert result.policy.family == family


def test_unknown_family_requires_semantic_review_by_configured_policy():
    result = review_engine().review(context("unknown", {"merchant":"Business","total":10,"date":"2026-08-05"}))
    assert result.decision.key == "insufficient_evidence"
    assert result.decision.requires_human_review is True


def test_models_are_immutable_and_inputs_are_preserved():
    payload = context("retail_receipt", {"merchant":"Store","total":10}, items=[{"name":"Item"}])
    before = deepcopy(payload)
    result = review_engine().review(payload)
    with pytest.raises(FrozenInstanceError):
        result.decision.key = "changed"
    assert payload == before
    assert DocumentReviewSerializer().to_dict(result)["diagnostics"]["parserModified"] is False


def test_processing_experience_consumes_resolved_review_decision():
    payload = context("payment_slip", {"merchant":"Store","total":10,"payment_method":"Card","card_brand":"Visa","card_last_four":"1234","approval_code":"A1"})
    review = DocumentReviewSerializer().to_dict(review_engine().review(payload))
    payload["documentReview"] = review
    payload["receiptAgent"] = {"status":"needs_human_review","humanReview":{"required":True}}
    processing = ReceiptProcessingExperienceEngine(ProcessingExperienceConfigurationLoader(FileEnterpriseConfigurationProvider(CONFIG))).build(payload)
    assert processing.state.key == "completed"
    assert processing.summary.human_review is False


def test_processing_timeline_uses_resolved_quality_not_raw_advisory_failure():
    payload = context("payment_slip", {"merchant":"Store","total":10,"payment_method":"Card","card_brand":"Visa","card_last_four":"1234","approval_code":"A1"})
    payload["receiptQuality"].update({"passed":False,"factors":[{"name":"edge_clipping","passed":False,"score":.1}],"geometryValidation":{"reliability":"fallback_reliable","selectedSource":"page_boundary","overallConfidence":.8}})
    payload["documentReview"] = DocumentReviewSerializer().to_dict(review_engine().review(payload))
    processing = ReceiptProcessingExperienceEngine(ProcessingExperienceConfigurationLoader(FileEnterpriseConfigurationProvider(CONFIG))).build(payload)
    quality_stage = next(stage for stage in processing.timeline.stages if stage.key == "quality_validation")
    assert processing.state.key == "completed"
    assert quality_stage.state == "success"
