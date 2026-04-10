import discord
from discord.ext import commands
import json
import re
import os
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- CONFIGURATION ---
TARGET_CHANNEL_ID = 1481636340914196520  # Update this for each channel run
BOT_APP_ID = 1485938016437407824
SERVER_ID = "1432450864974532892"
FILENAME = "older_bets.json"
# ---------------------

REACTION_MAP = {
    "✅": "Win",
    "❌": "Loss",
    "⏹️": "Void",
    "💩": "Delete"
}

def calculate_profit(status, units, odds):
    if status == "Win":
        return round(units * (odds - 1), 2)
    elif status == "Loss":
        return round(-units, 2)
    return 0.0

def is_old_format(embed):
    """
    Old slips have the bet title in embed.author.name and use inline fields
    whose names contain EVENT, WAGER, and ODDS (possibly with emoji prefixes
    like '🏆 EVENT', '💰 WAGER', '📈 ODDS').
    """
    if not embed.author or not embed.author.name:
        return False
    if not embed.fields:
        return False
    field_names_upper = [f.name.upper() for f in embed.fields]
    has_event = any("EVENT" in n for n in field_names_upper)
    has_wager = any("WAGER" in n for n in field_names_upper)
    has_odds  = any("ODDS"  in n for n in field_names_upper)
    # Must have all three field columns AND no description (new format uses description)
    return has_event and has_wager and has_odds and not embed.description

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}.")
    print(f"Scanning Channel: {TARGET_CHANNEL_ID} in Server: {SERVER_ID}...")

    channel = bot.get_channel(TARGET_CHANNEL_ID)
    if not channel:
        print("Error: Could not find channel. Check permissions/ID!")
        await bot.close()
        return

    # Build a name -> member map so we can resolve display names to user IDs
    guild = channel.guild
    name_to_member = {}
    async for member in guild.fetch_members(limit=None):
        name_to_member[member.display_name.lower()] = member
        name_to_member[member.name.lower()] = member

    # Load existing data to allow appending
    if os.path.exists(FILENAME):
        with open(FILENAME, "r") as f:
            try:
                master_data = json.load(f)
            except json.JSONDecodeError:
                master_data = {}
    else:
        master_data = {}

    new_count = 0
    skipped_count = 0

    async for message in channel.history(limit=None, oldest_first=True):
        if message.author.id != BOT_APP_ID:
            continue
        if not message.embeds:
            continue

        embed = message.embeds[0]

        if not is_old_format(embed):
            continue

        try:
            title = (embed.author.name or "").replace("**", "").strip()

            # Extract username and sport from title like "booshh's Baseball Bet"
            title_match = re.match(r"^(.+?)'s (.+?) Bet$", title, re.IGNORECASE)
            if not title_match:
                print(f"Skipping {message.id}: title '{title}' did not match expected pattern.")
                skipped_count += 1
                continue

            user_name = title_match.group(1).strip()
            sport = title_match.group(2).strip()

            # Resolve username to a Discord user ID
            member = (
                name_to_member.get(user_name.lower())
            )
            if member:
                user_id = member.id
            else:
                # Fall back: store under a synthetic key using the display name
                # so the data isn't lost, but flag it clearly
                print(f"Warning: Could not resolve '{user_name}' to a member. "
                      f"Storing under name-based key.")
                user_id = f"unresolved_{user_name.lower()}"

            user_key = f"{SERVER_ID}_{user_id}"

            # Parse fields — field names may have emoji/extra whitespace
            fields = {f.name.upper().strip(): f.value.strip() for f in embed.fields}

            event_val = fields.get("EVENT") or fields.get("🏆 EVENT") or ""
            wager_val = fields.get("WAGER") or fields.get("💰 WAGER") or ""
            odds_val  = fields.get("ODDS")  or fields.get("📈 ODDS")  or ""

            # Strip emoji prefixes that may appear in field names
            # (e.g. "🏆 EVENT" → already handled above via partial matching)
            # Also try stripped emoji patterns
            if not event_val:
                for k, v in fields.items():
                    if "EVENT" in k:
                        event_val = v
                        break
            if not wager_val:
                for k, v in fields.items():
                    if "WAGER" in k:
                        wager_val = v
                        break
            if not odds_val:
                for k, v in fields.items():
                    if "ODDS" in k:
                        odds_val = v
                        break

            if not event_val:
                print(f"Skipping {message.id}: could not find EVENT field.")
                skipped_count += 1
                continue

            pick = event_val.strip()

            # WAGER: "1.0u" → 1.0
            units_match = re.search(r"(\d+\.?\d*)", wager_val)
            if not units_match:
                print(f"Skipping {message.id}: could not parse wager '{wager_val}'.")
                skipped_count += 1
                continue
            units = float(units_match.group(1))

            # ODDS: "2.25 (+125)" → decimal 2.25
            odds_match = re.search(r"(\d+\.?\d*)", odds_val)
            if not odds_match:
                print(f"Skipping {message.id}: could not parse odds '{odds_val}'.")
                skipped_count += 1
                continue
            odds = float(odds_match.group(1))

            # Footer: "ID: 88cbbca5 • 3/25/2026 5:43 AM"
            footer = embed.footer.text if embed.footer else ""
            bet_id = "Unknown"
            if footer:
                id_match = re.search(r"ID:\s*([a-f0-9\-]+)", footer, re.IGNORECASE)
                if id_match:
                    bet_id = id_match.group(1).strip()[:8]

            # Reactions → settlement status
            status = "Pending"
            for reaction in message.reactions:
                emoji_str = str(reaction.emoji)
                if emoji_str in REACTION_MAP and reaction.count > 0:
                    status = REACTION_MAP[emoji_str]
                    break

            if status == "Delete":
                continue

            timestamp = message.created_at.replace(tzinfo=None).isoformat()

            bet_data = {
                "bet_id": bet_id,
                "sport": sport,
                "pick": pick,
                "units": units,
                "odds": odds,
                "original_odds": odds,
                "status": status,
                "profit": calculate_profit(status, units, odds),
                "user_name": user_name,
                "timestamp": timestamp
            }

            if user_key not in master_data:
                master_data[user_key] = []

            if not any(b["bet_id"] == bet_id for b in master_data[user_key]):
                master_data[user_key].append(bet_data)
                new_count += 1

        except Exception as e:
            print(f"Skipping message {message.id} | Reason: {e}")
            skipped_count += 1

    with open(FILENAME, "w") as f:
        json.dump(master_data, f, indent=4)

    print(f"\nDone! Added {new_count} older bets. Skipped {skipped_count}.")
    print(f"Total users in '{FILENAME}': {len(master_data)}")
    await bot.close()

bot.run(os.getenv("DISCORD_TOKEN"))
