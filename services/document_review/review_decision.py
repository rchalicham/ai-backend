from .models import ReviewDecision


class ReviewDecisionEngine:
    def decide(self, policy, completeness, quality, confidence, configuration):
        reasons = []
        if not quality.passed:
            decision_key = "needs_user_action"
            reasons.extend(f"quality_{item.get('code')}" for item in quality.unresolved_warnings)
        elif policy.configuration.get("completionAllowed") is False:
            decision_key = "insufficient_evidence"
            reasons.append("document_family_unknown")
        elif completeness.missing_required_fields:
            decision_key = "human_review_required"
            reasons.extend(f"missing_{name}" for name in completeness.missing_required_fields)
        elif not completeness.item_expectation_satisfied:
            decision_key = "human_review_required"
            reasons.append("item_expectation_not_satisfied")
        elif completeness.score < policy.minimum_completeness:
            decision_key = "manual_verification"
            reasons.append("semantic_completeness_below_policy")
        elif confidence.overall < policy.minimum_confidence:
            decision_key = "completed_with_warnings"
            reasons.append("confidence_below_policy")
        else:
            decision_key = "completed"
        item = configuration["decisions"][decision_key]
        return ReviewDecision(
            decision_key, item["label"], item["processingState"], bool(item["requiresHumanReview"]),
            confidence.overall, tuple(reasons),
        )
