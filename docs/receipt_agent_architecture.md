# Receipt Intelligence And Agent Architecture

## Purpose

OpenGrit receipt scanning is designed as a hybrid deterministic and agentic document-understanding pipeline. The deterministic layers do the stable work: image isolation, OCR row reconstruction, table parsing, merchant/date/payment/entity extraction, arithmetic validation, and confidence scoring. The agentic layer runs bounded autonomous retries, reconciles competing candidates, ranks extraction risk, and prepares receipts for human review in the unprocessed queue.

The key design rule is: AI can assist and retry, but receipt facts must be supported by OCR, geometry, arithmetic, or reviewable confidence traces.

## Runtime Flow

```text
browser scanner / upload
  -> processed receipt image
  -> FastAPI /receipt/document-understanding or /receipt/document-understanding/upload
  -> ReceiptAgentOrchestrator
      -> baseline document understanding attempt
      -> receipt image isolation attempt
      -> high-contrast OCR retry attempt
      -> adaptive-threshold OCR retry attempt
      -> Donut when enabled
      -> OCR fallback when Donut has no usable text
      -> ReceiptIntelligencePipeline
      -> LLM structuring when requested
      -> merchant confidence pass
      -> financial item candidate pass
      -> best-attempt selection
      -> human-review task generation
  -> Java ImageService persistence
  -> unprocessed receipt review UI
  -> user approves/fixes receipt
  -> processed company/address/items/entities
```

## Main Components

### Browser Scanner

The browser scanner should send a processed scan, not a raw camera frame. The intended browser processing sequence is:

1. grayscale
2. blur
3. edge detection
4. quadrilateral receipt detection
5. perspective transform
6. orientation correction
7. threshold/denoise/sharpen
8. readability quality gate

Relevant frontend entry points:

- `ShellSpyWebUI/src/features/documentScanner/services/ocrScanApi.js`
- `ShellSpyWebUI/src/features/documentScanner/components/OpenSourceDocumentScanner.jsx`
- `ShellSpyWebUI/src/components/reusables/Upload.js`

### FastAPI Routes

Relevant backend routes:

- `POST /receipt/semantic`
- `POST /receipt/document-understanding`
- `POST /receipt/document-understanding/upload`
- `POST /receipt/image/isolate`

The production path is `/receipt/document-understanding`, delegated to `ReceiptAgentOrchestrator`.

### ReceiptAgentOrchestrator

File:

- `ai-backend/services/receipt_agent_orchestrator.py`

Responsibilities:

- run bounded autonomous attempts
- execute image retry variants
- compare extraction attempts
- enforce merchant-confidence rules
- apply financial item candidate selection
- produce `receiptAgent`
- produce `humanReview`
- produce `postScanTasks`
- preserve legacy response shape: `donut`, `semantic`, `llama`

Bounded attempt strategy:

```text
attempt 0: baseline_document_understanding
attempt 1: isolate_receipt_then_ocr
attempt 2: opencv_preprocess_high_contrast
attempt 3: deskew_and_adaptive_threshold
```

The default max attempts is controlled by:

```text
RECEIPT_AGENT_MAX_ATTEMPTS=3
RECEIPT_AGENT_ACCEPT_CONFIDENCE=0.82
RECEIPT_AGENT_REVIEW_CONFIDENCE=0.78
```

### ReceiptIntelligencePipeline

File:

- `ai-backend/services/receipt_intelligence.py`

Responsibilities:

- reconstruct OCR rows from bounding boxes
- suppress duplicate OCR passes
- normalize merchants
- parse semantic item/fact candidates
- perform OCR-box table reconstruction
- extract temporal entities
- extract receipt entities
- build semantic blocks
- build layout JSON
- build receipt graph
- validate financial consistency
- score confidence
- generate retry plans

## Detailed Backend Pipeline

### 1. Image Isolation

File:

- `ai-backend/services/receipt_image_isolation.py`

