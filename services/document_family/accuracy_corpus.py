from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.receipt_dom import (
    BlockType, BoundingBox, CoordinateSpace, Dimensions, ReceiptBlock,
    ReceiptDocument, ReceiptDocumentMetadata, ReceiptGeometrySnapshot,
    ReceiptLine, ReceiptPage, ReceiptRegion, RegionType,
)

from .models import DocumentFamily, SemanticZoneType


@dataclass(frozen=True, slots=True)
class GoldenTruth:
    family: DocumentFamily
    merchant: str
    address: tuple[str, ...]
    date: str
    total: str
    payment: str
    items_expected: bool
    semantic_zones: tuple[SemanticZoneType, ...]
    projection: str
    minimum_confidence: float
    reasoning: str
    business_projection: tuple[tuple[str, Any], ...]


@dataclass(frozen=True, slots=True)
class FamilyCorpusDocument:
    document_id: str
    source_kind: str
    scan_condition: str
    content_type: str
    rotation_degrees: int
    contrast: float
    lines: tuple[str, ...]
    golden: GoldenTruth


VARIANTS = (
    ("real", "image/jpeg", 0, 1.0),
    ("edge-case", "image/png", 0, .9),
    ("poor-scan", "image/jpeg", 0, .55),
    ("rotated-scan", "image/png", 90, .9),
    ("low-contrast", "image/jpeg", 0, .35),
    ("thermal-paper", "image/png", 0, .6),
    ("partial-receipt", "image/jpeg", 0, .7),
    ("pdf-upload", "application/pdf", 0, 1.0),
    ("png-upload", "image/png", 0, 1.0),
    ("heic-upload", "image/heic", 0, 1.0),
)


def _truth(family, merchant, address, date, total, payment, items, zones, view, confidence=.45):
    return GoldenTruth(
        family, merchant, address, date, total, payment, items, zones, view, confidence,
        "deterministic_evidence_ranking",
        (("merchant", merchant), ("date", date), ("total", total), ("business_view", view)),
    )


