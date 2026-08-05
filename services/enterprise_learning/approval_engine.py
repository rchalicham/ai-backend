from __future__ import annotations

import hashlib
from dataclasses import replace

from .models import (
    LearningApproval,
    LearningDecision,
    LearningProposal,
    LearningStatus,
)


class LearningApprovalEngine:
    def decide(
        self,
        proposal: LearningProposal,
        status: LearningStatus | str,
        *,
        approver_id: str,
        approver_role: str,
        reason: str,
    ) -> tuple[LearningProposal, LearningApproval, LearningDecision]:
        target = LearningStatus(status)
        if target not in {
            LearningStatus.APPROVED,
            LearningStatus.REJECTED,
            LearningStatus.EXPIRED,
            LearningStatus.SUPERSEDED,
        }:
            raise ValueError("invalid_learning_decision_status")
        if proposal.status != LearningStatus.PENDING:
            raise ValueError("learning_proposal_is_not_pending")
        identity = f"{proposal.proposal_id}|{target.value}|{approver_id}|{reason}"
        token = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        updated = replace(
            proposal,
            status=target,
            candidate=replace(proposal.candidate, status=target),
            explanation=replace(proposal.explanation, approval_status=target),
        )
        return (
            updated,
            LearningApproval(
                f"approval:{token}", proposal.proposal_id, target,
                approver_id, approver_role, reason,
            ),
            LearningDecision(
                f"decision:{token}", proposal.proposal_id, target,
                reason, approver_id,
            ),
        )

    def approve(self, proposal, **kwargs):
        return self.decide(proposal, LearningStatus.APPROVED, **kwargs)

    def reject(self, proposal, **kwargs):
        return self.decide(proposal, LearningStatus.REJECTED, **kwargs)

    def expire(self, proposal, **kwargs):
        return self.decide(proposal, LearningStatus.EXPIRED, **kwargs)

    def supersede(self, proposal, **kwargs):
        return self.decide(proposal, LearningStatus.SUPERSEDED, **kwargs)

