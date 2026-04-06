import asyncio
import os
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def install_service_stubs():
    embedding_module = types.ModuleType("services.embedding_service")

    class EmbeddingService:
        def __init__(self):
            self.model_name = "stub"

        def chunk_text(self, text):
            return [text] if text else []

        def embed_texts(self, texts):
            return [[0.0] for _ in texts]

    embedding_module.EmbeddingService = EmbeddingService
    sys.modules["services.embedding_service"] = embedding_module

    qdrant_module = types.ModuleType("services.qdrant_service")

    class QdrantService:
        def __init__(self):
            self.collection_name = "test_chunks"

        def index_document_chunks(self, **_kwargs):
            return 0

        def search_chunks(self, **_kwargs):
            return []

    qdrant_module.QdrantService = QdrantService
    sys.modules["services.qdrant_service"] = qdrant_module

    graph_module = types.ModuleType("services.graph_service")

    class GraphService:
        def create_entity(self, entity_id, name=None):
            return {"id": entity_id, "name": name}

        def create_document(self, document_id, name=None):
            return {"id": document_id, "name": name}

        def create_relationship(self, **kwargs):
            return {"relationship": kwargs["relationship_type"]}

        def get_related_data(self, entity_id):
            return {"entity": {"id": entity_id}, "relationships": []}

    graph_module.GraphService = GraphService
    sys.modules["services.graph_service"] = graph_module

    llm_module = types.ModuleType("services.llm_service")

    class LLMService:
        async def ask(self, question, chunks, graph_context):
            return f"stub answer for {question}"

        async def suggest_template(self, **_kwargs):
            return {"template_id": "stub_template_v1"}

        async def warmup(self):
            return None

    llm_module.LLMService = LLMService
    sys.modules["services.llm_service"] = llm_module


install_service_stubs()

from fastapi import HTTPException

from models.schemas import AskRequest, CreateRelationshipRequest, IndexRequest, TemplateSuggestRequest
from api import routes
from main import health


class AiBackendRouteTests(unittest.TestCase):

    def test_health_returns_ok(self):
        self.assertEqual(health(), {"status": "ok"})

    def test_index_document_returns_indexing_summary(self):
        payload = IndexRequest(
            document_id="doc-1",
            entity_id="entity-1",
            file_url="https://files/doc-1.pdf",
            text="alpha beta gamma",
            metadata={"name": "Spec"},
        )

        with patch.object(routes.embedding_service, "chunk_text", return_value=["alpha beta", "gamma"]) as chunk_text, \
             patch.object(routes.embedding_service, "embed_texts", return_value=[[0.1, 0.2], [0.3, 0.4]]) as embed_texts, \
             patch.object(routes.graph_service, "create_entity", return_value={"id": "entity-1"}) as create_entity, \
             patch.object(routes.graph_service, "create_document", return_value={"id": "doc-1"}) as create_document, \
             patch.object(routes.graph_service, "create_relationship", return_value={"relationship": "HAS_DOCUMENT"}) as create_relationship, \
             patch.object(routes.qdrant_service, "index_document_chunks", return_value=2) as index_chunks:
            response = routes.index_document(payload)

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["chunks_indexed"], 2)
        self.assertEqual(response["document_id"], "doc-1")
        self.assertEqual(response["collection"], routes.qdrant_service.collection_name)
        chunk_text.assert_called_once_with("alpha beta gamma")
        embed_texts.assert_called_once_with(["alpha beta", "gamma"])
        create_entity.assert_called_once_with("entity-1")
        create_document.assert_called_once()
        create_relationship.assert_called_once()
        index_chunks.assert_called_once()

    def test_index_document_rejects_empty_text(self):
        payload = IndexRequest(document_id="doc-1", entity_id="entity-1", text=" ", metadata={})

        with patch.object(routes.embedding_service, "chunk_text", return_value=[]):
            with self.assertRaises(HTTPException) as error:
                routes.index_document(payload)

        self.assertEqual(error.exception.status_code, 400)

    def test_create_relationship_maps_domain_errors_to_http_400(self):
        payload = CreateRelationshipRequest(
            from_id="entity-1",
            from_type="Entity",
            to_id="doc-1",
            to_type="Document",
            relationship_type="HAS_DOCUMENT",
        )

        with patch.object(routes.graph_service, "create_relationship", side_effect=ValueError("bad link")):
            with self.assertRaises(HTTPException) as error:
                routes.create_relationship(payload)

        self.assertEqual(error.exception.status_code, 400)
        self.assertEqual(error.exception.detail, "bad link")

    def test_ask_question_requires_non_blank_question(self):
        payload = AskRequest(question="   ", entity_id="entity-1", top_k=3)

        with self.assertRaises(HTTPException) as error:
            asyncio.run(routes.ask_question(payload))

        self.assertEqual(error.exception.status_code, 400)

    def test_ask_question_returns_answer_with_chunks_and_graph(self):
        payload = AskRequest(question="What changed?", entity_id="entity-1", top_k=2)

        with patch.object(routes.embedding_service, "embed_texts", return_value=[[0.9, 0.1]]) as embed_texts, \
             patch.object(routes.qdrant_service, "search_chunks", return_value=[{"text": "chunk-1"}]) as search_chunks, \
             patch.object(routes.graph_service, "get_related_data", return_value={"relationships": []}) as get_related_data, \
             patch.object(routes.llm_service, "ask", new=AsyncMock(return_value="Answer text")) as ask:
            response = asyncio.run(routes.ask_question(payload))

        self.assertEqual(response["answer"], "Answer text")
        self.assertEqual(response["chunks"], [{"text": "chunk-1"}])
        embed_texts.assert_called_once_with(["What changed?"])
        search_chunks.assert_called_once()
        get_related_data.assert_called_once_with("entity-1")
        ask.assert_awaited_once()

    def test_template_suggest_requires_template_name(self):
        payload = TemplateSuggestRequest(template_name="   ", description="test")

        with self.assertRaises(HTTPException) as error:
            asyncio.run(routes.template_suggest(payload))

        self.assertEqual(error.exception.status_code, 400)

    def test_template_suggest_delegates_to_llm_service(self):
        payload = TemplateSuggestRequest(template_name="Member Access", description="Permissions template")

        with patch.object(routes.llm_service, "suggest_template", new=AsyncMock(return_value={"template_id": "member_access_v1"})) as suggest_template:
            response = asyncio.run(routes.template_suggest(payload))

        self.assertEqual(response["template_id"], "member_access_v1")
        suggest_template.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
