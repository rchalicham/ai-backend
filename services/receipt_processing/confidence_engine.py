from .models import ProcessingConfidence


class ProcessingConfidenceEngine:
    def calculate(self, context):
        quality = (context.get("receiptQuality") or {}).get("overallScore")
        family = (((context.get("documentFamilyContext") or {}).get("activation") or {}).get("confidence"))
        projection = (((context.get("businessProjection") or {}).get("overall_confidence") or {}).get("display"))
        agent = (context.get("receiptAgent") or {}).get("confidence")
        values = [float(value) for value in (quality, family, projection, agent) if value is not None]
        return ProcessingConfidence(round(sum(values) / len(values), 4) if values else 0.0, quality, family, projection)

