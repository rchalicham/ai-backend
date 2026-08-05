from collections import defaultdict


class HouseholdConsumptionEngine:
    TYPES = {
        "Consumed By", "Shared Consumption", "Household Consumption",
        "Pet Consumption", "Inventory Consumption", "Medical Consumption",
        "Food Consumption", "Travel Consumption",
    }

    def by_consumer(self, records):
        values = defaultdict(list)
        for record in records:
            for consumer in record.consumer_ids:
                values[consumer].append(record)
        return tuple((key, tuple(items)) for key, items in sorted(values.items()))

    def trends(self, records):
        values = defaultdict(float)
        for item in records:
            values[(item.occurred_at[:7], item.consumption_type)] += item.quantity
        return tuple((month, kind, round(value, 3))
                     for (month, kind), value in sorted(values.items()))
