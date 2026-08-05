import os
import sys
from copy import deepcopy

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.document_family.models import (
    DocumentFamily, DocumentFamilyContext, EntityCandidate, EntityType,
    FamilyActivation, FamilyEvidence, FamilyProfile, KeyValueRelationship,
    SemanticZoneType,
)
from services.presentation_projection import (
    PresentationProjectionEngine, ProjectionMigrationController, ProjectionMode,
    ProjectionRegistry, ProjectionSource,
)


def candidate(identifier, kind, value, confidence=.95):
    evidence = FamilyEvidence("golden", value, confidence, "fixture", (identifier,))
    return EntityCandidate(identifier, kind, value, confidence, "zone", (evidence,), "fixture")


def payment_context():
    profile = FamilyProfile(
        DocumentFamily.PAYMENT_SLIP, "payment-slip-v1", 1,
        "payment-slip-grammar-v1", "payment-slip-constraints-v1",
        (SemanticZoneType.MERCHANT, SemanticZoneType.ADDRESS, SemanticZoneType.PAYMENT, SemanticZoneType.FINANCIAL),
        (EntityType.MERCHANT, EntityType.ADDRESS, EntityType.FINANCIAL_AMOUNT), False,
    )
    merchant = candidate("merchant-1", EntityType.MERCHANT, "Luther Hopkins Honda", .98)
    address1 = candidate("address-1", EntityType.ADDRESS, "250 5th Ave South", .96)
    address2 = candidate("address-2", EntityType.ADDRESS, "Hopkins MN 55343", .95)
    brand = candidate("brand-1", EntityType.PAYMENT_BRAND, "American Express", .97)
    pan = candidate("pan-1", EntityType.MASKED_PAN, "8007", .99)
    approval = candidate("approval-1", EntityType.APPROVAL_CODE, "841286", .97)
    date = candidate("date-1", EntityType.DATE, "12/31/2024", .96)
    amount = candidate("amount-1", EntityType.FINANCIAL_AMOUNT, "310.76", .98)
    relationship = KeyValueRelationship("kv-sale", "SALE AMOUNT", "310.76", "line-a", "line-b", .98, "geometry")
    activation = FamilyActivation(DocumentFamily.PAYMENT_SLIP, .98, profile.profile_id, ())
    entities = (merchant, address1, address2, brand, pan, approval, date, amount)
    return DocumentFamilyContext("document-1", activation, profile, (), entities,
                                 (merchant,), (brand, pan, approval), (address1, address2),
                                 (relationship,), profile.grammar_id, profile.constraint_set_id, ())


def test_payment_slip_projection_resolves_conflicts_and_preserves_parser():
    parser = {
        "company": "AMEX SALE", "date": "12/31/2024", "total": "0",
        "subTotal": "0", "tax": "0", "items": [{"name": "SALE AMOUNT", "price": "310.76"}],
        "cardUsed": "AMEX", "cardLast4": "8007",
    }
    before = deepcopy(parser)
    projection = PresentationProjectionEngine().project(
        parser=parser, document_family_context=payment_context(), document_id="document-1",
    )
    fields = {field.key: field for field in projection.fields}
    assert projection.metadata.business_view == "payment_slip_view"
    assert fields["merchant"].displayed_value == "Luther Hopkins Honda"
    assert fields["merchant"].parser_value == "AMEX SALE"
    assert fields["merchant"].source is ProjectionSource.ENTERPRISE
    assert fields["address"].displayed_value == "250 5th Ave South\nHopkins MN 55343"
    assert fields["total"].displayed_value == "310.76"
    assert fields["card_last_four"].displayed_value == "8007"
    assert not any(section.key == "items" for section in projection.sections)
    assert parser == before
    assert projection.diagnostics.parser_modified is False
    assert projection.diagnostics.parser_authority_changed is False


def test_migration_modes_parser_enterprise_shadow_compare_and_overrides():
    context = payment_context()
    parser = {"company": "AMEX SALE"}
    for mode, expected in (
        (ProjectionMode.PARSER_ONLY, "AMEX SALE"),
        (ProjectionMode.SHADOW, "AMEX SALE"),
        (ProjectionMode.ENTERPRISE_ONLY, "Luther Hopkins Honda"),
        (ProjectionMode.HYBRID, "Luther Hopkins Honda"),
        (ProjectionMode.COMPARE, "Luther Hopkins Honda"),
    ):
        engine = PresentationProjectionEngine()
        engine.selector.migration_controller = ProjectionMigrationController(mode)
        projection = engine.project(parser=parser, document_family_context=context)
        assert next(field for field in projection.fields if field.key == "merchant").displayed_value == expected
    controller = ProjectionMigrationController(ProjectionMode.PARSER_ONLY)
    assert controller.select_mode(family="payment_slip", family_overrides={"payment_slip": "hybrid"}) is ProjectionMode.HYBRID


def test_registry_has_required_business_views_and_is_extensible():
    registry = ProjectionRegistry()
    views = {profile.business_view for profile in registry.profiles()}
    assert {"retail_receipt_view", "restaurant_receipt_view", "fuel_receipt_view",
            "payment_slip_view", "credit_card_slip_view", "refund_view", "invoice_view",
            "statement_view", "warranty_view", "medical_bill_view", "insurance_eob_view",
            "unknown_view"} <= views


def test_projection_models_are_immutable_and_confidence_retains_components():
    projection = PresentationProjectionEngine().project(parser={}, document_family_context=payment_context())
    field = next(item for item in projection.fields if item.key == "merchant")
    assert dict(field.confidence.components)["enterprise"] == .98
    try:
        projection.metadata.mode = ProjectionMode.PARSER_ONLY
        assert False
    except (AttributeError, TypeError):
        pass
