from __future__ import annotations

from typing import Any

from .analyzer import ReceiptGeometryAnalyzer
from .models import Geometry
from .utilities import GeometryUtilities


class ReceiptGeometryEngine:
    """Public, OCR-free facade for receipt geometry analysis."""

    def __init__(self, analyzer: ReceiptGeometryAnalyzer | None = None) -> None:
        self.analyzer = analyzer or ReceiptGeometryAnalyzer()

    def analyze(self, image_bytes: bytes) -> Geometry:
        if not image_bytes:
            raise ValueError("empty_image")
        try:
            import cv2
            import numpy as np
        except Exception as exc:
            raise RuntimeError("opencv_unavailable") from exc
        return self.analyzer.analyze_image(cv2, np, GeometryUtilities.decode_image(cv2, np, image_bytes))

    def safe_analyze(self, image_bytes: bytes) -> Geometry | None:
        try:
            return self.analyze(image_bytes)
        except Exception:
            return None

    def analyze_image(self, cv2: Any, np: Any, image: Any) -> Geometry:
        return self.analyzer.analyze_image(cv2, np, image)
