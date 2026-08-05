from .models import ReviewRecommendation


class DocumentReviewRecommendationEngine:
    def build(self, decision, completeness, quality, configuration):
        codes = []
        if not quality.passed:
            codes.extend(f"quality_{item.get('code')}" for item in quality.unresolved_warnings)
        codes.extend(f"missing_{field}" for field in completeness.missing_required_fields)
        codes.extend(configuration["decisions"][decision.key].get("recommendations") or ())
        output = []
        for code in dict.fromkeys(codes):
            item = configuration["recommendations"].get(code) or configuration["recommendations"].get("default_review")
            if item:
                output.append(ReviewRecommendation(code, item["message"], item["reason"], item["priority"]))
        return tuple(output)
