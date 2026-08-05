from .models import ProcessingStage, ProcessingTimeline


def path_value(document, path):
    if not path:
        return None
    value = document
    for part in str(path or "").split("."):
        if not part: continue
        if not isinstance(value, dict): return None
        value = value.get(part)
    return value


class ProcessingStageEngine:
    def build(self, context, status, configuration):
        resolved_quality = (context.get("documentReview") or {}).get("resolvedQuality") or {}
        quality_failed = (resolved_quality.get("passed") is False) if resolved_quality else ((context.get("receiptQuality") or {}).get("passed") is False)
        stages = []
        failed_seen = False
        current = configuration["stages"][0]["key"]
        for order, item in enumerate(configuration["stages"]):
            present = path_value(context, item.get("evidencePath")) is not None
            if item["key"] == "upload": stage_state = "success"
            elif item["key"] == "geometry" and context.get("receiptQuality"): stage_state = "success"
            elif item["key"] == "quality_validation" and quality_failed: stage_state, failed_seen, current = "failed", True, item["key"]
            elif failed_seen: stage_state = "skipped"
            elif present: stage_state, current = "success", item["key"]
            elif status.state.key == "completed": stage_state = "skipped"
            else: stage_state, current = "waiting", item["key"]
            confidence = path_value(context, item.get("confidencePath"))
            duration = path_value(context, item.get("durationPath"))
            presentation = configuration["stageStates"][stage_state]
            stages.append(ProcessingStage(item["key"], item["label"], stage_state, int(duration) if duration is not None else None, float(confidence) if confidence is not None else None, item["explanations"][stage_state], order, presentation["color"], presentation["icon"]))
        return ProcessingTimeline(tuple(stages), current)
