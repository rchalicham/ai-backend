from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class CoordinateSpace(str, Enum):
    ORIGINAL_IMAGE = "original_image"
    CORRECTED_IMAGE = "corrected_image"
    NORMALIZED_PAGE = "normalized_page"


@dataclass(frozen=True, slots=True)
class Dimensions:
    width: float
    height: float


@dataclass(frozen=True, slots=True)
class BoundingBox:
    x: float
    y: float
    width: float
    height: float
    coordinate_space: CoordinateSpace = CoordinateSpace.CORRECTED_IMAGE

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.width / 2.0, self.y + self.height / 2.0


@dataclass(frozen=True, slots=True)
class ReceiptGeometrySnapshot:
    """Immutable snapshot of Phase 1 Geometry; the engine remains unchanged."""

    receipt_boundary: tuple[tuple[float, float], ...]
    page_dimensions: Dimensions
    source_dimensions: Dimensions | None
    rotation: float
    skew: float
    perspective_matrix: tuple[tuple[float, ...], ...]
    detected_columns: tuple[BoundingBox, ...]
    whitespace_map: tuple[tuple[str, Any], ...]
    estimated_reading_zones: tuple[BoundingBox, ...]
    geometric_confidence: float
    diagnostics: tuple[tuple[str, Any], ...]

    @classmethod
    def from_phase1(cls, geometry: Any) -> "ReceiptGeometrySnapshot":
        return cls(
            receipt_boundary=tuple((float(point.x), float(point.y)) for point in geometry.receipt_boundary),
            page_dimensions=Dimensions(float(geometry.page_dimensions.width), float(geometry.page_dimensions.height)),
            source_dimensions=(
                Dimensions(float(geometry.source_dimensions.width), float(geometry.source_dimensions.height))
                if geometry.source_dimensions else None
            ),
            rotation=float(geometry.rotation),
            skew=float(geometry.skew),
            perspective_matrix=tuple(tuple(float(value) for value in row) for row in geometry.perspective_matrix),
            detected_columns=tuple(_region_box(region) for region in geometry.detected_columns),
            whitespace_map=_freeze_mapping(geometry.whitespace_map),
            estimated_reading_zones=tuple(_region_box(region) for region in geometry.estimated_reading_zones),
            geometric_confidence=float(geometry.geometric_confidence),
            diagnostics=_freeze_mapping(geometry.diagnostics),
        )


class CoordinateSystem:
    """The only supported coordinate conversion boundary for DOM consumers."""

    def __init__(self, geometry: ReceiptGeometrySnapshot) -> None:
        self.geometry = geometry

    def convert(self, box: BoundingBox, target: CoordinateSpace) -> BoundingBox:
        if box.coordinate_space == target:
            return box
        corrected = self._to_corrected(box)
        return self._from_corrected(corrected, target)

    def _to_corrected(self, box: BoundingBox) -> BoundingBox:
        if box.coordinate_space == CoordinateSpace.NORMALIZED_PAGE:
            dimensions = self.geometry.page_dimensions
            return BoundingBox(
                box.x * dimensions.width, box.y * dimensions.height,
                box.width * dimensions.width, box.height * dimensions.height,
                CoordinateSpace.CORRECTED_IMAGE,
            )
        if box.coordinate_space == CoordinateSpace.ORIGINAL_IMAGE:
            return self._perspective_box(box, self.geometry.perspective_matrix)
        return box

    def _from_corrected(self, box: BoundingBox, target: CoordinateSpace) -> BoundingBox:
        if target == CoordinateSpace.NORMALIZED_PAGE:
            dimensions = self.geometry.page_dimensions
            return BoundingBox(
                box.x / max(dimensions.width, 1), box.y / max(dimensions.height, 1),
                box.width / max(dimensions.width, 1), box.height / max(dimensions.height, 1),
                target,
            )
        if target == CoordinateSpace.ORIGINAL_IMAGE:
            inverse = _invert_3x3(self.geometry.perspective_matrix)
            return self._perspective_box(box, inverse, target)
        return BoundingBox(box.x, box.y, box.width, box.height, target)

    @staticmethod
    def _perspective_box(
        box: BoundingBox,
        matrix: tuple[tuple[float, ...], ...],
        target: CoordinateSpace = CoordinateSpace.CORRECTED_IMAGE,
    ) -> BoundingBox:
        points = [
            _transform_point(box.x, box.y, matrix),
            _transform_point(box.right, box.y, matrix),
            _transform_point(box.right, box.bottom, matrix),
            _transform_point(box.x, box.bottom, matrix),
        ]
        xs, ys = [point[0] for point in points], [point[1] for point in points]
        return BoundingBox(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys), target)


def _region_box(region: Any) -> BoundingBox:
    return BoundingBox(float(region.x), float(region.y), float(region.width), float(region.height))


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return _freeze_mapping(value)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _freeze_mapping(value: dict[str, Any]) -> tuple[tuple[str, Any], ...]:
    return tuple((str(key), _freeze(item)) for key, item in sorted((value or {}).items()))


def _transform_point(x: float, y: float, matrix: tuple[tuple[float, ...], ...]) -> tuple[float, float]:
    denominator = matrix[2][0] * x + matrix[2][1] * y + matrix[2][2]
    denominator = denominator if abs(denominator) > 1e-12 else 1.0
    return (
        (matrix[0][0] * x + matrix[0][1] * y + matrix[0][2]) / denominator,
        (matrix[1][0] * x + matrix[1][1] * y + matrix[1][2]) / denominator,
    )


def _invert_3x3(matrix: tuple[tuple[float, ...], ...]) -> tuple[tuple[float, ...], ...]:
    a, b, c = matrix[0]
    d, e, f = matrix[1]
    g, h, i = matrix[2]
    determinant = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(determinant) < 1e-12:
        return ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    inverse = (
        (e * i - f * h, c * h - b * i, b * f - c * e),
        (f * g - d * i, a * i - c * g, c * d - a * f),
        (d * h - e * g, b * g - a * h, a * e - b * d),
    )
    return tuple(tuple(value / determinant for value in row) for row in inverse)
