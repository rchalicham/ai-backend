from __future__ import annotations

from services.receipt_geometry.correction import ReceiptDeskewEngine
from .models import GeometryObservation, frozen_map


class SkewValidator:
    def validate(self, cv2, np, image, geometry_reliable, policy):
        measured = ReceiptDeskewEngine().estimate(cv2, np, image)
        gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY); edges=cv2.Canny(gray,50,150,apertureSize=3)
        lines=cv2.HoughLinesP(edges,1,np.pi/180,threshold=max(30,image.shape[1]//8),
                             minLineLength=max(30,image.shape[1]//5),maxLineGap=12)
        line_count=0 if lines is None else len(lines)
        minimum_lines=int(policy.skew_limits["minimumLineCount"])
        maximum = float(policy.skew_limits["maximumReliableDegrees"])
        confidence = round(max(0.0, 1.0-abs(measured)/max(maximum,0.001)),4)
        reliable = geometry_reliable and line_count >= minimum_lines and abs(measured) <= maximum and confidence >= float(policy.confidence_thresholds["skew"])
        return GeometryObservation(measured, confidence, reliable, "skew_valid" if reliable else "skew_unreliable",
                                   frozen_map({"directImageMeasurement": True, "maximumDegrees": maximum,
                                               "lineCount":line_count,"minimumLineCount":minimum_lines}))
