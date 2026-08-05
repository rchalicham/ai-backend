from .models import HouseholdExplanation


class HouseholdExplanationEngine:
    def explain(self, insight, profile, reasoning=None):
        evidence = tuple(dict.fromkeys((
            *insight.evidence_ids,
            *(x for member in profile.members for x in member.evidence_ids),
        )))
        relationships = tuple(x.relationship_id for x in profile.relationships)
        history = tuple(x for member in profile.members for x in member.history)
        traces = tuple(
            f"{x.get('tool_name')}:{x.get('status')}"
            for x in (reasoning or {}).get("session", {}).get("traces", ())
        )
        receipts = tuple(
            x for x in evidence if x.startswith("receipt:") or x.startswith("document:")
        )
        products = tuple(x for x in evidence if x.startswith("product:"))
        return HouseholdExplanation(
            insight.explanation_id, insight.insight_id,
            f"{insight.title} is supported by household, relationship, expense, and enterprise evidence.",
            evidence, receipts, products, relationships, history, traces,
            insight.confidence,
        )
