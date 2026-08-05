from __future__ import annotations

from collections.abc import Callable
from difflib import SequenceMatcher

from .models import Similarity


class SimilarityEngine:
    def __init__(
        self,
        embedding_similarity: Callable[[str, str], float] | None = None,
    ) -> None:
        self.embedding_similarity = embedding_similarity

    def compare(
        self,
        left_id: str,
        right_id: str,
        left_value: str,
        right_value: str,
        *,
        aliases: tuple[str, ...] = (),
        historical_match: bool = False,
        structural_score: float | None = None,
    ) -> tuple[Similarity, ...]:
        left = self._normalize(left_value)
        right = self._normalize(right_value)
        values: list[Similarity] = []
        if left == right and left:
            values.append(self._item(left_id, right_id, "exact", 1.0, "Normalized values are identical."))
        if right in {self._normalize(item) for item in aliases}:
            values.append(self._item(left_id, right_id, "alias", 0.98, "An approved alias matches."))
        semantic = self._token_similarity(left, right)
        values.append(self._item(left_id, right_id, "semantic", semantic, "Deterministic token overlap."))
        if historical_match:
            values.append(self._item(left_id, right_id, "historical", 0.95, "Canonical identity matched historical context."))
        if structural_score is not None:
            values.append(self._item(
                left_id, right_id, "structural",
                max(0.0, min(1.0, structural_score)),
                "Document graph structures were compared.",
            ))
        if self.embedding_similarity is not None:
            values.append(self._item(
                left_id, right_id, "embedding",
                max(0.0, min(1.0, self.embedding_similarity(left_value, right_value))),
                "Optional embedding adapter supplied a similarity score.",
            ))
        return tuple(values)

    @staticmethod
    def best(values: tuple[Similarity, ...]) -> Similarity | None:
        return max(values, key=lambda item: item.score, default=None)

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(str(value).casefold().split())

    @staticmethod
    def _token_similarity(left: str, right: str) -> float:
        left_tokens = set(left.split())
        right_tokens = set(right.split())
        jaccard = len(left_tokens & right_tokens) / len(left_tokens | right_tokens) if left_tokens | right_tokens else 0.0
        return round(max(jaccard, SequenceMatcher(None, left, right).ratio()), 6)

    @staticmethod
    def _item(left_id: str, right_id: str, strategy: str, score: float, explanation: str) -> Similarity:
        return Similarity(
            f"{strategy}:{left_id}:{right_id}",
            left_id,
            right_id,
            strategy,
            score,
            (left_id, right_id),
            explanation,
        )

