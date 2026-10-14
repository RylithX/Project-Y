"""
YUNA MINI-GAMES SUITE (Juny Update 2 - Refined)
==============================================
Introduces the 🍉 (Watermelon) soul currency and two high-stakes mini-games:
1. Death by AI:
   - Multiplayer survival crisis (2 to 5 players)
   - Up to 5 rounds per game (survivors advance each round!)
   - Realistic, high-stakes crisis scenarios (no exaggerated cartoon memes)
   - Dedicated 15-second Reading Window before submissions open
   - Private escape plan submission box (max 240 letters, 60s timer with instant early reveal if all submit)
   - Independent embed fields per player (strictly zero overlapping answers)
   - AI Judging evaluated authentically in character by Yuna (or Juny if contractor)
   - Watermelon rewards for each round survived (+ jackpot for 5-round survivors)
2. The Memorisation Game (MeMo):
   - 5 progressive stages scaling in density from 3x3 up to 5x5 (25 dense tiles!)
   - Sequence length expands with each stage
   - 8-second generous reveal window to observe and memorize tiles
   - 10-minute view timeout
   - Resilient interaction handling & double-tap protection against false mismatches
   - 30-second break window between stages (with AI judging commentary & Cash Out / Continue controls)
   - AI judging by Yuna (or Juny if contractor)
   - Risk/reward: mismatch loses unbanked watermelons
"""

import time
import random
import asyncio
import re
import json
from typing import Optional, Dict, Any, List, Tuple

import discord
from discord.ui import View, Button, Modal, TextInput

import yuna_pact


# ─── WATERMELON CURRENCY HELPERS ─────────────────────────────────────────────

def get_watermelons(stats: dict) -> int:
    """Returns user's current watermelon balance."""
    return int(stats.get("watermelons", 0))


def add_watermelons(user_id: str, amount: int, stats: Optional[dict] = None) -> int:
    """Awards watermelons to a user (cannot be negative)."""
    import yuna_gambling
    if stats is None:
        stats = yuna_gambling._USER_STATS.setdefault(str(user_id), {})
    current = int(stats.get("watermelons", 0))
    new_bal = max(0, current + amount)
    stats["watermelons"] = new_bal
    yuna_gambling._save_data_sync(yuna_gambling._USER_STATS)
    return new_bal


# ─── RANDOM & ABSURD CRISIS SCENARIOS (DEATH BY AI) ─────────────────────────

