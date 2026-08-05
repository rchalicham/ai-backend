class HouseholdRelationshipEngine:
    TYPES = {
        "Parent", "Child", "Spouse", "Partner", "Sibling", "Guardian",
        "Dependent", "Roommate", "Pet Owner", "Caregiver", "Unknown",
    }

    def validate(self, relationships, member_ids):
        known = set(member_ids)
        errors = []
        for item in relationships:
            if item.source_member_id not in known or item.target_member_id not in known:
                errors.append(f"{item.relationship_id}:unknown_member")
            if item.source_member_id == item.target_member_id:
                errors.append(f"{item.relationship_id}:self_relationship")
        return tuple(errors)

    def graph(self, relationships):
        return tuple({
            "id": x.relationship_id, "source": x.source_member_id,
            "target": x.target_member_id, "type": x.relationship_type,
            "confidence": x.confidence, "evidence_ids": x.evidence_ids,
        } for x in relationships)