The isolation service uses OpenCV to find the physical receipt, warp it, remove background, and enhance pixels for OCR/model input. If no contour is found, it still performs full-image enhancement instead of forwarding an unprocessed raw image.

Output includes:

- `receiptIsolated`
- `backgroundRemoved`
- contour diagnostics
- selected quadrilateral
- section-boundary hints

### 2. Donut Document Understanding

File:

- `ai-backend/services/donut_receipt_service.py`

Donut is optional and lazy-loaded. It is disabled by default for CPU/local development.

Important env vars:

```text
DONUT_RECEIPT_ENABLED=true
DONUT_RECEIPT_MODEL=naver-clova-ix/donut-base-finetuned-cord-v2
DONUT_RECEIPT_MAX_CONCURRENCY=2
DONUT_RECEIPT_MAX_NEW_TOKENS=768
```

Donut output is consolidated by `ReceiptRowConsolidationPipeline` before being passed into semantic extraction.

### 3. OCR Fallback

File:

- `ai-backend/services/receipt_ocr_service.py`

When Donut is unavailable or returns no usable text/items, the agent runs Tesseract fallback on the current image attempt. It returns:

- raw text
- raw lines
- OCR word blocks
- confidence
- bounding boxes

### 4. OCR Row Reconstruction

Class:

- `ReceiptLineReconstructor`

If OCR boxes exist, rows are rebuilt using page, y-axis clustering, and left-to-right x ordering. If boxes do not exist, the pipeline falls back to supplied lines or raw text.

This step preserves geometry for downstream:

- table reconstruction
- visual hierarchy
- merchant header scoring
- temporal/entity extraction
- row-level diagnostics

### 5. Duplicate Suppression

Class:

- `ReceiptDuplicateSuppressor`

This removes duplicate OCR passes and repeated rows, especially after subtotal/totals markers. It keeps diagnostics showing which row was retained and which was suppressed.

### 6. Section Extraction And State Machine

File:

- `ai-backend/services/receipt_section_engine.py`

Responsibilities:

- split document into header/items/totals/payment/footer states
- lock item parser to item regions
- keep totals/payment/footer out of item extraction
- build table graph
- build candidate item graph
- perform financial reconciliation traces
- expose debug visualizations

Important outputs:

- `sectionExtraction`
- `documentStateMachine`
- `tableGraph`
- `financialReconciliation`
- `debug.rejectedItemRows`
- `debug.rowReconstructionVisualization`
- `debug.tableColumnOverlays`

### 7. OCR-Box Table Reconstruction

Class:

- `ReceiptTableReconstructor`

The table reconstructor now has geometry-aware extraction:

- detects quantity column
- detects item-name column
- detects right-aligned price column
- pairs quantity/name/price by row
- rejects orphan monetary values
- rejects totals/payment/footer rows
- preserves table diagnostics

Output location:

```json
{
  "tables": [
    {
      "id": "items-table",
      "kind": "items",
      "reconstruction": {
        "schemaVersion": "receipt-aligned-table-reconstruction-v1",
        "strategy": "ocr_box_alignment",
        "columnAnchors": {},
        "rows": [],
        "rejectedRows": []
      }
    }
  ]
}
```

### 8. Item Candidate Source Selection

The pipeline compares item candidates from:

- section parser
- aligned OCR table reconstruction
- semantic parser
- external parser JSON / Donut

The selected source is scored by:

- validation success
- item sum vs subtotal/total
- average confidence
- warning penalties

### 9. Agent PASS 3 Financial Candidate Selection

File:

- `ReceiptAgentOrchestrator._reconcile_semantic_item_candidates`

Goal:

Find the smallest valid item set whose sum matches the receipt target.

Rules:

- use receipt item count when available
- prefer subtotal when tax/tip is present
- otherwise target total
- reject totals/payment/footer rows
- reject numeric/code-only names
- reject rows exceeding receipt target
- dedupe same name/amount/qty
- maximize weighted candidate score

Weighted scoring:

