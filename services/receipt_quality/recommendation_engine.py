from .models import QualityRecommendation

class RecommendationEngine:
    def build(self, factors, policy):
        output = []
        for item in factors:
            if item.passed:
                continue
            message = policy.recommendations.get(item.name)
            if message:
                output.append(QualityRecommendation(f"capture_{item.name}", message, "error", item.name))
        return tuple(output)