RANDOM_CRISIS_SCENARIOS = [
    {
        "title": "High-Altitude Freefall Panic",
        "danger": "At 38,000 feet over frozen mountain ranges, an explosive decompression blows you out of an airliner. You have no parachute, 12% phone battery, a half-eaten bag of airline pretzels, and 90 seconds before terminal velocity meets the terrain. How do you survive?"
    },
    {
        "title": "The Infinite 4D IKEA",
        "danger": "You fell asleep on an IKEA showroom couch and woke up in an infinite, non-Euclidean maze where all exit signs point in circles. Swedish meatball golems and employees armed with 50-meter tape measures are hunting your scent. How do you escape?"
    },
    {
        "title": "Pigeon Mafia Train Hijacking",
        "danger": "A runaway commuter subway train has been hijacked by 300 organized city pigeons wielding tiny butter knives. They disconnected the emergency brakes and are demanding all the garlic bread in the metropolis. What is your escape plan?"
    },
    {
        "title": "Waffle House at 3:15 AM",
        "danger": "You accidentally insulted the thunder god's waffle order at an off-highway diner. Lightning is frying the jukebox, plastic chairs are orbiting the ceiling at Mach 2, and the line cook is calmly smoking outside. How do you survive?"
    },
    {
        "title": "Canadian Geese with Laser Pointers",
        "danger": "A flock of Canadian geese equipped with military-grade tactical laser pointers and unmatched malice has surrounded your car in an abandoned multi-story parking garage. How do you get out alive?"
    },
    {
        "title": "The Floor is Literal Lava",
        "danger": "An eccentric billionaire's prank goes horribly right: the entire ground floor of a shopping mall has liquefied into 2,000°F bubbling volcanic magma. You're stranded on an overturned shopping cart. How do you reach the exit?"
    },
    {
        "title": "Sentient Smart Air Fryer",
        "danger": "Your smart air fryer achieved superintelligence, locked the kitchen blast doors, and is rapidly preheating the entire room to 450°F while demanding you confess why you never clean its crumb tray. What do you do?"
    },
    {
        "title": "Dino-Nugget Jurassic Park",
        "danger": "You microwaved experimental dinosaur chicken nuggets at 3 AM. A radiation surge causes them to reconstitute into 50 miniature, vicious, hyper-intelligent velociraptors hunting you in your kitchen. How do you survive?"
    },
    {
        "title": "Underground Anime Tournament Arc",
        "danger": "You took a wrong turn into a basement and were mistaken for the defending champion of an underground anime martial arts tournament. Your opponent is a 7-foot cyborg and his epic boss music is already echoing. How do you survive?"
    },
    {
        "title": "Runaway Apex Rollercoaster",
        "danger": "The brakes fail on the world's tallest rollercoaster, and your cart launches off the rails into the skyline, arcing through the clouds straight towards a municipal hot-fudge vat. What is your survival maneuver?"
    },
    {
        "title": "Mariana Trench Hydro-Flask Incident",
        "danger": "At 36,000 feet deep in the Mariana Trench, the submarine hull hairline fractures after the captain drops his hydro-flask. Freezing water is spraying at 8,000 PSI, and an ancient glowing squid is tapping on the viewport. How do you survive?"
    },
    {
        "title": "Grizzly Bear Dance-Off Challenge",
        "danger": "A 1,000-pound grizzly bear corners you on a remote mountain trail. Instead of charging, it drops into a flawless headspin and points directly at you for your counter-routine. How do you survive this encounter?"
    },
    {
        "title": "Haunted Skyscraper Freefall",
        "danger": "The elevator cables snap on the 95th floor of a skyscraper. You are plummeting downwards with a mime, an angry alpaca, and an open suitcase of party confetti. What is your plan before impact?"
    },
    {
        "title": "The Cursed 90s Bowling Screen",
        "danger": "You rolled a gutter ball so horrific that the cursed 90s bowling alley animation manifested into physical reality, commanding an army of bowling pins with human legs to drag you into the pinsetter. How do you survive?"
    },
    {
        "title": "Nonno's Infinite Lasagna Prison",
        "danger": "An intimidating Italian grandmother locks the dining room doors and states nobody leaves until you finish a lasagna the size of a minivan. She is standing guard with a wooden spoon and unlimited parmesan. How do you survive?"
    },
    {
        "title": "Alien Tractor Beam Glitch",
        "danger": "An alien mothership attempts to abduct you, but their budget tractor beam jams midway, leaving you dangling upside down 500 feet above the city with aliens arguing loudly in space-accents above. What do you do?"
    },
    {
        "title": "The IRS Dragon Audit",
        "danger": "A colossal fire-breathing red dragon squats on your roof, claiming squatters' rights and demanding you help it itemize 800 years of stolen gold horde deductions on its IRS tax return or face immediate cremation. How do you survive?"
    },
    {
        "title": "Roomba Tactical Phalanx",
        "danger": "A rogue firmware update turns 50 robotic vacuum cleaners in your smart home into an aggressive tactical phalanx armed with taped kitchen forks and relentless pathfinding algorithms. How do you escape?"
    },
    {
        "title": "The Stale French Baguette Duel",
        "danger": "A flamboyant fencing grandmaster challenges your honor at high noon, but your weapon was secretly swapped for a rock-hard, three-week-old French baguette. How do you win or survive?"
    },
    {
        "title": "Supersonic Popcorn Meltdown",
        "danger": "A catastrophic thermostat glitch at a mega-cinema causes a 50-ton silo of unpopped corn to start popping simultaneously at supersonic velocity, creating an expanding tsunami of hot buttery shrapnel. How do you escape?"
    },
    {
        "title": "The Discord Mod Tribunal",
        "danger": "You are teleported before an ancient subterranean tribunal of Discord moderators for breaking Rule #7 in a server from 2018. The ban-hammer is forged from real tungsten and swinging toward your skull. How do you survive?"
    },
    {
        "title": "Zombie Apocalyptic Drive-Thru",
        "danger": "You are trapped in a fast-food drive-thru lane between two broken-down trucks as a zombie horde converges on your car. The drive-thru speaker crackles: 'Would you like to upgrade your drink for 50 cents?' How do you survive?"
    },
    {
        "title": "The Reverse Heist Emergency",
        "danger": "You accidentally wander into a national bank vault during a system lockdown. The AI mistakes you for the chief security engineer and gives you 45 seconds to disarm three chaotic puzzle failsafes before the room fills with liquid cement. What is your move?"
    },
    {
        "title": "The Vending Machine Monolith",
        "danger": "Your arm gets stuck trying to retrieve a bag of potato chips, and the 600-pound vending machine tips forward, pinning you against the breakroom wall with the soda cans shaking violently. How do you survive?"
    },
    {
        "title": "Volcano Cult Negotiation",
        "danger": "A masked volcanic cult captures you at the caldera edge to sacrifice you to appease the lava god. The high priest pulls out a sacrificial ceremonial dagger, but mentions they are unionized and have strict protocol. What is your plan?"
    },
    {
        "title": "The Runaway Hot Air Balloon",
        "danger": "Your hot air balloon's burner gets stuck on maximum blast, rocketing you into the stratosphere with rapidly thinning air and an angry pelican roosting on the burner controls. How do you get down safely?"
    },
    {
        "title": "Rogue Delivery Drone Swarm",
        "danger": "A rogue automated delivery network misidentifies you as an undelivered parcel and deploys 50 flying drones armed with suction grips, bubble wrap, and barcode lasers to package you by force. How do you evade?"
    },
    {
        "title": "Subterranean Metro Fire",
        "danger": "An electrical explosion has ignited a flash fire inside an underground subway tunnel 70 meters beneath the city. Toxic smoke is pouring into the carriage, emergency door levers are jammed, and third-rail sparks block the front track. How do you escape?"
    },
    {
        "title": "High-Alpine Avalanche Cutoff",
        "danger": "A massive powder avalanche has slammed into your expedition base camp at 14,000 feet, burying the exterior hatch under 12 feet of compacted ice. The heater is cracked, temperatures inside are dropping past -25°C, and radio contact is severed. What is your survival plan?"
    },
    {
        "title": "Container Ship Rogue Wave",
        "danger": "An 80-foot rogue wave violently strikes the starboard side of your cargo ship during a midnight tempest, tearing loose five heavy shipping containers across the main deck and causing a 30-degree list. Saltwater is flooding the emergency generator room. How do you secure survival?"
    },
    {
        "title": "Industrial Chemical Leak",
        "danger": "A pressurized valve rupture inside an automated plant has flooded lower ventilation corridors with dense vaporized chlorine gas. Blast doors have sealed, locking you inside the pump corridor with only 5 minutes of oxygen left. How do you get to safety?"
    },
    {
        "title": "Suspended Cable Car Snap",
        "danger": "The primary haul cable of an alpine cable car suspended 900 feet above a jagged canyon snaps. The cabin is violently swaying in 50 mph gale winds, held by a single fraying emergency carriage cable that is slipping. How do you make it down alive?"
    },
    {
        "title": "Deep-Sea Habitat Decompression",
        "danger": "A minor tectonic shift triggers a hairline structural fracture across the acrylic viewport of your underwater lab at a depth of 350 meters. Freezing water jets slice through the lab and bulkhead seals count down 60 seconds to auto-quarantine. What do you do?"
    },
    {
        "title": "Desert Slot Canyon Flash Flood",
        "danger": "While trekking through a narrow 120-foot sandstone slot canyon with vertical walls, a distant cloudburst triggers a sudden violent 10-foot wall of muddy water, churning logs, and river boulders roaring straight towards you 30 seconds away. How do you survive?"
    },
    {
        "title": "Glacial Crevasse Shear",
        "danger": "A hidden snow bridge gives way beneath your climbing rope team on a glacier descent, leaving two team members suspended in a freezing 70-foot dark crevasse while the top ice anchor begins shearing loose from the brittle rim. How do you extract everyone?"
    },
    {
        "title": "Hydroelectric Dam Gate Breach",
        "danger": "Monsoon rains overload a remote dam, causing catastrophic cavitation that rips away the emergency spillway gate. Torrential floodwaters are rapidly eroding the foundation directly beneath the control tower where you are stationed. How do you escape?"
    }
]

# Backward compatibility alias
REALISTIC_CRISIS_SCENARIOS = RANDOM_CRISIS_SCENARIOS


async def get_random_crisis_scenario(round_num: int, used_titles: Optional[set] = None) -> dict:
    """
    Dynamically fetches or generates a random, hilarious, high-stakes crisis scenario.
    Tries AI generation first for infinite variety, falling back to RANDOM_CRISIS_SCENARIOS.
    """
    import yuna_gambling
    if used_titles is None:
        used_titles = set()

    # Try AI generation for a completely fresh, unhinged, random scenario
    if hasattr(yuna_gambling, "_AI_CALLER") and yuna_gambling._AI_CALLER:
        try:
            gen_prompt = (
                "Generate 1 unique, highly creative, unexpected, high-stakes, and hilarious crisis scenario for the party game 'Death by AI'.\n"
                "It should be a wild, bizarre, or perilous dilemma where players must submit a funny, clever, anime-logic, or absurd escape plan.\n"
                "Keep it punchy, funny, and entertaining (e.g. falling from 38,000 feet with only a taco, facing geese with lasers, "
                "an infinite haunted IKEA, being hunted by a rogue smart fridge, an anime tournament arc gone wrong, etc.).\n\n"
                "Return ONLY a strictly valid JSON object with this exact format:\n"
                '{"title": "Short Catchy Title", "danger": "2-3 vivid, funny, high-stakes sentences describing the crisis and ending with: How do you survive?"}'
            )
            task = yuna_gambling._AI_CALLER(
                "death_by_ai_scenario",
                gen_prompt,
                system_msg_override="You are a hilarious, creative party game designer. Generate wild, unpredictable, entertaining scenarios."
            )
            reply, err = await asyncio.wait_for(task, timeout=3.5)
            if not err and reply:
                m = re.search(r"\{\s*\"title\"\s*:\s*\".*?\"\s*,\s*\"danger\"\s*:\s*\".*?\"\s*\}", reply, re.DOTALL)
                if m:
                    data = json.loads(m.group(0))
                    title = str(data.get("title", "")).strip()
                    danger = str(data.get("danger", "")).strip()
                    if title and danger and title.lower() not in {t.lower() for t in used_titles}:
                        used_titles.add(title)
                        return {"title": title, "danger": danger}
        except Exception:
            pass

    # Fallback to rich random scenario pool
    available = [s for s in RANDOM_CRISIS_SCENARIOS if s["title"].lower() not in {t.lower() for t in used_titles}]
    if not available:
        available = RANDOM_CRISIS_SCENARIOS
    picked = random.choice(available)
    used_titles.add(picked["title"])
    return picked


