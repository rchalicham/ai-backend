from .models import ExpenseDiagnostics


class ExpenseIntelligenceDiagnostics:
    def create(self, expenses, *, warnings=()):
        return ExpenseDiagnostics(
            warnings=tuple(warnings),
            information=(
                f"business expenses evaluated: {len(expenses)}",
                "platform services consumed through read-only contracts",
                "trends are observational and recommendations require human decisions",
            ),
        )

    @staticmethod
    def failed(error):
        return ExpenseDiagnostics(errors=(f"expense_intelligence_failed:{error}",))
