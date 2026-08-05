from __future__ import annotations

import json
from typing import Any

from .models import (
    LearningApproval,
    LearningAudit,
    LearningCandidate,
    LearningConfidence,
    LearningDecision,
    LearningEvidence,
    LearningEvent,
    LearningExplanation,
    LearningFeedback,
    LearningProposal,
    LearningQuality,
    LearningSnapshot,
    LearningSnapshotVersion,
    LearningStatus,
)


class EnterpriseLearningLoader:
    def snapshot_from_json(self, payload: str) -> LearningSnapshot:
        return self.snapshot_from_dict(json.loads(payload))

    def snapshot_from_dict(self, data: dict[str, Any]) -> LearningSnapshot:
        evidence = tuple(LearningEvidence(
            x["evidence_id"], x["source_type"], x["verified"], x["quality"],
            x["confidence"], tuple(x.get("document_references", ())),
            tuple(x.get("entity_references", ())), tuple(x.get("provenance", ())),
            x.get("timestamp", ""), x.get("version", "learning-evidence-v1"),
        ) for x in data.get("evidence", ()))
        events = tuple(LearningEvent(
            x["event_id"], x["event_type"], x["source"], x["actor_id"],
            tuple(x.get("evidence_ids", ())), x.get("payload"),
            x.get("timestamp", ""), x.get("version", "learning-event-v1"),
        ) for x in data.get("events", ()))
        feedback = tuple(LearningFeedback(
            x["feedback_id"], x["actor_id"], x["actor_role"], x["feedback_type"],
            x["subject_id"], x.get("previous_value"), x.get("proposed_value"),
            x.get("reason", ""), tuple(x.get("evidence_ids", ())),
            tuple(x.get("provenance", ())), x.get("verified", False),
            x.get("timestamp", ""),
        ) for x in data.get("feedback", ()))
        proposals = tuple(self._proposal(x) for x in data.get("proposals", ()))
        decisions = tuple(LearningDecision(
            x["decision_id"], x["proposal_id"], LearningStatus(x["status"]),
            x["reason"], x["actor_id"], x.get("timestamp", ""), x.get("version", 1),
        ) for x in data.get("decisions", ()))
        approvals = tuple(LearningApproval(
            x["approval_id"], x["proposal_id"], LearningStatus(x["status"]),
            x["approver_id"], x["approver_role"], x["reason"],
            x.get("timestamp", ""), x.get("version", 1),
        ) for x in data.get("approvals", ()))
        audit = tuple(LearningAudit(
            x["audit_id"], x["action"], x["subject_id"], x["actor_id"],
            x["source"], x["reason"], tuple(x.get("evidence_ids", ())),
            x.get("previous_value"), x.get("new_value"),
            x.get("timestamp", ""), x.get("version", 1),
        ) for x in data.get("audit", ()))
        return LearningSnapshot(
            data["snapshot_id"], events, feedback, evidence, proposals,
            decisions, approvals, audit,
            LearningSnapshotVersion(**data.get("version", {})),
        )

    @staticmethod
    def _confidence(data: dict[str, Any]) -> LearningConfidence:
        return LearningConfidence(
            data["current"], data["proposed"], data["delta"],
            data.get("repeated_confirmations", 0.0),
            data.get("historical_consistency", 0.0),
            data.get("evidence_quality", 0.0),
            data.get("human_approval", 0.0),
            data.get("cross_document_agreement", 0.0),
            tuple(data.get("components", {}).items()) if isinstance(data.get("components"), dict)
            else tuple(tuple(x) for x in data.get("components", ())),
            tuple(data.get("history", {}).items()) if isinstance(data.get("history"), dict)
            else tuple(tuple(x) for x in data.get("history", ())),
        )

    def _proposal(self, data: dict[str, Any]) -> LearningProposal:
        c = data["candidate"]
        candidate = LearningCandidate(
            c["candidate_id"], c["candidate_type"], c["subject_id"],
            c.get("proposed_value"), tuple(c.get("evidence_ids", ())), c["source"],
            self._confidence(c["confidence"]), c["confirmation_count"],
            LearningStatus(c.get("status", "pending")), c.get("previous_value"),
            c.get("version", 1),
        )
        q = data["quality"]
        quality = LearningQuality(
            q["score"], q["confirmation_count"], q["evidence_coverage"],
            q.get("conflict_count", 0), q.get("low_confidence_count", 0),
            q.get("acceptable", False), tuple(q.get("reasons", ())),
        )
        e = data["explanation"]
        components = e.get("confidence_components", ())
        explanation = LearningExplanation(
            e["explanation_id"], e["subject_id"], e["summary"],
            tuple(e.get("evidence_ids", ())), tuple(e.get("supporting_documents", ())),
            tuple(e.get("supporting_entities", ())),
            tuple(e.get("historical_observations", ())),
            tuple(components.items()) if isinstance(components, dict)
            else tuple(tuple(x) for x in components),
            LearningStatus(e.get("approval_status", "pending")),
        )
        return LearningProposal(
            data["proposal_id"], candidate, quality, explanation,
            LearningStatus(data.get("status", "pending")), data.get("created_at", ""),
            data.get("expires_at", ""), data.get("supersedes_proposal_id", ""),
        )
