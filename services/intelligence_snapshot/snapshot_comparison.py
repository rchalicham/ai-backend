from __future__ import annotations

from .models import SnapshotComparison, thaw


def _diff(before, after):
    left, right = thaw(before), thaw(after)
    if left == right: return ()
    if isinstance(left, dict) and isinstance(right, dict):
        return tuple((key, left.get(key), right.get(key)) for key in sorted(set(left) | set(right)) if left.get(key) != right.get(key))
    return (("value", left, right),)


class SnapshotComparisonEngine:
    def compare(self, before, after):
        if before.header.receipt_id != after.header.receipt_id:
            raise ValueError("snapshot_receipt_mismatch")
        return SnapshotComparison(
            before.header.receipt_id, before.header.snapshot_id, after.header.snapshot_id,
            version_changes=_diff(before.metadata, after.metadata),
            field_changes=_diff(before.context.business_projection, after.context.business_projection),
            confidence_changes=_diff(before.confidence, after.confidence),
            reasoning_changes=_diff(before.context.enterprise_reasoning, after.context.enterprise_reasoning),
            knowledge_changes=_diff(before.references, after.references),
            projection_changes=_diff(before.context.business_projection, after.context.business_projection),
            grammar_changes=_diff(before.context.grammar, after.context.grammar),
            constraint_changes=_diff(before.context.constraints, after.context.constraints),
            learning_changes=_diff(
                tuple(item for item in before.references if item.artifact_type == "enterprise_learning"),
                tuple(item for item in after.references if item.artifact_type == "enterprise_learning"),
            ),
        )

