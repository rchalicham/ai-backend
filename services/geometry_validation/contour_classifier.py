from __future__ import annotations

from .models import GeometryObservation, frozen_map


class ContourClassifier:
    def classify(self, geometry, policy):
        diagnostic = (geometry.diagnostics or {}).get("selectedContour") or {}
        rectangularity = float(diagnostic.get("rectangularity") or 0.0)
        aspect = float(diagnostic.get("aspectRatio") or 0.0)
        area = float(diagnostic.get("areaRatio") or 0.0)
        limits = policy.contour_limits
        rectangular = min(1.0, rectangularity / max(float(limits["minimumRectangularity"]), 0.001))
        aspect_ok = float(limits["minimumAspectRatio"]) <= aspect <= float(limits["maximumAspectRatio"])
        area_ok = float(limits["minimumAreaRatio"]) <= area <= float(limits["maximumAreaRatio"])
        likelihood = round(rectangular * (1.0 if aspect_ok else 0.35) * (1.0 if area_ok else 0.25), 4)
        reliable = likelihood >= float(limits["minimumReceiptLikelihood"])
        return GeometryObservation(likelihood, likelihood, reliable,
                                   "receipt_likely" if reliable else "low_receipt_likelihood",
                                   frozen_map({"rectangularity": rectangularity, "aspectRatio": aspect,
                                               "areaRatio": area, "strategy": diagnostic.get("strategy", "none")}))
