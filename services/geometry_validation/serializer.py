from __future__ import annotations

from .diagnostics import observation_diagnostics


class GeometryValidationSerializer:
    def to_dict(self,result):
        points=lambda value:[{"x":x,"y":y} for x,y in value]
        return {"schemaVersion":"geometry-validation-v1","reliability":result.reliability,"reason":result.reason,
                "rawContour":points(result.raw_contour),"validatedContour":points(result.validated_contour),
                "fallbackContour":points(result.fallback_contour),"fallbackSource":result.fallback_source,
                "rejectedContours":[{"boundary":points(item.boundary),"reasons":list(item.reasons),"confidence":item.confidence} for item in result.rejected_contours],
                "confidence":result.confidence.__dict__,"observations":observation_diagnostics(result),
                "timeline":[dict(item) for item in result.timeline],
                "configuration":{"id":result.configuration_id,"version":result.configuration_version}}
