import json
import os
import sys
from dataclasses import FrozenInstanceError

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.receipt_dom import ReceiptDomBuilder
from services.receipt_geometry import Dimensions, Geometry, Point, Region
from services.receipt_structure import (
    AlignmentType,
    PageRegionClass,
    PhysicalBlockType,
    ReceiptAlignmentAnalyzer,
    ReceiptBlockClassifier,
    ReceiptDensityAnalyzer,
    ReceiptPhysicalStructureEngine,
    ReceiptRegionClassifier,
    ReceiptStructureSerializer,
    ReceiptTableDetector,
    ReceiptVisualGroupingEngine,
    ReceiptWhitespaceAnalyzer,
    VisualGroupType,
)


def geometry():
    return Geometry(
        receipt_boundary=[Point(0, 0), Point(399, 0), Point(399, 799), Point(0, 799)],
        page_dimensions=Dimensions(400, 800),
        source_dimensions=Dimensions(400, 800),
        rotation=0,
        skew=0,
        perspective_matrix=[[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        detected_columns=[
            Region(20, 0, 180, 800, "column", 0.9),
            Region(230, 0, 150, 800, "column", 0.9),
        ],
        estimated_reading_zones=[
            Region(0, 10, 400, 100, "reading_zone", 0.8),
            Region(0, 250, 400, 300, "reading_zone", 0.8),
            Region(0, 680, 400, 100, "reading_zone", 0.8),
        ],
        geometric_confidence=0.9,
    )


def table_words():
    words = []
    for line_index, y in enumerate((250, 285, 320, 355), start=1):
        words.extend([
            {"text": f"ROW{line_index}", "confidence": 0.94, "x": 30, "y": y, "width": 90, "height": 18,
             "block": 1, "paragraph": 1, "line": line_index, "word": 1},
            {"text": str(line_index), "confidence": 0.93, "x": 190, "y": y, "width": 25, "height": 18,
             "block": 1, "paragraph": 1, "line": line_index, "word": 2},
            {"text": f"{line_index}.00", "confidence": 0.92, "x": 300, "y": y, "width": 55, "height": 18,
             "block": 1, "paragraph": 1, "line": line_index, "word": 3},
        ])
    words.extend([
        {"text": "TOP", "confidence": 0.9, "x": 170, "y": 35, "width": 60, "height": 22,
         "block": 2, "paragraph": 1, "line": 1, "word": 1},
        {"text": "BOTTOM", "confidence": 0.9, "x": 150, "y": 720, "width": 100, "height": 20,
         "block": 3, "paragraph": 1, "line": 1, "word": 1},
    ])
    return words


@pytest.fixture()
def document():
    return ReceiptDomBuilder().build(
        receipt_geometry=geometry(),
        ocr_blocks=table_words(),
        source_ocr_engine="fixture",
    )


@pytest.fixture()
def structure(document):
    return ReceiptPhysicalStructureEngine().analyze(document)


def test_table_detector_finds_repeated_rows_columns_and_numeric_alignment(document):
    tables = ReceiptTableDetector().detect(document)

    assert tables
    table = tables[0]
    assert len(table.row_line_ids) >= 4
    assert len(table.columns) >= 3
    assert table.columns[-1].alignment == AlignmentType.RIGHT
    assert table.row_spacing_consistency > 0.9
    assert table.row_height_consistency > 0.9
    assert table.confidence >= 0.5


def test_region_classifier_produces_only_physical_header_body_footer_classes(document):
    tables = ReceiptTableDetector().detect(document)
    annotations = ReceiptRegionClassifier().classify(document, tables)

    page_classes = {annotation.page_region for annotation in annotations}

    assert PageRegionClass.HEADER in page_classes
    assert PageRegionClass.BODY in page_classes
    assert PageRegionClass.FOOTER in page_classes
    assert all(annotation.node_id for annotation in annotations)


def test_block_classifier_marks_table_and_generic_text_blocks(document):
    tables = ReceiptTableDetector().detect(document)
    annotations = ReceiptBlockClassifier().classify(document, tables)
    by_id = {annotation.node_id: annotation for annotation in annotations}

    assert any(annotation.physical_type == PhysicalBlockType.TABLE for annotation in annotations)
    assert any(annotation.physical_type == PhysicalBlockType.TEXT for annotation in annotations)
    assert all(annotation.alignment in AlignmentType for annotation in by_id.values())


def test_alignment_analysis_builds_geometry_based_clusters(document):
    analyzer = ReceiptAlignmentAnalyzer()
    groups = analyzer.groups(document)

    assert groups
    assert any(group.alignment == AlignmentType.CENTER for group in groups)
    assert all(group.node_ids for group in groups)
    assert all(0 <= group.confidence <= 1 for group in groups)


def test_density_analysis_measures_metrics_and_generates_heat_map(document):
    analyzer = ReceiptDensityAnalyzer()
    region = next(region for region in document.pages[0].regions if region.blocks)
    metrics = analyzer.measure(region)
    density_map = analyzer.maps(document, rows=4, columns=2)[0]

    assert metrics.character_density > 0
    assert metrics.word_density > 0
    assert 0 <= metrics.whitespace_percentage <= 1
    assert density_map.rows == 4
    assert density_map.columns == 2
    assert len(density_map.cells) == 8
    assert any(cell.density > 0 for cell in density_map.cells)


def test_whitespace_analyzer_detects_margins_gutter_and_spacing(document):
    zones, separators = ReceiptWhitespaceAnalyzer().analyze(document)
    kinds = {zone.kind for zone in zones}

    assert "left_margin" in kinds
    assert "right_margin" in kinds
    assert "gutter" in kinds
    assert any(kind in kinds for kind in ("paragraph_spacing", "section_spacing"))
    assert isinstance(separators, tuple)


def test_visual_grouping_uses_dom_reading_order_and_table_membership(document):
    tables = ReceiptTableDetector().detect(document)
    groups = ReceiptVisualGroupingEngine().group(document, tables)

    assert any(group.group_type == VisualGroupType.TABLE for group in groups)
    assert any(group.group_type == VisualGroupType.WORD for group in groups)
    assert all(group.node_ids for group in groups)
    assert all(group.geometry.width >= 0 for group in groups)


def test_engine_builds_complete_structural_hints_without_mutating_dom(document, structure):
    original_ids = tuple(node.id for node in document.walk() if hasattr(node, "id"))

    assert structure.document_id == document.id
    assert structure.schema_version == "receipt-physical-structure-v1"
    assert structure.hints.candidate_tables
    assert structure.hints.candidate_headers
    assert structure.hints.candidate_footers
    assert structure.hints.alignment_groups
    assert structure.hints.visual_groups
    assert structure.hints.whitespace_zones
    assert tuple(node.id for node in document.walk() if hasattr(node, "id")) == original_ids
    with pytest.raises(FrozenInstanceError):
        structure.document_id = "changed"  # type: ignore[misc]


def test_structure_is_annotation_sidecar_referencing_existing_node_identity(document, structure):
    node_ids = {node.id for node in document.walk() if hasattr(node, "id")}

    assert all(annotation.node_id in node_ids for annotation in structure.region_annotations)
    assert all(annotation.node_id in node_ids for annotation in structure.block_annotations)
    assert all(line_id in node_ids for table in structure.candidate_tables for line_id in table.row_line_ids)


def test_serializer_supports_json_debug_pretty_mongo_and_graph_projections(structure):
    serializer = ReceiptStructureSerializer()
    payload = serializer.to_dict(structure)
    debug_payload = serializer.to_dict(structure, debug=True)
    encoded = serializer.to_json(structure, pretty=True)
    graph = serializer.graph_projection(structure)

    assert json.loads(encoded)["schema_version"] == "receipt-physical-structure-v1"
    assert "diagnostics" not in payload
    assert debug_payload["diagnostics"]["immutableAnnotation"] is True
    assert "Candidate tables" in serializer.pretty_print(structure)
    assert graph["nodes"]
    assert any(edge["type"] == "ANNOTATES" for edge in graph["edges"])


def test_serialized_structure_contains_no_business_classification(structure):
    payload = json.dumps(ReceiptStructureSerializer().to_dict(structure, debug=True)).lower()

    for forbidden in ("merchant", "product", "subtotal", "tax", "coupon", "payment_method", "discount"):
        assert forbidden not in payload


def test_safe_engine_failure_boundary_is_non_throwing():
    assert ReceiptPhysicalStructureEngine().safe_analyze(None) is None
