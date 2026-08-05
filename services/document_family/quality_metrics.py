from __future__ import annotations

from dataclasses import asdict, dataclass
from types import SimpleNamespace
from typing import Any

from services.presentation_projection import PresentationProjectionEngine
from services.presentation_projection.serializer import PresentationProjectionSerializer

from .accuracy_corpus import FamilyCorpusDocument, build_receipt_document, document_family_corpus
from .family_engine import DocumentFamilyEngine


METRIC_NAMES = (
    "recognition", "merchant", "address", "date", "total", "item",
    "semantic_zones", "projection", "reasoning", "family_confidence",
    "grammar_confidence", "constraint_confidence", "business_projection_confidence",
)


@dataclass(frozen=True, slots=True)
class FamilyQualityResult:
    document_id: str
    family: str
    scan_condition: str
    content_type: str
    passed: bool
    checks: tuple[tuple[str, bool], ...]
    confidences: tuple[tuple[str, float], ...]
    missing_fields: tuple[str, ...]
    expected: tuple[tuple[str, Any], ...]
    actual: tuple[tuple[str, Any], ...]


@dataclass(frozen=True, slots=True)
class FamilyQualitySummary:
    family: str
    documents: int
    passed: int
    metrics: tuple[tuple[str, float], ...]
    average_confidence: float
    status: str


@dataclass(frozen=True, slots=True)
class DocumentFamilyQualityReport:
    corpus_version: str
    total_documents: int
    passed_documents: int
    regression_status: str
    overall_metrics: tuple[tuple[str, float], ...]
    family_coverage: tuple[str, ...]
    family_summaries: tuple[FamilyQualitySummary, ...]
    results: tuple[FamilyQualityResult, ...]
    parser_authority_unchanged: bool = True


