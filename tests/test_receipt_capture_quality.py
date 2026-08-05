from pathlib import Path
import asyncio

import cv2
import numpy as np
import pytest

from services.receipt_agent_orchestrator import ReceiptAgentOrchestrator
from services.receipt_geometry import ReceiptGeometryEngine
from services.receipt_quality import (
    FileEnterpriseConfigurationProvider,
    MappingConfigurationProvider,
    QualityPolicyLoader,
    ReceiptCaptureQualityEngine,
)


CONFIG = Path(__file__).parents[1] / "config" / "receipt_capture_quality.json"


def encoded(image):
    ok, value = cv2.imencode(".jpg", image)
    assert ok
    return value.tobytes()


def quality_engine():
    return ReceiptCaptureQualityEngine(
        QualityPolicyLoader(FileEnterpriseConfigurationProvider(CONFIG)),
        ReceiptGeometryEngine(),
    )


def test_policy_requires_enterprise_configuration_and_has_no_code_defaults():
    with pytest.raises(ValueError, match="enterprise_configuration_missing"):
        QualityPolicyLoader(MappingConfigurationProvider({})).load()


def test_rotated_low_resolution_capture_is_normalized_then_rejected_before_ocr():
    image = np.zeros((240, 320, 3), dtype=np.uint8)
    image[:] = (20, 20, 20)
    cv2.rectangle(image, (20, 75), (300, 165), (245, 245, 245), -1)
    for x in range(35, 285, 15):
        cv2.line(image, (x, 88), (x, 150), (60, 60, 60), 1)
    result = quality_engine().evaluate(encoded(image))
    assert result.status == "quality_failure"
    assert result.orientation.normalized is True
    assert result.orientation.degrees in {90, 270}
    assert result.passed is False
    assert any(not factor.passed for factor in result.factors)
    assert result.diagnostics["ocrInvoked"] is False


def test_orchestrator_quality_failure_never_calls_ocr_or_document_understanding():
    calls = {"donut": 0, "ocr": 0, "llm": 0}

    class Donut:
        async def analyze_image_bytes(self, _): calls["donut"] += 1
    class Ocr:
        def extract(self, _): calls["ocr"] += 1
    class Llm:
        async def structure_receipt(self, **_): calls["llm"] += 1
    class Isolation:
        def isolate(self, _): raise AssertionError("image variants must not be created")

    orchestrator = ReceiptAgentOrchestrator(
        donut_receipt_service=Donut(), receipt_image_isolation_service=Isolation(),
        receipt_ocr_service=Ocr(), llm_service=Llm(), capture_quality_engine=quality_engine(),
    )
    image = np.full((180, 240, 3), 245, dtype=np.uint8)
    result = asyncio.run(orchestrator.process(image_bytes=encoded(image), parser_json={"company": "Preserved"}))
    assert result["receiptAgent"]["status"] == "quality_failure"
    assert result["receiptAgent"]["attemptCount"] == 0
    assert result["receiptAgent"]["diagnostics"]["ocrInvoked"] is False
    assert result["semantic"]["company"] == "Preserved"
    assert calls == {"donut": 0, "ocr": 0, "llm": 0}


def test_quality_result_exposes_configured_thresholds_and_recapture_guidance():
    image = np.full((200, 300, 3), 128, dtype=np.uint8)
    result = quality_engine().evaluate(encoded(image))
    payload = result.to_dict()
    assert payload["policy"]["id"] == "enterprise-receipt-capture-default"
    assert all(factor["threshold"] is not None for factor in payload["factors"])
    assert payload["recommendations"]
    assert payload["status"] == "quality_failure"
