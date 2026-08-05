from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np
import pytest

from services.geometry_validation import (
    GeometryQualityMetrics, GeometryValidationEngine, GeometryValidationPolicyLoader, PerspectiveValidator,
)
from services.receipt_geometry import ReceiptGeometryEngine
from services.receipt_geometry.models import Point
from services.receipt_quality import FileEnterpriseConfigurationProvider, QualityPolicyLoader, ReceiptCaptureQualityEngine


CONFIG = Path(__file__).parents[1] / "config" / "receipt_capture_quality.json"


def provider(): return FileEnterpriseConfigurationProvider(CONFIG)
def validator(metrics=None): return GeometryValidationEngine(GeometryValidationPolicyLoader(provider()), metrics)
def quality(): return ReceiptCaptureQualityEngine(QualityPolicyLoader(provider()), ReceiptGeometryEngine())


def readable_receipt():
    image=np.full((1320,687,3),248,dtype=np.uint8)
    for index,text in enumerate(("LUTHER HOPKINS HONDA","250 5TH AVE SOUTH","12/31/2024","AMEX SALE","SALE AMOUNT       $310.76")):
        cv2.putText(image,text,(45,180+index*180),cv2.FONT_HERSHEY_SIMPLEX,1.05,(25,25,25),2,cv2.LINE_AA)
    for y in range(1010, 1210, 35):
        cv2.line(image,(55,y),(630,y),(45,45,45),3)
    return image


def encode(image,extension):
    ok,value=cv2.imencode(extension,image); assert ok; return value.tobytes()


def test_out_of_bounds_diagonal_contour_is_rejected_and_page_fallback_is_reliable():
    image=readable_receipt(); raw=ReceiptGeometryEngine().analyze_image(cv2,np,image)
    impossible=replace(raw,receipt_boundary=[Point(225,291),Point(508,140),Point(844,766),Point(561,918)],geometric_confidence=.5016)
    result=validator().validate(cv2,np,image,impossible)
    assert result.rejected_contours
    assert "coordinate_outside_image" in result.rejected_contours[0].reasons
    assert result.fallback_source == "page_boundary"
    assert result.confidence.reliable is True
    assert max(point.x for point in result.effective_geometry.receipt_boundary) < image.shape[1]


def test_exact_production_false_reject_uses_validated_page_geometry_and_passes_quality():
    source=Path("/tmp/receipt-627c.webp")
    if not source.exists(): pytest.skip("production regression fixture not available")
    result=quality().evaluate(source.read_bytes())
    assert result.passed is True
    assert result.geometry_validation["fallbackSource"] == "page_boundary"
    assert result.geometry_validation["rejectedContours"][0]["reasons"] == ["coordinate_outside_image"]
    assert result.geometry_validation["observations"]["skew"]["measurement"] == pytest.approx(-1.035,.01)


@pytest.mark.parametrize("source_format,extension",[
    ("pdf_rendered_processing_asset",".png"),("jpeg",".jpg"),("png",".png"),
    ("heic_converted_processing_asset",".webp"),("tiff_converted_processing_asset",".png")])
def test_supported_document_processing_assets_use_same_validated_geometry(source_format,extension):
    result=quality().evaluate(encode(readable_receipt(),extension))
    assert source_format
    assert result.geometry_validation["confidence"]["reliable"] is True
    assert result.passed is True


def test_unreadable_receipt_still_stops_on_critical_factors():
    image=np.full((180,240,3),245,dtype=np.uint8)
    result=quality().evaluate(encode(image,".jpg"))
    failed={item.name for item in result.factors if not item.passed}
    critical=set(result.diagnostics["criticalFactors"])
    assert result.passed is False
    assert failed & critical


def test_advisory_geometry_factor_cannot_be_the_only_ocr_blocker():
    source=Path("/tmp/receipt-627c.webp")
    if not source.exists(): pytest.skip("production regression fixture not available")
    result=quality().evaluate(source.read_bytes())
    assert "edge_clipping" in result.diagnostics["advisoryFailures"]
    assert result.passed is True


def test_geometry_metrics_track_fallback_and_ocr_recovery():
    metrics=GeometryQualityMetrics(); image=readable_receipt(); raw=ReceiptGeometryEngine().analyze_image(cv2,np,image)
    impossible=replace(raw,receipt_boundary=[Point(10,10),Point(800,10),Point(800,900),Point(10,900)])
    validator(metrics).validate(cv2,np,image,impossible)
    snapshot=metrics.snapshot()
    assert snapshot["fallbackUsage"] == 1
    assert snapshot["ocrRecoveryRate"] == 1


def test_dark_scan_with_impossible_contour_uses_image_boundary_after_page_fallback_fails():
    image=np.full((900,600,3),45,dtype=np.uint8); cv2.putText(image,"THERMAL RECEIPT",(60,250),cv2.FONT_HERSHEY_SIMPLEX,1,(230,230,230),2)
    raw=ReceiptGeometryEngine().analyze_image(cv2,np,image)
    impossible=replace(raw,receipt_boundary=[Point(-90,10),Point(800,10),Point(800,850),Point(-90,850)])
    result=validator().validate(cv2,np,image,impossible)
    assert result.fallback_source == "image_boundary"
    assert result.observations["boundary"].reliable is True


def test_rotated_large_processing_asset_is_normalized_using_validated_geometry():
    rotated=cv2.rotate(readable_receipt(),cv2.ROTATE_90_CLOCKWISE)
    result=quality().evaluate(encode(rotated,".png"))
    assert result.orientation.degrees in {90,270}
    assert result.orientation.normalized is True
    assert result.geometry_validation["confidence"]["reliable"] is True


def test_unstable_perspective_matrix_is_rejected_even_with_valid_corners():
    image=readable_receipt(); geometry=ReceiptGeometryEngine().analyze_image(cv2,np,image)
    boundary=[Point(5,5),Point(681,5),Point(681,1314),Point(5,1314)]
    unstable=replace(geometry,receipt_boundary=boundary,perspective_matrix=[[1,0,0],[0,1,0],[0,0,0.000001]])
    policy=GeometryValidationPolicyLoader(provider()).load()
    observation=PerspectiveValidator().validate(unstable,True,policy)
    assert observation.reliable is False
    assert observation.reason == "unstable_perspective"
    assert observation.diagnostics["transformationConditionNumber"] > observation.diagnostics["maximumConditionNumber"]
