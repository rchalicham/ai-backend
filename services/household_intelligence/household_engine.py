from __future__ import annotations

import hashlib
from collections import Counter, defaultdict

from .confidence_engine import HouseholdConfidenceEngine
from .diagnostics import HouseholdIntelligenceDiagnostics
from .explanation_engine import HouseholdExplanationEngine
from .household_profile_engine import HouseholdProfileEngine
from .models import (
    Household, HouseholdInsight, HouseholdIntelligenceResult, HouseholdProfile,
)
from .recommendation_engine import HouseholdRecommendationEngine
from .relationship_engine import HouseholdRelationshipEngine


class HouseholdIntelligenceEngine:
    def __init__(self, profiles=None, relationships=None, recommendations=None,
                 explanations=None, confidence=None, diagnostics=None):
        self.profiles = profiles or HouseholdProfileEngine()
        self.relationships = relationships or HouseholdRelationshipEngine()
        self.recommendations = recommendations or HouseholdRecommendationEngine()
        self.explanations = explanations or HouseholdExplanationEngine()
        self.confidence = confidence or HouseholdConfidenceEngine()
        self.diagnostics = diagnostics or HouseholdIntelligenceDiagnostics()

    def analyze(self, reasoning, expense_intelligence, household, **facts):
        reasoning = reasoning or {}
        expense_intelligence = expense_intelligence or {}
        profile = self.profiles.build(
            household, expense_intelligence=expense_intelligence, **facts,
        )
        warnings = self.relationships.validate(
            profile.relationships, tuple(x.member_id for x in profile.members),
        )
        confidence = self.confidence.aggregate(profile, reasoning, expense_intelligence)
        insights = self._insights(profile, expense_intelligence, confidence.overall)
        recommendations = self.recommendations.generate(profile)
        explanations = tuple(
            self.explanations.explain(item, profile, reasoning) for item in insights
        )
        return HouseholdIntelligenceResult(
            profile, insights, recommendations, explanations, confidence,
            self.diagnostics.create(profile, warnings),
        )

    def safe_analyze(self, reasoning, expense_intelligence, household=None, **facts):
        try:
            household = household or Household("household:unassigned", "Unassigned Household")
            return self.analyze(reasoning, expense_intelligence, household, **facts)
        except Exception as exc:
            profile = HouseholdProfile(Household("household:failed", "Failed Household"))
            return HouseholdIntelligenceResult(
                profile, diagnostics=self.diagnostics.failed(exc),
            )

    def _insights(self, profile, expense, confidence):
        values = []
        expenses = expense.get("expenses") or ()
        people = defaultdict(float)
        groceries = Counter()
        for item in expenses:
            person = item.get("person_id") or "unassigned"
            people[person] += float(item.get("amount") or 0)
            if item.get("category") == "Groceries":
                groceries[person] += 1
        if people:
            top = max(people, key=people.get)
            values.append(self._insight(
                "spends_most", "Who spends most", top, (top,),
                self._expense_evidence(expenses), confidence,
            ))
        if groceries:
            top = groceries.most_common(1)[0][0]
            values.append(self._insight(
                "buys_groceries", "Who buys groceries", top, (top,),
                self._expense_evidence(expenses), confidence,
            ))
        owned = Counter(
            member for asset in profile.assets for member in asset.owner_member_ids
        )
        if owned:
            top = owned.most_common(1)[0][0]
            values.append(self._insight(
                "owns_most_assets", "Who owns most assets", top, (top,),
                tuple(x for asset in profile.assets for x in asset.evidence_ids), confidence,
            ))
        merchants = (expense.get("summary") or {}).get("merchants") or ()
        if merchants:
            top = merchants[0]
            values.append(self._insight(
                "favorite_merchant", "Favorite merchant", top.get("merchant_name", ""),
                (top.get("merchant_id", ""),), (), confidence,
            ))
        shared = tuple(x for x in profile.ownership if len(x.owner_member_ids) > 1)
        if shared:
            values.append(self._insight(
                "shared_purchases", "Shared purchases", len(shared),
                tuple(x.subject_id for x in shared),
                tuple(v for x in shared for v in x.evidence_ids), confidence,
            ))
        return tuple(values)

    @staticmethod
    def _expense_evidence(expenses):
        return tuple(dict.fromkeys(
            value for item in expenses for value in item.get("evidence_ids", ())
        ))

    @staticmethod
    def _insight(kind, title, value, subjects, evidence, confidence):
        token = hashlib.sha256(f"{kind}|{value}".encode()).hexdigest()[:20]
        return HouseholdInsight(
            f"household-insight:{token}", kind, title, value, tuple(subjects),
            tuple(evidence), f"household-explanation:{token}", confidence,
        )
