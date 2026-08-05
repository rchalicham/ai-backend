from __future__ import annotations

from copy import deepcopy
from typing import Callable

from .models import DocumentFamily, DocumentFamilyContext, RegressionFixture, RegressionResult


class DocumentFamilyRegressionSuite:
    """Runs golden sidecar assertions and verifies parser-facing state is untouched."""

    def run_context(self, fixture: RegressionFixture, context: DocumentFamilyContext,
                    parser_payload_before: dict | None = None, parser_payload_after: dict | None = None) -> RegressionResult:
        before = deepcopy(parser_payload_before or {})
        after = deepcopy(parser_payload_after if parser_payload_after is not None else before)
        entities = {(item.entity_type, item.value.lower()) for item in context.entity_candidates}
        checks = [
            ("family", context.activation.family is fixture.expected_family),
            ("item_expectation", context.profile.item_table_expected is fixture.expected_item_table),
            ("entities", all((kind, value.lower()) in entities for kind, value in fixture.expected_entities)),
            ("parser_unchanged", before == after),
        ]
        return RegressionResult(fixture.fixture_id, all(value for _, value in checks), tuple(checks), context, before == after)

    def run(self, fixtures: tuple[RegressionFixture, ...], context_factory: Callable[[RegressionFixture], DocumentFamilyContext]) -> tuple[RegressionResult, ...]:
        return tuple(self.run_context(fixture, context_factory(fixture)) for fixture in fixtures)

    @staticmethod
    def supported_family_fixtures() -> tuple[RegressionFixture, ...]:
        return tuple(
            RegressionFixture(f"golden-{family.value}", (), family, expected_item_table=family in {
                DocumentFamily.RETAIL_RECEIPT, DocumentFamily.RESTAURANT_RECEIPT,
                DocumentFamily.FUEL_RECEIPT, DocumentFamily.RETURN_RECEIPT,
                DocumentFamily.PHARMACY_RECEIPT,
                DocumentFamily.INVOICE,
            })
            for family in (
                DocumentFamily.RETAIL_RECEIPT, DocumentFamily.RESTAURANT_RECEIPT,
                DocumentFamily.FUEL_RECEIPT, DocumentFamily.PAYMENT_SLIP,
                DocumentFamily.PHARMACY_RECEIPT,
                DocumentFamily.REFUND_RECEIPT, DocumentFamily.INVOICE,
                DocumentFamily.STATEMENT, DocumentFamily.WARRANTY,
                DocumentFamily.DONATION_RECEIPT,
            )
        )
