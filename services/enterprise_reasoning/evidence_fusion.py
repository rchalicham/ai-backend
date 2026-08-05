from __future__ import annotations

import hashlib
from typing import Any

from .models import ReasoningEvidence


def thaw(value: Any) -> Any:
    if isinstance(value, tuple):
        if value and all(isinstance(x, tuple) and len(x) == 2 for x in value):
            return {str(key): thaw(item) for key, item in value}
        return [thaw(item) for item in value]
    return value


class EvidenceFusionEngine:
    def fuse(self, collected: tuple[tuple[str, Any], ...]) -> tuple[ReasoningEvidence, ...]:
        evidence = []
        for tool, frozen in collected:
            payload = thaw(frozen)
            if payload in (None, {}, []):
                continue
            confidence = self._confidence(payload)
            identity = hashlib.sha256(f"{tool}|{repr(payload)}".encode()).hexdigest()[:24]
            evidence.append(ReasoningEvidence(
                f"reasoning-evidence:{identity}", tool, self._type(tool), payload,
                confidence, confidence,
                tuple(self._find(payload, ("entity_id", "subject_id"))),
                tuple(self._find(payload, ("document_id",))),
                tuple(self._find(payload, ("provenance", "evidence_references"))),
            ))
        return tuple(evidence)

    def _confidence(self, value: Any) -> float:
        found = self._numbers(value, {
            "overall", "normalized", "confidence", "score", "proposed",
            "overall_compliance",
        })
        return round(sum(found) / len(found), 6) if found else 0.5

    def _numbers(self, value, keys):
        values = []
        if isinstance(value, dict):
            for key, item in value.items():
                if key in keys and isinstance(item, (int, float)) and not isinstance(item, bool):
                    values.append(max(0.0, min(1.0, float(item))))
                else:
                    values.extend(self._numbers(item, keys))
        elif isinstance(value, list):
            for item in value:
                values.extend(self._numbers(item, keys))
        return values

    def _find(self, value, keys):
        found = []
        if isinstance(value, dict):
            for key, item in value.items():
                if key in keys:
                    if isinstance(item, str):
                        found.append(item)
                    elif isinstance(item, list):
                        found.extend(str(x) for x in item if isinstance(x, str))
                found.extend(self._find(item, keys))
        elif isinstance(value, list):
            for item in value:
                found.extend(self._find(item, keys))
        return tuple(dict.fromkeys(found))

    @staticmethod
    def _type(tool):
        return {
            "constraint_solver": "validated_constraint_context",
            "product_intelligence": "canonical_product_context",
            "enterprise_graph": "semantic_graph_context",
            "cross_document_intelligence": "historical_context",
            "enterprise_learning": "governed_learning_context",
            "merchant_knowledge": "approved_merchant_context",
        }.get(tool, "enterprise_context")
