from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any

from .nodes import ReceiptDocument


class ReceiptDomSerializer:
    def to_dict(self, document: ReceiptDocument, *, debug: bool = False) -> dict[str, Any]:
        payload = self._value(document)
        if not debug:
            self._strip_debug(payload)
        return payload

    def to_json(self, document: ReceiptDocument, *, pretty: bool = False) -> str:
        return json.dumps(self.to_dict(document), indent=2 if pretty else None, sort_keys=pretty)

    def to_debug_json(self, document: ReceiptDocument, *, pretty: bool = True) -> str:
        return json.dumps(self.to_dict(document, debug=True), indent=2 if pretty else None, sort_keys=pretty)

    def pretty_print(self, document: ReceiptDocument) -> str:
        return self._tree_text(document)

    def tree_visualization(self, document: ReceiptDocument) -> dict[str, Any]:
        return self._tree_node(document, "ReceiptDocument")

    def graph_projection(self, document: ReceiptDocument) -> dict[str, list[dict[str, Any]]]:
        nodes, edges = [], []
        for node in document.walk():
            node_id = getattr(node, "id", document.id)
            nodes.append({"id": node_id, "type": node.__class__.__name__})
            relationships = getattr(node, "relationships", None)
            if relationships and relationships.parent_id:
                edges.append({"from": relationships.parent_id, "to": node_id, "type": "CONTAINS"})
            if relationships:
                for relation in ("above_id", "below_id", "left_id", "right_id"):
                    target = getattr(relationships, relation)
                    if target:
                        edges.append({"from": node_id, "to": target, "type": relation.removesuffix("_id").upper()})
        return {"nodes": nodes, "edges": edges}

    def _tree_node(self, node: Any, label: str | None = None) -> dict[str, Any]:
        return {
            "id": getattr(node, "id", ""),
            "type": label or node.__class__.__name__,
            "readingOrder": getattr(node, "reading_order", None),
            "geometry": self._value(getattr(node, "geometry", None)),
            "children": [self._tree_node(child) for child in getattr(node, "children", ())],
        }

    def _tree_text(self, document: ReceiptDocument) -> str:
        lines = []

        def visit(node: Any, prefix: str, last: bool, root: bool = False) -> None:
            connector = "" if root else ("└── " if last else "├── ")
            node_id = getattr(node, "id", "")
            suffix = f" [{node_id[:8]}]" if node_id else ""
            lines.append(f"{prefix}{connector}{node.__class__.__name__}{suffix}")
            children = getattr(node, "children", ())
            child_prefix = prefix + ("" if root else ("    " if last else "│   "))
            for index, child in enumerate(children):
                visit(child, child_prefix, index == len(children) - 1)

        visit(document, "", True, root=True)
        return "\n".join(lines)

    def _value(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Enum):
            return value.value
        if is_dataclass(value):
            return {field.name: self._value(getattr(value, field.name)) for field in fields(value)}
        if isinstance(value, tuple):
            if value and all(isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str) for item in value):
                return {item[0]: self._value(item[1]) for item in value}
            return [self._value(item) for item in value]
        if isinstance(value, list):
            return [self._value(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self._value(item) for key, item in value.items()}
        return str(value)

    def _strip_debug(self, value: Any) -> None:
        if isinstance(value, dict):
            value.pop("diagnostics", None)
            for item in value.values():
                self._strip_debug(item)
        elif isinstance(value, list):
            for item in value:
                self._strip_debug(item)
