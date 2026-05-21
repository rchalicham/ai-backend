# Enterprise Receipt Intelligence Architecture

## Processing Architecture

```text
React scanner
  -> camera frame
  -> OpenCV edge detection
  -> quadrilateral validation
  -> perspective flattening
  -> orientation correction
  -> thermal receipt enhancement
  -> quality gate
  -> processed image only
  -> FastAPI document understanding
  -> Donut CORD-v2 extraction
  -> PaddleOCR boxes/text
  -> ReceiptIntelligencePipeline
  -> Llama semantic reasoning
  -> MongoDB receipt document
  -> Qdrant embeddings
  -> Neo4j receipt graph
```

## Sequence

```text
User
  -> Scan receipt in React
  -> Browser validates edges and quality
  -> Browser uploads processed scan
  -> FastAPI runs Donut when enabled
  -> FastAPI reconstructs OCR rows from bounding boxes
  -> FastAPI validates item subtotal/tax/total consistency
  -> Llama receives structured JSON, not noisy flat OCR text
  -> Caller persists receipt JSON, vectors, and graph relationships
```

## Production Services

- `services/donut_receipt_service.py`
  Lazy-loads `naver-clova-ix/donut-base-finetuned-cord-v2` only when `DONUT_RECEIPT_ENABLED=true`.
- `services/receipt_intelligence.py`
  Performs OCR line grouping, duplicate suppression, item parsing, quantity extraction, merchant normalization, validation, confidence scoring, table reconstruction, and graph generation.
- `api/routes.py`
  Exposes deterministic `/receipt/semantic`, JSON-based `/receipt/document-understanding`, and multipart `/receipt/document-understanding/upload`.

## Runtime Contracts

`POST /receipt/semantic`

```json
{
  "raw_text": "",
  "lines": [],
  "ocr_blocks": [
    { "text": "TOTAL", "x": 40, "y": 140, "width": 60, "height": 14, "confidence": 0.94 }
  ],
  "parser_json": {},
  "ocr_engine": "paddleocr",
  "ocr_variants": []
}
```

`POST /receipt/document-understanding`

```json
{
  "image_base64": "processed-scan-base64",
  "raw_text": "",
  "lines": [],
  "ocr_blocks": [],
  "parser_json": {},
  "run_llama": true
}
```

## Browser Scanner Requirements

The React scanner must not upload raw camera photos. It must produce a processed scan using:

1. grayscale
2. gaussian blur
3. canny edge detection
4. contour/quadrilateral detection
5. perspective transform
6. orientation correction
7. adaptive thresholding
8. denoise/sharpen
9. OCR readability quality gate

## Deployment Notes

For CPU/local development, Donut remains disabled and the backend still imports cleanly.

For GPU model containers:

```text
DONUT_RECEIPT_ENABLED=true
DONUT_RECEIPT_MODEL=naver-clova-ix/donut-base-finetuned-cord-v2
DONUT_RECEIPT_MAX_CONCURRENCY=2
DONUT_RECEIPT_MAX_NEW_TOKENS=768
```

Install model dependencies in the AI image:

```text
torch
transformers
Pillow
accelerate
```

Scale Donut separately from Llama/OCR workers when GPU demand grows. Keep FastAPI request workers thin; queue large production scans through the platform queue and persist intermediate artifacts for retry/debugging.
