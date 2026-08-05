from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any


class EnterpriseGraphSerializer:
    def to_dict(self, value: Any) -> dict[str, Any]:
        payload = self._value(value)
        if not isinstance(payload, dict):
            raise TypeError("enterprise_graph_serialization_requires_object")
        return payload

    def to_json(self, value: Any, *, pretty: bool = False) -> str:
        return json.dumps(self.to_dict(value), indent=2 if pretty else None, sort_keys=pretty)

    def _value(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Enum):
            return value.value
        if is_dataclass(value):
            payload = {item.name: self._value(getattr(value, item.name)) for item in fields(value)}
            if value.__class__.__name__ == "GraphDiagnostics":
                payload["valid"] = value.valid
            return payload
        if isinstance(value, tuple):
            if value and all(
                isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str)
                for item in value
            ):
                return {key: self._value(item) for key, item in value}
            return [self._value(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self._value(item) for key, item in value.items()}
        return str(value)

