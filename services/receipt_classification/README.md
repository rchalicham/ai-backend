# Receipt Classification Engine

The Receipt Classification Engine ranks learned receipt families by physical
similarity. It is an immutable, request-scoped sidecar over the Receipt DOM and
Receipt Physical Structure. It does not read OCR text, infer merchant identity,
parse fields, or alter extraction.

## Responsibilities and ownership

- `ReceiptFeatureExtractor` owns deterministic physical measurement.
- `ReceiptBlueprintMatcher` adapts versioned repository family profiles.
- `ReceiptSimilarityEngine` owns pluggable similarity strategies.
- `ReceiptConfidenceEngine` combines similarity, coverage, strategy agreement,
  and profile confidence.
- `ReceiptCandidateRanker` applies stable Top-N ordering and explanations.
- `ReceiptClassificationEngine` coordinates these services and creates
  approval-only learning suggestions.
- `ReceiptClassificationSerializer` provides JSON, debug, pretty, Mongo-friendly,
  and graph projections.

The Receipt DOM and physical structure remain owned by their existing systems.
Classification never mutates them. Merchant Intelligence remains the owner of
blueprints and version history; suggestions do not write to it.

## Runtime sequence

```mermaid
sequenceDiagram
    participant O as ReceiptAgentOrchestrator
    participant P as Physical Structure Engine
    participant C as Classification Engine
    participant K as Explicitly Loaded Blueprint
    participant X as Existing Parser
    O->>P: analyze immutable ReceiptDocument
    P-->>O: ReceiptPhysicalStructure
    O->>C: classify(document, structure, loaded blueprints)
    C->>C: extract physical feature vector
    C->>K: adapt family feature profiles
    K-->>C: versioned physical profiles
    C->>C: compare, score, rank Top-N
    C-->>O: ReceiptClassification sidecar
    O->>X: continue existing inputs unchanged
```

When no blueprint was explicitly loaded, the engine still returns the feature
vector and an empty candidate list. It never searches aliases or derives a
merchant key.

## Package architecture

```mermaid
flowchart LR
    subgraph Inputs
        DOM[Receipt DOM]
        PS[Physical Structure]
        BP[Family Profiles]
    end
    subgraph receipt_classification
        FE[Feature Extractor]
        BM[Blueprint Matcher]
        SE[Similarity Engine]
        CE[Confidence Engine]
        CR[Candidate Ranker]
        RE[Classification Engine]
        SZ[Serializer]
    end
    DOM --> FE
    PS --> FE
    BP --> BM
    FE --> RE
    BM --> RE
    RE --> SE
    SE --> CE
    CE --> CR
    CR --> SZ
```

## Feature model

`ReceiptFeatureVector` is frozen, versioned, serializable, and divided into
stable namespaces:

```mermaid
flowchart TD
    FV[ReceiptFeatureVector v1]
    FV --> PG[Page metrics]
    FV --> LM[Layout metrics]
    FV --> TM[Table metrics]
    FV --> SM[Spacing metrics]
    FV --> AM[Alignment metrics]
    FV --> RM[Reading metrics]
    FV --> DM[Density metrics]
    FV --> GM[Geometry metrics]
    PG --> P1[Width, height, aspect ratio]
    LM --> L1[Regions, columns, header and footer ratios]
    TM --> T1[Candidate geometry, rows, columns]
    SM --> S1[Line, word, block, separator spacing]
    AM --> A1[Physical alignment clusters]
    RM --> R1[Reading order and visual groups]
    DM --> D1[Density map and whitespace]
    GM --> G1[Rotation, skew, perspective, confidence]
```

No node text or semantic label is part of the vector.

## Similarity architecture

```mermaid
flowchart LR
    C[Current vector] --> I[Shared numeric features]
    P[Family profile] --> I
    W[Configurable weights] --> E[Weighted Euclidean]
    W --> O[Cosine]
    W --> N[Normalized distance]
    I --> E
    I --> O
    I --> N
    E --> CF[Confidence and coverage]
    O --> CF
    N --> CF
    CF --> RN[Stable Top-N ranking]
```

Strategies implement the `SimilarityStrategy` protocol, so future algorithms
can be injected without changing the engine or profile schema. Missing features
reduce coverage rather than being treated as zeros.

## Object lifecycle

```mermaid
flowchart TD
    D[Immutable ReceiptDocument] --> F[Immutable ReceiptFeatureVector]
    S[Immutable structure annotations] --> F
    F --> C[BlueprintComparison]
    B[Versioned family profile] --> C
    C --> R[Ranked family candidates]
    R --> L[Approval-only learning suggestions]
    L -. no automatic write .-> Q[Future review workflow]
```

Future merchant detection may consume ranked family candidates as evidence. It
must remain a separate engine and must not reinterpret classification as a
detected merchant.

## Blueprint physical profile

A `ReceiptFamily.attributes` entry may use `feature_vector`,
`physical_features`, or `feature_profile`. Values are nested physical numeric
metrics matching the vector namespaces. Optional `feature_weights` use flattened
keys such as `layout.reading_column_count`.

```json
{
  "physical_features": {
    "page": {"width": 400, "height": 800},
    "layout": {"reading_column_count": 2},
    "density": {"whitespace_percentage": 0.31}
  },
  "feature_weights": {
    "layout.reading_column_count": 2.0
  }
}
```

Layout profiles and physical aggregate statistics are also adapted when
available. Textual vocabulary, aliases, OCR corrections, and business profiles
are never consumed.
