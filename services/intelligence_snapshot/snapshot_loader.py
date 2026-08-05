from __future__ import annotations

from .models import *


class SnapshotLoader:
    def from_dict(self, value):
        value = dict(value or {})
        value.pop("_id", None)
        header_data = value.get("header") or {}
        version = SnapshotVersion(**(header_data.get("version") or {"number": 1}))
        header = SnapshotHeader(**{**header_data, "version": version})
        metadata_data = dict(value.get("metadata") or {})
        model_versions = metadata_data.get("model_versions") or ()
        metadata_data["model_versions"] = tuple(model_versions.items()) if isinstance(model_versions, dict) else tuple(tuple(item) for item in model_versions)
        metadata = SnapshotMetadata(**metadata_data)
        context = SnapshotContext(**(value.get("context") or {}))
        references = tuple(SnapshotReference(**item) for item in value.get("references") or ())
        confidence_data = dict(value.get("confidence") or {})
        components = confidence_data.get("components") or ()
        confidence_data["components"] = tuple(components.items()) if isinstance(components, dict) else tuple(tuple(item) for item in components)
        confidence = SnapshotConfidence(**confidence_data)
        explanations = tuple(SnapshotExplanation(**item) for item in value.get("explanations") or ())
        diagnostics = SnapshotDiagnostics(**(value.get("diagnostics") or {}))
        summary = SnapshotSummary(**(value.get("summary") or {}))
        return ReceiptIntelligenceSnapshot(header, metadata, context, references, confidence, explanations, diagnostics, summary, value.get("schema_version", "receipt-intelligence-snapshot-v1"))

    load = from_dict
