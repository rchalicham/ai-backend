class HouseholdResponsibilityEngine:
    TYPES = {
        "Budget Owner", "Warranty Owner", "Property Owner", "Vehicle Owner",
        "Bill Owner", "Pet Caregiver", "Medication Manager",
        "Shopping Responsibility", "Maintenance Responsibility",
        "Shared Responsibility",
    }

    def assignments(self, responsibilities, member_id):
        return tuple(x for x in responsibilities if member_id in x.member_ids)

    def unassigned(self, responsibilities):
        return tuple(x for x in responsibilities if not x.member_ids)
