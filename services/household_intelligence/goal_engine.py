class HouseholdGoalEngine:
    TYPES = {
        "Savings Goal", "Health Goal", "Fitness Goal", "Budget Goal",
        "Travel Goal", "Education Goal", "Household Goal",
    }

    def active(self, goals):
        return tuple(x for x in goals if x.status not in {"completed", "cancelled"})

    def by_owner(self, goals, owner_id):
        return tuple(x for x in goals if owner_id in x.owner_ids)
