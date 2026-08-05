from .models import ProcessingDiagnostics, frozen_map


def processing_diagnostics(context):
    return ProcessingDiagnostics(frozen_map({
        "qualityStatus": (context.get("receiptQuality") or {}).get("status"),
        "agentStatus": (context.get("receiptAgent") or {}).get("status"),
        "family": ((context.get("documentFamilyContext") or {}).get("activation") or {}).get("family"),
        "projectionAvailable": bool(context.get("businessProjection")),
        "documentReviewDecision": ((context.get("documentReview") or {}).get("decision") or {}).get("key"),
        "resolvedQuality": (context.get("documentReview") or {}).get("resolvedQuality"),
    }))
