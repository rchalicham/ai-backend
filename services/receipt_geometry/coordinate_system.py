from __future__ import annotations

from .models import Dimensions, Point, Region


class ReceiptCoordinateSystem:
    """Converts between pixel coordinates and normalized receipt coordinates."""

    def __init__(self, dimensions: Dimensions) -> None:
        self.dimensions = dimensions

    def normalize_point(self, point: Point) -> Point:
        return Point(point.x / max(self.dimensions.width, 1), point.y / max(self.dimensions.height, 1))

    def denormalize_point(self, point: Point) -> Point:
        return Point(point.x * self.dimensions.width, point.y * self.dimensions.height)

    def normalize_region(self, region: Region) -> dict[str, float | str]:
        return {
            "x": region.x / max(self.dimensions.width, 1),
            "y": region.y / max(self.dimensions.height, 1),
            "width": region.width / max(self.dimensions.width, 1),
            "height": region.height / max(self.dimensions.height, 1),
            "kind": region.kind,
            "confidence": region.confidence,
        }
