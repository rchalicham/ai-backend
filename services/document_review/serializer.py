from dataclasses import fields, is_dataclass
from types import MappingProxyType


class DocumentReviewSerializer:
    def to_dict(self, value):
        def convert(item):
            if is_dataclass(item):
                item = {field.name: getattr(item, field.name) for field in fields(item)}
            if isinstance(item, (dict, MappingProxyType)):
                return {self._camel(str(key)): convert(nested) for key, nested in item.items()}
            if isinstance(item, (list, tuple)):
                return [convert(nested) for nested in item]
            return item
        payload = convert(value)
        payload["schemaVersion"] = "document-family-review-v1"
        payload["humanReview"] = self.compatibility_human_review(payload)
        return payload

    @staticmethod
    def compatibility_human_review(payload):
        decision = payload["decision"]
        completeness = payload["semanticCompleteness"]
        recommendations = payload.get("recommendations") or []
        reasons = [
            {"field": code.removeprefix("missing_"), "reason": code, "severity": "high", "detail": payload["explanation"]["message"], "action": recommendations[0]["message"] if recommendations else "Review the semantic evidence."}
            for code in decision.get("reasonCodes") or []
        ]
        return {
            "required": decision["requiresHumanReview"],
            "queue": "document_family_review",
            "reviewMode": "semantic_policy",
            "priority": "high" if decision["requiresHumanReview"] else "none",
            "riskScore": round((1.0 - decision["confidence"]) * 100),
            "summary": payload["explanation"]["message"],
            "reasons": reasons,
            "actionableExplanations": [item["message"] for item in recommendations],
            "suggestedChecks": list(completeness.get("missingRequiredFields") or []),
            "source": "document_family_review_policy",
        }

    @staticmethod
    def _camel(value):
        parts = value.split("_")
        return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])
