from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .models import (
    ConstraintCategory,
    ConstraintGroup,
    ConstraintOutcome,
    ConstraintPenalty,
    ConstraintRule,
    ConstraintVersion,
    ConstraintWeight,
    ReceiptConstraint,
)


class ReceiptConstraintLoader:
    def from_json(self, payload: str) -> ReceiptConstraint:
        value = json.loads(payload)
        if not isinstance(value, dict):
            raise ValueError("receipt_constraint_definition_must_be_an_object")
        return self.from_dict(value)

    def from_file(self, path: str | Path) -> ReceiptConstraint:
        return self.from_json(Path(path).read_text(encoding="utf-8"))

    def from_dict(self, payload: Mapping[str, Any]) -> ReceiptConstraint:
        version = self._mapping(payload.get("version"))
        return ReceiptConstraint(
            constraint_set_id=str(payload.get("constraint_set_id") or payload.get("constraintSetId") or ""),
            receipt_family=str(payload.get("receipt_family") or payload.get("receiptFamily") or ""),
            name=str(payload.get("name") or ""),
            version=ConstraintVersion(
                entity_version=int(version.get("entity_version") or version.get("entityVersion") or 1),
                schema_version=str(version.get("schema_version") or version.get("schemaVersion") or "receipt-constraints-v1"),
                status=str(version.get("status") or "active"),
                created_at=str(version.get("created_at") or version.get("createdAt") or ConstraintVersion().created_at),
                updated_at=str(version.get("updated_at") or version.get("updatedAt") or ConstraintVersion().updated_at),
                supersedes_version=self._optional_int(
                    version.get("supersedes_version", version.get("supersedesVersion")),
                ),
            ),
            rules=tuple(self._rule(value) for value in self._mappings(payload.get("rules"))),
            groups=tuple(self._group(value) for value in self._mappings(payload.get("groups"))),
            weights=tuple(self._weight(value) for value in self._mappings(payload.get("weights"))),
            penalties=tuple(self._penalty(value) for value in self._mappings(payload.get("penalties"))),
            dependencies=self._strings(payload.get("dependencies")),
            description=str(payload.get("description") or ""),
        )

    def _rule(self, value: Mapping[str, Any]) -> ConstraintRule:
        return ConstraintRule(
            rule_id=str(value.get("rule_id") or value.get("ruleId") or ""),
            category=ConstraintCategory(str(value.get("category") or "unknown")),
            rule_type=str(value.get("rule_type") or value.get("ruleType") or ""),
            description=str(value.get("description") or ""),
            weight_id=str(value.get("weight_id") or value.get("weightId") or ""),
            penalty_id=str(value.get("penalty_id") or value.get("penaltyId") or ""),
            dependency_ids=self._strings(value.get("dependency_ids", value.get("dependencyIds"))),
            parameters=self._pairs(value.get("parameters")),
            required=bool(value.get("required", True)),
        )

    def _group(self, value: Mapping[str, Any]) -> ConstraintGroup:
        return ConstraintGroup(
            group_id=str(value.get("group_id") or value.get("groupId") or ""),
            name=str(value.get("name") or ""),
            rule_ids=self._strings(value.get("rule_ids", value.get("ruleIds"))),
            aggregation=str(value.get("aggregation") or "all"),
            required=bool(value.get("required", True)),
        )

    def _weight(self, value: Mapping[str, Any]) -> ConstraintWeight:
        return ConstraintWeight(
            weight_id=str(value.get("weight_id") or value.get("weightId") or ""),
            value=float(value.get("value", 0.0)),
            category=ConstraintCategory(str(value.get("category") or "unknown")),
        )

    def _penalty(self, value: Mapping[str, Any]) -> ConstraintPenalty:
        return ConstraintPenalty(
            penalty_id=str(value.get("penalty_id") or value.get("penaltyId") or ""),
            value=float(value.get("value", 0.0)),
            outcome=ConstraintOutcome(str(value.get("outcome") or "violation")),
        )

    def _mapping(self, value: Any) -> Mapping[str, Any]:
        return value if isinstance(value, Mapping) else {}

    def _mappings(self, value: Any) -> tuple[Mapping[str, Any], ...]:
        return tuple(item for item in (value or ()) if isinstance(item, Mapping))

    def _strings(self, value: Any) -> tuple[str, ...]:
        return tuple(str(item) for item in (value or ()))

    def _pairs(self, value: Any) -> tuple[tuple[str, Any], ...]:
        if isinstance(value, Mapping):
            return tuple((str(key), item) for key, item in value.items())
        return tuple((str(item[0]), item[1]) for item in (value or ()) if len(item) == 2)

    def _optional_int(self, value: Any) -> int | None:
        return None if value is None else int(value)

