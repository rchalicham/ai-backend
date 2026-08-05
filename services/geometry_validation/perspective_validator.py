from __future__ import annotations

import math
import numpy as np
from .models import GeometryObservation, frozen_map


class PerspectiveValidator:
    def validate(self, geometry, contour_reliable, policy):
        p = geometry.receipt_boundary
        if len(p) != 4 or not contour_reliable:
            return GeometryObservation(None, 0.0, False, "perspective_requires_reliable_contour")
        top,bottom = math.dist((p[0].x,p[0].y),(p[1].x,p[1].y)), math.dist((p[3].x,p[3].y),(p[2].x,p[2].y))
        left,right = math.dist((p[0].x,p[0].y),(p[3].x,p[3].y)), math.dist((p[1].x,p[1].y),(p[2].x,p[2].y))
        distortion = max(abs(top-bottom)/max(top,bottom,1), abs(left-right)/max(left,right,1))
        maximum = float(policy.perspective_limits["maximumOpposingEdgeDistortion"])
        matrix=np.asarray(geometry.perspective_matrix,dtype=float)
        condition=float(np.linalg.cond(matrix)) if matrix.shape == (3,3) else float("inf")
        maximum_condition=float(policy.perspective_limits["maximumConditionNumber"])
        stability=max(0.0,1.0-condition/max(maximum_condition,1.0))
        confidence = round(max(0.0, 1.0-distortion/max(maximum,0.001))*stability,4)
        reliable = distortion <= maximum and condition <= maximum_condition and confidence >= float(policy.confidence_thresholds["perspective"])
        return GeometryObservation(distortion, confidence, reliable, "perspective_valid" if reliable else "unstable_perspective",
                                   frozen_map({"opposingEdgeDistortion": distortion, "maximum": maximum,
                                               "transformationConditionNumber":condition,"maximumConditionNumber":maximum_condition}))
