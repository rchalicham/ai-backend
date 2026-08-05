class HouseholdPetEngine:
    def for_owner(self, pets, member_id):
        return tuple(x for x in pets if member_id in x.owner_member_ids)

    def needs(self, pet):
        return {
            "food_product_ids": pet.food_product_ids,
            "medication_ids": pet.medication_ids,
            "supply_product_ids": pet.supply_product_ids,
            "veterinarian": pet.veterinarian,
            "insurance_id": pet.insurance_id,
        }
