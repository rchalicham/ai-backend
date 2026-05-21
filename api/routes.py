from fastapi import APIRouter, HTTPException, Request

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


router = APIRouter()
embedding_service = EmbeddingService()
qdrant_service = QdrantService()
graph_service = GraphService()
llm_service = LLMService()
donut_receipt_service = DonutReceiptService()


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
    try:
        image_bytes = donut_receipt_service.decode_base64_image(payload.image_base64)
        if not image_bytes and payload.image_url:
            image_bytes = await donut_receipt_service.fetch_image_url(payload.image_url)
        donut_json = await donut_receipt_service.analyze_image_bytes(image_bytes)
        donut_json = donut_receipt_service.consolidate_receipt_rows(
            donut_json,
            raw_text=payload.raw_text,
            lines=payload.lines,
            ocr_blocks=payload.ocr_blocks,
            parser_json=payload.parser_json,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DonutUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to fetch or process receipt image: {exc}") from exc

    semantic_parser_json = {
        **payload.parser_json,
        **({
            "company": donut_json.get("merchant", ""),
            "storeName": donut_json.get("merchant", ""),
            "date": donut_json.get("date", ""),
            "purchaseDate": donut_json.get("date", ""),
            "items": donut_json.get("items", []),
            "subtotal": donut_json.get("subtotal", ""),
            "tax": donut_json.get("tax", ""),
            "total": donut_json.get("total", ""),
            "documentUnderstanding": donut_json,
        } if donut_json.get("available") else {"documentUnderstanding": donut_json}),
    }
    semantic = llm_service.receipt_intelligence.to_structured_json(
        raw_text=payload.raw_text,
        lines=payload.lines,
        parser_json=semantic_parser_json,
        ocr_variants=payload.ocr_variants,
        ocr_blocks=payload.ocr_blocks,
        ocr_engine=payload.ocr_engine or "donut+ocr",
    )
    if not payload.run_llama:
        return {"donut": donut_json, "semantic": semantic, "llama": None}
    llama = await llm_service.structure_receipt(
        raw_text=payload.raw_text or "\n".join(payload.lines),
        lines=payload.lines,
        ocr_blocks=payload.ocr_blocks,
        parser_json=semantic_parser_json,
        ocr_engine=payload.ocr_engine or "donut+ocr",
        ocr_variants=payload.ocr_variants,
    )
    return {"donut": donut_json, "semantic": semantic, "llama": llama}


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
    try:
        donut_json = await donut_receipt_service.analyze_image_bytes(image_bytes)
        donut_json = donut_receipt_service.consolidate_receipt_rows(
            donut_json,
            raw_text=raw_text,
            lines=lines,
            parser_json={},
        )
    except DonutUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    parser_json = {
        "company": donut_json.get("merchant", ""),
        "storeName": donut_json.get("merchant", ""),
        "date": donut_json.get("date", ""),
        "purchaseDate": donut_json.get("date", ""),
        "items": donut_json.get("items", []),
        "subtotal": donut_json.get("subtotal", ""),
        "tax": donut_json.get("tax", ""),
        "total": donut_json.get("total", ""),
        "documentUnderstanding": donut_json,
    }
    semantic = llm_service.receipt_intelligence.to_structured_json(
        raw_text=raw_text,
        lines=lines,
        parser_json=parser_json,
        ocr_engine="donut-upload",
    )
    return {"donut": donut_json, "semantic": semantic}
