import json
import os
import sys
from dataclasses import FrozenInstanceError, replace

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.receipt_constraints import (
    ArithmeticConstraintValidator,
    ConstraintCandidate,
    ConstraintCandidateGenerator,
    ConstraintCandidateRanker,
    ConstraintCategory,
    ConstraintConfidenceEngine,
    ConstraintDiagnosticsService,
    ConstraintEngine,
    ConstraintExplanationEngine,
    ConstraintGroup,
    ConstraintLearningService,
    ConstraintOutcome,
    ConstraintPenalty,
    ConstraintRule,
    ConstraintVersion,
    ConstraintWeight,
    GrammarConstraintValidator,
    ReceiptConstraint,
    ReceiptConstraintCompiler,
    ReceiptConstraintLoader,
    ReceiptConstraintRepository,
    ReceiptConstraintSerializer,
    StructuralConstraintValidator,
)
from services.receipt_dom import ReceiptDomBuilder
from services.receipt_geometry import Dimensions, Geometry, Point, Region
from services.receipt_grammar import (
    CandidateGrammarRole,
    GrammarCompliance,
    GrammarRoleType,
    ReceiptGrammarContext,
)
from services.receipt_structure import ReceiptPhysicalStructureEngine


def geometry():
    return Geometry(
        receipt_boundary=[Point(0, 0), Point(399, 0), Point(399, 799), Point(0, 799)],
        page_dimensions=Dimensions(400, 800),
        source_dimensions=Dimensions(400, 800),
        rotation=0,
        skew=0,
        perspective_matrix=[[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        detected_columns=[Region(20, 180, 360, 450, "column")],
        estimated_reading_zones=[
            Region(0, 0, 400, 120, "reading"),
            Region(0, 180, 400, 450, "reading"),
            Region(0, 690, 400, 110, "reading"),
        ],
        geometric_confidence=0.95,
    )


@pytest.fixture()
def physical_pair():
    blocks = []
    for row, y in enumerate((40, 230, 270, 310, 710), 1):
        blocks.extend((
            {
                "text": f"LEFT-{row}",
                "confidence": 0.9,
                "x": 30, "y": y, "width": 120, "height": 18,
                "block": row, "line": row, "word": 1,
            },
            {
                "text": f"RIGHT-{row}",
                "confidence": 0.9,
                "x": 250, "y": y, "width": 80, "height": 18,
                "block": row, "line": row, "word": 2,
            },
        ))
    document = ReceiptDomBuilder().build(
        receipt_geometry=geometry(),
        ocr_blocks=blocks,
        source_ocr_engine="constraint-fixture",
    )
    return document, ReceiptPhysicalStructureEngine().analyze(document)


def grammar_context(compliance=0.95):
    return ReceiptGrammarContext(
        receipt_family="family-one",
        loaded=True,
        compliance=GrammarCompliance(
            document_id="document-grammar",
            grammar_id="grammar-family-one",
            grammar_version=1,
            overall_compliance=compliance,
            matched_rules=(
                "header-once",
                "transition:header-items",
                "relationship:header-before-items",
            ),
            candidate_roles=(
                CandidateGrammarRole(
                    "merchant-role",
                    GrammarRoleType.MERCHANT,
                    "header",
                    ("region-header",),
                    0.9,
                ),
            ),
            matched_sections=("header", "items", "footer"),
        ),
    )


def constraint_set(*, rules=None):
    return ReceiptConstraint(
        constraint_set_id="constraints-family-one",
        receipt_family="family-one",
        name="Family One Constraints",
        version=ConstraintVersion(),
        rules=rules or (
            ConstraintRule(
                "arithmetic-total",
                ConstraintCategory.ARITHMETIC,
                "subtotal_tax_total",
                "Subtotal plus tax equals total.",
                "arithmetic-weight",
                "hard-penalty",
                parameters=(("tolerance", "0.01"),),
            ),
            ConstraintRule(
                "grammar-minimum",
                ConstraintCategory.GRAMMAR,
                "grammar_compliance",
                "Grammar compliance meets the minimum.",
                "grammar-weight",
                "medium-penalty",
                parameters=(("minimum", 0.8),),
            ),
            ConstraintRule(
                "section-order",
                ConstraintCategory.ORDERING,
                "section_order",
                "Sections follow expected order.",
                "structural-weight",
                "medium-penalty",
                parameters=(("order", ("header", "items", "footer")),),
            ),
            ConstraintRule(
                "knowledge-minimum",
                ConstraintCategory.KNOWLEDGE,
                "knowledge_confidence",
                "Knowledge confidence meets minimum.",
                "knowledge-weight",
                "soft-penalty",
                parameters=(("minimum", 0.5),),
                required=False,
            ),
        ),
        groups=(
            ConstraintGroup(
                "core", "Core deterministic constraints",
                ("arithmetic-total", "grammar-minimum", "section-order"),
            ),
        ),
        weights=(
            ConstraintWeight("arithmetic-weight", 1.0, ConstraintCategory.ARITHMETIC),
            ConstraintWeight("grammar-weight", 0.8, ConstraintCategory.GRAMMAR),
            ConstraintWeight("structural-weight", 0.7, ConstraintCategory.STRUCTURAL),
            ConstraintWeight("knowledge-weight", 0.4, ConstraintCategory.KNOWLEDGE),
        ),
        penalties=(
            ConstraintPenalty("hard-penalty", 0.5),
            ConstraintPenalty("medium-penalty", 0.25),
            ConstraintPenalty("soft-penalty", 0.1, ConstraintOutcome.WARNING),
        ),
        dependencies=("receipt-grammar-v1",),
    )


def candidate(candidate_id, total, *, grammar=0.95, knowledge=0.8):
    return {
        "candidate_id": candidate_id,
        "interpretation": {
            "subtotal": "10.00",
            "tax": "1.00",
            "total": total,
            "sections": ("header", "items", "footer"),
        },
        "base_confidence": 0.9,
        "grammar_compliance": grammar,
        "knowledge_confidence": knowledge,
        "provenance": ("supplied-test-hypothesis",),
    }


def test_core_constraint_models_are_immutable():
    value = constraint_set()

    with pytest.raises(FrozenInstanceError):
        value.rules = ()  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        value.rules[0].required = False  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        value.weights[0].value = 0.1  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        value.version.entity_version = 2  # type: ignore[misc]


def test_compiler_builds_ordered_runtime_contract():
    compilation = ReceiptConstraintCompiler().compile(constraint_set())

    assert compilation.valid is True
    assert compilation.ordered_rule_ids == (
        "arithmetic-total", "grammar-minimum", "section-order", "knowledge-minimum",
    )
    assert dict(compilation.rules_by_category)["arithmetic"] == ("arithmetic-total",)


def test_compiler_detects_duplicates_cycles_invalid_references_conflicts_and_weights():
    rules = (
        ConstraintRule(
            "duplicate", ConstraintCategory.STRUCTURAL, "required", "Required.",
            weight_id="missing-weight", dependency_ids=("cycle",),
            parameters=(("subject", "items"),),
        ),
        ConstraintRule(
            "duplicate", ConstraintCategory.STRUCTURAL, "forbidden", "Forbidden.",
            dependency_ids=("duplicate",), parameters=(("subject", "items"),),
        ),
        ConstraintRule(
            "cycle", ConstraintCategory.GRAMMAR, "grammar_compliance", "Cycle.",
            dependency_ids=("duplicate",),
        ),
    )
    value = ReceiptConstraint(
        "invalid", "family-one", "Invalid", ConstraintVersion(), rules,
        weights=(ConstraintWeight("invalid-weight", 2.0),),
    )

    compilation = ReceiptConstraintCompiler().compile(value)
    codes = {item.code for item in compilation.diagnostics.errors}

    assert compilation.valid is False
    assert "duplicate_rule_id" in codes
    assert "invalid_weight_reference" in codes
    assert "invalid_constraint_weight" in codes
    assert "conflicting_constraint_rules" in codes
    assert "circular_rule_dependency" in codes


@pytest.mark.parametrize(
    ("rule_type", "interpretation", "expected"),
    [
        ("subtotal_tax_total", {"subtotal": "10", "tax": "1", "total": "11"}, ConstraintOutcome.PASS),
        (
            "subtotal_discount_tax_total",
            {"subtotal": "10", "discount": "1", "tax": "1", "total": "10"},
            ConstraintOutcome.PASS,
        ),
        (
            "quantity_unit_line_total",
            {"lines": ({"quantity": "2", "unit_price": "3.50", "line_total": "7.00"},)},
            ConstraintOutcome.PASS,
        ),
        (
            "multiple_taxes",
            {"subtotal": "10", "taxes": ("0.50", "0.25"), "total": "10.75"},
            ConstraintOutcome.PASS,
        ),
        ("subtotal_tax_total", {"subtotal": "10", "tax": "1", "total": "12"}, ConstraintOutcome.VIOLATION),
    ],
)
def test_arithmetic_validator_evaluates_supplied_values_without_modifying_them(
    rule_type, interpretation, expected,
):
    source = tuple(interpretation.items())
    candidate_value = ConstraintCandidate("candidate", source)
    before = candidate_value.interpretation
    rule = ConstraintRule(
        "arithmetic", ConstraintCategory.ARITHMETIC, rule_type, "Arithmetic test.",
        parameters=(("tolerance", "0.01"), ("currency_precision", 2)),
    )

    result = ArithmeticConstraintValidator().evaluate(rule, candidate_value, penalty=0.5)

    assert result.outcome is expected
    assert candidate_value.interpretation == before


def test_structural_validator_uses_candidate_structure_and_physical_boundaries(physical_pair):
    document, structure = physical_pair
    candidate_value = ConstraintCandidate(
        "candidate",
        (("sections", ("header", "items", "footer")),),
    )
    order = ConstraintRule(
        "order", ConstraintCategory.ORDERING, "section_order", "Order.",
        parameters=(("order", ("header", "items", "footer")),),
    )
    boundaries = ConstraintRule(
        "boundaries", ConstraintCategory.STRUCTURAL, "receipt_boundaries", "Bounds.",
    )
    validator = StructuralConstraintValidator()

    assert validator.evaluate(
        order, candidate_value, document, structure, penalty=0.2,
    ).outcome is ConstraintOutcome.PASS
    assert validator.evaluate(
        boundaries, candidate_value, document, structure, penalty=0.2,
    ).outcome is ConstraintOutcome.PASS


def test_grammar_validator_consumes_existing_compliance_without_revalidating_grammar():
    context = grammar_context()
    candidate_value = ConstraintCandidate("candidate", (), grammar_compliance=0.95)
    rules = (
        ConstraintRule(
            "grammar", ConstraintCategory.GRAMMAR, "grammar_compliance", "Grammar.",
            parameters=(("minimum", 0.9),),
        ),
        ConstraintRule(
            "transition", ConstraintCategory.TRANSITION, "transition_compliance", "Transition.",
            parameters=(("transition_id", "header-items"),),
        ),
        ConstraintRule(
            "relationship", ConstraintCategory.RELATIONSHIP, "relationship_compliance", "Relationship.",
            parameters=(("relationship_id", "header-before-items"),),
        ),
        ConstraintRule(
            "role", ConstraintCategory.GRAMMAR, "role_expectation", "Role.",
            parameters=(("role_type", "merchant"),),
        ),
    )

    results = tuple(
        GrammarConstraintValidator().evaluate(
            rule, candidate_value, context, penalty=0.2,
        )
        for rule in rules
    )

    assert all(result.outcome is ConstraintOutcome.PASS for result in results)
    assert context.compliance.overall_compliance == 0.95


def test_candidate_generator_creates_multiple_supplied_hypotheses_without_selecting():
    generated = ConstraintCandidateGenerator().generate(
        grammar_context(),
        (
            candidate("candidate-a", "11.00"),
            candidate("candidate-b", "12.00"),
            candidate("candidate-c", "11.00", grammar=0.6),
        ),
    )

    assert [item.candidate_id for item in generated] == [
        "candidate-a", "candidate-b", "candidate-c",
    ]
    assert all(item.source == "supplied_hypothesis" for item in generated)


def test_candidate_generator_uses_only_grammar_structure_when_no_values_are_supplied():
    generated = ConstraintCandidateGenerator().generate(grammar_context())
    interpretation = dict(generated[0].interpretation)

    assert generated[0].source == "receipt_grammar_sidecar"
    assert interpretation["sections"] == ("header", "items", "footer")
    assert "subtotal" not in interpretation
    assert "total" not in interpretation


def test_engine_ranks_valid_candidate_and_explains_rejections(physical_pair):
    document, structure = physical_pair
    repository = ReceiptConstraintRepository()
    repository.save_constraints(constraint_set())
    result = ConstraintEngine(repository=repository).evaluate(
        document,
        structure,
        grammar_context(),
        (
            candidate("candidate-a", "11.00"),
            candidate("candidate-b", "12.00"),
            candidate("candidate-c", "11.00", grammar=0.6),
        ),
    )

    assert result.loaded is True
    assert result.decision.best_candidate.candidate_id == "candidate-a"
    assert [item.candidate_id for item in result.decision.rejected_candidates] == [
        "candidate-c", "candidate-b",
    ]
    assert "Candidate candidate-a selected" in result.decision.reason
    score_by_id = {score.candidate_id: score for score in result.decision.scores}
    assert score_by_id["candidate-a"].arithmetic_score == 1
    assert score_by_id["candidate-b"].arithmetic_score == 0
    assert score_by_id["candidate-b"].violations
    assert dict(result.diagnostics)["candidateDecisionAuthoritative"] is False
    assert dict(result.diagnostics)["businessFactsGenerated"] is False


def test_confidence_engine_aggregates_without_overwriting_components():
    engine = ConstraintConfidenceEngine()
    result = engine.combine(
        grammar=0.9, knowledge=0.8, arithmetic=1.0,
        structural=0.7, constraint=0.85,
    )

    assert 0 <= result.normalized <= 1
    assert result.grammar == 0.9
    assert result.knowledge == 0.8
    assert result.arithmetic == 1.0
    assert dict(result.components)["structural"] == 0.7


def test_repository_versions_archives_lists_indexes_and_compares():
    repository = ReceiptConstraintRepository()
    first = repository.saveConstraints(constraint_set())
    second_definition = replace(
        first,
        rules=first.rules + (
            ConstraintRule(
                "new-rule", ConstraintCategory.CONFIDENCE,
                "minimum", "New confidence rule.",
            ),
        ),
    )
    second = repository.versionConstraints(second_definition, expected_version=1)
    comparison = repository.compareConstraintVersions("family-one", 1, 2)

    assert first.version.entity_version == 1
    assert second.version.entity_version == 2
    assert comparison.added_rules == ("new-rule",)
    assert repository.index().receipt_families == ("family-one",)
    repository.archiveConstraints("family-one", 1)
    assert len(repository.listConstraintSets("family-one")) == 1
    assert len(repository.listConstraintSets("family-one", include_archived=True)) == 2


def test_serializer_and_loader_round_trip_and_expose_diagnostics_validity():
    source = constraint_set()
    serializer = ReceiptConstraintSerializer()
    loaded = ReceiptConstraintLoader().from_json(serializer.to_json(source, pretty=True))
    compilation = ReceiptConstraintCompiler().compile(source)
    payload = serializer.to_dict(compilation)

    assert loaded == source
    assert payload["diagnostics"]["valid"] is True
    assert json.loads(serializer.to_json(compilation))["schema_version"] == "compiled-receipt-constraints-v1"


def test_diagnostics_service_partitions_findings():
    diagnostics = ConstraintDiagnosticsService()
    result = diagnostics.build((
        diagnostics.error("error", "Error"),
        diagnostics.warning("warning", "Warning"),
        diagnostics.information("info", "Information"),
    ))

    assert result.valid is False
    assert result.errors[0].code == "error"
    assert result.warnings[0].code == "warning"
    assert result.information[0].code == "info"


def test_learning_suggestions_are_approval_only_and_do_not_mutate_constraints(physical_pair):
    document, structure = physical_pair
    repository = ReceiptConstraintRepository()
    source = repository.save_constraints(constraint_set())
    result = ConstraintEngine(repository=repository).evaluate(
        document,
        structure,
        grammar_context(),
        (candidate("candidate-b", "12.00"),),
    )

    assert result.learning_suggestions
    assert all(item.requires_approval for item in result.learning_suggestions)
    assert repository.load_constraints("family-one") == source


def test_explanation_engine_reports_empty_candidate_state():
    decision = ConstraintExplanationEngine().decide((), ())

    assert decision.best_candidate is None
    assert decision.ranked_candidates == ()
    assert "No candidate interpretation" in decision.reason


def test_engine_missing_repository_is_safe_non_authoritative_sidecar(physical_pair):
    document, structure = physical_pair

    result = ConstraintEngine().evaluate(document, structure, grammar_context())

    assert result.loaded is False
    assert dict(result.diagnostics)["warning"] == "matching_constraint_set_not_found"
    assert dict(result.diagnostics)["affectsExtraction"] is False
    assert dict(result.diagnostics)["parserAuthorityChanged"] is False