```text
arithmetic consistency: 0.45
semantic confidence:    0.25
item count match:       0.15
minimal rows:           0.10
non-item penalty:       0.05
```

Diagnostics:

```json
{
  "receiptAgentPasses": {
    "pass3CandidateSelection": {
      "schemaVersion": "receipt-agent-pass3-v1",
      "strategy": "constraint_based_financial_reconciliation",
      "targetField": "subtotal",
      "expectedItemCount": 3,
      "selectedCount": 3,
      "selectedSum": "21.58",
      "selectedDelta": "0.00",
      "selectedDiagnostics": [],
      "rejectedCandidates": []
    }
  }
}
```

### 10. Merchant Confidence Pass

File:

- `ReceiptAgentOrchestrator._reconcile_merchant_confidence`

Goal:

Prevent merchant hallucinations while preserving OCR-supported merchant values.

Rules:

- prioritize domain names
- prioritize centered header text
- use visual hierarchy scoring
- penalize disclaimer/legal text
- existing normalized merchant traces are capped unless independently verified
- merchant override only when confidence is greater than `0.90`
- preserve raw OCR merchant when uncertain

Diagnostics:

```json
{
  "receiptAgentPasses": {
    "merchantConfidence": {
      "schemaVersion": "receipt-agent-merchant-confidence-v1",
      "selectedMerchant": "Freshthyme",
      "previousMerchant": "Official Rules",
      "rawOcrMerchant": "",
      "confidence": 0.98,
      "source": "domain_name",
      "overrideApplied": true,
      "preservedRawOcr": false,
      "overrideThreshold": 0.9,
      "candidates": []
    }
  }
}
```

### 11. Temporal Entity Extraction

Class:

- `ReceiptIntelligencePipeline._temporal_entities`

Supported formats:

- `MM/DD/YYYY`
- `MM/DD/YY`
- `DD-Mon-YYYY`
- `Mon DD YYYY`
- timestamps with `AM/PM`
- timestamps with seconds

Classification:

- `transactionDate`
- `transactionTime`
- `orderDate`
- `paymentTime`
- `printTime`

Payment-context timestamps such as `CARD PAYMENT 4:32 PM` are classified as `paymentTime`, not purchase date.

### 12. Financial Validation

Class:

- `ReceiptValidationEngine`

Validates:

- item sum vs subtotal
- subtotal + tax + tip vs total

Warnings feed:

- retry plan
- agent risk score
- human review priority

Common warnings:

```text
item_sum_does_not_match_subtotal
subtotal_tax_tip_total_mismatch
```

### 13. Confidence Scoring

Class:

- `ReceiptConfidenceEngine`

Scores:

- OCR confidence
- item extraction completeness
- merchant confidence
- validation confidence
- overall confidence

Agent attempts are scored using semantic, LLM, Donut, and validation signals.

## Human-In-The-Loop Review

The unprocessed receipt UI is the human review queue. The backend produces review metadata; the UI ranks and displays it.

Backend fields:

```json
{
  "humanReview": {
    "required": true,
    "queue": "unprocessed_receipts",
    "reviewMode": "human_in_the_loop",
    "priority": "urgent",
    "riskScore": 92,
    "summary": "Urgent risk: Receipt arithmetic does not reconcile.",
    "reasons": [],
    "actionableExplanations": [],
    "suggestedChecks": []
  }
}
```

Risk priority ranking:

1. arithmetic mismatch
2. low-confidence merchant
3. item-count mismatch
4. missing items
5. overall low confidence
6. retry recommendations

Frontend behavior:

- groups with highest receipt risk appear first
- receipts inside a group are sorted by `riskScore`
- review card shows priority, score, and actions

Relevant frontend file:

- `ShellSpyWebUI/src/components/products/UnProcessed.js`

## Persistence And Java Integration

File:

- `shellspy/src/main/java/com/chalicham/opengrit/service/ImageService.java`
- `shellspy/src/main/java/com/chalicham/opengrit/controller/ImageController.java`
- `shellspy/src/main/java/com/chalicham/opengrit/controller/UploadController.java`

