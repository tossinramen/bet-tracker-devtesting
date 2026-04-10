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
TARGET_CHANNEL_ID = 1486023440728330340 # Update per channel
BOT_APP_ID        = 1485938016437407824
SERVER_ID         = "1432450864974532892"
FILENAME          = "oldcos.json"
# ---------------------

def is_cashout_embed(embed):
    if not embed.title:
        return False
    return "BET CASHED OUT" in embed.title.upper()

def parse_profit(text: str) -> float:
    """Pull the numeric value out of strings like '-0.26u' or '+1.5u'."""
    text = text.replace("**", "").strip()
    match = re.search(r"([+-]?\d+\.?\d*)", text)
    return float(match.group(1)) if match else 0.0

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}.")
    print(f"Scanning Channel: {TARGET_CHANNEL_ID} in Server: {SERVER_ID}...")

    channel = bot.get_channel(TARGET_CHANNEL_ID)
    if not channel:
        print("Error: Could not find channel. Check permissions/ID!")
        await bot.close()
        return

    # Load existing data for appending
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

        if not is_cashout_embed(embed):
            continue

        try:
            # --- User ID ---
            user_id = None
            if message.interaction_metadata:
                user_id = message.interaction_metadata.user.id

            if not user_id:
                skipped_count += 1
                print(f"Skipping {message.id}: no interaction metadata.")
                continue

            user_key = f"{SERVER_ID}_{user_id}"

            # --- Parse fields ---
            fields = {f.name.strip(): f.value.strip() for f in embed.fields}

            pick   = fields.get("Event", "Unknown").replace("`", "").strip()
            method = fields.get("Method", "Unknown").replace("`", "").strip()
            pnl_raw = fields.get("Resulting P/L", "0u")
            profit = parse_profit(pnl_raw)

            # --- Bet ID from footer ---
            footer = embed.footer.text if embed.footer else ""
            bet_id = "Unknown"
            if footer:
                id_match = re.search(r"ID:\s*([a-f0-9\-]+)", footer, re.IGNORECASE)
                if id_match:
                    bet_id = id_match.group(1).strip()[:8]

            # --- Timestamp ---
            timestamp = message.created_at.replace(tzinfo=None).isoformat()

            co_data = {
                "bet_id":    bet_id,
                "pick":      pick,
                "method":    method,
                "profit":    profit,
                "status":    "Cashed Out",
                "timestamp": timestamp
            }

            if user_key not in master_data:
                master_data[user_key] = []

            if not any(b["bet_id"] == bet_id for b in master_data[user_key]):
                master_data[user_key].append(co_data)
                new_count += 1
            else:
                skipped_count += 1

        except Exception as e:
            print(f"Skipping message {message.id} | Reason: {e}")
            skipped_count += 1

    with open(FILENAME, "w") as f:
        json.dump(master_data, f, indent=4)

    print(f"\nDone! Saved {new_count} cashout records. Skipped {skipped_count}.")
    print(f"Total users in '{FILENAME}': {len(master_data)}")
    await bot.close()

bot.run(os.getenv("DISCORD_TOKEN"))
