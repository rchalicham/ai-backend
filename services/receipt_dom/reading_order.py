from __future__ import annotations

import math
from dataclasses import replace
from typing import Any, TypeVar

from .geometry import BoundingBox
from .nodes import NodeRelationships

NodeT = TypeVar("NodeT")


class ReadingOrderEngine:
    """Geometry-first ordering and spatial relationships; OCR order is ignored."""

    def order(self, nodes: tuple[NodeT, ...] | list[NodeT]) -> tuple[NodeT, ...]:
        values = list(nodes)
        if not values:
            return ()
        ordered = sorted(values, key=self._sort_key)
        relationships = self._relationships(ordered)
        return tuple(
            replace(node, reading_order=index, relationships=relationships[node.id])
            for index, node in enumerate(ordered)
        )

    def _sort_key(self, node: Any) -> tuple[float, float, float]:
        box = node.geometry
        row_tolerance = max(4.0, box.height * 0.55)
        row_bucket = round(box.y / row_tolerance) * row_tolerance
        return row_bucket, box.x, box.y

    def _relationships(self, nodes: list[Any]) -> dict[str, NodeRelationships]:
        output = {}
        for index, node in enumerate(nodes):
            box = node.geometry
            others = [candidate for candidate in nodes if candidate.id != node.id]
            above = self._nearest_direction(box, others, "above")
            below = self._nearest_direction(box, others, "below")
            left = self._nearest_direction(box, others, "left")
            right = self._nearest_direction(box, others, "right")
            nearest = sorted(others, key=lambda candidate: self._distance(box, candidate.geometry))[:4]
            previous = nodes[index - 1] if index else None
            following = nodes[index + 1] if index + 1 < len(nodes) else None
            output[node.id] = replace(
                node.relationships,
                previous_sibling_id=previous.id if previous else None,
                next_sibling_id=following.id if following else None,
                above_id=above.id if above else None,
                below_id=below.id if below else None,
                left_id=left.id if left else None,
                right_id=right.id if right else None,
                nearest_neighbor_ids=tuple(candidate.id for candidate in nearest),
            )
        return output

    def _nearest_direction(self, box: BoundingBox, nodes: list[Any], direction: str) -> Any | None:
        cx, cy = box.center
        candidates = []
        for node in nodes:
            nx, ny = node.geometry.center
            valid = {
                "above": ny < cy and self._overlaps_x(box, node.geometry),
                "below": ny > cy and self._overlaps_x(box, node.geometry),
                "left": nx < cx and self._overlaps_y(box, node.geometry),
                "right": nx > cx and self._overlaps_y(box, node.geometry),
            }[direction]
            if valid:
                candidates.append(node)
        return min(candidates, key=lambda node: self._distance(box, node.geometry)) if candidates else None

    @staticmethod
    def _distance(left: BoundingBox, right: BoundingBox) -> float:
        lx, ly = left.center
        rx, ry = right.center
        return math.hypot(lx - rx, ly - ry)

    @staticmethod
    def _overlaps_x(left: BoundingBox, right: BoundingBox) -> bool:
        return max(left.x, right.x) <= min(left.right, right.right)

    @staticmethod
    def _overlaps_y(left: BoundingBox, right: BoundingBox) -> bool:
        return max(left.y, right.y) <= min(left.bottom, right.bottom)