Java receives the AI backend response, compacts receipt intelligence for UI, and persists receipt JSON.

The compaction preserves:

- validation
- confidence
- retry plan
- warnings
- `humanReview`
- `postScanTasks`
- `receiptAgent`

This keeps list views lightweight while still exposing review-critical metadata.

Durable receipt-agent records are also written to Mongo:

- `receipt_agent_jobs`: queueable post-scan tasks from `receiptAgent.postScanTasks`
- `receipt_merchant_memory`: tenant/domain merchant aliases learned from agent output and human corrections
- `receipt_rejected_candidate_rows`: rejected item-row candidates for offline evaluation
- `receipt_correction_feedback`: user correction payloads from the unprocessed review UI
- `receipt_extraction_metrics`: per-receipt extraction risk snapshots

Operational endpoints:

- `GET /main/imgs/receipt-agent/jobs`
- `GET /main/imgs/receipt-agent/metrics`
- `POST /main/imgs/receipt/{id}/correction-feedback`

## Data Contracts

### `/receipt/document-understanding`

Request:

```json
{
  "image_base64": "",
  "image_url": "",
  "raw_text": "",
  "lines": [],
  "ocr_blocks": [],
  "parser_json": {},
  "ocr_engine": "donut+ocr-agent",
  "ocr_variants": [],
  "run_llama": true
}
```

Response:

```json
{
  "donut": {},
  "semantic": {},
  "llama": {},
  "receiptAgent": {}
}
```

### Semantic Receipt Output

Important fields:

```json
{
  "schemaVersion": "receipt-semantic-v1",
  "documentType": "receipt",
  "merchant": "",
  "storeName": "",
  "date": "",
  "purchaseDate": "",
  "transactionDate": "",
  "transactionTime": "",
  "paymentTime": "",
  "items": [],
  "facts": {
    "subtotal": "",
    "tax": "",
    "tip": "",
    "total": ""
  },
  "validation": {},
  "confidence": {},
  "retryPlan": [],
  "receiptAgentPasses": {},
  "humanReview": {},
  "postScanTasks": [],
  "tables": [],
  "layout": {
    "retailRowReconstruction": {}
  },
  "sectionExtraction": {},
  "documentOntology": {},
  "graph": {}
}
```

## Retail Multi-Line Row Reconstruction

Retail receipts often split one item across multiple lines:

- description line without a price
- pricing line with quantity, unit price, and extended price
- optional modifier, discount, size, style, or SKU lines

The table reconstruction layer handles this with `receipt-retail-row-reconstruction-v1`.

Core behavior:

- keeps description-only rows pending
- attaches the next nearby pricing row when vertical proximity and indentation/alignment agree
- detects retail price patterns such as `5 @ 14.99` and `1 @ 29.99`
- extracts `qty`, `unitPrice`, and `extendedPrice`
- validates `qty * unitPrice ~= extendedPrice`
- emits one merged item entity with full product description
- builds a row graph linking item, description line, pricing line, and modifier lines
- exposes pending-row, merged-row, visualization, and arithmetic diagnostics

Diagnostics are available at:

- `layout.retailRowReconstruction`
- `tables[0].reconstruction.retailRowAssembly`
- `confidenceTrace.items[].trace`

This logic is generalized and does not depend on merchant-specific rules.

## Post-Scan Tasks

The agent emits suggested tasks:

- `link_company_address`
- `dedupe_receipt`
- `categorize_expense`
- `embed_receipt_facts`
- `update_receipt_graph`
- `bookkeeping_entry`

These are review-aware and are persisted as durable queueable job records.

Current implementation boundary:

- tasks are emitted in `receiptAgent.postScanTasks`
- Java compaction preserves `postScanTasks`
- the diagnostics UI can display the task list
- Java stores each task in `receipt_agent_jobs`
- worker execution for those jobs can be attached later

