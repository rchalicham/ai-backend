from __future__ import annotations

import math
from .models import GeometryObservation, frozen_map


class ContourValidator:
    def validate(self, geometry, boundary, classification, policy):
        points = geometry.receipt_boundary
        area = self._area(points)
        dimensions = geometry.source_dimensions or geometry.page_dimensions
        area_ratio = area / max(dimensions.width * dimensions.height, 1)
        edges = [math.dist((points[i].x, points[i].y), (points[(i+1)%4].x, points[(i+1)%4].y)) for i in range(4)] if len(points) == 4 else []
        aspect = max(edges) / max(min(edges), 1) if edges else 0.0
        limits = policy.contour_limits
        reasons = list(boundary.diagnostics.get("reasons", ()))
        if not (float(limits["minimumAreaRatio"]) <= area_ratio <= float(limits["maximumAreaRatio"])): reasons.append("area_ratio_out_of_range")
        if not (float(limits["minimumAspectRatio"]) <= aspect <= float(limits["maximumAspectRatio"])): reasons.append("aspect_ratio_out_of_range")
        if not classification.reliable: reasons.append("low_receipt_likelihood")
        confidence = round(min(boundary.confidence, classification.confidence,
                               float(getattr(geometry, "geometric_confidence", 0.0))), 4)
        reliable = not reasons and confidence >= float(policy.confidence_thresholds["contour"])
        if not reliable and not reasons: reasons.append("contour_confidence_below_threshold")
        return GeometryObservation(tuple((p.x,p.y) for p in points), confidence, reliable,
                                   "contour_valid" if reliable else reasons[0],
                                   frozen_map({"reasons": tuple(reasons), "areaRatio": area_ratio, "aspectRatio": aspect}))

    @staticmethod
    def _area(points):
        return abs(sum(points[i].x*points[(i+1)%len(points)].y-points[(i+1)%len(points)].x*points[i].y for i in range(len(points))))/2 if points else 0.0
