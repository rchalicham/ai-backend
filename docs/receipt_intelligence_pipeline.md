# Receipt Intelligence Pipeline

## Runtime Flow

```text
image upload
  -> OpenCV/image preprocessing in ai-backend
  -> OCR text + optional OCR bounding boxes
  -> ai-backend /receipt/structure
  -> ReceiptIntelligencePipeline
  -> Llama structured extraction
  -> validation/confidence/retry metadata
  -> receipt document persistence by caller
```

## Modules

- `ReceiptLineReconstructor`
  Rebuilds row text from OCR bounding boxes using y-axis clustering and left-to-right ordering. Falls back to supplied OCR lines/raw text.

- `ReceiptDuplicateSuppressor`
  Removes duplicate OCR passes and repeated rows after subtotal markers.

- `ReceiptSpatialClusterer`
  Converts reconstructed rows into spatial regions using page/y-position gaps, bounding boxes, and semantic breaks.

- `ReceiptSemanticBlockBuilder`
  Reconstructs receipt-level semantic blocks such as merchant, header, items, totals, payment, footer, and unknown fragments.

- `ReceiptTableReconstructor`
  Produces item and totals tables with line references so the Llama prompt reasons from structured rows instead of flat OCR noise.

- `ReceiptGraphBuilder`
  Emits a receipt graph with `Receipt`, `Merchant`, `ReceiptItem`, `ReceiptFact`, and `SemanticBlock` nodes for downstream MongoDB/Qdrant/Neo4j persistence.

- `ReceiptLayoutAnalyzer`
  Produces quality indicators for blurry, folded, and shadowed receipts, plus structured layout JSON for multi-pass retry decisions.

- `MerchantNormalizer`
  Normalizes common merchant OCR variants such as Lowe's `PENT COP` / `HOME CENFERS`.

- `ReceiptSemanticParser`
  Builds rule-based item candidates, quantity inference, receipt facts, and deduplicated semantic items.

- `ReceiptValidationEngine`
  Validates item sum vs subtotal and subtotal/tax/total consistency.

- `ReceiptConfidenceEngine`
  Scores OCR, merchant, item, validation, and overall confidence.

- `ReceiptRetryPlanner`
  Produces retry strategies for low OCR confidence, subtotal mismatches, and weak item extraction.

## Request Contract

`POST /receipt/structure`

```json
{
  "raw_text": "flat OCR text",
  "lines": ["optional OCR lines"],
  "ocr_blocks": [
    {
      "text": "item",
      "x": 10,
      "y": 20,
      "width": 100,
      "height": 14,
      "confidence": 0.92,
      "page": 1
    }
  ],
  "ocr_engine": "paddle|tesseract|easyocr|cloud",
  "ocr_variants": [],
  "parser_json": {}
}
```

## Response Additions

The normal receipt schema now includes:

```json
{
  "confidence": 0.91,
  "aiRetryRecommended": false,
  "receiptIntelligence": {
    "version": "2026.05",
    "lineCount": 42,
    "reconstructedLines": [],
    "merchantNormalized": "LOWE'S HOME CENTERS, LLC",
    "layout": {
      "schemaVersion": "receipt-layout-v1",
      "quality": {
        "averageOcrConfidence": 0.91,
        "lineCount": 42,
        "regionCount": 8,
        "warnings": [],
        "indicators": {
          "likelyBlurry": false,
          "likelyFolded": false,
          "likelyShadowed": false
        }
      },
      "regions": [],
      "semanticBlocks": [],
      "tables": [],
      "graph": {
        "nodes": [],
        "edges": []
      }
    },
    "semanticBlocks": [],
    "tables": [],
    "graph": {
      "nodes": [],
      "edges": []
    },
    "validation": {
      "itemSum": "94.98",
      "subtotalDelta": 0.0,
      "warnings": [],
      "valid": true
    },
    "confidence": {},
    "retryPlan": [],
    "warnings": []
  }
}
```

## Llama Prompt Strategy

The LLM now receives structured receipt layout JSON before flat text:

1. `regions` preserve spatial OCR blocks and bounding boxes.
2. `semanticBlocks` separate merchant/header/items/totals/payment/footer content.
3. `tables` provide item and total rows with source line references.
4. `graph` describes receipt relationships for downstream persistence.
5. Flat OCR remains available as fallback evidence only.

This reduces hallucinated item rows from duplicated OCR fragments and lets the model reason over receipt structure instead of noisy text alone.

## Queue And Persistence Architecture

Production queue stages should use idempotent jobs:

```text
receipt.scan.requested
  -> receipt.image.preprocessed
  -> receipt.ocr.completed
  -> receipt.intelligence.completed
  -> receipt.persisted
  -> receipt.embedded
  -> receipt.graph.updated
```

MongoDB should persist:

- raw OCR text and OCR boxes
- reconstructed rows
- structured receipt
- validation/confidence metadata
- retry history
- original file URL and processed image URL

Qdrant should index:

- merchant
- item names
- receipt facts
- reconstructed lines
- extracted insight summaries

Neo4j should model:

- `User` / `Tenant` / `Document`
- `Merchant`
- `Receipt`
- `ReceiptItem`
- `ExpenseCategory`

Relationships:

- `(:User)-[:OWNS]->(:Receipt)`
- `(:Receipt)-[:FROM_MERCHANT]->(:Merchant)`
- `(:Receipt)-[:HAS_ITEM]->(:ReceiptItem)`
- `(:ReceiptItem)-[:CATEGORIZED_AS]->(:ExpenseCategory)`

## OpenCV Integration Points

The image service should emit multiple OCR variants:

- original
- deskewed
- denoised
- adaptive threshold
- high contrast
- long receipt split segments

Each variant can include `lines`, `boxes`, `score`, `psm`, and preprocessing metadata. The intelligence pipeline already accepts those variants.
