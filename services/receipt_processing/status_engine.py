from .models import ProcessingState


class ProcessingStatusEngine:
    def resolve(self, context, configuration):
        resolved_review = context.get("documentReview") or {}
        resolved_decision = resolved_review.get("decision") or {}
        quality = context.get("receiptQuality") or {}
        agent = context.get("receiptAgent") or {}
        review = agent.get("humanReview") or {}
        projection = context.get("businessProjection") or {}
        source_status = str(context.get("receiptSourceStatus") or context.get("status") or "").lower()
        projection_confidence = ((projection.get("overall_confidence") or {}).get("display"))
        threshold = float(configuration["thresholds"]["businessProjectionDisplay"])
        if resolved_decision.get("processingState"):
            key = resolved_decision["processingState"]
        elif quality.get("passed") is False or agent.get("status") == "quality_failure": key = "needs_user_action"
        elif agent.get("status") in {"failed", "error"}: key = "failed"
        elif agent.get("status") == "cancelled": key = "cancelled"
        elif review.get("required"): key = "human_review_required"
        elif projection and float(projection_confidence or 0) >= threshold: key = "completed"
        elif agent.get("status") in {"running", "processing", "needs_human_review"}: key = "processing"
        elif agent: key = "processing"
        elif source_status in configuration.get("sourceStatusMappings", {}): key = configuration["sourceStatusMappings"][source_status]
        else: key = "unknown"
        configured = next((item for item in configuration["states"] if item["key"] == key), None)
        if configured is None:
            raise ValueError(f"enterprise_configuration_missing:state.{key}")
        return ProcessingState(key, configured["label"], configured["color"], configured["icon"])