class DocumentFamilyQualityRunner:
    def __init__(self, family_engine=None, projection_engine=None):
        self.family_engine = family_engine or DocumentFamilyEngine()
        self.projection_engine = projection_engine or PresentationProjectionEngine()

    def evaluate(self, fixture: FamilyCorpusDocument) -> FamilyQualityResult:
        document = build_receipt_document(fixture)
        structure = SimpleNamespace(candidate_tables=(object(),) if fixture.golden.items_expected else ())
        parser = {
            "company": fixture.golden.merchant,
            "storeAddress": "\n".join(fixture.golden.address),
            "purchaseDate": fixture.golden.date,
            "total": fixture.golden.total,
            "items": [{"name": "golden item"}] if fixture.golden.items_expected else [],
            "paymentCard": {"brand": fixture.golden.payment},
        }
        parser_before = repr(parser)
        context = self.family_engine.evaluate(document, structure, None)
        projection = self.projection_engine.project(
            parser=parser, document_family_context=context, document_id=fixture.document_id,
        )
        fields = {field.key: field for field in projection.fields}
        merchant = context.merchant_candidates[0].value if context.merchant_candidates else ""
        addresses = tuple(item.value for item in context.address_candidates)
        dates = tuple(item.value for item in context.entity_candidates if item.entity_type.value == "date")
        totals = tuple(item.value for item in context.entity_candidates if item.entity_type.value == "financial_amount")
        zones = {zone.zone_type for zone in context.semantic_zones}
        projection_total = str(getattr(fields.get("total"), "displayed_value", "") or "")
        checks = (
            ("recognition", context.activation.family is fixture.golden.family),
            ("merchant", merchant.casefold() == fixture.golden.merchant.casefold()),
            ("address", all(expected.casefold() in {value.casefold() for value in addresses} for expected in fixture.golden.address)),
            ("date", not fixture.golden.date or fixture.golden.date in dates),
            ("total", not fixture.golden.total or fixture.golden.total in totals),
            ("item", context.profile.item_table_expected is fixture.golden.items_expected),
            ("semantic_zones", set(fixture.golden.semantic_zones) <= zones),
            ("projection", projection.metadata.business_view == fixture.golden.projection),
            ("reasoning", context.activation.reason == fixture.golden.reasoning),
            ("family_confidence", context.activation.confidence >= fixture.golden.minimum_confidence),
            ("grammar_confidence", bool(context.activated_grammar)),
            ("constraint_confidence", bool(context.activated_constraints)),
            ("business_projection_confidence", projection.overall_confidence.display >= .2),
            ("projection_total", not fixture.golden.total or projection_total == fixture.golden.total),
            ("parser_unchanged", repr(parser) == parser_before),
        )
        check_map = dict(checks)
        missing = tuple(name for name in ("merchant", "address", "date", "total") if not check_map[name])
        expected = tuple(fixture.golden.business_projection)
        actual = (
            ("merchant", merchant), ("address", addresses), ("date", dates),
            ("total", totals), ("business_view", projection.metadata.business_view),
        )
        confidences = (
            ("family", context.activation.confidence),
            ("grammar", 1.0 if context.activated_grammar else 0.0),
            ("constraint", 1.0 if context.activated_constraints else 0.0),
            ("business_projection", projection.overall_confidence.display),
        )
        return FamilyQualityResult(
            fixture.document_id, fixture.golden.family.value, fixture.scan_condition,
            fixture.content_type, all(value for _, value in checks), checks, confidences,
            missing, expected, actual,
        )

    def run(self, corpus=None) -> DocumentFamilyQualityReport:
        fixtures = tuple(corpus or document_family_corpus())
        results = tuple(self.evaluate(fixture) for fixture in fixtures)
        families = sorted({result.family for result in results})
        summaries = tuple(self._summarize(family, tuple(item for item in results if item.family == family)) for family in families)
        metrics = tuple((metric, self._accuracy(results, metric)) for metric in METRIC_NAMES)
        passed = sum(item.passed for item in results)
        return DocumentFamilyQualityReport(
            "document-family-corpus-v1", len(results), passed,
            "passed" if passed == len(results) else "failed", metrics, tuple(families),
            summaries, results, all(dict(item.checks).get("parser_unchanged") for item in results),
        )

    def assert_quality_gate(self, report, baseline=None):
        failures = [item.document_id for item in report.results if not item.passed]
        if baseline:
            current = {item.family: item for item in report.family_summaries}
            previous = {item.family: item for item in baseline.family_summaries}
            for family in set(current) & set(previous):
                if current[family].average_confidence + 1e-9 < previous[family].average_confidence:
                    failures.append(f"{family}:confidence_drop")
        if failures:
            raise AssertionError("document_family_quality_gate_failed:" + ",".join(failures))
        return report

    def _summarize(self, family, results):
        metrics = tuple((metric, self._accuracy(results, metric)) for metric in METRIC_NAMES)
        confidence = sum(dict(item.confidences)["family"] for item in results) / max(len(results), 1)
        passed = sum(item.passed for item in results)
        return FamilyQualitySummary(family, len(results), passed, metrics, round(confidence, 4), "passed" if passed == len(results) else "failed")

    @staticmethod
    def _accuracy(results, metric):
        values = [dict(item.checks).get(metric, True) for item in results]
        return round(sum(bool(value) for value in values) / max(len(values), 1), 4)


def quality_report_to_dict(value):
    if hasattr(value, "__dataclass_fields__"):
        return {key: quality_report_to_dict(item) for key, item in asdict(value).items()}
    if isinstance(value, tuple):
        if value and all(isinstance(item, tuple) and len(item) == 2 for item in value):
            return {str(key): quality_report_to_dict(item) for key, item in value}
        return [quality_report_to_dict(item) for item in value]
    if isinstance(value, list): return [quality_report_to_dict(item) for item in value]
    if isinstance(value, dict): return {str(key): quality_report_to_dict(item) for key, item in value.items()}
    return value
