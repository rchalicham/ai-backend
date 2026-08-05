from __future__ import annotations

from .models import (
    GrammarExpectation,
    GrammarMetadata,
    GrammarRole,
    GrammarRoleType,
    GrammarSection,
    GrammarSectionType,
    GrammarVersion,
    ReceiptGrammar,
)


def payment_slip_grammar() -> ReceiptGrammar:
    """Non-authoritative expectations for payment/card transaction slips."""
    expectations = (
        GrammarExpectation("merchant", "merchant-role", "Merchant identity", required=True),
        GrammarExpectation("date", "metadata-role", "Transaction date", required=True),
        GrammarExpectation("total", "financial-role", "Transaction total", required=True),
        GrammarExpectation("payment-method", "payment-role", "Payment method", required=True),
        GrammarExpectation("approval-code", "reference-role", "Approval code", required=True),
        GrammarExpectation("card", "payment-role", "Card brand or masked card", required=True),
    )
    roles = (
        GrammarRole("merchant-role", GrammarRoleType.MERCHANT, "header", True, expectation_ids=("merchant",)),
        GrammarRole("metadata-role", GrammarRoleType.METADATA, "header", True, expectation_ids=("date",)),
        GrammarRole("payment-role", GrammarRoleType.PAYMENT, "payment", True, expectation_ids=("payment-method", "card")),
        GrammarRole("reference-role", GrammarRoleType.REFERENCE, "payment", True, expectation_ids=("approval-code",)),
        GrammarRole("financial-role", GrammarRoleType.FINANCIAL, "summary", True, expectation_ids=("total",)),
    )
    return ReceiptGrammar(
        metadata=GrammarMetadata(
            "payment-slip-v1", "payment-slip", "Payment Slip",
            "A transaction slip where an item table is neither required nor expected.",
            tags=("payment", "credit-card-slip", "zero-items-valid"),
        ),
        version=GrammarVersion(),
        sections=(
            GrammarSection("header", GrammarSectionType.HEADER, "Merchant and date", ("merchant-role", "metadata-role"), True, minimum_occurrences=1),
            GrammarSection("payment", GrammarSectionType.PAYMENT, "Card and authorization", ("payment-role", "reference-role"), True, minimum_occurrences=1),
            GrammarSection("summary", GrammarSectionType.FINANCIAL_SUMMARY, "Transaction total", ("financial-role",), True, minimum_occurrences=1),
        ),
        roles=roles,
        expectations=expectations,
    )


def retail_receipt_grammar() -> ReceiptGrammar:
    """Non-authoritative expectations for itemized retail receipts."""
    return ReceiptGrammar(
        metadata=GrammarMetadata("retail-receipt-v1", "retail-receipt", "Retail Receipt"),
        version=GrammarVersion(),
        sections=(
            GrammarSection("header", GrammarSectionType.HEADER, "Merchant", ("merchant-role",), True, minimum_occurrences=1),
            GrammarSection("items", GrammarSectionType.ITEMS, "Purchased items", ("item-role",), True, True, 1, None),
            GrammarSection("summary", GrammarSectionType.FINANCIAL_SUMMARY, "Totals", ("financial-role",), True, minimum_occurrences=1),
        ),
        roles=(
            GrammarRole("merchant-role", GrammarRoleType.MERCHANT, "header", True),
            GrammarRole("item-role", GrammarRoleType.ITEM, "items", True, True),
            GrammarRole("financial-role", GrammarRoleType.FINANCIAL, "summary", True),
        ),
        expectations=(
            GrammarExpectation("merchant", "merchant-role", "Merchant identity", True),
            GrammarExpectation("item-table", "item-role", "At least one purchased item", True),
            GrammarExpectation("total", "financial-role", "Receipt total", True),
        ),
    )


def builtin_grammars() -> tuple[ReceiptGrammar, ...]:
    return payment_slip_grammar(), retail_receipt_grammar()
