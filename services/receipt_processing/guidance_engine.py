class GuidanceEngine:
    """Business-safe guidance facade; never exposes internal sidecar names."""
    def business_summary(self, state, explanation, recoverability):
        return f"{state.label}. {explanation.message} {recoverability.recommendation}".strip()