## Feedback Loops

Human review corrections are captured when the user processes a receipt from the unprocessed review UI.

Stored feedback includes:

- original merchant/date/totals/item count
- corrected merchant/date/totals/item count
- corrected item names, quantities, prices, categories, and expense tags
- changed field list

The backend persists this payload in `receipt_correction_feedback` and uses corrected merchant names to update `receipt_merchant_memory`.

Tenant merchant memory is read during Donut reprocessing and passed back to the agent through `parser_json.knownMerchantAliases`.
The latest correction payload for the same receipt is also passed back into Donut reprocessing as parser hints for merchant, date, totals, and item rows.

## Observability And Debugging

Use these fields for inspection:

- `receiptAgent.attempts`
- `receiptAgent.autonomousActions`
- `receiptAgent.humanReview`
- `receiptAgent.memory`
- `receiptAgent.postScanTasks`
- `receiptAgentPasses.merchantConfidence`
- `receiptAgentPasses.pass3CandidateSelection`
- `tables[].reconstruction`
- `layout.retailRowReconstruction`
- `sectionExtraction.debug.rejectedItemRows`
- `sectionExtraction.financialReconciliation`
- `temporalEntities`
- `confidenceTrace`

Frontend diagnostics panel:

- `ShellSpyWebUI/src/components/receipts/ReceiptOrchestrationDebugPanel.jsx`

## Testing

Focused test suites:

```bash
pytest ai-backend/tests/test_receipt_agent_orchestrator.py
pytest ai-backend/tests/test_receipt_intelligence.py
pytest ai-backend/tests/test_routes.py
```

Current coverage includes:

- OCR row reconstruction
- duplicate suppression
- table reconstruction with bounding boxes
- orphan monetary rejection
- merchant hallucination prevention
- domain/header merchant scoring
- PASS 3 financial candidate selection
- temporal extraction
- payment time classification
- human review risk prioritization
- image-quality review risk
- route compatibility
- Playwright receipt review priority visual contract

## Design Principles

1. Prefer deterministic parsing before LLM reasoning.
2. Use geometry when OCR boxes are available.
3. Never trust flat OCR text alone when layout contradicts it.
4. Do not let totals/payment/footer rows become items.
5. Preserve raw OCR merchant when normalized merchant confidence is uncertain.
6. Require very high confidence for merchant override.
7. Use arithmetic as a hard reconciliation signal.
8. Keep every autonomous decision auditable.
9. Route uncertain receipts to human review instead of silently accepting them.
10. Keep legacy API response shape stable while adding richer intelligence.

## Implemented Today

- Human-review queue prioritization ranks receipts by extraction risk.
- Arithmetic mismatch, low-confidence merchants, item-count mismatch, missing items, and low overall confidence feed `humanReview.riskScore`.
- Image-quality and layout-quality signals feed `humanReview.riskScore`.
- The unprocessed receipt UI sorts groups and receipts by human-review risk.
- `receiptAgent.postScanTasks` is generated and preserved in the receipt payload.
- `receiptAgent.postScanTasks` is persisted as queueable records in `receipt_agent_jobs`.
- Merchant memory summaries expose learnable aliases and applied known-merchant hints.
- Corrected merchant aliases from human review are persisted in `receipt_merchant_memory`.
- Tenant-specific merchant memory is loaded into Donut reprocessing as known aliases.
- Rejected candidate rows are exposed in extraction diagnostics and persisted to `receipt_rejected_candidate_rows`.
- Per-field correction feedback is persisted from user edits in the review UI.
- Batch metrics are available through `/main/imgs/receipt-agent/metrics`.
- Playwright covers the review priority visual contract.

## Future Improvements

- Add workers that execute `receipt_agent_jobs`.
- Add dashboards for `receipt_extraction_metrics`.
- Add offline model-evaluation jobs that consume `receipt_rejected_candidate_rows`.
- Add correction-driven model/prompt regression tests from `receipt_correction_feedback`.
