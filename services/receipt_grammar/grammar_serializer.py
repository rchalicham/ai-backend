from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any

from .models import GrammarDiagnostics, ReceiptGrammar, ReceiptGrammarContext


class ReceiptGrammarSerializer:
    def to_dict(self, value: Any) -> dict[str, Any]:
        payload = self._value(value)
        if not isinstance(payload, dict):
            raise TypeError("receipt_grammar_serialization_requires_object")
        return payload

    def to_json(self, value: Any, *, pretty: bool = False) -> str:
        return json.dumps(self.to_dict(value), indent=2 if pretty else None, sort_keys=pretty)

    def context_to_dict(self, context: ReceiptGrammarContext) -> dict[str, Any]:
        return self.to_dict(context)

    def grammar_to_dict(self, grammar: ReceiptGrammar) -> dict[str, Any]:
        return self.to_dict(grammar)

    def _value(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, GrammarDiagnostics):
            return {
                "valid": value.valid,
                "errors": self._value(value.errors),
                "warnings": self._value(value.warnings),
                "information": self._value(value.information),
            }
        if is_dataclass(value):
            return {item.name: self._value(getattr(value, item.name)) for item in fields(value)}
        if isinstance(value, tuple):
            if value and all(
                isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str)
                for item in value
            ):
                return {key: self._value(item) for key, item in value}
            return [self._value(item) for item in value]
        if isinstance(value, list):
            return [self._value(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self._value(item) for key, item in value.items()}
        return str(value)
