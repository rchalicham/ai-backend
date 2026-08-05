from dataclasses import replace


class HouseholdMemberEngine:
    def add(self, household, members, member):
        if member.household_id != household.household_id:
            raise ValueError("member_household_mismatch")
        if any(x.member_id == member.member_id for x in members):
            raise ValueError("household_member_already_exists")
        return replace(household, member_ids=(*household.member_ids, member.member_id)), (*members, member)

    def by_role(self, members, role):
        value = str(getattr(role, "value", role))
        return tuple(x for x in members if str(getattr(x.role, "value", x.role)) == value)
