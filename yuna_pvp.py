"""
Yuna PvP Combat Engine & Duel System
Full-fledged interactive turn-based PvP battle system mirroring the RPG engine.
- y!duel @user [lvl<N>] (Level Selection up to 3000, defaults to player's current level)
- 2-minute duel request with [⚔️ Accept] and [❌ Decline]
- Real RPG Player Builds: class, skills, stats (ATK, DEF, SPD, INT), equipment, passives, buffs/debuffs
- Speed System: Higher SPD = First Turn (random tiebreaker if equal)
- Speed Difference Dodge System: Dodge chance scaled by difference in actual SPD values (capped at 35%)
- Battle Actions: Exactly [✨ Skills], [🎒 Items], [🏳️ Quit]
- Fishing-Style Skill Selection: Player's available skills are directly displayed as selectable buttons!
  Tap skill -> immediately fires & locks -> prevents double-clicks, duplicate attacks, race conditions
- Usable Inventory Items: [🎒 Items] opens real consumable inventory buttons, tap immediately consumes & executes
- Quit Confirmation: [Leave the duel? [Yes] [No]], Yes forfeits match
- Complete RPG Combat Calculations: ATK, DEF mitigation, INT, Crits, Lifesteal, Guard, Shields, True Damage
- Secondary Status Effects: Freeze (skips turn, check resistance), Stun, Poison (Poison II), Burn, Bleed, Atk Up, Def Down
- Phoenix Feather auto-revive (75% HP)
- Live Battle Log & Duel Complete summary with turns, final HP, damage dealt, and full combat log
- Safety / Interaction Handling: Prevent self-duel, bot-duel, active battle conflicts, duplicate requests, expired acceptance
- Request State Machine: PENDING -> ACCEPTED -> ACTIVE -> FINISHED, or PENDING -> DECLINED / EXPIRED
"""

import asyncio
import copy
import random
import re
import time
from typing import Optional, List, Dict, Any, Tuple
import discord
from discord.ui import View, Button, Select

try:
    import yuna_id_guard
    YUNA_ID_GUARD_AVAILABLE = True
except Exception:
    yuna_id_guard = None
    YUNA_ID_GUARD_AVAILABLE = False

ACTIVE_PVP_BATTLES: Dict[str, Any] = {}
PENDING_DUEL_REQUESTS: Dict[str, Any] = {}
DUEL_LOCK = asyncio.Lock()


# ─────────────────────────────────────────────────────────────────────────────
# 1. CONSUMABLE INVENTORY & PLAYER BUILD HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def get_pvp_consumable_inventory(stats: dict) -> dict:
    """Collects all consumable/usable combat items from player's inventory."""
    inv = stats.get("inventory", {})
    consumables = {}

    wm_count = stats.get("watermelons", 0)
    if wm_count > 0:
        consumables["watermelons"] = wm_count

    known_consumables = {
        "dungeon_elixir": {"name": "Abyssal Healing Elixir", "emoji": "✨", "desc": "Restores +60% HP & 100% MP"},
        "full_heal": {"name": "Full Heal", "emoji": "❤️", "desc": "Restores +60% HP & 100% MP"},
        "healing_potion": {"name": "Healing Potion", "emoji": "🧪", "desc": "Restores +40% Max HP & +25 MP"},
        "potion": {"name": "HP Potion", "emoji": "🧪", "desc": "Restores +40% Max HP & +25 MP"},
        "health_potion": {"name": "Health Potion", "emoji": "🧪", "desc": "Restores +40% Max HP & +25 MP"},
        "hp_potion": {"name": "HP Potion", "emoji": "🧪", "desc": "Restores +40% Max HP & +25 MP"},
        "elixir": {"name": "Archangel Elixir", "emoji": "✨", "desc": "Restores +65% Max HP & +40 MP"},
        "pocket_watermelon": {"name": "Pocket Watermelon", "emoji": "🍉", "desc": "Restores +30% Max HP & +20 MP"},
        "watermelons": {"name": "Fresh Watermelon", "emoji": "🍉", "desc": "Restores +30% Max HP & +15 MP"},
        "adrenaline_shot": {"name": "Adrenaline Battle Shot", "emoji": "💉", "desc": "+50% ATK next round & +30 MP"},
        "smoke_bomb": {"name": "Tactical Smoke Bomb", "emoji": "💨", "desc": "100% Dodge next incoming hit"},
        "stagger_grenade": {"name": "Disruptor Stagger Grenade", "emoji": "💣", "desc": "Staggers target (+50% dmg taken)"},
        "phoenix_feather": {"name": "Phoenix Feather", "emoji": "🪶", "desc": "Celestial blessing / auto-revives with 75% HP"},
        "strength_potion": {"name": "Strength Potion", "emoji": "💪", "desc": "Boosts physical damage output (+50% ATK)"},
        "iron_skin_potion": {"name": "Iron Skin Potion", "emoji": "🛡️", "desc": "Increases damage resistance (Guard Raised)"},
        "heat_resistance_potion": {"name": "Heat Resistance Potion", "emoji": "🔥", "desc": "Volcanic heat shield"},
        "energy_potion": {"name": "Energy Potion", "emoji": "⚡", "desc": "Restores +50 MP"},
        "antidote": {"name": "Antidote", "emoji": "🧪", "desc": "Cleanses all poison, burn, and bleed debuffs"}
    }

    try:
        from yuna_equipment import ALL_EQUIPMENT
    except Exception:
        ALL_EQUIPMENT = {}

    for k, v in inv.items():
        if not isinstance(v, (int, float)) or v <= 0:
            continue
        if k in ALL_EQUIPMENT:
            continue
        if k in known_consumables or any(term in k.lower() for term in ("potion", "elixir", "grenade", "bomb", "shot", "feather", "melon", "berry", "food", "ration", "antidote")):
            consumables[k] = int(v)

    return consumables


BASE_PVP_SKILLS = {
    "power_strike": {
        "id": "power_strike",
        "name": "Power Strike",
        "emoji": "⚔️",
        "mp_cost": 20,
        "stance": "strike",
        "dmg_mult": 2.0,
        "desc": "Focuses all might into a heavy, crushing physical strike."
    },
    "shield_bash": {
        "id": "shield_bash",
        "name": "Shield Bash",
        "emoji": "🛡️",
        "mp_cost": 15,
        "stance": "defend",
        "dmg_mult": 1.4,
        "dmg_reduction": 0.25,
        "desc": "Strikes target and raises defensive guard against incoming damage."
    },
    "mana_surge": {
        "id": "mana_surge",
        "name": "Mana Surge",
        "emoji": "✨",
        "mp_cost": 10,
        "stance": "tactical",
        "dmg_mult": 1.2,
        "party_mp_restore": 30,
        "desc": "Strikes while channeling inward mana (+30 MP)."
    },
    "mending_light": {
        "id": "mending_light",
        "name": "Mending Light",
        "emoji": "🌿",
        "mp_cost": 25,
        "stance": "defend",
        "dmg_mult": 0.8,
        "heal_pct": 0.35,
        "desc": "Channels soothing light to strike and heal 35% Max HP."
    }
}


def get_pvp_player_skills(stats: dict) -> list:
    """Retrieves player's equipped and unlocked class skills with standard fallback."""
    import yuna_rpg
    skills = []
    seen = set()
    try:
        yuna_rpg.sync_player_unlocked_skills(stats)
        w_sk, m_sk = yuna_rpg.get_player_equipped_skills(stats)
        for sk in (w_sk + m_sk):
            if sk.get("id") and sk["id"] not in seen:
                seen.add(sk["id"])
                skills.append(sk)

        unlocked = stats.get("unlocked_skills", [])
        for sid in unlocked:
            if sid in yuna_rpg.CLASS_SKILLS and sid not in seen:
                seen.add(sid)
                skills.append(yuna_rpg.CLASS_SKILLS[sid])

        # If still empty or fewer than 3, add class skills matching player's class
        p_class = stats.get("class", "physicist")
        for sid, sk_meta in yuna_rpg.CLASS_SKILLS.items():
            if sk_meta.get("class_id") == p_class and sid not in seen:
                seen.add(sid)
                skills.append(sk_meta)
                if len(skills) >= 6:
                    break

        if skills:
            return skills
    except Exception:
        pass

    return list(BASE_PVP_SKILLS.values())


def build_pvp_hp_bar(current: int, maximum: int, length: int = 10) -> str:
    """Renders a clean unicode health bar."""
    pct = max(0.0, min(1.0, current / max(1, maximum)))
    filled = int(round(pct * length))
    empty = length - filled
    return f"`[{'█' * filled}{'░' * empty}]` {current:,}/{maximum:,}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. DUEL SAFETY & STATE MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

def is_in_duel(user_id: str) -> bool:
    """Returns True if user is currently fighting in an active duel."""
    uid = str(user_id)
    battle = ACTIVE_PVP_BATTLES.get(uid)
    return bool(battle and not battle.ended)


def get_pending_outgoing_duel(author_id: str) -> Optional[dict]:
    """Returns any unexpired pending outgoing challenge sent by author_id."""
    now = time.time()
    for req_id, req in list(PENDING_DUEL_REQUESTS.items()):
        if str(req.get("author_id")) == str(author_id):
            if req.get("status") == "PENDING":
                if now <= req.get("expires_at", 0):
                    return req
                else:
                    req["status"] = "EXPIRED"
    return None


def get_pending_duel_for_target(target_id: str, author_id: Optional[str] = None) -> Optional[dict]:
    """Returns any unexpired pending duel request waiting for target_id."""
    now = time.time()
    for req_id, req in list(PENDING_DUEL_REQUESTS.items()):
        if str(req.get("target_id")) == str(target_id):
            if author_id is None or str(req.get("author_id")) == str(author_id):
                if req.get("status") == "PENDING":
                    if now <= req.get("expires_at", 0):
                        return req
                    else:
                        req["status"] = "EXPIRED"
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 3. DUEL REQUEST VIEW (2-MINUTE ACCEPT / DECLINE)
# ─────────────────────────────────────────────────────────────────────────────

class DuelRequestView(View):
    """
    Duel request interactive view with [⚔️ Accept] and [❌ Decline].
    Expires in 120 seconds (2 minutes).
    """
    def __init__(self, req_id: str, req_data: dict):
        super().__init__(timeout=120.0)
        self.req_id = req_id
        self.req_data = req_data

        self.accept_btn = Button(
            label="Accept",
            style=discord.ButtonStyle.success,
            emoji="⚔️",
            custom_id=f"duel_accept_{req_id}"
        )
        self.accept_btn.callback = self.on_accept
        self.add_item(self.accept_btn)

        self.decline_btn = Button(
            label="Decline",
            style=discord.ButtonStyle.danger,
            emoji="❌",
            custom_id=f"duel_decline_{req_id}"
        )
        self.decline_btn.callback = self.on_decline
        self.add_item(self.decline_btn)

    async def on_accept(self, interaction: discord.Interaction):
        target_id = self.req_data["target_id"]
        if str(interaction.user.id) != str(target_id):
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ Only the challenged player can accept this duel!", ephemeral=True)
            except Exception:
                pass
            return

        async with DUEL_LOCK:
            if self.req_data.get("status") != "PENDING" or time.time() > self.req_data.get("expires_at", 0):
                try:
                    if not interaction.response.is_done():
                        await interaction.response.send_message("❌ This duel request has expired or has already been resolved!", ephemeral=True)
                except Exception:
                    pass
                return

            p1_id = self.req_data["author_id"]
            p2_id = self.req_data["target_id"]
            if is_in_duel(p1_id) or is_in_duel(p2_id):
                try:
                    if not interaction.response.is_done():
                        await interaction.response.send_message("❌ One of the players is already engaged in another duel!", ephemeral=True)
                except Exception:
                    pass
                return

            self.req_data["status"] = "ACCEPTED"

        for child in self.children:
            child.disabled = True

        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
        except Exception:
            pass

        await start_duel_from_request(self.req_data, interaction=interaction, view=self)

    async def on_decline(self, interaction: discord.Interaction):
        uid = str(interaction.user.id)
        target_id = str(self.req_data["target_id"])
        author_id = str(self.req_data["author_id"])
        if uid not in (target_id, author_id):
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ You cannot decline this duel challenge!", ephemeral=True)
            except Exception:
                pass
            return

        async with DUEL_LOCK:
            if self.req_data.get("status") != "PENDING":
                return
            self.req_data["status"] = "DECLINED"

        for child in self.children:
            child.disabled = True

        decline_embed = discord.Embed(
            title="❌ DUEL DECLINED",
            description=f"<@{target_id}> declined the duel challenge from <@{author_id}>.",
            color=0x7F8C8D
        )
        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(content=None, embed=decline_embed, view=self)
            elif self.req_data.get("message"):
                await self.req_data["message"].edit(content=None, embed=decline_embed, view=self)
        except Exception:
            pass

    async def on_timeout(self):
        async with DUEL_LOCK:
            if self.req_data.get("status") != "PENDING":
                return
            self.req_data["status"] = "EXPIRED"

        for child in self.children:
            child.disabled = True

        author_name = self.req_data.get("author_name", "Challenger")
        target_name = self.req_data.get("target_name", "Opponent")
        expired_embed = discord.Embed(
            title="⏳ DUEL REQUEST EXPIRED",
            description=f"The duel request from **{author_name}** to **{target_name}** has expired after 2 minutes.",
            color=0x95A5A6
        )
        msg = self.req_data.get("message")
        if msg:
            try:
                await msg.edit(content=None, embed=expired_embed, view=self)
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# 4. DUEL ENTRY POINT: y!duel @user [lvl<N>]
# ─────────────────────────────────────────────────────────────────────────────

