from fastapi import APIRouter, HTTPException

from models.schemas import AskRequest, CreateRelationshipRequest, IndexRequest, ReceiptStructureRequest, TemplateSuggestRequest
from services.embedding_service import EmbeddingService
from services.graph_service import GraphService
from services.llm_service import LLMService
from services.qdrant_service import QdrantService


router = APIRouter()
embedding_service = EmbeddingService()
qdrant_service = QdrantService()
graph_service = GraphService()
llm_service = LLMService()


@router.post("/index")
def index_document(payload: IndexRequest):
    chunks = embedding_service.chunk_text(payload.text)
    if not chunks:
        raise HTTPException(status_code=400, detail="No indexable text was provided.")

    embeddings = embedding_service.embed_texts(chunks)
    entity = graph_service.create_entity(payload.entity_id)
    document = graph_service.create_document(
        payload.document_id,
        name=payload.metadata.get("name") or payload.file_url,
    )
    relationship = graph_service.create_relationship(
        from_id=payload.entity_id,
        from_type="Entity",
        to_id=payload.document_id,
        to_type="Document",
        relationship_type="HAS_DOCUMENT",
    )
    stored = qdrant_service.index_document_chunks(
        document_id=payload.document_id,
        entity_id=payload.entity_id,
        file_url=payload.file_url,
        metadata=payload.metadata,
        chunks=chunks,
        vectors=embeddings,
    )
    return {
        "status": "ok",
        "document_id": payload.document_id,
        "entity_id": payload.entity_id,
        "file_url": payload.file_url,
        "metadata": payload.metadata,
        "chunks_indexed": stored,
        "collection": qdrant_service.collection_name,
        "graph": {
            "entity": entity,
            "document": document,
            "relationship": relationship,
        },
    }


@router.post("/create-relationship")
def create_relationship(payload: CreateRelationshipRequest):
    try:
        created = graph_service.create_relationship(
            from_id=payload.from_id,
            from_type=payload.from_type,
            to_id=payload.to_id,
            to_type=payload.to_type,
            relationship_type=payload.relationship_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"status": "ok", **created}


@router.post("/ask")
async def ask_question(payload: AskRequest):
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required.")

    query_vector = embedding_service.embed_texts([question])[0]
    chunks = qdrant_service.search_chunks(
        query_vector=query_vector,
        entity_id=payload.entity_id,
        top_k=payload.top_k,
    )
    graph_context = graph_service.get_related_data(payload.entity_id)
    answer = await llm_service.ask(
        question=question,
        chunks=chunks,
        graph_context=graph_context,
    )
    return {
        "answer": answer,
        "chunks": chunks,
        "graph": graph_context,
    }


@router.post("/template-suggest")
async def template_suggest(payload: TemplateSuggestRequest):
    template_name = payload.template_name.strip()
    if not template_name:
        raise HTTPException(status_code=400, detail="template_name is required.")
    return await llm_service.suggest_template(
        template_name=template_name,
        description=payload.description,
        domain_id=payload.domain_id,
        domain_type=payload.domain_type,
        response_mode=payload.response_mode,
    )


@router.post("/receipt/structure")
async def structure_receipt(payload: ReceiptStructureRequest):
    raw_text = payload.raw_text.strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="raw_text is required.")
    return await llm_service.structure_receipt(
        raw_text=raw_text,
        lines=payload.lines,
        parser_json=payload.parser_json,
        ocr_engine=payload.ocr_engine,
        ocr_variants=payload.ocr_variants,
    )