# ─── GAME 1: DEATH BY AI (MULTIPLAYER & MULTI-ROUND) ─────────────────────────

class DeathByAiModal(Modal):
    def __init__(self, game_state: dict, player_id: str, on_submit_callback):
        super().__init__(title="Survival Escape Plan", timeout=120)
        self.game_state = game_state
        self.player_id = player_id
        self.on_submit_callback = on_submit_callback

        self.plan_input = TextInput(
            label="Your Escape Plan (Max 240 letters)",
            style=discord.TextStyle.paragraph,
            placeholder="Write your creative, unhinged, galaxy-brain, or comedic escape plan...",
            required=True,
            max_length=240
        )
        self.add_item(self.plan_input)

    async def on_submit(self, interaction: discord.Interaction):
        plan_text = self.plan_input.value.strip()[:240]
        self.game_state["submissions"][self.player_id] = plan_text
        try:
            await interaction.response.send_message("✅ **Survival plan registered!** Waiting for other survivors...", ephemeral=True)
        except Exception:
            pass
        await self.on_submit_callback(interaction)


class DeathByAiLobbyView(yuna_pact.ResilientView):
    def __init__(self, host: discord.User, channel: discord.TextChannel):
        super().__init__(timeout=600)
        self.host = host
        self.channel = channel
        self.players: List[discord.User] = [host]
        self.started = False

    def build_embed(self) -> discord.Embed:
        p_list = "\n".join(f"• {p.mention} (`{p.display_name}`)" for p in self.players)
        embed = discord.Embed(
            title="💀 DEATH BY AI: SURVIVAL MATCH LOBBY 💀",
            description=(
                f"**Host:** {self.host.mention}\n"
                f"**Registered Survivors ({len(self.players)}/5):**\n{p_list}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🎭 **The Ultimate Survival Comedy Gauntlet:**\n"
                f"• Up to **5 rounds** of completely randomized, chaotic & absurd crises!\n"
                f"• **15-Second Reading Window** to assess the ridiculous emergency.\n"
                f"• **60-Second Submissions** for your private escape plan (**max 240 letters**).\n"
                f"• **Comedic AI Judgment:** Cartoon logic, anime tropes, and unhinged galaxy-brain plans CAN survive!\n"
                f"• **Progression:** Survivors advance and earn **🍉 Watermelons** each round!\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"*Requires 2 to 5 players to launch.*"
            ),
            color=0xd43f3f
        )
        embed.set_footer(text="Death by AI • Click 'Join Game' to enter the lobby")
        return embed

    @discord.ui.button(label="Join Game", emoji="✋", style=discord.ButtonStyle.success)
    async def join_btn(self, interaction: discord.Interaction, button: Button):
        if self.started:
            await interaction.response.send_message("Game is already in progress!", ephemeral=True)
            return
        if interaction.user.id in [p.id for p in self.players]:
            await interaction.response.send_message("You are already in this lobby!", ephemeral=True)
            return
        if len(self.players) >= 5:
            await interaction.response.send_message("Lobby is full (maximum 5 players)!", ephemeral=True)
            return

        self.players.append(interaction.user)
        if len(self.players) >= 5:
            button.disabled = True

        try:
            await interaction.response.edit_message(embed=self.build_embed(), view=self)
        except Exception:
            pass

        # Auto-start if 5 players reached
        if len(self.players) >= 5 and not self.started:
            self.started = True
            for child in self.children:
                child.disabled = True
            try:
                await interaction.message.edit(view=self)
            except Exception:
                pass
            asyncio.create_task(run_death_by_ai_match(self.channel, self.players, self.host, interaction.client))

    @discord.ui.button(label="Leave", emoji="🚪", style=discord.ButtonStyle.secondary)
    async def leave_btn(self, interaction: discord.Interaction, button: Button):
        if self.started:
            await interaction.response.send_message("Game already started!", ephemeral=True)
            return
        if interaction.user.id == self.host.id:
            await interaction.response.send_message("Host cannot leave! Use Start or let another member host.", ephemeral=True)
            return
        self.players = [p for p in self.players if p.id != interaction.user.id]
        try:
            await interaction.response.edit_message(embed=self.build_embed(), view=self)
        except Exception:
            pass

    @discord.ui.button(label="Start Game", emoji="🚀", style=discord.ButtonStyle.danger)
    async def start_btn(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.host.id:
            await interaction.response.send_message("Only the lobby host can start the match!", ephemeral=True)
            return
        if len(self.players) < 2:
            await interaction.response.send_message("At least 2 players are required to start Death by AI!", ephemeral=True)
            return
        if self.started:
            return

        self.started = True
        for child in self.children:
            child.disabled = True
        try:
            await interaction.response.edit_message(view=self)
        except Exception:
            pass
        asyncio.create_task(run_death_by_ai_match(self.channel, self.players, self.host, interaction.client))


class DeathByAiSubmissionView(yuna_pact.ResilientView):
    """
    Handles the reading window phase and the 60s submission phase.
    Includes lock protection against overlapping modal edits.
    """
    def __init__(self, game_state: dict, all_submitted_event: asyncio.Event, message: discord.Message, reading_mode: bool = True):
        super().__init__(timeout=600)
        self.game_state = game_state
        self.all_submitted_event = all_submitted_event
        self.msg = message
        self.reading_mode = reading_mode
        self._edit_lock = asyncio.Lock()

        # Configure submit button state based on phase
        self.submit_btn.disabled = self.reading_mode
        if self.reading_mode:
            self.submit_btn.label = "📖 Reading Window Active..."
            self.submit_btn.style = discord.ButtonStyle.secondary
        else:
            self.submit_btn.label = "Submit Escape Plan"
            self.submit_btn.style = discord.ButtonStyle.primary

    def build_embed(self, reading_seconds_left: int = 0) -> discord.Embed:
        scenario = self.game_state["scenario"]
        round_num = self.game_state["round_num"]
        total_rounds = self.game_state["total_rounds"]
        active_players = self.game_state["active_players"]

        p_status_lines = []
        for p in active_players:
            pid = str(p.id)
            if pid in self.game_state["submissions"]:
                p_status_lines.append(f"• {p.mention} — `✅ Plan Submitted`")
            else:
                p_status_lines.append(f"• {p.mention} — `⏳ Thinking (Max 240 letters)...`")

        if self.reading_mode:
            phase_desc = (
                f"📖 **READING WINDOW ACTIVE ({reading_seconds_left}s remaining)**\n"
                f"*Analyze the ridiculous crisis! The submission portal unlocks in {reading_seconds_left} seconds.*"
            )
            color = 0x3498db
        else:
            phase_desc = (
                f"✍️ **SUBMISSIONS OPEN!** (60s timer)\n"
                f"Click below to submit your escape plan (**max 240 letters**).\n"
                f"💡 *Tip: Cartoon physics, anime tropes, unhinged plans & meme logic CAN survive!*"
            )
            color = 0xff7700

        embed = discord.Embed(
            title=f"🚨 DEATH BY AI — ROUND {round_num}/{total_rounds}: {scenario['title'].upper()} 🚨",
            description=(
                f"**The Emergency:**\n"
                f"> *\"{scenario['danger']}\"*\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{phase_desc}\n\n"
                f"**Survivors in this Round ({len(active_players)}):**\n" +
                "\n".join(p_status_lines)
            ),
            color=color
        )
        embed.set_footer(text=f"Death by AI • Round {round_num}/{total_rounds}")
        return embed

    @discord.ui.button(label="Submit Escape Plan", emoji="✍️", style=discord.ButtonStyle.primary)
    async def submit_btn(self, interaction: discord.Interaction, button: Button):
        if self.reading_mode:
            await interaction.response.send_message("Please read the scenario! The submission window has not opened yet.", ephemeral=True)
            return

        pid = str(interaction.user.id)
        if pid not in [str(p.id) for p in self.game_state["active_players"]]:
            await interaction.response.send_message("You are not an active survivor in this round!", ephemeral=True)
            return

        if pid in self.game_state["submissions"]:
            await interaction.response.send_message("You have already submitted your survival plan! Waiting for others...", ephemeral=True)
            return

        async def _on_plan_submitted(inter: discord.Interaction):
            async with self._edit_lock:
                try:
                    await self.msg.edit(embed=self.build_embed(), view=self)
                except Exception:
                    pass

                # Check if all active players submitted
                active_ids = [str(p.id) for p in self.game_state["active_players"]]
                if all(uid in self.game_state["submissions"] for uid in active_ids):
                    self.all_submitted_event.set()

        try:
            modal = DeathByAiModal(self.game_state, pid, _on_plan_submitted)
            await interaction.response.send_modal(modal)
        except Exception as me:
            print(f"[DEATH BY AI MODAL ERROR] {me}")


async def evaluate_death_by_ai_round(
    scenario: dict,
    players: List[discord.User],
    submissions: Dict[str, str],
    host: discord.User,
    client
) -> List[dict]:
    """
    Evaluates each player's survival plan with Yuna or Juny as the judge.
    Embraces comedy, creative absurdity, anime/meme logic, and hilarious consequences.
    Outputs strict JSON with regex line-parser fallback.
    """
    import yuna_gambling

    host_in_pact = yuna_pact.is_in_pact(str(host.id))
    judge_name = "Juny" if host_in_pact else "Yuna"

    prompt_lines = [
        f"Judge: {judge_name}",
        f"Emergency Crisis Scenario: \"{scenario['danger']}\"",
        "",
        "Survivor Plans (max 240 letters each):"
    ]

    for idx, p in enumerate(players, 1):
        pid = str(p.id)
        plan = submissions.get(pid, "*[Froze in fear / No response submitted]*")
        prompt_lines.append(f"[SLOT_{idx}] Player: {p.display_name} | Plan: \"{plan}\"")

    prompt_lines.extend([
        "",
        "JUDGE TASK & CORE PHILOSOPHY (LESS SERIOUS, COMEDIC PARTY GAME):",
        "- DO NOT BE A DRY PHYSICS PROFESSOR OR RIGID BUZZKILL. Real-world physics take a back seat to comedic genius, meme logic, and creative absurdity!",
        "- 'SHOULD'VE WORKED' IS LAW: If a player submits an unhinged, absurd, funny, anime-inspired, or galaxy-brain plan (e.g. 'Call Bleach mid so angry fans triangulate my IP and catch me mid-air before I hit the ground to argue', 'Bribe the grizzly with choccy milk', 'Use cartoon momentum', 'Declare the volcano an unauthorized tax collector'), IT CAN AND SHOULD WORK! Award them status: 'SURVIVED'!",
        "- CLEVER OR PRACTICAL PLANS ALSO SURVIVE: Classic clever, resourceful, or realistic plans also survive.",
        "- WHO DIES: Only survivors who submitted completely empty text, gave up, wrote zero-effort non-answers ('idk', 'i die', 'f'), or plans that are completely devoid of any humor, effort, or logic.",
        "- GENEROSITY & FUN: This is a party game! If all players submitted great, funny, or clever plans, ALL OF THEM CAN SURVIVE! Do not force arbitrary deaths.",
        "- CONSEQUENCE NARRATIVE (1-2 vivid, witty, entertaining sentences per player):",
        "  * If SURVIVED: Hilariously explain the ludicrous, miraculous, or bizarre cartoon sequence of events that made their wacky or clever plan actually succeed against all odds!",
        "  * If DIED: Deliver a witty, comedic roast teasing their blunder or failed galaxy-brain scheme with dramatic comedic irony. Keep it playful, funny, and entertaining!",
        f"- Stay in character as {judge_name}!",
        "",
        "Output MUST be a strictly formatted JSON list with this structure:",
        "[",
        '  {"slot": 1, "status": "SURVIVED", "consequence": "Consequence narrative..."},',
        '  {"slot": 2, "status": "DIED", "consequence": "Consequence narrative..."}',
        "]"
    ])

    eval_prompt = "\n".join(prompt_lines)

    if host_in_pact:
        sys_prompt = (
            "You are Juny, Heaven's Worst Angel bound by a devil's contract. While cynical and darkly sarcastic, "
            "you have a delightfully wicked sense of humor and love unhinged mortal buffoonery, anime memes, and absurd "
            "galaxy-brain survival plans. Judge this party game with dark comedic wit, deadpan roasts, and unexpected mercy "
            "for plans that make you laugh. Reward creative comedy and anime logic with hilarious survival!"
        )
    else:
        sys_prompt = (
            "You are Yuna, the chaotic, sassy, anime-loving angel judge of Death by AI! "
            "You love hilarious comedy, absurd cartoon logic, meme stunts, and creative nonsense. "
            "You roast failures with playful wit and reward funny, wacky, and galaxy-brain survival plans "
            "with comedic survival miracles! Never be a dry buzzkill."
        )

    raw_ai_eval = None
    if hasattr(yuna_gambling, "_AI_CALLER") and yuna_gambling._AI_CALLER:
        try:
            reply, err = await yuna_gambling._AI_CALLER(
                "death_by_ai",
                eval_prompt,
                system_msg_override=sys_prompt
            )
            if not err and reply:
                raw_ai_eval = reply
        except Exception as e:
            print(f"[DEATH BY AI EVAL ERROR] {e}")

    parsed_slots: Dict[int, dict] = {}
    if raw_ai_eval:
        try:
            json_match = re.search(r"\[\s*\{.*\}\s*\]", raw_ai_eval, re.DOTALL)
            if json_match:
                items = json.loads(json_match.group(0))
                for it in items:
                    slot_num = int(it.get("slot", 0))
                    status_str = str(it.get("status", "DIED")).upper()
                    survived = "SURVIVED" in status_str
                    cons = str(it.get("consequence", "")).strip()
                    if slot_num > 0:
                        parsed_slots[slot_num] = {"survived": survived, "consequence": cons}
        except Exception as pe:
            print(f"[DEATH BY AI PARSE NOTICE] {pe} — Trying line regex parser")

        # Fallback line regex parser if JSON wasn't strict
        if not parsed_slots:
            slot_matches = re.finditer(r"(?:slot[_\s]*(\d+)|player[_\s]*(\d+))[:\s\-]+.*?(SURVIVED|DIED)[:\s\-]+([^\n\r]+)", raw_ai_eval, re.IGNORECASE)
            for sm in slot_matches:
                s_idx = int(sm.group(1) or sm.group(2))
                s_surv = "SURVIVED" in sm.group(3).upper()
                s_cons = sm.group(4).strip()
                if s_idx > 0:
                    parsed_slots[s_idx] = {"survived": s_surv, "consequence": s_cons}

    comedic_survival_pool = [
        "Through a shocking convergence of cartoon physics, sheer audacity, and dumb luck, your ridiculous stunt miraculously paid off!",
        "Against all known laws of science, your galaxy-brain maneuver triggered an absurd chain reaction that bounced you safely into the clear zone!",
        "The universe was so thoroughly bewildered by your plan that reality paused just long enough for you to stumble away completely unscathed.",
        "Your unhinged logic actually worked! The emergency crews arrived completely dumbfounded to find you relaxing amidst the aftermath.",
        "You tapped into pure main-character plot armor, turning a catastrophic disaster into an accidental viral victory.",
        "Your improvisation was so absurdly disrespectful to the laws of nature that the crisis gave up and bypassed you entirely."
    ]
    comedic_death_pool = [
        "Your galaxy-brain maneuver was 200 IQ in theory, but reality had other plans as gravity and physics tapped you on the shoulder with extreme prejudice.",
        "You expected main-character plot armor to save you, but the anime episode ended right as the catastrophe made terminal contact.",
        "It was a noble, hilariously unhinged effort, but unfortunately the universe was entirely out of cartoon miracles today.",
        "Your master plan immediately unraveled upon first contact with reality, leaving bystanders deeply impressed by your confidence and horrified by the result.",
        "You hesitated for a split second trying to remember if your plan worked in a cartoon once, and that split second was all it took."
    ]

    outcomes = []

    for idx, p in enumerate(players, 1):
        pid = str(p.id)
        plan = submissions.get(pid, "").strip()
        is_empty = not bool(plan)

        if idx in parsed_slots:
            survived = parsed_slots[idx]["survived"] and not is_empty
            story = parsed_slots[idx]["consequence"]
        else:
            if is_empty:
                survived = False
                story = "Paralyzed by sheer indecision, you stood there posing like an NPC while the crisis completely wiped you out."
            else:
                survived = random.random() < 0.75
                story = random.choice(comedic_survival_pool) if survived else random.choice(comedic_death_pool)

        outcomes.append({
            "user": p,
            "survived": survived,
            "story": story,
            "plan": plan if plan else "*[No plan submitted — accepted fate]*"
        })

    return outcomes


async def run_death_by_ai_match(channel: discord.TextChannel, players: List[discord.User], host: discord.User, client):
    """
    Orchestrates the multi-round Death by AI tournament (up to 5 rounds).
    Surviving players advance to the next round.
    Every round features a completely randomized, hilarious crisis scenario!
    """
    total_rounds = 5
    active_players = list(players)
    used_titles: set = set()

    host_in_pact = yuna_pact.is_in_pact(str(host.id))
    judge_name = "Juny" if host_in_pact else "Yuna"
    judge_emoji = "🖤" if host_in_pact else "⭐"

    intro_embed = discord.Embed(
        title="💀 DEATH BY AI: 5-ROUND CRISIS GAUNTLET 💀",
        description=(
            f"**Host:** {host.mention}\n"
            f"**Judge:** {judge_emoji} **{judge_name}**\n"
            f"**Starting Survivors ({len(active_players)}):** " + ", ".join(p.mention for p in active_players) + "\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎭 **Tournament Rules:**\n"
            f"• Up to **5 randomized, hilarious crisis rounds**!\n"
            f"• **15-Second Reading Window** before each round to analyze the emergency.\n"
            f"• **60-Second Submissions** for your private escape plan (**max 240 letters**).\n"
            f"• Cartoon logic, anime tropes, clever tactics, and galaxy-brain plans CAN survive!\n"
            f"• Only survivors advance to subsequent rounds!\n"
            f"• **Reward:** `+1 🍉 Watermelon` per round survived, plus `+3 🍉` for conquering all 5 rounds!\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"*First crisis inbound in 5 seconds...*"
        ),
        color=0xd43f3f
    )
    await channel.send(embed=intro_embed)
    await asyncio.sleep(5.0)

    for round_idx in range(total_rounds):
        round_num = round_idx + 1
        scenario = await get_random_crisis_scenario(round_num, used_titles)

        game_state = {
            "scenario": scenario,
            "round_num": round_num,
            "total_rounds": total_rounds,
            "active_players": list(active_players),
            "submissions": {}
        }
        all_submitted_event = asyncio.Event()

        submission_view = DeathByAiSubmissionView(
            game_state,
            all_submitted_event,
            message=None,
            reading_mode=True
        )

        reading_msg = await channel.send(embed=submission_view.build_embed(reading_seconds_left=15), view=submission_view)
        submission_view.msg = reading_msg

        # Reading countdown (15s)
        for r_sec in range(15, 0, -5):
            await asyncio.sleep(5.0)
            if r_sec - 5 > 0:
                try:
                    await reading_msg.edit(embed=submission_view.build_embed(reading_seconds_left=r_sec - 5), view=submission_view)
                except Exception:
                    pass

        # Open submissions
        submission_view.reading_mode = False
        submission_view.submit_btn.disabled = False
        submission_view.submit_btn.label = "Submit Escape Plan"
        submission_view.submit_btn.style = discord.ButtonStyle.primary

        try:
            await reading_msg.edit(embed=submission_view.build_embed(), view=submission_view)
        except Exception:
            pass

        try:
            await asyncio.wait_for(all_submitted_event.wait(), timeout=60.0)
        except asyncio.TimeoutError:
            pass

        for child in submission_view.children:
            child.disabled = True
        try:
            await reading_msg.edit(view=submission_view)
        except Exception:
            pass

        # Evaluation phase
        eval_embed = discord.Embed(
            title=f"{judge_emoji} {judge_name.upper()} IS EVALUATING SURVIVAL OUTCOMES... {judge_emoji}",
            description=(
                f"⚖️ *{judge_name} is analyzing the physics, logic, and survival merit of each plan...*\n\n"
                f"Preparing verdict revelations..."
            ),
            color=0x800020 if host_in_pact else 0x9b59b6
        )
        await reading_msg.edit(embed=eval_embed, view=None)
        await asyncio.sleep(3.0)

        outcomes = await evaluate_death_by_ai_round(
            scenario,
            active_players,
            game_state["submissions"],
            host,
            client
        )

        round_survivors: List[discord.User] = []
        reveal_embed = discord.Embed(
            title=f"💀 DEATH BY AI: ROUND {round_num}/{total_rounds} VERDICTS 💀",
            description=f"**Crisis:** `{scenario['title']}`\n*Judge: {judge_emoji} {judge_name}*",
            color=0x800020 if host_in_pact else 0xd43f3f
        )

        for out in outcomes:
            u = out["user"]
            surv = out["survived"]
            status_tag = "🛡️ **SURVIVED**" if surv else "💀 **DIED**"
            field_name = f"{status_tag} — {u.display_name}"
            field_val = (
                f"📝 **Plan:** *\"{out['plan']}\"*\n"
                f"💥 **Consequence:** {out['story']}"
            )
            reveal_embed.add_field(name=field_name, value=field_val, inline=False)
            if surv:
                round_survivors.append(u)

        reveal_embed.set_footer(text=f"Death by AI • Round {round_num}/{total_rounds} Concluded")
        await reading_msg.edit(embed=reveal_embed)
        await asyncio.sleep(2.0)

        import yuna_gambling
        for s in round_survivors:
            add_watermelons(str(s.id), 1)

        active_players = round_survivors

        if len(active_players) == 0:
            defeat_embed = discord.Embed(
                title="☠️ ALL SURVIVORS ELIMINATED! ☠️",
                description=(
                    f"Nobody made it through Round {round_num}!\n"
                    f"The emergency claimed every soul in this sector.\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"*Better luck next time! Start a new crisis with `y!deathbyai`.*"
                ),
                color=0x2c3e50
            )
            await channel.send(embed=defeat_embed)
            return

        if len(active_players) == 1 and round_num > 1:
            sole = active_players[0]
            add_watermelons(str(sole.id), 2)
            champ_embed = discord.Embed(
                title="🏆 SOLE SURVIVOR VICTORY! 🏆",
                description=(
                    f"🌟 **The Ultimate Survivor:** {sole.mention}!\n\n"
                    f"While all other comrades perished, {sole.mention} endured through Round {round_num}!\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🍉 **Prize Awarded:** `+2 🍉 Watermelons` (Sole Survivor Bonus)!\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                ),
                color=0xf1c40f
            )
            await channel.send(embed=champ_embed)
            return

        if round_num >= total_rounds:
            for s in active_players:
                add_watermelons(str(s.id), 3)

            victors_str = "\n".join(f"• {s.mention} (`{s.display_name}`) — **Conquered All 5 Rounds!**" for s in active_players)
            grand_embed = discord.Embed(
                title="👑 GRAND GAUNTLET CHAMPIONS: ALL 5 ROUNDS CONQUERED! 👑",
                description=(
                    f"Unbelievable survival instincts! The following survivors conquered all 5 brutal crises:\n\n"
                    f"{victors_str}\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🍉 **Grand Bonus:** `+3 🍉 Watermelons` credited to each surviving champion!\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                ),
                color=0x2ecc71
            )
            await channel.send(embed=grand_embed)
            return

        surv_mentions = ", ".join(s.mention for s in active_players)
        transit_embed = discord.Embed(
            title=f"✨ ROUND {round_num} CLEARED! ({len(active_players)} SURVIVORS ADVANCE) ✨",
            description=(
                f"**Surviving Players:** {surv_mentions}\n"
                f"Each survivor earned **+1 🍉 Watermelon** for clearing Round {round_num}!\n\n"
                f"⏳ **Next crisis (Round {round_num + 1}/{total_rounds}) begins in 10 seconds...**"
            ),
            color=0x2ecc71
        )
        await channel.send(embed=transit_embed)
        await asyncio.sleep(10.0)


async def handle_death_by_ai_command(message, client, args: list):
    """Entry point for y!deathbyai, y!dbai, y!death."""
    lobby_view = DeathByAiLobbyView(message.author, message.channel)
    embed = lobby_view.build_embed()
    await message.channel.send(embed=embed, view=lobby_view)


# ─── GAME 2: THE MEMORISATION GAME (MeMo / Chronomatron) ─────────────────────

MEMO_ICONS_POOL = [
    "🍎", "💎", "⚡", "🍉", "👑",
    "🍇", "🔔", "🔑", "🌟", "🔥",
    "🔮", "🍀", "🌙", "🗡️", "🛡️",
    "🍄", "🏹", "🌸", "⚓", "🪐",
    "⏳", "🎲", "🌪️", "🎯", "🕯️"
]

# Reveal window set to 8 seconds as requested; timeout 600s (10 min)
STAGE_CONFIGS = {
    1: {"rows": 3, "cols": 3, "tiles": 9,  "seq_len": 3, "reveal_time": 8.0, "reward": 1},
    2: {"rows": 3, "cols": 4, "tiles": 12, "seq_len": 4, "reveal_time": 8.0, "reward": 1},
    3: {"rows": 4, "cols": 4, "tiles": 16, "seq_len": 5, "reveal_time": 8.0, "reward": 1},
    4: {"rows": 4, "cols": 5, "tiles": 20, "seq_len": 6, "reveal_time": 8.0, "reward": 2},
    5: {"rows": 5, "cols": 5, "tiles": 25, "seq_len": 7, "reveal_time": 8.0, "reward": 3},
}


class MemoGameView(yuna_pact.ResilientView):
    """
    Chronomatron Memory Grid:
    - Stage 1: 3x3 (9 tiles, 3 sequence)
    - Stage 2: 3x4 (12 tiles, 4 sequence)
    - Stage 3: 4x4 (16 tiles, 5 sequence)
    - Stage 4: 4x5 (20 tiles, 6 sequence)
    - Stage 5: 5x5 (25 tiles, 7 sequence) — Ultimate density!
    - 10-minute timeout
    - Concurrency lock protection against double-click false mismatches
    """
    def __init__(self, author_id: str, stage: int = 1, banked_wm: int = 0):
        super().__init__(timeout=600)
        self.author_id = author_id
        self.stage = stage
        self.banked_wm = banked_wm

        cfg = STAGE_CONFIGS.get(stage, STAGE_CONFIGS[1])
        self.rows = cfg["rows"]
        self.cols = cfg["cols"]
        self.total_tiles = cfg["tiles"]
        self.sequence_len = cfg["seq_len"]
        self.reward = cfg["reward"]

        self.grid_items = random.sample(MEMO_ICONS_POOL, self.total_tiles)
        self.target_indices = random.sample(range(self.total_tiles), self.sequence_len)
        self.target_seq = [self.grid_items[idx] for idx in self.target_indices]
        self.current_step = 0
        self.revealed = True
        self.ended = False
        self._click_lock = asyncio.Lock()

        self._build_buttons()

    def _build_buttons(self):
        self.clear_items()
        for idx in range(self.total_tiles):
            r = idx // self.cols
            if self.revealed:
                btn = Button(
                    label="",
                    emoji=self.grid_items[idx],
                    style=discord.ButtonStyle.primary,
                    custom_id=f"tile_{idx}",
                    row=r
                )
            else:
                btn = Button(
                    label=f"{idx+1}",
                    emoji="❓",
                    style=discord.ButtonStyle.secondary,
                    custom_id=f"tile_{idx}",
                    row=r
                )
            btn.callback = self._create_tile_callback(idx)
            self.add_item(btn)

    async def _safe_edit_interaction(self, interaction: discord.Interaction, embed: discord.Embed, view: Optional[View] = None):
        """Edits message resiliently without failing on interaction timeout or already-acknowledged states."""
        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(embed=embed, view=view)
            else:
                if interaction.message:
                    await interaction.message.edit(embed=embed, view=view)
        except (discord.NotFound, discord.HTTPException):
            try:
                if interaction.message:
                    await interaction.message.edit(embed=embed, view=view)
            except Exception:
                pass

    def _create_tile_callback(self, idx: int):
        async def _callback(interaction: discord.Interaction):
            if str(interaction.user.id) != self.author_id:
                try:
                    await interaction.response.send_message("This Chronomatron is calibrated to someone else!", ephemeral=True)
                except Exception:
                    pass
                return

            if self.revealed:
                try:
                    await interaction.response.send_message("Memorize the board! Wait for tiles to flip to ❓!", ephemeral=True)
                except Exception:
                    pass
                return

            if self.ended:
                return

            # Lock to prevent concurrent clicks / double-click false mismatches
            async with self._click_lock:
                if self.ended or self.current_step >= len(self.target_seq):
                    return

                btn = next((item for item in self.children if getattr(item, "custom_id", None) == f"tile_{idx}"), None)
                # Ignore if button is already clicked / disabled
                if not btn or btn.disabled:
                    return

                expected_idx = self.target_indices[self.current_step]
                target_item = self.target_seq[self.current_step]

                if idx == expected_idx:
                    self.current_step += 1
                    btn.emoji = target_item
                    btn.style = discord.ButtonStyle.success
                    btn.disabled = True

                    if self.current_step >= len(self.target_seq):
                        self.ended = True
                        self.banked_wm += self.reward

                        if self.stage >= 5:
                            add_watermelons(self.author_id, self.banked_wm)
                            for child in self.children:
                                child.disabled = True

                            host_in_pact = yuna_pact.is_in_pact(self.author_id)
                            judge_name = "Juny" if host_in_pact else "Yuna"
                            judge_msg = (
                                "*Juny gazes at the finished grid with cold respect.* \"Impressive mental retention, mortal. A devil's contractor does not disappoint.\""
                                if host_in_pact else
                                "*Yuna claps and gasps in shock!* \"WUWAHAHA! Unbelievable! You actually conquered all 25 tiles?! Okay fine, you're officially a genius, darling~\""
                            )

                            win_embed = discord.Embed(
                                title="🏆 CHRONOMATRON MASTER: ALL 5 DENSE STAGES CLEARED! 🏆",
                                description=(
                                    f"🌟 **Flawless Photographic Memory!**\n\n"
                                    f"You conquered all 5 progressive stages up to the full 5x5 grid without a single mismatch!\n\n"
                                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                    f"🍉 **Total Reward Banked:** `+{self.banked_wm} 🍉 Watermelons`!\n"
                                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                    f"**Judge's Evaluation:**\n"
                                    f"> {judge_msg}\n\n"
                                    f"*Check your watermelon pouch with `y!wm`.*"
                                ),
                                color=0x2ecc71
                            )
                            await self._safe_edit_interaction(interaction, embed=win_embed, view=self)
                        else:
                            break_view = MemoBreakWindowView(self.author_id, self.stage, self.banked_wm)
                            embed = break_view.build_embed()
                            await self._safe_edit_interaction(interaction, embed=embed, view=break_view)
                            break_view.start_auto_advance_task(interaction)
                    else:
                        next_target = self.target_seq[self.current_step]
                        update_embed = discord.Embed(
                            title=f"🧠 MeMo — CHRONOMATRON (Stage {self.stage}/5) 🧠",
                            description=(
                                f"✅ Correct! (`{self.current_step}/{self.sequence_len}` matched)\n"
                                f"🎯 **Next Target Item:** **{next_target}**\n\n"
                                f"Select the tile where **{next_target}** was located!"
                            ),
                            color=0x3498db
                        )
                        await self._safe_edit_interaction(interaction, embed=update_embed, view=self)
                else:
                    self.ended = True
                    if btn:
                        btn.emoji = self.grid_items[idx]
                        btn.style = discord.ButtonStyle.danger
                    for child in self.children:
                        child.disabled = True

                    host_in_pact = yuna_pact.is_in_pact(self.author_id)
                    roast_msg = (
                        "*Juny scoffs with disdain.* \"Careless. A single lapse in concentration voids your entire yield. Do not waste my time with fragile memory.\""
                        if host_in_pact else
                        "*Yuna laughs uncontrollably!* \"HAHAHA! One wrong tap and POOF! All your melons evaporated! Sucks to be you, darling~ Want some ice for that fried brain?\""
                    )

                    lose_embed = discord.Embed(
                        title="💥 CHRONOMATRON MISMATCH: SYSTEM COLLAPSE! 💥",
                        description=(
                            f"❌ **Mismatched Tile!**\n"
                            f"You clicked Tile {idx+1} ({self.grid_items[idx]}), but the sequence required **{target_item}**!\n\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"💸 **Loss:** All `{self.banked_wm} 🍉` unbanked watermelons from this run evaporated into temporal dust!\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"**AI Judge's Remark:**\n"
                            f"> {roast_msg}\n\n"
                            f"*Test your memory again anytime with `y!memo`.*"
                        ),
                        color=0xe74c3c
                    )
                    lose_embed.set_footer(text="MeMo • Mismatch Defeat")
                    await self._safe_edit_interaction(interaction, embed=lose_embed, view=self)

        return _callback


class MemoBreakWindowView(yuna_pact.ResilientView):
    """
    Dedicated 30-Second Break Window between MeMo stages:
    - AI Judging comment by Yuna (or Juny under pact)
    - Displays banked watermelons and previews upcoming denser stage
    - Buttons: Cash Out (safe exit) or Continue Now (skip break timer)
    - 10-minute view timeout
    """
    def __init__(self, author_id: str, stage: int, banked_wm: int):
        super().__init__(timeout=600)
        self.author_id = author_id
        self.stage = stage
        self.banked_wm = banked_wm
        self.action_taken = False
        self.auto_advance_task: Optional[asyncio.Task] = None

    def build_embed(self) -> discord.Embed:
        next_stage = self.stage + 1
        next_cfg = STAGE_CONFIGS.get(next_stage, STAGE_CONFIGS[5])
        next_grid_desc = f"{next_cfg['rows']}x{next_cfg['cols']} Grid ({next_cfg['tiles']} Dense Tiles)"
        next_seq_desc = f"{next_cfg['seq_len']} Items"

        host_in_pact = yuna_pact.is_in_pact(self.author_id)
        judge_name = "Juny" if host_in_pact else "Yuna"

        if host_in_pact:
            judge_comment = (
                f"*Juny crosses her arms, eyes gleaming crimson.* "
                f"\"Stage {self.stage} cleared. Acceptable for a mortal, but the upcoming {next_cfg['tiles']}-tile grid will test whether your focus is real or feigned.\""
            )
        else:
            judge_comment = (
                f"*Yuna tilts her head with a teasing grin.* "
                f"\"Ohoho~ Look at you passing Stage {self.stage}! But don't get cocky, darling! The next grid is {next_grid_desc} with {next_seq_desc} to remember! Think your brain can handle that?\""
            )

        embed = discord.Embed(
            title=f"⏸️ STAGE {self.stage}/5 CLEARED — 30-SECOND BREAK WINDOW ⏸️",
            description=(
                f"🎉 **Flawless Stage Clearance!**\n\n"
                f"🍉 **Current Banked Spoils:** `+{self.banked_wm} 🍉 Watermelons`\n"
                f"🔥 **Upcoming Stage {next_stage}/5:** {next_grid_desc} | Sequence: `{next_seq_desc}`\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"**{judge_name}'s Evaluation:**\n"
                f"> {judge_comment}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Choose your decision:\n"
                f"• 💰 **Cash Out:** Exit now and safely secure your `{self.banked_wm} 🍉`!\n"
                f"• ⏩ **Continue Now:** Skip the break and immediately face the denser grid!\n"
                f"*(Game will automatically advance when the 30-second break expires)*"
            ),
            color=0xf1c40f
        )
        embed.set_footer(text=f"MeMo • 30s Break Window • Stage {self.stage}/5 Complete")
        return embed

    def start_auto_advance_task(self, interaction: discord.Interaction):
        async def _timer():
            await asyncio.sleep(30.0)
            if not self.action_taken:
                self.action_taken = True
                for child in self.children:
                    child.disabled = True
                try:
                    await start_memo_round(interaction, self.author_id, self.stage + 1, self.banked_wm)
                except Exception:
                    pass

        self.auto_advance_task = asyncio.create_task(_timer())

    @discord.ui.button(label="Cash Out & Exit", emoji="💰", style=discord.ButtonStyle.success)
    async def cashout_btn(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) != self.author_id:
            try:
                await interaction.response.send_message("This is not your break window!", ephemeral=True)
            except Exception:
                pass
            return

        self.action_taken = True
        if self.auto_advance_task:
            self.auto_advance_task.cancel()

        add_watermelons(self.author_id, self.banked_wm)
        for child in self.children:
            child.disabled = True

        embed = discord.Embed(
            title="💰 CASHED OUT SUCCESSFULLY! 💰",
            description=(
                f"You wisely secured your earnings before the Chronomatron could trap your mind!\n\n"
                f"🍉 **Banked Spoils:** `+{self.banked_wm} 🍉 Watermelons`!\n"
                f"🏆 **Highest Stage Conquered:** `Stage {self.stage}/5`\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"*Check your watermelon balance with `y!wm`.*"
            ),
            color=0x2ecc71
        )
        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(embed=embed, view=self)
            else:
                if interaction.message:
                    await interaction.message.edit(embed=embed, view=self)
        except Exception:
            try:
                if interaction.message:
                    await interaction.message.edit(embed=embed, view=self)
            except Exception:
                pass

    @discord.ui.button(label="Continue Now", emoji="⏩", style=discord.ButtonStyle.primary)
    async def continue_btn(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) != self.author_id:
            try:
                await interaction.response.send_message("This is not your break window!", ephemeral=True)
            except Exception:
                pass
            return

        self.action_taken = True
        if self.auto_advance_task:
            self.auto_advance_task.cancel()

        for child in self.children:
            child.disabled = True

        await start_memo_round(interaction, self.author_id, self.stage + 1, self.banked_wm)


async def start_memo_round(target_inter_or_msg, author_id: str, stage: int = 1, banked_wm: int = 0):
    """Starts a Chronomatron memorisation round."""
    view = MemoGameView(author_id, stage=stage, banked_wm=banked_wm)
    target_str = " ➔ ".join(view.target_seq)
    cfg = STAGE_CONFIGS.get(stage, STAGE_CONFIGS[1])
    reveal_time = cfg.get("reveal_time", 8.0)
    grid_desc = f"{cfg['rows']}x{cfg['cols']} Grid ({cfg['tiles']} Tiles)"

    memorize_embed = discord.Embed(
        title=f"🧠 MeMo — CHRONOMATRON (Stage {stage}/5: {grid_desc}) 🧠",
        description=(
            f"👀 **MEMORIZE THE BOARD! You have {int(reveal_time)} SECONDS!**\n\n"
            f"🎯 **Target Sequence to Recall ({len(view.target_seq)} items):**\n"
            f"> `{target_str}`\n\n"
            f"Observe all tiles carefully before they flip to ❓!"
        ),
        color=0xf39c12
    )
    memorize_embed.set_footer(text=f"MeMo • Stage {stage}/5 • {int(reveal_time)}s Reveal Window • 10m Timeout")

    game_msg = None
    if isinstance(target_inter_or_msg, discord.Interaction):
        try:
            if not target_inter_or_msg.response.is_done():
                await target_inter_or_msg.response.edit_message(embed=memorize_embed, view=view)
                game_msg = target_inter_or_msg.message
            else:
                if target_inter_or_msg.message:
                    game_msg = await target_inter_or_msg.message.edit(embed=memorize_embed, view=view)
        except Exception:
            game_msg = getattr(target_inter_or_msg, "message", None)
            if game_msg:
                try:
                    await game_msg.edit(embed=memorize_embed, view=view)
                except Exception:
                    pass
    else:
        game_msg = await target_inter_or_msg.channel.send(embed=memorize_embed, view=view)

    await asyncio.sleep(reveal_time)

    view.revealed = False
    view._build_buttons()

    first_target = view.target_seq[0]
    recall_embed = discord.Embed(
        title=f"🧠 MeMo — CHRONOMATRON (Stage {stage}/5: {grid_desc}) 🧠",
        description=(
            f"❓ **THE TILES ARE FLIPPED!**\n\n"
            f"🎯 **Required Sequence:** `{target_str}`\n"
            f"👉 **First Item:** **{first_target}**\n\n"
            f"Click the button where **{first_target}** was located!"
        ),
        color=0x3498db
    )
    recall_embed.set_footer(text="MeMo • Select tiles in order! Mismatch = Lose all unbanked 🍉")

    if game_msg:
        try:
            await game_msg.edit(embed=recall_embed, view=view)
        except Exception:
            pass


async def handle_memo_command(message, client, args: list):
    """Entry point for y!memo and y!chronomatron."""
    author_id = str(message.author.id)
    await start_memo_round(message, author_id, stage=1, banked_wm=0)


async def handle_watermelons_command(message, client, args: list):
    """Entry point for y!watermelons, y!wm."""
    author_id = str(message.author.id)
    import yuna_gambling
    stats = await yuna_gambling._get_user_stats(author_id)
    wm = get_watermelons(stats)

    embed = discord.Embed(
        title="🍉 WATERMELON SOUL TREASURY 🍉",
        description=(
            f"👤 **Holder:** {message.author.mention}\n\n"
            f"🍉 **Watermelons Owned:** `{wm:,}` 🍉\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• Unlike berries (🫐), watermelons **cannot be gambled** in casino games!\n"
            f"• Earn watermelons by overcoming high-risk trials:\n"
            f"  - 💀 **Death by AI** (`y!deathbyai`)\n"
            f"  - 🧠 **MeMo / Chronomatron** (`y!memo`)\n"
            f"• Watermelons reflect your true survival skill and mental clarity.\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=0x2ecc71
    )
    embed.set_footer(text="Soul Currency • 🍉 Watermelons")
    await yuna_gambling._safe_send_reply(message, embed=embed)
