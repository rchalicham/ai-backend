import os
import sys
from dataclasses import FrozenInstanceError, replace

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.document_family import (
    DocumentFamily, DocumentFamilyQualityRunner, document_family_corpus,
    quality_report_to_dict,
)


def test_corpus_covers_every_required_family_and_scan_upload_condition():
    corpus = document_family_corpus()
    assert len(corpus) == 130
    assert {item.golden.family for item in corpus} == set(DocumentFamily)
    conditions = {item.scan_condition for item in corpus}
    assert {"real", "edge-case", "poor-scan", "rotated-scan", "low-contrast", "thermal-paper", "partial-receipt"} <= conditions
    assert {item.content_type for item in corpus} >= {"application/pdf", "image/jpeg", "image/png", "image/heic"}
    for family in DocumentFamily:
        family_documents = [item for item in corpus if item.golden.family is family]
        assert len(family_documents) == 10
        assert all(item.source_kind == "anonymized_real_pattern" for item in family_documents)


def test_every_golden_truth_contains_complete_expected_contract():
    for fixture in document_family_corpus():
        truth = fixture.golden
        assert truth.family
        assert truth.merchant
        assert truth.semantic_zones
        assert truth.projection
        assert truth.minimum_confidence > 0
        assert truth.reasoning
        assert dict(truth.business_projection)["business_view"] == truth.projection


def test_full_document_family_quality_gate_passes_and_parser_authority_is_unchanged():
    runner = DocumentFamilyQualityRunner()
    report = runner.assert_quality_gate(runner.run())
    assert report.regression_status == "passed"
    assert report.passed_documents == report.total_documents == 130
    assert report.parser_authority_unchanged is True
    assert all(value == 1.0 for _, value in report.overall_metrics)
    assert all(summary.status == "passed" for summary in report.family_summaries)


@pytest.mark.parametrize("protected_check", ["recognition", "merchant", "projection", "reasoning"])
def test_gate_fails_when_protected_golden_result_changes(protected_check):
    runner = DocumentFamilyQualityRunner()
    report = runner.run()
    first = report.results[0]
    checks = tuple((name, False if name == protected_check else value) for name, value in first.checks)
    broken = replace(first, checks=checks, passed=False)
    degraded = replace(report, results=(broken,) + report.results[1:], passed_documents=129, regression_status="failed")
    with pytest.raises(AssertionError, match="quality_gate_failed"):
        runner.assert_quality_gate(degraded)


def test_gate_fails_when_family_confidence_drops_from_baseline():
    runner = DocumentFamilyQualityRunner()
    baseline = runner.run()
    first = baseline.family_summaries[0]
    degraded = replace(baseline, family_summaries=(replace(first, average_confidence=first.average_confidence - .01),) + baseline.family_summaries[1:])
    with pytest.raises(AssertionError, match="confidence_drop"):
        runner.assert_quality_gate(degraded, baseline=baseline)


def test_pharmacy_activates_grammar_constraints_zones_and_projection():
    report = DocumentFamilyQualityRunner().run(
        tuple(item for item in document_family_corpus() if item.golden.family is DocumentFamily.PHARMACY_RECEIPT)
    )
    assert report.total_documents == report.passed_documents == 10
    assert dict(report.overall_metrics)["recognition"] == 1.0
    assert dict(report.overall_metrics)["grammar_confidence"] == 1.0
    assert dict(report.overall_metrics)["constraint_confidence"] == 1.0
    assert dict(report.overall_metrics)["projection"] == 1.0


def test_corpus_and_quality_models_are_immutable_and_dashboard_serializable():
    fixture = document_family_corpus()[0]
    with pytest.raises(FrozenInstanceError):
        fixture.scan_condition = "changed"
    payload = quality_report_to_dict(DocumentFamilyQualityRunner().run())
    assert payload["corpus_version"] == "document-family-corpus-v1"
    assert payload["regression_status"] == "passed"
    assert len(payload["family_summaries"]) == 13

