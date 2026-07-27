from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from services.receipt_dom import ReceiptDocument

from .metrics import coefficient_consistency, iter_lines, union_boxes
from .models import AlignmentType, CandidateTable, TableColumn


class ReceiptTableDetector:
    """Detects repeated geometric row/column structure without assigning meaning."""

    def detect(self, document: ReceiptDocument) -> tuple[CandidateTable, ...]:
        candidates = []
        for page in document.pages:
            lines = sorted(iter_lines(page), key=lambda line: line.reading_order)
            runs = self._row_runs(lines)
            for run_index, run in enumerate(runs):
                columns = self._columns(run, page.dimensions.width)
                if len(run) < 3 or len(columns) < 2:
                    continue
                gaps = [run[index + 1].geometry.y - run[index].geometry.bottom for index in range(len(run) - 1)]
                heights = [line.geometry.height for line in run]
                spacing = coefficient_consistency(gaps)
                height_consistency = coefficient_consistency(heights)
                occupancy = sum(1 for line in run if len(line.words) >= 2) / len(run)
                confidence = min(1.0, spacing * 0.3 + height_consistency * 0.25 + occupancy * 0.25 + min(len(columns), 4) * 0.05)
                if confidence < 0.5:
                    continue
                block_ids = tuple(dict.fromkeys(line.relationships.parent_id for line in run if line.relationships.parent_id))
                candidates.append(CandidateTable(
                    id=str(uuid5(NAMESPACE_URL, f"{document.id}:{page.id}:table:{run_index}")),
                    page_id=page.id,
                    block_ids=block_ids,
                    row_line_ids=tuple(line.id for line in run),
                    columns=columns,
                    geometry=union_boxes(run),
                    confidence=round(confidence, 4),
                    row_spacing_consistency=round(spacing, 4),
                    row_height_consistency=round(height_consistency, 4),
                ))
        return tuple(candidates)

    def _row_runs(self, lines: list) -> list[list]:
        if not lines:
            return []
        heights = [max(line.geometry.height, 1) for line in lines]
        median_height = sorted(heights)[len(heights) // 2]
        runs, current = [], [lines[0]]
        for line in lines[1:]:
            gap = line.geometry.y - current[-1].geometry.bottom
            if gap <= median_height * 2.2:
                current.append(line)
            else:
                if len(current) >= 3:
                    runs.append(current)
                current = [line]
        if len(current) >= 3:
            runs.append(current)
        return runs

    def _columns(self, lines: list, page_width: float) -> tuple[TableColumn, ...]:
        tolerance = max(8.0, page_width * 0.035)
        clusters: list[list] = []
        for line in lines:
            for word in line.words:
                cluster = next((values for values in clusters if abs(sum(item.geometry.x for item in values) / len(values) - word.geometry.x) <= tolerance), None)
                if cluster is None:
                    clusters.append([word])
                else:
                    cluster.append(word)
        required = max(2, round(len(lines) * 0.45))
        columns = []
        for values in sorted((values for values in clusters if len(values) >= required), key=lambda values: sum(word.geometry.x for word in values) / len(values)):
            left = sum(word.geometry.x for word in values) / len(values)
            width = sum(word.geometry.width for word in values) / len(values)
            right_spread = max(word.geometry.right for word in values) - min(word.geometry.right for word in values)
            left_spread = max(word.geometry.x for word in values) - min(word.geometry.x for word in values)
            numeric_ratio = sum(1 for word in values if self._numeric_shape(word.text)) / len(values)
            alignment = AlignmentType.RIGHT if numeric_ratio >= 0.6 and right_spread <= left_spread + tolerance else AlignmentType.LEFT
            columns.append(TableColumn(len(columns), round(left, 2), round(width, 2), alignment, round(min(1.0, len(values) / len(lines)), 4)))
        return tuple(columns)

    @staticmethod
    def _numeric_shape(text: str) -> bool:
        compact = "".join(character for character in str(text) if character.isdigit() or character in ".,-+")
        return bool(compact) and sum(character.isdigit() for character in compact) >= max(1, len(compact) - 2)
