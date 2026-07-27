import json
import os
import sys
from dataclasses import FrozenInstanceError

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.receipt_dom import (
    BlockType,
    BoundingBox,
    CoordinateSpace,
    CoordinateSystem,
    Dimensions,
    NodeRelationships,
    ReadingOrderEngine,
    ReceiptBlock,
    ReceiptDocument,
    ReceiptDomBuilder,
    ReceiptDomSerializer,
    ReceiptGeometrySnapshot,
    ReceiptLine,
    ReceiptPage,
    ReceiptRegion,
    ReceiptWord,
    RegionType,
)
from services.receipt_geometry import Dimensions as Phase1Dimensions
from services.receipt_geometry import Geometry, Point, Region


def phase1_geometry():
    return Geometry(
        receipt_boundary=[Point(10, 20), Point(410, 20), Point(410, 820), Point(10, 820)],
        page_dimensions=Phase1Dimensions(400, 800),
        source_dimensions=Phase1Dimensions(500, 900),
        rotation=0.5,
        skew=-0.25,
        perspective_matrix=[[1, 0, -10], [0, 1, -20], [0, 0, 1]],
        detected_columns=[Region(20, 40, 160, 700, "column", 0.8)],
        whitespace_map={"rowRuns": [{"start": 100, "end": 120}]},
        estimated_reading_zones=[Region(20, 40, 360, 80, "reading_zone", 0.9)],
        geometric_confidence=0.88,
        diagnostics={"contourFound": True},
    )


def ocr_words():
    return [
        {"text": "ALPHA", "confidence": 0.91, "x": 20, "y": 50, "width": 70, "height": 20,
         "block": 1, "paragraph": 1, "line": 1, "word": 1, "source": "fixture.word"},
        {"text": "BETA", "confidence": 0.89, "x": 105, "y": 50, "width": 65, "height": 20,
         "block": 1, "paragraph": 1, "line": 1, "word": 2, "source": "fixture.word"},
        {"text": "GAMMA", "confidence": 0.93, "x": 20, "y": 95, "width": 85, "height": 20,
         "block": 1, "paragraph": 1, "line": 2, "word": 1, "source": "fixture.word"},
        {"text": "DELTA", "confidence": 0.87, "x": 235, "y": 55, "width": 80, "height": 20,
         "block": 2, "paragraph": 1, "line": 1, "word": 1, "source": "fixture.word"},
    ]


@pytest.fixture()
def document():
    return ReceiptDomBuilder().build(
        receipt_geometry=phase1_geometry(),
        ocr_blocks=ocr_words(),
        ocr_lines=["ignored OCR ordering"],
        source_ocr_engine="fixture",
        source_image_id="image-1",
        source_filename="sample.jpg",
    )


def test_receipt_document_metadata_and_page_ownership(document):
    assert isinstance(document, ReceiptDocument)
    assert document.metadata.version == "receipt-dom-v1"
    assert document.metadata.document_type == "physical_receipt"
    assert document.metadata.source_image_id == "image-1"
    assert document.metadata.source_filename == "sample.jpg"
    assert document.metadata.page_count == 1
    assert document.pages[0].relationships.parent_id == document.id
    assert document.children == document.pages


def test_receipt_page_integrates_immutable_phase1_geometry_snapshot(document):
    page = document.pages[0]

    assert isinstance(page, ReceiptPage)
    assert isinstance(page.geometry, ReceiptGeometrySnapshot)
    assert page.geometry.rotation == 0.5
    assert page.geometry.skew == -0.25
    assert page.geometry.receipt_boundary[0] == (10.0, 20.0)
    assert page.dimensions == Dimensions(400, 800)
    assert page.coordinate_system == CoordinateSpace.CORRECTED_IMAGE


def test_builder_preserves_complete_hierarchy_and_source_references(document):
    text_region = document.pages[0].regions[0]
    first_block = text_region.blocks[0]
    first_line = first_block.lines[0]
    first_word = first_line.words[0]

    assert isinstance(text_region, ReceiptRegion)
    assert text_region.region_type == RegionType.TEXT
    assert isinstance(first_block, ReceiptBlock)
    assert first_block.block_type == BlockType.TEXT
    assert isinstance(first_line, ReceiptLine)
    assert first_line.text == "ALPHA BETA"
    assert isinstance(first_word, ReceiptWord)
    assert first_word.text == "ALPHA"
    assert first_word.geometry == BoundingBox(20, 50, 70, 20)
    assert first_word.confidence == 0.91
    assert first_word.source_reference.source_index == 0
    assert first_word.source_reference.source_type == "fixture.word"


def test_parent_child_and_sibling_relationships_are_identity_based(document):
    region = document.pages[0].regions[0]
    block = region.blocks[0]
    line = block.lines[0]
    first, second = line.words

    assert block.relationships.parent_id == region.id
    assert line.relationships.parent_id == block.id
    assert first.relationships.parent_id == line.id
    assert first.relationships.next_sibling_id == second.id
    assert second.relationships.previous_sibling_id == first.id
    assert second.id in first.relationships.nearest_neighbor_ids


