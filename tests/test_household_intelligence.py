import os
import sys
from dataclasses import FrozenInstanceError

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api.household_routes import (
    assets, dashboard, goals, insights, members, ownership, pets,
    preferences, recommendations, relationships, responsibilities, summary,
)
from services.household_intelligence import (
    ConsumptionRecord, Goal, Household, HouseholdAsset,
    HouseholdConsumptionEngine, HouseholdIntelligenceEngine,
    HouseholdIntelligenceLoader, HouseholdIntelligenceSerializer,
    HouseholdMember, HouseholdMemberEngine, HouseholdOwnershipEngine,
    HouseholdPetEngine, HouseholdRepository, HouseholdRole, Ownership, Pet,
    Preference, Relationship, Responsibility, Vehicle,
)


def reasoning():
    return {
        "decision": {"confidence": {"overall": .94}},
        "evidence": [
            {"source_tool": "enterprise_graph", "confidence": .92},
            {"source_tool": "cross_document_intelligence", "confidence": .93},
            {"source_tool": "enterprise_learning", "confidence": .88},
        ],
        "session": {"traces": [{"tool_name": "enterprise_graph", "status": "completed"}]},
    }


def expense():
    return {
        "expenses": [
            {"expense_id": "e1", "amount": 100, "person_id": "member:alex",
             "category": "Groceries", "evidence_ids": ["receipt:1"]},
            {"expense_id": "e2", "amount": 50, "person_id": "member:sam",
             "category": "Shopping", "evidence_ids": ["receipt:2"]},
        ],
        "summary": {
            "monthly": [{"month": "2026-07", "total": 150}],
            "merchants": [{"merchant_id": "merchant:market", "merchant_name": "Market"}],
            "categories": [{"category": "Groceries"}],
        },
        "confidence": {"overall": .91},
    }


def facts():
    household = Household("household:1", "River Household",
                          ("member:alex", "member:sam"), ("asset:laptop",), ("pet:milo",),
                          ("document:household",))
    members = (
        HouseholdMember("member:alex", "Alex", HouseholdRole.ADULT, "household:1",
                        ("document:alex",), ("history:alex",), .95),
        HouseholdMember("member:sam", "Sam", HouseholdRole.CHILD, "household:1",
                        ("document:sam",), (), .9),
    )
    return household, {
        "members": members,
        "relationships": (
            Relationship("relationship:parent", "member:alex", "member:sam", "Parent",
                         ("document:family",), .95),
        ),
        "ownership": (
            Ownership("ownership:laptop", "asset:laptop", ("member:alex",),
                      "Owned By", evidence_ids=("receipt:3",), confidence=.95),
        ),
        "responsibilities": (
            Responsibility("responsibility:shopping", ("member:alex",),
                           "Shopping Responsibility", evidence_ids=("document:family",),
                           confidence=.9),
        ),
        "consumption": (
            ConsumptionRecord("consumption:milk", ("member:alex", "member:sam"),
                              "product:milk", "Shared Consumption", 2, "units",
                              "2026-07-01", ("receipt:1",), .9),
        ),
        "preferences": (
            Preference("preference:store", ("member:alex",), "Favorite Stores",
                       "Market", ("receipt:1",), .85),
        ),
        "goals": (
            Goal("goal:savings", ("member:alex",), "Savings Goal", "Emergency fund",
                 "$5000", evidence_ids=("goal:document",)),
        ),
        "assets": (
            HouseholdAsset("asset:laptop", "household:1", "Electronics", "Laptop",
                           ("member:alex",), warranty_id="warranty:laptop",
                           evidence_ids=("receipt:3",), confidence=.95),
        ),
        "vehicles": (
            Vehicle("vehicle:1", "household:1", "Family Car", ("member:alex",),
                    evidence_ids=("document:vehicle",)),
        ),
        "pets": (
            Pet("pet:milo", "household:1", "Milo", "Dog", "Mixed",
                ("member:alex",), ("product:dog-food",), (), ("product:leash",),
                "Community Vet", "insurance:pet", ("e-pet",), ("document:pet",)),
        ),
    }


