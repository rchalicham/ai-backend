from __future__ import annotations

from .models import GeometryObservation, frozen_map


class BoundaryValidator:
    def validate(self, points, width, height, policy):
        limits = policy.contour_limits
        tolerance = float(limits["boundsToleranceRatio"]) * min(width, height)
        reasons = []
        if len(points) != 4: reasons.append("boundary_must_have_four_points")
        if any(p.x < -tolerance or p.y < -tolerance or p.x > width + tolerance or p.y > height + tolerance for p in points):
            reasons.append("coordinate_outside_image")
        polygon = [(float(p.x), float(p.y)) for p in points]
        if len(polygon) == 4 and self._self_intersects(polygon): reasons.append("self_intersection")
        convex = self._convex(polygon) if len(polygon) == 4 else False
        if not convex: reasons.append("non_convex_boundary")
        confidence = max(0.0, 1.0 - len(reasons) * 0.5)
        return GeometryObservation(tuple(polygon), confidence, not reasons, reasons[0] if reasons else "boundary_valid",
                                   frozen_map({"reasons": tuple(reasons), "imageWidth": width, "imageHeight": height,
                                               "boundsTolerance": tolerance, "convex": convex}))

    @staticmethod
    def _self_intersects(p):
        def cross(a, b, c): return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
        def intersects(a, b, c, d): return cross(a,b,c)*cross(a,b,d) < 0 and cross(c,d,a)*cross(c,d,b) < 0
        return intersects(p[0], p[1], p[2], p[3]) or intersects(p[1], p[2], p[3], p[0])

    @staticmethod
    def _convex(p):
        signs = []
        for i in range(4):
            a, b, c = p[i], p[(i+1)%4], p[(i+2)%4]
            value = (b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0])
            if value: signs.append(value > 0)
        return bool(signs) and all(item == signs[0] for item in signs)
