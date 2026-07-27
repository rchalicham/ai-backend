from __future__ import annotations

import math
from typing import Any

from .contour import ReceiptContourDetector
from .correction import ReceiptDeskewEngine, ReceiptPerspectiveCorrector
from .models import Dimensions, Geometry, Point
from .regions import ReceiptRegionLocator
from .utilities import GeometryUtilities


class ReceiptGeometryAnalyzer:
    def __init__(
        self,
        contour_detector: ReceiptContourDetector | None = None,
        deskew_engine: ReceiptDeskewEngine | None = None,
        perspective_corrector: ReceiptPerspectiveCorrector | None = None,
        region_locator: ReceiptRegionLocator | None = None,
    ) -> None:
        self.contour_detector = contour_detector or ReceiptContourDetector()
        self.deskew_engine = deskew_engine or ReceiptDeskewEngine()
        self.perspective_corrector = perspective_corrector or ReceiptPerspectiveCorrector()
        self.region_locator = region_locator or ReceiptRegionLocator()

    def analyze_image(self, cv2: Any, np: Any, source: Any) -> Geometry:
        source_height, source_width = source.shape[:2]
        working, scale = GeometryUtilities.scale_for_detection(cv2, source)
        candidates = self.contour_detector.detect(cv2, np, working)
        selected = candidates[0] if candidates else None
        if selected:
            quad = (selected["quad"] / scale).astype("float32")
            layout_image, matrix = self.perspective_corrector.correct(cv2, np, source, quad)
            confidence = self._confidence(selected["diagnostic"], True)
        else:
            quad = np.array(
                [[0, 0], [source_width - 1, 0], [source_width - 1, source_height - 1], [0, source_height - 1]],
                dtype="float32",
            )
            layout_image = source
            matrix = np.eye(3, dtype="float32")
            confidence = 0.2
        skew = self.deskew_engine.estimate(cv2, np, layout_image)
        rotation = self._boundary_rotation(quad)
        columns, whitespace, zones = self.region_locator.locate(cv2, np, layout_image)
        height, width = layout_image.shape[:2]
        return Geometry(
            receipt_boundary=[Point(round(float(x), 2), round(float(y), 2)) for x, y in quad],
            page_dimensions=Dimensions(width, height),
            source_dimensions=Dimensions(source_width, source_height),
            rotation=round(rotation, 3),
            skew=skew,
            perspective_matrix=[[round(float(value), 8) for value in row] for row in matrix],
            detected_columns=columns,
            whitespace_map=whitespace,
            estimated_reading_zones=zones,
            geometric_confidence=confidence,
            diagnostics={
                "contourFound": bool(selected),
                "selectedContour": selected["diagnostic"] if selected else None,
                "candidateCount": len(candidates),
                "workingScale": round(scale, 4),
            },
        )

    @staticmethod
    def _boundary_rotation(quad: Any) -> float:
        tl, tr = quad[0], quad[1]
        return math.degrees(math.atan2(float(tr[1] - tl[1]), float(tr[0] - tl[0])))

    @staticmethod
    def _confidence(diagnostic: dict[str, Any], found: bool) -> float:
        if not found:
            return 0.2
        area = float(diagnostic.get("areaRatio") or 0.0)
        rectangularity = float(diagnostic.get("rectangularity") or 0.0)
        aspect = float(diagnostic.get("aspectRatio") or 1.0)
        aspect_score = min(1.0, max(0.0, (aspect - 1.0) / 1.5))
        return round(min(1.0, 0.25 + area * 0.35 + rectangularity * 0.3 + aspect_score * 0.1), 4)
