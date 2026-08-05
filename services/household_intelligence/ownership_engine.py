class HouseholdOwnershipEngine:
    TYPES = {
        "Purchased By", "Owned By", "Shared Ownership", "Gifted To",
        "Inherited", "Assigned", "Temporary Use", "Lost", "Disposed",
    }

    def for_member(self, ownership, member_id):
        return tuple(x for x in ownership if member_id in x.owner_member_ids)

    def for_subject(self, ownership, subject_id):
        return tuple(x for x in ownership if x.subject_id == subject_id)
