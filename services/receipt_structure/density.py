from __future__ import annotations

from services.receipt_dom import BoundingBox, ReceiptDocument

from .metrics import clamp, iter_blocks, iter_lines, iter_words
from .models import DensityCell, DensityMap, DensityMetrics


class ReceiptDensityAnalyzer:
    def measure(self, node) -> DensityMetrics:
        lines = tuple(getattr(node, "lines", ()))
        if hasattr(node, "blocks"):
            lines = tuple(line for block in node.blocks for line in block.lines)
        words = tuple(word for line in lines for word in line.words)
        if hasattr(node, "words"):
            words = tuple(node.words)
            lines = (node,)
        text = " ".join(getattr(word, "text", "") for word in words) or getattr(node, "text", "")
        area = max(float(node.geometry.width * node.geometry.height), 1.0)
        page_scale = max(node.geometry.width, node.geometry.height, 1.0)
        occupied = sum(word.geometry.width * word.geometry.height for word in words)
        character_density = clamp(len(text.replace(" ", "")) * page_scale / area)
        word_density = clamp(len(words) * page_scale * 8.0 / area)
        line_density = clamp(len(lines) * page_scale * 12.0 / area)
        block_count = len(getattr(node, "blocks", ())) or (1 if hasattr(node, "lines") else 0)
        block_density = clamp(block_count * page_scale * 16.0 / area)
        whitespace = clamp(1.0 - occupied / area)
        return DensityMetrics(
            round(character_density, 4), round(word_density, 4), round(line_density, 4),
            round(whitespace, 4), round(block_density, 4),
        )

    def maps(self, document: ReceiptDocument, rows: int = 12, columns: int = 8) -> tuple[DensityMap, ...]:
        maps = []
        for page in document.pages:
            width, height = page.dimensions.width, page.dimensions.height
            words = iter_words(page)
            cells = []
            for row in range(rows):
                for column in range(columns):
                    box = BoundingBox(
                        column * width / columns, row * height / rows,
                        width / columns, height / rows,
                    )
                    members = tuple(word for word in words if self._intersects(box, word.geometry))
                    occupied = sum(
                        min(word.geometry.width, box.width) * min(word.geometry.height, box.height)
                        for word in members
                    )
                    cells.append(DensityCell(box, round(clamp(occupied / max(box.width * box.height, 1)), 4), tuple(word.id for word in members)))
            maps.append(DensityMap(page.id, rows, columns, tuple(cells)))
        return tuple(maps)

    @staticmethod
    def _intersects(left: BoundingBox, right: BoundingBox) -> bool:
        return left.x < right.right and right.x < left.right and left.y < right.bottom and right.y < left.bottom
