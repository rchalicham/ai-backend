from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any

from .models import ReceiptPhysicalStructure


class ReceiptStructureSerializer:
    def to_dict(self, structure: ReceiptPhysicalStructure, *, debug: bool = False) -> dict[str, Any]:
        payload = self._value(structure)
        if not debug:
            payload.pop("diagnostics", None)
            for density_map in payload.get("density_maps", []):
                for cell in density_map.get("cells", []):
                    cell.pop("node_ids", None)
        return payload

    def to_json(self, structure: ReceiptPhysicalStructure, *, pretty: bool = False, debug: bool = False) -> str:
        return json.dumps(self.to_dict(structure, debug=debug), indent=2 if pretty else None, sort_keys=pretty)

    def to_debug_json(self, structure: ReceiptPhysicalStructure) -> str:
        return self.to_json(structure, pretty=True, debug=True)

    def pretty_print(self, structure: ReceiptPhysicalStructure) -> str:
        return "\n".join((
            f"ReceiptPhysicalStructure [{structure.document_id[:8]}]",
            f"├── Regions: {len(structure.region_annotations)}",
            f"├── Blocks: {len(structure.block_annotations)}",
            f"├── Candidate tables: {len(structure.candidate_tables)}",
            f"├── Visual groups: {len(structure.visual_groups)}",
            f"├── Alignment groups: {len(structure.alignment_groups)}",
            f"├── Whitespace zones: {len(structure.whitespace_zones)}",
            f"└── Density maps: {len(structure.density_maps)}",
        ))

    def graph_projection(self, structure: ReceiptPhysicalStructure) -> dict[str, list[dict[str, Any]]]:
        nodes = [{"id": structure.document_id, "type": "ReceiptDocument"}]
        edges = []
        collections = (
            ("RegionAnnotation", structure.region_annotations),
            ("BlockAnnotation", structure.block_annotations),
            ("CandidateTable", structure.candidate_tables),
            ("AlignmentGroup", structure.alignment_groups),
            ("VisualGroup", structure.visual_groups),
            ("WhitespaceZone", structure.whitespace_zones),
        )
        for kind, values in collections:
            for index, value in enumerate(values):
                identifier = getattr(value, "id", f"{kind}:{getattr(value, 'node_id', index)}")
                nodes.append({"id": identifier, "type": kind})
                edges.append({"from": structure.document_id, "to": identifier, "type": "HAS_PHYSICAL_ANNOTATION"})
                target = getattr(value, "node_id", None)
                if target:
                    edges.append({"from": identifier, "to": target, "type": "ANNOTATES"})
        return {"nodes": nodes, "edges": edges}

    def _value(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Enum):
            return value.value
        if is_dataclass(value):
            return {field.name: self._value(getattr(value, field.name)) for field in fields(value)}
        if isinstance(value, tuple):
            if value and all(isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str) for item in value):
                return {key: self._value(item) for key, item in value}
            return [self._value(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self._value(item) for key, item in value.items()}
        return str(value)
