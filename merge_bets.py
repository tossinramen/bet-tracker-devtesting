import json

MAIN_FILE   = "bets.json"
OLDER_FILE  = "older_bets.json"

with open(MAIN_FILE, "r") as f:
    main_data = json.load(f)

with open(OLDER_FILE, "r") as f:
    older_data = json.load(f)

added = 0
skipped = 0

for user_key, bets in older_data.items():
    if user_key not in main_data:
        main_data[user_key] = []

    existing_ids = {b["bet_id"] for b in main_data[user_key]}

    for bet in bets:
        if bet["bet_id"] in existing_ids:
            skipped += 1
        else:
            main_data[user_key].append(bet)
            existing_ids.add(bet["bet_id"])
            added += 1

with open(MAIN_FILE, "w") as f:
    json.dump(main_data, f, indent=4)

print(f"Done! Added {added} bets, skipped {skipped} duplicates.")
print(f"Total users in {MAIN_FILE}: {len(main_data)}")
