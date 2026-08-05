# Product Intelligence Engine

`product_intelligence` is the non-authoritative semantic enrichment sidecar
after Receipt Constraint Solver.

It consumes a copied view of already extracted line items and approved,
versioned Product Knowledge. It preserves original descriptions and values,
then adds normalization, optional canonical Product candidates, taxonomy,
brand/manufacturer context, nutrition and pricing profiles, confidence,
explanations, diagnostics, and approval-only learning suggestions.

It does not perform OCR, parse receipts, detect merchants, extract products,
change upstream confidence, create Business Facts, mutate parser output, or
become extraction authority.

The in-memory `ProductRepository` defines the governed repository contract for
local execution and tests. A durable adapter may implement the same append-only,
versioned lifecycle without changing the engine contract.

