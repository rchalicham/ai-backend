# Receipt Geometry Engine

The Receipt Geometry Engine is the shared, OCR-independent geometry layer for
OpenGrit receipt intelligence. It detects the physical receipt, describes its
coordinate space and layout, and exposes correction primitives without reading
or interpreting any text.

## Public API

```python
from services.receipt_geometry import ReceiptGeometryEngine

geometry = ReceiptGeometryEngine().analyze(image_bytes)
payload = geometry.to_dict()
```

`Geometry` contains:

- `receipt_boundary`: ordered top-left, top-right, bottom-right, bottom-left points
- `page_dimensions` and `source_dimensions`
- `rotation` of the physical page and residual `skew` of ink lines, in degrees
- the 3 by 3 `perspective_matrix`
- projection-derived `detected_columns`, `whitespace_map`, and `estimated_reading_zones`
- normalized `geometric_confidence`
- contour diagnostics useful for observability

The engine imports OpenCV lazily. `analyze()` raises a clear error for missing
or invalid input; `safe_analyze()` is the non-throwing integration API.

## Components

- `ReceiptGeometryEngine`: stable public facade
- `ReceiptGeometryAnalyzer`: coordinates the analysis pipeline
- `ReceiptContourDetector`: existing bright-paper and edge-contour algorithms
- `ReceiptDeskewEngine`: estimates and optionally corrects line rotation
- `ReceiptPerspectiveCorrector`: computes and applies the existing page warp
- `ReceiptRegionLocator`: projection-based columns, whitespace, and reading zones
- `ReceiptCoordinateSystem`: pixel/normalized coordinate conversion
- `GeometryUtilities`: shared decoding, scaling, quad, enhancement, and encoding

`ReceiptImageIsolationService` remains the compatibility facade used by the
existing extraction pipeline. Its contour, perspective, scaling, quad, and
enhancement work now delegates to these components. Its output policy, strategy
names, source ordering, and image cleanup remain unchanged.

`ReceiptAgentOrchestrator` runs `safe_analyze()` on the uploaded image and adds
the resulting object only under isolation diagnostics as `geometry`. Geometry
does not select attempts, alter pixels, invoke OCR, or affect receipt scoring.

## Architecture

```mermaid
flowchart LR
    subgraph service ["Receipt Processing Services"]
        orchestrator[Receipt Agent Orchestrator]
        isolation[Receipt Image Isolation]
        geometry[Receipt Geometry Engine]
        analyzer[Geometry Analyzer]
        contour[Contour Detector]
        deskew[Deskew Engine]
        perspective[Perspective Corrector]
        regions[Region Locator]
        coordinates[Coordinate System]
        utilities[Geometry Utilities]
    end

    orchestrator -->|"Sidecar analysis"| geometry
    orchestrator -->|"Existing image flow"| isolation
    isolation -->|"Reuses primitives"| contour
    isolation -->|"Reuses warp"| perspective
    isolation -->|"Reuses enhancement"| utilities
    geometry -->|"Coordinates"| analyzer
    analyzer -->|"Detects boundary"| contour
    analyzer -->|"Measures skew"| deskew
    analyzer -->|"Computes warp"| perspective
    analyzer -->|"Finds layout"| regions
    analyzer -->|"Returns dimensions"| coordinates
    analyzer -->|"Uses image helpers"| utilities
```

## Analysis sequence

```mermaid
sequenceDiagram
    participant O as ReceiptAgentOrchestrator
    participant G as ReceiptGeometryEngine
    participant A as ReceiptGeometryAnalyzer
    participant C as ReceiptContourDetector
    participant P as ReceiptPerspectiveCorrector
    participant D as ReceiptDeskewEngine
    participant R as ReceiptRegionLocator

    O->>G: safe_analyze(image bytes)
    G->>A: analyze_image(decoded image)
    A->>C: detect(scaled image)
    C-->>A: ranked receipt boundaries
    A->>P: correct(source, selected boundary)
    P-->>A: normalized page and matrix
    A->>D: estimate(normalized page)
    D-->>A: residual skew
    A->>R: locate(normalized page)
    R-->>A: columns, whitespace, reading zones
    A-->>G: Geometry
    G-->>O: Geometry sidecar
```

## Testing

Run:

```bash
pytest -q tests/test_receipt_geometry.py \
  tests/test_receipt_geometry_orchestrator_integration.py \
  tests/test_receipt_image_isolation.py
```

The tests use synthetic images and never invoke OCR, parsers, models, merchant
logic, network services, or LLMs.
# Validation boundary

`ReceiptGeometryEngine` publishes observations. Consumers that make blocking quality decisions must pass those observations through `services.geometry_validation.GeometryValidationEngine`. Raw contour coordinates and perspective matrices are not authoritative until validated.
