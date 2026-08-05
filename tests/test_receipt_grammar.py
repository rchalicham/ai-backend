import json
import os
import sys
from dataclasses import FrozenInstanceError, replace

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.merchant_intelligence import MerchantBlueprint, MerchantIdentity, ReceiptFamily
from services.receipt_classification import ReceiptClassificationEngine, ReceiptFeatureExtractor
from services.receipt_dom import ReceiptDomBuilder
from services.receipt_geometry import Dimensions, Geometry, Point, Region
from services.receipt_grammar import (
    GrammarConfidence,
    GrammarExpectation,
    GrammarMetadata,
    GrammarRelationship,
    GrammarRelationshipType,
    GrammarRole,
    GrammarRoleType,
    GrammarRule,
    GrammarRuleType,
    GrammarSection,
    GrammarSectionType,
    GrammarTransition,
    GrammarTransitionType,
    GrammarVersion,
    ReceiptGrammar,
    ReceiptGrammarCompiler,
    ReceiptGrammarEngine,
    ReceiptGrammarLearningService,
    ReceiptGrammarLoader,
    ReceiptGrammarRepository,
    ReceiptGrammarSerializer,
    ReceiptGrammarValidator,
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
        geometric_confidence=0.94,
    )


def words():
    values = []
    for row, y in enumerate((40, 230, 265, 300, 335, 720), 1):
        for column, (x, width) in enumerate(((30, 150), (250, 80)), 1):
            values.append({
                "text": f"PHYSICAL-{row}-{column}",
                "confidence": 0.9,
                "x": x,
                "y": y,
                "width": width,
                "height": 18,
                "block": row,
                "paragraph": 1,
                "line": row,
                "word": column,
            })
    return values


@pytest.fixture()
def physical_pair():
    document = ReceiptDomBuilder().build(
        receipt_geometry=geometry(),
        ocr_blocks=words(),
        source_ocr_engine="grammar-fixture",
    )
    return document, ReceiptPhysicalStructureEngine().analyze(document)


def grammar(*, transitions=None, rules=None, relationships=None):
    sections = (
        GrammarSection(
            "header", GrammarSectionType.HEADER, "Header",
            role_ids=("merchant-role",), required=True, minimum_occurrences=1,
        ),
        GrammarSection(
            "body", GrammarSectionType.BODY, "Body",
            required=True, minimum_occurrences=1,
        ),
        GrammarSection(
            "items", GrammarSectionType.ITEMS, "Items",
            role_ids=("item-role",), required=True, repeatable=True,
            minimum_occurrences=1, maximum_occurrences=None,
        ),
        GrammarSection(
            "footer", GrammarSectionType.FOOTER, "Footer",
            role_ids=("reference-role",), required=False,
        ),
    )
    return ReceiptGrammar(
        metadata=GrammarMetadata("grammar-family-one", "family-one", "Family One Grammar"),
        version=GrammarVersion(),
        sections=sections,
        roles=(
            GrammarRole("merchant-role", GrammarRoleType.MERCHANT, "header", required=True),
            GrammarRole("item-role", GrammarRoleType.ITEM, "items", required=True, repeatable=True),
            GrammarRole("reference-role", GrammarRoleType.REFERENCE, "footer"),
        ),
        relationships=relationships or (
            GrammarRelationship(
                "header-before-items", "header", "items",
                GrammarRelationshipType.BEFORE, required=True,
            ),
        ),
        transitions=transitions or (
            GrammarTransition("header-body", "header", "body", GrammarTransitionType.REQUIRED),
            GrammarTransition("body-items", "body", "items", GrammarTransitionType.REQUIRED),
            GrammarTransition("items-footer", "items", "footer", GrammarTransitionType.OPTIONAL),
        ),
        rules=rules or (
            GrammarRule("header-once", GrammarRuleType.OCCURS_ONCE, "header", description="Header occurs once"),
            GrammarRule("body-once", GrammarRuleType.OCCURS_ONCE, "body", description="Body occurs once"),
            GrammarRule("items-repeat", GrammarRuleType.REPEATS, "items", description="Items repeat"),
            GrammarRule(
                "items-follow-body", GrammarRuleType.FOLLOWS, "items",
                target_id="body", description="Items follow Body",
            ),
            GrammarRule(
                "footer-optional", GrammarRuleType.OPTIONAL, "footer",
                description="Footer is optional", required=False,
            ),
            GrammarRule(
                "footer-ends", GrammarRuleType.ENDS_DOCUMENT, "footer",
                description="Footer ends document", required=False,
            ),
        ),
        expectations=(
            GrammarExpectation(
                "merchant-expectation", "merchant-role",
                "The header may contain a merchant role expectation.",
            ),
        ),
        confidence=GrammarConfidence(0.95, (("authored", 1.0), ("sampleSupport", 0.9))),
    )


