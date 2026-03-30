from __future__ import annotations

import os
import uuid
from typing import List

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams

class QdrantService:
    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        collection_name: str | None = None,
    ):
        self.host = host or os.getenv("QDRANT_HOST", "localhost")
        self.port = port or int(os.getenv("QDRANT_PORT", "6333"))
        self.collection_name = collection_name or os.getenv("QDRANT_COLLECTION", "document_chunks")
        self.client = QdrantClient(host=self.host, port=self.port)

    def ensure_collection(self, vector_size: int) -> None:
        collections = self.client.get_collections().collections
        if any(collection.name == self.collection_name for collection in collections):
            return
        try:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=Distance.COSINE,
                ),
            )
        except UnexpectedResponse as exc:
            if exc.status_code != 409:
                raise

    def index_document_chunks(
        self,
        document_id: str,
        entity_id: str,
        file_url: str | None,
        metadata: dict | None,
        chunks: List[str],
        vectors: List[List[float]],
    ) -> int:
        if not vectors:
            return 0
        self.ensure_collection(vector_size=len(vectors[0]))
        points = []
        for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{document_id}:{entity_id}:{index}:{chunk}"))
            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "document_id": document_id,
                        "entity_id": entity_id,
                        "file_url": file_url,
                        "chunk_index": index,
                        "text": chunk,
                        "metadata": metadata or {},
                    },
                )
            )
        if points:
            self.client.upsert(collection_name=self.collection_name, points=points)
        return len(points)

    def search_chunks(
        self,
        query_vector: List[float],
        entity_id: str,
        top_k: int = 5,
    ) -> List[dict]:
        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=top_k,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="entity_id",
                        match=MatchValue(value=entity_id),
                    )
                ]
            ),
        )
        return [
            {
                "id": result.id,
                "score": result.score,
                **(result.payload or {}),
            }
            for result in results
        ]
