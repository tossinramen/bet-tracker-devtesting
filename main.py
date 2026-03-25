import datetime

import discord
from discord import app_commands, ui
from discord.app_commands import Choice, Range 
from discord.ext import commands
import os
import json
import uuid 
from dotenv import load_dotenv

load_dotenv()
token = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True 
DATA_FILE = "bets.json"

SPORTS_LIST = [
    "LCS", "LEC", "LPL", "LCK", "APAC", "CBLOL", "League Int",
    "Basketball",
    "CS2", "Val", "Dota", "Tennis", "MMA", 
    "Cricket", "Baseball", "Soccer", "Hockey"
]

# --- DATA HELPERS ---
def convert_to_decimal(odds_input: float) -> float:
    # If odds are between -100 and 100, assume they are already Decimal
    if -100 < odds_input < 100:
        return round(odds_input, 2)
    # American Positive (e.g., +220)
    if odds_input >= 100:  
        return round((odds_input / 100) + 1, 2)
    # American Negative (e.g., -110)
    if odds_input <= -100:  
        return round((100 / abs(odds_input)) + 1, 2)
    return round(odds_input, 2) 

def format_odds(odds_input: float) -> str:
    # 1. Handle Decimal Odds (anything between -100 and 100)
    if -100 < odds_input < 100:
        if odds_input <= 1.0:
            return f"{odds_input}" # Avoid division by zero
        
        # Calculate American equivalent for the label
        if odds_input >= 2.0:
            ame = int((odds_input - 1) * 100)
            return f"{odds_input} (+{ame})"
        else:
            ame = int(-100 / (odds_input - 1))
            return f"{odds_input} ({ame})"

    # 2. Handle American Odds (anything >= 100 or <= -100)
    decimal = convert_to_decimal(odds_input)
    sign = "+" if odds_input > 0 else ""
    return f"{decimal} ({sign}{int(odds_input)})"


