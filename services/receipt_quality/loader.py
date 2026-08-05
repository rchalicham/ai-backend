from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Protocol

from .models import CaptureQualityPolicy, immutable_mapping


class EnterpriseConfigurationPort(Protocol):
    def get(self, key: str) -> Mapping[str, Any] | None: ...


class MappingConfigurationProvider:
    """Adapter used by tests and by the Enterprise Configuration client."""
    def __init__(self, values: Mapping[str, Mapping[str, Any]]) -> None:
        self._values = dict(values)

    def get(self, key: str) -> Mapping[str, Any] | None:
        return self._values.get(key)


class FileEnterpriseConfigurationProvider:
    """Read-only adapter for configuration exported by Enterprise Configuration."""
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def get(self, key: str) -> Mapping[str, Any] | None:
        document = json.loads(self.path.read_text(encoding="utf-8"))
        value = document.get(key)
        return value if isinstance(value, dict) else None


class QualityPolicyLoader:
    CONFIGURATION_KEY = "receipt.capture.quality"
    REQUIRED = {
        "policyId", "version", "minimumOverallScore", "minimumFactorScores",
        "scoringRanges", "weights", "minimumFamilyConfidence",
        "minimumSemanticConfidence", "minimumEnterpriseConfidence", "recommendations",
    }

    def __init__(self, configuration: EnterpriseConfigurationPort) -> None:
        self.configuration = configuration

    def load(self) -> CaptureQualityPolicy:
        value = self.configuration.get(self.CONFIGURATION_KEY)
        if not value:
            raise ValueError("enterprise_configuration_missing:receipt.capture.quality")
        missing = sorted(self.REQUIRED.difference(value))
        if missing:
            raise ValueError(f"enterprise_configuration_incomplete:{','.join(missing)}")
        return CaptureQualityPolicy(
            policy_id=str(value["policyId"]), version=str(value["version"]),
            minimum_overall_score=float(value["minimumOverallScore"]),
            minimum_factor_scores=immutable_mapping(value["minimumFactorScores"]),
            scoring_ranges=immutable_mapping({key: immutable_mapping(item) for key, item in value["scoringRanges"].items()}),
            weights=immutable_mapping(value["weights"]),
            minimum_family_confidence=float(value["minimumFamilyConfidence"]),
            minimum_semantic_confidence=float(value["minimumSemanticConfidence"]),
            minimum_enterprise_confidence=float(value["minimumEnterpriseConfidence"]),
            recommendations=immutable_mapping(value["recommendations"]),
        )
