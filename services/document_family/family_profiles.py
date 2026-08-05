from __future__ import annotations

from .models import DocumentFamily, EntityType, FamilyProfile, SemanticZoneType


def _profile(family, zones, entities, items, terms, labels=()):
    name = family.value
    return FamilyProfile(
        family, f"{name}-profile-v1", 1, f"{name}-grammar-v1", f"{name}-constraints-v1",
        zones, entities, items, terms, labels,
        ("contextual_resolution", "zone_scoped_candidates", "geometry_key_value"),
    )


COMMON = (SemanticZoneType.MERCHANT, SemanticZoneType.ADDRESS, SemanticZoneType.FINANCIAL)
PROFILES = (
    _profile(DocumentFamily.RETAIL_RECEIPT, COMMON + (SemanticZoneType.ITEM, SemanticZoneType.PAYMENT),
             (EntityType.MERCHANT, EntityType.FINANCIAL_AMOUNT), True,
             ("subtotal", "tax", "total", "qty", "item"), ("subtotal", "tax", "total")),
    _profile(DocumentFamily.RESTAURANT_RECEIPT, COMMON + (SemanticZoneType.ITEM, SemanticZoneType.PAYMENT),
             (EntityType.MERCHANT, EntityType.FINANCIAL_AMOUNT), True,
             ("server", "table", "guest", "tip", "gratuity"), ("subtotal", "tip", "total")),
    _profile(DocumentFamily.FUEL_RECEIPT, COMMON + (SemanticZoneType.ITEM, SemanticZoneType.PAYMENT),
             (EntityType.MERCHANT, EntityType.FINANCIAL_AMOUNT), True,
             ("gallons", "fuel", "pump", "price/gal", "diesel"), ("pump", "gallons", "total")),
    _profile(DocumentFamily.PHARMACY_RECEIPT, COMMON + (SemanticZoneType.ITEM, SemanticZoneType.PAYMENT, SemanticZoneType.REFERENCE),
             (EntityType.MERCHANT, EntityType.FINANCIAL_AMOUNT), True,
             ("pharmacy", "prescription", "rx number", "rx #", "ndc", "copay"),
             ("rx number", "prescription", "copay", "total")),
    _profile(DocumentFamily.PAYMENT_SLIP, COMMON + (SemanticZoneType.PAYMENT, SemanticZoneType.REFERENCE),
             (EntityType.MERCHANT, EntityType.FINANCIAL_AMOUNT, EntityType.PAYMENT_BRAND), False,
             ("sale amount", "amex sale", "approval code", "entry method", "customer copy", "credit card"),
             ("approval code", "sale amount", "entry method", "aid", "invoice")),
    _profile(DocumentFamily.CREDIT_CARD_SLIP, COMMON + (SemanticZoneType.PAYMENT, SemanticZoneType.REFERENCE),
             (EntityType.MERCHANT, EntityType.FINANCIAL_AMOUNT, EntityType.MASKED_PAN), False,
             ("cardholder", "authorization", "masked pan", "credit card", "signature"),
             ("authorization", "card", "amount")),
    _profile(DocumentFamily.REFUND_RECEIPT, COMMON + (SemanticZoneType.ITEM, SemanticZoneType.PAYMENT),
             (EntityType.MERCHANT, EntityType.FINANCIAL_AMOUNT), False,
             ("refund", "refunded", "credit due", "refund amount"), ("refund amount", "reference")),
    _profile(DocumentFamily.RETURN_RECEIPT, COMMON + (SemanticZoneType.ITEM, SemanticZoneType.REFERENCE),
             (EntityType.MERCHANT, EntityType.FINANCIAL_AMOUNT), True,
             ("return", "returned item", "return authorization"), ("return authorization", "total")),
    _profile(DocumentFamily.INVOICE, (SemanticZoneType.MERCHANT, SemanticZoneType.ADDRESS, SemanticZoneType.ITEM, SemanticZoneType.FINANCIAL, SemanticZoneType.REFERENCE),
             (EntityType.MERCHANT, EntityType.REFERENCE_NUMBER, EntityType.FINANCIAL_AMOUNT), True,
             ("invoice", "bill to", "due date", "amount due"), ("invoice", "invoice #", "amount due")),
    _profile(DocumentFamily.STATEMENT, (SemanticZoneType.MERCHANT, SemanticZoneType.ADDRESS, SemanticZoneType.FINANCIAL, SemanticZoneType.REFERENCE),
             (EntityType.MERCHANT, EntityType.FINANCIAL_AMOUNT), False,
             ("statement", "opening balance", "closing balance", "account summary"), ("account", "balance")),
    _profile(DocumentFamily.WARRANTY, (SemanticZoneType.MERCHANT, SemanticZoneType.REFERENCE, SemanticZoneType.FOOTER),
             (EntityType.MERCHANT, EntityType.REFERENCE_NUMBER), False,
             ("warranty", "serial number", "coverage", "expires"), ("serial number", "expires")),
    _profile(DocumentFamily.DONATION_RECEIPT, COMMON + (SemanticZoneType.REFERENCE,),
             (EntityType.MERCHANT, EntityType.FINANCIAL_AMOUNT), False,
             ("donation", "charitable", "tax deductible", "donor"), ("donation amount", "receipt number")),
    _profile(DocumentFamily.UNKNOWN, (SemanticZoneType.UNKNOWN,), (), False, (), ()),
)


def builtin_family_profiles() -> tuple[FamilyProfile, ...]:
    return PROFILES