def get_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# --- UI COMPONENTS ---
class LeaderboardPaginator(ui.View):
    def __init__(self, stats, guild_name):
        super().__init__(timeout=60)
        self.stats = stats
        self.guild_name = guild_name
        self.current_page = 0
        self.per_page = 10 
        self.message = None 

    def create_embed(self):
        start = self.current_page * self.per_page
        end = start + self.per_page
        page_stats = self.stats[start:end]
        
        embed = discord.Embed(
            title=f"🏆 {self.guild_name} Betting Leaderboard",
            color=discord.Color.red(),
            description="Ranked by total units won/lost."
        )
        
        leaderboard_text = ""
        for i, user in enumerate(page_stats, start + 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"**#{i}**"
            pnl_display = f"+{user['pnl']}u" if user['pnl'] > 0 else f"{user['pnl']}u"
            
           
            stats_line = f"`{user['record']}` | `{user['winrate']}%` | `{user['roi']}% ROI`"
            leaderboard_text += f"{medal} **{user['name']}**: **{pnl_display}**\n╰ {stats_line}\n"
        
        embed.add_field(name="Rankings", value=leaderboard_text or "No data for this page.", inline=False)
        total_pages = (len(self.stats) - 1) // self.per_page + 1
        embed.set_footer(text=f"Page {self.current_page + 1} of {total_pages}")
        return embed

    @ui.button(label="⬅️ Previous", style=discord.ButtonStyle.gray)
    async def previous(self, interaction: discord.Interaction, button: ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @ui.button(label="Next ➡️", style=discord.ButtonStyle.gray)
    async def next(self, interaction: discord.Interaction, button: ui.Button):
        if (self.current_page + 1) * self.per_page < len(self.stats):
            self.current_page += 1
            await interaction.response.edit_message(embed=self.create_embed(), view=self)

class HistoryPaginator(ui.View):
    def __init__(self, bets, user_name):
        super().__init__(timeout=60)
        self.bets = bets
        self.user_name = user_name
        self.current_page = 0
        self.per_page = 5 

    def create_embed(self):
        start = self.current_page * self.per_page
        end = start + self.per_page
        page_bets = self.bets[start:end]
        
        embed = discord.Embed(title=f"📋 Bet History: {self.user_name}", color=discord.Color.red())
        
        for i, b in enumerate(page_bets, start + 1):
            
            status = b['status']
            if status == "Win": emoji = "✅"
            elif status == "Loss": emoji = "❌"
            elif status == "Cashed Out": emoji = "💰"
            elif status == "Void": emoji = "⏹️"
            else: emoji = "⏳" # Pending
            
            profit_val = float(b.get('profit', 0.0))
            
            if status == "Pending":
                result_str = "---"
            else:
                result_str = f"{'+' if profit_val > 0 else ''}{profit_val}u"

            embed.add_field(
                name=f"Bet #{i} - {emoji} {status}", 
                value=(
                    f"**Pick:** `{b.get('pick', 'Unknown')}`\n"
                    f"**Wager:** `{b['units']}u`\n"
                    f"**Odds:** `{b.get('original_odds', b['odds'])}`\n"
                    f"**Result:** `{result_str}`\n"
                    f"**ID:** `{b['bet_id']}`"
                ), 
                inline=False
            )
        
        total_pages = (len(self.bets) - 1) // self.per_page + 1
        embed.set_footer(text=f"Page {self.current_page + 1} of {total_pages}")
        return embed

    @ui.button(label="⬅️ Previous", style=discord.ButtonStyle.gray)
    async def previous(self, interaction: discord.Interaction, button: ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @ui.button(label="Next ➡️", style=discord.ButtonStyle.gray)
    async def next(self, interaction: discord.Interaction, button: ui.Button):
        if (self.current_page + 1) * self.per_page < len(self.bets):
            self.current_page += 1
            await interaction.response.edit_message(embed=self.create_embed(), view=self)

# --- BOT SETUP ---
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="/", intents=intents)
    async def setup_hook(self):
        await self.tree.sync()
        print(f"Synced slash commands for {self.user}")

bot = MyBot()

@bot.tree.command(name="bet", description="Track a new bet")
@app_commands.describe(sport="The sport/league this bet belongs to")
@app_commands.choices(sport=[Choice(name=s, value=s) for s in SPORTS_LIST])
async def bet(interaction: discord.Interaction, sport: Choice[str], pick: str, units: Range[float, 0, 10], odds: float):
    await interaction.response.defer()
    user_id, guild_id = str(interaction.user.id), str(interaction.guild.id)
    user_key = f"{guild_id}_{user_id}"
    bet_id = str(uuid.uuid4())[:8]
    decimal_odds = convert_to_decimal(odds)
    display_odds = format_odds(odds)

    data = get_data()
    if user_key not in data: data[user_key] = []
    
    data[user_key].append({
        "bet_id": bet_id, "sport": sport.value, "pick": pick, "units": units, 
        "odds": decimal_odds, "original_odds": odds, "status": "Pending", 
        "profit": 0.0, "user_name": interaction.user.display_name, "timestamp": datetime.datetime.now().isoformat()
    })
    save_data(data)

    file = discord.File("gdenimg.jpg", filename="gdenimg.jpg")
    embed = discord.Embed(color=discord.Color.red(), timestamp=interaction.created_at)
    embed.set_author(name=f"{interaction.user.display_name}'s {sport.value} Bet", icon_url=interaction.user.display_avatar.url)
    embed.set_thumbnail(url="attachment://gdenimg.jpg")

    embed.add_field(name="🏆 EVENT", value=f"`{pick}`", inline=True)
    embed.add_field(name="💰 WAGER", value=f"`{units}u`", inline=True)
    embed.add_field(name="📈 ODDS", value=f"`{display_odds}`", inline=True)
    embed.set_footer(text=f"ID: {bet_id}")

    await interaction.followup.send(file=file, embed=embed)

@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id: return
    
    emoji = str(payload.emoji)
    if emoji not in ["✅", "❌", "⏹️", "💩"]: return

    channel = bot.get_channel(payload.channel_id) or await bot.fetch_channel(payload.channel_id)
    message = await channel.fetch_message(payload.message_id)

    if message.embeds and message.embeds[0].footer.text:
        footer_text = message.embeds[0].footer.text
        if "ID: " in footer_text:
            bet_id = footer_text.split("ID: ")[1].strip()
            
            data = get_data()
            target_user_key = None
            found_bet = None

           
            guild_prefix = f"{payload.guild_id}_"
            for key in data:
                if key.startswith(guild_prefix):
                    for b in data[key]:
                        if b["bet_id"] == bet_id:
                            target_user_key = key
                            found_bet = b
                            break
            
            if not found_bet: return

          
            is_owner = str(payload.user_id) in target_user_key
            
            
            is_admin = payload.member.guild_permissions.administrator
            
           
            staff_role_names = ['mod', 'moderator', 'staff', 'admin']
            has_mod_role = any(role.name.lower() in staff_role_names for role in payload.member.roles)

       
            if not (is_owner or is_admin or has_mod_role):
                return 

           
            if emoji == "💩":
                data[target_user_key] = [b for b in data[target_user_key] if b["bet_id"] != bet_id]
                if not data[target_user_key]: del data[target_user_key]
                save_data(data)
                await message.delete()
                return

            if emoji == "✅":
                found_bet["status"], found_bet["profit"] = "Win", round((float(found_bet["units"]) * float(found_bet["odds"])) - float(found_bet["units"]), 2)
            elif emoji == "❌":
                found_bet["status"], found_bet["profit"] = "Loss", -float(found_bet["units"])
            elif emoji == "⏹️":
                found_bet["status"], found_bet["profit"] = "Void", 0.0
            
            save_data(data)
            await channel.send(f"📊 Bet `{bet_id}` settled as **{found_bet['status']}** by {payload.member.display_name}!", delete_after=5)

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.user_id == bot.user.id: return
    channel = bot.get_channel(payload.channel_id) or await bot.fetch_channel(payload.channel_id)
    message = await channel.fetch_message(payload.message_id)

    if message.embeds and message.embeds[0].footer.text:
        footer_text = message.embeds[0].footer.text
        if "ID: " in footer_text:
            bet_id = footer_text.split("ID: ")[1].strip()
            user_key = f"{payload.guild_id}_{payload.user_id}"
            data = get_data()

            if user_key in data:
                for b in data[user_key]:
                    if b["bet_id"] == bet_id:
                        b["status"] = "Pending"
                        b["profit"] = 0.0
                        save_data(data)
                        await channel.send(f"🔄 Bet `{bet_id}` set back to **Pending**.", delete_after=5)
                        break

@bot.tree.command(name="pnl", description="Show your total Profit/Loss")
async def pnl(interaction: discord.Interaction):
    data = get_data()
    user_key = f"{interaction.guild.id}_{interaction.user.id}"
    user_bets = data.get(user_key, [])
    
    total_pnl = round(sum(float(b["profit"]) for b in user_bets), 2)
    wins = len([b for b in user_bets if b.get("status") == "Win"])
    losses = len([b for b in user_bets if b.get("status") == "Loss"])
    cov = len([b for b in user_bets if b.get("status") in ["Cashed Out", "Void"]])
    
    embed = discord.Embed(title=f"💰 PnL Report: {interaction.user.display_name}", color=discord.Color.red())
    embed.add_field(name="Total Profit/Loss", value=f"**{total_pnl} units**", inline=False)
    embed.add_field(name="Record", value=f"`{wins}W - {losses}L - {cov}CO/V`", inline=True)
    await interaction.response.send_message(embed=embed)

class LeaderboardView(ui.View):
    def __init__(self, all_data, guild_id, guild_name):
        super().__init__(timeout=60)
        self.all_data = all_data
        self.guild_id = guild_id
        self.guild_name = guild_name
        self.current_page = 0
        self.per_page = 10
        self.timeframe = "All-Time"

    def get_filtered_stats(self):
        server_stats = []
        now = datetime.datetime.now()

        for key, user_bets in self.all_data.items():
            if not key.startswith(f"{self.guild_id}_"): continue
            
            # Filter bets by timeframe
            filtered_bets = []
            for b in user_bets:
                if self.timeframe == "All-Time":
                    filtered_bets.append(b)
                else:
                    # Parse timestamp (handle old bets without timestamps as 'All-Time' only)
                    if "timestamp" not in b: continue
                    ts = datetime.datetime.fromisoformat(b["timestamp"])
                    days_diff = (now - ts).days
                    if self.timeframe == "Weekly" and days_diff <= 7:
                        filtered_bets.append(b)
                    elif self.timeframe == "Monthly" and days_diff <= 30:
                        filtered_bets.append(b)

            if not filtered_bets: continue

            # Calculate stats for the filtered period
            total_pnl = round(sum(float(b["profit"]) for b in filtered_bets), 2)
            wins = len([b for b in filtered_bets if b.get("status") == "Win"])
            losses = len([b for b in filtered_bets if b.get("status") == "Loss"])
            total_staked = sum(float(b["units"]) for b in filtered_bets if b.get("status") in ["Win", "Loss", "Cashed Out"])
            
            total_settled = wins + losses
            winrate = round((wins / total_settled) * 100, 1) if total_settled > 0 else 0
            roi = round((total_pnl / total_staked) * 100, 1) if total_staked > 0 else 0
            
            user_name = filtered_bets[0].get("user_name", "Unknown User")
            server_stats.append({
                "name": user_name, "pnl": total_pnl, "record": f"{wins}W-{losses}L",
                "winrate": winrate, "roi": roi
            })

        server_stats.sort(key=lambda x: x["pnl"], reverse=True)
        return server_stats

    def create_embed(self):
        stats = self.get_filtered_stats()
        start = self.current_page * self.per_page
        end = start + self.per_page
        page_stats = stats[start:end]
        
        embed = discord.Embed(
            title=f"🏆 {self.guild_name} Leaderboard ({self.timeframe})",
            color=discord.Color.red(),
            description=f"Showing rankings for **{self.timeframe.lower()}**."
        )
        
        leaderboard_text = ""
        for i, user in enumerate(page_stats, start + 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"**#{i}**"
            pnl_display = f"+{user['pnl']}u" if user['pnl'] > 0 else f"{user['pnl']}u"
            stats_line = f"`{user['record']}` | `{user['winrate']}%` | `{user['roi']}% ROI`"
            leaderboard_text += f"{medal} **{user['name']}**: **{pnl_display}**\n╰ {stats_line}\n"
        
        embed.add_field(name="Rankings", value=leaderboard_text or "No data for this period.", inline=False)
        total_pages = (len(stats) - 1) // self.per_page + 1
        embed.set_footer(text=f"Page {self.current_page + 1} of {max(1, total_pages)}")
        return embed

    @ui.select(placeholder="Choose Timeframe", options=[
        discord.SelectOption(label="All-Time", emoji="🌎"),
        discord.SelectOption(label="Weekly", description="Last 7 days", emoji="📅"),
        discord.SelectOption(label="Monthly", description="Last 30 days", emoji="🌙")
    ])
    async def select_timeframe(self, interaction: discord.Interaction, select: ui.Select):
        self.timeframe = select.values[0]
        self.current_page = 0
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @ui.button(label="⬅️", style=discord.ButtonStyle.gray)
    async def previous(self, interaction: discord.Interaction, button: ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @ui.button(label="➡️", style=discord.ButtonStyle.gray)
    async def next(self, interaction: discord.Interaction, button: ui.Button):
        stats = self.get_filtered_stats()
        if (self.current_page + 1) * self.per_page < len(stats):
            self.current_page += 1
            await interaction.response.edit_message(embed=self.create_embed(), view=self)

@bot.tree.command(name="history", description="Show a user's bet history. Sorts by most recent.")
@app_commands.describe(user="The user to view", sport="Filter by sport", status="Filter by result")
@app_commands.choices(
    sport=[Choice(name=s, value=s) for s in SPORTS_LIST],
    status=[
        Choice(name="Win", value="Win"),
        Choice(name="Loss", value="Loss"),
        Choice(name="Void", value="Void"),
        Choice(name="Cashed Out", value="Cashed Out"),
        Choice(name="Pending", value="Pending")
    ]
)
async def history(interaction: discord.Interaction, user: discord.Member = None, sport: Choice[str] = None, status: Choice[str] = None):
    await interaction.response.defer()
    
    target_user = user or interaction.user
    data = get_data()
    user_key = f"{interaction.guild.id}_{target_user.id}"
    user_bets = data.get(user_key, [])

    if not user_bets:
        return await interaction.followup.send(f"No bets recorded for {target_user.display_name}.", ephemeral=True)

    
    
    display_bets = sorted(user_bets, key=lambda x: x.get('timestamp', ''), reverse=True)

    
    filter_parts = []
    if sport:
        display_bets = [b for b in display_bets if b.get('sport') == sport.value]
        filter_parts.append(sport.value)
    if status:
        display_bets = [b for b in display_bets if b.get('status') == status.value]
        filter_parts.append(status.value)

    filter_text = f" ({', '.join(filter_parts)})" if filter_parts else ""

    if not display_bets:
        return await interaction.followup.send(f"No bets matching those filters found for {target_user.display_name}.", ephemeral=True)

    view = HistoryPaginator(display_bets, f"{target_user.display_name}{filter_text}")
    msg = await interaction.followup.send(embed=view.create_embed(), view=view)
    view.message = msg

@bot.tree.command(name="removebet", description="Delete a bet. Staff can delete anyone's bet.")
async def removebet(interaction: discord.Interaction, bet_id: str, user: discord.Member = None):
   
    target_user = user or interaction.user
    
    is_admin = interaction.user.guild_permissions.administrator
    staff_roles = ['mod', 'moderator', 'staff', 'admin']
    is_staff = any(role.name.lower() in staff_roles for role in interaction.user.roles)

    if target_user != interaction.user and not (is_admin or is_staff):
        return await interaction.response.send_message("❌ You don't have permission to remove someone else's bet.", ephemeral=True)

    user_key = f"{interaction.guild.id}_{target_user.id}"
    data = get_data()
    
    if user_key not in data:
        return await interaction.response.send_message("No history found for this user.", ephemeral=True)
    
    original_list = data[user_key]
    new_list = [b for b in original_list if b['bet_id'] != bet_id]
    
    if len(original_list) == len(new_list):
        return await interaction.response.send_message(f"Could not find bet ID `{bet_id}` for this user.", ephemeral=True)
  
    data[user_key] = new_list
    if not data[user_key]: del data[user_key]
    save_data(data)
    
    await interaction.response.send_message(f"✅ Bet `{bet_id}` has been removed.", ephemeral=True)

@bot.tree.command(name="editbet", description="Edit a bet's details. Staff can edit anyone's bet.")
@app_commands.describe(sport="The corrected sport/league for this bet", user="Optional: Tag a user if you are staff editing their bet")
@app_commands.choices(sport=[Choice(name=s, value=s) for s in SPORTS_LIST])
async def editbet(interaction: discord.Interaction, bet_id: str, sport: Choice[str], new_pick: str, new_units: Range[float, 0, 10], new_odds: float, user: discord.Member = None):
    
    target_user = user or interaction.user
    
   
    is_admin = interaction.user.guild_permissions.administrator
    staff_roles = ['mod', 'moderator', 'staff', 'admin']
    is_staff = any(role.name.lower() in staff_roles for role in interaction.user.roles)

    if target_user != interaction.user and not (is_admin or is_staff):
        return await interaction.response.send_message("❌ You don't have permission to edit someone else's bet.", ephemeral=True)

    user_key = f"{interaction.guild.id}_{target_user.id}"
    data = get_data()
    
   
    user_bets = data.get(user_key, [])
    bet_to_update = next((b for b in user_bets if b['bet_id'] == bet_id), None)
            
    if not bet_to_update:
        return await interaction.response.send_message(f"Bet ID `{bet_id}` not found for {target_user.display_name}.", ephemeral=True)

    
    bet_to_update["sport"] = sport.value 
    bet_to_update["pick"] = new_pick
    bet_to_update["units"] = new_units
    bet_to_update["original_odds"] = new_odds
    bet_to_update["odds"] = convert_to_decimal(new_odds)
    
   
    bet_to_update["status"] = "Pending"
    bet_to_update["profit"] = 0.0
    
    save_data(data)
    
   
    display_odds = format_odds(new_odds)
    file = discord.File("gdenimg.jpg", filename="gdenimg.jpg")
    
    embed = discord.Embed(
        color=discord.Color.blue(), 
        timestamp=interaction.created_at
    )
    
   
    embed.set_author(name=f"{target_user.display_name}'s Updated {sport.value} Bet", icon_url=target_user.display_avatar.url)
    embed.set_thumbnail(url="attachment://gdenimg.jpg")

    embed.add_field(name="🏆 EVENT", value=f"`{new_pick}`", inline=True)
    embed.add_field(name="💰 WAGER", value=f"`{new_units}u`", inline=True)
    embed.add_field(name="📈 ODDS", value=f"`{display_odds}`", inline=True)
    
    embed.set_footer(text=f"ID: {bet_id} • Updated by {interaction.user.display_name}")

    await interaction.response.send_message(content=f"✅ Bet `{bet_id}` updated!", file=file, embed=embed)

async def editbet(interaction: discord.Interaction, bet_id: str, new_pick: str, new_units: Range[float, 0, 10], new_odds: float):
    user_key = f"{interaction.guild.id}_{interaction.user.id}"
    data = get_data()
    
    if user_key not in data:
        return await interaction.response.send_message("You have no bet history.", ephemeral=True)
    
    bet_to_update = None
    for b in data[user_key]:
        if b['bet_id'] == bet_id:
            bet_to_update = b
            break
            
    if not bet_to_update:
        return await interaction.response.send_message(f"Could not find a bet with ID: `{bet_id}`", ephemeral=True)

    bet_to_update["pick"] = new_pick
    bet_to_update["units"] = new_units
    bet_to_update["original_odds"] = new_odds
    bet_to_update["odds"] = convert_to_decimal(new_odds)
    bet_to_update["status"] = "Pending"
    bet_to_update["profit"] = 0.0
    save_data(data)
    
    try:
        async for message in interaction.channel.history(limit=100):
            if message.author == bot.user and message.embeds:
                footer = message.embeds[0].footer.text
                if footer and bet_id in footer:
                    await message.delete()
                    break 
    except Exception:
        pass


    display_odds = format_odds(new_odds)
    file = discord.File("gdenimg.jpg", filename="gdenimg.jpg")
    embed = discord.Embed(title="🎫 UPDATED BET SLIP", color=discord.Color.red(), timestamp=interaction.created_at)
    embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
    embed.set_thumbnail(url="attachment://gdenimg.jpg")
    embed.add_field(name="🏆 EVENT", value=f"`{new_pick}`", inline=False)
    embed.add_field(name="💰 WAGER", value=f"`{new_units} units`", inline=True)
    embed.add_field(name="📈 ODDS", value=f"`{display_odds}`", inline=True)
    embed.set_footer(text=f"ID: {bet_id}")

    await interaction.response.send_message(content=f"✅ Bet `{bet_id}` updated!", file=file, embed=embed)

@bot.tree.command(name="cashout", description="Settle a bet early via payout amount or specific odds")
async def cashout(interaction: discord.Interaction, bet_id: str, payout_amount: float = None, cashout_odds: float = None):
    user_key = f"{interaction.guild.id}_{interaction.user.id}"
    data = get_data()
    
    if user_key not in data:
        return await interaction.response.send_message("No history found.", ephemeral=True)
    
    bet_to_pull = next((b for b in data[user_key] if b['bet_id'] == bet_id), None)
    if not bet_to_pull:
        return await interaction.response.send_message(f"Bet ID `{bet_id}` not found.", ephemeral=True)

    original_stake = float(bet_to_pull["units"])
    
    if payout_amount is not None:
        actual_profit = round(payout_amount - original_stake, 2)
        display_val = f"{payout_amount}u Payout"
    elif cashout_odds is not None:
        actual_profit = round((original_stake * cashout_odds) - original_stake, 2)
        display_val = f"{cashout_odds} Odds"
    else:
        return await interaction.response.send_message("Please provide either `payout_amount` or `cashout_odds`.", ephemeral=True)

   
    bet_to_pull["status"] = "Cashed Out"
    bet_to_pull["profit"] = actual_profit 
    save_data(data)

    color = discord.Color.blue() if actual_profit >= 0 else discord.Color.orange()
    embed = discord.Embed(title="💰 BET CASHED OUT", color=color)
    embed.add_field(name="Event", value=f"`{bet_to_pull['pick']}`", inline=False)
    embed.add_field(name="Method", value=f"`{display_val}`", inline=True)
    embed.add_field(name="Resulting P/L", value=f"**{'+' if actual_profit > 0 else ''}{actual_profit}u**", inline=True)
    embed.set_footer(text=f"ID: {bet_id}")
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="leaderboard", description="Show top bettors by timeframe")
async def leaderboard(interaction: discord.Interaction):
    data = get_data()
    view = LeaderboardView(data, interaction.guild.id, interaction.guild.name)
    
   
    if not view.get_filtered_stats():
        return await interaction.response.send_message("No bets recorded for this server yet.", ephemeral=True)

    await interaction.response.send_message(embed=view.create_embed(), view=view)


@bot.tree.command(name="profile", description="View a bettor's full profile and sport stats")
async def profile(interaction: discord.Interaction, user: discord.Member = None):
    target_user = user or interaction.user
    data = get_data()
    user_key = f"{interaction.guild.id}_{target_user.id}"
    user_bets = data.get(user_key, [])

    if not user_bets:
        return await interaction.response.send_message(f"No data found for {target_user.display_name}.", ephemeral=True)

    settled_bets = [b for b in user_bets if b['status'] in ["Win", "Loss"]]
    wins = len([b for b in settled_bets if b['status'] == "Win"])
    losses = len([b for b in settled_bets if b['status'] == "Loss"])
    total_pnl = round(sum(float(b['profit']) for b in user_bets), 2)
    
    total_staked = sum(float(b['units']) for b in user_bets if b['status'] in ["Win", "Loss", "Cashed Out"])
    wr = round((wins / len(settled_bets) * 100), 1) if settled_bets else 0
    roi = round((total_pnl / total_staked * 100), 1) if total_staked > 0 else 0
    avg_odds = round(sum(float(b['odds']) for b in user_bets) / len(user_bets), 2) if user_bets else 0

    embed = discord.Embed(title=f"👤 {target_user.display_name.upper()}'S BETTING PROFILE", color=discord.Color.red())
    embed.set_thumbnail(url=target_user.display_avatar.url)

    embed.add_field(name="📊 RECORD", value=f"`{wins}W-{losses}L`", inline=True)
    embed.add_field(name="🎯 WINRATE", value=f"`{wr}%`", inline=True)
    embed.add_field(name="💰 P/L", value=f"`{total_pnl}u`", inline=True)
    embed.add_field(name="📈 ROI", value=f"`{roi}%`", inline=True)
    embed.add_field(name="🎲 AVG ODDS", value=f"`{avg_odds}`", inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True) # Spacer


    sport_stats = ""
    for sport in SPORTS_LIST:
        s_bets = [b for b in user_bets if b.get('sport') == sport]
        if not s_bets: continue
        
        s_settled = [b for b in s_bets if b['status'] in ["Win", "Loss"]]
        s_wins = len([b for b in s_settled if b['status'] == "Win"])
        s_losses = len([b for b in s_settled if b['status'] == "Loss"])
        s_pnl = round(sum(float(b['profit']) for b in s_bets), 2)
        
        pnl_str = f"+{s_pnl}u" if s_pnl > 0 else f"{s_pnl}u"
        sport_stats += f"**{sport}**: `{s_wins}W-{s_losses}L` | `{pnl_str}`\n"

    embed.add_field(name="🏟️ SPORT BREAKDOWN", value=sport_stats or "No sports tracked yet.", inline=False)
    
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="help", description="View all available commands and how to use the bot")
async def help(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎲 Bet Tracker Pro - Help Menu", 
        description="Track your bets, climb the leaderboard, and analyze your ROI by sport.",
        color=discord.Color.red()
    )

    all_cmds = (
        "📝 **/bet [sport] [pick] [units] [odds]**\n"
        "Starts a new bet slip. Select your sport from the dropdown.\n\n"
        "👤 **/profile (@user)**\n"
        "Shows global stats (ROI, WR) and a sport-by-sport breakdown.\n\n"
        "📋 **/history (@user) [sport]**\n"
        "View a list of bets. You can filter by a specific sport.\n\n"
        "🏆 **/leaderboard**\n"
        "View rankings. Toggle between All-Time, Weekly, and Monthly.\n\n"
        "💸 **/cashout [id] [payout/odds]**\n"
        "Settle a bet early before the match officially ends.\n\n"
        "✏️ **/editbet [id] [sport] [pick] [units] [odds] (@user)**\n"
        "Fix errors on a slip. \n\n"
        "🗑️ **/removebet [id]**\n"
        "Delete a specific bet. Can also use poop emoji on the slip.\n\n"
        "💰 **/pnl**\n"
        "Quick check of your total units won/lost and overall record."
    )
    embed.add_field(name="🚀 Available Commands", value=all_cmds, inline=False)

   
    settle_guide = (
        "React to your **Bet Slip** to update the status:\n"
        "✅ = **Win** | ❌ = **Loss** | ⏹️ = **Void** | 💩 = **Delete Slip**\n"
        "*Removing your reaction sets the bet back to 'Pending'.*"
    )
    embed.add_field(name="⚖️ How to Settle", value=settle_guide, inline=False)

    embed.set_footer(text="Tip: Use the Bet ID found at the bottom of every slip for edits/removals.")

    await interaction.response.send_message(embed=embed)

bot.run(token)