from .models import ProcessingRecommendation


class ProcessingRecommendationEngine:
    def build(self, context, state, configuration):
        document_review = context.get("documentReview") or {}
        if document_review:
            output = []
            for item in document_review.get("recommendations") or []:
                output.append(ProcessingRecommendation(item["code"], item["message"], item["reason"], item["message"], item["priority"]))
            return tuple(output)
        quality_items = (context.get("receiptQuality") or {}).get("recommendations") or []
        codes = [item.get("code") for item in quality_items if item.get("code")]
        if not codes:
            codes = configuration.get("stateRecommendations", {}).get(state.key, [])
        output = []
        for code in codes:
            item = configuration["recommendations"].get(code)
            if item:
                output.append(ProcessingRecommendation(code, item["label"], item["why"], item["action"], item["priority"]))
        return tuple(output)
