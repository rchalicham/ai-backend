from __future__ import annotations

import hashlib

from .models import LearningApproval, LearningAudit, LearningProposal


class LearningAuditEngine:
    """Creates append-only audit facts; it never applies the audited change."""

    def proposal_created(self, proposal: LearningProposal) -> LearningAudit:
        candidate = proposal.candidate
        return LearningAudit(
            self._id("proposal_created", proposal.proposal_id),
            "proposal_created",
            proposal.proposal_id,
            "system",
            candidate.source,
            proposal.explanation.summary,
            candidate.evidence_ids,
            candidate.previous_value,
            candidate.proposed_value,
        )

    def decision_recorded(
        self, proposal: LearningProposal, approval: LearningApproval,
    ) -> LearningAudit:
        return LearningAudit(
            self._id(approval.status.value, proposal.proposal_id, approval.approval_id),
            f"proposal_{approval.status.value}",
            proposal.proposal_id,
            approval.approver_id,
            approval.approver_role,
            approval.reason,
            proposal.candidate.evidence_ids,
            proposal.candidate.previous_value,
            proposal.candidate.proposed_value,
        )

    @staticmethod
    def _id(*values: str) -> str:
        return "audit:" + hashlib.sha256("|".join(values).encode()).hexdigest()[:24]
