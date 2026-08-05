from __future__ import annotations

from .models import ReasoningConfidence, ReasoningEvidence


class ReasoningConfidenceEngine:
    SOURCES = {
        "constraint_solver": "constraint",
        "enterprise_graph": "graph",
        "enterprise_learning": "learning",
        "cross_document_intelligence": "historical",
    }

    def aggregate(
        self, evidence: tuple[ReasoningEvidence, ...], llm_confidence: float = 0.0,
    ) -> ReasoningConfidence:
        values = {name: 0.0 for name in ("constraint", "graph", "learning", "historical")}
        for item in evidence:
            name = self.SOURCES.get(item.source_tool)
            if name:
                values[name] = max(values[name], item.confidence)
        evidence_score = (
            sum(item.confidence * item.quality for item in evidence) / len(evidence)
            if evidence else 0.0
        )
        components = (*values.items(), ("evidence", evidence_score), ("llm", llm_confidence))
        deterministic = [value for key, value in components if key != "llm" and value > 0]
        overall = sum(deterministic) / len(deterministic) if deterministic else 0.0
        if llm_confidence:
            overall = overall * 0.9 + max(0.0, min(1.0, llm_confidence)) * 0.1
        return ReasoningConfidence(
            round(overall, 6), values["constraint"], values["graph"], values["learning"],
            round(evidence_score, 6), values["historical"], llm_confidence,
            tuple((key, round(value, 6)) for key, value in components),
        )
