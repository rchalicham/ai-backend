from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from services.receipt_dom import ReceiptDocument

from .metrics import coefficient_consistency, iter_lines, union_boxes
from .models import CandidateTable, VisualGroup, VisualGroupType


class ReceiptVisualGroupingEngine:
    def group(self, document: ReceiptDocument, tables: tuple[CandidateTable, ...]) -> tuple[VisualGroup, ...]:
        groups = []
        table_lines = {line_id: table for table in tables for line_id in table.row_line_ids}
        for page in document.pages:
            lines = sorted(iter_lines(page), key=lambda line: line.reading_order)
            current = []
            for line in lines:
                if line.id in table_lines:
                    if current:
                        groups.append(self._make_group(document.id, page.id, current, VisualGroupType.PARAGRAPH, len(groups)))
                        current = []
                    continue
                if not current or self._belongs(current[-1], line, page.dimensions.width):
                    current.append(line)
                else:
                    groups.append(self._make_group(document.id, page.id, current, self._type(current), len(groups)))
                    current = [line]
            if current:
                groups.append(self._make_group(document.id, page.id, current, self._type(current), len(groups)))
            for table in (table for table in tables if table.page_id == page.id):
                members = [line for line in lines if line.id in table.row_line_ids]
                groups.append(self._make_group(document.id, page.id, members, VisualGroupType.TABLE, len(groups)))
            for line in lines:
                if len(line.words) > 1:
                    groups.append(self._make_group(document.id, page.id, list(line.words), VisualGroupType.WORD, len(groups)))
        return tuple(groups)

    @staticmethod
    def _belongs(previous, current, page_width: float) -> bool:
        gap = current.geometry.y - previous.geometry.bottom
        indent_delta = abs(current.geometry.x - previous.geometry.x)
        return gap <= max(previous.geometry.height, current.geometry.height) * 1.8 and indent_delta <= page_width * 0.12

    @staticmethod
    def _type(lines: list) -> VisualGroupType:
        if len(lines) == 1:
            return VisualGroupType.CAPTION
        gaps = [lines[index + 1].geometry.y - lines[index].geometry.bottom for index in range(len(lines) - 1)]
        return VisualGroupType.PARAGRAPH if coefficient_consistency(gaps) >= 0.6 else VisualGroupType.MULTILINE

    @staticmethod
    def _make_group(document_id: str, page_id: str, nodes: list, kind: VisualGroupType, index: int) -> VisualGroup:
        return VisualGroup(
            id=str(uuid5(NAMESPACE_URL, f"{document_id}:{page_id}:visual:{index}:{kind.value}")),
            page_id=page_id,
            group_type=kind,
            node_ids=tuple(node.id for node in nodes),
            geometry=union_boxes(nodes),
            confidence=round(min(1.0, 0.55 + len(nodes) * 0.08), 4),
        )
