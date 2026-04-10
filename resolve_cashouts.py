import json

with open("pending.json", "r") as f:
    pending = json.load(f)

with open("oldcos.json", "r") as f:
    oldcos = json.load(f)

# Build a flat lookup: bet_id -> cashout record
co_lookup = {}
for user_bets in oldcos.values():
    for co in user_bets:
        co_lookup[co["bet_id"]] = co

resolved_count = 0
still_pending  = 0

resolved_pending = {}

for user_key, user_bets in pending.items():
    for bet in user_bets:
        co = co_lookup.get(bet["bet_id"])
        if co:
            updated = dict(bet)
            updated["status"] = "Cashed Out"
            updated["profit"] = co["profit"]
            if user_key not in resolved_pending:
                resolved_pending[user_key] = []
            resolved_pending[user_key].append(updated)
            resolved_count += 1
        else:
            still_pending += 1

with open("resolved_pending.json", "w") as f:
    json.dump(resolved_pending, f, indent=4)

print(f"Done!")
print(f"  Resolved as Cashed Out : {resolved_count}")
print(f"  Still Pending (skipped): {still_pending}")
print(f"Output saved to resolved_pending.json")
