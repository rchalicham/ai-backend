from __future__ import annotations

from dataclasses import replace

from .models import (
    ConstraintRepository,
    ConstraintVersionComparison,
    ReceiptConstraint,
    utc_now,
)


class ReceiptConstraintRepository:
    """Append-only constraint-set repository keyed by Receipt Family and version."""

    def __init__(self) -> None:
        self._sets: dict[str, list[ReceiptConstraint]] = {}

    def load_constraints(self, receipt_family: str, version: int | None = None) -> ReceiptConstraint | None:
        history = self._sets.get(receipt_family, ())
        if version is None:
            return next((item for item in reversed(history) if item.version.status == "active"), None)
        return next((item for item in history if item.version.entity_version == version), None)

    def save_constraints(
        self,
        constraint_set: ReceiptConstraint,
        expected_version: int | None = None,
    ) -> ReceiptConstraint:
        family = constraint_set.receipt_family
        if not family:
            raise ValueError("receipt_constraints_require_receipt_family")
        history = self._sets.setdefault(family, [])
        if history:
            raise ValueError("receipt_constraints_already_exist_use_version_constraints")
        if expected_version not in {None, 0}:
            raise ValueError("receipt_constraints_version_conflict")
        saved = replace(
            constraint_set,
            version=replace(
                constraint_set.version,
                entity_version=1,
                status="active",
                updated_at=utc_now(),
                supersedes_version=None,
            ),
        )
        history.append(saved)
        return saved

    def version_constraints(
        self,
        constraint_set: ReceiptConstraint,
        expected_version: int | None = None,
    ) -> ReceiptConstraint:
        family = constraint_set.receipt_family
        history = self._sets.setdefault(family, [])
        current = history[-1] if history else None
        current_version = current.version.entity_version if current else 0
        if expected_version is not None and expected_version != current_version:
            raise ValueError("receipt_constraints_version_conflict")
        if current and current.constraint_set_id != constraint_set.constraint_set_id:
            raise ValueError("receipt_constraints_identity_conflict")
        saved = replace(
            constraint_set,
            version=replace(
                constraint_set.version,
                entity_version=current_version + 1,
                status="active",
                created_at=current.version.created_at if current else constraint_set.version.created_at,
                updated_at=utc_now(),
                supersedes_version=current_version or None,
            ),
        )
        history.append(saved)
        return saved

    def archive_constraints(self, receipt_family: str, version: int | None = None) -> ReceiptConstraint:
        history = self._sets.get(receipt_family, [])
        value = self.load_constraints(receipt_family, version)
        if value is None:
            raise KeyError("receipt_constraints_not_found")
        archived = replace(value, version=replace(value.version, status="archived", updated_at=utc_now()))
        history[history.index(value)] = archived
        return archived

    def list_constraint_sets(
        self,
        receipt_family: str = "",
        include_archived: bool = False,
    ) -> tuple[ReceiptConstraint, ...]:
        values = (
            tuple(self._sets.get(receipt_family, ()))
            if receipt_family
            else tuple(item for history in self._sets.values() for item in history)
        )
        return values if include_archived else tuple(
            item for item in values if item.version.status == "active"
        )

    def compare_constraint_versions(
        self,
        receipt_family: str,
        from_version: int,
        to_version: int,
    ) -> ConstraintVersionComparison:
        before = self.load_constraints(receipt_family, from_version)
        after = self.load_constraints(receipt_family, to_version)
        if before is None or after is None:
            raise KeyError("receipt_constraints_version_not_found")
        before_rules = {rule.rule_id: rule for rule in before.rules}
        after_rules = {rule.rule_id: rule for rule in after.rules}
        before_weights = {weight.weight_id: weight for weight in before.weights}
        after_weights = {weight.weight_id: weight for weight in after.weights}
        return ConstraintVersionComparison(
            constraint_set_id=after.constraint_set_id,
            from_version=from_version,
            to_version=to_version,
            added_rules=tuple(sorted(set(after_rules) - set(before_rules))),
            removed_rules=tuple(sorted(set(before_rules) - set(after_rules))),
            changed_rules=tuple(sorted(
                key for key in set(before_rules) & set(after_rules)
                if before_rules[key] != after_rules[key]
            )),
            changed_weights=tuple(sorted(
                key for key in set(before_weights) | set(after_weights)
                if before_weights.get(key) != after_weights.get(key)
            )),
        )

    def index(self) -> ConstraintRepository:
        latest = tuple(
            (family, history[-1].version.entity_version)
            for family, history in sorted(self._sets.items())
            if history
        )
        return ConstraintRepository(
            receipt_families=tuple(family for family, _ in latest),
            constraint_set_ids=tuple(
                self._sets[family][-1].constraint_set_id for family, _ in latest
            ),
            versions=latest,
        )

    loadConstraints = load_constraints
    saveConstraints = save_constraints
    versionConstraints = version_constraints
    archiveConstraints = archive_constraints
    listConstraintSets = list_constraint_sets
    compareConstraintVersions = compare_constraint_versions

