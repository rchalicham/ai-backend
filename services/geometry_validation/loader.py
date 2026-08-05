from __future__ import annotations

from .models import GeometryValidationPolicy, frozen_map


class GeometryValidationPolicyLoader:
    KEY = "receipt.geometry.validation"
    REQUIRED = {"configurationId", "version", "contourLimits", "confidenceThresholds",
                "confidenceWeights", "fallbackOrder", "perspectiveLimits", "skewLimits",
                "pageDetection", "criticalFactors", "advisoryFactors"}

    def __init__(self, configuration):
        self.configuration = configuration

    def load(self):
        value = self.configuration.get(self.KEY)
        if not value:
            raise ValueError(f"enterprise_configuration_missing:{self.KEY}")
        missing = sorted(self.REQUIRED.difference(value))
        if missing:
            raise ValueError(f"enterprise_configuration_incomplete:{','.join(missing)}")
        return GeometryValidationPolicy(
            str(value["configurationId"]), str(value["version"]),
            frozen_map(value["contourLimits"]), frozen_map(value["confidenceThresholds"]),
            frozen_map(value["confidenceWeights"]), tuple(value["fallbackOrder"]),
            frozen_map(value["perspectiveLimits"]), frozen_map(value["skewLimits"]),
            frozen_map(value["pageDetection"]), tuple(value["criticalFactors"]),
            tuple(value["advisoryFactors"]),
        )
