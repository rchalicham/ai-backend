import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.receipt_image_isolation import ReceiptImageIsolationService


def test_receipt_image_isolation_warps_largest_receipt_region_and_reports_debug_metadata():
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")

    image = np.zeros((900, 700, 3), dtype=np.uint8)
    image[:] = (18, 18, 18)
    receipt = np.array([[185, 70], [520, 105], [575, 820], [125, 790]], dtype=np.int32)
    cv2.fillConvexPoly(image, receipt, (238, 238, 228))
    cv2.putText(image, "FRESHTHYME.COM", (190, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (35, 35, 35), 2)
    cv2.putText(image, "TOTAL 12.34", (190, 730), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (35, 35, 35), 2)
    success, encoded = cv2.imencode(".jpg", image)
    assert success

    result = ReceiptImageIsolationService().isolate(encoded.tobytes())
    output = cv2.imdecode(np.frombuffer(result.image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)

    assert result.diagnostics["applied"] is True
    assert result.diagnostics["ocrInputPolicy"] == "raw_image_never_forwarded"
    assert result.diagnostics["receiptIsolated"] is True
    assert result.diagnostics["backgroundRemoved"] is True
    assert result.diagnostics["selectedContour"]["areaRatio"] > 0.25
    assert output.shape[0] > output.shape[1]
    assert output.mean() > 120
