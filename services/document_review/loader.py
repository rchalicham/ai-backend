from types import MappingProxyType


class DocumentReviewConfigurationLoader:
    KEY = "receipt.document.review"
    REQUIRED = {
        "configurationId", "version", "defaultPolicy", "familyPolicies",
        "fieldAliases", "weights", "decisions", "qualityResolution",
        "recommendations", "explanations", "confidenceWeights",
    }

    def __init__(self, configuration_provider):
        self.configuration_provider = configuration_provider

    def load(self):
        value = self.configuration_provider.get(self.KEY)
        if not value:
            raise ValueError(f"enterprise_configuration_missing:{self.KEY}")
        missing = sorted(self.REQUIRED.difference(value))
        if missing:
            raise ValueError(f"enterprise_configuration_incomplete:{','.join(missing)}")
        return MappingProxyType(dict(value))
