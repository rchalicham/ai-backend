from __future__ import annotations

from .models import (
    LearningEvidence,
    LearningProposal,
    LearningRule,
    LearningStatus,
)


class LearningGovernanceEngine:
    def __init__(self, rule: LearningRule | None = None) -> None:
        self.rule = rule or LearningRule("enterprise-learning-default", "Default learning governance")

    def govern(
        self,
        proposals: tuple[LearningProposal, ...],
        evidence: tuple[LearningEvidence, ...],
        existing: tuple[LearningProposal, ...] = (),
    ) -> tuple[tuple[LearningProposal, ...], tuple[str, ...]]:
        evidence_by_id = {item.evidence_id: item for item in evidence}
        existing_keys = {
            (
                item.candidate.candidate_type,
                item.candidate.subject_id,
                repr(item.candidate.proposed_value),
            ): item
            for item in existing
        }
        accepted = []
        warnings = []
        seen = set()
        for proposal in proposals:
            candidate = proposal.candidate
            key = (
                candidate.candidate_type,
                candidate.subject_id,
                repr(candidate.proposed_value),
            )
            reasons = []
            relevant = tuple(
                evidence_by_id[item] for item in candidate.evidence_ids
                if item in evidence_by_id
            )
            if key in seen or key in existing_keys:
                reasons.append("duplicate proposal")
            if any(item.status == LearningStatus.REJECTED for item in existing if (
                item.candidate.candidate_type,
                item.candidate.subject_id,
                repr(item.candidate.proposed_value),
            ) == key):
                reasons.append("proposal was previously rejected")
            if candidate.version < 1:
                reasons.append("invalid candidate version")
            if candidate.source not in self.rule.allowed_source_types:
                reasons.append("unapproved learning source")
            if not relevant or any(not item.verified for item in relevant):
                reasons.append("evidence is not verified")
            if any(item.quality < self.rule.minimum_evidence_quality for item in relevant):
                reasons.append("evidence quality below governance threshold")
            if candidate.confidence.proposed < self.rule.minimum_confidence:
                reasons.append("candidate confidence below governance threshold")
            if not proposal.quality.acceptable:
                reasons.extend(proposal.quality.reasons or ("quality gate failed",))
            if proposal.status != LearningStatus.PENDING:
                reasons.append("new proposals must enter pending")
            if reasons:
                warnings.append(f"{proposal.proposal_id}:{','.join(dict.fromkeys(reasons))}")
                continue
            seen.add(key)
            accepted.append(proposal)
        return tuple(accepted), tuple(warnings)

