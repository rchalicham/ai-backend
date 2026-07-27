import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.receipt_geometry import (
    Dimensions,
    GeometryUtilities,
    Point,
    ReceiptContourDetector,
    ReceiptCoordinateSystem,
    ReceiptDeskewEngine,
    ReceiptGeometryEngine,
    ReceiptPerspectiveCorrector,
    ReceiptRegionLocator,
    Region,
)


@pytest.fixture()
def cv():
    return pytest.importorskip("cv2"), pytest.importorskip("numpy")


@pytest.fixture()
def receipt_image(cv):
    cv2, np = cv
    image = np.full((900, 700, 3), 18, dtype=np.uint8)
    boundary = np.array([[175, 65], [525, 95], [570, 830], [120, 800]], dtype=np.int32)
    cv2.fillConvexPoly(image, boundary, (242, 242, 235))
    for y, left, right in [(150, 200, 480), (250, 170, 510), (350, 170, 510), (650, 180, 500), (750, 210, 470)]:
        cv2.line(image, (left, y), (right, y), (25, 25, 25), 5)
    return image


def test_geometry_engine_returns_complete_structured_geometry(cv, receipt_image):
    cv2, _ = cv
    success, encoded = cv2.imencode(".jpg", receipt_image)
    assert success

    geometry = ReceiptGeometryEngine().analyze(encoded.tobytes())
    payload = geometry.to_dict()

    assert len(payload["receipt_boundary"]) == 4
    assert payload["source_dimensions"] == {"width": 700, "height": 900}
    assert payload["page_dimensions"]["height"] > payload["page_dimensions"]["width"]
    assert len(payload["perspective_matrix"]) == 3
    assert all(len(row) == 3 for row in payload["perspective_matrix"])
    assert isinstance(payload["rotation"], float)
    assert isinstance(payload["skew"], float)
    assert payload["estimated_reading_zones"]
    assert payload["whitespace_map"]["rowRuns"]
    assert 0.0 <= payload["geometric_confidence"] <= 1.0
    assert payload["diagnostics"]["contourFound"] is True


def test_contour_detector_reuses_document_candidate_scoring(cv, receipt_image):
    cv2, np = cv
    candidates = ReceiptContourDetector().detect(cv2, np, receipt_image)

    assert candidates
    assert candidates[0]["diagnostic"]["areaRatio"] > 0.25
    assert candidates[0]["diagnostic"]["strategy"] in {"bright_paper_region", "edge_document_contour"}
    assert candidates[0]["quad"].shape == (4, 2)


def test_perspective_corrector_returns_portrait_warp_and_matrix(cv, receipt_image):
    cv2, np = cv
    quad = np.array([[175, 65], [525, 95], [570, 830], [120, 800]], dtype="float32")

    warped, matrix = ReceiptPerspectiveCorrector().correct(cv2, np, receipt_image, quad)

    assert warped.shape[0] > warped.shape[1]
    assert warped.shape[0] >= 620
    assert matrix.shape == (3, 3)


def test_deskew_engine_estimates_horizontal_line_rotation(cv):
    cv2, np = cv
    image = np.full((500, 500, 3), 255, dtype=np.uint8)
    for y in range(100, 401, 60):
        cv2.line(image, (60, y), (440, y + 34), (0, 0, 0), 4)

    skew = ReceiptDeskewEngine().estimate(cv2, np, image)
    corrected = ReceiptDeskewEngine().correct(cv2, image, skew)

    assert 3.0 < skew < 7.0
    assert corrected.shape == image.shape
    assert not np.array_equal(corrected, image)


def test_region_locator_builds_columns_whitespace_and_reading_zones_without_ocr(cv):
    cv2, np = cv
    image = np.full((500, 400, 3), 255, dtype=np.uint8)
    for y in range(60, 421, 60):
        cv2.rectangle(image, (35, y), (160, y + 12), (0, 0, 0), -1)
        cv2.rectangle(image, (245, y), (365, y + 12), (0, 0, 0), -1)

    columns, whitespace, zones = ReceiptRegionLocator().locate(cv2, np, image)

    assert len(columns) >= 2
    assert any(run["start"] < 200 < run["end"] for run in whitespace["columnRuns"])
    assert len(zones) >= 5
    assert all(zone.kind == "reading_zone" for zone in zones)


def test_coordinate_system_round_trips_points_and_normalizes_regions():
    coordinates = ReceiptCoordinateSystem(Dimensions(width=400, height=800))
    point = Point(100, 200)

    normalized = coordinates.normalize_point(point)
    restored = coordinates.denormalize_point(normalized)
    region = coordinates.normalize_region(Region(40, 80, 200, 400, "column", 0.9))

    assert normalized == Point(0.25, 0.25)
    assert restored == point
    assert region == {
        "x": 0.1, "y": 0.1, "width": 0.5, "height": 0.5,
        "kind": "column", "confidence": 0.9,
    }


def test_utilities_order_quad_and_preserve_small_detection_image(cv):
    cv2, np = cv
    points = np.array([[10, 90], [100, 10], [100, 90], [10, 10]], dtype="float32")
    ordered = GeometryUtilities.order_quad(np, points)
    image = np.zeros((100, 120, 3), dtype=np.uint8)
    working, scale = GeometryUtilities.scale_for_detection(cv2, image)

    assert ordered.tolist() == [[10.0, 10.0], [100.0, 10.0], [100.0, 90.0], [10.0, 90.0]]
    assert scale == 1.0
    assert working is not image


def test_safe_analyze_returns_none_for_invalid_input():
    assert ReceiptGeometryEngine().safe_analyze(b"not-an-image") is None
