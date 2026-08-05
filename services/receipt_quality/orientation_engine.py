from __future__ import annotations

from .models import OrientationResult


class OrientationEngine:
    def normalize(self, cv2, np, image, geometry) -> tuple[object, OrientationResult]:
        points = geometry.receipt_boundary
        width = max(abs(points[1].x - points[0].x), abs(points[2].x - points[3].x)) if len(points) >= 4 else image.shape[1]
        height = max(abs(points[3].y - points[0].y), abs(points[2].y - points[1].y)) if len(points) >= 4 else image.shape[0]
        if width <= height:
            inverted = cv2.rotate(image, cv2.ROTATE_180)
            if self._header_density(cv2, image) >= self._header_density(cv2, inverted):
                return image, OrientationResult(0, geometry.geometric_confidence, False)
            return inverted, OrientationResult(180, geometry.geometric_confidence, True)
        clockwise = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
        counter = cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
        chosen, degrees = self._upright_candidate(cv2, np, clockwise, counter)
        return chosen, OrientationResult(degrees, geometry.geometric_confidence, True)

    @staticmethod
    def _upright_candidate(cv2, np, clockwise, counter):
        return (clockwise, 90) if OrientationEngine._header_density(cv2, clockwise) >= OrientationEngine._header_density(cv2, counter) else (counter, 270)

    @staticmethod
    def _header_density(cv2, candidate):
        gray = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY)
        ink = 255 - gray
        segment = max(1, gray.shape[0] // 3)
        return float(ink[:segment].mean()) - float(ink[-segment:].mean())
