from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class Dimensions:
    width: int
    height: int


@dataclass(frozen=True)
class Region:
    x: int
    y: int
    width: int
    height: int
    kind: str
    confidence: float = 0.0


@dataclass
class Geometry:
    """OCR-independent geometric description of a receipt image."""

    receipt_boundary: list[Point]
    page_dimensions: Dimensions
    rotation: float
    skew: float
    perspective_matrix: list[list[float]]
    detected_columns: list[Region] = field(default_factory=list)
    whitespace_map: dict[str, Any] = field(default_factory=dict)
    estimated_reading_zones: list[Region] = field(default_factory=list)
    geometric_confidence: float = 0.0
    source_dimensions: Dimensions | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
