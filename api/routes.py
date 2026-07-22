from fastapi import APIRouter, HTTPException, Request, Response

from models.schemas import (
    AskRequest,
    CreateRelationshipRequest,
    IndexRequest,
    ReceiptDocumentUnderstandingRequest,
    ReceiptSemanticRequest,
    ReceiptStructureRequest,
    TemplateSuggestRequest,
)
from services.donut_receipt_service import DonutReceiptService, DonutUnavailableError
from services.embedding_service import EmbeddingService
from services.graph_service import GraphService
from services.llm_service import LLMService
from services.qdrant_service import QdrantService
from services.receipt_agent_orchestrator import ReceiptAgentOrchestrator
from services.receipt_image_isolation import ReceiptImageIsolationService
from services.receipt_ocr_service import ReceiptOcrService


router = APIRouter()
embedding_service = EmbeddingService()
qdrant_service = QdrantService()
graph_service = GraphService()
llm_service = LLMService()
donut_receipt_service = DonutReceiptService()
receipt_image_isolation_service = ReceiptImageIsolationService()
receipt_ocr_service = ReceiptOcrService()
receipt_agent_orchestrator = ReceiptAgentOrchestrator(
    donut_receipt_service=donut_receipt_service,
    receipt_image_isolation_service=receipt_image_isolation_service,
    receipt_ocr_service=receipt_ocr_service,
    llm_service=llm_service,
)


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
        ocr_blocks=payload.ocr_blocks,
        parser_json=payload.parser_json,
        ocr_engine=payload.ocr_engine,
        ocr_variants=payload.ocr_variants,
    )


@router.post("/receipt/semantic")
async def semantic_receipt(payload: ReceiptSemanticRequest):
    raw_text = payload.raw_text.strip()
    has_lines = any(str(line).strip() for line in payload.lines)
    has_boxes = any(
        isinstance(box, dict) and str(box.get("text") or box.get("value") or "").strip()
        for box in payload.ocr_blocks
    )
    if not raw_text and not has_lines and not has_boxes:
        raise HTTPException(status_code=400, detail="raw_text, lines, or ocr_blocks is required.")
    return llm_service.receipt_intelligence.to_structured_json(
        raw_text=raw_text,
        lines=payload.lines,
        parser_json=payload.parser_json,
        ocr_variants=payload.ocr_variants,
        ocr_blocks=payload.ocr_blocks,
        ocr_engine=payload.ocr_engine,
    )


@router.post("/receipt/document-understanding")
async def receipt_document_understanding(payload: ReceiptDocumentUnderstandingRequest):
    image_bytes = b""
    try:
        image_bytes = donut_receipt_service.decode_base64_image(payload.image_base64)
        if not image_bytes and payload.image_url:
            image_bytes = await donut_receipt_service.fetch_image_url(payload.image_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DonutUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to fetch or process receipt image: {exc}") from exc
    try:
        return await receipt_agent_orchestrator.process(
            image_bytes=image_bytes,
            raw_text=payload.raw_text,
            lines=payload.lines,
            ocr_blocks=payload.ocr_blocks,
            parser_json=payload.parser_json,
            ocr_engine=payload.ocr_engine or "receipt-agent",
            ocr_variants=payload.ocr_variants,
            run_llama=payload.run_llama,
        )
    except DonutUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to process receipt through agent: {exc}") from exc


@router.post("/receipt/document-understanding/upload")
async def receipt_document_understanding_upload(request: Request):
    try:
        form = await request.form()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="multipart/form-data with a processed receipt image is required.") from exc
    upload = form.get("file")
    if upload is None or not hasattr(upload, "read"):
        raise HTTPException(status_code=400, detail="file is required.")
    image_bytes = await upload.read()
    raw_text = str(form.get("raw_text") or "")
    lines = [line for line in raw_text.splitlines() if line.strip()]
    ocr_blocks = []
    try:
        return await receipt_agent_orchestrator.process(
            image_bytes=image_bytes,
            raw_text=raw_text,
            lines=lines,
            ocr_blocks=ocr_blocks,
            parser_json={},
            ocr_engine="receipt-upload-agent",
            run_llama=False,
        )
    except DonutUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to process receipt upload through agent: {exc}") from exc


@router.post("/receipt/image/isolate")
async def isolate_receipt_image(request: Request):
    content_type = request.headers.get("content-type", "")
    image_bytes = b""
    if "multipart/form-data" in content_type:
        try:
            form = await request.form()
        except Exception as exc:
            raise HTTPException(status_code=400, detail="multipart/form-data with a receipt image is required.") from exc
        upload = form.get("file")
        if upload is not None and hasattr(upload, "read"):
            image_bytes = await upload.read()
    else:
        image_bytes = await request.body()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="receipt image bytes are required.")
    result = receipt_image_isolation_service.isolate(image_bytes)
    return Response(
        content=result.image_bytes,
        media_type="image/jpeg",
        headers={
            "X-Receipt-Isolation-Applied": str(result.diagnostics.get("applied", False)).lower(),
            "X-Receipt-Isolated": str(result.diagnostics.get("receiptIsolated", False)).lower(),
            "X-Receipt-Background-Removed": str(result.diagnostics.get("backgroundRemoved", False)).lower(),
        },
    )
