from __future__ import annotations

import re

from services.receipt_dom import ReceiptDocument, ReceiptLine

from .models import FamilyEvidence, KeyValueRelationship, SemanticZone
from .semantic_zones import document_lines


class KeyValueRelationshipEngine:
    INLINE = re.compile(r"^\s*([A-Za-z][A-Za-z #/_-]{1,32}?):\s*(\S.+)$")
    MONEY = re.compile(r"(?:\$\s*)?-?\d+[.,]\d{2}\b")

    def reconstruct(self, document: ReceiptDocument, zones: tuple[SemanticZone, ...], labels: tuple[str, ...] = ()) -> tuple[KeyValueRelationship, ...]:
        lines = document_lines(document)
        zone_by_node = {node_id: zone.zone_id for zone in zones for node_id in zone.node_ids}
        results: list[KeyValueRelationship] = []
        label_set = {label.lower().rstrip(":") for label in labels}
        for index, line in enumerate(lines):
            inline = self.INLINE.match(line.text)
            if inline and inline.group(2).strip():
                results.append(self._relationship(line, line, inline.group(1), inline.group(2), 0.93, "same_line", zone_by_node))
                continue
            key = line.text.strip().rstrip(":")
            is_key = line.text.rstrip().endswith(":") or key.lower() in label_set
            if not is_key and not any(key.lower().startswith(label) for label in label_set):
                continue
            candidates = [other for other in lines if other.id != line.id and self._same_row(line, other) and other.geometry.x >= line.geometry.x]
            if not candidates and index + 1 < len(lines):
                candidates = [lines[index + 1]]
            if candidates:
                value = min(candidates, key=lambda other: (abs(other.geometry.y - line.geometry.y), abs(other.geometry.x - (line.geometry.x + line.geometry.width))))
                confidence = 0.9 if self._same_row(line, value) else 0.68
                results.append(self._relationship(line, value, key, value.text.strip(), confidence, "geometry_nearest_neighbor", zone_by_node))
        return tuple(self._dedupe(results))

    def _same_row(self, left: ReceiptLine, right: ReceiptLine) -> bool:
        overlap = max(0.0, min(left.geometry.y + left.geometry.height, right.geometry.y + right.geometry.height) - max(left.geometry.y, right.geometry.y))
        return overlap / max(min(left.geometry.height, right.geometry.height), 1.0) >= 0.45

    def _relationship(self, key_line, value_line, key, value, confidence, strategy, zones):
        evidence = FamilyEvidence("geometry", f"{key_line.id}->{value_line.id}", confidence, strategy, (key_line.id, value_line.id))
        return KeyValueRelationship(
            f"kv-{key_line.id}-{value_line.id}", key.strip(), value.strip(), key_line.id, value_line.id,
            confidence, strategy, zones.get(key_line.id, ""), (evidence,),
        )

    def _dedupe(self, values):
        seen = set()
        for value in values:
            key = (value.key.lower(), value.value.lower())
            if key not in seen:
                seen.add(key)
                yield value
