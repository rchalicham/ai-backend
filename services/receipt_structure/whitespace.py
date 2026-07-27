from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from services.receipt_dom import BoundingBox, ReceiptDocument

from .metrics import iter_lines
from .models import SeparatorLine, WhitespaceZone


class ReceiptWhitespaceAnalyzer:
    def analyze(self, document: ReceiptDocument) -> tuple[tuple[WhitespaceZone, ...], tuple[SeparatorLine, ...]]:
        zones, separators = [], []
        for page in document.pages:
            lines = sorted(iter_lines(page), key=lambda line: line.geometry.y)
            width, height = page.dimensions.width, page.dimensions.height
            if lines:
                left = min(line.geometry.x for line in lines)
                right = max(line.geometry.right for line in lines)
                for kind, box in (
                    ("left_margin", BoundingBox(0, 0, max(0, left), height)),
                    ("right_margin", BoundingBox(right, 0, max(0, width - right), height)),
                    ("top_margin", BoundingBox(0, 0, width, max(0, lines[0].geometry.y))),
                    ("bottom_margin", BoundingBox(0, lines[-1].geometry.bottom, width, max(0, height - lines[-1].geometry.bottom))),
                ):
                    if box.width > 1 and box.height > 1:
                        zones.append(self._zone(document.id, page.id, kind, box, len(zones)))
                gaps = [(lines[index].geometry.bottom, lines[index + 1].geometry.y) for index in range(len(lines) - 1)]
                positive = [bottom - top for top, bottom in gaps if bottom > top]
                typical = sorted(positive)[len(positive) // 2] if positive else 0
                for gap_index, (top, bottom) in enumerate(gaps):
                    gap = bottom - top
                    if gap > max(6, typical * 1.6):
                        kind = "paragraph_spacing" if gap < max(18, typical * 3) else "section_spacing"
                        zones.append(self._zone(document.id, page.id, kind, BoundingBox(0, top, width, gap), gap_index))
                    if 1 <= gap <= 4 and lines[gap_index].geometry.width >= width * 0.7:
                        separators.append(SeparatorLine(
                            id=str(uuid5(NAMESPACE_URL, f"{document.id}:{page.id}:separator:{gap_index}")),
                            page_id=page.id,
                            geometry=BoundingBox(0, top, width, max(1, gap)),
                            confidence=0.6,
                        ))
            for index, column in enumerate(page.geometry.detected_columns):
                if index:
                    previous = page.geometry.detected_columns[index - 1]
                    gap = column.x - previous.right
                    if gap > 4:
                        zones.append(self._zone(
                            document.id, page.id, "gutter",
                            BoundingBox(previous.right, 0, gap, height), index,
                        ))
        return tuple(zones), tuple(separators)

    @staticmethod
    def _zone(document_id: str, page_id: str, kind: str, box: BoundingBox, index: int) -> WhitespaceZone:
        return WhitespaceZone(
            id=str(uuid5(NAMESPACE_URL, f"{document_id}:{page_id}:whitespace:{kind}:{index}")),
            page_id=page_id,
            kind=kind,
            geometry=box,
            confidence=0.8,
        )
