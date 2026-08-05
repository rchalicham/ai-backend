from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import Expense


@runtime_checkable
class ExpenseRepositoryProtocol(Protocol):
    def save(self, expense: Expense) -> Expense: ...
    def load(self, expense_id: str) -> Expense | None: ...
    def list(self, household_id: str = "", person_id: str = "") -> tuple[Expense, ...]: ...


class ExpenseRepository:
    """In-memory reference repository owned by the business capability."""

    def __init__(self) -> None:
        self._expenses: dict[str, Expense] = {}

    def save(self, expense: Expense) -> Expense:
        if not expense.expense_id:
            raise ValueError("expense_requires_identity")
        if expense.expense_id in self._expenses:
            raise ValueError("expense_already_exists")
        self._expenses[expense.expense_id] = expense
        return expense

    def load(self, expense_id: str) -> Expense | None:
        return self._expenses.get(expense_id)

    def list(self, household_id: str = "", person_id: str = "") -> tuple[Expense, ...]:
        return tuple(sorted((
            item for item in self._expenses.values()
            if (not household_id or item.household_id == household_id)
            and (not person_id or item.person_id == person_id)
        ), key=lambda x: (x.occurred_at, x.expense_id)))
