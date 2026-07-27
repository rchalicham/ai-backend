import json
import os
import sys
from dataclasses import FrozenInstanceError

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.merchant_intelligence import (
    MerchantBlueprint, MerchantIdentity, ReceiptFamily,
)
from services.receipt_classification import (
    CosineSimilarity, NormalizedFeatureDistance, ReceiptClassificationEngine,
    ReceiptClassificationSerializer, ReceiptConfidenceEngine, ReceiptFeatureExtractor,
    ReceiptSimilarityEngine, WeightedEuclideanSimilarity,
)
from services.receipt_dom import ReceiptDomBuilder
from services.receipt_geometry import Dimensions, Geometry, Point, Region
from services.receipt_structure import ReceiptPhysicalStructureEngine


def geometry():
    return Geometry(
        receipt_boundary=[Point(0, 0), Point(399, 0), Point(399, 799), Point(0, 799)],
        page_dimensions=Dimensions(400, 800),
        source_dimensions=Dimensions(400, 800),
        rotation=0.5,
        skew=-0.25,
        perspective_matrix=[[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        detected_columns=[Region(20, 0, 170, 800, "column"), Region(220, 0, 160, 800, "column")],
        estimated_reading_zones=[Region(0, 0, 400, 120, "reading"), Region(0, 180, 400, 500, "reading")],
        geometric_confidence=0.92,
    )


def words(label="A"):
    result = []
    for row, y in enumerate((40, 240, 275, 310, 710), 1):
        for column, (x, width) in enumerate(((30, 100), (240, 60)), 1):
            result.append({
                "text": f"{label}-{row}-{column}",
                "confidence": 0.9,
                "x": x, "y": y, "width": width, "height": 18,
                "block": row, "paragraph": 1, "line": row, "word": column,
            })
    return result


@pytest.fixture()
def physical_pair():
    document = ReceiptDomBuilder().build(
        receipt_geometry=geometry(), ocr_blocks=words(), source_ocr_engine="fixture",
    )
    return document, ReceiptPhysicalStructureEngine().analyze(document)


def blueprint(family_id, metrics, confidence=1.0):
    family = ReceiptFamily(
        family_id=family_id,
        merchant_id="repository-owner",
        name=family_id,
        confidence=confidence,
        attributes=(("physical_features", metrics),),
    )
    return MerchantBlueprint(
        identity=MerchantIdentity("repository-owner", "Repository Owner"),
        receipt_families=(family,),
    )


def nested_metrics(vector):
    values = {}
    for key, value in vector.flatten():
        group, name = key.split(".", 1)
        values.setdefault(group, {})[name] = value
    return values


def test_feature_extractor_creates_versioned_immutable_physical_vector(physical_pair):
    document, structure = physical_pair
    vector = ReceiptFeatureExtractor().extract(document, structure)

    assert vector.version == 1
    assert vector.schema_version == "receipt-feature-vector-v1"
    assert dict(vector.page_metrics.metrics)["width"] == 400
    assert dict(vector.layout_metrics.metrics)["reading_column_count"] == 2
    assert dict(vector.geometry_metrics.metrics)["confidence"] == 0.92
    with pytest.raises(FrozenInstanceError):
        vector.version = 2  # type: ignore[misc]


def test_feature_extraction_does_not_depend_on_ocr_text():
    builder = ReceiptDomBuilder()
    first = builder.build(receipt_geometry=geometry(), ocr_blocks=words("FIRST"))
    second = builder.build(receipt_geometry=geometry(), ocr_blocks=words("COMPLETELY-DIFFERENT"))
    engine = ReceiptPhysicalStructureEngine()

    left = ReceiptFeatureExtractor().extract(first, engine.analyze(first))
    right = ReceiptFeatureExtractor().extract(second, engine.analyze(second))

    assert tuple(value for _, value in left.flatten()) == tuple(value for _, value in right.flatten())


@pytest.mark.parametrize(
    "strategy",
    [WeightedEuclideanSimilarity(), CosineSimilarity(), NormalizedFeatureDistance()],
)
def test_similarity_strategies_are_modular_and_score_identical_vectors(strategy):
    values = {"page.width": 400.0, "layout.region_count": 3.0}
    assert strategy.score(values, values, {}) == pytest.approx(1.0)


def test_blueprint_matching_ranks_closest_family_and_respects_top_n(physical_pair):
    document, structure = physical_pair
    vector = ReceiptFeatureExtractor().extract(document, structure)
    close = blueprint("family-close", nested_metrics(vector))
    far_metrics = nested_metrics(vector)
    far_metrics["page"]["width"] = 1200
    far_metrics["page"]["height"] = 200
    far = blueprint("family-far", far_metrics)

    result = ReceiptClassificationEngine(top_n=1).classify(document, structure, (far, close))

    assert len(result.candidates) == 1
    assert result.candidates[0].receipt_family == "family-close"
    assert result.candidates[0].confidence > 0.9
    assert len(result.comparisons) == 2


def test_no_loaded_blueprint_still_returns_feature_vector_with_no_guess(physical_pair):
    document, structure = physical_pair
    result = ReceiptClassificationEngine().classify(document, structure)

    assert result.feature_vector.document_id == document.id
    assert result.candidates == ()
    assert dict(result.diagnostics)["merchantDetectionPerformed"] is False


def test_confidence_contains_required_physical_breakdown():
    scores = ReceiptSimilarityEngine().strategies
    assert {strategy.name for strategy in scores} == {
        "weighted_euclidean", "cosine", "normalized_feature_distance",
    }
    confidence, breakdown = ReceiptConfidenceEngine().calculate((), (), 1.0)
    assert confidence == 0
    assert {"geometry", "layout", "alignment", "density", "table", "reading"}.issubset(dict(breakdown))


def test_learning_is_approval_only_and_never_mutates_blueprint(physical_pair):
    document, structure = physical_pair
    vector = ReceiptFeatureExtractor().extract(document, structure)
    source = blueprint("learned-family", nested_metrics(vector))
    before = source

    result = ReceiptClassificationEngine().classify(document, structure, (source,))

    assert result.learning_suggestions
    assert result.learning_suggestions[0].requires_approval is True
    assert source == before


def test_serializer_supports_debug_pretty_json_and_graph(physical_pair):
    document, structure = physical_pair
    vector = ReceiptFeatureExtractor().extract(document, structure)
    result = ReceiptClassificationEngine().classify(
        document, structure, (blueprint("fixture-family", nested_metrics(vector)),),
    )
    serializer = ReceiptClassificationSerializer()

    payload = serializer.to_dict(result)
    debug = serializer.to_dict(result, debug=True)
    encoded = json.loads(serializer.to_json(result, pretty=True))
    graph = serializer.graph_projection(result)

    assert payload["schema_version"] == "receipt-classification-v1"
    assert "diagnostics" not in payload
    assert debug["diagnostics"]["usesOcrText"] is False
    assert encoded["feature_vector"]["version"] == 1
    assert "Candidates: 1" in serializer.pretty_print(result)
    assert graph["edges"][0]["type"] == "PHYSICALLY_RESEMBLES"


def test_safe_failure_boundary_is_non_throwing():
    assert ReceiptClassificationEngine().safe_classify(None, None) is None
