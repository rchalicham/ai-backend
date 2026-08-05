from dataclasses import fields, is_dataclass
from collections.abc import Mapping


def primitive(value):
    if is_dataclass(value): return {item.name: primitive(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping): return {key: primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)): return [primitive(item) for item in value]
    return value


class ReceiptProcessingSerializer:
    def to_dict(self, value):
        payload = primitive(value)
        return {
            "schemaVersion": "receipt-processing-experience-v1",
            "state": payload["state"], "summary": payload["summary"],
            "timeline": payload["timeline"], "explanation": payload["explanation"],
            "confidence": payload["confidence"], "diagnostics": payload["diagnostics"],
            "configuration": {"id": value.configuration_id, "version": value.configuration_version},
            "actions": payload["actions"],
            "labels": payload["labels"],
        }
