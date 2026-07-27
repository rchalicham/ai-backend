from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from services.receipt_dom import ReceiptDocument

from .metrics import iter_lines
from .models import AlignmentGroup, AlignmentType


class ReceiptAlignmentAnalyzer:
    def classify(self, node, page_width: float) -> AlignmentType:
        box = node.geometry
        left_gap, right_gap = box.x, max(0.0, page_width - box.right)
        tolerance = max(6.0, page_width * 0.035)
        if abs(left_gap - right_gap) <= tolerance:
            return AlignmentType.CENTER
        if right_gap <= tolerance or right_gap < left_gap * 0.35:
            return AlignmentType.RIGHT
        if box.width >= page_width * 0.82:
            return AlignmentType.JUSTIFIED
        if left_gap <= tolerance or left_gap < right_gap * 0.35:
            return AlignmentType.LEFT
        return AlignmentType.MIXED

    def groups(self, document: ReceiptDocument) -> tuple[AlignmentGroup, ...]:
        groups = []
        for page in document.pages:
            buckets: dict[tuple[AlignmentType, int], list] = {}
            tolerance = max(8.0, page.dimensions.width * 0.04)
            for line in iter_lines(page):
                alignment = self.classify(line, page.dimensions.width)
                anchor = self._anchor(line, alignment)
                buckets.setdefault((alignment, round(anchor / tolerance)), []).append(line)
            for index, ((alignment, _), lines) in enumerate(sorted(buckets.items(), key=lambda item: (item[0][0].value, item[0][1]))):
                if not lines:
                    continue
                anchors = [self._anchor(line, alignment) for line in lines]
                spread = max(anchors) - min(anchors)
                confidence = max(0.2, 1.0 - spread / max(tolerance, 1))
                groups.append(AlignmentGroup(
                    id=str(uuid5(NAMESPACE_URL, f"{document.id}:{page.id}:alignment:{index}")),
                    page_id=page.id,
                    alignment=alignment,
                    node_ids=tuple(line.id for line in sorted(lines, key=lambda line: line.reading_order)),
                    anchor=round(sum(anchors) / len(anchors), 2),
                    confidence=round(confidence, 4),
                ))
        return tuple(groups)

    @staticmethod
    def _anchor(node, alignment: AlignmentType) -> float:
        if alignment == AlignmentType.RIGHT:
            return node.geometry.right
        if alignment == AlignmentType.CENTER:
            return node.geometry.center[0]
        return node.geometry.x
