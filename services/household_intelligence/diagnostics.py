from .models import HouseholdDiagnostics


class HouseholdIntelligenceDiagnostics:
    def create(self, profile, warnings=()):
        return HouseholdDiagnostics(
            warnings=tuple(warnings),
            information=(
                f"household members evaluated: {len(profile.members)}",
                f"household assets evaluated: {len(profile.assets)}",
                "household facts consume read-only platform and Expense Intelligence contracts",
            ),
        )

    @staticmethod
    def failed(error):
        return HouseholdDiagnostics(errors=(f"household_intelligence_failed:{error}",))