def blueprint_for(document, structure):
    vector = ReceiptFeatureExtractor().extract(document, structure)
    metrics = {}
    for key, value in vector.flatten():
        group, name = key.split(".", 1)
        metrics.setdefault(group, {})[name] = value
    family = ReceiptFamily(
        family_id="family-one",
        merchant_id="knowledge-owner",
        name="Family One",
        confidence=1.0,
        attributes=(("physical_features", metrics),),
    )
    return MerchantBlueprint(
        identity=MerchantIdentity("knowledge-owner", "Knowledge Owner"),
        receipt_families=(family,),
    )


def test_all_grammar_models_are_immutable():
    value = grammar()

    with pytest.raises(FrozenInstanceError):
        value.sections = ()  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        value.sections[0].required = False  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        value.roles[0].role_type = GrammarRoleType.UNKNOWN  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        value.version.entity_version = 2  # type: ignore[misc]


def test_compiler_accepts_declarative_acyclic_grammar():
    compilation = ReceiptGrammarCompiler().compile(grammar())

    assert compilation.valid is True
    assert compilation.diagnostics.errors == ()
    assert compilation.ordered_section_ids.index("header") < compilation.ordered_section_ids.index("items")


def test_compiler_detects_transition_cycles_and_invalid_relationships():
    value = grammar(
        transitions=(
            GrammarTransition("header-body", "header", "body", GrammarTransitionType.REQUIRED),
            GrammarTransition("body-header", "body", "header", GrammarTransitionType.REQUIRED),
        ),
        relationships=(
            GrammarRelationship(
                "invalid", "missing-role", "items",
                GrammarRelationshipType.CONTAINS, required=True,
            ),
        ),
    )

    compilation = ReceiptGrammarCompiler().compile(value)
    codes = {item.code for item in compilation.diagnostics.errors}

    assert compilation.valid is False
    assert "transition_cycle" in codes
    assert "unknown_relationship_source" in codes


def test_compiler_detects_required_optional_and_occurrence_rule_conflicts():
    source = grammar(rules=(
        GrammarRule("header-required", GrammarRuleType.REQUIRED, "header"),
        GrammarRule("header-optional", GrammarRuleType.OPTIONAL, "header"),
        GrammarRule("items-once", GrammarRuleType.OCCURS_ONCE, "items"),
        GrammarRule("items-repeat", GrammarRuleType.REPEATS, "items"),
    ))
    value = replace(
        source,
        sections=source.sections + (
            GrammarSection(
                "invalid-repeat",
                GrammarSectionType.UNKNOWN,
                "Invalid Repeat",
                repeatable=True,
                maximum_occurrences=1,
            ),
            GrammarSection(
                "optional-positive-minimum",
                GrammarSectionType.UNKNOWN,
                "Optional Positive Minimum",
                required=False,
                minimum_occurrences=1,
                maximum_occurrences=2,
            ),
        ),
    )

    compilation = ReceiptGrammarCompiler().compile(value)
    codes = {item.code for item in compilation.diagnostics.errors}

    assert "required_optional_conflict" in codes
    assert "occurrence_rule_conflict" in codes
    assert "repeatable_section_single_maximum" in codes
    assert "optional_section_positive_minimum" in {
        item.code for item in compilation.diagnostics.warnings
    }


def test_validator_reports_compliance_and_candidate_roles_without_values(physical_pair):
    document, structure = physical_pair
    compliance = ReceiptGrammarValidator().validate(document, structure, grammar())
    payload = ReceiptGrammarSerializer().to_dict(compliance)

    assert compliance.document_id == document.id
    assert 0 <= compliance.overall_compliance <= 1
    assert "header-once" in compliance.matched_rules
    assert all(candidate.basis == "physical_structure_compatibility" for candidate in compliance.candidate_roles)
    assert {candidate.role_type for candidate in compliance.candidate_roles} <= {
        GrammarRoleType.MERCHANT, GrammarRoleType.ITEM, GrammarRoleType.REFERENCE,
    }
    assert "detected_value" not in json.dumps(payload)
    assert "merchantName" not in json.dumps(payload)


