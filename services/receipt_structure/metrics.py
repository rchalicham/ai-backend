from __future__ import annotations

import math
from typing import Any, Iterable

from services.receipt_dom import BoundingBox


def union_boxes(nodes: Iterable[Any]) -> BoundingBox:
    boxes = [node.geometry if hasattr(node, "geometry") else node for node in nodes]
    if not boxes:
        return BoundingBox(0, 0, 0, 0)
    left, top = min(box.x for box in boxes), min(box.y for box in boxes)
    right, bottom = max(box.right for box in boxes), max(box.bottom for box in boxes)
    return BoundingBox(left, top, right - left, bottom - top, boxes[0].coordinate_space)


def coefficient_consistency(values: list[float]) -> float:
    positives = [value for value in values if value >= 0]
    if len(positives) < 2:
        return 0.5 if positives else 0.0
    mean = sum(positives) / len(positives)
    if mean <= 1e-9:
        return 1.0
    variance = sum((value - mean) ** 2 for value in positives) / len(positives)
    return max(0.0, min(1.0, 1.0 - math.sqrt(variance) / mean))


def clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def iter_blocks(page: Any) -> tuple[Any, ...]:
    return tuple(block for region in page.regions for block in region.blocks)


def iter_lines(page: Any) -> tuple[Any, ...]:
    return tuple(line for block in iter_blocks(page) for line in block.lines)


def iter_words(page: Any) -> tuple[Any, ...]:
    return tuple(word for line in iter_lines(page) for word in line.words)
