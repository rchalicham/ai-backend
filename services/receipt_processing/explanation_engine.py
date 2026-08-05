from .models import ProcessingExplanation


class ProcessingExplanationEngine:
    def explain(self, context, state, configuration):
        document_review = context.get("documentReview") or {}
        if document_review.get("explanation"):
            item = document_review["explanation"]
            return ProcessingExplanation(item["title"], item["message"], f"document_review_{(document_review.get('decision') or {}).get('key', state.key)}")
        quality = context.get("receiptQuality") or {}
        failed = next((item for item in quality.get("factors", []) if quality.get("passed") is False and not item.get("passed", True)), None)
        reason_code = f"quality_{failed['name']}" if failed else state.key
        item = configuration["explanations"].get(reason_code) or configuration["explanations"].get(state.key)
        if not item: raise ValueError(f"enterprise_configuration_missing:explanations.{reason_code}")
        return ProcessingExplanation(item["title"], item["message"], reason_code)
