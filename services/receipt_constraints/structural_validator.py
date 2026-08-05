from __future__ import annotations

from typing import Any

from services.receipt_dom import ReceiptDocument
from services.receipt_structure import ReceiptPhysicalStructure

from .models import (
    ConstraintCandidate,
    ConstraintCategory,
    ConstraintEvaluation,
    ConstraintOutcome,
    ConstraintRule,
)


class StructuralConstraintValidator:
    def evaluate(
        self,
        rule: ConstraintRule,
        candidate: ConstraintCandidate,
        document: ReceiptDocument,
        structure: ReceiptPhysicalStructure,
        *,
        penalty: float,
    ) -> ConstraintEvaluation:
        values = dict(candidate.interpretation)
        parameters = dict(rule.parameters)
        passed, detail = self._evaluate(rule.rule_type, values, parameters, document, structure)
        outcome = ConstraintOutcome.PASS if passed else (
            ConstraintOutcome.VIOLATION if rule.required else ConstraintOutcome.WARNING
        )
        applied_penalty = 0.0 if passed else penalty if rule.required else penalty * 0.5
        return ConstraintEvaluation(
            rule.rule_id,
            candidate.candidate_id,
            rule.category,
            outcome,
            round(applied_penalty, 6),
            1.0 if passed else 0.0,
            detail,
        )

    def _evaluate(
        self,
        rule_type: str,
        values: dict[str, Any],
        parameters: dict[str, Any],
        document: ReceiptDocument,
        structure: ReceiptPhysicalStructure,
    ) -> tuple[bool, str]:
        sections = tuple(str(value) for value in values.get("sections", ()))
        subject = str(parameters.get("subject", ""))
        if rule_type in {"section_exists", "required"}:
            return subject in sections, f"Checked whether section '{subject}' is present."
        if rule_type in {"section_optional", "optional"}:
            return True, f"Section '{subject}' is optional."
        if rule_type == "section_order":
            expected = tuple(str(value) for value in parameters.get("order", ()))
            observed = [value for value in sections if value in expected]
            return observed == [value for value in expected if value in observed], (
                f"Compared observed section order with {', '.join(expected)}."
            )
        if rule_type == "section_repetition":
            minimum = int(parameters.get("minimum", 1))
            maximum = parameters.get("maximum")
            count = sections.count(subject)
            passed = count >= minimum and (maximum is None or count <= int(maximum))
            return passed, f"Section '{subject}' occurred {count} times; expected {minimum}..{maximum}."
        if rule_type == "nested_structure":
            parent = str(parameters.get("parent", ""))
            child = str(parameters.get("child", ""))
            nested = values.get("nested_sections", ())
            pairs = {tuple(item) for item in nested if isinstance(item, (tuple, list)) and len(item) == 2}
            return (parent, child) in pairs, f"Checked whether '{child}' is nested under '{parent}'."
        if rule_type == "receipt_boundaries":
            page_count = len(document.pages)
            valid_regions = all(
                annotation.geometry.x >= 0
                and annotation.geometry.y >= 0
                and annotation.geometry.width >= 0
                and annotation.geometry.height >= 0
                for annotation in structure.region_annotations
            )
            return page_count > 0 and valid_regions, "Checked page existence and non-negative physical regions."
        if rule_type == "cardinality":
            values_field = str(parameters.get("field", subject))
            collection = values.get(values_field, ())
            count = len(collection) if isinstance(collection, (tuple, list)) else int(collection or 0)
            minimum = int(parameters.get("minimum", 0))
            maximum = parameters.get("maximum")
            return count >= minimum and (maximum is None or count <= int(maximum)), (
                f"Cardinality for '{values_field}' is {count}; expected {minimum}..{maximum}."
            )
        return False, f"Structural rule type '{rule_type}' is not supported."

