import json

with open("bets.json", "r") as f:
    bets = json.load(f)

pending = {}
total = 0

for user_key, user_bets in bets.items():
    if user_key == "__tails__":
        continue
    user_pending = [b for b in user_bets if b.get("status") == "Pending"]
    if user_pending:
        pending[user_key] = user_pending
        total += len(user_pending)

with open("pending.json", "w") as f:
    json.dump(pending, f, indent=4)

print(f"Done! Extracted {total} pending bets across {len(pending)} users into pending.json")
