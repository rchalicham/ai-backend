import os
import sys
from copy import deepcopy
from types import SimpleNamespace

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.document_family import (
    DocumentFamily, DocumentFamilyEngine, DocumentFamilyRegistry,
    DocumentFamilyRegressionSuite, EntityType, RegressionFixture,
    SemanticZoneType,
)
from services.receipt_dom import (
    BlockType, BoundingBox, CoordinateSpace, Dimensions, ReceiptBlock,
    ReceiptDocument, ReceiptDocumentMetadata, ReceiptGeometrySnapshot,
    ReceiptLine, ReceiptPage, ReceiptRegion, RegionType,
)


def document(*values):
    lines = tuple(
        ReceiptLine(f"line-{index}", text, BoundingBox(x, y, width, height), confidence, reading_order=index)
        for index, (text, x, y, width, height, confidence) in enumerate(values)
    )
    block = ReceiptBlock("block", BlockType.TEXT, BoundingBox(0, 0, 1000, 1600), 0.95, lines)
    region = ReceiptRegion("region", RegionType.TEXT, BoundingBox(0, 0, 1000, 1600), 0.95, (block,))
    geometry = ReceiptGeometrySnapshot(
        ((0, 0), (1000, 0), (1000, 1600), (0, 1600)), Dimensions(1000, 1600), Dimensions(1000, 1600),
        0, 0, ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (), (), (), 0.95, (),
    )
    page = ReceiptPage("page", 0, geometry, Dimensions(1000, 1600), CoordinateSpace.CORRECTED_IMAGE, (region,))
    return ReceiptDocument(ReceiptDocumentMetadata.create(page_count=1), (page,))


def structure(tables=()):
    return SimpleNamespace(candidate_tables=tables)


PAYMENT_SLIP = document(
    ("LUTHER HOPKINS HONDA", 290, 60, 430, 45, .94),
    ("250 5TH AVE SOUTH", 300, 115, 410, 40, .93),
    ("HOPKINS, MN 55343", 310, 165, 390, 40, .95),
    ("12/31/2024", 80, 230, 200, 38, .95),
    ("CREDIT CARD", 350, 300, 300, 40, .96),
    ("AMEX SALE", 375, 355, 250, 40, .96),
    ("Card # XXXXXXXXXXX8007", 80, 430, 700, 42, .94),
    ("AID: A000000025010801", 80, 490, 620, 42, .93),
    ("Approval Code:", 80, 560, 260, 42, .94),
    ("841286", 720, 560, 130, 42, .95),
    ("Entry Method: Chip Read", 80, 620, 700, 42, .94),
    ("SALE AMOUNT", 80, 760, 300, 55, .95),
    ("310.76", 720, 760, 150, 55, .96),
    ("CUSTOMER COPY", 350, 1450, 300, 40, .94),
)


def test_registry_supports_all_required_families_and_unlimited_registration_boundary():
    families = {profile.family for profile in DocumentFamilyRegistry().profiles()}
    assert families == set(DocumentFamily)


def test_payment_slip_activation_semantic_zones_and_contextual_entities():
    context = DocumentFamilyEngine().evaluate(PAYMENT_SLIP, structure(), None)
    assert context.activation.family is DocumentFamily.PAYMENT_SLIP
    assert context.profile.item_table_expected is False
    assert {zone.zone_type for zone in context.semantic_zones} >= {
        SemanticZoneType.MERCHANT, SemanticZoneType.ADDRESS,
        SemanticZoneType.PAYMENT, SemanticZoneType.FINANCIAL,
    }
    assert context.merchant_candidates[0].value == "LUTHER HOPKINS HONDA"
    assert all("AMEX" not in candidate.value for candidate in context.merchant_candidates)
    assert any(candidate.entity_type is EntityType.PAYMENT_IDENTIFIER and candidate.value == "A000000025010801" for candidate in context.payment_candidates)
    assert not any(candidate.entity_type.value == "phone" for candidate in context.entity_candidates)
    assert any(candidate.entity_type is EntityType.ADDRESS and "5TH AVE" in candidate.value for candidate in context.address_candidates)
    assert any(candidate.entity_type is EntityType.FINANCIAL_AMOUNT and candidate.value == "310.76" for candidate in context.entity_candidates)


def test_geometry_key_value_relationship_recovers_right_aligned_approval_code():
    context = DocumentFamilyEngine().evaluate(PAYMENT_SLIP, structure(), None)
    relationship = next(item for item in context.key_value_relationships if "approval" in item.key.lower())
    assert relationship.value == "841286"
    assert relationship.strategy == "geometry_nearest_neighbor"
    assert relationship.confidence >= .9
    assert any(candidate.entity_type is EntityType.APPROVAL_CODE and candidate.value == "841286" for candidate in context.payment_candidates)


def test_required_golden_families_activate_deterministically():
    fixtures = {
        DocumentFamily.RESTAURANT_RECEIPT: "SERVER TABLE TIP GRATUITY TOTAL 42.00",
        DocumentFamily.FUEL_RECEIPT: "PUMP GALLONS PRICE/GAL FUEL TOTAL 52.00",
        DocumentFamily.INVOICE: "INVOICE # 900128 AMOUNT DUE 120.00",
        DocumentFamily.REFUND_RECEIPT: "REFUND AMOUNT 25.00 REFUNDED TO CARD",
        DocumentFamily.STATEMENT: "ACCOUNT STATEMENT OPENING BALANCE 20.00 CLOSING BALANCE 10.00",
        DocumentFamily.WARRANTY: "WARRANTY SERIAL NUMBER 12345 COVERAGE EXPIRES 2027",
        DocumentFamily.DONATION_RECEIPT: "DONATION CHARITABLE CONTRIBUTION TAX DEDUCTIBLE 75.00",
        DocumentFamily.RETAIL_RECEIPT: "ITEM QTY SUBTOTAL 9.00 TAX 1.00 TOTAL 10.00",
    }
    for expected, text in fixtures.items():
        value = document((text, 50, 100, 850, 50, .95))
        tables = (object(),) if expected is DocumentFamily.RETAIL_RECEIPT else ()
        assert DocumentFamilyEngine().evaluate(value, structure(tables), None).activation.family is expected


def test_regression_suite_proves_parser_payload_is_unchanged():
    parser_payload = {"merchant": "legacy", "items": [{"name": "unchanged"}], "total": "1.00"}
    before = deepcopy(parser_payload)
    context = DocumentFamilyEngine().evaluate(PAYMENT_SLIP, structure(), None)
    fixture = RegressionFixture("payment-slip-golden", (), DocumentFamily.PAYMENT_SLIP,
                                ((EntityType.FINANCIAL_AMOUNT, "310.76"),), False)
    result = DocumentFamilyRegressionSuite().run_context(fixture, context, before, parser_payload)
    assert result.passed
    assert result.parser_unchanged
    assert parser_payload == before


def test_models_are_immutable():
    context = DocumentFamilyEngine().evaluate(PAYMENT_SLIP, structure(), None)
    try:
        context.activated_grammar = "mutated"
        assert False, "context must be immutable"
    except (AttributeError, TypeError):
        pass
