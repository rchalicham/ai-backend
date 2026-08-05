from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any


class DocumentFamilySerializer:
    def to_dict(self, value: Any) -> dict[str, Any]:
        return self._convert(value)

    def _convert(self, value):
        if isinstance(value, Enum): return value.value
        if is_dataclass(value): return {key: self._convert(item) for key, item in asdict(value).items()}
        if isinstance(value, tuple):
            if value and all(isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str) for item in value):
                return {item[0]: self._convert(item[1]) for item in value}
            return [self._convert(item) for item in value]
        if isinstance(value, list): return [self._convert(item) for item in value]
        if isinstance(value, dict): return {key: self._convert(item) for key, item in value.items()}
        return value
