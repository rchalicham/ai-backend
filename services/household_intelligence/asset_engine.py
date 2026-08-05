from collections import Counter


class HouseholdAssetEngine:
    TYPES = {
        "Property", "Vehicle", "Electronics", "Appliances", "Furniture",
        "Jewelry", "Equipment", "Subscriptions", "Warranty Items",
    }

    def by_owner(self, assets, member_id):
        return tuple(x for x in assets if member_id in x.owner_member_ids)

    def counts(self, assets):
        return tuple(sorted(Counter(x.asset_type for x in assets).items()))