def test_household_engine_builds_profile_insights_and_explanations():
    household, values = facts()
    result = HouseholdIntelligenceEngine().analyze(reasoning(), expense(), household, **values)
    assert result.profile.household == household
    assert result.profile.monthly_spending == 150
    assert result.profile.shopping_habits
    assert {x.insight_type for x in result.insights} >= {
        "spends_most", "buys_groceries", "owns_most_assets", "favorite_merchant",
    }
    assert result.explanations
    assert result.explanations[0].reasoning_steps
    assert result.confidence.overall > .8
    assert all(x.requires_human_decision for x in result.recommendations)


def test_members_relationships_ownership_and_responsibilities():
    household, values = facts()
    new_member = HouseholdMember("member:guest", "Guest", HouseholdRole.GUEST, "household:1")
    updated, members_value = HouseholdMemberEngine().add(household, values["members"], new_member)
    assert "member:guest" in updated.member_ids
    assert len(members_value) == 3
    assert HouseholdOwnershipEngine().for_member(values["ownership"], "member:alex")
    assert HouseholdIntelligenceEngine().relationships.validate(
        values["relationships"], household.member_ids,
    ) == ()


def test_consumption_assets_pets_preferences_and_goals_are_queryable():
    _, values = facts()
    assert HouseholdConsumptionEngine().by_consumer(values["consumption"])
    assert HouseholdPetEngine().for_owner(values["pets"], "member:alex")[0].name == "Milo"
    assert values["preferences"][0].evidence_ids
    assert values["goals"][0].predictive is False
    assert values["assets"][0].warranty_id


def test_models_are_immutable_and_repository_is_capability_owned():
    household, _ = facts()
    with pytest.raises(FrozenInstanceError):
        household.name = "Changed"
    repository = HouseholdRepository()
    assert repository.save(household) == household
    assert repository.load(household.household_id) == household
    with pytest.raises(ValueError, match="already_exists"):
        repository.save(household)


def payload():
    household, values = facts()
    serializer = HouseholdIntelligenceSerializer()
    household_data = {"household": serializer.to_dict(household)}
    household_data.update({
        key: [serializer.to_dict(item) for item in collection]
        for key, collection in values.items()
    })
    return {
        "enterprise_reasoning": reasoning(),
        "expense_intelligence": expense(),
        "household_data": household_data,
    }


def test_loader_and_serializer_preserve_household_contracts():
    loaded = HouseholdIntelligenceLoader().load(payload()["household_data"])
    assert loaded["household"].household_id == "household:1"
    assert loaded["members"][0].role == HouseholdRole.ADULT
    result = HouseholdIntelligenceEngine().analyze(
        reasoning(), expense(), loaded.pop("household"), **loaded,
    )
    assert HouseholdIntelligenceSerializer().to_dict(result)["diagnostics"]["valid"]


def test_rest_api_views_and_dashboard():
    assert dashboard(payload())["schema_version"] == "household-intelligence-result-v1"
    assert summary(payload())["household"]["name"] == "River Household"
    assert members(payload())["members"]
    assert relationships(payload())["relationships"]
    assert ownership(payload())["ownership"]
    assert responsibilities(payload())["responsibilities"]
    assert assets(payload())["assets"]
    assert pets(payload())["pets"]
    assert goals(payload())["goals"]
    assert preferences(payload())["preferences"]
    assert recommendations(payload())["recommendations"]
    assert insights(payload())["insights"]


def test_routes_are_registered_for_web_and_future_mobile_clients():
    from main import app
    paths = {route.path for route in app.routes}
    assert "/api/household-intelligence/dashboard" in paths
    assert "/household-intelligence/members" in paths
    assert "/api/household-intelligence/relationships" in paths


def test_platform_and_expense_isolation_diagnostics():
    household, values = facts()
    result = HouseholdIntelligenceEngine().analyze(reasoning(), expense(), household, **values)
    diagnostics = result.diagnostics
    assert diagnostics.authentication_logic_used is False
    assert diagnostics.identity_management_used is False
    assert diagnostics.platform_services_modified is False
    assert diagnostics.expense_intelligence_modified is False
    assert diagnostics.parser_modified is False
    assert diagnostics.extraction_modified is False
    assert diagnostics.enterprise_knowledge_modified is False
    assert diagnostics.graph_modified is False
    assert diagnostics.learning_modified is False
    assert diagnostics.reasoning_modified is False
    assert diagnostics.prediction_performed is False
