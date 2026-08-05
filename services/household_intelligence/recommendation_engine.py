from __future__ import annotations

import hashlib

from .models import HouseholdRecommendation


class HouseholdRecommendationEngine:
    def generate(self, profile):
        values = []
        assigned_assets = {x.subject_id for x in profile.ownership if x.owner_member_ids}
        for asset in profile.assets:
            if asset.asset_id not in assigned_assets:
                values.append(self._make(
                    "assignment", f"Assign an owner for {asset.name}",
                    "An asset has no evidence-backed ownership assignment.",
                    (asset.asset_id,), asset.evidence_ids, .8,
                ))
            if asset.warranty_id:
                values.append(self._make(
                    "warranty_reminder", f"Review warranty for {asset.name}",
                    "A warranty-linked household asset should have a reviewed reminder policy.",
                    (asset.asset_id, asset.warranty_id), asset.evidence_ids, .85,
                ))
        for pet in profile.pets:
            if not pet.owner_member_ids:
                values.append(self._make(
                    "pet_care_assignment", f"Assign a caregiver for {pet.name}",
                    "The pet has no evidence-backed caregiver or owner assignment.",
                    (pet.pet_id,), pet.evidence_ids, .8,
                ))
        for goal in profile.goals:
            values.append(self._make(
                "goal_organization", f"Review goal: {goal.title}",
                "Household goals are informational and require member decisions.",
                (goal.goal_id,), goal.evidence_ids, .75,
            ))
        return tuple(values)

    @staticmethod
    def _make(kind, title, description, subjects, evidence, confidence):
        token = hashlib.sha256(f"{kind}|{subjects}".encode()).hexdigest()[:20]
        return HouseholdRecommendation(
            f"household-recommendation:{token}", kind, title, description,
            tuple(subjects), tuple(evidence), confidence, True,
        )
