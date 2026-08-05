from .models import Recoverability


class RecoverabilityEngine:
    def resolve(self, context, state, configuration):
        signals = configuration.get("recoverabilitySignalMappings", {})
        quality_status = (context.get("receiptQuality") or {}).get("status")
        agent_status = (context.get("receiptAgent") or {}).get("status")
        key = signals.get(f"quality:{quality_status}") or signals.get(f"agent:{agent_status}") or configuration["stateRecoverabilityMappings"].get(state.key)
        if not key: raise ValueError(f"enterprise_configuration_missing:stateRecoverabilityMappings.{state.key}")
        rule = configuration["recoverabilityRules"].get(key)
        if not rule: raise ValueError(f"enterprise_configuration_missing:recoverabilityRules.{key}")
        return Recoverability(key, float(rule["score"]), float(rule["confidence"]), rule["recommendation"])
