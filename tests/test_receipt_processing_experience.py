from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from services.receipt_quality import FileEnterpriseConfigurationProvider
from services.receipt_processing import ProcessingExperienceConfigurationLoader, ReceiptProcessingExperienceEngine, ReceiptProcessingSerializer


CONFIG = Path(__file__).parents[1] / "config" / "receipt_capture_quality.json"


def engine():
    return ReceiptProcessingExperienceEngine(ProcessingExperienceConfigurationLoader(FileEnterpriseConfigurationProvider(CONFIG)))


def quality_failure():
    return {
        "receiptQuality": {"status":"quality_failure", "passed":False, "overallScore":.38, "factors":[{"name":"text_resolution","passed":False}], "recommendations":[{"code":"capture_text_resolution"}]},
        "receiptAgent": {"status":"quality_failure", "confidence":.8, "humanReview":{"required":True}},
    }


def test_quality_failure_becomes_business_safe_user_action_with_skipped_pipeline():
    result = engine().build(quality_failure())
    assert result.state.key == "needs_user_action"
    assert result.state.label == "Needs User Action"
    assert result.summary.current_stage == "quality_validation"
    assert result.explanation.title == "Receipt text too small"
    assert result.summary.recoverability.kind == "rescan"
    assert result.summary.recoverability.score == .95
    assert result.summary.recommendations[0].label == "Move closer"
    assert next(stage for stage in result.timeline.stages if stage.key == "quality_validation").state == "failed"
    assert next(stage for stage in result.timeline.stages if stage.key == "ocr").state == "skipped"


def test_completed_projection_uses_configured_confidence_threshold():
    result = engine().build({
        "receiptAgent":{"status":"completed","confidence":.9,"humanReview":{"required":False}},
        "documentFamilyContext":{"activation":{"family":"retail_receipt","confidence":.91}},
        "businessProjection":{"overall_confidence":{"display":.85}},
    })
    assert result.state.key == "completed"
    assert result.summary.projection_available is True
    assert result.summary.recoverability.kind == "already_complete"


def test_human_review_is_distinct_from_failure_and_explains_business_action():
    result = engine().build({"receiptAgent":{"status":"needs_human_review","confidence":.6,"humanReview":{"required":True}}})
    assert result.state.key == "human_review_required"
    assert result.summary.recommendations[0].code == "send_human_review"
    assert "review" in result.explanation.title.lower()


def test_models_are_immutable_and_serialization_preserves_parser_isolation():
    result = engine().build(quality_failure())
    with pytest.raises(FrozenInstanceError): result.state.label = "Changed"
    with pytest.raises(TypeError): result.actions["retry"]["label"] = "Changed"
    payload = ReceiptProcessingSerializer().to_dict(result)
    assert payload["diagnostics"]["parser_modified"] is False
    assert payload["diagnostics"]["enterprise_intelligence_modified"] is False
    assert payload["diagnostics"]["projection_modified"] is False
    assert payload["timeline"]["stages"][0]["label"] == "Upload"


def test_missing_enterprise_configuration_fails_explicitly():
    class Empty:
        def get(self, _): return None
    with pytest.raises(ValueError, match="enterprise_configuration_missing"):
        ProcessingExperienceConfigurationLoader(Empty()).load()


@pytest.mark.parametrize("source,expected", [("uploaded","uploaded"),("queued","queued"),("running","running"),("initial","processing"),("cancelled","cancelled")])
def test_configured_source_statuses_translate_to_business_states(source, expected):
    assert engine().build({"receiptSourceStatus": source}).state.key == expected
