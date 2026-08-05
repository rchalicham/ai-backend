from .models import HouseholdConfidence


class HouseholdConfidenceEngine:
    def aggregate(self, profile, reasoning=None, expense=None):
        reasoning = reasoning or {}
        expense = expense or {}
        evidence_values = [
            x.confidence for values in (
                profile.members, profile.relationships, profile.ownership,
                profile.responsibilities, profile.consumption, profile.preferences,
                profile.assets,
            ) for x in values if hasattr(x, "confidence")
        ]
        household = sum(evidence_values) / len(evidence_values) if evidence_values else 0.0
        reasoning_value = float(((reasoning.get("decision") or {}).get("confidence") or {}).get("overall") or 0)
        evidence = reasoning.get("evidence") or ()
        source = lambda name: max((
            float(x.get("confidence") or 0) for x in evidence
            if x.get("source_tool") == name
        ), default=0.0)
        values = {
            "reasoning": reasoning_value,
            "learning": source("enterprise_learning"),
            "cross_document": source("cross_document_intelligence"),
            "knowledge_graph": source("enterprise_graph"),
            "expense": float((expense.get("confidence") or {}).get("overall") or 0),
            "household_evidence": household,
        }
        present = [x for x in values.values() if x > 0]
        overall = sum(present) / len(present) if present else 0.0
        return HouseholdConfidence(round(overall, 6), **values, components=tuple(values.items()))
