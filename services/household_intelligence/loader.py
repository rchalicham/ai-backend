from __future__ import annotations

from .models import (
    ConsumptionRecord, Goal, Household, HouseholdAsset, HouseholdMember,
    HouseholdRole, Ownership, Pet, Preference, Property, Relationship,
    Responsibility, Vehicle,
)


class HouseholdIntelligenceLoader:
    TUPLES = {
        Household: ("member_ids", "asset_ids", "pet_ids", "evidence_ids"),
        HouseholdMember: ("evidence_ids", "history"),
        Relationship: ("evidence_ids",),
        Ownership: ("owner_member_ids", "evidence_ids"),
        Responsibility: ("member_ids", "evidence_ids"),
        ConsumptionRecord: ("consumer_ids", "evidence_ids"),
        Preference: ("subject_member_ids", "evidence_ids"),
        Goal: ("owner_ids", "evidence_ids"),
        HouseholdAsset: ("owner_member_ids", "evidence_ids"),
        Vehicle: ("owner_member_ids", "evidence_ids"),
        Property: ("owner_member_ids", "evidence_ids"),
        Pet: (
            "owner_member_ids", "food_product_ids", "medication_ids",
            "supply_product_ids", "expense_ids", "evidence_ids",
        ),
    }

    def load(self, data):
        household = self._model(Household, data["household"])
        members = []
        for item in data.get("members", ()):
            value = dict(item)
            try:
                value["role"] = HouseholdRole(value.get("role", "Unknown"))
            except ValueError:
                pass
            members.append(self._model(HouseholdMember, value))
        return {
            "household": household,
            "members": tuple(members),
            "relationships": self._models(Relationship, data.get("relationships", ())),
            "ownership": self._models(Ownership, data.get("ownership", ())),
            "responsibilities": self._models(Responsibility, data.get("responsibilities", ())),
            "consumption": self._models(ConsumptionRecord, data.get("consumption", ())),
            "preferences": self._models(Preference, data.get("preferences", ())),
            "goals": self._models(Goal, data.get("goals", ())),
            "assets": self._models(HouseholdAsset, data.get("assets", ())),
            "vehicles": self._models(Vehicle, data.get("vehicles", ())),
            "properties": self._models(Property, data.get("properties", ())),
            "pets": self._models(Pet, data.get("pets", ())),
        }

    def _models(self, cls, values):
        return tuple(self._model(cls, item) for item in values)

    def _model(self, cls, data):
        values = dict(data)
        for name in self.TUPLES.get(cls, ()):
            values[name] = tuple(values.get(name, ()))
        return cls(**values)
