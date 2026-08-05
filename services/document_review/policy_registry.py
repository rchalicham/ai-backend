from .review_policy import build_policy


class DocumentFamilyReviewPolicyRegistry:
    def __init__(self, configuration):
        self.configuration = configuration

    def resolve(self, family):
        normalized = str(family or "unknown").strip().lower().replace(" ", "_")
        policies = self.configuration["familyPolicies"]
        data = policies.get(normalized) or self.configuration["defaultPolicy"]
        return build_policy(normalized, data)
