from __future__ import annotations

from dataclasses import replace

from .boundary_validator import BoundaryValidator
from .contour_classifier import ContourClassifier
from .contour_validator import ContourValidator
from .fallback_engine import GeometryFallbackEngine
from .geometry_confidence import GeometryConfidenceEngine
from .models import GeometryObservation, GeometryValidationResult, RejectedContour, frozen_map
from .page_detector import PageBoundaryDetector
from .perspective_validator import PerspectiveValidator
from .skew_validator import SkewValidator


class GeometryValidationEngine:
    def __init__(self, policy_loader, metrics=None):
        self.policy_loader=policy_loader
        self.boundaries=BoundaryValidator(); self.classifier=ContourClassifier(); self.contours=ContourValidator()
        self.perspective=PerspectiveValidator(); self.skew=SkewValidator()
        self.fallback=GeometryFallbackEngine(PageBoundaryDetector()); self.confidence=GeometryConfidenceEngine()
        self.metrics=metrics

    def validate(self, cv2, np, image, geometry):
        policy=self.policy_loader.load(); dimensions=geometry.source_dimensions or geometry.page_dimensions
        boundary=self.boundaries.validate(geometry.receipt_boundary,dimensions.width,dimensions.height,policy)
        classification=self.classifier.classify(geometry,policy)
        contour=self.contours.validate(geometry,boundary,classification,policy)
        raw=tuple((p.x,p.y) for p in geometry.receipt_boundary)
        rejected=()
        timeline=[frozen_map({"stage":"contour_detection","status":"observed","confidence":geometry.geometric_confidence}),
                  frozen_map({"stage":"geometry_validation","status":"accepted" if contour.reliable else "rejected","reason":contour.reason})]
        if contour.reliable:
            effective=geometry; source="receipt_boundary"; fallback_contour=()
        else:
            rejected=(RejectedContour(raw,tuple(contour.diagnostics.get("reasons",())),contour.confidence),)
            effective,source,page=self.fallback.select(cv2,np,image,geometry,policy)
            fallback_contour=tuple((p.x,p.y) for p in effective.receipt_boundary)
            timeline.append(frozen_map({"stage":"fallback_geometry","status":"selected","source":source,"reason":page.reason}))

        effective_boundary=self.boundaries.validate(effective.receipt_boundary,dimensions.width,dimensions.height,policy)
        perspective=self.perspective.validate(effective,effective_boundary.reliable,policy)
        skew=self.skew.validate(cv2,np,image,effective_boundary.reliable,policy)
        effective=replace(effective,skew=float(skew.measurement) if skew.reliable else 0.0)
        area=self._coverage(effective.receipt_boundary,dimensions.width,dimensions.height)
        coverage_confidence=effective_boundary.confidence if source != "receipt_boundary" else contour.confidence
        coverage=GeometryObservation(area,coverage_confidence,coverage_confidence >= float(policy.confidence_thresholds["coverage"]),
                                     "coverage_reliable" if coverage_confidence >= float(policy.confidence_thresholds["coverage"]) else "coverage_advisory")
        observations={"contour":contour,"boundary":effective_boundary,"perspective":perspective,"skew":skew,"coverage":coverage,
                      "classification":classification}
        confidence=self.confidence.calculate(observations,policy)
        reliability="reliable" if confidence.reliable else "advisory"
        reason="validated_receipt_contour" if source == "receipt_boundary" else f"invalid_receipt_contour_using_{source}"
        timeline.append(frozen_map({"stage":"geometry_confidence","status":reliability,"confidence":confidence.overall}))
        result=GeometryValidationResult(geometry,geometry if contour.reliable else None,effective,raw,
            raw if contour.reliable else (),fallback_contour,rejected,confidence,reliability,reason,
            "" if source == "receipt_boundary" else source,frozen_map(observations),tuple(timeline),
            policy.configuration_id,policy.version)
        if self.metrics: self.metrics.record(result,ocr_recovered=bool(result.fallback_source))
        return result

    @staticmethod
    def _coverage(points,width,height):
        area=abs(sum(points[i].x*points[(i+1)%len(points)].y-points[(i+1)%len(points)].x*points[i].y for i in range(len(points))))/2 if points else 0
        return round(area/max(width*height,1),4)
