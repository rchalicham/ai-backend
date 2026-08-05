from __future__ import annotations

from fastapi import APIRouter, HTTPException

from services.household_intelligence import (
    HouseholdIntelligenceEngine,
    HouseholdIntelligenceLoader,
    HouseholdIntelligenceSerializer,
)


router = APIRouter(prefix="/household-intelligence", tags=["household-intelligence"])
engine = HouseholdIntelligenceEngine()
loader = HouseholdIntelligenceLoader()
serializer = HouseholdIntelligenceSerializer()


def analyze_payload(payload):
    reasoning = payload.get("enterprise_reasoning")
    expense = payload.get("expense_intelligence")
    household_data = payload.get("household_data")
    if not isinstance(reasoning, dict) or not isinstance(expense, dict):
        raise HTTPException(
            400, "enterprise_reasoning and expense_intelligence are required.",
        )
    if not isinstance(household_data, dict) or not household_data.get("household"):
        raise HTTPException(400, "household_data.household is required.")
    facts = loader.load(household_data)
    household = facts.pop("household")
    return engine.analyze(reasoning, expense, household, **facts)


def attach_household_intelligence(result):
    value = dict(result)
    reasoning = value.get("enterpriseReasoning")
    expense = value.get("expenseIntelligence")
    if isinstance(reasoning, dict) and isinstance(expense, dict):
        household_result = engine.safe_analyze(reasoning, expense)
        value["householdIntelligence"] = serializer.to_dict(household_result)
    return value


@router.post("/dashboard")
def dashboard(payload: dict):
    return serializer.to_dict(analyze_payload(payload))


@router.post("/summary")
def summary(payload: dict):
    return serializer.to_dict(analyze_payload(payload).profile)


@router.post("/members")
def members(payload: dict):
    return {"members": [serializer.to_dict(x) for x in analyze_payload(payload).profile.members]}


@router.post("/relationships")
def relationships(payload: dict):
    return {"relationships": [
        serializer.to_dict(x) for x in analyze_payload(payload).profile.relationships
    ]}


@router.post("/ownership")
def ownership(payload: dict):
    return {"ownership": [serializer.to_dict(x) for x in analyze_payload(payload).profile.ownership]}


@router.post("/responsibilities")
def responsibilities(payload: dict):
    return {"responsibilities": [
        serializer.to_dict(x) for x in analyze_payload(payload).profile.responsibilities
    ]}


@router.post("/assets")
def assets(payload: dict):
    return {"assets": [serializer.to_dict(x) for x in analyze_payload(payload).profile.assets]}


@router.post("/vehicles")
def vehicles(payload: dict):
    return {"vehicles": [serializer.to_dict(x) for x in analyze_payload(payload).profile.vehicles]}


@router.post("/pets")
def pets(payload: dict):
    return {"pets": [serializer.to_dict(x) for x in analyze_payload(payload).profile.pets]}


@router.post("/goals")
def goals(payload: dict):
    return {"goals": [serializer.to_dict(x) for x in analyze_payload(payload).profile.goals]}


@router.post("/preferences")
def preferences(payload: dict):
    return {"preferences": [
        serializer.to_dict(x) for x in analyze_payload(payload).profile.preferences
    ]}


@router.post("/recommendations")
def recommendations(payload: dict):
    return {"recommendations": [
        serializer.to_dict(x) for x in analyze_payload(payload).recommendations
    ]}


@router.post("/insights")
def insights(payload: dict):
    return {"insights": [serializer.to_dict(x) for x in analyze_payload(payload).insights]}
