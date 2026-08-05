from __future__ import annotations

from dataclasses import asdict
from enum import Enum
from typing import Any

from .models import ReceiptIntelligenceSnapshot, thaw


def _serialize(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return thaw(value)
    if hasattr(value, "__dataclass_fields__"):
        return {key: _serialize(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    return value


class SnapshotSerializer:
    def to_dict(self, snapshot: ReceiptIntelligenceSnapshot) -> dict[str, Any]:
        return _serialize(snapshot)

    serialize = to_dict

