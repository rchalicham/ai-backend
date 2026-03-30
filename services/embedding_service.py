from __future__ import annotations

import math
import os
from collections import Counter
from typing import List

from sentence_transformers import SentenceTransformer


class EmbeddingService:
    def __init__(
        self,
        model_name: str | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ):
        self.model_name = model_name or os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        self.chunk_size = chunk_size or int(os.getenv("CHUNK_SIZE", "800"))
        self.chunk_overlap = chunk_overlap or int(os.getenv("CHUNK_OVERLAP", "120"))
        self.fallback_dimension = int(os.getenv("EMBEDDING_FALLBACK_DIMENSION", "384"))
        self._model: SentenceTransformer | None = None
        self._use_fallback = False

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            try:
                self._model = SentenceTransformer(self.model_name, device="cpu")
            except Exception:
                self._use_fallback = True
                raise
        return self._model

    def embedding_dimension(self) -> int:
        if self._use_fallback:
            return self.fallback_dimension
        return int(self.model.get_sentence_embedding_dimension())

    def chunk_text(self, text: str) -> List[str]:
        normalized = " ".join((text or "").split())
        if not normalized:
            return []
        if len(normalized) <= self.chunk_size:
            return [normalized]

        chunks: List[str] = []
        start = 0
        step = max(1, self.chunk_size - self.chunk_overlap)
        while start < len(normalized):
            end = min(len(normalized), start + self.chunk_size)
            if end < len(normalized):
                split_at = normalized.rfind(" ", start, end)
                if split_at > start + (self.chunk_size // 2):
                    end = split_at
            chunk = normalized[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= len(normalized):
                break
            start = max(start + step, end - self.chunk_overlap)
        return chunks

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        if self._use_fallback:
            return [self._fallback_embed(text) for text in texts]

        try:
            vectors = self.model.encode(texts, normalize_embeddings=True)
            return [vector.tolist() for vector in vectors]
        except Exception:
            self._use_fallback = True
            return [self._fallback_embed(text) for text in texts]

    def _fallback_embed(self, text: str) -> List[float]:
        tokens = [token.lower() for token in (text or "").split() if token.strip()]
        if not tokens:
            return [0.0] * self.fallback_dimension

        counts = Counter(tokens)
        vector = [0.0] * self.fallback_dimension
        for token, count in counts.items():
            index = hash(token) % self.fallback_dimension
            vector[index] += float(count)

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return vector
        return [value / norm for value in vector]