TEMPLATES = (
    (("NORTHSTAR MARKET", "100 MAIN ST", "DENVER, CO 80202", "01/15/2026", "ITEM QTY 2", "SUBTOTAL: 18.50", "TAX: 1.50", "TOTAL: 20.00", "VISA ****1234"),
     _truth(DocumentFamily.RETAIL_RECEIPT, "NORTHSTAR MARKET", ("100 MAIN ST", "DENVER, CO 80202"), "01/15/2026", "20.00", "VISA", True,
            (SemanticZoneType.MERCHANT, SemanticZoneType.ADDRESS, SemanticZoneType.ITEM, SemanticZoneType.FINANCIAL, SemanticZoneType.PAYMENT), "retail_receipt_view")),
    (("RIVER TABLE KITCHEN", "22 LAKE AVE", "AUSTIN, TX 78701", "02/12/2026", "SERVER: MAYA", "TABLE: 14", "GUEST 2", "TIP: 8.00", "GRATUITY", "TOTAL: 48.00", "MASTERCARD ****4488"),
     _truth(DocumentFamily.RESTAURANT_RECEIPT, "RIVER TABLE KITCHEN", ("22 LAKE AVE", "AUSTIN, TX 78701"), "02/12/2026", "48.00", "MASTERCARD", True,
            (SemanticZoneType.MERCHANT, SemanticZoneType.ADDRESS, SemanticZoneType.ITEM, SemanticZoneType.FINANCIAL, SemanticZoneType.PAYMENT), "restaurant_receipt_view")),
    (("HIGHWAY ENERGY", "800 STATE HWY", "TULSA, OK 74103", "03/10/2026", "PUMP: 04", "FUEL REGULAR", "GALLONS: 10.000", "PRICE/GAL: 3.499", "TOTAL: 34.99", "VISA ****9001"),
     _truth(DocumentFamily.FUEL_RECEIPT, "HIGHWAY ENERGY", ("800 STATE HWY", "TULSA, OK 74103"), "03/10/2026", "34.99", "VISA", True,
            (SemanticZoneType.MERCHANT, SemanticZoneType.ADDRESS, SemanticZoneType.ITEM, SemanticZoneType.FINANCIAL, SemanticZoneType.PAYMENT), "fuel_receipt_view")),
    (("COMMUNITY PHARMACY", "15 OAK RD", "MADISON, WI 53703", "04/08/2026", "PRESCRIPTION", "RX NUMBER: 804422", "NDC: 00093-5056", "COPAY: 12.00", "TOTAL: 12.00", "VISA ****7721"),
     _truth(DocumentFamily.PHARMACY_RECEIPT, "COMMUNITY PHARMACY", ("15 OAK RD", "MADISON, WI 53703"), "04/08/2026", "12.00", "VISA", True,
            (SemanticZoneType.MERCHANT, SemanticZoneType.ADDRESS, SemanticZoneType.ITEM, SemanticZoneType.FINANCIAL, SemanticZoneType.PAYMENT, SemanticZoneType.REFERENCE), "pharmacy_receipt_view")),
    (("LAKESIDE AUTO", "250 5TH AVE", "HOPKINS, MN 55343", "12/31/2024", "CREDIT CARD", "AMEX SALE", "CARD # XXXXXXXXXXX8007", "APPROVAL CODE: 841286", "ENTRY METHOD: CHIP READ", "SALE AMOUNT: 310.76", "CUSTOMER COPY"),
     _truth(DocumentFamily.PAYMENT_SLIP, "LAKESIDE AUTO", ("250 5TH AVE", "HOPKINS, MN 55343"), "12/31/2024", "310.76", "AMEX", False,
            (SemanticZoneType.MERCHANT, SemanticZoneType.ADDRESS, SemanticZoneType.PAYMENT, SemanticZoneType.FINANCIAL), "payment_slip_view")),
    (("HARBOR SERVICES", "91 PORT ST", "BOSTON, MA 02110", "05/03/2026", "CREDIT CARD SLIP", "CARDHOLDER COPY", "AUTHORIZATION: 551992", "MASKED PAN ****6644", "SIGNATURE", "TOTAL: 84.20", "VISA"),
     _truth(DocumentFamily.CREDIT_CARD_SLIP, "HARBOR SERVICES", ("91 PORT ST", "BOSTON, MA 02110"), "05/03/2026", "84.20", "VISA", False,
            (SemanticZoneType.MERCHANT, SemanticZoneType.ADDRESS, SemanticZoneType.PAYMENT, SemanticZoneType.FINANCIAL), "credit_card_slip_view")),
    (("NORTHSTAR MARKET", "100 MAIN ST", "DENVER, CO 80202", "05/10/2026", "REFUND RECEIPT", "REFUNDED TO CARD", "REFERENCE: R88412", "REFUND AMOUNT: 25.00", "VISA ****1234"),
     _truth(DocumentFamily.REFUND_RECEIPT, "NORTHSTAR MARKET", ("100 MAIN ST", "DENVER, CO 80202"), "05/10/2026", "25.00", "VISA", False,
            (SemanticZoneType.MERCHANT, SemanticZoneType.ADDRESS, SemanticZoneType.FINANCIAL, SemanticZoneType.PAYMENT, SemanticZoneType.REFERENCE), "refund_view")),
    (("NORTHSTAR MARKET", "100 MAIN ST", "DENVER, CO 80202", "05/11/2026", "RETURN RECEIPT", "RETURNED ITEM", "RETURN AUTHORIZATION: A551", "TOTAL: 15.00"),
     _truth(DocumentFamily.RETURN_RECEIPT, "NORTHSTAR MARKET", ("100 MAIN ST", "DENVER, CO 80202"), "05/11/2026", "15.00", "", True,
            (SemanticZoneType.MERCHANT, SemanticZoneType.ADDRESS, SemanticZoneType.ITEM, SemanticZoneType.FINANCIAL, SemanticZoneType.PAYMENT), "refund_view")),
    (("ACME OFFICE SUPPLY", "700 MARKET BLVD", "PHOENIX, AZ 85004", "06/01/2026", "INVOICE # 900128", "BILL TO: SAMPLE CLIENT", "DUE DATE: 06/30/2026", "LINE ITEM SERVICES", "AMOUNT DUE: 120.00", "TOTAL: 120.00"),
     _truth(DocumentFamily.INVOICE, "ACME OFFICE SUPPLY", ("700 MARKET BLVD", "PHOENIX, AZ 85004"), "06/01/2026", "120.00", "", True,
            (SemanticZoneType.MERCHANT, SemanticZoneType.ADDRESS, SemanticZoneType.ITEM, SemanticZoneType.FINANCIAL, SemanticZoneType.REFERENCE), "invoice_view")),
    (("REGIONAL CREDIT UNION", "55 FINANCE DR", "OMAHA, NE 68102", "06/30/2026", "ACCOUNT STATEMENT", "ACCOUNT SUMMARY", "OPENING BALANCE: 200.00", "CLOSING BALANCE: 175.00", "STATEMENT TOTAL: 175.00"),
     _truth(DocumentFamily.STATEMENT, "REGIONAL CREDIT UNION", ("55 FINANCE DR", "OMAHA, NE 68102"), "06/30/2026", "175.00", "", False,
            (SemanticZoneType.MERCHANT, SemanticZoneType.ADDRESS, SemanticZoneType.FINANCIAL, SemanticZoneType.REFERENCE), "statement_view")),
    (("APEX ELECTRONICS", "44 TECH LN", "SEATTLE, WA 98101", "07/04/2026", "WARRANTY RECEIPT", "SERIAL NUMBER: SN12345", "COVERAGE: 24 MONTHS", "EXPIRES: 07/04/2028", "WARRANTY TERMS"),
     _truth(DocumentFamily.WARRANTY, "APEX ELECTRONICS", ("44 TECH LN", "SEATTLE, WA 98101"), "07/04/2026", "", "", False,
            (SemanticZoneType.MERCHANT, SemanticZoneType.ADDRESS, SemanticZoneType.REFERENCE, SemanticZoneType.FOOTER), "warranty_view")),
    (("COMMUNITY RELIEF FUND", "9 HOPE ST", "CHICAGO, IL 60601", "07/20/2026", "DONATION RECEIPT", "CHARITABLE CONTRIBUTION", "TAX DEDUCTIBLE", "DONATION AMOUNT: 75.00", "RECEIPT NUMBER: D1005"),
     _truth(DocumentFamily.DONATION_RECEIPT, "COMMUNITY RELIEF FUND", ("9 HOPE ST", "CHICAGO, IL 60601"), "07/20/2026", "75.00", "", False,
            (SemanticZoneType.MERCHANT, SemanticZoneType.ADDRESS, SemanticZoneType.FINANCIAL, SemanticZoneType.REFERENCE), "donation_receipt_view")),
    (("MISCELLANEOUS DOCUMENT", "GENERAL INFORMATION", "REFERENCE TEXT ONLY"),
     _truth(DocumentFamily.UNKNOWN, "MISCELLANEOUS DOCUMENT", (), "", "", "", False,
            (SemanticZoneType.MERCHANT,), "unknown_view", .15)),
)