def test_validator_checks_physical_transition_and_relationship_order(physical_pair):
    document, structure = physical_pair
    value = grammar(
        transitions=(
            GrammarTransition(
                "items-before-header",
                "items",
                "header",
                GrammarTransitionType.REQUIRED,
            ),
        ),
        relationships=(
            GrammarRelationship(
                "header-after-items",
                "header",
                "items",
                GrammarRelationshipType.AFTER,
                required=True,
            ),
        ),
    )

    compliance = ReceiptGrammarValidator().validate(document, structure, value)
    codes = {item.code for item in compliance.violations}

    assert "required_transition_not_observed" in codes
    assert "required_relationship_not_observed" in codes
    assert "transition:items-before-header" in compliance.missing_rules
    assert "relationship:header-after-items" in compliance.missing_rules


def test_repository_versions_archives_lists_and_compares():
    repository = ReceiptGrammarRepository()
    first = repository.saveGrammar(grammar())
    second_definition = replace(
        first,
        sections=first.sections + (
            GrammarSection("payment", GrammarSectionType.PAYMENT, "Payment"),
        ),
        rules=first.rules + (
            GrammarRule("payment-optional", GrammarRuleType.OPTIONAL, "payment", required=False),
        ),
    )
    second = repository.versionGrammar(second_definition, expected_version=1)
    comparison = repository.compareGrammarVersions("family-one", 1, 2)

    assert first.version.entity_version == 1
    assert second.version.entity_version == 2
    assert repository.loadGrammar("family-one") == second
    assert comparison.added_sections == ("payment",)
    assert comparison.added_rules == ("payment-optional",)
    archived = repository.archiveGrammar("family-one", 1)
    assert archived.version.status == "archived"
    assert len(repository.listGrammars("family-one")) == 1
    assert len(repository.listGrammars("family-one", include_archived=True)) == 2


def test_repository_rejects_optimistic_version_conflict():
    repository = ReceiptGrammarRepository()
    repository.save_grammar(grammar())

    with pytest.raises(ValueError, match="receipt_grammar_version_conflict"):
        repository.version_grammar(grammar(), expected_version=0)


def test_serializer_and_loader_round_trip_grammar():
    serializer = ReceiptGrammarSerializer()
    source = grammar()
    encoded = serializer.to_json(source, pretty=True)
    loaded = ReceiptGrammarLoader().from_json(encoded)
    compilation_payload = serializer.to_dict(ReceiptGrammarCompiler().compile(source))

    assert loaded == source
    assert loaded.metadata.receipt_family == "family-one"
    assert loaded.transitions[0].transition_type is GrammarTransitionType.REQUIRED
    assert loaded.confidence.components == (("authored", 1.0), ("sampleSupport", 0.9))
    assert compilation_payload["diagnostics"]["valid"] is True


def test_learning_creates_approval_only_suggestions_and_does_not_mutate_grammar(physical_pair):
    document, structure = physical_pair
    source = grammar()
    value = replace(
        source,
        sections=source.sections + (
            GrammarSection(
                "payment", GrammarSectionType.PAYMENT, "Payment",
                required=True, minimum_occurrences=1,
            ),
        ),
        rules=(
            GrammarRule(
                "payment-required", GrammarRuleType.REQUIRED, "payment",
                description="Payment structure required for this test",
            ),
        ),
    )
    compliance = ReceiptGrammarValidator().validate(document, structure, value)
    before = value

    suggestions = ReceiptGrammarLearningService().suggest(value, compliance)

    assert value == before
    assert suggestions
    assert all(item.requires_approval for item in suggestions)
    assert all(item.evidence_references == (document.id,) for item in suggestions)


def test_engine_loads_grammar_by_classified_family_as_non_authoritative_sidecar(physical_pair):
    document, structure = physical_pair
    classification = ReceiptClassificationEngine().classify(
        document, structure, (blueprint_for(document, structure),),
    )
    repository = ReceiptGrammarRepository()
    repository.save_grammar(grammar())
    context = ReceiptGrammarEngine(repository=repository).evaluate(
        document, structure, classification,
    )

    assert context.loaded is True
    assert context.receipt_family == "family-one"
    assert context.compliance is not None
    assert dict(context.diagnostics)["affectsExtraction"] is False
    assert dict(context.diagnostics)["parserAuthorityChanged"] is False
    assert dict(context.diagnostics)["merchantDetectionPerformed"] is False
    assert dict(context.diagnostics)["productDetectionPerformed"] is False
    assert dict(context.diagnostics)["grammarExecutedAsParser"] is False


def test_engine_returns_diagnostics_when_classification_has_no_family(physical_pair):
    document, structure = physical_pair
    classification = ReceiptClassificationEngine().classify(document, structure)

    context = ReceiptGrammarEngine().evaluate(document, structure, classification)

    assert context.loaded is False
    assert dict(context.diagnostics)["warning"] == "no_classified_receipt_family"
    assert dict(context.diagnostics)["affectsExtraction"] is False
