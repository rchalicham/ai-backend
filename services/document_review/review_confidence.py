from .models import ReviewConfidence


class ReviewConfidenceEngine:
    def calculate(self, context, completeness, resolved_quality, configuration):
        family = float((((context.get("documentFamilyContext") or {}).get("activation") or {}).get("confidence")) or 0.0)
        projection = float((((context.get("businessProjection") or {}).get("overall_confidence") or {}).get("display")) or 0.0)
        reasoning_payload = context.get("enterpriseReasoning") or {}
        reasoning = float(reasoning_payload.get("confidence") or reasoning_payload.get("overallConfidence") or 0.0)
        quality = float(resolved_quality.score or 0.0)
        values = {"family": family, "semantic": completeness.score, "projection": projection, "reasoning": reasoning, "quality": quality}
        weights = configuration["confidenceWeights"]
        available = [(values[key], float(weight)) for key, weight in weights.items() if values.get(key, 0) > 0]
        overall = sum(value * weight for value, weight in available) / sum(weight for _, weight in available) if available else 0.0
        return ReviewConfidence(round(overall, 4), round(family, 4), completeness.score, round(projection, 4), round(reasoning, 4), round(quality, 4))