async def handle_duel(message, client, args: list):
    """
    Handles y!duel @user [lvl<N>]
    - Optional level selection up to level 3000
    - If no level specified, uses player's current level
    - Sends 2-minute duel request with [⚔️ Accept] and [❌ Decline]
    """
    author = message.author
    author_id = str(author.id)

    # 1. Target resolution
    target = None
    if message.mentions:
        client_uid = getattr(getattr(client, "user", None), "id", None)
        for m in message.mentions:
            if client_uid is None or m.id != client_uid:
                target = m
                if m.id != author.id:
                    break

    # Look for UID or username in args if not found in mentions
    for a in args:
        if not target:
            uid_m = re.search(r'\d{17,20}', a)
            if uid_m:
                uid_int = int(uid_m.group())
                if message.guild:
                    target = message.guild.get_member(uid_int)
                if not target and client:
                    try:
                        target = client.get_user(uid_int)
                    except Exception:
                        pass
                if not target:
                    class FallbackTarget:
                        def __init__(self, uid):
                            self.id = uid
                            self.mention = f"<@{uid}>"
                            self.display_name = "Player"
                            self.name = "Player"
                            self.bot = False
                    target = FallbackTarget(uid_int)
            elif message.guild:
                clean_name = a.lstrip("@").lower()
                target = discord.utils.find(
                    lambda m: (m.name.lower() == clean_name or m.display_name.lower() == clean_name) and (not YUNA_ID_GUARD_AVAILABLE or not yuna_id_guard or yuna_id_guard.is_valid_guild_target(m, clean_name)),
                    message.guild.members
                )

    if not target:
        await message.reply(
            "⚔️ **YUNA RPG DUEL SYSTEM** ⚔️\n"
            "Challenge another player to a PvP duel using your real RPG build!\n\n"
            "• **Standard Duel:** `y!duel @user`\n"
            "• **Level-Scaled Duel:** `y!duel @user lvl2000` *(Max: Level 3000)*\n"
            "*(Uses real class, equipped skills, equipment, passives, and stats!)*"
        )
        return

    # Safety checks
    if target.id == author.id:
        await message.reply("❌ *Yuna sighs* \"You can't duel yourself! Find an opponent to test your strength.\"")
        return

    if getattr(target, "bot", False):
        await message.reply("❌ *Yuna rolls her eyes* \"Bots do not engage in mortal duels!\"")
        return

    if is_in_duel(author_id):
        await message.reply("❌ You are currently fighting in an active duel! Finish your match first.")
        return

    if is_in_duel(str(target.id)):
        await message.reply(f"❌ **{getattr(target, 'display_name', 'Opponent')}** is currently fighting in another duel!")
        return

    active_outgoing = get_pending_outgoing_duel(author_id)
    if active_outgoing:
        await message.reply("❌ You already have a pending duel request! Wait for it to be accepted, declined, or expire.")
        return

    # 2. Level selection parsing (Max: Level 3000)
    duel_level = None
    full_text = " ".join(args)
    lvl_match = re.search(r'(?:lvl|level)\s*(\d+)', full_text, re.IGNORECASE)
    if lvl_match:
        parsed_lvl = int(lvl_match.group(1))
        duel_level = max(1, min(3000, parsed_lvl))

    author_name = getattr(author, "display_name", author.name)
    target_name = getattr(target, "display_name", getattr(target, "name", "Opponent"))

    req_id = f"{author_id}_{target.id}_{int(time.time())}"
    req_data = {
        "id": req_id,
        "author_id": author_id,
        "author_name": author_name,
        "author_mention": author.mention,
        "target_id": str(target.id),
        "target_name": target_name,
        "target_mention": getattr(target, "mention", f"<@{target.id}>"),
        "author_user": author,
        "target_user": target,
        "duel_level": duel_level,
        "status": "PENDING",
        "created_at": time.time(),
        "expires_at": time.time() + 120.0,
        "channel": message.channel,
        "client": client,
        "message": None
    }
    PENDING_DUEL_REQUESTS[req_id] = req_data

    view = DuelRequestView(req_id, req_data)

    level_str = f"🎚️ **Duel Level:** Level {duel_level:,}\n" if duel_level else "🎚️ **Duel Level:** Current Player Level\n"
    embed = discord.Embed(
        title="⚔️ DUEL REQUEST",
        description=(
            f"**{author_name}** has challenged you to a duel!\n\n"
            f"{level_str}"
            f"🧬 **Real Player Build Active:**\n"
            f"• Current/Selected Class & Advancement\n"
            f"• Selected Skills from `y!skills`\n"
            f"• Total Stats (ATK, DEF, SPD, INT)\n"
            f"• Equipment & Accessories\n"
            f"• Passives & Secondary Effects\n\n"
            f"<@{target.id}>, will you accept the challenge?"
        ),
        color=0xE74C3C
    )
    embed.set_footer(text="Request expires in 2 minutes (2:00) • [⚔️ Accept] or [❌ Decline]")

    sent_msg = await message.reply(content=getattr(target, "mention", f"<@{target.id}>"), embed=embed, view=view)
    req_data["message"] = sent_msg


async def accept_duel_request(req_id: str, message=None, client=None):
    """Programmatic or text command accept entry point."""
    req = PENDING_DUEL_REQUESTS.get(req_id)
    if not req or req.get("status") != "PENDING" or time.time() > req.get("expires_at", 0):
        if message:
            await message.reply("❌ This duel request has expired or has already been resolved!")
        return

    async with DUEL_LOCK:
        req["status"] = "ACCEPTED"

    await start_duel_from_request(req, client=client)


async def decline_duel_request(req_id: str, user_id: str, message=None):
    """Programmatic or text command decline entry point."""
    req = PENDING_DUEL_REQUESTS.get(req_id)
    if not req or req.get("status") != "PENDING":
        return

    async with DUEL_LOCK:
        req["status"] = "DECLINED"

    target_id = req["target_id"]
    author_id = req["author_id"]
    if message:
        await message.reply(f"❌ **Duel Declined!** <@{target_id}> declined the duel with <@{author_id}>.")


# ─────────────────────────────────────────────────────────────────────────────
# 5. INTERACTIVE BATTLE VIEWS (SIMULTANEOUS LOCK-IN & EPHEMERAL MENUS)
# ─────────────────────────────────────────────────────────────────────────────

