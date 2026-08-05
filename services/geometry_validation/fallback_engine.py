from __future__ import annotations

from dataclasses import replace
import numpy as np
from services.receipt_geometry.models import Point


class GeometryFallbackEngine:
    def __init__(self, page_detector): self.page_detector = page_detector

    def select(self, cv2, np_module, image, geometry, policy):
        height,width = image.shape[:2]
        page_boundary,page = self.page_detector.detect(cv2,np_module,image,policy)
        image_boundary=(Point(0,0),Point(width-1,0),Point(width-1,height-1),Point(0,height-1))
        for source in policy.fallback_order:
            if source == "page_boundary" and page.reliable:
                return self._geometry(geometry,page_boundary,width,height), "page_boundary", page
            if source == "image_boundary":
                return self._geometry(geometry,image_boundary,width,height), "image_boundary", page
        return self._geometry(geometry,image_boundary,width,height), "image_boundary", page

    @staticmethod
    def _geometry(geometry,boundary,width,height):
        return replace(geometry, receipt_boundary=list(boundary), page_dimensions=geometry.source_dimensions or geometry.page_dimensions,
                       source_dimensions=geometry.source_dimensions or geometry.page_dimensions, rotation=0.0, skew=0.0,
                       perspective_matrix=np.eye(3,dtype="float32").tolist(), geometric_confidence=1.0,
                       diagnostics={**(geometry.diagnostics or {}),"fallbackGeometry":True})
