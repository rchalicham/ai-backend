from collections import Counter


class HouseholdPreferenceEngine:
    TYPES = {
        "Favorite Brands", "Favorite Stores", "Food Preferences",
        "Dietary Preferences", "Shopping Preferences", "Travel Preferences",
        "Entertainment Preferences", "Product Preferences", "Lifestyle Preferences",
    }

    def summarize(self, preferences):
        counts = Counter((x.preference_type, x.value) for x in preferences)
        return tuple((kind, value, count) for (kind, value), count in sorted(counts.items()))

    def for_member(self, preferences, member_id):
        return tuple(x for x in preferences if member_id in x.subject_member_ids)
