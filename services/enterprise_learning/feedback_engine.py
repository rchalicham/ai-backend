from __future__ import annotations

import hashlib
from typing import Any

from .models import LearningFeedback


class EnterpriseFeedbackEngine:
    ALLOWED_ROLES = {"developer", "administrator", "business_user", "ai_reviewer"}

    def create(
        self,
        *,
        actor_id: str,
        actor_role: str,
        feedback_type: str,
        subject_id: str,
        proposed_value: Any,
        reason: str,
        previous_value: Any = None,
        evidence_ids: tuple[str, ...] = (),
        provenance: tuple[str, ...] = (),
        verified: bool = False,
    ) -> LearningFeedback:
        role = actor_role.casefold()
        if role not in self.ALLOWED_ROLES:
            raise ValueError("unsupported_feedback_actor_role")
        identity = "|".join((actor_id, role, feedback_type, subject_id, reason))
        return LearningFeedback(
            hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24],
            actor_id,
            role,
            feedback_type,
            subject_id,
            previous_value,
            proposed_value,
            reason,
            tuple(evidence_ids),
            tuple(provenance),
            verified,
        )

