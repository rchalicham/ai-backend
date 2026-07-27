from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from typing import Any

from .models import FeatureMetricGroup, ReceiptClassification


class ReceiptClassificationSerializer:
    def to_dict(self, classification: ReceiptClassification, *, debug: bool = False) -> dict[str, Any]:
        payload = self._value(classification)
        if not debug:
            payload.pop("diagnostics", None)
            for comparison in payload.get("comparisons", []):
                comparison.pop("feature_deltas", None)
        return payload

    def to_json(self, classification: ReceiptClassification, *, pretty: bool = False, debug: bool = False) -> str:
        return json.dumps(self.to_dict(classification, debug=debug), indent=2 if pretty else None, sort_keys=pretty)

    def to_debug_json(self, classification: ReceiptClassification) -> str:
        return self.to_json(classification, pretty=True, debug=True)

    def pretty_print(self, classification: ReceiptClassification) -> str:
        lines = [
            f"ReceiptClassification [{classification.document_id[:8]}]",
            f"├── Feature vector: v{classification.feature_vector.version}",
            f"├── Comparisons: {len(classification.comparisons)}",
            f"├── Candidates: {len(classification.candidates)}",
        ]
        for candidate in classification.candidates:
            lines.append(f"│   {candidate.rank}. {candidate.receipt_family} ({candidate.confidence:.3f})")
        lines.append(f"└── Learning suggestions: {len(classification.learning_suggestions)}")
        return "\n".join(lines)

    def graph_projection(self, classification: ReceiptClassification) -> dict[str, list[dict[str, Any]]]:
        nodes = [{"id": classification.document_id, "type": "ReceiptDocument"}]
        edges = []
        for candidate in classification.candidates:
            node_id = f"family:{candidate.receipt_family}"
            nodes.append({"id": node_id, "type": "ReceiptFamilyCandidate", "confidence": candidate.confidence})
            edges.append({"from": classification.document_id, "to": node_id, "type": "PHYSICALLY_RESEMBLES"})
        return {"nodes": nodes, "edges": edges}

    def _value(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, FeatureMetricGroup):
            return {key: item for key, item in value.metrics}
        if is_dataclass(value):
            return {field.name: self._value(getattr(value, field.name)) for field in fields(value)}
        if isinstance(value, tuple):
            if value and all(isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str) for item in value):
                return {key: self._value(item) for key, item in value}
            return [self._value(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self._value(item) for key, item in value.items()}
        return str(value)