def document_family_corpus() -> tuple[FamilyCorpusDocument, ...]:
    documents = []
    for lines, golden in TEMPLATES:
        for condition, content_type, rotation, contrast in VARIANTS:
            documents.append(FamilyCorpusDocument(
                f"{golden.family.value}-{condition}", "anonymized_real_pattern",
                condition, content_type, rotation, contrast, tuple(lines), golden,
            ))
    return tuple(documents)


def build_receipt_document(fixture: FamilyCorpusDocument) -> ReceiptDocument:
    lines = tuple(
        ReceiptLine(f"{fixture.document_id}-line-{index}", text,
                    BoundingBox(60, 55 + index * 62, 850, 42),
                    max(.45, .97 * fixture.contrast), reading_order=index)
        for index, text in enumerate(fixture.lines)
    )
    block = ReceiptBlock(f"{fixture.document_id}-block", BlockType.TEXT, BoundingBox(0, 0, 1000, 1600), .9, lines)
    region = ReceiptRegion(f"{fixture.document_id}-region", RegionType.TEXT, BoundingBox(0, 0, 1000, 1600), .9, (block,))
    geometry = ReceiptGeometrySnapshot(
        ((0, 0), (1000, 0), (1000, 1600), (0, 1600)), Dimensions(1000, 1600), Dimensions(1000, 1600),
        fixture.rotation_degrees, 0, ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (), (), (), .9, (),
    )
    page = ReceiptPage(f"{fixture.document_id}-page", 0, geometry, Dimensions(1000, 1600), CoordinateSpace.CORRECTED_IMAGE, (region,))
    return ReceiptDocument(ReceiptDocumentMetadata.create(source_image_id=fixture.document_id, page_count=1), (page,))
