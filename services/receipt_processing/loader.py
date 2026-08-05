from __future__ import annotations

from types import MappingProxyType


class ProcessingExperienceConfigurationLoader:
    KEY = "receipt.processing.experience"
    REQUIRED = {"configurationId", "version", "states", "stageStates", "stages", "thresholds", "recoverabilityRules", "stateRecoverabilityMappings", "recommendations", "explanations", "actions", "labels"}

    def __init__(self, configuration_provider) -> None:
        self.configuration_provider = configuration_provider

    def load(self):
        value = self.configuration_provider.get(self.KEY)
        if not value:
            raise ValueError(f"enterprise_configuration_missing:{self.KEY}")
        missing = sorted(self.REQUIRED.difference(value))
        if missing:
            raise ValueError(f"enterprise_configuration_incomplete:{','.join(missing)}")
        return MappingProxyType(dict(value))