def test_reading_order_engine_uses_geometry_for_columns_and_vertical_neighbors():
    nodes = [
        ReceiptWord("right-bottom", "D", BoundingBox(220, 80, 30, 10), 1),
        ReceiptWord("left-top", "A", BoundingBox(10, 10, 30, 10), 1),
        ReceiptWord("right-top", "B", BoundingBox(220, 10, 30, 10), 1),
        ReceiptWord("left-bottom", "C", BoundingBox(10, 80, 30, 10), 1),
    ]

    ordered = ReadingOrderEngine().order(nodes)
    by_id = {node.id: node for node in ordered}

    assert [node.id for node in ordered] == ["left-top", "right-top", "left-bottom", "right-bottom"]
    assert by_id["left-top"].relationships.right_id == "right-top"
    assert by_id["left-top"].relationships.below_id == "left-bottom"
    assert by_id["right-bottom"].relationships.above_id == "right-top"


def test_builder_does_not_trust_input_ocr_order():
    reversed_words = list(reversed(ocr_words()))
    document = ReceiptDomBuilder().build(receipt_geometry=phase1_geometry(), ocr_blocks=reversed_words)

    first_line = document.pages[0].regions[0].blocks[0].lines[0]

    assert [word.text for word in first_line.words] == ["ALPHA", "BETA"]
    assert [word.reading_order for word in first_line.words] == [0, 1]


def test_overlapping_words_have_stable_geometric_order():
    words = [
        ReceiptWord("second", "B", BoundingBox(25, 20, 40, 15), 1),
        ReceiptWord("first", "A", BoundingBox(20, 20, 40, 15), 1),
    ]

    ordered = ReadingOrderEngine().order(words)

    assert [word.id for word in ordered] == ["first", "second"]


def test_coordinate_system_converts_original_corrected_and_normalized():
    snapshot = ReceiptGeometrySnapshot.from_phase1(phase1_geometry())
    coordinates = CoordinateSystem(snapshot)
    original = BoundingBox(10, 20, 100, 50, CoordinateSpace.ORIGINAL_IMAGE)

    corrected = coordinates.convert(original, CoordinateSpace.CORRECTED_IMAGE)
    normalized = coordinates.convert(corrected, CoordinateSpace.NORMALIZED_PAGE)
    restored = coordinates.convert(normalized, CoordinateSpace.ORIGINAL_IMAGE)

    assert corrected == BoundingBox(0, 0, 100, 50, CoordinateSpace.CORRECTED_IMAGE)
    assert normalized == BoundingBox(0, 0, 0.25, 0.0625, CoordinateSpace.NORMALIZED_PAGE)
    assert restored.x == pytest.approx(original.x)
    assert restored.y == pytest.approx(original.y)


def test_document_and_nested_nodes_are_immutable(document):
    with pytest.raises(FrozenInstanceError):
        document.pages = ()  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        document.pages[0].regions[0].confidence = 0.0  # type: ignore[misc]
    with pytest.raises(TypeError):
        document.pages[0].geometry.diagnostics[0] = ("changed", True)  # type: ignore[index]


def test_serializer_supports_json_debug_json_pretty_tree_and_graph(document):
    serializer = ReceiptDomSerializer()

    payload = serializer.to_dict(document)
    debug_payload = serializer.to_dict(document, debug=True)
    encoded = serializer.to_json(document)
    debug_encoded = serializer.to_debug_json(document)
    tree = serializer.pretty_print(document)
    visualization = serializer.tree_visualization(document)
    graph = serializer.graph_projection(document)

    assert json.loads(encoded)["metadata"]["document_type"] == "physical_receipt"
    assert "diagnostics" not in payload["metadata"]
    assert "diagnostics" in debug_payload["metadata"]
    assert "\n" in debug_encoded
    assert "ReceiptDocument" in tree and "ReceiptWord" in tree
    assert visualization["children"][0]["type"] == "ReceiptPage"
    assert any(edge["type"] == "CONTAINS" for edge in graph["edges"])


def test_dom_contains_only_physical_document_vocabulary(document):
    payload = json.dumps(ReceiptDomSerializer().to_dict(document, debug=True)).lower()

    for forbidden in ("merchant", "subtotal", "tax", "payment", "coupon", "product"):
        assert forbidden not in payload


def test_builder_supports_lines_when_word_geometry_is_unavailable():
    document = ReceiptDomBuilder().build(
        receipt_geometry=phase1_geometry(),
        ocr_lines=["FIRST PHYSICAL LINE", "SECOND PHYSICAL LINE"],
    )
    lines = document.pages[0].regions[0].blocks[0].lines

    assert [line.text for line in lines] == ["FIRST PHYSICAL LINE", "SECOND PHYSICAL LINE"]
    assert lines[0].geometry.y < lines[1].geometry.y
    assert lines[0].words == ()
