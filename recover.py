import discord
from discord.ext import commands
import json
import re
import os
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Updated to your new test-scraper channel
TARGET_CHANNEL_ID = 1489624493834899536
BOT_APP_ID = 1486064350258004088

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
    print(f'Logged in. Re-scanning channel: {TARGET_CHANNEL_ID}...')
    channel = bot.get_channel(TARGET_CHANNEL_ID)
    
    if not channel:
        print("Error: Could not find channel. Check permissions!")
        await bot.close()
        return

    scraped_bets = []

    async for message in channel.history(limit=None, oldest_first=True):
        # Only look at the bot's own messages with embeds
        if message.author.id == BOT_APP_ID and message.embeds:
            embed = message.embeds[0]
            
            # Defensive check: skip if embed is missing title or description
            if not embed.author or not embed.author.name or not embed.description:
                continue
            
            try:
                # --- 1. CLEANING STRINGS ---
                title = embed.author.name.replace("**", "")
                user_match = re.search(r"^(.*?)'s (.*?) Bet", title)
                user_name = user_match.group(1).strip() if user_match else "Unknown"
                sport = user_match.group(2).strip() if user_match else "Unknown"

                desc = embed.description.replace("**", "")
                parts = [p.strip() for p in desc.split('•')]
                
                # Ensure we have Pick, Units, and Odds parts
                if len(parts) < 3:
                    continue

                pick = parts[0]
                units = float(re.findall(r"\d+\.?\d*", parts[1])[0])
                odds = float(re.findall(r"\d+\.?\d*", parts[2])[0])

                # ID extraction from footer
                footer = embed.footer.text if embed.footer else ""
                bet_id = footer.split('•')[0].replace("ID:", "").strip() if footer else "Unknown"

                # --- 2. REACTION CHECK ---
                status = "Pending"
                for reaction in message.reactions:
                    emoji_str = str(reaction.emoji)
                    if emoji_str in REACTION_MAP:
                        if reaction.count > 0:
                            status = REACTION_MAP[emoji_str]
                            break

                if status == "Delete":
                    continue

                # --- 3. TIMESTAMP ---
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
                scraped_bets.append(bet_data)
                print(f"Recovered: {bet_id} ({pick}) - {status}")

            except Exception as e:
                print(f"Skipping message {message.id} | Reason: {e}")

    # Final Save
    with open('scraped_bets.json', 'w') as f:
        json.dump(scraped_bets, f, indent=4)
    
    print(f"\nSuccess! Recovered {len(scraped_bets)} bets to scraped_bets.json")
    await bot.close()

bot.run(os.getenv('DISCORD_TOKEN'))