import discord
from discord.ext import commands
import json
import re
import os
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
# If your bot needs to see members to resolve IDs, this is good to have on
intents.members = True 

bot = commands.Bot(command_prefix="!", intents=intents)

# --- CONFIGURATION (Change these as needed) ---
TARGET_CHANNEL_ID = 1432451888451686551  # Update this for each channel run
BOT_APP_ID = 1485938016437407824
SERVER_ID = "1432450864974532892"        # Your 500-member Server ID
FILENAME = 'scraped_bets.json'           # The file that gathers all results
# ---------------------------------------------

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

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}.')
    print(f'Scanning Channel: {TARGET_CHANNEL_ID} in Server: {SERVER_ID}...')
    
    channel = bot.get_channel(TARGET_CHANNEL_ID)
    if not channel:
        print("Error: Could not find channel. Check permissions/ID!")
        await bot.close()
        return

    # 1. Load existing data so we can APPEND to it
    if os.path.exists(FILENAME):
        with open(FILENAME, 'r') as f:
            try:
                master_data = json.load(f)
            except json.JSONDecodeError:
                master_data = {}
    else:
        master_data = {}

    new_count = 0

    async for message in channel.history(limit=None, oldest_first=True):
        # Filter for your bot's messages that have embeds
        if message.author.id == BOT_APP_ID and message.embeds:
            embed = message.embeds[0]
            
            # Defensive check
            if not embed.author or not embed.author.name or not embed.description:
                continue
            
            try:
                # --- A. Get the User ID from Interaction Metadata ---
                user_id = None
                if message.interaction_metadata:
                    user_id = message.interaction_metadata.user.id
                
                # If no metadata, we skip it (too old or not a slash command)
                if not user_id:
                    continue

                # Create the key: ServerID_UserID
                user_key = f"{SERVER_ID}_{user_id}"

                # --- B. Clean Strings & Parse Embed ---
                title = embed.author.name.replace("**", "")
                # Extracts 'tahjoker' from "tahjoker's Basketball Bet"
                user_name = title.split("'s")[0].strip()
                
                # Extract sport name
                sport_match = re.search(r"'s (.*?) Bet", title)
                sport = sport_match.group(1).strip() if sport_match else "Unknown"

                desc = embed.description.replace("**", "")
                parts = [p.strip() for p in desc.split('•')]
                
                if len(parts) < 3:
                    continue

                pick = parts[0]
                units = float(re.findall(r"\d+\.?\d*", parts[1])[0])
                odds = float(re.findall(r"\d+\.?\d*", parts[2])[0])

                # ID extraction from footer
                footer = embed.footer.text if embed.footer else ""
                bet_id = footer.split('•')[0].replace("ID:", "").strip() if footer else "Unknown"

                # --- C. Check Reactions for Settlement ---
                status = "Pending"
                for reaction in message.reactions:
                    emoji_str = str(reaction.emoji)
                    if emoji_str in REACTION_MAP:
                        if reaction.count > 0:
                            status = REACTION_MAP[emoji_str]
                            break

                if status == "Delete":
                    continue

                # --- D. Format Timestamp (UTC to String) ---
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

                # --- E. Add to the Dictionary ---
                if user_key not in master_data:
                    master_data[user_key] = []
                
                # Prevent duplicates if running same channel twice
                if not any(b['bet_id'] == bet_id for b in master_data[user_key]):
                    master_data[user_key].append(bet_data)
                    new_count += 1

            except Exception as e:
                print(f"Skipping message {message.id} | Reason: {e}")

    # 2. Final Save
    with open(FILENAME, 'w') as f:
        json.dump(master_data, f, indent=4)
    
    print(f"\nSuccess! Added {new_count} new bets.")
    print(f"Total users tracked in file: {len(master_data)}")
    await bot.close()

bot.run(os.getenv('DISCORD_TOKEN'))