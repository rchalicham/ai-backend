from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class HouseholdRepositoryProtocol(Protocol):
    def save(self, household): ...
    def load(self, household_id): ...
    def list(self): ...


class HouseholdRepository:
    def __init__(self):
        self._households = {}

    def save(self, household):
        if household.household_id in self._households:
            raise ValueError("household_already_exists")
        self._households[household.household_id] = household
        return household

    def load(self, household_id):
        return self._households.get(household_id)

    def list(self):
        return tuple(self._households[key] for key in sorted(self._households))
