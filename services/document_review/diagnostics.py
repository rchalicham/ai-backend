from .models import ReviewDiagnostics


def review_diagnostics(context):
    consumed = tuple(key for key in (
        "documentFamilyContext", "receiptGrammar", "receiptConstraintResult",
        "businessProjection", "enterpriseReasoning", "receiptQuality",
    ) if context.get(key) is not None)
    return ReviewDiagnostics("enterprise_configuration", consumed)
