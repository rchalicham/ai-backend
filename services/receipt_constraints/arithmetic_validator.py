from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from .models import (
    ConstraintCandidate,
    ConstraintCategory,
    ConstraintEvaluation,
    ConstraintOutcome,
    ConstraintRule,
)


class ArithmeticConstraintValidator:
    """Evaluates supplied numeric hypotheses without extracting or changing values."""

    def evaluate(
        self,
        rule: ConstraintRule,
        candidate: ConstraintCandidate,
        *,
        penalty: float,
    ) -> ConstraintEvaluation:
        values = dict(candidate.interpretation)
        parameters = dict(rule.parameters)
        tolerance = self._decimal(parameters.get("tolerance", "0.01"))
        precision = int(parameters.get("currency_precision", 2))
        passed, detail = self._evaluate(rule.rule_type, values, parameters, tolerance, precision)
        if passed is None:
            outcome = ConstraintOutcome.WARNING
            score = 0.5
            applied_penalty = penalty * 0.5
        elif passed:
            outcome = ConstraintOutcome.PASS
            score = 1.0
            applied_penalty = 0.0
        else:
            outcome = ConstraintOutcome.VIOLATION
            score = 0.0
            applied_penalty = penalty
        return ConstraintEvaluation(
            rule_id=rule.rule_id,
            candidate_id=candidate.candidate_id,
            category=ConstraintCategory.ARITHMETIC,
            outcome=outcome,
            penalty=round(applied_penalty, 6),
            score=score,
            explanation=detail,
        )

    def _evaluate(
        self,
        rule_type: str,
        values: dict[str, Any],
        parameters: dict[str, Any],
        tolerance: Decimal,
        precision: int,
    ) -> tuple[bool | None, str]:
        if rule_type == "subtotal_tax_total":
            fields = self._fields(parameters, ("subtotal", "tax", "total"))
            numbers = self._numbers(values, fields)
            if numbers is None:
                return None, f"Candidate does not supply all arithmetic inputs: {', '.join(fields)}."
            subtotal, tax, total = numbers
            return self._equal(subtotal + tax, total, tolerance, precision), (
                f"Evaluated {fields[0]} + {fields[1]} = {fields[2]} within tolerance {tolerance}."
            )
        if rule_type == "subtotal_discount_tax_total":
            fields = self._fields(parameters, ("subtotal", "discount", "tax", "total"))
            numbers = self._numbers(values, fields)
            if numbers is None:
                return None, f"Candidate does not supply all arithmetic inputs: {', '.join(fields)}."
            subtotal, discount, tax, total = numbers
            return self._equal(subtotal - discount + tax, total, tolerance, precision), (
                f"Evaluated {fields[0]} - {fields[1]} + {fields[2]} = {fields[3]} within tolerance {tolerance}."
            )
        if rule_type == "quantity_unit_line_total":
            fields = self._fields(parameters, ("quantity", "unit_price", "line_total"))
            lines = values.get(str(parameters.get("lines_field", "lines")))
            if not isinstance(lines, (tuple, list)) or not lines:
                numbers = self._numbers(values, fields)
                if numbers is None:
                    return None, "Candidate supplies no line arithmetic hypotheses."
                lines = (dict(zip(fields, numbers)),)
                already_decimal = True
            else:
                already_decimal = False
            for index, line in enumerate(lines):
                mapping = dict(line) if not isinstance(line, dict) else line
                numbers = (
                    tuple(mapping[field] for field in fields)
                    if already_decimal
                    else self._numbers(mapping, fields)
                )
                if numbers is None:
                    return None, f"Line {index + 1} lacks quantity, unit price, or line total."
                quantity, unit_price, line_total = numbers
                if not self._equal(quantity * unit_price, line_total, tolerance, precision):
                    return False, f"Line {index + 1} does not satisfy quantity × unit price = line total."
            return True, "All supplied line hypotheses satisfy quantity × unit price = line total."
        if rule_type == "multiple_taxes":
            subtotal_field, total_field = self._fields(parameters, ("subtotal", "total"))
            taxes_field = str(parameters.get("taxes_field", "taxes"))
            subtotal = self._decimal(values.get(subtotal_field))
            total = self._decimal(values.get(total_field))
            taxes = values.get(taxes_field)
            if subtotal is None or total is None or not isinstance(taxes, (tuple, list)):
                return None, "Candidate does not supply subtotal, total, and multiple tax hypotheses."
            tax_values = [self._decimal(value) for value in taxes]
            if any(value is None for value in tax_values):
                return None, "At least one supplied tax hypothesis is non-numeric."
            expected = subtotal + sum((value for value in tax_values if value is not None), Decimal("0"))
            return self._equal(expected, total, tolerance, precision), (
                f"Evaluated subtotal plus {len(tax_values)} supplied taxes against total."
            )
        return None, f"Arithmetic rule type '{rule_type}' is not supported by this validator."

    def _fields(self, parameters: dict[str, Any], defaults: tuple[str, ...]) -> tuple[str, ...]:
        configured = parameters.get("fields")
        return tuple(str(value) for value in configured) if isinstance(configured, (tuple, list)) else defaults

    def _numbers(self, values: dict[str, Any], fields: tuple[str, ...]) -> tuple[Decimal, ...] | None:
        numbers = tuple(self._decimal(values.get(field)) for field in fields)
        return None if any(value is None for value in numbers) else tuple(
            value for value in numbers if value is not None
        )

    def _decimal(self, value: Any) -> Decimal | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None

    def _equal(self, left: Decimal, right: Decimal, tolerance: Decimal, precision: int) -> bool:
        quantum = Decimal("1").scaleb(-precision)
        rounded_left = left.quantize(quantum, rounding=ROUND_HALF_UP)
        rounded_right = right.quantize(quantum, rounding=ROUND_HALF_UP)
        return abs(rounded_left - rounded_right) <= tolerance

