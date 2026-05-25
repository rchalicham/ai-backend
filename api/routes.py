import os

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


def _needs_ocr_fallback(donut_json: dict, raw_text: str = "", lines: list | None = None, ocr_blocks: list | None = None) -> bool:
    if str(raw_text or "").strip() or any(str(line).strip() for line in (lines or [])) or ocr_blocks:
        return False
    if not donut_json.get("available"):
        return True
    if str(donut_json.get("rawText") or "").strip():
        return False
    if donut_json.get("items"):
        return False
    return True


def _merge_ocr_fallback(raw_text: str, lines: list, ocr_blocks: list, ocr_result: dict) -> tuple[str, list, list]:
    next_raw_text = raw_text or str(ocr_result.get("rawText") or "")
    next_lines = lines or ocr_result.get("rawLines") or []
    next_blocks = ocr_blocks or ocr_result.get("ocrBlocks") or []
    return next_raw_text, next_lines, next_blocks


def _public_image_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.lower().startswith(("http://", "https://")):
        return raw
    base_url = os.getenv("OPENGRIT_PUBLIC_IMAGE_BASE_URL", "https://opengrit.com/images").rstrip("/")
    return f"{base_url}/{raw.lstrip('/')}"


def _flatten_receipt_response(receipt: dict, *, source: str = "ai-backend") -> dict:
    data = receipt.get("llama") or receipt.get("semantic") or receipt
    semantic = receipt.get("semantic") if isinstance(receipt.get("semantic"), dict) else {}
    donut = receipt.get("donut") if isinstance(receipt.get("donut"), dict) else {}
    items = data.get("items") or semantic.get("items") or donut.get("items") or []
    raw_text = data.get("rawText") or semantic.get("rawText") or donut.get("rawText") or ""
    raw_lines = data.get("rawLines") or semantic.get("rawLines") or raw_text.splitlines()
    return {
        "company": data.get("company") or data.get("storeName") or semantic.get("company") or donut.get("merchant") or "",
        "storeName": data.get("storeName") or data.get("company") or semantic.get("storeName") or donut.get("merchant") or "",
        "storeAddress": data.get("storeAddress") or semantic.get("storeAddress") or donut.get("address") or "",
        "date": data.get("date") or data.get("purchaseDate") or semantic.get("date") or donut.get("date") or "",
        "purchaseDate": data.get("purchaseDate") or data.get("date") or semantic.get("purchaseDate") or donut.get("date") or "",
        "subTotal": data.get("subTotal") or data.get("subtotal") or semantic.get("subTotal") or semantic.get("subtotal") or "",
        "subtotal": data.get("subtotal") or data.get("subTotal") or semantic.get("subtotal") or semantic.get("subTotal") or "",
        "tax": data.get("tax") or semantic.get("tax") or donut.get("tax") or "",
        "tip": data.get("tip") or semantic.get("tip") or "0",
        "total": data.get("total") or semantic.get("total") or donut.get("total") or "",
        "cardUsed": data.get("cardUsed") or data.get("cardBrand") or semantic.get("cardUsed") or "",
        "lastFour": data.get("lastFour") or data.get("cardLastFour") or semantic.get("lastFour") or "",
        "items": items,
        "rawText": raw_text,
        "rawLines": raw_lines,
        "ocrVariants": data.get("ocrVariants") or semantic.get("ocrVariants") or [],
        "documentUnderstanding": donut or data.get("documentUnderstanding") or {},
        "meta": {
            "ocrEngine": data.get("ocrEngine") or semantic.get("ocrEngine") or source,
            "source": source,
            "legacyCompatibility": True,
        },
    }


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
            ocr_engine=payload.ocr_engine or "donut+ocr-agent",
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
            ocr_engine="donut-upload-agent",
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


@router.post("/imageTranslation/")
async def legacy_image_translation(payload: dict):
    """Compatibility endpoint for the removed Django OCR service.

    Shellspy still posts to `/imageTranslation/` through its configured
    receipt URL. Keep that contract while routing the work through the
    FastAPI receipt intelligence engine.
    """
    raw_text = str(payload.get("rawText") or payload.get("raw_text") or "")
    lines = payload.get("lines") or payload.get("rawLines") or []
    if not isinstance(lines, list):
        lines = [str(lines)]
    ocr_blocks = payload.get("ocr_blocks") or payload.get("ocrBlocks") or []
    if not isinstance(ocr_blocks, list):
        ocr_blocks = []
    parser_json = payload.get("parser_json") or payload.get("parserJson") or {}
    if not isinstance(parser_json, dict):
        parser_json = {}

    has_structured_text = raw_text.strip() or any(str(line).strip() for line in lines) or ocr_blocks
    if has_structured_text:
        semantic = llm_service.receipt_intelligence.to_structured_json(
            raw_text=raw_text,
            lines=lines,
            parser_json=parser_json,
            ocr_blocks=ocr_blocks,
            ocr_engine=str(payload.get("ocrEngine") or payload.get("ocr_engine") or "legacy-imageTranslation"),
        )
        return _flatten_receipt_response(semantic, source="ai-backend-semantic")

    image_url = _public_image_url(str(payload.get("image_url") or payload.get("imageUrl") or payload.get("url") or ""))
    if not image_url:
        raise HTTPException(status_code=400, detail="url, image_url, rawText, lines, or ocr_blocks is required.")
    result = await receipt_document_understanding(
        ReceiptDocumentUnderstandingRequest(
            image_url=image_url,
            parser_json=parser_json,
            ocr_engine=str(payload.get("ocrEngine") or payload.get("ocr_engine") or "legacy-imageTranslation"),
            run_llama=True,
        )
    )
    return _flatten_receipt_response(result, source="ai-backend-document-understanding")


@router.post("/pdf/")
async def legacy_pdf_translation(payload: dict):
    return await legacy_image_translation(payload)