class PvPQuitConfirmView(View):
    """Ephemeral confirmation view when a player requests to quit/forfeit."""
    def __init__(self, controller, user_id: str):
        super().__init__(timeout=60)
        self.controller = controller
        self.user_id = str(user_id)

        confirm_btn = Button(
            label="Yes, Forfeit Match",
            style=discord.ButtonStyle.danger,
            emoji="🏳️",
            custom_id=f"pvp_ephemeral_confirm_quit_{user_id}"
        )
        confirm_btn.callback = self.on_confirm
        self.add_item(confirm_btn)

        cancel_btn = Button(
            label="No, Keep Fighting",
            style=discord.ButtonStyle.secondary,
            emoji="🛡️",
            custom_id=f"pvp_ephemeral_cancel_quit_{user_id}"
        )
        cancel_btn.callback = self.on_cancel
        self.add_item(cancel_btn)

    async def on_confirm(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ This is not your forfeit confirmation!", ephemeral=True)
            except Exception:
                pass
            return
        for child in self.children:
            child.disabled = True
        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(content="🏳️ **You have forfeited the match!**", view=self)
        except Exception:
            pass
        await self.controller.lock_in_action(self.user_id, {"type": "flee"}, interaction=interaction)

    async def on_cancel(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ This is not your forfeit confirmation!", ephemeral=True)
            except Exception:
                pass
            return
        for child in self.children:
            child.disabled = True
        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(content="🛡️ **Forfeit cancelled. Fight on!**", view=self)
        except Exception:
            pass


class PvPSkillSelectView(View):
    """Ephemeral skill selection menu showing ONLY the invoking player's skills and MP."""
    def __init__(self, controller, user_id: str):
        super().__init__(timeout=60)
        self.controller = controller
        self.user_id = str(user_id)

        player_skills = self.controller.get_player_skills(self.user_id)
        cur_mp = self.controller.p1_mp if self.user_id == self.controller.p1_id else self.controller.p2_mp
        max_mp = self.controller.p1_max_mp if self.user_id == self.controller.p1_id else self.controller.p2_max_mp

        VALID_EMOJIS = {"⚔️", "🛡️", "✨", "🌿", "🔥", "⚡", "❄️", "💥", "🗡️", "🥊", "🎯", "🩸", "🥋", "💀", "🏹", "🌑", "🌪️", "🌊", "🩹", "🌸", "💖", "🎺", "🔗", "🌟", "☀️", "🪽", "🪷", "❓", "🕳️", "🌘", "⭕", "∞", "🌀", "🕶️", "🌌", "📐", "⏱️", "🔬", "🔋", "☢️", "🧪", "🧲", "💉", "📢", "🐾", "🥩", "🦁", "👟", "🪓", "🌋", "🔮", "☄️", "🧘", "💫", "🌈", "⏳", "💢", "🧱", "🤝", "🔨", "💎", "🏰", "🥏", "🦏", "🏛️", "⛰️", "💧", "💞"}

        options = []
        for sk in player_skills[:25]:
            mp_c = sk.get("mp_cost", 20)
            stance = sk.get("stance", "tactical").upper()
            desc = sk.get("desc", "")[:80]
            emoji_str = sk.get("emoji", "⚔️")
            sel_emoji = emoji_str if emoji_str in VALID_EMOJIS else None
            mp_warn = " ⚠️ Low MP" if cur_mp < mp_c else ""
            options.append(discord.SelectOption(
                label=f"{sk['name']} [{stance}] ({mp_c} MP){mp_warn}"[:100],
                value=sk["id"],
                emoji=sel_emoji,
                description=desc
            ))

        if options:
            skill_select = Select(
                placeholder=f"✦ Select Class Skill ({cur_mp}/{max_mp} MP)...",
                options=options,
                row=0,
                custom_id=f"pvp_ephemeral_select_skill_{user_id}"
            )
            skill_select.callback = self.on_select
            self.add_item(skill_select)
        else:
            btn_empty = Button(label="No Skills Available", disabled=True, style=discord.ButtonStyle.secondary)
            self.add_item(btn_empty)

    async def on_select(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ This is not your skill selection menu!", ephemeral=True)
            except Exception:
                pass
            return

        vals = interaction.data.get("values", []) if hasattr(interaction, "data") and isinstance(interaction.data, dict) else []
        chosen_id = vals[0] if vals else "power_strike"
        sk_meta = self.controller.get_skill_meta(chosen_id)
        sk_name = sk_meta.get("name", chosen_id.replace("_", " ").title())

        for child in self.children:
            child.disabled = True
        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(
                    content=f"🔒 Locked in **{sk_name}** for **Round {self.controller.round_num}**! Waiting for opponent...",
                    view=self
                )
        except Exception:
            pass

        await self.controller.lock_in_action(self.user_id, {"type": "skill", "skill_id": chosen_id}, interaction=interaction)


class PvPItemSelectView(View):
    """Ephemeral inventory menu allowing player to choose and lock in a consumable item."""
    def __init__(self, controller, user_id: str):
        super().__init__(timeout=60)
        self.controller = controller
        self.user_id = str(user_id)

        consumables = self.controller.get_player_consumables(self.user_id)
        item_list = list(consumables.items())

        options = []
        for item_id, qty in item_list[:25]:
            clean_name = item_id.replace("_", " ").title()
            emoji = "🎒"
            if "elixir" in item_id or "full_heal" in item_id:
                emoji = "✨"
            elif "potion" in item_id or "antidote" in item_id:
                emoji = "🧪"
            elif "melon" in item_id:
                emoji = "🍉"
            elif "smoke" in item_id:
                emoji = "💨"
            elif "grenade" in item_id:
                emoji = "💣"
            elif "feather" in item_id:
                emoji = "🪶"

            options.append(discord.SelectOption(
                label=f"{clean_name} ×{qty}"[:100],
                value=item_id,
                emoji=emoji,
                description=f"Lock in {clean_name} for this round"
            ))

        if options:
            item_select = Select(
                placeholder=f"🎒 Select Consumable Item (Round {self.controller.round_num})...",
                options=options,
                row=0,
                custom_id=f"pvp_ephemeral_select_item_{user_id}"
            )
            item_select.callback = self.on_select
            self.add_item(item_select)
        else:
            btn_empty = Button(label="No Usable Items In Inventory", disabled=True, style=discord.ButtonStyle.secondary)
            self.add_item(btn_empty)

    async def on_select(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ This is not your item selection menu!", ephemeral=True)
            except Exception:
                pass
            return

        vals = interaction.data.get("values", []) if hasattr(interaction, "data") and isinstance(interaction.data, dict) else []
        item_id = vals[0] if vals else "healing_potion"
        item_name = item_id.replace("_", " ").title()

        for child in self.children:
            child.disabled = True
        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(
                    content=f"🔒 Locked in **{item_name}** for **Round {self.controller.round_num}**! Waiting for opponent...",
                    view=self
                )
        except Exception:
            pass

        await self.controller.lock_in_action(self.user_id, {"type": "item", "item_id": item_id}, interaction=interaction)


class PvPBattleView(View):
    """
    Simultaneous Round-Based PvP Battle Interface:
    Row 0: [✨ Skills] [🎒 Items] [🏳️ Quit]

    Both players choose and lock in their skills/items simultaneously via private ephemeral menus!
    Each player only sees and uses their own class skills and inventory items.
    Once both players lock in, the round resolves in Speed order.
    """
    def __init__(self, controller):
        super().__init__(timeout=120)
        self.controller = controller
        self.refresh_components()

    def refresh_components(self):
        """Builds action buttons for simultaneous lock-in combat."""
        self.clear_items()

        # Row 0: [✨ Skills] [🎒 Items] [🏳️ Quit]
        skills_btn = Button(
            label="✨ Skills",
            style=discord.ButtonStyle.primary,
            row=0,
            custom_id="pvp_btn_open_skills"
        )
        skills_btn.callback = self.on_open_skills
        self.add_item(skills_btn)

        items_btn = Button(
            label="🎒 Items",
            style=discord.ButtonStyle.secondary,
            row=0,
            custom_id="pvp_btn_open_items"
        )
        items_btn.callback = self.on_open_items
        self.add_item(items_btn)

        quit_btn = Button(
            label="🏳️ Quit",
            style=discord.ButtonStyle.danger,
            row=0,
            custom_id="pvp_btn_open_quit"
        )
        quit_btn.callback = self.on_open_quit
        self.add_item(quit_btn)

    async def on_open_skills(self, interaction: discord.Interaction):
        if not await self._check_participant(interaction):
            return
        uid = str(interaction.user.id)
        skill_view = PvPSkillSelectView(self.controller, uid)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "✨ **Select your skill to lock in for this round:**",
                    view=skill_view,
                    ephemeral=True
                )
        except Exception:
            pass

    async def on_open_items(self, interaction: discord.Interaction):
        if not await self._check_participant(interaction):
            return
        uid = str(interaction.user.id)
        consumables = self.controller.get_player_consumables(uid)
        if not consumables:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("🎒 You have no usable consumable items in your inventory!", ephemeral=True)
            except Exception:
                pass
            return

        item_view = PvPItemSelectView(self.controller, uid)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("🎒 **Select an item from your inventory to lock in:**", view=item_view, ephemeral=True)
        except Exception:
            pass

    async def on_open_quit(self, interaction: discord.Interaction):
        if not await self._check_participant(interaction):
            return
        uid = str(interaction.user.id)
        quit_view = PvPQuitConfirmView(self.controller, uid)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("🏳️ **Are you sure you want to forfeit this duel?**", view=quit_view, ephemeral=True)
        except Exception:
            pass

    async def on_confirm_quit(self, interaction: discord.Interaction):
        if not await self._check_participant(interaction):
            return
        uid = str(interaction.user.id)
        await self.controller.lock_in_action(uid, {"type": "flee"}, interaction=interaction)

    async def on_cancel_quit(self, interaction: discord.Interaction):
        if not await self._check_participant(interaction):
            return
        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(embed=self.controller.render_embed(), view=self)
            elif self.controller.battle_message:
                await self.controller.battle_message.edit(embed=self.controller.render_embed(), view=self)
        except Exception:
            pass

    # Backward compatibility callbacks
    async def on_skill_btn(self, interaction: discord.Interaction):
        await self.on_open_skills(interaction)

    async def on_skill_select(self, interaction: discord.Interaction):
        if not await self._check_participant(interaction):
            return
        uid = str(interaction.user.id)
        vals = interaction.data.get("values", []) if hasattr(interaction, "data") and isinstance(interaction.data, dict) else []
        chosen_id = vals[0] if vals else "power_strike"
        await self.controller.lock_in_action(uid, {"type": "skill", "skill_id": chosen_id}, interaction=interaction)

    async def on_item_btn(self, interaction: discord.Interaction):
        await self.on_open_items(interaction)

    async def on_item_select(self, interaction: discord.Interaction):
        if not await self._check_participant(interaction):
            return
        uid = str(interaction.user.id)
        vals = interaction.data.get("values", []) if hasattr(interaction, "data") and isinstance(interaction.data, dict) else []
        chosen_id = vals[0] if vals else "none"
        if chosen_id != "none":
            await self.controller.lock_in_action(uid, {"type": "item", "item_id": chosen_id}, interaction=interaction)

    async def on_flee_btn(self, interaction: discord.Interaction):
        await self.on_confirm_quit(interaction)

    async def _check_participant(self, interaction: discord.Interaction) -> bool:
        uid = str(interaction.user.id)
        if uid not in (self.controller.p1_id, self.controller.p2_id):
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ This is not your duel! Challenge a user with `y!duel @user`.", ephemeral=True)
            except Exception:
                pass
            return False
        return True

    async def on_confirm_quit(self, interaction: discord.Interaction):
        if not await self._check_participant(interaction):
            return
        uid = str(interaction.user.id)
        await self.controller.lock_in_action(uid, {"type": "flee"}, interaction=interaction)

    async def on_cancel_quit(self, interaction: discord.Interaction):
        if not await self._check_participant(interaction):
            return
        self.controller.ui_mode = "skills"
        self.refresh_components()
        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(embed=self.controller.render_embed(), view=self)
            elif self.controller.battle_message:
                await self.controller.battle_message.edit(embed=self.controller.render_embed(), view=self)
        except Exception:
            pass

    # Backward compatibility callbacks
    async def on_skill_btn(self, interaction: discord.Interaction):
        if not await self._check_participant(interaction):
            return
        uid = str(interaction.user.id)
        skills = self.controller.get_player_skills(uid)
        sk_id = skills[0]["id"] if skills else "power_strike"
        await self.controller.lock_in_action(uid, {"type": "skill", "skill_id": sk_id}, interaction=interaction)

    async def on_item_btn(self, interaction: discord.Interaction):
        await self.on_open_items(interaction)

    async def on_item_select(self, interaction: discord.Interaction):
        if not await self._check_participant(interaction):
            return
        uid = str(interaction.user.id)
        vals = interaction.data.get("values", []) if hasattr(interaction, "data") and isinstance(interaction.data, dict) else []
        chosen_id = vals[0] if vals else "none"
        if chosen_id != "none":
            await self.controller.lock_in_action(uid, {"type": "item", "item_id": chosen_id}, interaction=interaction)

    async def on_flee_btn(self, interaction: discord.Interaction):
        await self.on_confirm_quit(interaction)

    async def _check_participant(self, interaction: discord.Interaction) -> bool:
        uid = str(interaction.user.id)
        if uid not in (self.controller.p1_id, self.controller.p2_id):
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ This is not your duel! Challenge a user with `y!duel @user`.", ephemeral=True)
            except Exception:
                pass
            return False
        return True


# ─────────────────────────────────────────────────────────────────────────────
# 6. PVP BATTLE CONTROLLER (SIMULTANEOUS LOCK-IN COMBAT ENGINE)
# ─────────────────────────────────────────────────────────────────────────────

class PvPBattleController:
    """
    Simultaneous Round-Based PvP Combat Engine:
    - Both players lock onto their skills/items first before any actions fire
    - Once both players lock in, the round resolves in Speed order
    - Real RPG Player Builds: class, skills, stats (ATK, DEF, SPD, INT), equipment, passives
    - Duel level scaling (up to level 3000)
    - Speed Difference Dodge System: Dodge chance scaled by difference in actual SPD values (capped at 35%)
    - Complete live combat log and final statistics
    """
    def __init__(self, channel, p1_user, p2_user, wager_amount: int = 0, client=None, yuna_gambling_mod=None, duel_level: Optional[int] = None, initial_message=None):
        self.channel = channel
        self.client = client
        self.yuna_gambling_mod = yuna_gambling_mod
        self.initial_message = initial_message
        self.battle_message = initial_message
        self.wager_amount = max(0, int(wager_amount))
        self.pot = self.wager_amount * 2
        self.duel_level = min(3000, max(1, int(duel_level))) if duel_level is not None else None

        # Player 1 setup
        self.p1_id = str(p1_user.id)
        self.p1_name = getattr(p1_user, "display_name", getattr(p1_user, "name", "Player 1"))
        self.p1_mention = getattr(p1_user, "mention", f"<@{self.p1_id}>")
        self.p1_stats = yuna_gambling_mod._USER_STATS.get(self.p1_id, {}) if yuna_gambling_mod and hasattr(yuna_gambling_mod, "_USER_STATS") else {}

        # Player 2 setup
        self.p2_id = str(p2_user.id)
        self.p2_name = getattr(p2_user, "display_name", getattr(p2_user, "name", "Player 2"))
        self.p2_mention = getattr(p2_user, "mention", f"<@{self.p2_id}>")
        self.p2_stats = yuna_gambling_mod._USER_STATS.get(self.p2_id, {}) if yuna_gambling_mod and hasattr(yuna_gambling_mod, "_USER_STATS") else {}

        # Compute Real Player Builds with optional duel level scaling
        import yuna_rpg
        yuna_rpg.ensure_player_rpg(self.p1_stats)
        yuna_rpg.ensure_player_rpg(self.p2_stats)

        p1_build_data = copy.deepcopy(self.p1_stats)
        p2_build_data = copy.deepcopy(self.p2_stats)
        if self.duel_level is not None:
            p1_build_data["battle_level"] = self.duel_level
            p2_build_data["battle_level"] = self.duel_level

        self.p1_rpg = yuna_rpg.get_player_rpg_stats(p1_build_data, self.p1_name)
        self.p2_rpg = yuna_rpg.get_player_rpg_stats(p2_build_data, self.p2_name)

        # Vitals
        self.p1_max_hp = max(1000, self.p1_rpg.get("max_hp", 1000))
        self.p1_hp = self.p1_max_hp
        self.p1_max_mp = max(100, self.p1_rpg.get("max_mp", 100))
        self.p1_mp = self.p1_max_mp
        self.p1_shield = 0
        self.p1_damage_dealt = 0
        self.p1_skills = get_pvp_player_skills(p1_build_data)

        self.p2_max_hp = max(1000, self.p2_rpg.get("max_hp", 1000))
        self.p2_hp = self.p2_max_hp
        self.p2_max_mp = max(100, self.p2_rpg.get("max_mp", 100))
        self.p2_mp = self.p2_max_mp
        self.p2_shield = 0
        self.p2_damage_dealt = 0
        self.p2_skills = get_pvp_player_skills(p2_build_data)

        # Status Effects
        self.p1_status = {
            "frozen": 0, "stunned": 0, "burn": 0, "bleed": 0, "poison": 0,
            "atk_buff": 0.0, "def_down": 0.0, "guard": False, "smoke": False, "stagger": False
        }
        self.p2_status = {
            "frozen": 0, "stunned": 0, "burn": 0, "bleed": 0, "poison": 0,
            "atk_buff": 0.0, "def_down": 0.0, "guard": False, "smoke": False, "stagger": False
        }

        # Speed Comparison
        p1_spd = self.p1_rpg.get("spd", 100)
        p2_spd = self.p2_rpg.get("spd", 100)
        if p1_spd > p2_spd:
            self.active_id = self.p1_id
            first_actor = self.p1_name
            first_spd = p1_spd
        elif p2_spd > p1_spd:
            self.active_id = self.p2_id
            first_actor = self.p2_name
            first_spd = p2_spd
        else:
            self.active_id = random.choice([self.p1_id, self.p2_id])
            first_actor = self.p1_name if self.active_id == self.p1_id else self.p2_name
            first_spd = p1_spd

        # Turn & Interaction State
        self.is_couple = (self.p1_stats.get("spouse") == self.p2_id or self.p2_stats.get("spouse") == self.p1_id)
        self.round_num = 1
        self.combat_logs = [f"⚡ **{first_actor}** has initiative with **{first_spd:,} SPD**!"]
        self.full_battle_log = [f"Round 1: ⚡ {first_actor} initiative (SPD: {p1_spd:,} vs {p2_spd:,})"]
        self.ended = False
        self.ui_mode = "skills"
        self.processing_action = False
        self.resolving_round = False
        self.action_lock = asyncio.Lock()
        self.action_queue = asyncio.Queue()
        self.locked_actions: Dict[str, dict] = {}
        self.round_ready_event = asyncio.Event()
        self.view = PvPBattleView(self)

        ACTIVE_PVP_BATTLES[self.p1_id] = self
        ACTIVE_PVP_BATTLES[self.p2_id] = self

    # State helpers
    def get_status(self, uid: str) -> dict:
        return self.p1_status if uid == self.p1_id else self.p2_status

    def get_rpg(self, uid: str) -> dict:
        return self.p1_rpg if uid == self.p1_id else self.p2_rpg

    def get_player_skills(self, uid: str) -> list:
        return self.p1_skills if uid == self.p1_id else self.p2_skills

    def get_player_consumables(self, uid: str) -> dict:
        stats = self.p1_stats if uid == self.p1_id else self.p2_stats
        return get_pvp_consumable_inventory(stats)

    def get_all_battle_skills(self) -> list:
        """Returns unified list of both players' class skills for the dropdown menu."""
        seen = set()
        res = []
        for sk in (self.p1_skills + self.p2_skills):
            if sk.get("id") and sk["id"] not in seen:
                seen.add(sk["id"])
                res.append(sk)
        if not res:
            res = list(BASE_PVP_SKILLS.values())
        return res

    def get_skill_meta(self, sk_id: str) -> dict:
        """Retrieves skill metadata across player skills, class skills, and base skills."""
        for sk in (self.p1_skills + self.p2_skills):
            if sk.get("id") == sk_id or sk.get("name", "").lower() == str(sk_id).lower():
                return sk
        import yuna_rpg
        if sk_id in yuna_rpg.CLASS_SKILLS:
            return yuna_rpg.CLASS_SKILLS[sk_id]
        if sk_id in yuna_rpg.MARITAL_SKILLS:
            return yuna_rpg.MARITAL_SKILLS[sk_id]
        if sk_id in BASE_PVP_SKILLS:
            return BASE_PVP_SKILLS[sk_id]
        return {"id": sk_id, "name": str(sk_id).replace("_", " ").title(), "mp_cost": 20, "dmg_mult": 1.8, "emoji": "⚔️"}

    def get_active_skills(self) -> list:
        return self.p1_skills if self.active_id == self.p1_id else self.p2_skills

    def get_active_mp(self) -> int:
        return self.p1_mp if self.active_id == self.p1_id else self.p2_mp

    def get_active_max_mp(self) -> int:
        return self.p1_max_mp if self.active_id == self.p1_id else self.p2_max_mp

    def get_active_consumables(self) -> dict:
        stats = self.p1_stats if self.active_id == self.p1_id else self.p2_stats
        return get_pvp_consumable_inventory(stats)

    def get_active_name(self) -> str:
        return self.p1_name if self.active_id == self.p1_id else self.p2_name

    def _fmt_status(self, st: dict, shield: int) -> str:
        tags = []
        if shield > 0:
            tags.append(f"🛡️ Shield: {shield:,}")
        if st.get("guard"):
            tags.append("⛨ Guard")
        if st.get("smoke"):
            tags.append("💨 Smoked")
        if st.get("stagger"):
            tags.append("💣 Staggered")
        if st.get("frozen", 0) > 0:
            tags.append(f"❄️ Frozen ({st['frozen']}t)")
        if st.get("stunned", 0) > 0:
            tags.append(f"💫 Stunned ({st['stunned']}t)")
        if st.get("burn", 0) > 0:
            tags.append(f"🔥 Burn ({st['burn']}t)")
        if st.get("bleed", 0) > 0:
            tags.append(f"🩸 Bleed ({st['bleed']}t)")
        if st.get("poison", 0) > 0:
            tags.append(f"☠️ Poison ({st['poison']}t)")
        if st.get("atk_buff", 0.0) > 0:
            tags.append(f"⚔️ +{int(st['atk_buff']*100)}% ATK")
        if st.get("def_down", 0.0) > 0:
            tags.append(f"🛡️ -{int(st['def_down']*100)}% DEF")
        return " • ".join(tags) if tags else "Healthy"

    def check_dodge(self, actor_id: str, target_id: str) -> Tuple[bool, str]:
        """
        Dodge Calculation:
        - Tactical smoke: 100% dodge on next hit
        - SPD Difference System: Difference between players' actual SPD values determines bonus dodge
        - Capped at 35% so high SPD does not make players untouchable
        """
        target_status = self.get_status(target_id)
        if target_status.get("smoke"):
            target_status["smoke"] = False
            return True, "vanished into smoke! **(100% DODGE)**"

        actor_rpg = self.get_rpg(actor_id)
        target_rpg = self.get_rpg(target_id)

        atk_spd = max(1, actor_rpg.get("spd", 100))
        def_spd = max(1, target_rpg.get("spd", 100))

        spd_dodge = 0.0
        if def_spd > atk_spd:
            spd_diff = def_spd - atk_spd
            spd_ratio = spd_diff / (def_spd + atk_spd)  # 0.0 to < 1.0
            spd_dodge = spd_ratio * 0.35  # Difference-scaled dodge

        base_dodge = min(0.15, target_rpg.get("dodge_bonus", 0.0) * 0.5)
        total_dodge = min(0.35, base_dodge + spd_dodge)  # Reasonably capped at 35%

        if random.random() < total_dodge:
            return True, f"**dodged!** *(SPD: {def_spd:,} vs {atk_spd:,})*"
        return False, ""

    def render_embed(self, round_summary: str = "") -> discord.Embed:
        """Renders the battle embed showing both players' vitals and live lock-in status."""
        p1_lock = "🔒 **[LOCKED IN]**" if self.p1_id in self.locked_actions else "⏳ **[CHOOSING...]**"
        p2_lock = "🔒 **[LOCKED IN]**" if self.p2_id in self.locked_actions else "⏳ **[CHOOSING...]**"

        p1_st_str = self._fmt_status(self.p1_status, self.p1_shield)
        p2_st_str = self._fmt_status(self.p2_status, self.p2_shield)

        p1_spd = self.p1_rpg.get("spd", 100)
        p2_spd = self.p2_rpg.get("spd", 100)

        lvl_badge = f" [Lv.{self.duel_level}]" if self.duel_level else ""
        if self.is_couple:
            title_text = f"💍 SPOUSAL DUEL{lvl_badge} — ROUND {self.round_num}"
            color_val = 0xFF69B4
            footer_text = f"💍 Spousal Sparring • Round {self.round_num} • Select your skill from the dropdown to lock in!"
        elif self.pot > 0:
            title_text = f"⚔️ ARENA PVP DUEL{lvl_badge} — ROUND {self.round_num}"
            color_val = 0xE74C3C
            footer_text = f"Arena Pot: {self.pot:,} 🫐 • Round {self.round_num} • Select your skill from the dropdown to lock in!"
        else:
            title_text = f"⚔️ PVP DUEL{lvl_badge} — ROUND {self.round_num}"
            color_val = 0x3498DB
            footer_text = f"PvP Duel • Round {self.round_num} • Select your skill from the dropdown to lock in!"

        desc = (
            f"**{self.p1_name}** {p1_lock}\n"
            f"❤️ **HP:** {build_pvp_hp_bar(self.p1_hp, self.p1_max_hp)}\n"
            f"⚡ **SPD:** `{p1_spd:,}` | 💧 **MP:** `{self.p1_mp}/{self.p1_max_mp}`\n"
            f"◈ Status: `{p1_st_str}`\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"**{self.p2_name}** {p2_lock}\n"
            f"❤️ **HP:** {build_pvp_hp_bar(self.p2_hp, self.p2_max_hp)}\n"
            f"⚡ **SPD:** `{p2_spd:,}` | 💧 **MP:** `{self.p2_mp}/{self.p2_max_mp}`\n"
            f"◈ Status: `{p2_st_str}`\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

        embed = discord.Embed(title=title_text, description=desc, color=color_val)

        if self.combat_logs:
            embed.add_field(name="📜 Live Battle Log", value="\n".join(self.combat_logs[-4:]), inline=False)

        embed.set_footer(text=footer_text)
        return embed

    async def queue_action(self, action_data: dict):
        """Allows queueing an action or locking it in directly."""
        uid = action_data.get("actor_id") or self.active_id or self.p1_id
        await self.lock_in_action(uid, action_data)

    async def lock_in_action(self, uid: str, action_data: dict, interaction: Optional[discord.Interaction] = None):
        """Locks in an action for the specified player for the current round."""
        if self.ended:
            return
        if uid not in (self.p1_id, self.p2_id):
            if interaction and not interaction.response.is_done():
                try:
                    await interaction.response.send_message("❌ You are not a participant in this duel!", ephemeral=True)
                except Exception:
                    pass
            return

        action_data["actor_id"] = uid

        # Check forfeit
        if action_data.get("type") == "flee":
            self.locked_actions[uid] = action_data
            self.round_ready_event.set()
            return

        # Validate skill ownership
        if action_data.get("type") == "skill":
            sk_id = action_data.get("skill_id", "power_strike")
            player_skills = self.get_player_skills(uid)
            valid_skill_ids = {s.get("id") for s in player_skills}
            if valid_skill_ids and sk_id not in valid_skill_ids:
                if interaction and not interaction.response.is_done():
                    try:
                        await interaction.response.send_message(f"❌ You do not have the skill `{sk_id}` unlocked or equipped!", ephemeral=True)
                    except Exception:
                        pass
                return

        # Validate item ownership
        if action_data.get("type") == "item":
            item_id = action_data.get("item_id")
            consumables = self.get_player_consumables(uid)
            if item_id not in consumables or consumables[item_id] <= 0:
                if interaction and not interaction.response.is_done():
                    try:
                        await interaction.response.send_message(f"❌ You do not have `{item_id}` in your inventory!", ephemeral=True)
                    except Exception:
                        pass
                return

        # Check if already locked in
        if uid in self.locked_actions:
            if interaction and not interaction.response.is_done():
                try:
                    await interaction.response.send_message("🔒 You have already locked in your action for this round! Waiting for opponent...", ephemeral=True)
                except Exception:
                    pass
            return

        self.locked_actions[uid] = action_data
        # Put into action queue for test observability
        try:
            self.action_queue.put_nowait(action_data)
        except Exception:
            pass

        # Determine action name
        act_name = "Skill"
        if action_data.get("type") == "skill":
            sk_id = action_data.get("skill_id", "power_strike")
            meta = self.get_skill_meta(sk_id)
            act_name = meta.get("name", str(sk_id).replace("_", " ").title())
        elif action_data.get("type") == "item":
            act_name = str(action_data.get("item_id", "Item")).replace("_", " ").title()

        if interaction and not interaction.response.is_done():
            try:
                await interaction.response.send_message(
                    f"🔒 **{act_name}** locked in for **Round {self.round_num}**! Waiting for opponent...",
                    ephemeral=True
                )
            except Exception:
                pass

        # Update public battle embed to show locked in state
        if self.battle_message and not self.resolving_round:
            try:
                await self.battle_message.edit(content=None, embed=self.render_embed(), view=self.view)
            except Exception:
                pass

        # If both players locked in, notify round loop
        if self.p1_id in self.locked_actions and self.p2_id in self.locked_actions:
            self.round_ready_event.set()

    async def _wait_for_both_lock_ins(self, timeout: float = 60.0):
        """Waits until both players have locked in an action or timeout expires."""
        if self.p1_id in self.locked_actions and self.p2_id in self.locked_actions:
            return

        wait_event_task = asyncio.create_task(self.round_ready_event.wait())

        def _check_chat(m):
            if str(m.author.id) not in (self.p1_id, self.p2_id):
                return False
            chan_id = getattr(self.channel, "id", None)
            m_chan = getattr(m.channel, "id", None)
            if chan_id and m_chan and str(chan_id) != str(m_chan):
                return False
            return bool(m.content and m.content.strip())

        if self.client and hasattr(self.client, "wait_for"):
            start_t = time.time()
            while not (self.p1_id in self.locked_actions and self.p2_id in self.locked_actions):
                remain = max(0.5, timeout - (time.time() - start_t))
                if remain <= 0.5:
                    break
                msg_task = asyncio.create_task(self.client.wait_for("message", check=_check_chat))
                done, pending = await asyncio.wait([wait_event_task, msg_task], return_when=asyncio.FIRST_COMPLETED, timeout=remain)
                for p in pending:
                    p.cancel()
                if not done:
                    break
                for d in done:
                    res = d.result()
                    if isinstance(res, discord.Message):
                        u_id = str(res.author.id)
                        c = res.content.lower().strip()
                        for pfx in ("y!", "!", "/", ".", ","):
                            if c.startswith(pfx):
                                c = c[len(pfx):].strip()
                        if c in ("flee", "quit", "run", "surrender", "forfeit"):
                            await self.lock_in_action(u_id, {"type": "flee"})
                        elif c.startswith(("use ", "item ", "drink ")):
                            it = re.sub(r'^(?:use|item|drink)[:\s]*', '', c).strip()
                            await self.lock_in_action(u_id, {"type": "item", "item_id": it})
                        elif c.startswith(("skill ", "cast ", "s ")):
                            sk = re.sub(r'^(?:skill|cast|s)[:\s]*', '', c).strip()
                            await self.lock_in_action(u_id, {"type": "skill", "skill_id": sk})
                        else:
                            p_skills = self.p1_skills if u_id == self.p1_id else self.p2_skills
                            sk_id = p_skills[0]["id"] if p_skills else "power_strike"
                            await self.lock_in_action(u_id, {"type": "skill", "skill_id": sk_id})
        else:
            try:
                await asyncio.wait_for(wait_event_task, timeout=timeout)
            except asyncio.TimeoutError:
                pass

    async def execute_action(self, action: dict, actor_id: Optional[str] = None, target_id: Optional[str] = None) -> str:
        """Executes player's action using real RPG math and applies secondary effects."""
        if actor_id is None:
            actor_id = action.get("actor_id") or self.active_id or self.p1_id
        if target_id is None:
            target_id = self.p2_id if actor_id == self.p1_id else self.p1_id

        is_p1 = (actor_id == self.p1_id)
        actor_name = self.p1_name if is_p1 else self.p2_name
        target_name = self.p2_name if is_p1 else self.p1_name
        actor_stats = self.p1_stats if is_p1 else self.p2_stats
        target_stats = self.p2_stats if is_p1 else self.p1_stats
        actor_rpg = self.p1_rpg if is_p1 else self.p2_rpg
        target_rpg = self.p2_rpg if is_p1 else self.p1_rpg
        actor_status = self.p1_status if is_p1 else self.p2_status
        target_status = self.p2_status if is_p1 else self.p1_status

        act_type = action.get("type", "skill")

        # ── 1. QUIT / FORFEIT ──
        if act_type == "flee":
            self.ended = True
            log_entry = f"🏃 **{actor_name}** fled from the duel / forfeited! **{target_name}** claims victory!"
            self.combat_logs.append(log_entry)
            self.full_battle_log.append(f"Round {self.round_num}: {log_entry}")
            if is_p1:
                self.p1_hp = 0
            else:
                self.p2_hp = 0
            return log_entry

        # ── 2. CONSUMABLE ITEM USAGE ──
        elif act_type == "item":
            item_id = action.get("item_id", "healing_potion")
            consumables = get_pvp_consumable_inventory(actor_stats)
            if not item_id or item_id in ("item", "none"):
                item_id = list(consumables.keys())[0] if consumables else "healing_potion"

            inv = actor_stats.setdefault("inventory", {})
            has_item = False
            if item_id == "watermelons" and actor_stats.get("watermelons", 0) > 0:
                actor_stats["watermelons"] -= 1
                has_item = True
            elif inv.get(item_id, 0) > 0:
                inv[item_id] -= 1
                if inv[item_id] <= 0:
                    del inv[item_id]
                has_item = True

            # Persist item deduction immediately
            if has_item and self.yuna_gambling_mod and hasattr(self.yuna_gambling_mod, "_save_data_sync"):
                try:
                    self.yuna_gambling_mod._save_data_sync(self.yuna_gambling_mod._USER_STATS)
                except Exception:
                    pass

            max_hp = self.p1_max_hp if is_p1 else self.p2_max_hp
            max_mp = self.p1_max_mp if is_p1 else self.p2_max_mp

            if has_item:
                if item_id in ("dungeon_elixir", "elixir", "abyssal_elixir", "full_heal"):
                    heal = int(max_hp * 0.60)
                    if is_p1:
                        self.p1_hp = min(max_hp, self.p1_hp + heal)
                        self.p1_mp = max_mp
                    else:
                        self.p2_hp = min(max_hp, self.p2_hp + heal)
                        self.p2_mp = max_mp
                    msg = f"✨ **{actor_name}** consumed **{item_id.replace('_', ' ').title()}**, restoring **+{heal:,} HP** & 100% MP!"
                elif item_id in ("healing_potion", "potion", "health_potion", "hp_potion"):
                    heal = int(max_hp * 0.40)
                    if is_p1:
                        self.p1_hp = min(max_hp, self.p1_hp + heal)
                        self.p1_mp = min(max_mp, self.p1_mp + 25)
                    else:
                        self.p2_hp = min(max_hp, self.p2_hp + heal)
                        self.p2_mp = min(max_mp, self.p2_mp + 25)
                    msg = f"🧪 **{actor_name}** drank a **Healing Potion**, restoring **+{heal:,} HP** & +25 MP!"
                elif item_id in ("pocket_watermelon", "watermelons"):
                    heal = int(max_hp * 0.30)
                    if is_p1:
                        self.p1_hp = min(max_hp, self.p1_hp + heal)
                        self.p1_mp = min(max_mp, self.p1_mp + 15)
                    else:
                        self.p2_hp = min(max_hp, self.p2_hp + heal)
                        self.p2_mp = min(max_mp, self.p2_mp + 15)
                    msg = f"🍉 **{actor_name}** enjoyed **Fresh Watermelon**, restoring **+{heal:,} HP** & +15 MP!"
                elif item_id == "smoke_bomb":
                    actor_status["smoke"] = True
                    msg = f"💨 **{actor_name}** deployed a **Tactical Smoke Bomb**! (100% Dodge next incoming hit!)"
                elif item_id == "stagger_grenade":
                    target_status["stagger"] = True
                    msg = f"💣 **{actor_name}** hurled a **Stagger Grenade**! **{target_name}** was staggered (+50% damage taken)!"
                elif item_id == "strength_potion":
                    actor_status["atk_buff"] = 0.50
                    msg = f"💪 **{actor_name}** drank a **Strength Potion**! (+50% ATK next attack)!"
                elif item_id == "iron_skin_potion":
                    actor_status["guard"] = True
                    msg = f"🛡️ **{actor_name}** drank an **Iron Skin Potion**! (Guard raised / +50% Damage Resistance)!"
                elif item_id == "energy_potion":
                    if is_p1:
                        self.p1_mp = min(max_mp, self.p1_mp + 50)
                    else:
                        self.p2_mp = min(max_mp, self.p2_mp + 50)
                    msg = f"⚡ **{actor_name}** drank an **Energy Potion**, restoring **+50 MP**!"
                elif item_id == "antidote":
                    actor_status["burn"] = 0
                    actor_status["bleed"] = 0
                    actor_status["poison"] = 0
                    msg = f"🧪 **{actor_name}** used an **Antidote**! All poisons, burns, and bleeds were cleansed!"
                else:
                    heal = int(max_hp * 0.30)
                    if is_p1:
                        self.p1_hp = min(max_hp, self.p1_hp + heal)
                    else:
                        self.p2_hp = min(max_hp, self.p2_hp + heal)
                    msg = f"🎒 **{actor_name}** used **{item_id.replace('_', ' ').title()}**, restoring **+{heal:,} HP**!"
            else:
                msg = f"⚠️ **{actor_name}** had no **{item_id}** left in inventory!"

            self.combat_logs.append(msg)
            self.full_battle_log.append(f"Round {self.round_num}: {msg}")
            return msg

        # ── 3. SKILL EXECUTION (REAL RPG FORMULA & SECONDARY EFFECTS) ──
        else:
            sk_id = action.get("skill_id")
            skills = self.p1_skills if is_p1 else self.p2_skills
            sk = next((s for s in skills if s.get("id") == sk_id or s.get("name", "").lower() == str(sk_id).lower()), None)
            if not sk:
                import yuna_rpg
                sk = yuna_rpg.CLASS_SKILLS.get(sk_id) or yuna_rpg.MARITAL_SKILLS.get(sk_id) or BASE_PVP_SKILLS.get(sk_id)
                if not sk:
                    sk = next((s for s in yuna_rpg.CLASS_SKILLS.values() if s.get("name", "").lower() == str(sk_id).lower() or s.get("id") == sk_id), None)
                if not sk:
                    sk = next((s for s in BASE_PVP_SKILLS.values() if s.get("name", "").lower() == str(sk_id).lower() or s.get("id") == sk_id), None)
                if not sk:
                    sk = skills[0] if skills else {"id": "strike", "name": "Basic Strike", "mp_cost": 0, "dmg_mult": 1.5, "emoji": "⚔️"}

            cur_mp = self.p1_mp if is_p1 else self.p2_mp
            mp_c = sk.get("mp_cost", 0)
            if cur_mp < mp_c:
                dmg_mult = 1.0
                sk_name = f"Exhausted Strike ({sk['name']})"
                sk_emoji = "⚔️"
            else:
                if is_p1:
                    self.p1_mp -= mp_c
                else:
                    self.p2_mp -= mp_c
                dmg_mult = float(sk["dmg_mult"]) if "dmg_mult" in sk else 1.8
                sk_name = sk.get("name", "Class Skill")
                sk_emoji = sk.get("emoji", "✦")

            # Check Blind Accuracy Penalty
            if actor_status.get("blind", 0) > 0:
                actor_status["blind"] -= 1
                if random.random() < 0.35:
                    msg = f"👁️ **{actor_name}** was **Blinded** and missed their attack against **{target_name}**!"
                    self.combat_logs.append(msg)
                    self.full_battle_log.append(f"Round {self.round_num}: {msg}")
                    return msg

            # Check Dodge
            is_dodged, dodge_detail = self.check_dodge(actor_id, target_id)
            if is_dodged:
                msg = f"💨 **{actor_name}** used {sk_emoji} **{sk_name}**, but **{target_name}** {dodge_detail}!"
                self.combat_logs.append(msg)
                self.full_battle_log.append(f"Round {self.round_num}: {msg}")
                return msg

            # Calculate Real RPG Damage
            atk_val = actor_rpg.get("atk", 100) * (1.0 + actor_status["atk_buff"])
            if actor_status.get("atk_debuff", 0.0) > 0:
                atk_val *= max(0.20, (1.0 - actor_status["atk_debuff"]))
                actor_status["atk_debuff"] = 0.0

            target_def = target_rpg.get("def", 50) * max(0.10, (1.0 - target_status["def_down"]))
            if sk.get("armor_pierce"):
                target_def *= max(0.0, (1.0 - sk["armor_pierce"]))

            crit_rate = actor_rpg.get("crit_rate", 0.05)
            crit_mult = actor_rpg.get("crit_mult", 1.5) + sk.get("crit_mult_bonus", 0.0)
            is_crit = actor_status.pop("guaranteed_crit", False) or (random.random() < (crit_rate + actor_status.get("crit_buff", 0.0)))
            crit_factor = crit_mult if is_crit else 1.0

            if sk.get("true_damage"):
                raw_dmg = atk_val * dmg_mult * crit_factor
            elif sk.get("def_scaling"):
                base_stat = target_def + int(atk_val * 0.5)
                raw_dmg = base_stat * dmg_mult * crit_factor
            else:
                mitigation = min(0.75, target_def / (target_def + 1200.0))
                raw_dmg = atk_val * dmg_mult * crit_factor * (1.0 - mitigation)

            # Target Invulnerability
            if target_status.get("invulnerable"):
                target_status["invulnerable"] = False
                raw_dmg = 0

            # Target Guard
            if target_status.get("guard"):
                raw_dmg *= 0.50
                target_status["guard"] = False

            # Target Stagger
            if target_status.get("stagger"):
                raw_dmg *= 1.50
                target_status["stagger"] = False

            # Target Gear Damage Reduction
            gear_reduc = target_rpg.get("dmg_reduction", 0.0)
            if gear_reduc > 0:
                raw_dmg *= max(0.20, (1.0 - gear_reduc))

            # Missing HP scaling
            target_hp = self.p2_hp if is_p1 else self.p1_hp
            target_max_hp = self.p2_max_hp if is_p1 else self.p1_max_hp
            if sk.get("missing_hp_scaling"):
                missing_pct = max(0.0, 1.0 - (target_hp / max(1, target_max_hp)))
                raw_dmg *= (1.0 + missing_pct)

            # Multi-hit Apex Skills
            if sk.get("hits"):
                raw_dmg *= min(1.5, 1.0 + (sk["hits"] * 0.05))

            final_dmg = max(0, int(raw_dmg)) if not target_status.get("invulnerable") else 0
            if final_dmg > 0 and dmg_mult > 0:
                final_dmg = max(20, final_dmg)

            extras = []
            if is_crit:
                extras.append("💥 Crit!")

            # Self HP Sacrifice
            if sk.get("self_hp_sac"):
                actor_hp = self.p1_hp if is_p1 else self.p2_hp
                sac = int(actor_hp * sk["self_hp_sac"])
                if is_p1:
                    self.p1_hp = max(1, self.p1_hp - sac)
                else:
                    self.p2_hp = max(1, self.p2_hp - sac)
                extras.append(f"🩸 Sacrificed {sac:,} HP")

            # Shield Absorption
            target_shield = self.p2_shield if is_p1 else self.p1_shield
            if target_shield > 0 and final_dmg > 0:
                absorbed = min(target_shield, final_dmg)
                if is_p1:
                    self.p2_shield -= absorbed
                else:
                    self.p1_shield -= absorbed
                final_dmg -= absorbed
                if absorbed > 0:
                    extras.append(f"🛡️ {absorbed:,} Shield Absorbed")

            # Apply Damage
            if is_p1:
                self.p2_hp = max(0, self.p2_hp - final_dmg)
                self.p1_damage_dealt += final_dmg
            else:
                self.p1_hp = max(0, self.p1_hp - final_dmg)
                self.p2_damage_dealt += final_dmg

            # Damage Reflection onto Attacker
            if target_status.get("reflect_pct", 0.0) > 0 and final_dmg > 0:
                refl_dmg = int(final_dmg * target_status["reflect_pct"])
                if is_p1:
                    self.p1_hp = max(0, self.p1_hp - refl_dmg)
                else:
                    self.p2_hp = max(0, self.p2_hp - refl_dmg)
                extras.append(f"🪞 Reflected {refl_dmg:,} damage back")

            # Instant Execution
            if sk.get("instant_exec_threshold"):
                target_hp_now = self.p2_hp if is_p1 else self.p1_hp
                if (target_hp_now / max(1, target_max_hp)) < sk["instant_exec_threshold"]:
                    if is_p1:
                        self.p2_hp = 0
                    else:
                        self.p1_hp = 0
                    extras.append("💀 INSTANT EXECUTION!")

            # Reset one-turn attack buff after strike
            actor_status["atk_buff"] = 0.0

            # ── SECONDARY EFFECTS ──
            # Lifesteal
            ls_rate = float(actor_rpg.get("lifesteal", 0.0)) + float(sk.get("lifesteal", 0.0)) + float(sk.get("lifesteal_pct", 0.0))
            if ls_rate > 0 and final_dmg > 0:
                ls_amt = int(final_dmg * ls_rate)
                max_hp = self.p1_max_hp if is_p1 else self.p2_max_hp
                if is_p1:
                    self.p1_hp = min(max_hp, self.p1_hp + ls_amt)
                else:
                    self.p2_hp = min(max_hp, self.p2_hp + ls_amt)
                extras.append(f"+{ls_amt:,} Lifesteal")

            # Healing & Overheal Barrier
            if sk.get("heal_pct") or sk.get("party_heal_pct"):
                h_pct = float(sk.get("heal_pct") or sk.get("party_heal_pct"))
                cur_h = self.p1_hp if is_p1 else self.p2_hp
                max_h = self.p1_max_hp if is_p1 else self.p2_max_hp
                if sk.get("emergency_double") and (cur_h / max_h) < 0.30:
                    h_pct *= 2.0
                heal_amt = int(max_h * h_pct)
                new_h = min(max_h, cur_h + heal_amt)
                overheal = max(0, (cur_h + heal_amt) - max_h)
                if is_p1:
                    self.p1_hp = new_h
                else:
                    self.p2_hp = new_h
                extras.append(f"+{heal_amt:,} HP")
                if overheal > 0 and sk.get("overheal_barrier"):
                    if is_p1:
                        self.p1_shield += overheal
                    else:
                        self.p2_shield += overheal
                    extras.append(f"+{overheal:,} Shield (Overheal)")

            # Shield Barrier
            if sk.get("shield_pct") or sk.get("party_shield_pct"):
                s_pct = float(sk.get("shield_pct") or sk.get("party_shield_pct"))
                max_h = self.p1_max_hp if is_p1 else self.p2_max_hp
                sh_amt = int(max_h * s_pct)
                if is_p1:
                    self.p1_shield += sh_amt
                else:
                    self.p2_shield += sh_amt
                extras.append(f"+{sh_amt:,} Shield")

            # Party MP Restore / Refund
            mp_amt = int(sk.get("party_mp_restore", 0) + sk.get("mp_refund", 0) + sk.get("mp_refund_on_counter", 0))
            if mp_amt > 0:
                max_m = self.p1_max_mp if is_p1 else self.p2_max_mp
                if is_p1:
                    self.p1_mp = min(max_m, self.p1_mp + mp_amt)
                else:
                    self.p2_mp = min(max_m, self.p2_mp + mp_amt)
                extras.append(f"+{mp_amt} MP")

            # Guard Raised
            if sk.get("dmg_reduction") or sk.get("party_dmg_reduction") or sk.get("stance") == "defend":
                actor_status["guard"] = True
                extras.append("⛨ Guard Raised")

            # Invulnerability
            if sk.get("party_invulnerable"):
                actor_status["invulnerable"] = True
                extras.append("⛰️ 100% Damage Immunity (1 turn)")

            # Cleanse
            if sk.get("cleanse") or sk.get("party_cleanse"):
                actor_status["burn"] = 0
                actor_status["bleed"] = 0
                actor_status["poison"] = 0
                actor_status["atk_debuff"] = 0.0
                extras.append("✨ Cleansed")

            # Freeze / Stun
            if sk.get("stun_chance"):
                chance = float(sk["stun_chance"])
                if target_rpg.get("class_id") == "mystery" or "stun" in target_rpg.get("immune_statuses", []):
                    extras.append(f"❄️ {target_name} resisted Freeze")
                elif random.random() < chance:
                    is_frost = any(k in (sk.get("id", "") + sk.get("name", "")).lower() for k in ("frost", "freeze", "ice", "zero", "stasis", "thermal"))
                    if is_frost:
                        target_status["frozen"] = 1
                        extras.append(f"❄️ {target_name} was Frozen!")
                    else:
                        target_status["stunned"] = 1
                        extras.append(f"💫 {target_name} was Stunned!")

            # Stagger
            if sk.get("stagger_amt", 0) >= 20 or sk.get("interrupt"):
                target_status["stagger"] = True
                extras.append(f"💣 {target_name} was Staggered (+50% Dmg Taken)")

            # Attack Up
            b_val = sk.get("buff_next_atk") or sk.get("party_buff_atk")
            if b_val:
                boost = (b_val - 1.0) if b_val > 1.0 else b_val
                actor_status["atk_buff"] = max(actor_status.get("atk_buff", 0.0), boost)
                extras.append(f"⚔️ ATK increased by {int(boost*100)}%")

            # Defense Down
            if sk.get("armor_strip"):
                strip_val = float(sk["armor_strip"])
                target_status["def_down"] = min(0.90, target_status.get("def_down", 0.0) + strip_val)
                extras.append(f"🛡️ {target_name}'s DEF decreased by {int(strip_val*100)}%")

            # Poison
            if sk.get("debuff") == "poison" or "poison" in (sk.get("id", "") + sk.get("name", "")).lower():
                target_status["poison"] = 2
                extras.append(f"☠️ {target_name} gained Poison II")

            # Burn
            if sk.get("debuff") == "burn" or any(k in (sk.get("id", "") + sk.get("name", "")).lower() for k in ("burn", "inferno", "cinder", "ignite", "pyro", "detonation")):
                target_status["burn"] = 2
                extras.append(f"🔥 {target_name} was Ignited")

            # Bleed
            if sk.get("bleed") or any(k in (sk.get("id", "") + sk.get("name", "")).lower() for k in ("bleed", "artery", "rend")):
                target_status["bleed"] = 2
                extras.append(f"🩸 {target_name} gained Bleed")

            # Shock
            if sk.get("debuff") == "shock" or "shock" in (sk.get("id", "") + sk.get("name", "")).lower() or "chain_lightning" in sk.get("id", ""):
                target_status["atk_debuff"] = 0.30
                extras.append(f"⚡ {target_name} is Shocked (-30% ATK)")

            # Blind
            if sk.get("debuff") == "blind" or sk.get("blind_turns") or "blind" in sk.get("id", "").lower():
                target_status["blind"] = 1
                extras.append(f"👁️ {target_name} was Blinded")

            # Daze
            if sk.get("debuff") == "daze" or "daze" in sk.get("id", "").lower():
                target_status["atk_debuff"] = 0.25
                extras.append(f"💫 {target_name} was Dazed (-25% ATK)")

            # Speed Buff / Debuff / Turn Siphon
            if sk.get("spd_buff"):
                actor_rpg["spd"] = int(actor_rpg.get("spd", 100) * (1.0 + sk["spd_buff"]))
                extras.append(f"⚡ SPD +{int(sk['spd_buff']*100)}%")
            if sk.get("spd_debuff"):
                target_rpg["spd"] = int(target_rpg.get("spd", 100) * (1.0 - sk["spd_debuff"]))
                extras.append(f"⚡ {target_name}'s SPD -{int(sk['spd_debuff']*100)}%")
            if sk.get("turn_siphon"):
                siph = int(target_rpg.get("spd", 100) * sk["turn_siphon"])
                target_rpg["spd"] = max(10, target_rpg.get("spd", 100) - siph)
                actor_rpg["spd"] = actor_rpg.get("spd", 100) + siph
                extras.append(f"⏱️ Siphoned {siph:,} SPD")

            # Dodge Buff
            if sk.get("dodge_buff"):
                actor_status["smoke"] = True
                extras.append("💨 100% Dodge next hit")

            # Guaranteed Crit Next
            if sk.get("force_crit_next"):
                actor_status["guaranteed_crit"] = True
                extras.append("🎯 Guaranteed Crit Next Strike")

            # Reflection Stance
            if sk.get("reflect_pct"):
                actor_status["reflect_pct"] = float(sk["reflect_pct"])
                extras.append(f"🪞 Reflective Stance ({int(sk['reflect_pct']*100)}%)")

            # Passive Revive (Self)
            if sk.get("passive_revive"):
                actor_status["passive_revive"] = True
                extras.append("🪽 Protected from Death")

            # Auto-Revive check
            target_hp_after = self.p2_hp if is_p1 else self.p1_hp
            if target_hp_after <= 0:
                revived = False
                if target_status.get("passive_revive"):
                    target_status["passive_revive"] = False
                    revive_hp = int(target_max_hp * 0.75)
                    if is_p1:
                        self.p2_hp = revive_hp
                    else:
                        self.p1_hp = revive_hp
                    extras.append(f"✨ Divine Intervention Annulled Death (+{revive_hp:,} HP)!")
                    revived = True
                elif not revived:
                    t_inv = target_stats.get("inventory", {})
                    if t_inv.get("phoenix_feather", 0) > 0:
                        t_inv["phoenix_feather"] -= 1
                        revive_hp = int(target_max_hp * 0.75)
                        if is_p1:
                            self.p2_hp = revive_hp
                        else:
                            self.p1_hp = revive_hp
                        extras.append(f"🪶 Phoenix Feather Auto-Revive (+{revive_hp:,} HP)!")

            extra_str = f" *({', '.join(extras)})*" if extras else ""
            msg = f"{sk_emoji} **{actor_name}** used **{sk_name}** → **{target_name}** for `{final_dmg:,}` damage{extra_str}!"
            self.combat_logs.append(msg)
            self.full_battle_log.append(f"Round {self.round_num}: {msg}")
            return msg

    async def resolve_locked_round(self):
        """Resolves both players' locked actions in Speed order with full RPG mechanics and secondary effects."""
        # 1. Check Forfeit
        p1_act = self.locked_actions.get(self.p1_id, {})
        p2_act = self.locked_actions.get(self.p2_id, {})

        if p1_act.get("type") == "flee":
            self.p1_hp = 0
            log_entry = f"🏃 **{self.p1_name}** fled from the duel / forfeited! **{self.p2_name}** claims victory!"
            self.combat_logs.append(log_entry)
            self.full_battle_log.append(f"Round {self.round_num}: {log_entry}")
            await self.finish_duel(winner_id=self.p2_id, loser_id=self.p1_id)
            return
        if p2_act.get("type") == "flee":
            self.p2_hp = 0
            log_entry = f"🏃 **{self.p2_name}** fled from the duel / forfeited! **{self.p1_name}** claims victory!"
            self.combat_logs.append(log_entry)
            self.full_battle_log.append(f"Round {self.round_num}: {log_entry}")
            await self.finish_duel(winner_id=self.p1_id, loser_id=self.p2_id)
            return

        # 2. Determine Speed Order
        p1_spd = self.p1_rpg.get("spd", 100)
        p2_spd = self.p2_rpg.get("spd", 100)
        if p1_spd > p2_spd:
            order = [(self.p1_id, self.p2_id, p1_act), (self.p2_id, self.p1_id, p2_act)]
        elif p2_spd > p1_spd:
            order = [(self.p2_id, self.p1_id, p2_act), (self.p1_id, self.p2_id, p1_act)]
        else:
            if random.random() < 0.5:
                order = [(self.p1_id, self.p2_id, p1_act), (self.p2_id, self.p1_id, p2_act)]
            else:
                order = [(self.p2_id, self.p1_id, p2_act), (self.p1_id, self.p2_id, p1_act)]

        # Execute Actions in Speed Order
        for actor_id, target_id, action in order:
            if self.ended or self.p1_hp <= 0 or self.p2_hp <= 0:
                break

            actor_name = self.p1_name if actor_id == self.p1_id else self.p2_name
            actor_status = self.p1_status if actor_id == self.p1_id else self.p2_status

            # Check CC (Frozen / Stunned)
            if actor_status.get("frozen", 0) > 0:
                actor_status["frozen"] -= 1
                cc_msg = f"❄️ **{actor_name}** was **Frozen** and could not act this round!"
                self.combat_logs.append(cc_msg)
                self.full_battle_log.append(f"Round {self.round_num}: {cc_msg}")
                continue

            if actor_status.get("stunned", 0) > 0:
                actor_status["stunned"] -= 1
                cc_msg = f"💫 **{actor_name}** was **Stunned** and could not act this round!"
                self.combat_logs.append(cc_msg)
                self.full_battle_log.append(f"Round {self.round_num}: {cc_msg}")
                continue

            # Execute action
            await self.execute_action(action, actor_id=actor_id, target_id=target_id)

        # Check death after actions
        if self.p1_hp <= 0:
            await self.finish_duel(winner_id=self.p2_id, loser_id=self.p1_id)
            return
        elif self.p2_hp <= 0:
            await self.finish_duel(winner_id=self.p1_id, loser_id=self.p2_id)
            return

        # 3. End-of-Round DoT (Burn, Bleed, Poison)
        dot_logs = []
        for uid, uname, max_hp, st in [
            (self.p1_id, self.p1_name, self.p1_max_hp, self.p1_status),
            (self.p2_id, self.p2_name, self.p2_max_hp, self.p2_status)
        ]:
            if st.get("burn", 0) > 0:
                burn_dmg = max(10, int(max_hp * 0.05))
                if uid == self.p1_id:
                    self.p1_hp = max(0, self.p1_hp - burn_dmg)
                else:
                    self.p2_hp = max(0, self.p2_hp - burn_dmg)
                st["burn"] -= 1
                dot_logs.append(f"🔥 **{uname}** suffered `{burn_dmg:,}` Burn damage!")

            if st.get("bleed", 0) > 0:
                bleed_dmg = max(10, int(max_hp * 0.06))
                if uid == self.p1_id:
                    self.p1_hp = max(0, self.p1_hp - bleed_dmg)
                else:
                    self.p2_hp = max(0, self.p2_hp - bleed_dmg)
                st["bleed"] -= 1
                dot_logs.append(f"🩸 **{uname}** suffered `{bleed_dmg:,}` Bleed damage!")

            if st.get("poison", 0) > 0:
                poison_dmg = max(10, int(max_hp * 0.06))
                if uid == self.p1_id:
                    self.p1_hp = max(0, self.p1_hp - poison_dmg)
                else:
                    self.p2_hp = max(0, self.p2_hp - poison_dmg)
                st["poison"] -= 1
                dot_logs.append(f"☠️ **{uname}** suffered `{poison_dmg:,}` Poison damage!")

        if dot_logs:
            for dl in dot_logs:
                self.combat_logs.append(dl)
                self.full_battle_log.append(f"Round {self.round_num}: {dl}")

        # Check death after DoTs
        if self.p1_hp <= 0 and self.p2_hp <= 0:
            if (self.p1_hp / self.p1_max_hp) >= (self.p2_hp / self.p2_max_hp):
                await self.finish_duel(winner_id=self.p1_id, loser_id=self.p2_id)
            else:
                await self.finish_duel(winner_id=self.p2_id, loser_id=self.p1_id)
            return
        elif self.p1_hp <= 0:
            await self.finish_duel(winner_id=self.p2_id, loser_id=self.p1_id)
            return
        elif self.p2_hp <= 0:
            await self.finish_duel(winner_id=self.p1_id, loser_id=self.p2_id)
            return

    async def finish_duel(self, winner_id: str, loser_id: str):
        """Resolves victor rewards, achievements, and complete post-match battle log."""
        self.ended = True
        ACTIVE_PVP_BATTLES.pop(self.p1_id, None)
        ACTIVE_PVP_BATTLES.pop(self.p2_id, None)

        for child in self.view.children:
            child.disabled = True

        winner_name = self.p1_name if winner_id == self.p1_id else self.p2_name
        loser_name = self.p2_name if winner_id == self.p1_id else self.p1_name
        winner_hp = self.p1_hp if winner_id == self.p1_id else self.p2_hp

        # Optional berry pot handling for wager matches
        bonus_txt = ""
        win_delta = self.pot
        if self.wager_amount > 0 and self.yuna_gambling_mod:
            if hasattr(self.yuna_gambling_mod, "get_gamble_win_bonuses"):
                try:
                    bonus, bonus_txt = await self.yuna_gambling_mod.get_gamble_win_bonuses(winner_id, self.wager_amount)
                    win_delta = self.pot + bonus
                except Exception:
                    pass

            if win_delta > 0 and hasattr(self.yuna_gambling_mod, "_update_user_stats"):
                try:
                    await self.yuna_gambling_mod._update_user_stats(winner_id, berries_delta=win_delta, is_gamble=True)
                except Exception:
                    pass

        if self.yuna_gambling_mod and hasattr(self.yuna_gambling_mod, "_USER_STATS") and winner_id in self.yuna_gambling_mod._USER_STATS:
            self.yuna_gambling_mod._USER_STATS[winner_id]["fights_won"] = self.yuna_gambling_mod._USER_STATS[winner_id].get("fights_won", 0) + 1
            if hasattr(self.yuna_gambling_mod, "_save_data_sync"):
                self.yuna_gambling_mod._save_data_sync(self.yuna_gambling_mod._USER_STATS)

        if self.yuna_gambling_mod and hasattr(self.yuna_gambling_mod, "record_task_progress"):
            try:
                await self.yuna_gambling_mod.record_task_progress(winner_id, "gamble")
                await self.yuna_gambling_mod.record_task_progress(loser_id, "gamble")
            except Exception:
                pass

        banner = ""
        if self.yuna_gambling_mod and hasattr(self.yuna_gambling_mod, "check_and_award_achievements") and hasattr(self.yuna_gambling_mod, "format_achievement_banner"):
            try:
                unlocked = await self.yuna_gambling_mod.check_and_award_achievements(winner_id)
                banner = self.yuna_gambling_mod.format_achievement_banner(unlocked)
            except Exception:
                pass

        # Build Duel Complete Embed matching prompt specification
        if self.is_couple:
            end_desc = (
                f"💖 **{winner_name} defeated their beloved spouse {loser_name}!**\n\n"
                f"**Final HP**\n"
                f"{winner_name}: ❤️ {winner_hp:,}\n"
                f"{loser_name}: ☠️ 0\n\n"
                f"**Rounds:** {self.round_num}\n\n"
                f"**Damage dealt**\n"
                f"{self.p1_name}: {self.p1_damage_dealt:,}\n"
                f"{self.p2_name}: {self.p2_damage_dealt:,}\n"
            )
        else:
            end_desc = (
                f"⚔️ **{winner_name} defeated {loser_name}!**\n\n"
                f"**Final HP**\n"
                f"{winner_name}: ❤️ {winner_hp:,}\n"
                f"{loser_name}: ☠️ 0\n\n"
                f"**Rounds:** {self.round_num}\n\n"
                f"**Damage dealt**\n"
                f"{self.p1_name}: {self.p1_damage_dealt:,}\n"
                f"{self.p2_name}: {self.p2_damage_dealt:,}\n"
            )
        if self.pot > 0:
            end_desc += f"\n💰 **Pot Claimed:** `+{win_delta:,} 🫐`{bonus_txt}\n"
        if banner:
            end_desc += f"\n{banner}"

        embed_title = f"💍 SPOUSAL DUEL VICTOR • {winner_name.upper()} WINS!" if self.is_couple else "🏆 DUEL COMPLETE"
        embed = discord.Embed(
            title=embed_title,
            description=end_desc,
            color=0x2ECC71 if not self.is_couple else 0xFF69B4
        )

        log_summary = "\n".join(self.full_battle_log[-12:])
        embed.add_field(name="📜 Full Battle Log Summary", value=f"```text\n{log_summary[:950]}\n```", inline=False)
        embed.set_footer(text="Duel concluded • Real RPG Builds & Simultaneous Combat System")

        if self.battle_message:
            try:
                await self.battle_message.edit(content=None, embed=embed, view=self.view)
            except Exception:
                pass

    async def start(self):
        """Runs the interactive simultaneous turn-based PvP battle loop."""
        initial_embed = self.render_embed()
        done = False
        inter = getattr(self, "interaction", None)
        if inter:
            try:
                if hasattr(inter, "response") and not inter.response.is_done():
                    await inter.response.edit_message(content=None, embed=initial_embed, view=self.view)
                    done = True
                    if not self.battle_message and hasattr(inter, "message"):
                        self.battle_message = inter.message
                elif hasattr(inter, "edit_original_response"):
                    await inter.edit_original_response(content=None, embed=initial_embed, view=self.view)
                    done = True
                    if not self.battle_message and hasattr(inter, "message"):
                        self.battle_message = inter.message
            except Exception as e:
                print(f"[PVP INTERACTION EDIT ERROR] {e}")

        if not done:
            if self.battle_message:
                try:
                    await self.battle_message.edit(content=None, embed=initial_embed, view=self.view)
                    done = True
                except Exception as e:
                    print(f"[PVP BATTLE MSG EDIT ERROR] {e}")
            if not done and self.channel:
                try:
                    self.battle_message = await self.channel.send(embed=initial_embed, view=self.view)
                    done = True
                except Exception as e:
                    print(f"[PVP CHANNEL SEND ERROR] {e}")

        # Simultaneous Lock-In Battle Loop
        while not self.ended and self.p1_hp > 0 and self.p2_hp > 0 and self.round_num <= 50:
            self.locked_actions = {}
            self.round_ready_event.clear()
            self.resolving_round = False
            self.view.refresh_components()

            if self.battle_message:
                try:
                    await self.battle_message.edit(content=None, embed=self.render_embed(), view=self.view)
                except Exception:
                    pass

            # Wait for both players to lock in actions
            await self._wait_for_both_lock_ins(timeout=60.0)

            # Fallback if timeout expired without choosing
            if self.p1_id not in self.locked_actions:
                sk_1 = self.p1_skills[0]["id"] if self.p1_skills else "power_strike"
                self.locked_actions[self.p1_id] = {"type": "skill", "skill_id": sk_1, "timeout": True}
            if self.p2_id not in self.locked_actions:
                sk_2 = self.p2_skills[0]["id"] if self.p2_skills else "power_strike"
                self.locked_actions[self.p2_id] = {"type": "skill", "skill_id": sk_2, "timeout": True}

            self.resolving_round = True

            # Resolve simultaneous locked round
            await self.resolve_locked_round()

            if self.p1_hp <= 0 or self.p2_hp <= 0 or self.ended:
                break

            self.round_num += 1

        if not self.ended:
            # Round limit reached (round 50) -> HP% tiebreaker
            p1_pct = self.p1_hp / self.p1_max_hp
            p2_pct = self.p2_hp / self.p2_max_hp
            if p1_pct >= p2_pct:
                await self.finish_duel(winner_id=self.p1_id, loser_id=self.p2_id)
            else:
                await self.finish_duel(winner_id=self.p2_id, loser_id=self.p1_id)


# ─────────────────────────────────────────────────────────────────────────────
# 7. DUEL INITIALIZATION & INTERACTION DISPATCH
# ─────────────────────────────────────────────────────────────────────────────

async def start_duel_from_request(req_data: dict, interaction: Optional[discord.Interaction] = None, view: Optional[View] = None, client=None):
    """Launches PvP battle from accepted y!duel challenge."""
    author_id = req_data["author_id"]
    target_id = req_data["target_id"]
    duel_level = req_data.get("duel_level")
    battle_msg = req_data.get("message") or getattr(interaction, "message", None)
    channel = getattr(battle_msg, "channel", None) or getattr(interaction, "channel", None) or req_data.get("channel")
    resolved_client = client or req_data.get("client") or getattr(interaction, "client", None)

    # Fetch users
    p1_user = req_data.get("author_user")
    p2_user = req_data.get("target_user")
    if not p1_user and resolved_client:
        try:
            p1_user = resolved_client.get_user(int(author_id))
            if not p1_user and hasattr(resolved_client, "fetch_user"):
                p1_user = await resolved_client.fetch_user(int(author_id))
        except Exception:
            pass
    if not p2_user and resolved_client:
        try:
            p2_user = resolved_client.get_user(int(target_id))
            if not p2_user and hasattr(resolved_client, "fetch_user"):
                p2_user = await resolved_client.fetch_user(int(target_id))
        except Exception:
            pass

    class FallbackUser:
        def __init__(self, uid, name):
            self.id = int(uid)
            self.display_name = name
            self.name = name
            self.mention = f"<@{uid}>"

    if not p1_user:
        p1_user = FallbackUser(author_id, req_data.get("author_name", "Player 1"))
    if not p2_user:
        p2_user = FallbackUser(target_id, req_data.get("target_name", "Player 2"))

    import sys
    gambling_mod = sys.modules.get("yuna_gambling")

    controller = PvPBattleController(
        channel=channel,
        p1_user=p1_user,
        p2_user=p2_user,
        wager_amount=0,
        client=resolved_client,
        yuna_gambling_mod=gambling_mod,
        duel_level=duel_level,
        initial_message=battle_msg
    )
    controller.interaction = interaction
    if resolved_client and hasattr(resolved_client, "add_view"):
        try:
            resolved_client.add_view(controller.view)
        except Exception:
            pass
    await controller.start()


async def start_pvp_battle(data: dict, interaction: Optional[discord.Interaction], view: Optional[View], client, yuna_gambling_mod):
    """Entry point called by gambling module when y!fight challenge is accepted."""
    if interaction and hasattr(interaction, "response") and not interaction.response.is_done():
        try:
            await interaction.response.defer()
        except Exception:
            pass

    author_id = data["author_id"]
    target_id = data["target_id"]
    amount = data.get("amount", 0)
    battle_msg = data.get("message") or getattr(interaction, "message", None)
    channel = getattr(battle_msg, "channel", None) or getattr(interaction, "channel", None) or data.get("channel")
    channel_id = data.get("channel_id")
    if not channel and channel_id and client:
        try:
            channel = client.get_channel(int(channel_id))
        except Exception:
            pass
    if not battle_msg and channel and data.get("message_id"):
        try:
            battle_msg = await channel.fetch_message(int(data["message_id"]))
        except Exception:
            pass

    # Deduct wager from both users into pot escrow
    if amount > 0:
        await yuna_gambling_mod._update_user_stats(author_id, berries_delta=-amount, is_gamble=True)
        await yuna_gambling_mod._update_user_stats(target_id, berries_delta=-amount, is_gamble=True)

    # Resolve user objects
    p1_user = None
    p2_user = None
    if client:
        try:
            p1_user = client.get_user(int(author_id))
            if not p1_user and hasattr(client, "fetch_user"):
                p1_user = await client.fetch_user(int(author_id))
        except Exception:
            pass
        try:
            p2_user = client.get_user(int(target_id))
            if not p2_user and hasattr(client, "fetch_user"):
                p2_user = await client.fetch_user(int(target_id))
        except Exception:
            pass

    class FallbackUser:
        def __init__(self, uid, name):
            self.id = int(uid)
            self.display_name = name
            self.name = name
            self.mention = f"<@{uid}>"

    if not p1_user:
        p1_user = FallbackUser(author_id, "Challenger")
    if not p2_user:
        p2_user = FallbackUser(target_id, "Opponent")

    controller = PvPBattleController(
        channel=channel,
        p1_user=p1_user,
        p2_user=p2_user,
        wager_amount=amount,
        client=client,
        yuna_gambling_mod=yuna_gambling_mod,
        duel_level=None,
        initial_message=battle_msg
    )
    controller.interaction = interaction
    if client and hasattr(client, "add_view"):
        try:
            client.add_view(controller.view)
        except Exception:
            pass
    await controller.start()


async def handle_pvp_interaction(interaction: discord.Interaction) -> bool:
    """Dispatches incoming duel_ or pvp_ component interactions."""
    custom_id = getattr(interaction.data, "get", lambda k, d=None: None)("custom_id", "") or getattr(interaction, "custom_id", "")
    if not custom_id or not (custom_id.startswith("pvp_") or custom_id.startswith("duel_")):
        return False

    # 1. Duel Request buttons
    if custom_id.startswith("duel_accept_"):
        req_id = custom_id[len("duel_accept_"):]
        req = PENDING_DUEL_REQUESTS.get(req_id)
        if not req:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ This duel request has expired or does not exist!", ephemeral=True)
            except Exception:
                pass
            return True
        view = DuelRequestView(req_id, req)
        await view.on_accept(interaction)
        return True

    elif custom_id.startswith("duel_decline_"):
        req_id = custom_id[len("duel_decline_"):]
        req = PENDING_DUEL_REQUESTS.get(req_id)
        if not req:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ This duel request has expired or does not exist!", ephemeral=True)
            except Exception:
                pass
            return True
        view = DuelRequestView(req_id, req)
        await view.on_decline(interaction)
        return True

    # 2. Active PvP Battle Controller Lookup
    user_id = str(interaction.user.id)
    controller = ACTIVE_PVP_BATTLES.get(user_id)
    if not controller or controller.ended:
        for c in list(ACTIVE_PVP_BATTLES.values()):
            if c and not c.ended and user_id in (c.p1_id, c.p2_id):
                controller = c
                break

    if not controller or controller.ended:
        chan_id = getattr(getattr(interaction, "channel", None), "id", None)
        msg_id = getattr(getattr(interaction, "message", None), "id", None)
        for c in list(ACTIVE_PVP_BATTLES.values()):
            if c and not c.ended:
                c_chan_id = getattr(getattr(c, "channel", None), "id", None)
                c_msg_id = getattr(getattr(c, "battle_message", None), "id", None)
                if (msg_id and c_msg_id and str(msg_id) == str(c_msg_id)) or (chan_id and c_chan_id and str(chan_id) == str(c_chan_id)):
                    controller = c
                    break

    if not controller or controller.ended:
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ This is not your duel! Challenge a user with `y!duel @user`.", ephemeral=True)
        except Exception:
            pass
        return True

    # Check if user is in this duel
    if user_id not in (controller.p1_id, controller.p2_id):
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ This is not your duel! Challenge a user with `y!duel @user`.", ephemeral=True)
        except Exception:
            pass
        return True

    # Handle UI navigation buttons
    if custom_id == "pvp_btn_open_skills":
        await controller.view.on_open_skills(interaction)
        return True
    elif custom_id == "pvp_btn_open_items":
        await controller.view.on_open_items(interaction)
        return True
    elif custom_id == "pvp_btn_back_skills":
        await controller.view.on_back_skills(interaction)
        return True
    elif custom_id == "pvp_btn_open_quit":
        await controller.view.on_open_quit(interaction)
        return True
    elif custom_id == "pvp_btn_confirm_quit" or custom_id.startswith("pvp_ephemeral_confirm_quit_"):
        await controller.lock_in_action(user_id, {"type": "flee"}, interaction=interaction)
        return True
    elif custom_id == "pvp_btn_cancel_quit" or custom_id.startswith("pvp_ephemeral_cancel_quit_"):
        await controller.view.on_cancel_quit(interaction)
        return True

    # Handle direct skill buttons (or lock-in)
    if custom_id.startswith("pvp_btn_sk_"):
        sk_id = custom_id[len("pvp_btn_sk_"):]
        await controller.lock_in_action(user_id, {"type": "skill", "skill_id": sk_id}, interaction=interaction)
        return True

    # Handle direct item buttons (or lock-in)
    if custom_id.startswith("pvp_btn_use_"):
        item_id = custom_id[len("pvp_btn_use_"):]
        await controller.lock_in_action(user_id, {"type": "item", "item_id": item_id}, interaction=interaction)
        return True

    # Skill and Item Select Dropdown Menus (both Ephemeral and Legacy)
    if custom_id in ("pvp_select_skill", "fishing_boss_skill_select") or custom_id.startswith("pvp_ephemeral_select_skill_"):
        vals = interaction.data.get("values", []) if hasattr(interaction, "data") and isinstance(interaction.data, dict) else []
        chosen_id = vals[0] if vals else "power_strike"
        await controller.lock_in_action(user_id, {"type": "skill", "skill_id": chosen_id}, interaction=interaction)
        return True
    elif custom_id == "pvp_select_item" or custom_id.startswith("pvp_ephemeral_select_item_"):
        vals = interaction.data.get("values", []) if hasattr(interaction, "data") and isinstance(interaction.data, dict) else []
        chosen_id = vals[0] if vals else "none"
        if chosen_id != "none":
            await controller.lock_in_action(user_id, {"type": "item", "item_id": chosen_id}, interaction=interaction)
        return True

    # Legacy Fallbacks
    if custom_id == "pvp_btn_skill":
        skills = controller.get_player_skills(user_id)
        sk_id = skills[0]["id"] if skills else "power_strike"
        await controller.lock_in_action(user_id, {"type": "skill", "skill_id": sk_id}, interaction=interaction)
        return True
    elif custom_id == "pvp_btn_item":
        await controller.view.on_open_items(interaction)
        return True
    elif custom_id == "pvp_btn_flee":
        await controller.lock_in_action(user_id, {"type": "flee"}, interaction=interaction)
        return True

    return False
