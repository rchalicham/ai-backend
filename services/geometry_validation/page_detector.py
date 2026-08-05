from __future__ import annotations

from services.receipt_geometry.models import Point
from .models import GeometryObservation, frozen_map


class PageBoundaryDetector:
    def detect(self, cv2, np, image, policy):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        level = float(policy.page_detection["brightPixelLevel"])
        bright_ratio = float((gray >= level).mean())
        threshold = float(policy.page_detection["minimumBrightPixelRatio"])
        confidence = round(min(1.0, bright_ratio/max(threshold,0.001)),4)
        reliable = confidence >= float(policy.confidence_thresholds["page"])
        height,width = gray.shape[:2]
        inset = round(min(width,height)*float(policy.page_detection["boundaryInsetRatio"]),2)
        boundary = (Point(inset,inset), Point(width-1-inset,inset), Point(width-1-inset,height-1-inset), Point(inset,height-1-inset))
        return boundary, GeometryObservation(bright_ratio, confidence, reliable,
                                             "page_boundary_reliable" if reliable else "page_boundary_unreliable",
                                             frozen_map({"brightPixelRatio": bright_ratio, "threshold": threshold}))
