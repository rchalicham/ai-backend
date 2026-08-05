from .models import ReviewExplanation


class DocumentReviewExplanationEngine:
    def explain(self, family, decision, completeness, quality, configuration):
        item = configuration["explanations"][decision.key]
        evidence = [f"document_family:{family}", f"semantic_completeness:{completeness.score:.0%}"]
        evidence.extend(f"present:{name}" for name in completeness.missing_optional_fields if False)
        evidence.extend(f"missing:{name}" for name in completeness.missing_required_fields)
        if quality.resolved_warnings:
            evidence.append(f"resolved_quality_warnings:{len(quality.resolved_warnings)}")
        return ReviewExplanation(item["title"], item["message"], tuple(evidence))
