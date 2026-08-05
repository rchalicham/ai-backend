from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any


class ExpenseIntelligenceSerializer:
    def to_dict(self, value: Any) -> dict[str, Any]:
        result = self._value(value)
        if not isinstance(result, dict):
            raise TypeError("expense_serialization_requires_object")
        return result

    def to_json(self, value: Any, *, pretty=False):
        return json.dumps(self.to_dict(value), indent=2 if pretty else None, sort_keys=pretty)

    def _value(self, value):
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Enum):
            return value.value
        if is_dataclass(value):
            result = {item.name: self._value(getattr(value, item.name)) for item in fields(value)}
            if value.__class__.__name__ == "ExpenseDiagnostics":
                result["valid"] = value.valid
            return result
        if isinstance(value, tuple):
            if value and all(isinstance(x, tuple) and len(x) == 2 and isinstance(x[0], str)
                             for x in value):
                return {key: self._value(item) for key, item in value}
            return [self._value(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self._value(item) for key, item in value.items()}
        return str(value)
