from __future__ import annotations

import math
from typing import Any

from .utilities import GeometryUtilities


class ReceiptDeskewEngine:
    """Estimates and optionally corrects small text-line rotation without OCR."""

    def estimate(self, cv2: Any, np: Any, image: Any) -> float:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        lines = cv2.HoughLinesP(
            edges, 1, np.pi / 180, threshold=max(30, image.shape[1] // 8),
            minLineLength=max(30, image.shape[1] // 5), maxLineGap=12,
        )
        if lines is None:
            return 0.0
        angles = []
        for x1, y1, x2, y2 in lines[:, 0]:
            angle = math.degrees(math.atan2(float(y2 - y1), float(x2 - x1)))
            normalized = ((angle + 45.0) % 90.0) - 45.0
            if abs(normalized) <= 20.0:
                angles.append(normalized)
        return round(float(np.median(angles)), 3) if angles else 0.0

    def correct(self, cv2: Any, image: Any, skew: float) -> Any:
        if abs(skew) < 0.05:
            return image.copy()
        height, width = image.shape[:2]
        matrix = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), skew, 1.0)
        return cv2.warpAffine(image, matrix, (width, height), borderMode=cv2.BORDER_REPLICATE)


class ReceiptPerspectiveCorrector:
    def matrix(self, cv2: Any, np: Any, quad: Any) -> tuple[Any, tuple[int, int]]:
        width, height = GeometryUtilities.target_dimensions(quad)
        destination = np.array(
            [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
            dtype="float32",
        )
        return cv2.getPerspectiveTransform(quad.astype("float32"), destination), (width, height)

    def correct(self, cv2: Any, np: Any, image: Any, quad: Any) -> tuple[Any, Any]:
        matrix, (width, height) = self.matrix(cv2, np, quad)
        warped = cv2.warpPerspective(image, matrix, (width, height), borderMode=cv2.BORDER_REPLICATE)
        return warped, matrix
