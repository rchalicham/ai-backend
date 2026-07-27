from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any

from services.receipt_geometry import (
    GeometryUtilities,
    ReceiptContourDetector,
    ReceiptPerspectiveCorrector,
    ReceiptRegionLocator,
)


@dataclass
class ReceiptIsolationResult:
    image_bytes: bytes
    diagnostics: dict[str, Any] = field(default_factory=dict)


class ReceiptImageIsolationService:
    """Compatibility facade over the reusable Receipt Geometry Engine services."""

    def __init__(
        self,
        debug_preview: bool = False,
        contour_detector: ReceiptContourDetector | None = None,
        perspective_corrector: ReceiptPerspectiveCorrector | None = None,
        region_locator: ReceiptRegionLocator | None = None,
    ) -> None:
        self.debug_preview = debug_preview
        self.contour_detector = contour_detector or ReceiptContourDetector()
        self.perspective_corrector = perspective_corrector or ReceiptPerspectiveCorrector()
        self.region_locator = region_locator or ReceiptRegionLocator()

    def isolate(self, image_bytes: bytes, debug: bool | None = None) -> ReceiptIsolationResult:
        diagnostics: dict[str, Any] = {
            "schemaVersion": "receipt-image-isolation-v1",
            "applied": False,
            "engine": "opencv",
            "ocrInputPolicy": "raw_image_never_forwarded",
            "warnings": [],
            "contours": [],
            "selectedContour": None,
            "receiptMask": {},
            "sectionBoundaries": [],
        }
        if not image_bytes:
            diagnostics["warnings"].append("empty_image")
            return ReceiptIsolationResult(image_bytes=b"", diagnostics=diagnostics)
        try:
            import cv2
            import numpy as np
        except Exception as exc:
            diagnostics["engine"] = "unavailable"
            diagnostics["warnings"].append(f"opencv_unavailable:{exc.__class__.__name__}")
            return ReceiptIsolationResult(image_bytes=image_bytes, diagnostics=diagnostics)

        try:
            source = GeometryUtilities.decode_image(cv2, np, image_bytes)
            original_height, original_width = source.shape[:2]
            working, scale = GeometryUtilities.scale_for_detection(cv2, source)
            candidates = self.contour_detector.detect(cv2, np, working)
            diagnostics["source"] = {"width": original_width, "height": original_height}
            diagnostics["working"] = {
                "width": working.shape[1], "height": working.shape[0], "scale": round(scale, 4)
            }
            diagnostics["contours"] = [candidate["diagnostic"] for candidate in candidates[:10]]
            if not candidates:
                diagnostics["warnings"].append("receipt_contour_not_found")
                normalized = GeometryUtilities.enhance_receipt(cv2, source)
                return ReceiptIsolationResult(
                    image_bytes=GeometryUtilities.encode_image(cv2, normalized),
                    diagnostics={
                        **diagnostics,
                        "applied": True,
                        "receiptIsolated": False,
                        "backgroundRemoved": False,
                        "strategy": "full_image_enhancement_no_raw_passthrough",
                    },
                )

            selected = candidates[0]
            quad = (selected["quad"] / scale).astype("float32")
            warped, _ = self.perspective_corrector.correct(cv2, np, source, quad)
            cleaned = self._clean_receipt_pixels(cv2, warped)
            output_bytes = GeometryUtilities.encode_image(cv2, cleaned)
            diagnostics.update({
                "applied": True,
                "receiptIsolated": True,
                "backgroundRemoved": True,
                "strategy": "largest_document_contour_perspective_warp",
                "selectedContour": {
                    **selected["diagnostic"],
                    "quad": [
                        {"x": round(float(point[0] / scale), 2), "y": round(float(point[1] / scale), 2)}
                        for point in selected["quad"]
                    ],
                },
                "output": {"width": cleaned.shape[1], "height": cleaned.shape[0], "bytes": len(output_bytes)},
                "receiptMask": self._mask_diagnostics(cv2, np, working, selected["quad"]),
                "sectionBoundaries": self.region_locator.section_boundaries(cv2, cleaned),
            })
            if self.debug_preview if debug is None else debug:
                diagnostics["previews"] = self._debug_previews(cv2, working, selected["quad"], cleaned)
            return ReceiptIsolationResult(image_bytes=output_bytes, diagnostics=diagnostics)
        except Exception as exc:
            diagnostics["engine"] = "opencv_error"
            diagnostics["warnings"].append(f"receipt_isolation_failed:{exc.__class__.__name__}")
            return ReceiptIsolationResult(image_bytes=image_bytes, diagnostics=diagnostics)

    def _clean_receipt_pixels(self, cv2: Any, image: Any) -> Any:
        enhanced = GeometryUtilities.enhance_receipt(cv2, image)
        gray = cv2.cvtColor(enhanced, cv2.COLOR_BGR2GRAY)
        border = max(8, min(gray.shape[:2]) // 80)
        gray[:border, :] = 255
        gray[-border:, :] = 255
        gray[:, :border] = 255
        gray[:, -border:] = 255
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

    @staticmethod
    def _mask_diagnostics(cv2: Any, np: Any, image: Any, quad: Any) -> dict[str, Any]:
        mask = np.zeros(image.shape[:2], dtype=np.uint8)
        cv2.fillConvexPoly(mask, quad.astype("int32"), 255)
        return {
            "width": int(mask.shape[1]),
            "height": int(mask.shape[0]),
            "coverageRatio": round(int(cv2.countNonZero(mask)) / max(mask.size, 1), 4),
        }

    def _debug_previews(self, cv2: Any, working: Any, quad: Any, cleaned: Any) -> dict[str, str]:
        overlay = working.copy()
        cv2.polylines(overlay, [quad.astype("int32")], True, (0, 255, 0), 4)
        return {
            "contourOverlayJpegBase64": self._preview_b64(cv2, overlay),
            "ocrInputJpegBase64": self._preview_b64(cv2, cleaned),
        }

    @staticmethod
    def _preview_b64(cv2: Any, image: Any) -> str:
        success, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        return base64.b64encode(encoded.tobytes()).decode("ascii") if success else ""
