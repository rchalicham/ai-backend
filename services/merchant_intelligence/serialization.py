from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from typing import Any, TypeVar, get_args, get_origin, get_type_hints

from .models import MerchantBlueprint, MerchantIntelligenceContext

T = TypeVar("T")


class MerchantIntelligenceSerializer:
    def to_dict(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if is_dataclass(value):
            return {field.name: self.to_dict(getattr(value, field.name)) for field in fields(value)}
        if isinstance(value, tuple):
            if value and all(isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str) for item in value):
                return {key: self.to_dict(item) for key, item in value}
            return [self.to_dict(item) for item in value]
        if isinstance(value, list):
            return [self.to_dict(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self.to_dict(item) for key, item in value.items()}
        return str(value)

    def to_json(self, value: Any, *, pretty: bool = False) -> str:
        return json.dumps(self.to_dict(value), indent=2 if pretty else None, sort_keys=pretty)

    def blueprint_from_dict(self, payload: dict[str, Any]) -> MerchantBlueprint:
        return self._construct(MerchantBlueprint, payload)

    def context_to_dict(self, context: MerchantIntelligenceContext) -> dict[str, Any]:
        return self.to_dict(context)

    def _construct(self, target: type[T], payload: Any) -> T:
        if payload is None:
            return payload
        origin = get_origin(target)
        args = get_args(target)
        if origin is tuple:
            subtype = args[0] if args else Any
            if isinstance(payload, dict) and get_origin(subtype) is tuple and get_args(subtype) == (str, Any):
                return tuple((str(key), value) for key, value in payload.items())  # type: ignore[return-value]
            if get_origin(subtype) is tuple and isinstance(payload, (list, tuple)):
                return tuple(tuple(item) for item in payload)  # type: ignore[return-value]
            return tuple(self._construct(subtype, item) for item in payload)  # type: ignore[return-value]
        if origin is not None and type(None) in args:
            subtype = next(arg for arg in args if arg is not type(None))
            return self._construct(subtype, payload)
        if is_dataclass(target):
            hints = get_type_hints(target)
            values = {}
            for field in fields(target):
                if field.name in payload:
                    annotation = hints.get(field.name, field.type)
                    values[field.name] = self._construct(annotation, payload[field.name])
            return target(**values)
        return payload
