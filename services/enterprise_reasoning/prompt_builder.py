from __future__ import annotations

import json

from .models import ReasoningDecision, ReasoningEvidence, ReasoningRequest
from .serializer import EnterpriseReasoningSerializer


class PromptBuilder:
    def __init__(self) -> None:
        self.serializer = EnterpriseReasoningSerializer()

    def build(
        self, request: ReasoningRequest, decision: ReasoningDecision,
        evidence: tuple[ReasoningEvidence, ...],
    ) -> str:
        approved = tuple(item for item in evidence if item.quality >= 0.5)
        payload = {
            "question": request.question,
            "validatedDecision": self.serializer.to_dict(decision),
            "approvedEvidence": [self.serializer.to_dict(item) for item in approved],
            "rules": [
                "Use only the supplied approved evidence.",
                "Do not introduce facts not present in evidence.",
                "State uncertainty and preserve source identifiers.",
            ],
        }
        text = json.dumps(payload, sort_keys=True)
        forbidden = ("rawOcr", "raw_ocr", "parserGuess", "parser_guess")
        if any(value in text for value in forbidden):
            raise ValueError("reasoning_prompt_contains_forbidden_source")
        return text
