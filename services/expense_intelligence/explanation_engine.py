from __future__ import annotations

from .models import ExpenseExplanation


class ExpenseExplanationEngine:
    def for_summary(self, summary, expenses, reasoning=None):
        evidence = tuple(dict.fromkeys(x for item in expenses for x in item.evidence_ids))
        documents = tuple(dict.fromkeys(x for item in expenses for x in item.document_ids))
        steps = ()
        if reasoning:
            traces = reasoning.get("session", {}).get("traces", ())
            steps = tuple(
                f"{item.get('tool_name')}:{item.get('status')}" for item in traces
            )
        return ExpenseExplanation(
            f"explanation:{summary.summary_id}", summary.summary_id,
            (
                f"Total spending is {summary.currency} {summary.total:.2f} from "
                f"{summary.transaction_count} evidence-linked expenses."
            ),
            (
                f"{summary.transaction_count} expenses were included.",
                f"{len(documents)} source documents support the summary.",
                f"{len(summary.merchants)} merchants and {len(summary.categories)} categories were evaluated.",
            ),
            evidence, documents, steps,
        )

    def for_insight(self, insight_type, title, value, expenses, confidence):
        evidence = tuple(dict.fromkeys(x for item in expenses for x in item.evidence_ids))
        documents = tuple(dict.fromkeys(x for item in expenses for x in item.document_ids))
        return ExpenseExplanation(
            f"explanation:insight:{insight_type}", f"insight:{insight_type}",
            f"{title} is {value} based on linked expense evidence.",
            (f"{len(expenses)} expenses contributed.",),
            evidence, documents, confidence=confidence,
        )
