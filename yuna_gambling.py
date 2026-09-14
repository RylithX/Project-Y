#!/usr/bin/env python3
"""
Yuna Gambling, Morality & Social Codex
--------------------------------------
Prefix-based commands (y!) for Yuna.
Tracks 🫐 Berries (currency), 💖 Virtue, and ❤️🔥 Sin.

Features:
  - Economy: y!balance, y!give, y!donate, y!leaderboard
  - Morality: y!aid, y!steal
  - Games: y!blackjack (y!bj, y!hit, y!stand), y!crash (y!cashout)
  - Social: y!bet, y!fight, y!dare, y!trade, y!gift, y!marry, y!divorce
  - Meta: y!achievements (y!ach), y!accept, y!decline, y!help
"""

import os
import sys
import re
import json
import time
import random
import asyncio
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

import discord
from discord.ui import View, Button, Select, UserSelect, Modal, TextInput

try:
    import fcntl
    FCNTL_AVAILABLE = True
except ImportError:
    fcntl = None
    FCNTL_AVAILABLE = False

try:
    import yuna_rpc
    YUNA_RPC_AVAILABLE = True
except Exception:
    yuna_rpc = None
    YUNA_RPC_AVAILABLE = False

try:
    import yuna_rpg
    YUNA_RPG_AVAILABLE = True
except Exception as _rpg_err:
    print(f"[YUNA RPG IMPORT NOTE] {_rpg_err}")
    yuna_rpg = None
    YUNA_RPG_AVAILABLE = False

SCRIPT_DIR = Path(__file__).parent.resolve()
DATA_DIR = SCRIPT_DIR / "data"
GAMBLING_DATA_FILE = DATA_DIR / "yuna_gambling.json"
AUDIT_LOG_FILE = DATA_DIR / "player_stats_audit.log"
BACKUPS_DIR = DATA_DIR / "backups"
LOCK_FILE_PATH = Path("/data/data/com.termux/files/home/.yuna_gambling.lock")
YUNA_USER_ID = "yuna"

def _log_player_stat_audit(user_id: str, field: str, old_val: Any, new_val: Any, reason: str = ""):
    """Appends persistent audit log entry for user stat changes."""
    try:
        AUDIT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        now_str = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        line = f"[{now_str}] User: {user_id} | Field: {field} | {old_val} -> {new_val} | Reason: {reason}\n"
        with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


# In-memory caches and locks
_USER_STATS: Dict[str, Dict[str, Any]] = {}
_JOINT_VAULTS: Dict[str, dict] = {}           # pair_key -> joint vault data
_USER_SNAPSHOTS: Dict[str, str] = {}          # user_id -> json string representation at last load/save
_VAULT_SNAPSHOTS: Dict[str, str] = {}         # vkey -> json string representation at last load/save
_DARE_SNAPSHOTS: Dict[str, str] = {}          # target_id -> json string representation at last load/save
_LAST_FILE_MTIME: float = 0.0
_DATA_LOADED = False
_LOCK = asyncio.Lock()
_LAST_AID_TIME: Dict[str, float] = {}
_LAST_DOUBLE_AID_TIME: Dict[str, float] = {}  # user_id -> last double aid timestamp
_LAST_STEAL_TIME: Dict[str, float] = {}
_LAST_DOUBLE_STEAL_TIME: Dict[str, float] = {} # user_id -> last double steal timestamp
_LAST_WORK_TIME: Dict[str, float] = {}         # user_id -> last work timestamp
_LAST_CRIME_TIME: Dict[str, float] = {}        # user_id -> last crime timestamp
_LAST_FISH_TIME: Dict[str, float] = {}         # user_id -> last fish timestamp
_LAST_DATE_TIME: Dict[str, float] = {}         # user_id -> last romantic date timestamp
_LAST_KISS_TIME: Dict[str, float] = {}         # user_id -> last kiss timestamp
_ACTIVE_BLACKJACK_GAMES: Dict[str, dict] = {} # user_id -> game state
_ACTIVE_CRASH_GAMES: Dict[str, dict] = {}     # user_id -> game state
_ACTIVE_HL_GAMES: Dict[str, dict] = {}        # user_id -> higher/lower game state
_ACTIVE_POKER_GAMES: Dict[str, dict] = {}     # user_id -> poker game state
_ACTIVE_MINES_GAMES: Dict[str, dict] = {}     # user_id -> mines game state
_ACTIVE_WORDLE_GAMES: Dict[str, dict] = {}    # user_id -> wordle game state
_ACTIVE_DARES: Dict[str, dict] = {}           # user_id -> active dare state
_PENDING_CHALLENGES: Dict[str, dict] = {}     # challenge_id -> challenge state
_AI_CALLER: Optional[Any] = None              # AI callback function (ask_ai)
_CONTEXT_LOGGER: Optional[Any] = None         # Channel context logger for Yuna AI

# Cooldowns (in seconds)
AID_COOLDOWN_SECONDS = 5.0
DOUBLE_AID_COOLDOWN_SECONDS = 10.0
STEAL_COOLDOWN_SECONDS = 15.0
DOUBLE_STEAL_COOLDOWN_SECONDS = 15.0
WORK_COOLDOWN_SECONDS = 180.0     # 3 minutes
CRIME_COOLDOWN_SECONDS = 240.0    # 4 minutes
FISH_COOLDOWN_SECONDS = 60.0      # 1 minute
DATE_COOLDOWN_SECONDS = 300.0     # 5 minutes
KISS_COOLDOWN_SECONDS = 30.0      # 30 seconds

# ─── SCENARIO & FLAVOR COLLECTIONS ──────────────────────────────────────────

SUCCESS_SCENARIOS = [
    "You saw {user} trip on their feet, you walked over and gave them a hand, and they thanked you.",
    "You saw {user} struggling to open a stubborn pickle jar. You gave it a solid twist, the lid popped off, and they beamed with gratitude.",
    "You noticed {user} dropped their transit pass while sprinting for the bus. You dashed like an Olympian and handed it back before the doors closed.",
    "You saw {user} about to step on a dangerously sharp LEGO brick. You kicked it away just in time, sparing their soul from agony.",
    "You spotted {user} trying to reach the top shelf at the grocery store. You politely retrieved the box for them, earning a grateful bow.",
    "You saw {user} wrestling with a tangled nightmare of wired earphones. You sat down and patiently untangled every single knot.",
    "You caught {user}'s umbrella just as a violent gust of wind tried to flip it inside out. They smiled warmly and thanked you.",
    "You saw {user} studying desperately with droopy eyes. You slid a warm freshly brewed tea onto their desk, and they looked at you like an angel.",
    "You noticed {user}'s shoelaces were untied. You gave them a quick heads-up before they faceplanted into the sidewalk.",
    "You saw {user} pushing a door marked 'PULL'. You pointed to the sign with a reassuring smile, saving them from social ruin.",
    "You spotted {user} sneezing five times in a row. You handed them a pocket tissue, and they whispered a relieved 'bless you'.",
    "You noticed {user} forgot their coffee on the counter. You jogged over and delivered it warm right into their hands.",
    "You saw {user} getting circled by an overly excited stray puppy. You gently lured the pup away with a treat so {user} could make their train.",
    "You found {user}'s missing car keys hidden underneath a park bench and returned them before full panic took hold.",
    "You shielded {user} with your coat when a reckless delivery scooter splashed puddle water across the crosswalk.",
    "You helped {user} carry an absurdly heavy stack of parcels all the way up to their apartment door.",
    "You noticed {user} left their phone on the cafe table. You grabbed it and sprinted outside to catch them before they crossed the street.",
    "You helped {user} find their lost cat hiding under a parked truck, gently coaxing it out with tuna.",
    "You saw {user} struggling to fold a massive road map in the wind. You helped them fold it back into crisp neat corners.",
    "You saw {user} about to drink iced tea with a bee hovering inches from the straw. You swatted the bee away like a bodyguard.",
    "You caught {user}'s slipping grocery bag right before twelve fresh eggs hit the concrete pavement.",
    "You saw {user} looking completely lost in an unfamiliar station. You guided them directly to their platform with cheerful directions.",
    "You helped {user} push their bicycle with a flat tire all the way to the neighborhood repair shop.",
    "You saw {user} drop a handful of coins that rolled everywhere. You knelt down and helped retrieve every single coin.",
    "You spotted {user} having a nightmare on the park bench. You softly woke them up and offered a kind bottle of water."
]

MESS_UP_SCENARIOS = [
    (
        "You saw {user} beating up a stranger who look liked a thief, so you join in and beat the thief up together.",
        "they were shooting a film, you realise you just beat the shit out of a random stranger for no reason, you tiptoe your way home"
    ),
    (
        "You saw thick grey smoke pouring out of {user}'s bedroom window and heroically kicked down the front door with a fire extinguisher.",
        "it wasn't a fire, {user} was just burning aroma sage to cleanse bad vibes. Their room is now coated in 15 pounds of toxic white extinguisher powder."
    ),
    (
        "You saw {user} getting aggressively chased down the block by a big dog, so you bravely tackled the beast into a hedge.",
        "it was an emotional support golden retriever trying to bring {user} their dropped slipper. The whole neighborhood watched you suplex a therapy dog."
    ),
    (
        "You saw {user} looking faint and dehydrated on a hot afternoon, so you grabbed a bucket of ice water and dumped it over their head.",
        "{user} was holding an open $3,000 MacBook Pro. It made a loud sizzle, popped twice, and passed away forever."
    ),
    (
        "You saw a suspicious hooded figure creeping silently behind {user} in an alleyway and dropped them with a flying kick.",
        "it was {user}'s younger sibling in a superhero hoodie on their way home from a birthday party. You just punted a middle schooler into a recycling bin."
    ),
    (
        "You saw {user} struggling to push a vintage car uphill and threw your entire body weight into shoving it from behind.",
        "the handbrake was actually working until you pushed. The car snapped free, rolled downhill in reverse, and flattened a neighbor's mailbox."
    ),
    (
        "You saw {user} coughing violently at dinner and performed an aggressive airborne Heimlich maneuver from behind.",
        "{user} wasn't choking, they were beatboxing. You cracked two of their ribs and launched a roasted potato into the restaurant ceiling fan."
    ),
    (
        "You saw a hornet buzzing near {user}'s ear and swung a hardcover encyclopedia to swat it out of existence.",
        "the hornet flew away laughing. The encyclopedia struck {user} directly across the temple, knocking them out cold onto the carpet."
    ),
    (
        "You saw {user} locked out of their apartment and offered to pick the front door lock using a bent paperclip.",
        "the paperclip snapped deep inside the lock mechanism, jamming the deadbolt permanently. The emergency locksmith charged {user} $400."
    ),
    (
        "You noticed {user} left a backpack on a bench, so you snatched it and ran three blocks to return it to them.",
        "that was not {user}'s backpack. Campus security is now reviewing footage of you sprinting away with a stranger's luggage."
    ),
    (
        "You saw {user} waving their hands frantically at an intersection, so you threw yourself into oncoming traffic to stop cars.",
        "{user} was just stretching after a workout. The angry sports car driver stepped out holding a tire iron demanding your details."
    ),
    (
        "You saw {user} having trouble untying a heavy knot on their boat rope, so you whipped out a pocket knife and sliced it clean.",
        "the boat drifted into the lake without an anchor and bumped into a swan family. The mother swan is now attacking {user}."
    ),
    (
        "You saw {user} shivering in the cold and decided to drape a warm wool blanket over their shoulders.",
        "it was an expensive hand-dyed cashmere garment drying on a line that belonged to the cafe owner. You are now accused of grand theft knitwear."
    ),
    (
        "You saw {user} trying to capture a spider in a glass cup and decided to stomp it with your steel-toe boot to be helpful.",
        "you shattered the vintage glass cup, cracked the antique wooden floor, and the spider scampered up {user}'s pant leg."
    )
]

REFUSAL_SCENARIOS = [
    "You rushed over to carry {user}'s heavy grocery bags, but they slapped your hands away: \"Hands off my groceries, weirdo!\" They tossed a few berries at your feet just to make you leave.",
    "You tried to guide {user} across the crosswalk, but they yanked their arm back: \"I live on this side of the road!\" Out of sheer embarrassment and pity, they flicked some berries at your forehead.",
    "You offered {user} your umbrella during a sudden drizzle. They glared at you: \"I like getting wet, back off.\" They dropped a small handful of berries into your palm to shoo you away.",
    "You held the elevator door open for {user} while smiling warmly. They rolled their eyes, took the stairs instead, and tossed a small berry tip onto the floor.",
    "You tried to wipe what looked like a stain off {user}'s jacket. They gasped: \"That is designer distressed aesthetic!\" They threw some berries at your chest to make you go away.",
    "You offered {user} a sip of your cold water bottle when they coughed. They looked at you like you were trying to poison them, tossed a few berries on the ground, and walked away.",
    "You stepped in to help {user} solve a crossword puzzle. They slammed the book shut: \"I was almost done, you ruined the whole thing!\" They shoved a couple berries into your hand and turned their back.",
    "You offered to take a photo of {user} in front of the monument. They squinted suspiciously: \"Yeah right, so you can run away with my phone?\" They dropped some berries in your empty cup and scurried away.",
    "You tried to help {user} pack their suitcase before a trip. They pushed you out of the room: \"You're folding everything like a barbarian!\" They threw a small fistful of berries at your face and locked the door.",
    "You ran over to help {user} look for their dropped earring. They scowled: \"I didn't drop anything, I was scratching my ear.\" They tossed a few berries at you to buy some peace and quiet.",
    "You offered to hold {user}'s drink while they tied their shoelace. They looked at you like a hawk: \"Never let strangers touch the drink.\" They dropped some berries on your shoe and backed off.",
    "You tried to help {user} fix their bicycle chain. They swatted your hand away: \"You don't know what you're doing, get lost!\" They tossed a pouch of berries to make you vanish.",
    "You tried to give {user} directions when they stared at a map. They snapped: \"I'm looking at a fictional fantasy map, leave me alone.\" They flicked some berries at you in annoyance.",
    "You tried to adjust {user}'s crooked collar. They slapped your wrist away: \"Personal space violation!\" They threw a few berries at you like pocket sand and hurried off."
]

STEAL_SUCCESS_SCENARIOS = [
    "You quietly snipped the drawstring on {user}'s pouch while they were marveling at a street magician.",
    "You distracted {user} by pointing into the sky yelling \"LOOK, A SHINY RAYQUAZA!\" and swiftly emptied their berry stash.",
    "You slid your hand into {user}'s coat pocket during the evening rush hour and extracted a hefty handful of berries.",
    "While {user} was busy bargaining with an old merchant, you reached through the display stand and snatched their berry pouch.",
    "You crept up on tiptoes while {user} was taking an afternoon nap under a cherry blossom tree and made off with their berries.",
    "You casually bumped into {user} at the festival, bowed apologetically, and walked away with their entire berry jar.",
    "You swapped {user}'s heavy bag of fresh berries with a bag of identical-looking pebbles without them noticing.",
    "You tossed a smoke bomb at {user}'s feet and vanished into the foggy alleyway clutching their prized berries.",
    "You saw {user} drop their guard while opening an umbrella, quickly unhooking their berry pouch in a split-second heist.",
    "You sent a trained stray raccoon to run between {user}'s legs as a distraction while you swiped their berries."
]

STEAL_CAUGHT_SCENARIOS = [
    "You reached deep into {user}'s pocket, only to snap your fingers directly into a hidden mousetrap! {user} spun around and called the town guards.",
    "{user} caught your wrist in an iron grip before your fingers even grazed their pouch: \"Did you really think that would work on me?\"",
    "You grabbed {user}'s berry basket and sprinted, only to slip on a wet banana peel and faceplant in front of the entire marketplace.",
    "As you tugged {user}'s bag, a cluster of concealed tiny brass bells jingle-jangled loudly. Everyone on the street turned and stared right at you!",
    "You tried to pickpocket {user}, but you accidentally grabbed their pet hedgehog instead. Its angry squeaks alerted the entire district.",
    "You tipped over a tower of metal pots and pans while sneaking behind {user}. The thunderous crash exposed your crime instantly.",
    "{user} had coated their berries with sticky luminescent ink. The moment you touched them, your hands started glowing bright neon pink!",
    "You yanked {user}'s pouch, but the seam tore open and showered hard berries right onto the shiny helmet of a passing town sheriff."
]

STEAK_HEIST_SCENARIOS = [
    "As {sender}'s carrier pigeon fluttered toward {target} with the berry parcel, Empress Yuna dropped from the rafters wielding a massive, sizzling Wagyu T-Bone Steak like a cricket bat! *SMACK!* She swatted the delivery away and purloined 75% of the berries!",
    "A golden courier cart carrying {sender}'s berries was speeding toward {target} when Empress Yuna leaped out of the bushes dual-wielding smoking Tomahawk Steaks! She held up the cart, stuffed 75% into her royal pouch, and vanished into thin air!",
    "Just as {sender} placed the berries into {target}'s hands, Yuna slid across the marble floor riding a giant Ribeye Steak like a skateboard! *SWOOSH!* She scooped 75% of the berries right out of the basket!",
    "A delivery drone buzzing toward {target} was struck mid-flight by a precision-hurled, medium-rare Sirloin Steak! Empress Yuna caught 75% of the falling berries in her imperial apron, cackling wildly!",
    "Empress Yuna appeared behind {sender} in an anime teleport flash (*Omae wa mou shindeiru*), slapped the berry bag with a legendary Dry-Aged Porterhouse, and commandeered 75% for royal sustenance!"
]

FIGHT_SCENARIOS = [
    (
        "Round 1: {u1} lunges forward wielding a tactical french baguette, but {u2} parries with an iron trash can lid!\n"
        "Round 2: {u2} attempts a flying dropkick, but gets their shoelace caught on a passing pigeon!\n"
        "Final Blow: {winner} channels pure anime protagonist energy, unleashing a flurry of ultra-slaps that sends {loser} flying into a cardboard recycling bin!"
    ),
    (
        "Round 1: {u1} summons an angry flock of seagulls to steal {u2}'s snacks!\n"
        "Round 2: {u2} pulls out a laser pointer, causing the seagulls to turn against {u1}!\n"
        "Final Blow: {winner} whips out a giant squeaky inflatable hammer and lands a critical BONK on {loser}'s head!"
    ),
    (
        "Round 1: {u1} throws pocket sand, but {u2} was already wearing designer aviator sunglasses!\n"
        "Round 2: {u2} attempts a menacing WWE elbow drop from the top of a picnic table, but misses completely!\n"
        "Final Blow: {winner} executes a picture-perfect pillow barrage that knocks {loser} out cold onto a fluffy beanbag!"
    ),
    (
        "Round 1: {u1} challenges {u2} to an aggressive dance-off, executing a dizzying breakdance spin!\n"
        "Round 2: {u2} counters with an aggressive interpretive salsa dance that dazzles the spectators!\n"
        "Final Blow: {winner} drops a legendary split that ruptures space-time, leaving {loser} clapping in tears of defeat!"
    ),
    (
        "Round 1: {u1} hurls a cup of boiling instant ramen, but {u2} catches it with chopsticks mid-air and slurps it down!\n"
        "Round 2: {u2} tries to use psychic mind powers, but only gives themselves a mild migraine!\n"
        "Final Blow: {winner} sweeps {loser}'s legs with a wet mop from the supply closet, scoring an absolute knockout!"
    )
]

DARES = [
    "Speak exclusively in old Victorian Shakespearean English for your next 5 messages in this server.",
    "Write an original 4-line rhyming poem dedicated to Yuna's unmatched perfection right now.",
    "Describe your most recent meal in the style of an intense gothic horror psychological novel.",
    "Apologize profusely to a bot in the server as if you personally ruined its entire family lineage.",
    "Confess in this channel that you secretly enjoy dipping french fries in chocolate milk (or another cursed food combo).",
    "Send a message where every single word begins with the letter 'P' (or 'S'). Minimum 7 words!",
    "Type out a full 3-course gourmet review of a single raw potato or slice of plain bread.",
    "Declare your undying allegiance to the nearest inanimate object in your room and address it as supreme royalty.",
    "Write an overly emotional villain monologue explaining why you refuse to do the dishes.",
    "Type your next 3 messages in ALL CAPS as if you're an extreme esports commentator shouting at 300 dB.",
    "Explain the plot of your favorite anime, show, or game using only emojis.",
    "Send a message ending every single sentence with '~ nya :3' for your next 5 messages.",
    "Write a short dramatic eulogy for the last snack or drink you consumed.",
    "Ping the person directly above you in chat and thank them sincerely for inspiring your spiritual awakening.",
    "Pretend you are an undercover alien agent writing an urgent progress report about human Discord culture.",
    "Deliver an emotional Oscar-winning acceptance speech for winning 'World\'s Most Chaotic Procrastinator'.",
    "Describe your bedroom as if it were a terrifying high-difficulty Dark Souls boss arena.",
    "Post the most bizarre, cursed, or funny meme currently saved in your camera roll.",
    "Give a deeply passionate defense of why cereal is legally and scientifically considered soup.",
    "Roleplay as a disgruntled 1940s noir detective solving the mysterious case of who stole your berries.",
    "Type out a 5-step survival guide for surviving an ambush by an enraged Canadian goose.",
    "Compose a sales pitch for 'Invisible Socks' and convince the channel it's worth 1,000 berries.",
    "Send a message using exclusively pirate slang: 'Ahoy, shiver me timbers, blimey, walk the plank!'",
    "Rank the 3 most useless superpowers you would pick just to mildly inconvenience people.",
    "Write an aggressive love letter to your WiFi router pleading for lower ping.",
    "Pretend you are a medieval bard singing the legendary triumphs of your last gaming session in rhyming verse."
]

TRUTHS = [
    "What is the single most embarrassing thing you have ever typed, sent, or posted on Discord?",
    "What is your biggest guilty pleasure anime, song, or video that you secretly enjoy but would never admit publicly?",
    "Have you ever lied about your internet disconnecting just to rage-quit a multiplayer match or avoid a voice call?",
    "What was your most cringe-worthy username, gamer tag, or status from when you were younger?",
    "What is the weirdest, most unhinged food combination you genuinely believe is an absolute 10/10 masterpiece?",
    "If everyone in this Discord server could see your YouTube search history for the past 48 hours, how cooked are you from 1 to 10?",
    "What is the most ridiculous or childish thing you believed was true embarrassingly late into your life?",
    "Who in this server would you trust the LEAST to survive a zombie apocalypse with you, and why?",
    "Have you ever stalked someone's profile, server status, or Spotify activity for an embarrassing amount of time?",
    "What is an opinion about a popular game, movie, or anime that would get you instantly canceled by the community?",
    "What is the longest continuous stretch of time you've spent gaming in your pajamas without leaving your room?",
    "What is the pettiest reason you have ever blocked or unfriended someone online?",
    "If you were unexpectedly arrested with no explanation, what would your friends in this server assume you did?",
    "What is the most awkward lie you've ever told an employer, teacher, or friend to avoid attending an event?",
    "Have you ever accidentally sent a message to the wrong chat or DM that made your soul leave your body?",
    "What is one habit you have when nobody is looking that you would die of embarrassment if someone witnessed?",
    "If you had to trade bank accounts with anyone in this server's leaderboard, who would you pick and why?",
    "What is the most absurd rabbit hole you have stayed up until 4 AM reading about on Wikipedia or Reddit?"
]

# ─── ABSURDITY COLLECTIONS (COMEDY THEMES) ──────────────────────────────────

COINFLIP_ABSURDITIES = [
    {
        "type": "yuna_stole",
        "weight": 35,
        "refund": True,
        "text": (
            "🪙 **COIN FLIP — HEIST IN BROAD DAYLIGHT!** 🪙\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "You toss the shiny berry coin high into the air and—\n\n"
            "**WAIT WHAT?! YUNA SUDDENLY DIVES ACROSS THE TABLE, SNATCHES THE COIN MID-AIR, AND RUNS AWAY!**\n"
            "🏃‍♀️💨 *\"mehehhehehe mine now! *zoomies*\"*\n\n"
            "...Whoops, you lost nothing! Your **{amount}** 🫐 were safely refunded to your pouch.\n"
            "*Maybe this is a sign from the heavens to stop gambling...*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
    },
    {
        "type": "eagle",
        "weight": 15,
        "refund": False,
        "text": (
            "🦅 **COIN FLIP — AERIAL THEFT!** 🦅\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "You flick the coin high! Just as it glints in the sun, a ferocious bald eagle swoops down from the clouds at 90 mph, snatches the coin in its razor talons, and soars away over the mountains!\n\n"
            "*Yuna salutes the horizon:* \"Majestic creature. Terrible for your balance, but majestic.\"\n"
            "💸 You lost **{amount}** 🫐.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
    },
    {
        "type": "sewer",
        "weight": 15,
        "refund": False,
        "text": (
            "🕳️ **COIN FLIP — SEWER DRAIN DISASTER!** 🕳️\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "The coin falls... lands right on its thin outer edge... stays perfectly balanced... and starts rolling down the asphalt like a runaway wheel! It swerves past a curb, slips between the iron bars of a street sewer, and drops into the deep abyss.\n\n"
            "*...plink... plink... plop... splash.*\n"
            "*Yuna shines a flashlight down the grate:* \"It belongs to the sewer alligators now.\"\n"
            "💸 You lost **{amount}** 🫐.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
    },
    {
        "type": "pigeon",
        "weight": 12,
        "refund": False,
        "text": (
            "🐦 **COIN FLIP — THE PIGEON VACUUM!** 🐦\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "You flip the coin with dramatic elegance! A dangerously round metropolitan pigeon intercepts it in mid-flight, gulps the entire coin down in one violent swallow, lets out a small metallic burp, and waddles off behind a dumpster.\n\n"
            "💸 You lost **{amount}** 🫐.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
    },
    {
        "type": "spacetime",
        "weight": 10,
        "refund": False,
        "text": (
            "🌀 **COIN FLIP — 3042 CHRONO-HEIST!** 🌀\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Mid-air, a shimmering neon portal rips open with an electric zap! A chrome cybernetic robotic arm from the year 3042 reaches out, snatches the spinning coin, and an android voice echoes:\n"
            "*\"RARE 21ST CENTURY BERRY CURRENCY SECURED FOR THE GALACTIC MUSEUM.\"*\n"
            "The portal snaps shut with a loud *POP*.\n\n"
            "💸 You lost **{amount}** 🫐.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
    },
    {
        "type": "zero_gravity",
        "weight": 8,
        "refund": True,
        "text": (
            "🌌 **COIN FLIP — GRAVITATIONAL FAILURE!** 🌌\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "You flip the coin upward... but it never falls back down. It reaches eye height, freezes completely in place, and rotates slowly in mid-air in zero gravity. You try poking it with a stick, but it\'s locked into the spacetime fabric.\n\n"
            "*Yuna shrugs:* \"Server physics crashed. Come back in the next reality update.\"\n"
            "🫐 Bet refunded: **+{amount}** 🫐 returned to your pouch!\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
    },
    {
        "type": "lightning",
        "weight": 5,
        "refund": False,
        "text": (
            "⚡ **COIN FLIP — SMITED BY ZEUS!** ⚡\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "From a crystal clear sunny sky, a pinpoint beam of heavenly lightning strikes the coin with a deafening *CRACK!* The coin is instantly vaporized into a cloud of glowing purple ozone.\n\n"
            "*Yuna coughs through the smoke:* \"Zeus has spoken. He said your bet was trash.\"\n"
            "💸 You lost **{amount}** 🫐.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
    }
]

ROULETTE_ABSURDITIES = [
    {
        "type": "hamster_wheel",
        "weight": 25,
        "refund": True,
        "text": (
            "🎡 **ROULETTE — YUNA'S HAMSTER CRASH!** 🎡\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "The wheel begins to spin... when suddenly Yuna leaps onto the mahogany rim and starts sprinting inside it like a manic hamster!\n"
            "🏃‍♀️💨 *\"FASTER! MAXIMUM VELOCITY NYA!\"*\n\n"
            "The centrifugal force ejects the ivory ball straight into Yuna's boba straw with a loud *SLURP*! Spin declared void!\n"
            "🫐 Your bet of **{amount}** 🫐 was refunded to your pouch.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
    },
    {
        "type": "quantum_ball",
        "weight": 20,
        "refund": False,
        "is_win_all": True,
        "text": (
            "🌌 **ROULETTE — QUANTUM SUPERPOSITION!** 🌌\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "The ivory marble begins to hum and glow neon cyan. It starts vibrating at quantum frequency, splits into two ghostly mirror particles, and lands on **BOTH RED AND BLACK** at the exact same instant!\n\n"
            "🎰 *Yuna gasps:* \"Schrodinger's Roulette! The casino laws of physics have collapsed!\"\n"
            "🎉 **EVERY OUTSIDE BET WINS!** Payout: **+{payout}** 🫐!\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
    },
    {
        "type": "neodymium_magnet",
        "weight": 20,
        "refund": True,
        "text": (
            "🧲 **ROULETTE — NEODYMIUM CATASTROPHE!** 🧲\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "The marble rattles around the wheel... when suddenly Yuna slaps a giant souvenir anime fridge magnet on the table edge!\n"
            "The metal ball takes a sharp 90-degree right turn mid-air, snaps onto the magnet with a loud *CLACK!*, and refuses to let go.\n\n"
            "*Yuna blushes furiously:* \"Uh... that was totally accidental! Round canceled!\"\n"
            "🫐 Your **{amount}** 🫐 were refunded to your pouch.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
    },
    {
        "type": "pigeon_swoop",
        "weight": 15,
        "refund": False,
        "text": (
            "🐦 **ROULETTE — PIGEON CASINO HEIST!** 🐦\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "As the wheel slows down, an unusually muscular city pigeon glides in through the ventilation shaft, lands on the center spindle, grabs the ball with its beak, and flies away into the sunset.\n\n"
            "*Yuna pulls out binoculars:* \"He's heading south. He has your ball. Round lost.\"\n"
            "💸 You lost **{amount}** 🫐.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
    },
    {
        "type": "wheel_liftoff",
        "weight": 10,
        "refund": True,
        "bonus": 25,
        "text": (
            "🚁 **ROULETTE — CASINO WHEEL LIFTOFF!** 🚁\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "The wheel spins at 18,000 RPM. The center bolt strips its threads! The entire solid wood roulette wheel unscrews itself, ascends into the air like a helicopter rotor, and flies through the glass skylight toward the stratosphere.\n\n"
            "*Yuna tosses you a snack:* \"Well, that's not coming back. Here's your refund plus a 25 🫐 apology snack!\"\n"
            "🫐 Refunded: **+{amount}** 🫐 + **25** pity berries!\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
    },
    {
        "type": "strawberry_ball",
        "weight": 10,
        "refund": True,
        "bonus": 10,
        "text": (
            "🍓 **ROULETTE — THE ENCHANTED BERRY!** 🍓\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "The ivory marble rolls past slot 17... and suddenly blooms into a juicy, plump wild strawberry! It bounces softly off the brass frets and rolls into your palm.\n\n"
            "*Yuna smiles:* \"A sweet omen from the forest! Take your berries back, plus a fresh bonus!\"\n"
            "🫐 Refunded: **+{amount}** 🫐 + **10** sweet berries!\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
    }
]

POKER_ABSURDITIES = [
    {
        "type": "uno_wild",
        "title": "Uno Wild +4 Intervention",
        "multiplier": 2.0,
        "text": "🃏 **AN UNO WILD +4 CARD SLIPPED INTO YOUR HAND!** Yuna: *'Wait, that's not regulation Hoyle!'* It morphs into the perfect card and doubles your total payout!"
    },
    {
        "type": "exodia_limb",
        "title": "The Forbidden One",
        "multiplier": 20.0,
        "text": "👁️ **YOU WERE DEALT THE RIGHT ARM OF THE FORBIDDEN ONE!** Yuna shrieks in terror and drops an instant **20x Jackpot** at your feet!"
    },
    {
        "type": "crayon_ace",
        "title": "Crayon Ace Special",
        "multiplier": 1.5,
        "text": "🖍️ **ONE OF YOUR CARDS IS DRAWN IN SCENTED PURPLE CRAYON!** Yuna inspects it closely: *'Looks completely legitimate to me.'* Extra 1.5x bonus awarded!"
    },
    {
        "type": "berry_flush",
        "title": "Gourmet Berry Flush",
        "multiplier": 15.0,
        "text": "🍓 **YOUR CARDS MORPH INTO FRESH RIPE STRAWBERRIES!** The sweet aroma overwhelms the table, paying out a magical 15x Gourmet Berry Flush!"
    },
    {
        "type": "card_origami",
        "title": "Origami Paper Crane",
        "multiplier": 5.0,
        "text": "🦢 **YOUR DISCARD FOLDS ITSELF INTO A PAPER SWAN AND FLAPS OFF!** Yuna replaces it with a golden trump card! 5x bonus!"
    }
]

HL_COMEDY_EVENTS = [
    (
        "Wait! The number tile bounces off the table, hits Yuna\'s iced tea glass, and reveals **{num}**! Yuna: *\"Look, cosmic fate! It counts!\"*",
        True
    ),
    (
        "A stray tavern raccoon darts across the table, knocks over the number into infinity (∞), and scampers away! Yuna giggles: *\"Infinity is always higher! Round saved!\"*",
        True
    ),
    (
        "The next number was drawn in green crayon... it\'s a drawing of a dinosaur! 🦖 Yuna: *\"Dinosaurs are prehistoric, which means they are older than any number. Higher!\"*",
        True
    ),
    (
        "Yuna sneezed so hard she blew the number card out the window! She replaces it with a sticky note reading **{num}**: *\"Totally legit number, trust me!\"*",
        True
    )
]

COMEDY_CARDS = [
    ("Uno Reverse", 10, "🔄", "`[Uno Reverse 🔄]`", "Yuna gasped: *'Wait, an Uno Reverse Card?! Does that mean you dealer-bust me?! No, house rules say it counts as 10!'*"),
    ("Blue-Eyes", 10, "🐉", "`[Blue-Eyes Dragon 🐉]`", "Yuna panicked: *'WAIT, who shuffled a Yu-Gi-Oh card in here?! It counts as 10!'*"),
    ("Bitten 7", 7, "🍓", "`[Bitten 7 🍓]`", "Yuna took a bite out of this card: *'Tastes like sweet berries.'* It's a 7!"),
    ("Boba Coupon", 6, "🧋", "`[20% Boba Coupon]`", "Yuna accepted a discarded boba coupon as a 6!"),
    ("Wild +4", 10, "🃏", "`[Wild Draw +4 🃏]`", "Yuna blinked: *'Don't look at me, that counts as 10!'*")
]

COMEDY_CRASH_REASONS = [
    "A rogue space goose collided with the rocket thruster! *HONK!*",
    "The pilot accidentally fueled the rocket with berry smoothie. The engine sputtered purple foam and died.",
    "Intergalactic highway patrol pulled over the rocket for illegal tinted windshields.",
    "A space taco floated directly into the air intake!",
    "The pilot sneezed and accidentally pressed the red self-destruct button.",
    "A wandering astronaut unplugged the main cosmic extension cord."
]

DOUBLE_AID_SUCCESS_SCENARIOS = [
    "You and {spouse} formed an acrobatic human ladder to rescue {user}'s cat from an impossibly tall tree. The cat purred gratefully and {user} showered you both with joyful blessings!",
    "You and {spouse} synchronized like professional pit-crew mechanics to replace {user}'s flat bicycle tire in under 12 seconds flat!",
    "You and {spouse} whipped up a gourmet 3-course dinner for {user} when their food delivery got canceled. Absolute culinary masterclass!",
    "You and {spouse} coordinated a brilliant pincer maneuver to tackle a thief who snatched {user}'s backpack, returning all their belongings safe and sound!",
    "You and {spouse} sang a harmonized duet outside {user}'s window to cheer them up after a rough day. It was so angelic that {user} gave you a standing ovation!",
    "You and {spouse} tag-teamed {user}'s heavy moving boxes, carrying an entire solid oak wardrobe up three flights of stairs without breaking a sweat!",
    "You and {spouse} held an umbrella canopy over {user} during a flash thunderstorm while escorting them safely to the train station!"
]

DOUBLE_AID_MESS_UP_SCENARIOS = [
    (
        "You and {spouse} tried to help {user} assemble flatpack furniture...",
        "you two started arguing passionately over the allen wrench, and the entire bookshelf collapsed directly onto {user}'s toes!"
    ),
    (
        "You and {spouse} tried to catch {user} as they slipped on an icy patch...",
        "you both lunged forward at once, headbutted each other with a loud CLACK, and all three of you bowled directly into a snowbank!"
    ),
    (
        "You and {spouse} tried to surprise {user} with celebration party poppers...",
        "the confetti cannons backfired with a deafening BANG, coating {user}'s entire outfit in permanent neon pink glitter!"
    ),
    (
        "You and {spouse} tried to help {user} bake a birthday cake...",
        "you set the oven to 500 degrees while {spouse} added salt instead of sugar. The cake smoke-bombed {user}'s kitchen!"
    )
]

DOUBLE_AID_REFUSAL_SCENARIOS = [
    "You and {spouse} marched over in matching pastel outfits radiating intense couple energy. {user} felt so intimidated by your romantic aura that they slowly backed away into the bushes.",
    "You and {spouse} offered to help {user} with chores, but kept feeding each other strawberries so affectionately that {user} asked you both to please give them personal space.",
    "You and {spouse} tried to offer {user} life advice, but ended up gazing deeply into each other's eyes and forgot {user} was even standing there."
]

DOUBLE_STEAL_SUCCESS_SCENARIOS = [
    "You executed a diversion by loudly arguing with a street pretzel vendor while {spouse} stealthily picked {user}'s pocket with surgeon-like precision!",
    "You and {spouse} wore matching sleek spy trench coats, dropped a purple smoke bomb, and vanished into the night with {user}'s berry pouch!",
    "{spouse} posed as an earnest clipboard surveyor asking {user} silly questions while you swiftly unclipped their berry coin purse!",
    "You accidentally tripped and bowled into {user} while apologizing profusely; meanwhile {spouse} snagged their berries in the commotion!",
    "You and {spouse} pulled off a synchronized Hollywood bank-heist roll through {user}'s dining room, snatching the berry bowl clean!"
]

DOUBLE_STEAL_CAUGHT_SCENARIOS = [
    "You and {spouse} tried to coordinate a pincer snatch on {user}, but you both sprinted forward and slammed directly into each other forehead-first!",
    "You dropped your smoke bomb backwards into your own boots. Blinded by pink smoke, you and {spouse} tackled a mailbox instead of {user}!",
    "{spouse} stepped on a noisy whoopee cushion while sneaking behind {user}. {user} whipped around and caught you both red-handed!",
    "You were about to unzip {user}'s berry pouch, but you and {spouse} started whispering an argument over who gets the bigger cut and got spotted!"
]

WORK_JOBS = [
    ("🧋 Boba Barista", "whipped up 30 cups of brown sugar boba milk tea for thirsty gamers", 70, 130),
    ("🧹 Casino Floor Sweeper", "swept up thousands of discarded Uno cards and spilled berry juice from the VIP room", 60, 110),
    ("🎧 Anime Soundtrack DJ", "mixed a fiery 45-minute Vocaloid and eurobeat set that had the whole lounge dancing", 85, 145),
    ("🐱 Cat-Ear Untangler", "patiently untangled a horrifying nest of wired pink cat-ear headphones", 65, 120),
    ("🍓 Berry Orchard Harvester", "climbed high branches and picked baskets of plump, sun-ripened cosmic berries", 75, 135),
    ("⛩️ Shrine Maiden Assistant", "swept the stone steps of Yuna's mountaintop shrine and organized prayer amulets", 80, 150),
    ("🤖 Arcade Claw Machine Calibrator", "rigged 15 plushie claw machines so they were slightly less impossible to win", 70, 125)
]

CRIME_MISSIONS = [
    ("ATM Hacking", "spliced a modified Game Boy into the berry ATM and forced it to spit out loose loot", 130, 260),
    ("Bootleg Boba Cartel", "smuggled an unregistered batch of forbidden popping boba across municipal borders", 120, 240),
    ("Roulette Wheel Rigging", "placed a discreet neodymium magnet under Yuna's lucky 7 casino wheel", 150, 290),
    ("Vocaloid Bootlegging", "duplicated rare vintage Hatsune Miku vinyl records and sold them behind the alley", 140, 270),
    ("VIP Vault Heist", "crawled through the casino ventilation shaft and emptied the petty cash safe", 160, 310)
]

CRIME_FAIL_REASONS = [
    "Yuna's robotic guard hound caught your scent and chased you straight into a municipal fountain!",
    "A laser tripwire in the ceiling was triggered by your squeaky sneakers!",
    "You accidentally left your own Discord profile card at the scene of the crime!",
    "The security cameras caught your face in 4K resolution while you were smiling at a stray cat!"
]

FISH_CATCHES = [
    ("Tiny Berry Minnow", "🐟", 25, 40, "A tiny, wiggly blue minnow. Barely a mouthful!"),
    ("Cosmic Goldfish", "🐠", 45, 75, "Glittering scales reflecting starlight. Very pretty!"),
    ("Electric Jellyfish", "🪼", 75, 120, "Glows neon pink! Zapped your fingertips when reeled in."),
    ("Golden Koi", "✨🐟", 140, 220, "An auspicious, heavy golden koi revered by casino patrons!"),
    ("Giant King Berry Salmon", "🍣", 180, 280, "A magnificent beast that put up an epic 10-minute battle!"),
    ("Rare Dragon Pearl", "🔮", 350, 500, "A mystical iridescent orb whispered to hold ancient draconic fortune! (+1 💖 Virtue)"),
    ("Soggy Boot", "👢", 5, 15, "An old waterlogged leather boot with seaweed inside."),
    ("Discarded Boba Cup", "🧋", 10, 20, "Someone didn't recycle their taro bubble tea cup."),
    ("Ancient Uno Reverse Card", "🔄", 30, 50, "A waterlogged Uno Reverse card! Does this reverse your luck?")
]

SHOP_ITEMS = {
    "ward": {
        "name": "Heavenly Shield",
        "emoji": "🛡️",
        "price": 15000,
        "type": "shield",
        "desc": "Holy defensive equipment! Automatically blocks a steal or boss attack with 100% protection when pure. But beware: Sin corrupts this shield! High Sin causes it to fail, crack, recoil, or violently explode! (Max hold: 2)"
    },
    "clover": {
        "name": "Lucky Clover",
        "emoji": "🍀",
        "price": 10500,
        "type": "consumable",
        "desc": "Use with `y!use clover` for +25% luck on your next gamble, crime, or fishing trip! (Max hold: 2)"
    },
    "energy": {
        "name": "Energy Drink",
        "emoji": "⚡",
        "price": 7500,
        "type": "consumable",
        "desc": "Use with `y!use energy` to instantly reset your work, crime, and fishing cooldowns! (Max hold: 2)"
    },
    "mask": {
        "name": "Phantom Mask",
        "emoji": "🎭",
        "price": 18000,
        "type": "consumable",
        "desc": "Use with `y!use mask` before a steal/crime: produces zero sin and grants +30% extra loot! (Max hold: 2)"
    },
    "diamond": {
        "name": "Eternal Diamond",
        "emoji": "💎",
        "price": 75000,
        "type": "collectible",
        "desc": "Permanent heirloom: upgrades your joint vault daily passive love interest from +5% to +10%! (Max hold: 2)"
    },
    "insurance": {
        "name": "Divorce Insurance",
        "emoji": "📜",
        "price": 45000,
        "type": "policy",
        "desc": "One-time protection: cuts Yuna's 10,000 🫐 divorce legal fee in half down to 5,000 🫐! (Max hold: 2)"
    },
    "crown": {
        "name": "Empress Crown",
        "emoji": "👑",
        "price": 900000,
        "type": "flex",
        "desc": "The ultimate status symbol! Displays a glittering golden crown on your balance and rankings! (Max hold: 2)"
    },
    # ── Romance & Matrimonial Treasures ──
    "ring": {
        "name": "Golden Wedding Ring",
        "emoji": "💍",
        "price": 50000,
        "type": "romance",
        "desc": "Enchanted 24k gold band. While married, boosts daily allowance stipend (`y!daily`) from +50 to +120 🫐, increases marriage gambling profit bonus from +15% to +25%, and gives +10% Double Aid success! (Max hold: 2)"
    },
    "bouquet": {
        "name": "Starlight Rose Bouquet",
        "emoji": "💐",
        "price": 12000,
        "type": "romance",
        "desc": "Glowing celestial roses. Use with `y!use bouquet` (or take on `y!date`): grants +1 💖 Virtue to both partners and deposits 1,500 🫐 into your Joint Vault! (Max hold: 2)"
    },
    "chocolate": {
        "name": "Heart Truffles Box",
        "emoji": "🍫",
        "price": 8000,
        "type": "consumable",
        "desc": "Handmade strawberry-cocoa truffles. Use with `y!use chocolate` to share with your spouse: instantly resets cooldowns for `y!date` and `y!doubleaid`! (Max hold: 2)"
    },
    # ── Spiritual & High-Roller Charms ──
    "mirror": {
        "name": "Purifying Mirror",
        "emoji": "🪞",
        "price": 40000,
        "type": "consumable",
        "desc": "Sacred crystal glass. Use with `y!use mirror`: absorbs and cleanses 3 points of mortal ❤️‍🔥 Sin without angering Juny! (Max hold: 2)"
    },
    "magnet": {
        "name": "Super Berry Magnet",
        "emoji": "🧲",
        "price": 25000,
        "type": "consumable",
        "desc": "Polarizes your berry pouch. Use with `y!use magnet`: your next 3 casino wins or work shifts attract an extra +20% bonus berries! (Max hold: 2)"
    },
    "loaded_die": {
        "name": "Lucky Loaded Die",
        "emoji": "🎲",
        "price": 20000,
        "type": "consumable",
        "desc": "Enchanted weighted bone. Use with `y!use die`: guarantees your next `y!dice` roll will NEVER roll Snake Eyes (2) and boosts odds of Lucky 7 or Doubles! (Max hold: 2)"
    },
    "holy_water": {
        "name": "Blessed Holy Water",
        "emoji": "💧",
        "price": 18000,
        "type": "consumable",
        "desc": "Consecrated divine vial. Use with `y!use holy_water`: blesses your Heavenly Shield, making it immune to Sin corruption and guaranteeing 100% block! (Max hold: 2)"
    },
    # ── Combat Consumables & Boss Fight Gear ──
    "sword": {
        "name": "Legendary Expensive Sword",
        "emoji": "🗡️",
        "price": 5000000000,
        "price_display": "expensive",
        "type": "weapon",
        "desc": "A gleaming, god-slaying mythical blade forged from celestial stardust. The price is beyond mortal comprehension."
    },
    "feather": {
        "name": "Phoenix Feather",
        "emoji": "🪶",
        "price": 1000000000,
        "type": "combat",
        "desc": "One-time divine resurrection! Automatically revives you with 50 HP if you fall in battle against Juny! (Max holding limit: 1)"
    },
    "elixir": {
        "name": "Archangel's Elixir",
        "emoji": "🧪",
        "price": 6660000,
        "type": "combat",
        "desc": "One-time combat healing potion: restores 75 HP instantly during a boss fight!"
    },
    "powder": {
        "name": "Smite Powder",
        "emoji": "✨",
        "price": 11655000,
        "type": "combat",
        "desc": "One-time combat consumable: detonates for 150 true holy damage against Juny, bypassing defense!"
    },
    "ironbrew": {
        "name": "Aegis Iron Brew",
        "emoji": "🛡️",
        "price": 8325000,
        "type": "combat",
        "desc": "One-time combat tonic: hardens your flesh, granting +50 DEF for 3 combat turns!"
    },
    "adrenaline": {
        "name": "Adrenaline Injector",
        "emoji": "💉",
        "price": 9990000,
        "type": "combat",
        "desc": "One-time combat booster: sharpens reflexes, granting +35 ATK and +15% Dodge for 3 combat turns!"
    },
    "hammer": {
        "name": "Squeaky Rubber Hammer",
        "emoji": "🔨",
        "price": 499500,
        "type": "combat",
        "desc": "A squeaky clown hammer. Hits Juny for 1 comedic damage with a high-pitched squeak!"
    },
    "sand": {
        "name": "Pocket Sand",
        "emoji": "🏖️",
        "price": 1665000,
        "type": "combat",
        "desc": "A handful of coarse sand! Toss it into Juny's eyes to blind her, causing her next attack to miss!"
    },
    "coupon": {
        "name": "Coupon for 1 Free Apology",
        "emoji": "🎟️",
        "price": 3330000,
        "type": "special",
        "desc": "A crinkled coupon promising to be on your best behavior. Grants +5% plead success if Juny hunts you!"
    },
    # ── Non-Shop Relics & Artifacts ──
    "devil_contract": {
        "name": "Devil's Contract",
        "emoji": "📜",
        "price": 0,
        "price_display": "pact",
        "type": "pact",
        "desc": "A binding unholy pact signed with Juny, Heaven's Worst Angel. Proclaims your status as the Devil's Slave."
    },
    "devil_horn": {
        "name": "Devil's Horn",
        "emoji": "🦹",
        "price": 0,
        "price_display": "relic",
        "type": "relic",
        "desc": "A gleaming obsidian horn ripped from Juny's halo. Grants permanent +10% combat power and luck!"
    },
    "cardboard_shards": {
        "name": "Cardboard Shards",
        "emoji": "📦",
        "price": 0,
        "price_display": "junk",
        "type": "junk",
        "desc": "The broken remnants of the '5 Billion Berry' Legendary Sword. Still squeaks when stepped on."
    }
}

# ─── 25 ABSURD DEATH SCENARIOS (HIGH SIN KARMIC CATASTROPHES) ───────────────

ABSURD_SIN_DEATHS = [
    "🦈 A 2-ton great white shark suddenly plummets through the casino ceiling and crushes you directly into the poker table!",
    "💔 You clutch your chest as pure adrenaline, sinful guilt, and greasy casino nachos trigger a sudden comical heart attack!",
    "🔨 An ACME 16-ton iron anvil drops from nowhere with an audible whistle and flattens you into an accordion!",
    "🎳 A rogue bowling ball drops from the air conditioning duct and knocks you clean into next Tuesday!",
    "🌯 Your spicy black market burrito detonates with the yield of a tactical thermonuclear warhead!",
    "🕊️ A flock of 50 aggressive casino pigeons swoops into the room and carries you away into the void!",
    "🎹 A grand piano falls from the sky, plays one dissonant minor chord, and squashes you flat!",
    "🍌 You slip on a glowing banana peel and perform an involuntary triple backflip into the casino fountain!",
    "⚡ A freak holy lightning bolt arcs through the chandelier and incinerates you into a cartoon pile of soot!",
    "🚜 A runaway casino Zamboni bursts through the double doors and runs you over at 4 miles per hour!",
    "🦝 A rabid casino raccoon bursts out of the blackjack card shoe and attacks your shins with feral fury!",
    "🕳️ A miniature localized black hole opens under your chair and swallows you whole with a loud pop!",
    "🍂 You accidentally step on a cursed garden rake, which springs up and whacks you in the nose at Mach 3!",
    "🎺 An overly enthusiastic marching brass band tramples right across the table, stomping you into the carpet!",
    "🥤 A vintage soda vending machine mysteriously topples over and pins you to the felt!",
    "🪙 You bend over to pick up a shiny copper penny and get sideswiped by an indoor golf cart!",
    "🦆 A giant 20-foot rubber duck crashes through the front window and squeaks you into unconsciousness!",
    "🔥 You spontaneously combust from the unbearable friction of your own sinful thoughts!",
    "🥥 A coconut drops from a plastic indoor palm tree at terminal velocity squarely onto your head!",
    "🎲 You accidentally swallow a pair of loaded 20-sided dice and choke while gasping for air!",
    "🪿 A Canadian goose wearing a tiny dealer visor flies in and violently pecks you into submission!",
    "⚡ The floor beneath your stool collapses into a subterranean tank of agitated electric eels!",
    "🪤 A comically oversized wooden mousetrap under the table snaps shut with a deafening CRACK!",
    "🪩 The giant mirrored casino disco ball detaches from the ceiling and lands over you like a cage!",
    "😈 Satan's glowing demonic hand reaches up through the floorboards, slaps you across the cheek, and drags you down!"
]

# ─── ACHIEVEMENTS DICTIONARY ────────────────────────────────────────────────

ACHIEVEMENTS = {
    # ── Morality & Karma ──
    "what_have_you_done": {
        "title": "WHAT HAVE YOU DONE",
        "desc": "Reach 30 ❤️‍🔥 Sin (Max Limit).",
        "icon": "💀",
        "check": lambda s: s.get("sin", 0) >= 30
    },
    "local_saint": {
        "title": "Local Saint",
        "desc": "Reach 33 💖 Virtue (Max Limit).",
        "icon": "😇",
        "check": lambda s: s.get("virtue", 0) >= 33
    },
    "daredevil": {
        "title": "Daredevil",
        "desc": "Defeat Juny, Heaven's Worst Angel, in combat.",
        "icon": "👑",
        "check": lambda s: s.get("defeated_juny", False)
    },
    "clean_slate": {
        "title": "Clean Hands",
        "desc": "Hold at least 100 🫐 with absolute zero ❤️‍🔥 Sin.",
        "icon": "🕊️",
        "check": lambda s: s.get("berries", 0) >= 100 and s.get("sin", 0) == 0
    },
    "pure_soul": {
        "title": "Archangel's Blessing",
        "desc": "Reach 50 💖 Virtue while maintaining 0 ❤️‍🔥 Sin.",
        "icon": "✨",
        "check": lambda s: s.get("virtue", 0) >= 50 and s.get("sin", 0) == 0
    },
    "pure_sin": {
        "title": "Diabolical Menace",
        "desc": "Accumulate 25 ❤️‍🔥 Sin while keeping 0 💖 Virtue.",
        "icon": "😈",
        "check": lambda s: s.get("sin", 0) >= 25 and s.get("virtue", 0) == 0
    },
    "robin_hood": {
        "title": "Master Pickpocket",
        "desc": "Successfully steal berries 5 times.",
        "icon": "🦹",
        "check": lambda s: s.get("steals_success", 0) >= 5
    },
    "philanthropist": {
        "title": "Philanthropist",
        "desc": "Donate a cumulative total of 500 🫐 to others.",
        "icon": "✨",
        "check": lambda s: s.get("total_donated", 0) >= 500
    },
    "super_donor": {
        "title": "Great Benefactor",
        "desc": "Donate a cumulative total of 2,000 🫐 to other players.",
        "icon": "🌟",
        "check": lambda s: s.get("total_donated", 0) >= 2000
    },

    # ── Fortune & Berries ──
    "ballin": {
        "title": "Ballin'",
        "desc": "Hold 1,000 🫐 in your pouch at once.",
        "icon": "🏆",
        "check": lambda s: s.get("berries", 0) >= 1000
    },
    "berry_saver": {
        "title": "Piggy Banker",
        "desc": "Amass 2,500 🫐 in your berry pouch at once.",
        "icon": "🐷",
        "check": lambda s: s.get("berries", 0) >= 2500
    },
    "berry_billionaire": {
        "title": "Berry Tycoon",
        "desc": "Amass 10,000 🫐 in your berry pouch at once.",
        "icon": "💰",
        "check": lambda s: s.get("berries", 0) >= 10000
    },
    "down_bad": {
        "title": "Down Bad Financially",
        "desc": "Lose a cumulative total of 10,000 🫐 gambling.",
        "icon": "📉",
        "check": lambda s: s.get("total_lost_berries", 0) >= 10000
    },
    "professional_idiot": {
        "title": "Professional Idiot",
        "desc": "Lose all your berries to 0 three separate times.",
        "icon": "🤡",
        "check": lambda s: s.get("bankrupt_count", 0) >= 3
    },

    # ── Casino & Games ──
    "one_more_spin": {
        "title": "One More Spin",
        "desc": "Gamble 50 times in a single day.",
        "icon": "🎰",
        "check": lambda s: s.get("daily_gambles", 0) >= 50
    },
    "casino_veteran": {
        "title": "Casino Regular",
        "desc": "Participate in 100 total gambling games across Yuna's casino.",
        "icon": "🎲",
        "check": lambda s: s.get("total_gambles", 0) >= 100
    },
    "yunas_favorite": {
        "title": "Yuna's Favorite",
        "desc": "Win an absurdly unlikely gamble (e.g. 5.00x+ Crash cashout).",
        "icon": "⭐",
        "check": lambda s: False
    },
    "moon_walker": {
        "title": "To The Moon!",
        "desc": "Cash out at 10.00x multiplier or higher in Crash.",
        "icon": "🚀",
        "check": lambda s: False
    },
    "space_debris": {
        "title": "Cosmic Dust",
        "desc": "Experience a brutal Crash explosion at 1.20x or lower.",
        "icon": "💥",
        "check": lambda s: False
    },
    "coin_heist": {
        "title": "Victim of Circumstance",
        "desc": "Have your coin stolen by Yuna, an eagle, or a sewer drain.",
        "icon": "🦅",
        "check": lambda s: s.get("coin_heist_count", 0) >= 1
    },
    "mind_reader": {
        "title": "Mind Reader",
        "desc": "Reach a streak of 5 in Higher or Lower.",
        "icon": "🔮",
        "check": lambda s: s.get("hl_max_streak", 0) >= 5
    },
    "oracle_status": {
        "title": "Grand Oracle",
        "desc": "Achieve a psychic streak of 7 or higher in Higher or Lower.",
        "icon": "👁️",
        "check": lambda s: s.get("hl_max_streak", 0) >= 7
    },

    # ── Blackjack Curiosities ──
    "uno_reverse_card": {
        "title": "No, U!",
        "desc": "Draw an Uno Reverse comedy card at the Blackjack table.",
        "icon": "🔄",
        "check": lambda s: False
    },
    "blue_eyes_white_dragon": {
        "title": "Duelist Master",
        "desc": "Draw the legendary Blue-Eyes Dragon comedy card at the Blackjack table.",
        "icon": "🐉",
        "check": lambda s: False
    },
    "bitten_strawberry": {
        "title": "Snack Attack",
        "desc": "Draw the Bitten 7 card at the Blackjack table.",
        "icon": "🍓",
        "check": lambda s: False
    },
    "roulette_jackpot": {
        "title": "High Roller Sovereign",
        "desc": "Hit a 250x Golden Crown Jackpot at Yuna's Roulette wheel!",
        "icon": "👑",
        "check": lambda s: s.get("roulette_jackpots", 0) >= 1
    },
    "royal_flush": {
        "title": "Poker Royalty",
        "desc": "Hit a legendary Royal Flush in Video Poker!",
        "icon": "🃏",
        "check": lambda s: s.get("poker_royal_flushes", 0) >= 1
    },

    # ── Dares, Arena & Social ──
    "dare_master": {
        "title": "Certified Daredevil",
        "desc": "Have Yuna's AI approve your dare completion.",
        "icon": "🎭",
        "check": lambda s: s.get("dares_completed", 0) >= 1
    },
    "arena_gladiator": {
        "title": "Arena Gladiator",
        "desc": "Emerge victorious in 3 PvP duel fights.",
        "icon": "⚔️",
        "check": lambda s: s.get("fights_won", 0) >= 3
    },

    # ── Marriage, Dailies & Lifestyle ──
    "ball_and_chain": {
        "title": "Ball and Chain",
        "desc": "Tie the knot in Yuna's completely unserious marriage system.",
        "icon": "💍",
        "check": lambda s: bool(s.get("spouse"))
    },
    "irreconcilable_differences": {
        "title": "Irreconcilable Differences",
        "desc": "Pay Yuna's legal fees and get divorced.",
        "icon": "💔",
        "check": lambda s: s.get("divorce_count", 0) >= 1
    },
    "serial_marrier": {
        "title": "Hopeless Romantic",
        "desc": "Marry 2 or more times, or find love again after divorce.",
        "icon": "💒",
        "check": lambda s: s.get("marriage_count", 0) >= 2 or (s.get("marriage_count", 0) >= 1 and s.get("divorce_count", 0) >= 1)
    },
    "dynamic_duo": {
        "title": "Dynamic Duo",
        "desc": "Successfully execute a Double Aid with your spouse.",
        "icon": "💞",
        "check": lambda s: s.get("double_aid_count", 0) >= 1
    },
    "joint_investor": {
        "title": "Happily Ever After",
        "desc": "Deposit 1,000+ berries into your matrimonial joint vault.",
        "icon": "🏛️",
        "check": lambda s: s.get("joint_deposited", 0) >= 1000
    },
    "lovebirds": {
        "title": "Lovebirds",
        "desc": "Go on 3 romantic dates or exchange 5 loving kisses with your spouse.",
        "icon": "🕊️",
        "check": lambda s: (s.get("date_count", 0) >= 3) or (s.get("kiss_count", 0) >= 5)
    },
    "golden_anniversary": {
        "title": "Golden Vow",
        "desc": "Etch a sacred wedding vow and wear a Golden Wedding Ring.",
        "icon": "✨",
        "check": lambda s: bool(s.get("vow")) and (s.get("inventory", {}).get("ring", 0) > 0)
    },
    "daily_streak_7": {
        "title": "Daily Devotee",
        "desc": "Maintain a 7-day daily berry allowance streak.",
        "icon": "🔥",
        "check": lambda s: s.get("daily_streak", 0) >= 7
    },
    "taskmaster": {
        "title": "Taskmaster",
        "desc": "Complete all everyday daily tasks in a single day.",
        "icon": "📋",
        "check": lambda s: s.get("tasks_completed_count", 0) >= 1
    },
    "music_vibes": {
        "title": "Certified Audiophile",
        "desc": "Interact with Yuna's music player or Discord RPC 5 times.",
        "icon": "🎧",
        "check": lambda s: s.get("music_interactions", 0) >= 5
    },

    # ── Dice Gambling ──
    "dice_novice": {
        "title": "First Roll",
        "desc": "Roll the dice in Yuna's casino for the first time.",
        "icon": "🎲",
        "check": lambda s: s.get("dice_games_played", 0) >= 1
    },
    "dice_snake_eyes": {
        "title": "Snake Eyes",
        "desc": "Roll a double 1 (sum of 2) in Dice gambling.",
        "icon": "🐍",
        "check": lambda s: s.get("dice_snake_eyes_count", 0) >= 1
    },
    "dice_boxcars": {
        "title": "Midnight Boxcars",
        "desc": "Roll a double 6 (sum of 12) in Dice gambling.",
        "icon": "🚂",
        "check": lambda s: s.get("dice_boxcars_count", 0) >= 1
    },
    "dice_seven_heaven": {
        "title": "Lucky Seven",
        "desc": "Correctly predict and win a bet on exact Seven in Dice.",
        "icon": "7️⃣",
        "check": lambda s: s.get("dice_seven_wins", 0) >= 1
    },
    "dice_master": {
        "title": "Master of the Bones",
        "desc": "Win 10 games of Dice in Yuna's casino.",
        "icon": "🎲",
        "check": lambda s: s.get("dice_games_won", 0) >= 10
    },
    "dice_craps_king": {
        "title": "Dice High Roller",
        "desc": "Win 10,000+ berries in a single Dice roll.",
        "icon": "💎",
        "check": lambda s: s.get("dice_max_win", 0) >= 10000
    },

    # ── Boss Fight & Dark Lore ──
    "cardboard_scam": {
        "title": "Cardboard Warrior",
        "desc": "Swing the 5 Billion Berry Legendary Sword in battle only for it to snap into cardboard shards.",
        "icon": "📦",
        "check": lambda s: s.get("inventory", {}).get("cardboard_shards", 0) >= 1 or s.get("scammed_cardboard", False)
    },
    "dark_bargain": {
        "title": "Devil's Bargain",
        "desc": "Negotiate a dark pact with Juny and receive the Devil's Contract.",
        "icon": "📜",
        "check": lambda s: s.get("inventory", {}).get("devil_contract", 0) >= 1 or s.get("title") == "Devil's Slave" or s.get("dark_bargain", False)
    },
    "chicken_run": {
        "title": "Coward's Escape",
        "desc": "Chicken out of answering a comrade's call to aid against Juny.",
        "icon": "🐔",
        "check": lambda s: s.get("chickened_out_count", 0) >= 1
    },
    "angelic_mercy": {
        "title": "Heavenly Mercy",
        "desc": "Successfully plead with Juny and escape her divine wrath.",
        "icon": "🕊️",
        "check": lambda s: s.get("pleaded_juny_success", 0) >= 1
    },
    "party_champion": {
        "title": "Vanguard Hero",
        "desc": "Answer a comrade's call to aid and join their boss battle against Juny.",
        "icon": "🛡️",
        "check": lambda s: s.get("joined_boss_fights", 0) >= 1
    },

    # ── Karmic Catastrophes & Morality ──
    "karmic_victim": {
        "title": "Final Destination",
        "desc": "Perish from one of the 25 absurd karmic deaths during Blackjack.",
        "icon": "💀",
        "check": lambda s: s.get("karmic_deaths", 0) >= 1
    },
    "shark_bait": {
        "title": "Sharknado Casualty",
        "desc": "Get crushed by a falling sky-shark during Blackjack.",
        "icon": "🦈",
        "check": lambda s: s.get("shark_deaths", 0) >= 1
    },
    "reborn_soul": {
        "title": "The Long Road Home",
        "desc": "Break a Sin lock by performing 5 good deeds to redeem your soul.",
        "icon": "🌅",
        "check": lambda s: s.get("sin_locks_broken", 0) >= 1
    },

    # ── High Stakes & Luxury ──
    "berry_millionaire": {
        "title": "Berry Millionaire",
        "desc": "Accumulate 1,000,000 🫐 in your pouch at once.",
        "icon": "💰",
        "check": lambda s: s.get("berries", 0) >= 1000000
    },
    "berry_multimillionaire": {
        "title": "Berry Whale",
        "desc": "Accumulate 10,000,000 🫐 in your pouch at once.",
        "icon": "🐋",
        "check": lambda s: s.get("berries", 0) >= 10000000
    },
    "big_spender": {
        "title": "Big Spender",
        "desc": "Purchase any luxury shop item worth 3,000,000 🫐 or more.",
        "icon": "💳",
        "check": lambda s: s.get("bought_expensive_item", False)
    },
    "ward_shattered": {
        "title": "Corrupted Aegis",
        "desc": "Have your Divine Ward corrupted and shattered by your high Sin.",
        "icon": "💔",
        "check": lambda s: s.get("ward_corrupted_count", 0) >= 1
    },
    "phantom_ghost": {
        "title": "Ghost in the Shadows",
        "desc": "Execute a successful robbery while cloaked under a Phantom Mask.",
        "icon": "🎭",
        "check": lambda s: s.get("phantom_steals_count", 0) >= 1
    },
    "on_a_roll": {
        "title": "On a Roll",
        "desc": "Achieve a consecutive win streak of 3 in casino gambling.",
        "icon": "🔥",
        "check": lambda s: s.get("max_win_streak", 0) >= 3
    },
    "hot_streak": {
        "title": "Untouchable Streak",
        "desc": "Achieve a scorching consecutive win streak of 7 in casino gambling.",
        "icon": "⚡",
        "check": lambda s: s.get("max_win_streak", 0) >= 7
    },
    "minefield_master": {
        "title": "Minefield Sweeper",
        "desc": "Successfully navigate and cash out with profit from Yuna's Minefield.",
        "icon": "💣",
        "check": lambda s: s.get("mines_won", 0) >= 1
    },
    "lexicon_gambler": {
        "title": "Master of Anagrams",
        "desc": "Conquer Stage 3 (Master Enigma) in Wordle Gamble.",
        "icon": "📚",
        "check": lambda s: s.get("wordle_max_stage", 0) >= 3
    },
    "ascended_lexicon": {
        "title": "Ascended God of Words",
        "desc": "Clear all 5 progressive stages in Wordle Gamble to achieve Ascended God status.",
        "icon": "👑",
        "check": lambda s: s.get("wordle_max_stage", 0) >= 5
    }
}

DAILY_TASKS_POOL = {
    "gamble": {
        "name": "🎲 High Roller",
        "desc": "Play any gambling game (HL, Flip, Crash, BJ, Mines, Wordle, Dice, Bet)",
        "target": 1,
        "reward": 75
    },
    "aid": {
        "name": "🤝 Helping Hand",
        "desc": "Aid someone with y!aid or y!doubleaid",
        "target": 1,
        "reward": 50
    },
    "generosity": {
        "name": "💖 Kind Soul",
        "desc": "Donate or gift berries (y!donate or y!give)",
        "target": 1,
        "reward": 60
    },
    "vibe": {
        "name": "🎶 Vibe Check",
        "desc": "Check your profile (y!bal) or Yuna's song (y!song)",
        "target": 1,
        "reward": 40
    }
}

# ─── STORAGE & PERSISTENCE ──────────────────────────────────────────────────

def _ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

class _CrossProcessLock:
    """Inter-process lock using fcntl on Termux filesystem."""
    def __init__(self):
        self.fp = None

    def __enter__(self):
        if FCNTL_AVAILABLE and fcntl:
            try:
                self.fp = open(LOCK_FILE_PATH, "a+")
                fcntl.flock(self.fp.fileno(), fcntl.LOCK_EX)
            except Exception:
                if self.fp:
                    try:
                        self.fp.close()
                    except Exception:
                        pass
                self.fp = None
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.fp is not None:
            try:
                fcntl.flock(self.fp.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                self.fp.close()
            except Exception:
                pass
            self.fp = None

def _load_data_sync() -> Tuple[Dict[str, Dict[str, Any]], Dict[str, dict], Dict[str, dict]]:
    """Loads raw json data from disk."""
    _ensure_dirs()
    if not GAMBLING_DATA_FILE.exists():
        return {}, {}, {}
    try:
        with open(GAMBLING_DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return (
                    data.get("users", {}),
                    data.get("joint_vaults", {}),
                    data.get("active_dares", {})
                )
            return {}, {}, {}
    except Exception as e:
        print(f"[YUNA GAMBLING ERROR] Failed to load {GAMBLING_DATA_FILE}: {e}")
        return {}, {}, {}

def _create_default_yuna() -> Dict[str, Any]:
    return {
        "berries": 100000,
        "virtue": 77,
        "sin": 77,
        "total_aids": 999,
        "successful_aids": 777,
        "failed_aids": 222,
        "refused_aids": 0,
        "total_lost_berries": 50000,
        "total_won_berries": 500000,
        "total_gambles": 1337,
        "bankrupt_count": 0,
        "last_gamble_day": "",
        "daily_gambles": 0,
        "spouse": None,
        "marriage_date": None,
        "divorce_count": 0,
        "steals_success": 9999,
        "total_donated": 0,
        "last_daily_date": "",
        "daily_streak": 99,
        "daily_tasks": {},
        "double_aid_count": 0,
        "joint_deposited": 0,
        "tasks_completed_count": 777,
        "fights_won": 420,
        "marriage_count": 0,
        "music_interactions": 0,
        "inventory": {"crown": 1, "ward": 99},
        "clover_active": True,
        "mask_active": False,
        "achievements": ["divine_ascension", "abyssal_descent", "high_roller", "banker_breaker"]
    }

def _ensure_fresh_data():
    """Checks if data on disk is newer than our in-memory cache and reloads if so."""
    global _USER_STATS, _JOINT_VAULTS, _ACTIVE_DARES, _LAST_FILE_MTIME, _DATA_LOADED, _USER_SNAPSHOTS, _VAULT_SNAPSHOTS, _DARE_SNAPSHOTS
    _ensure_dirs()
    if not GAMBLING_DATA_FILE.exists():
        if not _DATA_LOADED:
            _USER_STATS = {YUNA_USER_ID: _create_default_yuna()}
            _JOINT_VAULTS = {}
            _ACTIVE_DARES = {}
            _USER_SNAPSHOTS = {YUNA_USER_ID: json.dumps(_USER_STATS[YUNA_USER_ID], sort_keys=True)}
            _VAULT_SNAPSHOTS = {}
            _DARE_SNAPSHOTS = {}
            _LAST_FILE_MTIME = 0.0
            _DATA_LOADED = True
        return

    try:
        disk_mtime = os.path.getmtime(GAMBLING_DATA_FILE)
        if (not _DATA_LOADED) or (disk_mtime > _LAST_FILE_MTIME):
            with _CrossProcessLock():
                fresh_users, fresh_vaults, fresh_dares = _load_data_sync()
                _USER_STATS = fresh_users
                _JOINT_VAULTS = fresh_vaults
                _ACTIVE_DARES = fresh_dares
                _LAST_FILE_MTIME = os.path.getmtime(GAMBLING_DATA_FILE)
                _DATA_LOADED = True
                if YUNA_USER_ID not in _USER_STATS:
                    _USER_STATS[YUNA_USER_ID] = _create_default_yuna()
                _USER_SNAPSHOTS = {uid: json.dumps(u, sort_keys=True) for uid, u in _USER_STATS.items()}
                _VAULT_SNAPSHOTS = {vk: json.dumps(v, sort_keys=True) for vk, v in _JOINT_VAULTS.items()}
                _DARE_SNAPSHOTS = {duid: json.dumps(d, sort_keys=True) for duid, d in _ACTIVE_DARES.items()}
    except Exception as e:
        print(f"[YUNA GAMBLING ERROR] Failed to check/sync from disk: {e}")

def _save_data_sync(users_data: Optional[Dict[str, Dict[str, Any]]] = None):
    """Safely saves users, joint vaults, and active dares to disk using inter-process locking, merging, and atomic replacement."""
    global _USER_STATS, _JOINT_VAULTS, _ACTIVE_DARES, _LAST_FILE_MTIME, _DATA_LOADED, _USER_SNAPSHOTS, _VAULT_SNAPSHOTS, _DARE_SNAPSHOTS
    _ensure_dirs()
    if users_data is None:
        users_data = _USER_STATS

    with _CrossProcessLock():
        try:
            # 1. Read latest disk state to avoid clobbering other processes
            disk_users, disk_vaults, disk_dares = _load_data_sync()

            # Safety guard: Never wipe disk users if in-memory user dict is unexpectedly empty!
            if len(disk_users) > 0 and len(users_data) == 0:
                print(f"[YUNA GAMBLING SAFETY GUARD] In-memory user data is empty while disk has {len(disk_users)} users. Skipping disk wipe!")
                return

            # 2. Merge dirty users from this process into disk_users
            for uid, user_obj in users_data.items():
                curr_dump = json.dumps(user_obj, sort_keys=True)
                if uid not in _USER_SNAPSHOTS or curr_dump != _USER_SNAPSHOTS.get(uid):
                    disk_users[uid] = user_obj

            # 3. Merge dirty joint vaults
            for vk, vault_obj in _JOINT_VAULTS.items():
                curr_dump = json.dumps(vault_obj, sort_keys=True)
                if vk not in _VAULT_SNAPSHOTS or curr_dump != _VAULT_SNAPSHOTS.get(vk):
                    disk_vaults[vk] = vault_obj

            # 4. Merge active dares
            for d_uid, dare_obj in _ACTIVE_DARES.items():
                curr_dump = json.dumps(dare_obj, sort_keys=True)
                if d_uid not in _DARE_SNAPSHOTS or curr_dump != _DARE_SNAPSHOTS.get(d_uid):
                    disk_dares[d_uid] = dare_obj

            # 5. Safe backup of current database file
            if GAMBLING_DATA_FILE.exists():
                try:
                    bak_file = DATA_DIR / "yuna_gambling.json.bak"
                    shutil.copyfile(GAMBLING_DATA_FILE, bak_file)
                    # Keep timestamped snapshot in backups directory
                    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
                    snap_file = BACKUPS_DIR / f"yuna_gambling_{time.strftime('%Y%m%d_%H')}.json"
                    if not snap_file.exists():
                        shutil.copyfile(GAMBLING_DATA_FILE, snap_file)
                except Exception:
                    pass

            # 6. Write atomically via temp file in same directory as target file
            target_dir = GAMBLING_DATA_FILE.parent
            target_dir.mkdir(parents=True, exist_ok=True)
            temp_file = target_dir / f"yuna_gambling.tmp.{os.getpid()}.{int(time.time()*1000)}"
            payload = {
                "version": 3,
                "updated_at": time.time(),
                "users": disk_users,
                "joint_vaults": disk_vaults,
                "active_dares": disk_dares
            }
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            try:
                os.replace(temp_file, GAMBLING_DATA_FILE)
            except OSError as ose:
                if ose.errno == 18: # Cross-device link
                    shutil.move(temp_file, GAMBLING_DATA_FILE)
                else:
                    raise

            # 7. Update local caches and snapshots
            _USER_STATS = disk_users
            _JOINT_VAULTS = disk_vaults
            _ACTIVE_DARES = disk_dares
            _LAST_FILE_MTIME = os.path.getmtime(GAMBLING_DATA_FILE)
            _DATA_LOADED = True
            _USER_SNAPSHOTS = {uid: json.dumps(u, sort_keys=True) for uid, u in _USER_STATS.items()}
            _VAULT_SNAPSHOTS = {vk: json.dumps(v, sort_keys=True) for vk, v in _JOINT_VAULTS.items()}
            _DARE_SNAPSHOTS = {duid: json.dumps(d, sort_keys=True) for duid, d in _ACTIVE_DARES.items()}

        except Exception as e:
            print(f"[YUNA GAMBLING ERROR] Failed to save {GAMBLING_DATA_FILE}: {e}")

def _create_default_user() -> Dict[str, Any]:
    return {
        "berries": 0,
        "virtue": 0,
        "sin": 0,
        "total_aids": 0,
        "successful_aids": 0,
        "failed_aids": 0,
        "refused_aids": 0,
        "total_lost_berries": 0,
        "total_won_berries": 0,
        "total_gambles": 0,
        "bankrupt_count": 0,
        "last_gamble_day": "",
        "daily_gambles": 0,
        "spouse": None,
        "marriage_date": None,
        "divorce_count": 0,
        "steals_success": 0,
        "total_donated": 0,
        "last_daily_date": "",
        "daily_streak": 0,
        "daily_tasks": {},
        "double_aid_count": 0,
        "joint_deposited": 0,
        "tasks_completed_count": 0,
        "fights_won": 0,
        "marriage_count": 0,
        "music_interactions": 0,
        "inventory": {},
        "clover_active": False,
        "mask_active": False,
        "achievements": [],
        "gamble_win_streak": 0,
        "max_win_streak": 0,
        "total_gamble_wins": 0,
        "total_gamble_losses": 0,
        "mines_played": 0,
        "mines_won": 0,
        "mines_max_win": 0,
        "wordle_played": 0,
        "wordle_stages_cleared": 0,
        "wordle_max_stage": 0,
        "wordle_max_win": 0
    }

def _ensure_user_defaults(user: Dict[str, Any]) -> Dict[str, Any]:
    user.setdefault("berries", 0)
    user.setdefault("virtue", 0)
    user.setdefault("sin", 0)
    user.setdefault("spouse", None)
    user.setdefault("marriage_date", None)
    user.setdefault("divorce_count", 0)
    user.setdefault("last_daily_date", "")
    user.setdefault("daily_streak", 0)
    user.setdefault("daily_tasks", {})
    user.setdefault("double_aid_count", 0)
    user.setdefault("joint_deposited", 0)
    user.setdefault("tasks_completed_count", 0)
    user.setdefault("fights_won", 0)
    user.setdefault("marriage_count", 0)
    user.setdefault("music_interactions", 0)
    user.setdefault("inventory", {})
    user.setdefault("clover_active", False)
    user.setdefault("mask_active", False)
    user.setdefault("achievements", [])
    user.setdefault("good_actions_needed", 0)
    user.setdefault("bad_actions_needed", 0)
    user.setdefault("title", None)
    user.setdefault("bad_luck_actions", 0)
    user.setdefault("boss_double_bonus_actions", 0)
    user.setdefault("defeated_juny", False)
    user.setdefault("dice_games_played", 0)
    user.setdefault("dice_games_won", 0)
    user.setdefault("dice_snake_eyes_count", 0)
    user.setdefault("dice_boxcars_count", 0)
    user.setdefault("dice_seven_wins", 0)
    user.setdefault("dice_max_win", 0)
    user.setdefault("bought_expensive_item", False)
    user.setdefault("ward_corrupted_count", 0)
    user.setdefault("phantom_steals_count", 0)
    user.setdefault("karmic_deaths", 0)
    user.setdefault("shark_deaths", 0)
    user.setdefault("sin_locks_broken", 0)
    user.setdefault("pleaded_juny_success", 0)
    user.setdefault("joined_boss_fights", 0)
    user.setdefault("chickened_out_count", 0)
    user.setdefault("scammed_cardboard", False)
    user.setdefault("dark_bargain", False)
    user.setdefault("vow", None)
    user.setdefault("date_count", 0)
    user.setdefault("kiss_count", 0)
    user.setdefault("magnet_charges", 0)
    user.setdefault("loaded_die_active", False)
    user.setdefault("shield_blessed", False)
    user.setdefault("gamble_win_streak", 0)
    user.setdefault("max_win_streak", 0)
    user.setdefault("total_gamble_wins", 0)
    user.setdefault("total_gamble_losses", 0)
    user.setdefault("mines_played", 0)
    user.setdefault("mines_won", 0)
    user.setdefault("mines_max_win", 0)
    user.setdefault("wordle_played", 0)
    user.setdefault("wordle_stages_cleared", 0)
    user.setdefault("wordle_max_stage", 0)
    user.setdefault("wordle_max_win", 0)
    if YUNA_RPG_AVAILABLE and yuna_rpg:
        yuna_rpg.ensure_player_rpg(user)
    return user

async def _get_user_stats(user_id: str) -> Dict[str, Any]:
    global _USER_STATS
    async with _LOCK:
        _ensure_fresh_data()
        if user_id not in _USER_STATS:
            if user_id == YUNA_USER_ID:
                _USER_STATS[user_id] = _create_default_yuna()
            else:
                _USER_STATS[user_id] = _create_default_user()
            _save_data_sync(_USER_STATS)
        user = _USER_STATS[user_id]
        _ensure_user_defaults(user)
        return user

async def _atomic_multi_account_update(updates: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Atomically updates multiple user accounts in a single locked transaction,
    ensuring immediate persistence to disk and preventing dropped or desynced updates.
    Enforces Sin (30) & Virtue (33) caps, mutual exclusivity locks, and boss bonus multipliers.
    """
    global _USER_STATS
    async with _LOCK:
        _ensure_fresh_data()
        results = {}
        for spec in updates:
            uid = str(spec["user_id"])
            berries_delta = spec.get("berries_delta", 0)
            virtue_delta = spec.get("virtue_delta", 0)
            sin_delta = spec.get("sin_delta", 0)
            outcome = spec.get("outcome", "")
            is_gamble = spec.get("is_gamble", False)

            if uid not in _USER_STATS:
                if uid == YUNA_USER_ID:
                    _USER_STATS[uid] = _create_default_yuna()
                else:
                    _USER_STATS[uid] = _create_default_user()

            user = _USER_STATS[uid]
            _ensure_user_defaults(user)

            # Boss Victory 2x Bonus on everything
            if berries_delta > 0 and user.get("boss_double_bonus_actions", 0) > 0:
                berries_delta = berries_delta * 2
                user["boss_double_bonus_actions"] = max(0, user["boss_double_bonus_actions"] - 1)

            old_berries = user.get("berries", 0)
            old_virtue = user.get("virtue", 0)
            old_sin = user.get("sin", 0)
            new_berries = max(0, old_berries + berries_delta)
            user["berries"] = new_berries

            # ── Morality Mutual Exclusivity & 5-Action Break Locks ──
            # If user earns Sin, cannot earn Virtue until 5 good actions are completed
            if virtue_delta > 0:
                needed = user.get("good_actions_needed", 0)
                if needed > 0:
                    user["good_actions_needed"] = max(0, needed - 1)
                    if user["good_actions_needed"] == 0:
                        user["sin_locks_broken"] = user.get("sin_locks_broken", 0) + 1
                    virtue_delta = 0 # Blocked until all 5 good actions are done
                else:
                    user["bad_actions_needed"] = 5 # Locking sin until 5 bad actions

            # If user earns Virtue, cannot earn Sin until 5 bad actions are completed
            if sin_delta > 0:
                needed = user.get("bad_actions_needed", 0)
                if needed > 0:
                    user["bad_actions_needed"] = max(0, needed - 1)
                    sin_delta = 0 # Blocked until all 5 bad actions are done
                else:
                    user["good_actions_needed"] = 5 # Locking virtue until 5 good actions

            # Caps: Virtue limit 33, Sin limit 30
            user["virtue"] = min(33, max(0, user.get("virtue", 0) + virtue_delta))
            user["sin"] = min(30, max(0, user.get("sin", 0) + sin_delta))

            # Audit logging of changes
            if old_berries != new_berries:
                _log_player_stat_audit(uid, "berries", f"{old_berries:,}", f"{new_berries:,}", f"delta={berries_delta:+,} outcome={outcome}")
            if old_virtue != user["virtue"]:
                _log_player_stat_audit(uid, "virtue", old_virtue, user["virtue"], f"delta={virtue_delta:+,} outcome={outcome}")
            if old_sin != user["sin"]:
                _log_player_stat_audit(uid, "sin", old_sin, user["sin"], f"delta={sin_delta:+,} outcome={outcome}")

            # Bankruptcy tracking
            if old_berries > 0 and new_berries == 0:
                user["bankrupt_count"] = user.get("bankrupt_count", 0) + 1

            # Loss / Win tracking
            if berries_delta < 0:
                user["total_lost_berries"] = user.get("total_lost_berries", 0) + abs(berries_delta)
            elif berries_delta > 0:
                user["total_won_berries"] = user.get("total_won_berries", 0) + berries_delta

            # Daily gamble counter
            if is_gamble:
                today_str = time.strftime("%Y-%m-%d")
                if user.get("last_gamble_day") != today_str:
                    user["last_gamble_day"] = today_str
                    user["daily_gambles"] = 0
                user["daily_gambles"] = user.get("daily_gambles", 0) + 1
                user["total_gambles"] = user.get("total_gambles", 0) + 1

            # Morality outcome tracking
            if outcome:
                user["total_aids"] = user.get("total_aids", 0) + 1
                if outcome == "success":
                    user["successful_aids"] = user.get("successful_aids", 0) + 1
                elif outcome == "mess_up":
                    user["failed_aids"] = user.get("failed_aids", 0) + 1
                elif outcome == "refused":
                    user["refused_aids"] = user.get("refused_aids", 0) + 1
                elif outcome == "steal_success":
                    user["steals_success"] = user.get("steals_success", 0) + 1

            results[uid] = dict(user)

        _save_data_sync(_USER_STATS)
        return results

async def _update_user_stats(
    user_id: str,
    berries_delta: int = 0,
    virtue_delta: int = 0,
    sin_delta: int = 0,
    outcome: str = "",
    is_gamble: bool = False
) -> Dict[str, Any]:
    res = await _atomic_multi_account_update([{
        "user_id": user_id,
        "berries_delta": berries_delta,
        "virtue_delta": virtue_delta,
        "sin_delta": sin_delta,
        "outcome": outcome,
        "is_gamble": is_gamble
    }])
    return res[str(user_id)]

async def _get_yuna_stats() -> Dict[str, Any]:
    return await _get_user_stats(YUNA_USER_ID)

async def _update_yuna_balance(delta: int) -> Dict[str, Any]:
    return await _update_user_stats(YUNA_USER_ID, berries_delta=delta)

# ─── MORALITY & GAMBLING BONUSES ────────────────────────────────────────────

def get_effective_morality(stats: dict) -> Tuple[int, int]:
    """
    Returns (effective_virtue, effective_sin).
    Sin and Virtue cannot co-work together: whichever is higher takes full priority.
    If tied, both are 0.
    """
    v = stats.get("virtue", 0)
    s = stats.get("sin", 0)
    if v > s:
        return v, 0
    elif s > v:
        return 0, s
    return 0, 0

def get_sin_warning_banner(stats: dict) -> str:
    """Returns warning banner if user holds 20-25 Sin."""
    eff_v, eff_s = get_effective_morality(stats)
    if 20 <= eff_s <= 25:
        return (
            f"\n⚠️ **WARNING FROM THE ABYSS:** You hold **{eff_s}/30 Sin**!\n"
            f"😈 **Juny, Heaven's Worst Angel**, is circling above...\n"
            f"She will come to claim your soul at 26–30 Sin! Repent before it is too late!"
        )
    return ""

def calculate_virtue_kind_bonus(stats: dict, base_payout: int) -> Tuple[int, str]:
    """
    Virtue boosts kind acts (aid, doubleaid, work, fish):
    - Scales +0.02% of user balance added to reward
    - Payout scales +0.2x per Virtue point
    - Increases all positive effects effectiveness by 1% per 2 Virtue points
    """
    eff_v, _ = get_effective_morality(stats)
    if eff_v <= 0:
        return 0, ""
    bal = stats.get("berries", 0)
    bal_bonus = int(bal * 0.0002) # 0.02% of balance
    payout_bonus = int(base_payout * (eff_v * 0.2)) # 0.2x per virtue point
    pos_mult = 1.0 + (eff_v // 2) * 0.01 # +1% per 2 virtue points
    total = int((bal_bonus + payout_bonus) * pos_mult)
    if total <= 0:
        return 0, ""
    return total, f" ✨ *(💖 Virtue Grace: +{total:,} 🫐)*"

def get_sin_protection_failure_rate(sin: int) -> float:
    """
    Returns the failure chance of defensive equipment (Heavenly Shield / Divine Ward)
    based on the user's Sin points:
    0–5 Sin:   0% (0.00)
    6–10 Sin:  5% (0.05)
    11–15 Sin: 10% (0.10)
    16–20 Sin: 15% (0.15)
    21–25 Sin: 25% (0.25)
    26–30 Sin: 40% (0.40)
    """
    if sin <= 5:
        return 0.0
    elif sin <= 10:
        return 0.05
    elif sin <= 15:
        return 0.10
    elif sin <= 20:
        return 0.15
    elif sin <= 25:
        return 0.25
    else:
        return 0.40

def resolve_sin_shield_corruption(sin: int, user_id: Optional[str] = None) -> dict:
    """
    Evaluates whether defensive equipment is corrupted by the user's sins and determines the outcome.
    If the user has consecrated their shield with Blessed Holy Water, corruption is prevented!
    Possible corrupted outcomes:
    - catastrophic_explosion (at 26-30 Sin: "I have prepared for this" / "Have you?" / fucking explodes)
    - fails (shield fails to activate)
    - partial (shield only blocks 50% damage/theft)
    - breaks_after (shield blocks, but breaks completely after activation)
    - penalty (shield blocks, but inflicts penalty on sinful user)
    """
    if user_id:
        u_stat = _USER_STATS.get(str(user_id), {})
        if u_stat.get("shield_blessed"):
            u_stat["shield_blessed"] = False
            _save_data_sync(_USER_STATS)
            return {"corrupted": False, "outcome": "normal", "failure_rate": 0.0, "blessed": True}

    failure_rate = get_sin_protection_failure_rate(sin)
    if failure_rate <= 0:
        return {"corrupted": False, "outcome": "normal", "failure_rate": 0.0}
    
    is_corrupted = (random.random() < failure_rate)
    if not is_corrupted:
        return {"corrupted": False, "outcome": "normal", "failure_rate": failure_rate}
    
    if sin >= 26:
        outcome = "catastrophic_explosion"
    else:
        outcome = random.choice(["fails", "partial", "breaks_after", "penalty"])
        
    return {"corrupted": True, "outcome": outcome, "failure_rate": failure_rate}


def get_virtue_title(virtue: int) -> str:
    if virtue >= 30:
        return "Seraphim Sovereign"
    elif virtue >= 20:
        return "Archangel of Light"
    elif virtue >= 10:
        return "Blessed Saint"
    elif virtue >= 5:
        return "Kind Samaritan"
    elif virtue > 0:
        return "Gentle Soul"
    return "Neutral"

def get_sin_title(sin: int) -> str:
    if sin >= 26:
        return "Juny's Marked Prey"
    elif sin >= 20:
        return "Underworld Menace"
    elif sin >= 10:
        return "Rogue Outlaw"
    elif sin >= 5:
        return "Mischief Maker"
    elif sin > 0:
        return "Petty Sinner"
    return "Clean"

async def check_sin_gamble_bonus(user_id: str, profit: int, game: str = "") -> Tuple[int, str]:
    """Calculates gambling extra payout multiplier (+0.1x per Sin) if user has effective Sin. Disabled on crash."""
    if profit <= 0 or (game and game.lower() == "crash"):
        return 0, ""
    stats = await _get_user_stats(user_id)
    _, eff_s = get_effective_morality(stats)
    if eff_s <= 0:
        return 0, ""
    mult = eff_s * 0.1
    bonus = max(1, int(profit * mult))
    return bonus, f" 🔥 *(❤️‍🔥 Sin Payout +{mult:.1f}x: +{bonus:,} 🫐)*"

async def record_gamble_win(user_id: str) -> Tuple[int, int]:
    """Increments user's gamble win streak and updates all-time max win streak."""
    async with _LOCK:
        _ensure_fresh_data()
        stats = _USER_STATS.setdefault(str(user_id), {})
        _ensure_user_defaults(stats)
        streak = stats.get("gamble_win_streak", 0) + 1
        stats["gamble_win_streak"] = streak
        stats["max_win_streak"] = max(stats.get("max_win_streak", 0), streak)
        stats["total_gamble_wins"] = stats.get("total_gamble_wins", 0) + 1
        _save_data_sync(_USER_STATS)
        return streak, stats["max_win_streak"]

async def record_gamble_loss(user_id: str) -> int:
    """Resets user's gamble win streak to 0 and records gamble loss."""
    async with _LOCK:
        _ensure_fresh_data()
        stats = _USER_STATS.setdefault(str(user_id), {})
        _ensure_user_defaults(stats)
        old_streak = stats.get("gamble_win_streak", 0)
        stats["gamble_win_streak"] = 0
        stats["total_gamble_losses"] = stats.get("total_gamble_losses", 0) + 1
        _save_data_sync(_USER_STATS)
        return old_streak

async def get_gamble_win_bonuses(user_id: str, profit: int, game: str = "") -> Tuple[int, str]:
    """Calculates combined Marriage (+15%/+25%), Sin (+0.1x per Sin, excl. crash), Magnet (+20%), and Win Streak profit bonuses."""
    total_bonus = 0
    notices = []
    if profit > 0:
        m_bonus, m_txt = await check_marriage_earn_bonus(user_id, profit)
        if m_bonus > 0:
            total_bonus += m_bonus
            notices.append(m_txt.strip())
        s_bonus, s_txt = await check_sin_gamble_bonus(user_id, profit, game=game)
        if s_bonus > 0:
            total_bonus += s_bonus
            notices.append(s_txt.strip())
        stats = await _get_user_stats(user_id)
        mag_charges = stats.get("magnet_charges", 0)
        if mag_charges > 0:
            mag_bonus = max(1, int(profit * 0.20))
            total_bonus += mag_bonus
            rem = mag_charges - 1
            async with _LOCK:
                _USER_STATS[user_id]["magnet_charges"] = rem
                _save_data_sync(_USER_STATS)
            notices.append(f"🧲 *(+20% Berry Magnet: +{mag_bonus:,} 🫐 [{rem} left])*")

        # Win Streak Profit Bonus (+5% per win above 1, capped at +50%) & Milestone Windfalls
        streak = stats.get("gamble_win_streak", 0)
        if streak >= 2:
            pct = min(50, (streak - 1) * 5)
            streak_bonus = max(1, int(profit * (pct / 100.0)))
            milestone = 0
            if streak == 3:
                milestone = 100
            elif streak == 5:
                milestone = 300
            elif streak == 7:
                milestone = 600
            elif streak == 10:
                milestone = 1500
            elif streak == 15:
                milestone = 3000
            elif streak == 20:
                milestone = 7500

            total_s_bonus = streak_bonus + milestone
            total_bonus += total_s_bonus
            mile_str = f" + 🏆 Milestone +{milestone:,} 🫐!" if milestone > 0 else ""
            notices.append(f"🔥 *(Win Streak #{streak}: +{pct}% [{total_s_bonus:,} 🫐]{mile_str})*")

    notice_str = (" " + " ".join(notices)) if notices else ""
    return total_bonus, notice_str

# ─── JOINT VAULT & DAILY TASK HELPERS ───────────────────────────────────────

def _get_vault_key(uid1: str, uid2: str) -> str:
    """Returns a canonical string key for two married spouses."""
    return ":".join(sorted([str(uid1), str(uid2)]))

def _get_joint_vault(uid1: str, uid2: str) -> dict:
    """Gets or initializes the shared matrimonial bank vault for a married couple."""
    global _JOINT_VAULTS
    _ensure_fresh_data()
    vkey = _get_vault_key(uid1, uid2)
    if vkey not in _JOINT_VAULTS:
        _JOINT_VAULTS[vkey] = {
            "spouses": sorted([str(uid1), str(uid2)]),
            "balance": 0,
            "total_deposited": 0,
            "total_withdrawn": 0,
            "last_interest_date": ""
        }
    return _JOINT_VAULTS[vkey]

def _accrue_vault_interest(vault: dict) -> Tuple[int, bool]:
    """Accrues +5% (or +10% with Eternal Diamond) daily love interest once per calendar day (UTC)."""
    today_str = time.strftime("%Y-%m-%d", time.gmtime())
    if vault.get("balance", 0) <= 0:
        return 0, False
    if vault.get("last_interest_date") == today_str:
        return 0, False

    # Check for Eternal Diamond in spouses' inventory
    has_diamond = False
    for sp_id in vault.get("spouses", []):
        u_stat = _USER_STATS.get(str(sp_id), {})
        if u_stat.get("inventory", {}).get("diamond", 0) > 0:
            has_diamond = True
            break

    rate = 0.10 if has_diamond else 0.05
    max_cap = 1000 if has_diamond else 500
    interest = min(max_cap, max(1, int(vault["balance"] * rate)))
    vault["balance"] += interest
    vault["last_interest_date"] = today_str
    return interest, True

async def check_marriage_earn_bonus(user_id: str, profit: int) -> Tuple[int, str]:
    """Calculates marriage extra earn (+15% or +25% with Golden Wedding Ring) if the user has a spouse."""
    if profit <= 0:
        return 0, ""
    stats = await _get_user_stats(user_id)
    spouse_id = stats.get("spouse")
    if not spouse_id:
        return 0, ""
    has_ring = stats.get("inventory", {}).get("ring", 0) > 0
    pct = 0.25 if has_ring else 0.15
    bonus = max(1, int(profit * pct))
    ring_lbl = " 💍 Golden Ring" if has_ring else ""
    return bonus, f" 💍 *(Marriage Profit Boost +{int(pct*100)}%{ring_lbl}: +{bonus:,} 🫐)*"

def _get_user_daily_tasks(user_stats: Dict[str, Any]) -> dict:
    """Gets or initializes the user's daily task list for today."""
    today_str = time.strftime("%Y-%m-%d", time.gmtime())
    user_dt = user_stats.get("daily_tasks")
    if not user_dt or user_dt.get("date") != today_str:
        user_dt = {
            "date": today_str,
            "tasks": {
                "gamble": {
                    "name": DAILY_TASKS_POOL["gamble"]["name"],
                    "desc": DAILY_TASKS_POOL["gamble"]["desc"],
                    "target": 1,
                    "progress": 0,
                    "reward": 75,
                    "claimed": False
                },
                "aid": {
                    "name": DAILY_TASKS_POOL["aid"]["name"],
                    "desc": DAILY_TASKS_POOL["aid"]["desc"],
                    "target": 1,
                    "progress": 0,
                    "reward": 50,
                    "claimed": False
                },
                "generosity": {
                    "name": DAILY_TASKS_POOL["generosity"]["name"],
                    "desc": DAILY_TASKS_POOL["generosity"]["desc"],
                    "target": 1,
                    "progress": 0,
                    "reward": 60,
                    "claimed": False
                },
                "vibe": {
                    "name": DAILY_TASKS_POOL["vibe"]["name"],
                    "desc": DAILY_TASKS_POOL["vibe"]["desc"],
                    "target": 1,
                    "progress": 0,
                    "reward": 40,
                    "claimed": False
                }
            },
            "all_bonus_claimed": False
        }
        user_stats["daily_tasks"] = user_dt
    return user_dt

async def record_task_progress(user_id: str, task_key: str, amount: int = 1) -> Optional[str]:
    """Records progress for a daily task and auto-credits berry rewards upon completion."""
    notification = None
    async with _LOCK:
        _ensure_fresh_data()
        if user_id not in _USER_STATS:
            return None
        user = _USER_STATS[user_id]
        dt = _get_user_daily_tasks(user)
        tasks = dt.get("tasks", {})
        if task_key not in tasks:
            return None
        t = tasks[task_key]
        if t.get("claimed", False):
            return None

        t["progress"] = min(t["target"], t.get("progress", 0) + amount)
        if t["progress"] >= t["target"] and not t["claimed"]:
            t["claimed"] = True
            reward = t["reward"]
            user["berries"] = user.get("berries", 0) + reward
            notification = f"✨ **Daily Task Completed:** [{t['name']}]! (+{reward} 🫐)"

            all_done = all(tk.get("claimed", False) for tk in tasks.values())
            if all_done and not dt.get("all_bonus_claimed", False):
                dt["all_bonus_claimed"] = True
                user["tasks_completed_count"] = user.get("tasks_completed_count", 0) + 1
                grand_bonus = 200
                if user.get("spouse"):
                    grand_bonus += 40
                user["berries"] = user.get("berries", 0) + grand_bonus
                user["virtue"] = user.get("virtue", 0) + 2
                notification += f"\n🎉 **ALL DAILY TASKS COMPLETED!** Grand Bounty: **+{grand_bonus} 🫐** & **+2 💖** Virtue!"

        _save_data_sync(_USER_STATS)

    if notification:
        await check_and_award_achievements(user_id, specific_id="taskmaster")
    return notification

async def check_and_award_achievements(user_id: str, specific_id: str = None) -> List[dict]:
    """Checks for newly unlocked achievements and records them."""
    global _USER_STATS
    newly_unlocked = []
    async with _LOCK:
        _ensure_fresh_data()
        user = _USER_STATS.get(user_id)
        if not user:
            return []
        
        user_achs = set(user.get("achievements", []))
        
        if specific_id and specific_id in ACHIEVEMENTS and specific_id not in user_achs:
            user_achs.add(specific_id)
            user["achievements"] = list(user_achs)
            newly_unlocked.append(ACHIEVEMENTS[specific_id])

        for ach_id, ach_info in ACHIEVEMENTS.items():
            if ach_id not in user_achs:
                if ach_info["check"](user):
                    user_achs.add(ach_id)
                    user["achievements"] = list(user_achs)
                    newly_unlocked.append(ach_info)

        if newly_unlocked:
            _save_data_sync(_USER_STATS)

    return newly_unlocked

def format_achievement_banner(unlocked_list: List[dict]) -> str:
    """Formats celebratory banners for newly unlocked achievements."""
    if not unlocked_list:
        return ""
    lines = []
    for ach in unlocked_list:
        lines.append(f"🏆 **ACHIEVEMENT UNLOCKED: [{ach['title']}]** — *{ach['desc']}*")
    return "\n" + "\n".join(lines)

# ─── REPLY HELPER ───────────────────────────────────────────────────────────

async def _safe_send_reply(message, content: Optional[str] = None, view: Optional[View] = None, embed: Optional[discord.Embed] = None):
    """Replies directly to message without ping notification, supporting embeds, views, and AI context logging."""
    sent_msg = None
    try:
        kwargs = {"mention_author": False}
        if content is not None:
            kwargs["content"] = content
        if view is not None:
            kwargs["view"] = view
        if embed is not None:
            kwargs["embed"] = embed
        sent_msg = await message.reply(**kwargs)
    except Exception:
        try:
            kwargs = {}
            if content is not None:
                kwargs["content"] = content
            if view is not None:
                kwargs["view"] = view
            if embed is not None:
                kwargs["embed"] = embed
            sent_msg = await message.channel.send(**kwargs)
        except Exception as e:
            print(f"[YUNA GAMBLING ERROR] Could not send reply: {e}")
            return None

    # RECORD INTO CONVERSATION CONTEXT SO YUNA AI CAN READ COMMANDS & OUTCOMES
    if _CONTEXT_LOGGER and message:
        try:
            summary = content or ""
            if embed:
                summary = f"[Embed: {embed.title or ''}] {embed.description or ''}"
                for fld in getattr(embed, "fields", []):
                    summary += f" | {fld.name}: {fld.value}"
            _CONTEXT_LOGGER(
                channel_id=message.channel.id,
                user_id=message.author.id,
                user_name=message.author.display_name,
                user_cmd=message.content,
                reply_text=summary[:500]
            )
        except Exception as _ce:
            pass

    return sent_msg

# ─── CARD LOGIC FOR BLACKJACK ───────────────────────────────────────────────

SUITS = ["♠️", "♥️", "♦️", "♣️"]
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]

def draw_card() -> Tuple[str, int, str, str]:
    if random.random() < 0.04:  # 4% low odds comedy card!
        c = random.choice(COMEDY_CARDS)
        return (c[0], c[1], c[2], c[3])
    rank = random.choice(RANKS)
    suit = random.choice(SUITS)
    if rank in ["J", "Q", "K"]:
        val = 10
    elif rank == "A":
        val = 11
    else:
        val = int(rank)
    return (rank, val, suit, f"`[{rank}{suit}]`")

def calculate_hand(cards: List[Tuple[str, int, str, str]]) -> int:
    total = sum(c[1] for c in cards)
    aces = sum(1 for c in cards if c[0] == "A")
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total

# ─── POKER & ROULETTE LOGIC & CONSTANTS ─────────────────────────────────────

ROULETTE_REDS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
ROULETTE_BLACKS = {2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35}

POKER_RANKS = [
    ("2", 2), ("3", 3), ("4", 4), ("5", 5), ("6", 6),
    ("7", 7), ("8", 8), ("9", 9), ("10", 10),
    ("J", 11), ("Q", 12), ("K", 13), ("A", 14)
]
POKER_SUITS = ["♠️", "♥️", "♦️", "♣️"]

def create_poker_deck() -> List[Tuple[str, str, int, str]]:
    deck = []
    for r_str, r_val in POKER_RANKS:
        for s in POKER_SUITS:
            deck.append((r_str, s, r_val, f"[{r_str}{s}]"))
    random.shuffle(deck)
    return deck

def evaluate_poker_hand(cards: List[Tuple[str, str, int, str]]) -> Tuple[str, int, str]:
    """
    Evaluates a 5-card poker hand and returns (hand_name, payout_multiplier, desc).
    Multipliers:
      - Royal Flush: 250x (Maximum Jackpot!)
      - Straight Flush: 50x
      - Four of a Kind: 25x
      - Full House: 9x
      - Flush: 6x
      - Straight: 4x
      - Three of a Kind: 3x
      - Two Pair: 2x
      - Jacks or Better: 1x
      - Low Hand: 0x
    """
    vals = sorted([c[2] for c in cards])
    suits = [c[1] for c in cards]
    is_flush = len(set(suits)) == 1

    is_straight = False
    if len(set(vals)) == 5:
        if vals[4] - vals[0] == 4:
            is_straight = True
        elif vals == [2, 3, 4, 5, 14]:  # Ace-low straight A-2-3-4-5
            is_straight = True

    counts = {}
    for v in vals:
        counts[v] = counts.get(v, 0) + 1
    freq = sorted(counts.values(), reverse=True)

    if is_flush and is_straight:
        if vals == [10, 11, 12, 13, 14]:
            return "Royal Flush", 250, "👑 **ROYAL FLUSH!** The rarest hand in poker! Legendary perfection!"
        return "Straight Flush", 50, "🌟 **STRAIGHT FLUSH!** 5 consecutive cards of the exact same suit!"

    if freq == [4, 1]:
        return "Four of a Kind", 25, "🔥 **FOUR OF A KIND!** Four cards of the identical rank!"

    if freq == [3, 2]:
        return "Full House", 9, "🏠 **FULL HOUSE!** Three of a kind plus a pair!"

    if is_flush:
        return "Flush", 6, "🌊 **FLUSH!** 5 cards of the matching suit!"

    if is_straight:
        return "Straight", 4, "⚡ **STRAIGHT!** 5 consecutive card ranks!"

    if freq == [3, 1, 1]:
        return "Three of a Kind", 3, "🎯 **THREE OF A KIND!** Triple matching cards!"

    if freq == [2, 2, 1]:
        return "Two Pair", 2, "✌️ **TWO PAIR!** Two distinct card pairs!"

    if freq == [2, 1, 1, 1]:
        pair_val = [k for k, v in counts.items() if v == 2][0]
        if pair_val >= 11:
            rank_name = {11: "Jacks", 12: "Queens", 13: "Kings", 14: "Aces"}[pair_val]
            return f"Pair of {rank_name}", 1, f"🃏 **JACKS OR BETTER!** Pair of {rank_name}! Bet returned!"
        else:
            return "Low Pair", 0, "Pair below Jacks. (No payout for low pairs)"

    return "High Card", 0, "High Card. Better luck next hand!"

def format_poker_message(game_state: dict) -> str:
    hand = game_state["hand"]
    held = game_state["held"]
    cards_display = []
    for i, c in enumerate(hand):
        status = "🔒 HELD" if i in held else "DROP"
        cards_display.append(f"`[{c[0]}{c[1]}]` *({status})*")
    
    return (
        f"🃏 **YUNA'S VIDEO POKER** 🃏\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Player: {game_state['author_mention']} | Wager: **{game_state['amount']:,}** 🫐\n\n"
        f"**Your 5 Cards:**\n"
        f"{'  '.join(cards_display)}\n\n"
        f"💡 Click card buttons to toggle **[🔒 Hold]**, then click **[🔄 Draw / Swap Cards]**!\n"
        f"*(Or type `y!hold 1 2 5` then `y!draw`)*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

# ─── DISCORD UI VIEWS ───────────────────────────────────────────────────────

def refresh_view_timeout(view: Optional[View], seconds: Optional[float] = None) -> None:
    """Refreshes a Discord UI View's inactivity timeout so active players are never timed out early."""
    if not view:
        return
    try:
        if seconds is not None:
            view.timeout = seconds
        if hasattr(view, "_refresh_timeout"):
            view._refresh_timeout()
        elif hasattr(view, "_BaseView__timeout_expiry") and view.timeout:
            setattr(view, "_BaseView__timeout_expiry", time.monotonic() + view.timeout)
    except Exception:
        pass


class BlackjackView(View):
    def __init__(self, author_id: str, game_state: dict):
        super().__init__(timeout=300.0)
        self.author_id = author_id
        self.game_state = game_state

    async def on_timeout(self):
        if self.author_id in _ACTIVE_BLACKJACK_GAMES:
            game = _ACTIVE_BLACKJACK_GAMES.pop(self.author_id, None)
            if game and not game.get("finished"):
                game["finished"] = True
                bet = game.get("bet", 0)
                await _update_user_stats(self.author_id, berries_delta=bet)
                for child in self.children:
                    child.disabled = True
                timeout_text = (
                    f"⏰ **BLACKJACK TABLE CLOSED (INACTIVITY)** ⏰\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"<@{self.author_id}>'s blackjack hand timed out after 5 minutes of inactivity.\n"
                    f"💸 Wager of **{bet:,} 🫐** was refunded to your balance.\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                if game.get("message"):
                    try:
                        await game["message"].edit(content=timeout_text, view=self)
                    except Exception:
                        pass

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary, emoji="🃏")
    async def hit_button(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) != self.author_id:
            await interaction.response.send_message("This isn't your blackjack hand, mortal!", ephemeral=True)
            return
        await interaction.response.defer()
        await process_blackjack_turn(self.game_state, action="hit", interaction=interaction, view=self)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary, emoji="🛑")
    async def stand_button(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) != self.author_id:
            await interaction.response.send_message("This isn't your blackjack hand, mortal!", ephemeral=True)
            return
        await interaction.response.defer()
        await process_blackjack_turn(self.game_state, action="stand", interaction=interaction, view=self)


class CrashView(View):
    def __init__(self, author_id: str, game_state: dict):
        super().__init__(timeout=300.0)
        self.author_id = author_id
        self.game_state = game_state

    async def on_timeout(self):
        if self.author_id in _ACTIVE_CRASH_GAMES:
            game = _ACTIVE_CRASH_GAMES.pop(self.author_id, None)
            if game and not game.get("finished"):
                game["finished"] = True
                for item in self.children:
                    item.disabled = True

    @discord.ui.button(label="💰 Cash Out", style=discord.ButtonStyle.success)
    async def cashout_button(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) != self.author_id:
            await interaction.response.send_message("Hands off! This isn't your crash game!", ephemeral=True)
            return
        await interaction.response.defer()
        await process_crash_cashout(self.game_state, interaction=interaction, view=self)


class ChallengeView(View):
    def __init__(self, target_id: str, author_id: str, challenge_type: str, data: dict):
        super().__init__(timeout=180.0)
        self.target_id = target_id
        self.author_id = author_id
        self.challenge_type = challenge_type
        self.data = data

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, emoji="✅")
    async def accept_btn(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) != self.target_id:
            await interaction.response.send_message("Only the challenged user can accept!", ephemeral=True)
            return
        await interaction.response.defer()
        await execute_challenge_resolution(self.data, accepted=True, interaction=interaction, view=self)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger, emoji="❌")
    async def decline_btn(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) not in (self.target_id, self.author_id):
            await interaction.response.send_message("You cannot decline this challenge!", ephemeral=True)
            return
        await interaction.response.defer()
        await execute_challenge_resolution(self.data, accepted=False, interaction=interaction, view=self)


class SoloDareView(View):
    def __init__(self, target_id: str):
        super().__init__(timeout=600.0)
        self.target_id = target_id

    @discord.ui.button(label="Reroll Prompt (1 Free)", style=discord.ButtonStyle.secondary, emoji="🎲")
    async def reroll_btn(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) != self.target_id:
            await interaction.response.send_message("This isn't your dare to reroll, mortal!", ephemeral=True)
            return
        await interaction.response.defer()
        await process_dare_reroll(self.target_id, interaction=interaction, view=self)

    @discord.ui.button(label="Forfeit", style=discord.ButtonStyle.danger, emoji="🏳️")
    async def forfeit_btn(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) != self.target_id:
            await interaction.response.send_message("This isn't your dare to forfeit!", ephemeral=True)
            return
        await interaction.response.defer()
        await process_dare_forfeit(self.target_id, interaction=interaction, view=self)


class PvPDareReviewView(View):
    def __init__(self, challenger_id: str, target_id: str, dare_info: dict, proof: str):
        super().__init__(timeout=900.0)
        self.challenger_id = challenger_id
        self.target_id = target_id
        self.dare_info = dare_info
        self.proof = proof

    @discord.ui.button(label="Approve & Payout", style=discord.ButtonStyle.success, emoji="✅")
    async def approve_btn(self, interaction: discord.Interaction, button: Button):
        is_admin = getattr(interaction.user.guild_permissions, "administrator", False) if interaction.guild else False
        if str(interaction.user.id) != self.challenger_id and not is_admin:
            await interaction.response.send_message("Only the challenger can approve this proof!", ephemeral=True)
            return
        await interaction.response.defer()
        await process_pvp_dare_review(self.target_id, action="approve", interaction=interaction, view=self, proof=self.proof)

    @discord.ui.button(label="Ask Yuna AI", style=discord.ButtonStyle.primary, emoji="🤖")
    async def ask_ai_btn(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) not in (self.challenger_id, self.target_id):
            await interaction.response.send_message("Only the challenger or target can ask Yuna AI!", ephemeral=True)
            return
        await interaction.response.defer()
        await process_pvp_dare_review(self.target_id, action="ask_ai", interaction=interaction, view=self, proof=self.proof)

    @discord.ui.button(label="Reject Proof", style=discord.ButtonStyle.danger, emoji="❌")
    async def reject_btn(self, interaction: discord.Interaction, button: Button):
        is_admin = getattr(interaction.user.guild_permissions, "administrator", False) if interaction.guild else False
        if str(interaction.user.id) != self.challenger_id and not is_admin:
            await interaction.response.send_message("Only the challenger can reject this proof!", ephemeral=True)
            return
        await interaction.response.defer()
        await process_pvp_dare_review(self.target_id, action="reject", interaction=interaction, view=self, proof=self.proof)

    @discord.ui.button(label="Forfeit", style=discord.ButtonStyle.secondary, emoji="🏳️")
    async def forfeit_btn(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) != self.target_id:
            await interaction.response.send_message("Only the challenged target can forfeit this dare!", ephemeral=True)
            return
        await interaction.response.defer()
        await process_dare_forfeit(self.target_id, interaction=interaction, view=self)


HL_STREAKS = {
    1: 1.5,
    2: 2.2,
    3: 3.2,
    4: 4.8,
    5: 7.5,
    6: 12.0,
    7: 20.0
}

def get_hl_multiplier(streak: int) -> float:
    if streak <= 0:
        return 1.0
    if streak in HL_STREAKS:
        return HL_STREAKS[streak]
    return 20.0 + (streak - 7) * 5.0

CARD_LABELS = {
    1: "Ace (1)",
    2: "2",
    3: "3",
    4: "4",
    5: "5",
    6: "6",
    7: "7",
    8: "8",
    9: "9",
    10: "10",
    11: "Jack (11)",
    12: "Queen (12)",
    13: "King (13)"
}

def format_hl_number(num: int) -> str:
    label = CARD_LABELS.get(num, str(num))
    return f"🎲 **{label}**"

class HigherLowerView(View):
    def __init__(self, author_id: str, game_state: dict):
        super().__init__(timeout=300.0)
        self.author_id = author_id
        self.game_state = game_state
        streak = game_state.get("streak", 0)
        bet = game_state.get("bet", 10)
        mult = get_hl_multiplier(streak)
        cashout_amt = int(bet * mult)
        
        for child in self.children:
            if hasattr(child, "label") and "Cash Out" in child.label:
                if streak >= 1:
                    child.label = f"💰 Cash Out ({cashout_amt} 🫐)"
                    child.disabled = False
                else:
                    child.label = "💰 Cash Out"
                    child.disabled = True

    async def on_timeout(self):
        if self.author_id in _ACTIVE_HL_GAMES:
            game = _ACTIVE_HL_GAMES.get(self.author_id)
            if not game or game.get("finished"):
                _ACTIVE_HL_GAMES.pop(self.author_id, None)
                return
            last_active = game.get("last_active", 0)
            if time.time() - last_active < 290:
                if hasattr(self, "_refresh_timeout"):
                    self._refresh_timeout()
                return

            _ACTIVE_HL_GAMES.pop(self.author_id, None)
            game["finished"] = True
            streak = game.get("streak", 0)
            bet = game.get("bet", 0)
            if streak > 0:
                mult = get_hl_multiplier(streak)
                pot = int(bet * mult)
                await record_gamble_win(self.author_id)
                await _update_user_stats(self.author_id, berries_delta=pot, is_gamble=True)
                action_msg = f"🏆 Auto-cashed out current streak winnings: **+{pot:,} 🫐**"
            else:
                await _update_user_stats(self.author_id, berries_delta=bet)
                action_msg = f"💸 Wager refunded (**+{bet:,} 🫐**)."

            for child in self.children:
                child.disabled = True

            timeout_text = (
                f"⏰ **HIGHER/LOWER TABLE CLOSED (INACTIVITY)** ⏰\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"<@{self.author_id}>'s Higher/Lower game timed out after 5 minutes of inactivity.\n"
                f"{action_msg}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            if game.get("message"):
                try:
                    await game["message"].edit(content=timeout_text, view=self)
                except Exception:
                    pass

    @discord.ui.button(label="Higher", style=discord.ButtonStyle.success, emoji="🔺")
    async def higher_button(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) != self.author_id:
            await interaction.response.send_message("This isn't your guessing game, mortal!", ephemeral=True)
            return
        await interaction.response.defer()
        await process_hl_turn(self.game_state, guess="higher", interaction=interaction, view=self)

    @discord.ui.button(label="Lower", style=discord.ButtonStyle.danger, emoji="🔻")
    async def lower_button(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) != self.author_id:
            await interaction.response.send_message("This isn't your guessing game, mortal!", ephemeral=True)
            return
        await interaction.response.defer()
        await process_hl_turn(self.game_state, guess="lower", interaction=interaction, view=self)

    @discord.ui.button(label="💰 Cash Out", style=discord.ButtonStyle.primary, disabled=True)
    async def cashout_button(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) != self.author_id:
            await interaction.response.send_message("This isn't your guessing game, mortal!", ephemeral=True)
            return
        await interaction.response.defer()
        await process_hl_cashout(self.game_state, interaction=interaction, view=self)

    @discord.ui.button(label="Reset", style=discord.ButtonStyle.secondary, emoji="🔄")
    async def reset_button(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) != self.author_id:
            await interaction.response.send_message("This isn't your guessing game, mortal!", ephemeral=True)
            return
        await interaction.response.defer()
        await process_hl_reset(self.game_state, interaction=interaction, view=self)


class CoinFlipView(View):
    def __init__(self, author_id: str, amount: int):
        super().__init__(timeout=300.0)
        self.author_id = author_id
        self.amount = amount

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

    @discord.ui.button(label="Heads", style=discord.ButtonStyle.primary, emoji="🪙")
    async def heads_button(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) != self.author_id:
            await interaction.response.send_message("Not your coin flip!", ephemeral=True)
            return
        await interaction.response.defer()
        await execute_solo_coinflip(interaction.message, self.author_id, self.amount, guess="heads", interaction=interaction, view=self)

    @discord.ui.button(label="Tails", style=discord.ButtonStyle.secondary, emoji="🪙")
    async def tails_button(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) != self.author_id:
            await interaction.response.send_message("Not your coin flip!", ephemeral=True)
            return
        await interaction.response.defer()
        await execute_solo_coinflip(interaction.message, self.author_id, self.amount, guess="tails", interaction=interaction, view=self)


class MarryView(View):
    def __init__(self, target_id: str, author_id: str):
        super().__init__(timeout=300.0)
        self.target_id = target_id
        self.author_id = author_id

    @discord.ui.button(label="💍 I Do!", style=discord.ButtonStyle.success)
    async def accept_marriage(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) != self.target_id:
            await interaction.response.send_message("Hey, they didn't propose to you!", ephemeral=True)
            return
        await interaction.response.defer()
        await resolve_marriage(self.author_id, self.target_id, accepted=True, interaction=interaction, view=self)

    @discord.ui.button(label="💔 Leave at Altar", style=discord.ButtonStyle.danger)
    async def reject_marriage(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) != self.target_id:
            await interaction.response.send_message("Only the proposed player can answer!", ephemeral=True)
            return
        await interaction.response.defer()
        await resolve_marriage(self.author_id, self.target_id, accepted=False, interaction=interaction, view=self)


class RouletteView(View):
    def __init__(self, author_id: str, amount: int):
        super().__init__(timeout=300.0)
        self.author_id = author_id
        self.amount = amount

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

    async def _handle_bet(self, interaction: discord.Interaction, bet_type: str):
        if str(interaction.user.id) != self.author_id:
            await interaction.response.send_message("Not your roulette wheel, mortal!", ephemeral=True)
            return
        await interaction.response.defer()
        await execute_roulette_spin(interaction.message, self.author_id, self.amount, bet_type, interaction=interaction, view=self)

    @discord.ui.button(label="🔴 Red (1:1)", style=discord.ButtonStyle.danger, row=0)
    async def red_btn(self, interaction: discord.Interaction, button: Button):
        await self._handle_bet(interaction, "red")

    @discord.ui.button(label="⚫ Black (1:1)", style=discord.ButtonStyle.secondary, row=0)
    async def black_btn(self, interaction: discord.Interaction, button: Button):
        await self._handle_bet(interaction, "black")

    @discord.ui.button(label="👑 Crown (250x)", style=discord.ButtonStyle.success, row=0)
    async def crown_btn(self, interaction: discord.Interaction, button: Button):
        await self._handle_bet(interaction, "crown")

    @discord.ui.button(label="Even (1:1)", style=discord.ButtonStyle.primary, row=1)
    async def even_btn(self, interaction: discord.Interaction, button: Button):
        await self._handle_bet(interaction, "even")

    @discord.ui.button(label="Odd (1:1)", style=discord.ButtonStyle.primary, row=1)
    async def odd_btn(self, interaction: discord.Interaction, button: Button):
        await self._handle_bet(interaction, "odd")

    @discord.ui.button(label="1-18 Low (1:1)", style=discord.ButtonStyle.secondary, row=1)
    async def low_btn(self, interaction: discord.Interaction, button: Button):
        await self._handle_bet(interaction, "low")

    @discord.ui.button(label="19-36 High (1:1)", style=discord.ButtonStyle.secondary, row=1)
    async def high_btn(self, interaction: discord.Interaction, button: Button):
        await self._handle_bet(interaction, "high")

    @discord.ui.button(label="1st 12 (2:1)", style=discord.ButtonStyle.secondary, row=2)
    async def d1_btn(self, interaction: discord.Interaction, button: Button):
        await self._handle_bet(interaction, "1st12")

    @discord.ui.button(label="2nd 12 (2:1)", style=discord.ButtonStyle.secondary, row=2)
    async def d2_btn(self, interaction: discord.Interaction, button: Button):
        await self._handle_bet(interaction, "2nd12")

    @discord.ui.button(label="3rd 12 (2:1)", style=discord.ButtonStyle.secondary, row=2)
    async def d3_btn(self, interaction: discord.Interaction, button: Button):
        await self._handle_bet(interaction, "3rd12")


class PokerView(View):
    def __init__(self, author_id: str, game_state: dict):
        super().__init__(timeout=300.0)
        self.author_id = author_id
        self.game_state = game_state
        self.update_buttons()

    def update_buttons(self):
        hand = self.game_state.get("hand", [])
        held = self.game_state.get("held", set())
        card_buttons = [self.card_btn_0, self.card_btn_1, self.card_btn_2, self.card_btn_3, self.card_btn_4]
        for i, btn in enumerate(card_buttons):
            if i < len(hand):
                c = hand[i]
                is_held = i in held
                btn.label = f"{c[0]}{c[1]} {'🔒' if is_held else ''}".strip()
                btn.style = discord.ButtonStyle.success if is_held else discord.ButtonStyle.secondary
            else:
                btn.disabled = True

    async def on_timeout(self):
        if self.author_id in _ACTIVE_POKER_GAMES:
            game = _ACTIVE_POKER_GAMES.pop(self.author_id, None)
            if game and not game.get("finished"):
                game["finished"] = True
                bet = game.get("amount", 0)
                await _update_user_stats(self.author_id, berries_delta=bet)
                for child in self.children:
                    child.disabled = True
                timeout_text = (
                    f"⏰ **POKER TABLE CLOSED (INACTIVITY)** ⏰\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"<@{self.author_id}>'s poker hand timed out after 5 minutes of inactivity.\n"
                    f"💸 Wager of **{bet:,} 🫐** was refunded to your balance.\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                if game.get("message"):
                    try:
                        await game["message"].edit(content=timeout_text, view=self)
                    except Exception:
                        pass

    async def _toggle_card(self, interaction: discord.Interaction, idx: int):
        if str(interaction.user.id) != self.author_id:
            await interaction.response.send_message("This isn't your poker game!", ephemeral=True)
            return
        refresh_view_timeout(self, 300.0)
        if self.game_state.get("finished"):
            await interaction.response.send_message("This hand has already completed!", ephemeral=True)
            return
        if idx in self.game_state["held"]:
            self.game_state["held"].remove(idx)
        else:
            self.game_state["held"].add(idx)
        self.update_buttons()
        await interaction.response.edit_message(content=format_poker_message(self.game_state), view=self)

    @discord.ui.button(label="Card 1", style=discord.ButtonStyle.secondary, row=0)
    async def card_btn_0(self, interaction: discord.Interaction, button: Button):
        await self._toggle_card(interaction, 0)

    @discord.ui.button(label="Card 2", style=discord.ButtonStyle.secondary, row=0)
    async def card_btn_1(self, interaction: discord.Interaction, button: Button):
        await self._toggle_card(interaction, 1)

    @discord.ui.button(label="Card 3", style=discord.ButtonStyle.secondary, row=0)
    async def card_btn_2(self, interaction: discord.Interaction, button: Button):
        await self._toggle_card(interaction, 2)

    @discord.ui.button(label="Card 4", style=discord.ButtonStyle.secondary, row=0)
    async def card_btn_3(self, interaction: discord.Interaction, button: Button):
        await self._toggle_card(interaction, 3)

    @discord.ui.button(label="Card 5", style=discord.ButtonStyle.secondary, row=0)
    async def card_btn_4(self, interaction: discord.Interaction, button: Button):
        await self._toggle_card(interaction, 4)

    @discord.ui.button(label="🔄 Draw Cards", style=discord.ButtonStyle.primary, row=1)
    async def draw_button(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) != self.author_id:
            await interaction.response.send_message("This isn't your poker game!", ephemeral=True)
            return
        await interaction.response.defer()
        await execute_poker_draw(interaction.message, self.author_id, interaction=interaction, view=self)

    @discord.ui.button(label="🏳️ Fold", style=discord.ButtonStyle.danger, row=1)
    async def fold_button(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) != self.author_id:
            await interaction.response.send_message("This isn't your poker game!", ephemeral=True)
            return
        await interaction.response.defer()
        await execute_poker_fold(interaction.message, self.author_id, interaction=interaction, view=self)


class DiceView(View):
    def __init__(self, author_id: str, amount: int):
        super().__init__(timeout=300.0)
        self.author_id = author_id
        self.amount = amount

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

    async def _handle_bet(self, interaction: discord.Interaction, bet_type: str):
        if str(interaction.user.id) != self.author_id:
            await interaction.response.send_message("Not your dice table, mortal!", ephemeral=True)
            return
        await interaction.response.defer()
        await execute_dice_roll(interaction.message, self.author_id, self.amount, bet_type, interaction=interaction, view=self)

    @discord.ui.button(label="🔴 Low 2-6 (1:1)", style=discord.ButtonStyle.secondary, row=0)
    async def low_btn(self, interaction: discord.Interaction, button: Button):
        await self._handle_bet(interaction, "low")

    @discord.ui.button(label="⭐ Seven 7 (4:1)", style=discord.ButtonStyle.primary, row=0)
    async def seven_btn(self, interaction: discord.Interaction, button: Button):
        await self._handle_bet(interaction, "seven")

    @discord.ui.button(label="🔵 High 8-12 (1:1)", style=discord.ButtonStyle.secondary, row=0)
    async def high_btn(self, interaction: discord.Interaction, button: Button):
        await self._handle_bet(interaction, "high")

    @discord.ui.button(label="🎲 Even (1:1)", style=discord.ButtonStyle.secondary, row=1)
    async def even_btn(self, interaction: discord.Interaction, button: Button):
        await self._handle_bet(interaction, "even")

    @discord.ui.button(label="🎯 Odd (1:1)", style=discord.ButtonStyle.secondary, row=1)
    async def odd_btn(self, interaction: discord.Interaction, button: Button):
        await self._handle_bet(interaction, "odd")

    @discord.ui.button(label="✨ Doubles (4:1)", style=discord.ButtonStyle.success, row=1)
    async def doubles_btn(self, interaction: discord.Interaction, button: Button):
        await self._handle_bet(interaction, "doubles")

    @discord.ui.button(label="⚔️ Roll vs Yuna (1:1)", style=discord.ButtonStyle.danger, row=2)
    async def vs_btn(self, interaction: discord.Interaction, button: Button):
        await self._handle_bet(interaction, "vs")

    @discord.ui.button(label="🐍 Snake Eyes [2] (30:1)", style=discord.ButtonStyle.secondary, row=2)
    async def snake_eyes_btn(self, interaction: discord.Interaction, button: Button):
        await self._handle_bet(interaction, "2")

    @discord.ui.button(label="🚂 Boxcars [12] (30:1)", style=discord.ButtonStyle.secondary, row=2)
    async def boxcars_btn(self, interaction: discord.Interaction, button: Button):
        await self._handle_bet(interaction, "12")


# ─── MINES & WORDLE CASINO SYSTEM ───────────────────────────────────────────

def get_mines_multiplier(mines_count: int, gems_revealed: int, total_tiles: int = 24) -> float:
    """Calculates fair casino multiplier for Mines with 96% RTP."""
    if gems_revealed <= 0:
        return 1.0
    safe_tiles = total_tiles - mines_count
    if gems_revealed > safe_tiles:
        return 1.0
    prob = 1.0
    for j in range(gems_revealed):
        prob *= (safe_tiles - j) / (total_tiles - j)
    if prob <= 0:
        return 1.0
    mult = 0.96 / prob
    return max(1.08, round(mult, 2))


class MinesTileButton(Button):
    def __init__(self, index: int, row: int):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label=str(index + 1),
            row=row,
            custom_id=f"mine_tile_{index}"
        )
        self.tile_index = index

    async def callback(self, interaction: discord.Interaction):
        view: MinesView = self.view
        if str(interaction.user.id) != view.author_id:
            await interaction.response.send_message("Not your minefield, mortal!", ephemeral=True)
            return
        await interaction.response.defer()
        await process_mines_click(view.game_state, self.tile_index, interaction=interaction, view=view)


class MinesCashoutButton(Button):
    def __init__(self, row: int = 4):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="💰 Cash Out",
            row=row,
            disabled=True,
            custom_id="mines_cashout_btn"
        )

    async def callback(self, interaction: discord.Interaction):
        view: MinesView = self.view
        if str(interaction.user.id) != view.author_id:
            await interaction.response.send_message("Not your minefield, mortal!", ephemeral=True)
            return
        await interaction.response.defer()
        await process_mines_cashout(view.game_state, interaction=interaction, view=view)


class MinesView(View):
    def __init__(self, author_id: str, game_state: dict):
        super().__init__(timeout=600.0)
        self.author_id = author_id
        self.game_state = game_state
        self.tile_buttons = {}

        # 24 tile buttons distributed across rows 0 to 4
        # Row 0: 0-4 (5 buttons)
        # Row 1: 5-9 (5 buttons)
        # Row 2: 10-14 (5 buttons)
        # Row 3: 15-19 (5 buttons)
        # Row 4: 20-23 (4 buttons)
        for i in range(24):
            r = i // 5
            btn = MinesTileButton(i, r)
            self.tile_buttons[i] = btn
            self.add_item(btn)

        # 25th item: Cash Out button at row 4, position 5
        self.cashout_btn = MinesCashoutButton(row=4)
        self.add_item(self.cashout_btn)
        self.sync_state()

    def sync_state(self):
        revealed = set(self.game_state.get("revealed", []))
        mines = set(self.game_state.get("mines", []))
        finished = self.game_state.get("finished", False)
        exploded = self.game_state.get("exploded_tile", None)

        for i, btn in self.tile_buttons.items():
            if i in revealed:
                btn.style = discord.ButtonStyle.success
                btn.emoji = "💎"
                btn.label = None
                btn.disabled = True
            elif finished:
                btn.disabled = True
                if i == exploded:
                    btn.style = discord.ButtonStyle.danger
                    btn.emoji = "💥"
                    btn.label = None
                elif i in mines:
                    btn.style = discord.ButtonStyle.danger
                    btn.emoji = "💣"
                    btn.label = None
                else:
                    btn.style = discord.ButtonStyle.secondary
                    btn.emoji = "💎"
                    btn.label = None
            else:
                btn.style = discord.ButtonStyle.secondary
                btn.emoji = None
                btn.label = str(i + 1)
                btn.disabled = False

        bet = self.game_state.get("bet", 10)
        k = len(revealed)
        mult = get_mines_multiplier(len(mines), k)
        pot = int(bet * mult)

        if k > 0 and not finished:
            self.cashout_btn.style = discord.ButtonStyle.success
            self.cashout_btn.label = f"💰 Cash Out ({pot:,} 🫐)"
            self.cashout_btn.disabled = False
        else:
            self.cashout_btn.style = discord.ButtonStyle.secondary
            self.cashout_btn.label = "💰 Cash Out"
            self.cashout_btn.disabled = True

    async def on_timeout(self):
        if self.author_id in _ACTIVE_MINES_GAMES:
            game = _ACTIVE_MINES_GAMES.get(self.author_id)
            if not game or game.get("finished"):
                _ACTIVE_MINES_GAMES.pop(self.author_id, None)
                return
            last_active = game.get("last_active", 0)
            if time.time() - last_active < 590:
                if hasattr(self, "_refresh_timeout"):
                    self._refresh_timeout()
                return

            _ACTIVE_MINES_GAMES.pop(self.author_id, None)
            game["finished"] = True
            k = len(game.get("revealed", []))
            bet = game.get("bet", 0)
            if k > 0:
                mult = get_mines_multiplier(len(game.get("mines", [])), k)
                pot = int(bet * mult)
                await record_gamble_win(self.author_id)
                await _update_user_stats(self.author_id, berries_delta=pot, is_gamble=True)
                action_msg = f"🏆 Auto-cashed out {k} safe gems: **+{pot:,} 🫐** ({mult:.2f}x)"
            else:
                await _update_user_stats(self.author_id, berries_delta=bet)
                action_msg = f"💸 Minefield closed — Wager refunded (**+{bet:,} 🫐**)."

            for child in self.children:
                child.disabled = True

            timeout_text = (
                f"⏰ **MINEFIELD CLOSED (INACTIVITY)** ⏰\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"<@{self.author_id}>'s minefield timed out after 10 minutes of inactivity.\n"
                f"{action_msg}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            if game.get("message"):
                try:
                    await game["message"].edit(content=timeout_text, view=self)
                except Exception:
                    pass


WORDLE_STAGE_SPECS = {
    1: {"name": "Novice Scholar", "len": 4, "max_guesses": 6, "mult": 1.8},
    2: {"name": "Adept Cryptographer", "len": 5, "max_guesses": 5, "mult": 3.6},
    3: {"name": "Master Enigma", "len": 6, "max_guesses": 5, "mult": 8.0},
    4: {"name": "Grandmaster of the Labyrinth", "len": 6, "max_guesses": 4, "mult": 18.0},
    5: {"name": "Ascended God of Words", "len": 7, "max_guesses": 4, "mult": 40.0}
}
WORDLE_STAGE_MULTIPLIERS = {k: v["mult"] for k, v in WORDLE_STAGE_SPECS.items()}

WORDLE_WORDS = {
    4: [
        "LUCK", "GOLD", "STAR", "COIN", "BEAT", "PLAY", "CHIP", "RISK", "WISH", "GAME",
        "RUBY", "HOPE", "MINT", "BIRD", "LOVE", "MOON", "FROG", "FIRE", "RAIN", "CARD",
        "DECK", "DICE", "SAFE", "BANK", "CASH", "FAST", "BEST", "RICH", "GLOW", "HERO",
        "WAVE", "TIME", "PEAK", "WIND", "ROSE", "DOVE", "WOLF", "LION", "BOLT", "VAST",
        "DAWN", "DUSK", "LEAF", "BELL", "RING", "TREE", "KING", "SOUL", "AURA", "GEMS"
    ],
    5: [
        "LUCKY", "BERRY", "CROWN", "VAULT", "SHARK", "DEVIL", "ANGEL", "PRIZE", "ROYAL",
        "FLUSH", "MANOR", "WHEEL", "SPARK", "FAITH", "CHARM", "BLUFF", "CLOVER", "GHOST",
        "DREAM", "CHESS", "MAGIC", "QUEST", "SWORD", "FLAME", "PEARL", "QUEEN", "TITAN",
        "VAPOR", "TIGER", "ROBIN", "OCEAN", "STORM", "POWER", "BLADE", "HONOR", "FROST",
        "SHINE", "COMET", "SOLAR", "LUNAR", "EMBER", "VALOR", "RELIC", "SPELL", "RIVER",
        "HAZEL", "AMBER", "PIXEL", "NOBLE", "BREEZE"
    ],
    6: [
        "CASINO", "GOLDEN", "WEALTH", "JACKPOT", "SHRINE", "LEGEND", "FORTUNE", "SHIELD",
        "MYSTIC", "PURPLE", "MIRROR", "CLOVER", "DRAGON", "SILVER", "PIRATE", "PALACE",
        "WIZARD", "KNIGHT", "BLADES", "HUNTER", "FOREST", "TEMPLE", "HEAVEN", "FROZEN",
        "SPIRIT", "CHANCE", "SHADOW", "REWARD", "EMPIRE", "CASTLE", "AURORA", "METEOR",
        "PRINCE", "VALLEY", "BEACON", "PHOENIX", "SPHERE", "PORTAL", "SUMMIT", "CANDLE"
    ],
    "tricky_6": [
        "SPHINX", "CIPHER", "VORTEX", "ZODIAC", "QUARTZ", "GLYPHS", "ABYSS", "MYTHIC",
        "FRENZY", "CRUXES", "PHANTOM", "ECLIPSE", "GOBLIN", "VOODOO", "KISMET", "KARMIC",
        "ENIGMA", "CYNIC", "PYRITE", "CHAOS", "COSMIC", "OCCULT", "ZEPHYR", "HYBRIS",
        "SHADOW", "CHIMERA", "KEEPER", "GRAILS", "ARCANE", "WYVERN", "RITUAL", "BISHOP"
    ],
    7: [
        "DIAMOND", "CORRUPT", "INFERNO", "MIRACLE", "TITANIC", "PHANTOM", "BLOSSOM", "ETERNAL",
        "BLINDED", "DESTINY", "FORTUNE", "CRYSTAL", "KINGDOM", "DRAGONS", "SHADOWS", "PHOENIX",
        "BRAVERY", "MYSTERY", "TRIUMPH", "SPECTRE", "HARMONY", "VICTORY", "VALIANT", "ROYALTY",
        "MAJESTY", "CHAMPION", "EMPEROR", "WARRIOR", "BLAZING", "SUPREME", "MIRRORED", "ANGELIC"
    ]
}

def evaluate_wordle_guess(target: str, guess: str) -> List[str]:
    target = target.upper()
    guess = guess.upper()
    length = len(target)
    clues = ["⬛"] * length
    unmatched_counts = {}

    for i in range(length):
        if guess[i] == target[i]:
            clues[i] = "🟩"
        else:
            t = target[i]
            unmatched_counts[t] = unmatched_counts.get(t, 0) + 1

    for i in range(length):
        if clues[i] == "🟩":
            continue
        g = guess[i]
        if unmatched_counts.get(g, 0) > 0:
            clues[i] = "🟨"
            unmatched_counts[g] -= 1
        else:
            clues[i] = "⬛"

    return clues

def render_wordle_embed_desc(game_state: dict) -> str:
    stage = game_state["stage"]
    spec = WORDLE_STAGE_SPECS.get(stage, WORDLE_STAGE_SPECS[1])
    word_len = game_state["word_length"]
    max_g = game_state["max_guesses"]
    guesses = game_state["guesses"]
    bet = game_state["bet"]
    mult = spec["mult"]
    pot = int(bet * mult)
    status = game_state["status"]

    lines = [
        f"📚 **WORDLE GAMBLE — STAGE {stage}/5: {spec['name'].upper()}** 📚",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"Player: {game_state['author_mention']} | Wager: **{bet:,}** 🫐",
        f"Difficulty: **{word_len} Letters** | Max Attempts: **{max_g} Guesses**",
        f"Stage Multiplier: **{mult:.1f}x** ➔ Current Pot: **{pot:,} 🫐**",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    ]

    for i in range(max_g):
        if i < len(guesses):
            g_entry = guesses[i]
            g_word = g_entry["word"]
            clues_str = " ".join(g_entry["clues"])
            spaced_word = " ".join(g_word)
            lines.append(f"`#{i+1}` {clues_str}   `{spaced_word}`")
        else:
            empty_boxes = " ".join(["⬜"] * word_len)
            empty_slots = " ".join(["_"] * word_len)
            lines.append(f"`#{i+1}` {empty_boxes}   `{empty_slots}`")

    correct = sorted(list(game_state["used_letters"]["correct"]))
    present = sorted(list(game_state["used_letters"]["present"] - set(correct)))
    absent = sorted(list(game_state["used_letters"]["absent"] - set(correct) - set(present)))
    all_used = set(correct) | set(present) | set(absent)
    remaining = [chr(c) for c in range(ord('A'), ord('Z') + 1) if chr(c) not in all_used]

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("🔤 **Alphabet Intelligence:**")
    if correct:
        lines.append(f"🟩 **Correct:** `{' '.join(correct)}`")
    if present:
        lines.append(f"🟨 **Misplaced:** `{' '.join(present)}`")
    if absent:
        lines.append(f"⬛ **Absent:** `{' '.join(absent)}`")
    lines.append(f"⚪ **Available:** `{' '.join(remaining)}`")

    if status == "guessing":
        rem_g = max_g - len(guesses)
        lines.append(f"\n*(**{rem_g} guess{'es' if rem_g != 1 else ''} remaining!** Click **✏️ Guess Word** or type `y!guess <word>`)*")
    elif status == "stage_cleared":
        next_stage = stage + 1
        lines.append(f"\n🎉 **STAGE {stage} SOLVED! Secret word: {game_state['target_word']}!**")
        if next_stage <= 5:
            next_spec = WORDLE_STAGE_SPECS[next_stage]
            next_pot = int(bet * next_spec["mult"])
            lines.append(
                f"Choose your fate: **[💰 Cash Out ({pot:,} 🫐)]** or **[🔥 Risk & Advance to Stage {next_stage}]**!\n"
                f"Next Stage: **{next_spec['name']}** ({next_spec['len']} letters, {next_spec['max_guesses']} guesses, **{next_spec['mult']}x** = **{next_pot:,} 🫐**!)"
            )
        else:
            lines.append("👑 **YOU HAVE CLEARED ALL 5 STAGES! SUPREME VICTORY!**")

    return "\n".join(lines)


class WordleGuessModal(Modal):
    def __init__(self, game_state: dict, wordle_view: View):
        stage = game_state.get("stage", 1)
        w_len = game_state.get("word_length", 5)
        super().__init__(title=f"Stage {stage} Wordle ({w_len} Letters)")
        self.game_state = game_state
        self.wordle_view = wordle_view

        self.guess_input = TextInput(
            label=f"Enter your {w_len}-letter guess:",
            placeholder=f"Type a {w_len}-letter word (e.g. {'LUCK' if w_len==4 else 'BERRY'})...",
            min_length=w_len,
            max_length=w_len,
            required=True
        )
        self.add_item(self.guess_input)

    async def on_submit(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.game_state["author_id"]:
            await interaction.response.send_message("Not your Wordle game!", ephemeral=True)
            return
        await interaction.response.defer()
        refresh_view_timeout(self.wordle_view, 600.0)
        guess_word = self.guess_input.value.strip().upper()
        await process_wordle_guess(self.game_state, guess_word, interaction=interaction, view=self.wordle_view)


class WordleView(View):
    def __init__(self, author_id: str, game_state: dict):
        super().__init__(timeout=600.0)
        self.author_id = author_id
        self.game_state = game_state
        self.sync_buttons()

    def sync_buttons(self):
        self.clear_items()
        status = self.game_state.get("status", "guessing")
        stage = self.game_state.get("stage", 1)
        bet = self.game_state.get("bet", 20)
        mult = WORDLE_STAGE_MULTIPLIERS.get(stage, 1.8)
        pot = int(bet * mult)

        if status == "guessing":
            btn_guess = Button(label="✏️ Guess Word", style=discord.ButtonStyle.primary, emoji="✍️")
            async def _on_guess(interaction: discord.Interaction):
                if str(interaction.user.id) != self.author_id:
                    await interaction.response.send_message("Not your Wordle table!", ephemeral=True)
                    return
                modal = WordleGuessModal(self.game_state, self)
                await interaction.response.send_modal(modal)
            btn_guess.callback = _on_guess
            self.add_item(btn_guess)

            btn_give_up = Button(label="🏳️ Give Up", style=discord.ButtonStyle.danger)
            async def _on_give_up(interaction: discord.Interaction):
                if str(interaction.user.id) != self.author_id:
                    await interaction.response.send_message("Not your Wordle table!", ephemeral=True)
                    return
                await interaction.response.defer()
                await process_wordle_give_up(self.game_state, interaction=interaction, view=self)
            btn_give_up.callback = _on_give_up
            self.add_item(btn_give_up)

        elif status == "stage_cleared":
            btn_cashout = Button(label=f"💰 Cash Out ({pot:,} 🫐)", style=discord.ButtonStyle.success, emoji="💵")
            async def _on_cashout(interaction: discord.Interaction):
                if str(interaction.user.id) != self.author_id:
                    await interaction.response.send_message("Not your Wordle table!", ephemeral=True)
                    return
                await interaction.response.defer()
                await process_wordle_cashout(self.game_state, interaction=interaction, view=self)
            btn_cashout.callback = _on_cashout
            self.add_item(btn_cashout)

            next_stage = stage + 1
            if next_stage <= 5:
                next_mult = WORDLE_STAGE_MULTIPLIERS.get(next_stage, 3.6)
                next_pot = int(bet * next_mult)
                next_len = WORDLE_STAGE_SPECS.get(next_stage, {}).get("len", 5)
                btn_advance = Button(
                    label=f"🔥 Advance to Stage {next_stage} ({next_len} letters, {next_mult}x -> {next_pot:,} 🫐)",
                    style=discord.ButtonStyle.primary,
                    emoji="⚡"
                )
                async def _on_advance(interaction: discord.Interaction):
                    if str(interaction.user.id) != self.author_id:
                        await interaction.response.send_message("Not your Wordle table!", ephemeral=True)
                        return
                    await interaction.response.defer()
                    await process_wordle_advance(self.game_state, interaction=interaction, view=self)
                btn_advance.callback = _on_advance
                self.add_item(btn_advance)

    async def on_timeout(self):
        if self.author_id in _ACTIVE_WORDLE_GAMES:
            game = _ACTIVE_WORDLE_GAMES.get(self.author_id)
            if not game or game.get("finished"):
                _ACTIVE_WORDLE_GAMES.pop(self.author_id, None)
                return
            last_active = game.get("last_active", 0)
            if time.time() - last_active < 590:
                if hasattr(self, "_refresh_timeout"):
                    self._refresh_timeout()
                return

            _ACTIVE_WORDLE_GAMES.pop(self.author_id, None)
            game["finished"] = True
            status = game.get("status")
            stage = game.get("stage", 1)
            bet = game.get("bet", 0)

            if status == "stage_cleared":
                mult = WORDLE_STAGE_MULTIPLIERS.get(stage, 1.8)
                pot = int(bet * mult)
                await record_gamble_win(self.author_id)
                await _update_user_stats(self.author_id, berries_delta=pot, is_gamble=True)
                action_msg = f"🏆 Auto-cashed out Stage {stage} cleared winnings: **+{pot:,} 🫐** ({mult:.1f}x)"
            elif stage > 1:
                prev_stage = stage - 1
                mult = WORDLE_STAGE_MULTIPLIERS.get(prev_stage, 1.0)
                pot = int(bet * mult)
                await record_gamble_win(self.author_id)
                await _update_user_stats(self.author_id, berries_delta=pot, is_gamble=True)
                action_msg = f"🏆 Auto-cashed out Stage {prev_stage} cleared winnings: **+{pot:,} 🫐** ({mult:.1f}x)"
            else:
                await _update_user_stats(self.author_id, berries_delta=bet)
                action_msg = f"💸 Wordle table closed — Wager refunded (**+{bet:,} 🫐**)."

            for child in self.children:
                child.disabled = True

            timeout_text = (
                f"⏰ **WORDLE TABLE CLOSED (INACTIVITY)** ⏰\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"<@{self.author_id}>'s Wordle game timed out after 10 minutes of inactivity.\n"
                f"{action_msg}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            if game.get("message"):
                try:
                    await game["message"].edit(content=timeout_text, view=self)
                except Exception:
                    pass




# ─── COMMAND HANDLERS: ECONOMY & MORALITY ───────────────────────────────────

async def handle_daily(message, client, args: list):
    """Handles y!daily or y!claim (Daily berry allowance, streak bonuses, and marriage stipend)."""
    author_id = str(message.author.id)
    today_str = time.strftime("%Y-%m-%d", time.gmtime())
    yesterday_str = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 86400))

    stats = await _get_user_stats(author_id)
    last_daily = stats.get("last_daily_date", "")

    if last_daily == today_str:
        now_gm = time.gmtime()
        secs_left = 86400 - (now_gm.tm_hour * 3600 + now_gm.tm_min * 60 + now_gm.tm_sec)
        h = secs_left // 3600
        m = (secs_left % 3600) // 60
        await _safe_send_reply(
            message,
            f"- *Yuna crosses her arms with a smirk*\n"
            f"\"Greedy! You've already collected today's daily berries! Come back in **{h}h {m}m** (midnight UTC)!\n"
            f"> Complete your everyday task list with `y!tasks` for extra rewards!\""
        )
        return

    # Calculate streak
    prev_streak = stats.get("daily_streak", 0)
    streak = (prev_streak + 1) if last_daily == yesterday_str else 1

    base_allowance = 150
    streak_bonus = min(500, (streak - 1) * 25)
    spouse_id = stats.get("spouse")
    has_ring = stats.get("inventory", {}).get("ring", 0) > 0
    marriage_bonus = (120 if has_ring else 50) if spouse_id else 0
    total_gain = base_allowance + streak_bonus + marriage_bonus

    # Accrue joint vault interest if married
    accrued_interest = 0
    if spouse_id:
        async with _LOCK:
            vault = _get_joint_vault(author_id, spouse_id)
            interest, accrued = _accrue_vault_interest(vault)
            if accrued:
                accrued_interest = interest

    async with _LOCK:
        stats["daily_streak"] = streak
        stats["last_daily_date"] = today_str
        stats["berries"] = stats.get("berries", 0) + total_gain
        stats["virtue"] = stats.get("virtue", 0) + 1
        _save_data_sync(_USER_STATS)

    unlocked = await check_and_award_achievements(author_id)
    banner = format_achievement_banner(unlocked)

    embed = discord.Embed(
        title="🎁 Yuna's Daily Berry Allowance!",
        description=f"You opened today's berry basket and received fresh divine treats!",
        color=0xF59E0B
    )
    embed.add_field(name="📦 Base Grant", value=f"`+{base_allowance} 🫐`", inline=True)
    embed.add_field(name=f"🔥 Daily Streak (Day {streak})", value=f"`+{streak_bonus} 🫐`", inline=True)
    if spouse_id:
        ring_txt = " *(💍 Ring Boost)*" if has_ring else " *(Spouse Bonus)*"
        embed.add_field(name="💍 Marriage Stipend", value=f"`+{marriage_bonus} 🫐`{ring_txt}", inline=True)
    embed.add_field(name="💖 Virtue Earned", value="`+1 💖`", inline=True)
    if accrued_interest > 0:
        embed.add_field(name="🏛️ Joint Vault Love Yield", value=f"`+{accrued_interest} 🫐`", inline=True)
    embed.add_field(name="💰 Total Berries Added", value=f"**+{total_gain:,} 🫐**", inline=False)
    if banner:
        embed.add_field(name="🏆 Achievements", value=banner.strip(), inline=False)
    embed.set_footer(text="💡 Tip: Type 'y!tasks' to view and progress your everyday quest list!")

    await _safe_send_reply(message, embed=embed)


async def handle_tasks(message, client, args: list):
    """Handles y!tasks, y!dailies, y!tasklist, y!todo (Everyday Task List)."""
    author_id = str(message.author.id)
    stats = await _get_user_stats(author_id)
    dt = _get_user_daily_tasks(stats)
    tasks = dt.get("tasks", {})

    now_gm = time.gmtime()
    secs_left = 86400 - (now_gm.tm_hour * 3600 + now_gm.tm_min * 60 + now_gm.tm_sec)
    h = secs_left // 3600
    m = (secs_left % 3600) // 60

    completed_count = sum(1 for t in tasks.values() if t.get("claimed", False))
    total_tasks = len(tasks)

    embed = discord.Embed(
        title=f"📋 Everyday Task List — {dt['date']}",
        description=(
            f"Complete everyday tasks to earn extra berries and morality rewards!\n"
            f"Progress: **{completed_count}/{total_tasks}** completed • Resets in **{h}h {m}m**"
        ),
        color=0x3B82F6
    )

    for key, t in tasks.items():
        name = t["name"]
        desc = t["desc"]
        reward = t["reward"]
        prog = t.get("progress", 0)
        target = t["target"]
        claimed = t.get("claimed", False)

        if claimed:
            status_text = f"✅ **{name}** [Completed]\n> *{desc}* — Earned **+{reward} 🫐**"
        else:
            status_text = f"⏳ **{name}** [{prog}/{target}]\n> *{desc}* — Reward: **+{reward} 🫐**"
        embed.add_field(name="\u200b", value=status_text, inline=False)

    all_bonus_claimed = dt.get("all_bonus_claimed", False)
    spouse_id = stats.get("spouse")
    grand_bonus = 200 + (40 if spouse_id else 0)

    if all_bonus_claimed:
        embed.add_field(
            name="🎉 Grand Daily Bounty",
            value=f"✅ **CLAIMED!** You unlocked **+{grand_bonus} 🫐** & **+2 💖** Virtue!",
            inline=False
        )
    else:
        marriage_note = " *(+40 🫐 marriage bonus included!)*" if spouse_id else " *(Married couples get +40 🫐 extra!)*"
        embed.add_field(
            name="🎁 Grand Daily Bounty",
            value=f"Complete all {total_tasks} tasks to unlock **+{grand_bonus} 🫐** & **+2 💖** Virtue!{marriage_note}",
            inline=False
        )

    embed.set_footer(text="💡 Tip: Type y!daily for your daily login allowance!")
    await _safe_send_reply(message, embed=embed)


async def handle_shared(message, client, args: list):
    """Handles y!shared, y!joint, y!vault (Matrimonial Joint Bank Vault)."""
    author_id = str(message.author.id)
    stats = await _get_user_stats(author_id)
    spouse_id = stats.get("spouse")

    if not spouse_id:
        await _safe_send_reply(
            message,
            "- *Yuna giggles and shakes her head*\n"
            "\"You don't have a shared account because you're not married!\n"
            "Propose to someone with `y!marry @user` to unlock a Joint Vault and marriage perks!\""
        )
        return

    sub = args[0].lower() if args else "view"

    if sub in ("view", "info", "bal", "balance", "status", "check"):
        async with _LOCK:
            vault = _get_joint_vault(author_id, spouse_id)
            interest, accrued = _accrue_vault_interest(vault)
            if accrued:
                _save_data_sync(_USER_STATS)
            v_bal = vault["balance"]
            dep = vault.get("total_deposited", 0)
            wdr = vault.get("total_withdrawn", 0)

        embed = discord.Embed(
            title="💍 Matrimonial Joint Vault",
            description=f"Shared bank vault of <@{author_id}> & <@{spouse_id}>!",
            color=0xEC4899
        )
        embed.add_field(name="💰 Vault Balance", value=f"**{v_bal:,}** 🫐", inline=False)
        embed.add_field(name="📈 Daily Love Interest", value="+5% daily passive yield (up to 500 🫐/day)", inline=True)
        if accrued:
            embed.add_field(name="✨ Interest Accrued Today", value=f"**+{interest} 🫐**", inline=True)
        embed.add_field(name="📊 Lifetime Deposits", value=f"`{dep:,} 🫐`", inline=True)
        embed.add_field(name="💸 Lifetime Withdrawals", value=f"`{wdr:,} 🫐`", inline=True)
        embed.add_field(
            name="🛠️ Joint Vault Commands",
            value=(
                "• `y!shared deposit <amount|all>` — Deposit berries into joint vault\n"
                "• `y!shared withdraw <amount|all>` — Withdraw berries from joint vault\n"
                "• `y!doubleaid @user` — Team up with your spouse for a 2x Super Aid!"
            ),
            inline=False
        )
        embed.set_footer(text="Yuna's Matrimonial Banking • Funds are divided 50/50 upon divorce!")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub in ("deposit", "dep", "put", "add"):
        if len(args) < 2:
            await _safe_send_reply(message, "- *Yuna tilts her head* \"How many berries do you want to deposit? Usage: `y!shared deposit <amount|all>`\"")
            return

        amt_str = args[1].lower().strip()
        author_berries = stats.get("berries", 0)
        if amt_str == "all":
            amount = author_berries
        else:
            try:
                amount = int(amt_str.replace(",", ""))
            except ValueError:
                await _safe_send_reply(message, "- *Yuna scoffs* \"Please provide a valid berry number to deposit!\"")
                return

        if amount <= 0:
            await _safe_send_reply(message, "- *Yuna smirks* \"You can't deposit zero or negative berries, nice try!\"")
            return

        if author_berries < amount:
            await _safe_send_reply(message, f"- *Yuna rolls her eyes* \"You only have **{author_berries:,}** 🫐! You can't deposit **{amount:,}** 🫐!\"")
            return

        async with _LOCK:
            vault = _get_joint_vault(author_id, spouse_id)
            stats["berries"] -= amount
            vault["balance"] += amount
            vault["total_deposited"] = vault.get("total_deposited", 0) + amount
            stats["joint_deposited"] = stats.get("joint_deposited", 0) + amount
            _save_data_sync(_USER_STATS)

        unlocked = await check_and_award_achievements(author_id, specific_id="joint_investor")
        banner = format_achievement_banner(unlocked)

        await _safe_send_reply(
            message,
            f"💍 **JOINT VAULT DEPOSIT!** 💍\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<@{author_id}> deposited **{amount:,}** 🫐 into the shared vault with <@{spouse_id}>!\n"
            f"💰 New Joint Balance: **{vault['balance']:,}** 🫐\n"
            f"🫐 Your Remaining Berries: **{stats['berries']:,}** 🫐{banner}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        return

    elif sub in ("withdraw", "with", "take", "pull"):
        if len(args) < 2:
            await _safe_send_reply(message, "- *Yuna tilts her head* \"How many berries do you want to withdraw? Usage: `y!shared withdraw <amount|all>`\"")
            return

        amt_str = args[1].lower().strip()
        async with _LOCK:
            vault = _get_joint_vault(author_id, spouse_id)
            vault_bal = vault.get("balance", 0)

            if amt_str == "all":
                amount = vault_bal
            else:
                try:
                    amount = int(amt_str.replace(",", ""))
                except ValueError:
                    await _safe_send_reply(message, "- *Yuna scoffs* \"Please provide a valid berry number to withdraw!\"")
                    return

            if amount <= 0:
                await _safe_send_reply(message, "- *Yuna smirks* \"You can't withdraw zero or negative berries!\"")
                return

            if vault_bal < amount:
                await _safe_send_reply(message, f"- *Yuna holds the vault shut* \"Your joint vault only has **{vault_bal:,}** 🫐! You can't withdraw **{amount:,}** 🫐!\"")
                return

            vault["balance"] -= amount
            vault["total_withdrawn"] = vault.get("total_withdrawn", 0) + amount
            stats["berries"] = stats.get("berries", 0) + amount
            _save_data_sync(_USER_STATS)

        await _safe_send_reply(
            message,
            f"💸 **JOINT VAULT WITHDRAWAL!** 💸\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<@{author_id}> withdrew **{amount:,}** 🫐 from the shared vault with <@{spouse_id}>!\n"
            f"💰 Remaining Joint Balance: **{vault['balance']:,}** 🫐\n"
            f"🫐 Your New Balance: **{stats['berries']:,}** 🫐\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        return

    else:
        await _safe_send_reply(
            message,
            f"- *Yuna tilts her head* \"Unknown vault action `{sub}`! Use `y!shared`, `y!shared deposit <amt>`, or `y!shared withdraw <amt>`!\""
        )


async def handle_doubleaid(message, client, args: list):
    """Handles y!doubleaid <@user> (Married couples team up for a 2x Super Aid)."""
    author_id = str(message.author.id)
    stats = await _get_user_stats(author_id)
    spouse_id = stats.get("spouse")

    if not spouse_id:
        await _safe_send_reply(
            message,
            "- *Yuna bursts out laughing WUWAHAHAHAHAH~*\n"
            "\"You're single! Who are you double-aiding with? Your own imagination?!\n"
            "You need to be married to perform a Double Aid! Find a partner with `y!marry @user`!\""
        )
        return

    spouse_id_str = str(spouse_id)
    spouse_stats = await _get_user_stats(spouse_id_str)

    now = time.time()
    last_time_a = _LAST_DOUBLE_AID_TIME.get(author_id, 0.0)
    last_time_s = _LAST_DOUBLE_AID_TIME.get(spouse_id_str, 0.0)
    last_time = max(last_time_a, last_time_s)
    if now - last_time < DOUBLE_AID_COOLDOWN_SECONDS:
        rem = DOUBLE_AID_COOLDOWN_SECONDS - (now - last_time)
        await _safe_send_reply(
            message,
            f"*Yuna waves her arms* \"Give your marriage a breather! Wait {rem:.1f}s before double-aiding again!\""
        )
        return

    target = None
    if message.mentions:
        for m in message.mentions:
            if m.id != message.author.id and (not client or not getattr(client, "user", None) or m.id != client.user.id):
                target = m
                break
        if not target and message.mentions:
            target = message.mentions[0]

    if not target and args:
        for token in args:
            clean = token.strip()
            if not clean or clean.lower() == "aid":
                continue
            uid_match = re.search(r'<@!?(\d{17,20})>', clean) or re.search(r'\d{17,20}', clean)
            if uid_match:
                uid = int(uid_match.group(1) if uid_match.groups() else uid_match.group())
                if getattr(message, "guild", None):
                    try:
                        target = message.guild.get_member(uid)
                    except Exception:
                        pass
                if not target and client:
                    try:
                        target = client.get_user(uid) or await client.fetch_user(uid)
                    except Exception:
                        pass
                if target:
                    break
            elif getattr(message, "guild", None) and getattr(message.guild, "members", None):
                clean_name = clean.lstrip("@").lower()
                for m in message.guild.members:
                    m_name = getattr(m, "name", "").lower()
                    m_nick = getattr(m, "display_name", "").lower()
                    if clean_name in (m_name, m_nick):
                        target = m
                        break
                if target:
                    break

    if not target:
        await _safe_send_reply(
            message,
            "- *Yuna tilts her head and points*\n"
            "\"Who are you and your spouse trying to double-aid? You need another user to interact with this command!\"\n"
            "> Example: `y!doubleaid @username`"
        )
        return

    if target.id == message.author.id:
        await _safe_send_reply(
            message,
            "- *Yuna scoffs* \"You can't aid yourself, silly! Go help someone else!\""
        )
        return

    if str(target.id) == spouse_id_str:
        await _safe_send_reply(
            message,
            "- *Yuna winks and chuckles*\n"
            "\"You two can cuddle in private! Double Aid is for showing off your couple power by helping OTHER people in the server together!\""
        )
        return

    if getattr(target, "bot", False):
        await _safe_send_reply(
            message,
            "- *Yuna pushes your hands away*\n"
            "\"Bots don't need your chaotic couple energy! Go aid a real human!\""
        )
        return

    _LAST_DOUBLE_AID_TIME[author_id] = now
    _LAST_DOUBLE_AID_TIME[spouse_id_str] = now
    target_name = f"<@{target.id}>"
    spouse_name = f"<@{spouse_id_str}>"

    # Couple Virtue bonus: +2% luck (up to 90%) and scaled earnings
    author_v, _ = get_effective_morality(stats)
    spouse_v, _ = get_effective_morality(spouse_stats)
    couple_virtue = max(author_v, spouse_v)

    has_ring = (stats.get("inventory", {}).get("ring", 0) > 0 or 
                spouse_stats.get("inventory", {}).get("ring", 0) > 0)
    ring_boost = 10 if has_ring else 0
    success_threshold = min(95, 55 + int(couple_virtue * 2) + ring_boost)
    rem_odds = 100 - success_threshold
    mess_up_threshold = success_threshold + rem_odds // 2

    roll = random.randint(1, 100)

    if roll <= success_threshold:
        # Power Couple Success!
        scenario_template = random.choice(DOUBLE_AID_SUCCESS_SCENARIOS)
        scenario = scenario_template.format(user=target_name, spouse=spouse_name)
        base_berries = random.randint(60, 140)

        # Virtue money gain: 0.02% balance, 0.2x per virtue, +1% per 2 virtue
        virtue_bonus, v_text = calculate_virtue_kind_bonus(stats, base_berries)
        berries_gained = base_berries + virtue_bonus
        spouse_bonus = 20 + int(virtue_bonus * 0.5)

        # Love kickback into joint vault (10%)
        vault_kickback = max(5, int(berries_gained * 0.10))
        async with _LOCK:
            vault = _get_joint_vault(author_id, spouse_id_str)
            vault["balance"] += vault_kickback
            u_stat = _USER_STATS.setdefault(author_id, _create_default_user())
            u_stat["double_aid_count"] = u_stat.get("double_aid_count", 0) + 1
            _save_data_sync(_USER_STATS)

        await _update_user_stats(
            author_id,
            berries_delta=berries_gained,
            virtue_delta=2,
            sin_delta=0,
            outcome="success"
        )
        await _update_user_stats(
            spouse_id_str,
            berries_delta=spouse_bonus,
            virtue_delta=1,
            sin_delta=0
        )

        unlocked1 = await check_and_award_achievements(author_id, specific_id="dynamic_duo")
        unlocked2 = await check_and_award_achievements(spouse_id, specific_id="dynamic_duo")
        banner = format_achievement_banner(unlocked1 + unlocked2)
        response = (
            f"💞 **DYNAMIC DUO — DOUBLE AID SUCCESS!** 💞\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"- *{scenario}*\n\n"
            f"- Invoker Gained | +{berries_gained:02d} 🫐 | +02 💖 |{v_text}\n"
            f"- Spouse Gained  | +{spouse_bonus:02d} 🫐 | +01 💖 |\n"
            f"- Joint Vault    | +{vault_kickback:02d} 🫐 (Love Kickback!) |{banner}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await _safe_send_reply(message, response)

    elif roll <= mess_up_threshold:
        # 25% Couple Blunder
        scenario_tuple = random.choice(DOUBLE_AID_MESS_UP_SCENARIOS)
        part1 = scenario_tuple[0].format(user=target_name, spouse=spouse_name)
        part2 = scenario_tuple[1].format(user=target_name, spouse=spouse_name)

        await _update_user_stats(
            author_id,
            berries_delta=0,
            virtue_delta=-2,
            sin_delta=2,
            outcome="mess_up"
        )

        unlocked = await check_and_award_achievements(author_id)
        banner = format_achievement_banner(unlocked)

        response = (
            f"💔 **COUPLE DISASTER — DOUBLE AID BLUNDER!** 💔\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"- *{part1}*\n\n"
            f".....Oh no! *{part2}*\n\n"
            f"- Invoker Lost   | -2 💖 Virtue |\n"
            f"- Invoker Gained | +2 ❤️‍🔥 Sin |{banner}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await _safe_send_reply(message, response)

    else:
        # 20% Awkward Couple Overwhelm
        scenario_template = random.choice(DOUBLE_AID_REFUSAL_SCENARIOS)
        scenario = scenario_template.format(user=target_name, spouse=spouse_name)
        berries_gained = random.randint(15, 30)

        await _update_user_stats(
            author_id,
            berries_delta=berries_gained,
            virtue_delta=0,
            sin_delta=0,
            outcome="refused"
        )
        unlocked = await check_and_award_achievements(author_id)
        banner = format_achievement_banner(unlocked)

        response = (
            f"👀 **OVERWHELMED BY ROMANCE!** 👀\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"- *{scenario}*\n\n"
            f"- Consolation Gained | +{berries_gained:02d} 🫐 |\n"
            f"- Virtue / Sin Unchanged{banner}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await _safe_send_reply(message, response)

    await record_task_progress(author_id, "aid")


async def handle_balance(message, client, args: list):
    """Handles y!balance or y!bal."""
    # Check if querying Empress Yuna's Imperial Treasury
    is_yuna = False
    if args and args[0].strip().lstrip("@").lower() in ("yuna", "bot", "treasury", "empress", "yuna's"):
        is_yuna = True
    elif message.mentions and client and client.user and any(m.id == client.user.id for m in message.mentions):
        is_yuna = True

    if is_yuna:
        yuna_stats = await _get_user_stats(YUNA_USER_ID)
        berries = yuna_stats.get("berries", 100000)
        virtue = yuna_stats.get("virtue", 77)
        sin = yuna_stats.get("sin", 77)
        steals = yuna_stats.get("steals_success", 9999)
        v_title = get_virtue_title(virtue)
        s_title = get_sin_title(sin)

        reply_text = (
            f"👑 **Imperial Treasury of Empress Yuna** 👑\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👑 **Status:** *Supreme Monarch of the Berry Realm*\n"
            f"🫐 **Royal Treasury:** `{berries:,}` 🫐\n"
            f"💖 **Virtue:** `{virtue}` *({v_title})*\n"
            f"❤️🔥 **Sin:** `{sin}` *({s_title})*\n"
            f"🥩 **T-Bone Ambush Loot:** `{steals:,}` parcels intercepted\n"
            f"🛡️ **Divine Wards:** `Active (Permanent Imperial Sanctuary)`\n"
            f"📜 **Tax Law:** `25% Royal Inflow on all Transfers`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"*- Yuna proudly raises a sizzling Wagyu steak like a royal scepter* \"All taxes, tolls, and confiscated treats belong to ME! Pay your respects to the crown!\""
        )
        await _safe_send_reply(message, reply_text)
        await record_task_progress(str(message.author.id), "vibe")
        return

    target_user = message.author
    if message.mentions:
        for m in message.mentions:
            if not client or not client.user or m.id != client.user.id:
                target_user = m
                break
        if not target_user and message.mentions:
            target_user = message.mentions[0]
    elif args:
        raw_target = args[0].strip()
        uid_match = re.search(r'\d{17,20}', raw_target)
        if uid_match:
            uid = int(uid_match.group())
            if message.guild:
                found = message.guild.get_member(uid)
                if found:
                    target_user = found
            if target_user == message.author:
                try:
                    found = await client.fetch_user(uid)
                    if found:
                        target_user = found
                except Exception:
                    pass
        elif message.guild:
            clean_name = raw_target.lstrip("@").lower()
            match = discord.utils.find(
                lambda m: m.name.lower() == clean_name or m.display_name.lower() == clean_name,
                message.guild.members
            )
            if match:
                target_user = match

    if client and client.user and getattr(target_user, "id", None) == client.user.id:
        yuna_stats = await _get_user_stats(YUNA_USER_ID)
        berries = yuna_stats.get("berries", 100000)
        virtue = yuna_stats.get("virtue", 77)
        sin = yuna_stats.get("sin", 77)
        steals = yuna_stats.get("steals_success", 9999)
        v_title = get_virtue_title(virtue)
        s_title = get_sin_title(sin)

        reply_text = (
            f"👑 **Imperial Treasury of Empress Yuna** 👑\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👑 **Status:** *Supreme Monarch of the Berry Realm*\n"
            f"🫐 **Royal Treasury:** `{berries:,}` 🫐\n"
            f"💖 **Virtue:** `{virtue}` *({v_title})*\n"
            f"❤️🔥 **Sin:** `{sin}` *({s_title})*\n"
            f"🥩 **T-Bone Ambush Loot:** `{steals:,}` parcels intercepted\n"
            f"🛡️ **Divine Wards:** `Active (Permanent Imperial Sanctuary)`\n"
            f"📜 **Tax Law:** `25% Royal Inflow on all Transfers`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"*- Yuna proudly raises a sizzling Wagyu steak like a royal scepter* \"All taxes, tolls, and confiscated treats belong to ME! Pay your respects to the crown!\""
        )
        await _safe_send_reply(message, reply_text)
        await record_task_progress(str(message.author.id), "vibe")
        return

    stats = await _get_user_stats(str(target_user.id))
    show_equip = bool(args and args[0].lower() in ("equip", "equipment", "gear", "rpg", "armory", "stats"))

    if YUNA_RPG_AVAILABLE and yuna_rpg:
        view = yuna_rpg.BalanceView(str(message.author.id), target_user, sys.modules[__name__], current_page="equip" if show_equip else "pouch")
        if show_equip:
            embed = yuna_rpg.build_equipment_embed(stats, target_user, message.guild)
            await _safe_send_reply(message, embed=embed, view=view)
        else:
            reply_text = format_balance_card_text(target_user, stats)
            await _safe_send_reply(message, reply_text, view=view)
    else:
        reply_text = format_balance_card_text(target_user, stats)
        await _safe_send_reply(message, reply_text)
    await record_task_progress(str(message.author.id), "vibe")

def format_balance_card_text(target_user, stats: dict) -> str:
    """Formats the text for the Soul & Pouch balance card."""
    berries = stats.get("berries", 0)
    virtue = stats.get("virtue", 0)
    sin = stats.get("sin", 0)
    spouse_id = stats.get("spouse")

    display_name = getattr(target_user, "display_name", target_user.name)
    spouse_line = ""
    if spouse_id:
        vault = _get_joint_vault(str(target_user.id), spouse_id)
        v_bal = vault.get("balance", 0)
        spouse_line = f"💍 **Spouse:** <@{spouse_id}>\n🏛️ **Joint Vault:** `{v_bal:,} 🫐` *(y!shared)*\n"

    streak = stats.get("daily_streak", 0)
    streak_line = f"🔥 **Daily Streak:** `{streak} days` *(y!daily)*\n" if streak > 0 else ""
    g_streak = stats.get("gamble_win_streak", 0)
    g_max_streak = stats.get("max_win_streak", 0)
    if g_streak > 0 or g_max_streak > 0:
        streak_line += f"🎲 **Win Streak:** `{g_streak}` wins *(Record: `{g_max_streak}`)* *(y!streak)*\n"

    eff_v, eff_s = get_effective_morality(stats)
    v_title = get_virtue_title(virtue)
    s_title = get_sin_title(sin)

    if eff_v > 0:
        v_line = f"💖 **Virtue:** `{virtue}/33` *({v_title})* `[ACTIVE]` *(Kind Acts Boosted & Karmic Ward)*"
        s_line = f"❤️🔥 **Sin:** `{sin}/30` *({s_title})* `[DORMANT]`"
    elif eff_s > 0:
        v_line = f"💖 **Virtue:** `{virtue}/33` *({v_title})* `[DORMANT]`"
        s_line = f"❤️🔥 **Sin:** `{sin}/30` *({s_title})* `[ACTIVE]` *(+{eff_s * 0.1:.1f}x Gamble Payout)*"
    else:
        v_line = f"💖 **Virtue:** `{virtue}/33` *({v_title})*"
        s_line = f"❤️🔥 **Sin:** `{sin}/30` *({s_title})*"

    custom_title = stats.get("title")
    title_line = f"🎖️ **Title:** *{custom_title}*\n" if custom_title else ""
    warning_line = get_sin_warning_banner(stats)

    has_crown = stats.get("inventory", {}).get("crown", 0) > 0
    crown_line = "👑 **Status:** *Empress Crown Bearer*\n" if has_crown else ""

    inv = stats.get("inventory", {})
    item_count = sum(inv.values())
    inv_line = f"🎒 **Inventory:** `{item_count} items` *(y!inv)*\n" if item_count > 0 else ""

    buffs = []
    if stats.get("clover_active"):
        buffs.append("🍀 Clover (+25% Luck)")
    if stats.get("mask_active"):
        buffs.append("🎭 Mask (0 Sin & +30% Loot)")
    buff_line = f"🔮 **Active Buffs:** {' | '.join(buffs)}\n" if buffs else ""

    # Battle & Dungeon Summary
    b_lvl = stats.get("battle_level", 1)
    d_stg = stats.get("godhell_highest_stage", 0)
    d_str = f"GoD-HeLL: Stage {d_stg}/10" if d_stg > 0 else "GoD-HeLL: Untested"
    battle_line = f"⚔️ **Battle:** `Lv. {b_lvl}` | `{d_str}` *(Click below for Equipment!)*\n"

    return (
        f"🫐 **{display_name}'s Soul & Pouch** 🫐\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{crown_line}"
        f"{title_line}"
        f"🫐 **Berries:** `{berries:,}`\n"
        f"{v_line}\n"
        f"{s_line}\n"
        f"{spouse_line}"
        f"{streak_line}"
        f"{inv_line}"
        f"{battle_line}"
        f"{buff_line}"
        f"━━━━━━━━━━━━━━━━━━"
        f"{warning_line}"
    )


async def handle_aid(message, client, args: list):
    """Handles y!aid <@user>."""
    author_id = str(message.author.id)

    now = time.time()
    last_time = _LAST_AID_TIME.get(author_id, 0.0)
    if now - last_time < AID_COOLDOWN_SECONDS:
        rem = AID_COOLDOWN_SECONDS - (now - last_time)
        await _safe_send_reply(
            message,
            f"*Yuna taps her foot impatiently* \"Slow down! Wait {rem:.1f}s before trying to aid someone again!\""
        )
        return

    target = None
    if message.mentions:
        for m in message.mentions:
            if m.id != message.author.id and (not client.user or m.id != client.user.id):
                target = m
                break
        if not target:
            for m in message.mentions:
                if m.id != message.author.id:
                    target = m
                    break
        if not target and message.mentions:
            target = message.mentions[0]

    if not target and args:
        raw_target = args[0].strip()
        uid_match = re.search(r'\d{17,20}', raw_target)
        if uid_match:
            uid = int(uid_match.group())
            if message.guild:
                target = message.guild.get_member(uid)
            if not target:
                try:
                    target = await client.fetch_user(uid)
                except Exception:
                    pass
        elif message.guild:
            clean_name = raw_target.lstrip("@").lower()
            target = discord.utils.find(
                lambda m: m.name.lower() == clean_name or m.display_name.lower() == clean_name,
                message.guild.members
            )

    if not target:
        await _safe_send_reply(
            message,
            "- *Yuna tilts her head and crosses her arms*\n"
            "\"Who are you trying to aid? You need another user to interact with this command!\"\n"
            "> Example: `y!aid @username`"
        )
        return

    if target.id == message.author.id:
        await _safe_send_reply(
            message,
            "- *Yuna scoffs and laughs WUWAHAHAHAHAH~*\n"
            "\"You can't aid yourself, silly! You need another user to interact with this command!\""
        )
        return

    if getattr(target, "bot", False):
        await _safe_send_reply(
            message,
            "- *Yuna pushes your hand away with a pout*\n"
            "\"Bots don't need your clumsy mortal help! Go aid a real human!\""
        )
        return

    _LAST_AID_TIME[author_id] = now
    target_name = f"<@{target.id}>"

    stats = await _get_user_stats(author_id)
    author_virtue, _ = get_effective_morality(stats)

    # Virtue increases luck (success rate): +2% per point (base 50%, capped at 85%)
    success_threshold = min(85, 50 + int(author_virtue * 2))
    rem_odds = 100 - success_threshold
    mess_up_threshold = success_threshold + rem_odds // 2

    roll = random.randint(1, 100)

    if roll <= success_threshold:
        # Success!
        scenario_template = random.choice(SUCCESS_SCENARIOS)
        scenario = scenario_template.format(user=target_name)
        base_berries = random.randint(20, 50)

        # Virtue scaling: 0.02% balance, 0.2x per virtue, +1% per 2 virtue
        virtue_bonus, virtue_bonus_text = calculate_virtue_kind_bonus(stats, base_berries)
        berries_gained = base_berries + virtue_bonus

        spouse_bonus_text = ""
        if stats.get("spouse"):
            bonus = max(5, int(berries_gained * 0.25))
            berries_gained += bonus
            spouse_bonus_text = f" 💍 *(Spouse Bonus: +{bonus} 🫐)*"

        await _update_user_stats(
            author_id,
            berries_delta=berries_gained,
            virtue_delta=1,
            sin_delta=0,
            outcome="success"
        )
        unlocked = await check_and_award_achievements(author_id)
        banner = format_achievement_banner(unlocked)

        response = (
            f"- *{scenario}*\n\n"
            f"- Gained | +{berries_gained:02d} 🫐 |{spouse_bonus_text}{virtue_bonus_text}\n"
            f"- Gained | +01 💖 |\n"
            f"- Gained | +00 ❤️🔥|{banner}"
        )
        await _safe_send_reply(message, response)
        await record_task_progress(author_id, "aid")

    elif roll <= mess_up_threshold:
        # 25% Mess up
        scenario_tuple = random.choice(MESS_UP_SCENARIOS)
        part1 = scenario_tuple[0].format(user=target_name)
        part2 = scenario_tuple[1].format(user=target_name)

        await _update_user_stats(
            author_id,
            berries_delta=0,
            virtue_delta=-1,
            sin_delta=1,
            outcome="mess_up"
        )
        unlocked = await check_and_award_achievements(author_id)
        banner = format_achievement_banner(unlocked)

        response = (
            f"- *{part1}*\n\n\n"
            f".....Oh *{part2}*\n\n"
            f"- Gained | +00 🫐 |\n"
            f"- lost | -1 💖 |\n"
            f"- Gained | +1 ❤️🔥 |{banner}"
        )
        await _safe_send_reply(message, response)

    else:
        # 25% Refusal
        scenario_template = random.choice(REFUSAL_SCENARIOS)
        scenario = scenario_template.format(user=target_name)
        berries_gained = random.randint(5, 15)

        await _update_user_stats(
            author_id,
            berries_delta=berries_gained,
            virtue_delta=0,
            sin_delta=0,
            outcome="refused"
        )
        unlocked = await check_and_award_achievements(author_id)
        banner = format_achievement_banner(unlocked)

        response = (
            f"- *{scenario}*\n\n"
            f"- Gained | +{berries_gained:02d} 🫐 |\n"
            f"- Gained | +00 💖 |\n"
            f"- Gained | +00 ❤️🔥|{banner}"
        )
        await _safe_send_reply(message, response)
        await record_task_progress(author_id, "aid")


async def handle_give(message, client, args: list):
    """Handles y!give @user <amount> or y!pay."""
    author_id = str(message.author.id)
    amount = None
    raw_target_token = None

    for a in args:
        cleaned = a.replace(",", "")
        if cleaned.isdigit() and amount is None:
            amount = int(cleaned)
        elif raw_target_token is None and not cleaned.isdigit():
            raw_target_token = a

    target = None
    if message.mentions:
        for m in message.mentions:
            if m.id != message.author.id and (not client or not client.user or m.id != client.user.id):
                target = m
                break
        if not target and message.mentions:
            target = message.mentions[0]

    # Check if target is Empress Yuna
    is_target_yuna = False
    if raw_target_token and raw_target_token.lstrip("@").lower() in ("yuna", "empress", "treasury"):
        is_target_yuna = True
    elif message.mentions and client and client.user and any(m.id == client.user.id for m in message.mentions):
        is_target_yuna = True

    if not is_target_yuna and not target and raw_target_token:
        uid_match = re.search(r'\d{17,20}', raw_target_token)
        if uid_match:
            uid = int(uid_match.group())
            if message.guild:
                target = message.guild.get_member(uid)
            if not target:
                try:
                    target = await client.fetch_user(uid)
                except Exception:
                    pass
        elif message.guild:
            clean_name = raw_target_token.lstrip("@").lower()
            target = discord.utils.find(
                lambda m: m.name.lower() == clean_name or m.display_name.lower() == clean_name,
                message.guild.members
            )

    if not is_target_yuna and target and client and client.user and target.id == client.user.id:
        is_target_yuna = True

    if not target and not is_target_yuna:
        await _safe_send_reply(
            message,
            "- *Yuna tilts her head* \"Who are you trying to pay? Usage: `y!give @user <amount>`\""
        )
        return

    if amount is None or amount <= 0:
        await _safe_send_reply(
            message,
            "- *Yuna frowns* \"How many berries are you giving? Specify a valid amount! Example: `y!give @user 50`\""
        )
        return

    author_stats = await _get_user_stats(author_id)
    author_berries = author_stats.get("berries", 0)

    # 1. Direct tribute to Empress Yuna
    if is_target_yuna:
        if author_berries < amount:
            await _safe_send_reply(
                message,
                f"- *Yuna scoffs* \"You want to pay tribute to Empress Yuna with berries you don't have?! You only have **{author_berries:,}** 🫐!\""
            )
            return

        updated = await _atomic_multi_account_update([
            {"user_id": author_id, "berries_delta": -amount, "virtue_delta": 1},
            {"user_id": YUNA_USER_ID, "berries_delta": amount}
        ])
        author_rem = updated[author_id]["berries"]
        yuna_new = updated[YUNA_USER_ID]["berries"]

        unlocked = await check_and_award_achievements(author_id)
        banner = format_achievement_banner(unlocked)

        reply_text = (
            f"👑 **ROYAL TRIBUTE ACCEPTED!** 👑\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{message.author.mention} presented a royal tribute of **{amount:,}** 🫐 directly into Empress Yuna's Imperial Treasury!\n"
            f"✨ *Empress Yuna beams with delight, offering a royal nod:* \"Your devotion and piety are noted, loyal subject! (+01 💖 Virtue)\"\n"
            f"🏛️ **Royal Treasury:** `{yuna_new:,}` 🫐\n"
            f"💰 *Your remaining balance:* `{author_rem:,}` 🫐\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━{banner}"
        )
        await _safe_send_reply(message, reply_text)
        await record_task_progress(author_id, "generosity")
        return

    if target.id == message.author.id:
        await _safe_send_reply(
            message,
            "- *Yuna scoffs* \"You can't give berries to yourself! That doesn't change anything, silly!\""
        )
        return

    if getattr(target, "bot", False):
        await _safe_send_reply(
            message,
            "- *Yuna crosses her arms* \"Other bots don't eat berries! Give them to a mortal or tribute them to Empress Yuna!\""
        )
        return

    # 2. Transfer between players: 25% Royal Tax
    tax = max(1, int(amount * 0.25))
    total_cost = amount + tax

    if author_berries < total_cost:
        await _safe_send_reply(
            message,
            f"- *Yuna crosses her arms* \"Transferring **{amount:,}** 🫐 requires a **25% royal tax** (**{tax:,}** 🫐)! Total needed: **{total_cost:,}** 🫐.\n"
            f"You only have **{author_berries:,}** 🫐, broke mortal!\""
        )
        return

    # 45% Hidden Chance: Yuna "steaks" 75% of the transferred amount
    is_steak_heist = (random.random() < 0.45)
    if is_steak_heist:
        stolen_by_yuna = max(1, int(amount * 0.75))
        delivered_to_target = amount - stolen_by_yuna
        yuna_total_gain = tax + stolen_by_yuna

        updated = await _atomic_multi_account_update([
            {"user_id": author_id, "berries_delta": -total_cost},
            {"user_id": str(target.id), "berries_delta": delivered_to_target},
            {"user_id": YUNA_USER_ID, "berries_delta": yuna_total_gain, "outcome": "steal_success"}
        ])
        author_rem = updated[author_id]["berries"]
        target_rem = updated[str(target.id)]["berries"]
        yuna_new = updated[YUNA_USER_ID]["berries"]

        unlocked_author = await check_and_award_achievements(author_id)
        unlocked_target = await check_and_award_achievements(str(target.id))
        banner = format_achievement_banner(unlocked_author + unlocked_target)

        scenario = random.choice(STEAK_HEIST_SCENARIOS).format(
            sender=message.author.mention,
            target=f"<@{target.id}>"
        )
        reply_text = (
            f"🥩 **THE ROYAL STEAK HEIST!** 🥩\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{scenario}\n\n"
            f"*- Yuna takes a glorious bite of steak and cackles* \"MEHEHEHEHE! The Empress demands an impromptu 75% transit snack fee! Yoink!\"\n\n"
            f"📦 **Transfer Breakdown:**\n"
            f"- 🫐 **Sent:** `{amount:,}` 🫐 *(+`{tax:,}` 🫐 25% Royal Tax)*\n"
            f"- 🥩 **Snatched by Yuna (75%):** `-{stolen_by_yuna:,}` 🫐\n"
            f"- 👑 **Empress Yuna Hoard (+Tax & Steak):** `+{yuna_total_gain:,}` 🫐 *(Treasury: `{yuna_new:,}` 🫐)*\n"
            f"- 📬 **Actually Delivered to <@{target.id}>:** `+{delivered_to_target:,}` 🫐 *(Balance: `{target_rem:,}` 🫐)*\n"
            f"- 💰 **Sender Remaining:** `{author_rem:,}` 🫐\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━{banner}"
        )
        await _safe_send_reply(message, reply_text)
        await record_task_progress(author_id, "generosity")
        return

    # Normal delivery (55% chance): 100% delivered to target, 25% tax deposited to Yuna
    updated = await _atomic_multi_account_update([
        {"user_id": author_id, "berries_delta": -total_cost},
        {"user_id": str(target.id), "berries_delta": amount},
        {"user_id": YUNA_USER_ID, "berries_delta": tax}
    ])
    author_rem = updated[author_id]["berries"]
    target_rem = updated[str(target.id)]["berries"]
    yuna_new = updated[YUNA_USER_ID]["berries"]

    unlocked_author = await check_and_award_achievements(author_id)
    unlocked_target = await check_and_award_achievements(str(target.id))
    banner = format_achievement_banner(unlocked_author + unlocked_target)

    reply_text = (
        f"🫐 **Berry Transfer Successful!** 🫐\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{message.author.mention} transferred **{amount:,}** 🫐 to <@{target.id}>!\n"
        f"👑 **Royal Tax (25%):** `{tax:,}` 🫐 deposited into Empress Yuna's Treasury *(Treasury: `{yuna_new:,}` 🫐)*.\n"
        f"📬 **Recipient Balance:** `{target_rem:,}` 🫐\n"
        f"💰 *Your remaining balance:* `{author_rem:,}` 🫐\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━{banner}"
    )
    await _safe_send_reply(message, reply_text)
    await record_task_progress(author_id, "generosity")


async def handle_steal(message, client, args: list):
    """Handles y!steal @user."""
    author_id = str(message.author.id)

    now = time.time()
    last_time = _LAST_STEAL_TIME.get(author_id, 0.0)
    if now - last_time < STEAL_COOLDOWN_SECONDS:
        rem = STEAL_COOLDOWN_SECONDS - (now - last_time)
        await _safe_send_reply(
            message,
            f"*Yuna whispers* \"Keep your hands to yourself! The guards are watching! Wait {rem:.1f}s before attempting another robbery!\""
        )
        return

    target = None
    if message.mentions:
        for m in message.mentions:
            if m.id != message.author.id and (not client or not getattr(client, "user", None) or m.id != client.user.id):
                target = m
                break
        if not target and message.mentions:
            target = message.mentions[0]

    if not target and args:
        raw_target = args[0].strip()
        uid_match = re.search(r'\d{17,20}', raw_target)
        if uid_match:
            uid = int(uid_match.group())
            if message.guild:
                target = message.guild.get_member(uid)
            if not target:
                try:
                    target = await client.fetch_user(uid)
                except Exception:
                    pass
        elif message.guild:
            clean_name = raw_target.lstrip("@").lower()
            target = discord.utils.find(
                lambda m: m.name.lower() == clean_name or m.display_name.lower() == clean_name,
                message.guild.members
            )

    if not target:
        await _safe_send_reply(
            message,
            "- *Yuna tilts her head* \"Who are you trying to steal from? Mention someone! Example: `y!steal @user`\""
        )
        return

    if target.id == message.author.id:
        await _safe_send_reply(
            message,
            "- *Yuna blinks in disbelief* \"You want to rob yourself? Are you experiencing memory loss?\""
        )
        return

    # Check if attempting to rob Empress Yuna
    if (args and args[0].strip().lstrip("@").lower() in ("yuna", "empress", "treasury")) or (client and client.user and target and target.id == client.user.id):
        await _safe_send_reply(
            message,
            "- 🥩 *Yuna slaps your hand away with a sizzling Wagyu T-Bone steak!* \"WUWAHAHA! Are you insane?! You cannot rob Empress Yuna! The Imperial Guards would turn you into berry compost before you even touched my pouch!\""
        )
        return

    if getattr(target, "bot", False):
        await _safe_send_reply(
            message,
            "- *Yuna scoffs* \"Bots don't carry berry pouches, genius! Find a real player to pickpocket!\""
        )
        return

    author_stats = await _get_user_stats(author_id)
    if author_stats.get("spouse") == str(target.id):
        await _safe_send_reply(
            message,
            "- 💍 *Yuna grabs your wrist!* \"Are you seriously trying to pickpocket your own spouse?! What's yours is theirs! Keep your sticky fingers away!\""
        )
        return

    target_stats = await _get_user_stats(str(target.id))
    target_berries = target_stats.get("berries", 0)

    if target_berries <= 0:
        await _safe_send_reply(
            message,
            f"- *Yuna sighs* \"<@{target.id}> is completely broke! They don't have a single berry on them to steal!\""
        )
        return

    _LAST_STEAL_TIME[author_id] = now
    target_name = f"<@{target.id}>"

    t_eff_v, t_eff_s = get_effective_morality(target_stats)

    # 1. Virtue Protection Check (5% protection per 5 points of Virtue)
    if t_eff_v >= 5:
        virtue_prot = (t_eff_v // 5) * 0.05
        if random.random() < virtue_prot:
            await _update_user_stats(author_id, sin_delta=1)
            await _safe_send_reply(
                message,
                f"✨ **VIRTUE SANCTUARY DEFLECTION!** ✨\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{target_name}'s pure Virtue aura ({t_eff_v} 💖) forms an impenetrable holy shield!\n"
                f"Your theft was completely repelled by their sacred benevolence ({int(virtue_prot * 100)}% Protection)!\n"
                f"- Gained | +01 ❤️🔥|\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            return

    # 2. Heavenly Shield / Divine Ward Protection Check (with Sin corruption scaling)
    if target_stats.get("inventory", {}).get("ward", 0) > 0:
        # Always consumes 1 shield on trigger
        async with _LOCK:
            _USER_STATS[str(target.id)]["inventory"]["ward"] -= 1
            if _USER_STATS[str(target.id)]["inventory"]["ward"] <= 0:
                _USER_STATS[str(target.id)]["inventory"].pop("ward", None)
            _save_data_sync(_USER_STATS)

        corr_res = resolve_sin_shield_corruption(t_eff_s)
        if corr_res["corrupted"]:
            async with _LOCK:
                _USER_STATS[str(target.id)]["ward_corrupted_count"] = _USER_STATS[str(target.id)].get("ward_corrupted_count", 0) + 1
                _save_data_sync(_USER_STATS)
            await check_and_award_achievements(str(target.id))

            fail_pct = int(corr_res["failure_rate"] * 100)
            outcome = corr_res["outcome"]

            if outcome == "catastrophic_explosion":
                # At 26-30 Sin: Complete failure, shield explodes!
                recoil_penalty = min(target_berries, max(50, int(target_berries * 0.05)))
                if recoil_penalty > 0:
                    await _update_user_stats(str(target.id), berries_delta=-recoil_penalty, outcome="shield_explosion_recoil")

                await _safe_send_reply(
                    message,
                    f"⚠️ **YOUR HEAVENLY SHIELD HAS BEEN CORRUPTED BY YOUR SINS!** ⚠️\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"💬 {target_name}: *\"I have prepared for this.\"*\n"
                    f"😈 **Juny-HWA**: *\"Have you?\"*\n"
                    f"💥 **HEAVENLY SHIELD: FUCKING EXPLODES!**\n"
                    f"The sacred relic could not bear {target_name}'s dark sins ({t_eff_s} ❤️‍🔥, {fail_pct}% failure chance)!\n"
                    f"It detonated violently in their hands, scorching **{recoil_penalty:,}** 🫐 from their pouch and leaving them completely defenseless!\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                # Shield completely failed to protect! Theft proceeds!

            elif outcome == "fails":
                await _safe_send_reply(
                    message,
                    f"⚠️ **YOUR HEAVENLY SHIELD HAS BEEN CORRUPTED BY YOUR SINS!** ⚠️\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"{target_name}'s Heavenly Shield fizzled and failed to activate due to their dark sins ({t_eff_s} ❤️‍🔥, {fail_pct}% failure chance)!\n"
                    f"The holy barrier sputtered into useless smoke, leaving them completely vulnerable!\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                # Shield failed! Theft proceeds!

            elif outcome == "partial":
                # Absorbs only 50% of the theft!
                stolen_rate = random.uniform(0.15, 0.35)
                full_loot = max(2, int(target_berries * stolen_rate))
                half_loot = max(1, full_loot // 2)
                await _atomic_multi_account_update([
                    {"user_id": str(target.id), "berries_delta": -half_loot, "outcome": "stolen_partial_shield"},
                    {"user_id": author_id, "berries_delta": half_loot, "sin_delta": 1, "outcome": "steal_success"}
                ])
                await _safe_send_reply(
                    message,
                    f"⚠️ **YOUR HEAVENLY SHIELD HAS BEEN CORRUPTED BY YOUR SINS!** ⚠️\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"{target_name}'s Heavenly Shield cracked under karmic darkness ({t_eff_s} ❤️‍🔥)!\n"
                    f"It only absorbed **50%** of the robbery! <@{author_id}> slipped through and stole **{half_loot:,}** 🫐 (halved by damaged shield)!\n"
                    f"- Gained | +01 ❤️🔥|\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                return

            elif outcome == "breaks_after":
                # Blocks 100%, shocks thief, but breaks with a warning
                author_berries = author_stats.get("berries", 0)
                ward_thief_scale = int(author_berries * random.uniform(0.20, 0.35))
                ward_target_scale = int(target_berries * 0.15)
                base_shock = max(50, ward_thief_scale, ward_target_scale)
                shock_fine = min(author_berries, base_shock)
                sin_penalty = 1 if shock_fine > 0 else 3
                if shock_fine > 0:
                    await _atomic_multi_account_update([
                        {"user_id": author_id, "berries_delta": -shock_fine, "sin_delta": sin_penalty, "outcome": "ward_fine"},
                        {"user_id": str(target.id), "berries_delta": shock_fine, "outcome": "ward_reward"}
                    ])
                else:
                    await _update_user_stats(author_id, sin_delta=sin_penalty)

                await _safe_send_reply(
                    message,
                    f"⚠️ **YOUR HEAVENLY SHIELD HAS BEEN CORRUPTED BY YOUR SINS!** ⚠️\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"{target_name}'s Heavenly Shield deflected the thief and shocked them for **{shock_fine:,}** 🫐, but the corrupted divine metal **SHATTERED INTO BRITTLE SHARDS AFTER ACTIVATION**!\n"
                    f"- Gained | +{sin_penalty:02d} ❤️🔥|\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                return

            elif outcome == "penalty":
                # Blocks thief, but inflicts penalty on user
                recoil_penalty = min(target_berries, max(50, int(target_berries * 0.05)))
                author_berries = author_stats.get("berries", 0)
                ward_thief_scale = int(author_berries * random.uniform(0.20, 0.35))
                base_shock = max(50, ward_thief_scale)
                shock_fine = min(author_berries, base_shock)
                sin_penalty = 1 if shock_fine > 0 else 3

                updates = [
                    {"user_id": author_id, "berries_delta": -shock_fine, "sin_delta": sin_penalty, "outcome": "ward_fine"},
                    {"user_id": str(target.id), "berries_delta": -recoil_penalty, "outcome": "shield_recoil_penalty"}
                ]
                await _atomic_multi_account_update(updates)

                await _safe_send_reply(
                    message,
                    f"⚠️ **YOUR HEAVENLY SHIELD HAS BEEN CORRUPTED BY YOUR SINS!** ⚠️\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"{target_name}'s Heavenly Shield deflected the thief, but **INFLICTED A DIVINE PENALTY** on its sinful bearer ({t_eff_s} ❤️‍🔥)!\n"
                    f"A surge of holy backlash burned **{recoil_penalty:,}** 🫐 from {target_name}'s own pouch, while the thief was zapped for **{shock_fine:,}** 🫐!\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                return

        else:
            # 100% block and shock thief normally
            author_berries = author_stats.get("berries", 0)
            ward_thief_scale = int(author_berries * random.uniform(0.20, 0.35))
            ward_target_scale = int(target_berries * 0.15)
            base_shock = max(50, ward_thief_scale, ward_target_scale)
            shock_fine = min(author_berries, base_shock)
            sin_penalty = 1 if shock_fine > 0 else 3

            if shock_fine > 0:
                await _atomic_multi_account_update([
                    {"user_id": author_id, "berries_delta": -shock_fine, "sin_delta": sin_penalty, "outcome": "ward_fine"},
                    {"user_id": str(target.id), "berries_delta": shock_fine, "outcome": "ward_reward"}
                ])
            else:
                await _update_user_stats(author_id, sin_delta=sin_penalty)

            await _safe_send_reply(
                message,
                f"🛡️ **HEAVENLY SHIELD DEFLECTION!** ⚡\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"As you reach for {target_name}'s pouch, their **Heavenly Shield** radiates pure uncorrupted holy light, **BLOCKING 100%** of your theft!\n"
                f"You were blasted backwards, losing **{shock_fine:,}** 🫐 to {target_name} as restitution, and their shield broke!\n"
                f"- Gained | +{sin_penalty:02d} ❤️🔥|\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            return

    # Check Thief Buffs (Clover & Mask)
    has_clover = author_stats.get("clover_active", False)
    if has_clover:
        async with _LOCK:
            _USER_STATS[author_id]["clover_active"] = False
            _save_data_sync(_USER_STATS)

    has_mask = author_stats.get("mask_active", False)
    if has_mask:
        async with _LOCK:
            _USER_STATS[author_id]["mask_active"] = False
            _save_data_sync(_USER_STATS)

    # Success threshold: Base 45% + 25% if clover active + vulnerability if victim has Sin
    success_threshold = 70 if has_clover else 45
    if t_eff_s > 0:
        success_threshold = min(90, success_threshold + int(t_eff_s * 1.5))
    roll = random.randint(1, 100)

    if roll <= success_threshold:
        # Success! Stolen amount scales dynamically with target's balance (15% to 35%)
        loot_rate = random.uniform(0.15, 0.35)
        base_stolen = max(5, int(target_berries * loot_rate))
        if has_mask:
            base_stolen = int(base_stolen * 1.30)
            async with _LOCK:
                _USER_STATS[author_id]["phantom_steals_count"] = _USER_STATS[author_id].get("phantom_steals_count", 0) + 1
                _save_data_sync(_USER_STATS)
        stolen = min(base_stolen, target_berries)

        sin_gain = 0 if has_mask else 2
        updated = await _atomic_multi_account_update([
            {"user_id": author_id, "berries_delta": stolen, "sin_delta": sin_gain, "outcome": "steal_success"},
            {"user_id": str(target.id), "berries_delta": -stolen}
        ])
        victim_new_berries = updated[str(target.id)]["berries"]

        unlocked = await check_and_award_achievements(author_id)
        banner = format_achievement_banner(unlocked)

        buff_tags = []
        if has_clover:
            buff_tags.append("🍀 *(Lucky Clover +25% Success!)*")
        if has_mask:
            buff_tags.append("🎭 *(Phantom Mask: 0 Sin & +30% Loot!)*")
        buff_str = ("\n" + " ".join(buff_tags)) if buff_tags else ""

        scenario = random.choice(STEAL_SUCCESS_SCENARIOS).format(user=target_name)
        response = (
            f"- *{scenario}*\n\n"
            f"- Stole | +{stolen:,} 🫐 from {target_name} |\n"
            f"- Depleted | -{stolen:,} 🫐 from {target_name}'s pouch (Remaining: {victim_new_berries:,} 🫐) |\n"
            f"- Gained | +00 💖 |\n"
            f"- Gained | +{sin_gain:02d} ❤️🔥|{buff_str}{banner}"
        )
        await _safe_send_reply(message, response)

    else:
        # Caught! Restitution penalty scales with both thief's balance (15%-30%) and target's balance (10%-20%)
        author_stats_fresh = await _get_user_stats(author_id)
        author_berries = author_stats_fresh.get("berries", 0)

        thief_fine = int(author_berries * random.uniform(0.15, 0.30))
        target_fine = int(target_berries * random.uniform(0.10, 0.20))
        base_fine = max(25, thief_fine, target_fine)
        fine = min(author_berries, base_fine)

        if author_berries == 0:
            sin_gain = 0 if has_mask else 3
            fine_line = f"- lost | +00 🫐 (you're too broke to pay a fine! Penalized with extra ❤️‍🔥 Sin!) |"
        else:
            sin_gain = 0 if has_mask else 1
            fine_line = f"- lost | -{fine:,} 🫐 (paid as restitution to {target_name}) |"

        if fine > 0:
            await _atomic_multi_account_update([
                {"user_id": author_id, "berries_delta": -fine, "sin_delta": sin_gain},
                {"user_id": str(target.id), "berries_delta": fine}
            ])
        else:
            await _update_user_stats(author_id, sin_delta=sin_gain)

        unlocked = await check_and_award_achievements(author_id)
        banner = format_achievement_banner(unlocked)

        scenario = random.choice(STEAL_CAUGHT_SCENARIOS).format(user=target_name)
        response = (
            f"- *{scenario}*\n\n"
            f"{fine_line}\n"
            f"- Gained | +00 💖 |\n"
            f"- Gained | +{sin_gain:02d} ❤️🔥|{banner}"
        )
        await _safe_send_reply(message, response)


async def handle_doublesteal(message, client, args: list):
    """Handles y!doublesteal @victim (Married couple tag-team heist)."""
    author_id = str(message.author.id)
    now = time.time()
    last_time = _LAST_DOUBLE_STEAL_TIME.get(author_id, 0.0)
    if now - last_time < DOUBLE_STEAL_COOLDOWN_SECONDS:
        rem = DOUBLE_STEAL_COOLDOWN_SECONDS - (now - last_time)
        await _safe_send_reply(
            message,
            f"- *Yuna whispers* \"Slow down, Bonnie & Clyde! The town watch is still combing the area! Wait **{rem:.1f}s** before attempting another double-heist!\""
        )
        return

    stats = await _get_user_stats(author_id)
    spouse_id = stats.get("spouse")
    if not spouse_id:
        await _safe_send_reply(
            message,
            "- 💔 *Yuna crosses her arms* \"You need a married spouse to execute a Double Steal! Propose with `y!marry @user` first!\""
        )
        return

    # Find target
    target = None
    if message.mentions:
        for m in message.mentions:
            if m.id != message.author.id and (not client or not getattr(client, "user", None) or m.id != client.user.id):
                target = m
                break

    if not target and args:
        raw_target = args[0].strip()
        uid_match = re.search(r'\d{17,20}', raw_target)
        if uid_match:
            uid = int(uid_match.group())
            if message.guild:
                target = message.guild.get_member(uid)
            if not target:
                try:
                    target = await client.fetch_user(uid)
                except Exception:
                    pass
        elif message.guild:
            clean_name = raw_target.lstrip("@").lower()
            target = discord.utils.find(
                lambda m: m.name.lower() == clean_name or m.display_name.lower() == clean_name,
                message.guild.members
            )

    if not target:
        await _safe_send_reply(message, "- *Yuna tilts her head* \"Who are you and your spouse robbing? Usage: `y!doublesteal @victim`\"")
        return

    if target.id == message.author.id or str(target.id) == spouse_id:
        await _safe_send_reply(message, "- *Yuna laughs* \"You can't rob yourselves, you absolute clowns! Pick a third party!\"")
        return

    # Check if attempting to rob Empress Yuna
    if (args and args[0].strip().lstrip("@").lower() in ("yuna", "empress", "treasury")) or (client and client.user and target and target.id == client.user.id):
        await _safe_send_reply(
            message,
            "- 🥩 *Yuna smirks, tapping her T-Bone steak rhythmically against her palm.* \"A double heist against Empress Yuna?! Nice try, lovebirds! Go pick on a mortal instead!\""
        )
        return

    if getattr(target, "bot", False):
        await _safe_send_reply(message, "- *Yuna scoffs* \"Bots don't carry berry pouches! Pick a living player!\"")
        return

    target_stats = await _get_user_stats(str(target.id))
    target_berries = target_stats.get("berries", 0)
    if target_berries <= 0:
        await _safe_send_reply(message, f"- *Yuna sighs* \"<@{target.id}> doesn't have a single berry to their name! Move along!\"")
        return

    _LAST_DOUBLE_STEAL_TIME[author_id] = now
    target_name = f"<@{target.id}>"

    # 1. Victim Heavenly Shield check (with Sin corruption scaling)
    if target_stats.get("inventory", {}).get("ward", 0) > 0:
        async with _LOCK:
            _USER_STATS[str(target.id)]["inventory"]["ward"] -= 1
            if _USER_STATS[str(target.id)]["inventory"]["ward"] <= 0:
                _USER_STATS[str(target.id)]["inventory"].pop("ward", None)
            _save_data_sync(_USER_STATS)

        _, t_sin = get_effective_morality(target_stats)
        corr_res = resolve_sin_shield_corruption(t_sin)
        if corr_res["corrupted"]:
            async with _LOCK:
                _USER_STATS[str(target.id)]["ward_corrupted_count"] = _USER_STATS[str(target.id)].get("ward_corrupted_count", 0) + 1
                _save_data_sync(_USER_STATS)
            await check_and_award_achievements(str(target.id))

            fail_pct = int(corr_res["failure_rate"] * 100)
            outcome = corr_res["outcome"]

            if outcome == "catastrophic_explosion":
                recoil_penalty = min(target_berries, max(50, int(target_berries * 0.05)))
                if recoil_penalty > 0:
                    await _update_user_stats(str(target.id), berries_delta=-recoil_penalty, outcome="shield_explosion_recoil")

                await _safe_send_reply(
                    message,
                    f"⚠️ **YOUR HEAVENLY SHIELD HAS BEEN CORRUPTED BY YOUR SINS!** ⚠️\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"💬 {target_name}: *\"I have prepared for this.\"*\n"
                    f"😈 **Juny-HWA**: *\"Have you?\"*\n"
                    f"💥 **HEAVENLY SHIELD: FUCKING EXPLODES!**\n"
                    f"The sacred relic could not bear {target_name}'s dark sins ({t_sin} ❤️‍🔥, {fail_pct}% failure chance)!\n"
                    f"It detonated violently in their hands, scorching **{recoil_penalty:,}** 🫐 from their pouch and leaving them completely defenseless!\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                # Shield failed completely! Double steal proceeds!

            elif outcome == "fails":
                await _safe_send_reply(
                    message,
                    f"⚠️ **YOUR HEAVENLY SHIELD HAS BEEN CORRUPTED BY YOUR SINS!** ⚠️\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"{target_name}'s Heavenly Shield sputtered and failed to activate due to their dark sins ({t_sin} ❤️‍🔥, {fail_pct}% failure chance)!\n"
                    f"The holy barrier crumbled away, leaving them vulnerable to the double heist!\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                # Shield failed! Double steal proceeds!

            elif outcome == "partial":
                # Absorbs only 50% of the theft
                stolen_rate = random.uniform(0.20, 0.40)
                full_loot = max(4, int(target_berries * stolen_rate))
                half_loot = max(2, full_loot // 2)
                loot_each = half_loot // 2
                await _atomic_multi_account_update([
                    {"user_id": str(target.id), "berries_delta": -half_loot, "outcome": "stolen_partial_doubleshield"},
                    {"user_id": author_id, "berries_delta": loot_each, "sin_delta": 1, "outcome": "doublesteal_success"},
                    {"user_id": spouse_id, "berries_delta": loot_each, "sin_delta": 1, "outcome": "doublesteal_success"}
                ])
                await _safe_send_reply(
                    message,
                    f"⚠️ **YOUR HEAVENLY SHIELD HAS BEEN CORRUPTED BY YOUR SINS!** ⚠️\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"{target_name}'s Heavenly Shield cracked under dark karmic weight ({t_sin} ❤️‍🔥)!\n"
                    f"It only absorbed **50%** of the double robbery! <@{author_id}> and <@{spouse_id}> stole **{half_loot:,}** 🫐 total (**{loot_each:,}** 🫐 each)!\n"
                    f"- Both Gained | +01 ❤️🔥|\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                return

            elif outcome == "breaks_after":
                author_berries = stats.get("berries", 0)
                spouse_stats = await _get_user_stats(spouse_id)
                spouse_berries = spouse_stats.get("berries", 0)
                fine_1 = min(author_berries, max(40, int(author_berries * 0.25), int(target_berries * 0.12)))
                fine_2 = min(spouse_berries, max(40, int(spouse_berries * 0.25), int(target_berries * 0.12)))
                tot_fine = fine_1 + fine_2
                acc_updates = []
                if fine_1 > 0: acc_updates.append({"user_id": author_id, "berries_delta": -fine_1, "sin_delta": 1})
                if fine_2 > 0: acc_updates.append({"user_id": spouse_id, "berries_delta": -fine_2, "sin_delta": 1})
                if tot_fine > 0: acc_updates.append({"user_id": str(target.id), "berries_delta": tot_fine})
                if acc_updates: await _atomic_multi_account_update(acc_updates)
                await _safe_send_reply(
                    message,
                    f"⚠️ **YOUR HEAVENLY SHIELD HAS BEEN CORRUPTED BY YOUR SINS!** ⚠️\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"{target_name}'s Heavenly Shield deflected the double heist and shocked the thieves for **{tot_fine:,}** 🫐, but the corrupted divine metal **SHATTERED INTO BRITTLE SHARDS AFTER ACTIVATION**!\n"
                    f"- Both Gained | +01 ❤️🔥|\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                return

            elif outcome == "penalty":
                recoil_penalty = min(target_berries, max(50, int(target_berries * 0.05)))
                author_berries = stats.get("berries", 0)
                spouse_stats = await _get_user_stats(spouse_id)
                spouse_berries = spouse_stats.get("berries", 0)
                fine_1 = min(author_berries, max(40, int(author_berries * 0.25)))
                fine_2 = min(spouse_berries, max(40, int(spouse_berries * 0.25)))
                acc_updates = [
                    {"user_id": str(target.id), "berries_delta": -recoil_penalty, "outcome": "shield_recoil_penalty"},
                    {"user_id": author_id, "berries_delta": -fine_1, "sin_delta": 1},
                    {"user_id": spouse_id, "berries_delta": -fine_2, "sin_delta": 1}
                ]
                await _atomic_multi_account_update(acc_updates)
                await _safe_send_reply(
                    message,
                    f"⚠️ **YOUR HEAVENLY SHIELD HAS BEEN CORRUPTED BY YOUR SINS!** ⚠️\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"{target_name}'s Heavenly Shield repelled the double heist, but **INFLICTED A DIVINE PENALTY** on its sinful owner ({t_sin} ❤️‍🔥)!\n"
                    f"A surge of holy recoil burned **{recoil_penalty:,}** 🫐 from {target_name}'s pouch, while the thieves were shocked for **{fine_1+fine_2:,}** 🫐!\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                return

        else:
            # 100% normal block and twin shock
            author_berries = stats.get("berries", 0)
            spouse_stats = await _get_user_stats(spouse_id)
            spouse_berries = spouse_stats.get("berries", 0)
            fine_1 = min(author_berries, max(40, int(author_berries * 0.25), int(target_berries * 0.12)))
            fine_2 = min(spouse_berries, max(40, int(spouse_berries * 0.25), int(target_berries * 0.12)))
            tot_fine = fine_1 + fine_2
            sin_1 = 1 if fine_1 > 0 else 3
            sin_2 = 1 if fine_2 > 0 else 3

            acc_updates = []
            if fine_1 > 0: acc_updates.append({"user_id": author_id, "berries_delta": -fine_1, "sin_delta": sin_1})
            else: acc_updates.append({"user_id": author_id, "sin_delta": sin_1})

            if fine_2 > 0: acc_updates.append({"user_id": spouse_id, "berries_delta": -fine_2, "sin_delta": sin_2})
            else: acc_updates.append({"user_id": spouse_id, "sin_delta": sin_2})

            if tot_fine > 0: acc_updates.append({"user_id": str(target.id), "berries_delta": tot_fine})

            await _atomic_multi_account_update(acc_updates)

            await _safe_send_reply(
                message,
                f"🛡️ **HEAVENLY SHIELD TWIN DEFLECTION!** ⚡\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{target_name}'s **Heavenly Shield** sensed the dual ambush and radiated 100% uncorrupted holy light, detonating an arc of lightning across both <@{author_id}> and <@{spouse_id}>!\n"
                f"<@{author_id}> was zapped for **{fine_1:,}** 🫐 and <@{spouse_id}> for **{fine_2:,}** 🫐 (total **{tot_fine:,}** 🫐 paid to {target_name}), and the shield broke!\n"
                f"- Both Gained | +01 ❤️🔥|\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            return

    # 2. Victim Karmic Aura check
    target_virtue = target_stats.get("virtue", 0)
    if target_virtue > 0 and random.random() < min(0.40, target_virtue * 0.025):
        await _update_user_stats(author_id, sin_delta=1)
        await _update_user_stats(spouse_id, sin_delta=1)
        await _safe_send_reply(
            message,
            f"✨ **KARMIC AURA TWIN DEFLECTION!** ✨\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{target_name}'s immaculate Virtue ({target_virtue} 💖) casts a divine warmth over the alleyway!\n"
            f"<@{author_id}> and <@{spouse_id}> looked into each other's eyes, felt sudden moral repentance, and walked away in silence!\n"
            f"- Both Gained | +01 ❤️🔥|\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        return

    # Check Thief Buffs
    has_clover = stats.get("clover_active", False)
    if has_clover:
        async with _LOCK:
            _USER_STATS[author_id]["clover_active"] = False
            _save_data_sync(_USER_STATS)

    has_mask = stats.get("mask_active", False)
    if has_mask:
        async with _LOCK:
            _USER_STATS[author_id]["mask_active"] = False
            _save_data_sync(_USER_STATS)

    # Calculate success: Base 55% + sin bonus from both spouses + clover
    author_sin = stats.get("sin", 0)
    spouse_stats = await _get_user_stats(spouse_id)
    spouse_sin = spouse_stats.get("sin", 0)
    sin_luck = min(20, int((author_sin + spouse_sin) * 0.5))

    success_rate = 55 + sin_luck + (20 if has_clover else 0)
    roll = random.randint(1, 100)

    if roll <= success_rate:
        # Success! Steal scales with target balance: 25% to 45%
        loot_rate = random.uniform(0.25, 0.45)
        raw_stolen = max(15, int(target_berries * loot_rate))
        if has_mask:
            raw_stolen = int(raw_stolen * 1.30)
        stolen = min(raw_stolen, target_berries)

        # 15% vault cut
        vault_cut = max(1, int(stolen * 0.15))
        rem_loot = stolen - vault_cut
        half_1 = rem_loot // 2
        half_2 = rem_loot - half_1

        # Deposit vault cut into joint vault
        vault = _get_joint_vault(author_id, spouse_id)
        vault["balance"] += vault_cut
        vault["total_deposited"] = vault.get("total_deposited", 0) + vault_cut

        sin_gain = 0 if has_mask else 2
        updated = await _atomic_multi_account_update([
            {"user_id": author_id, "berries_delta": half_1, "sin_delta": sin_gain, "outcome": "steal_success"},
            {"user_id": spouse_id, "berries_delta": half_2, "sin_delta": sin_gain, "outcome": "steal_success"},
            {"user_id": str(target.id), "berries_delta": -stolen}
        ])
        victim_new_berries = updated[str(target.id)]["berries"]

        u1 = await check_and_award_achievements(author_id)
        u2 = await check_and_award_achievements(spouse_id)
        banner = format_achievement_banner(u1 + u2)

        scenario_kwargs = {
            "spouse": f"<@{spouse_id}>",
            "user": target_name,
            "u1": f"<@{author_id}>",
            "u2": f"<@{spouse_id}>",
            "victim": target_name,
            "author": f"<@{author_id}>"
        }
        scenario = random.choice(DOUBLE_STEAL_SUCCESS_SCENARIOS).format(**scenario_kwargs)
        mask_tag = " 🎭 *(Phantom Mask: 0 Sin & +30% Loot!)*" if has_mask else ""
        clover_tag = " 🍀 *(Lucky Clover Boost!)*" if has_clover else ""

        desc = (
            f"🦹‍♀️ **DOUBLE-STEAL HEIST SUCCESS!** 🦹‍♂️\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{scenario}\n\n"
            f"💰 **Total Stolen:** `{stolen:,}` 🫐 from {target_name}\n"
            f"🔻 **Victim Depleted:** `-{stolen:,}` 🫐 (Remaining: `{victim_new_berries:,}` 🫐)\n"
            f"🏛️ **Joint Vault Cut (15%):** `+{vault_cut:,}` 🫐\n"
            f"💎 <@{author_id}> Pouch: `+{half_1:,}` 🫐 | +{sin_gain} ❤️🔥\n"
            f"💎 <@{spouse_id}> Pouch: `+{half_2:,}` 🫐 | +{sin_gain} ❤️🔥{mask_tag}{clover_tag}{banner}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await _safe_send_reply(message, desc)
    else:
        # Caught! Fines scale with each spouse's balance & target balance
        author_fresh = await _get_user_stats(author_id)
        author_berries = author_fresh.get("berries", 0)
        spouse_stats_fresh = await _get_user_stats(spouse_id)
        spouse_berries = spouse_stats_fresh.get("berries", 0)

        fine_rate_1 = random.uniform(0.15, 0.30)
        fine_rate_2 = random.uniform(0.15, 0.30)
        target_scale = int(target_berries * random.uniform(0.08, 0.15))

        base_fine_1 = max(30, int(author_berries * fine_rate_1), target_scale)
        fine_1 = min(author_berries, base_fine_1)

        base_fine_2 = max(30, int(spouse_berries * fine_rate_2), target_scale)
        fine_2 = min(spouse_berries, base_fine_2)

        sin_gain_1 = 0 if has_mask else (3 if author_berries == 0 else 1)
        sin_gain_2 = 0 if has_mask else (3 if spouse_berries == 0 else 1)

        tot_fine = fine_1 + fine_2
        acc_updates = []
        if fine_1 > 0:
            acc_updates.append({"user_id": author_id, "berries_delta": -fine_1, "sin_delta": sin_gain_1})
        else:
            acc_updates.append({"user_id": author_id, "sin_delta": sin_gain_1})

        if fine_2 > 0:
            acc_updates.append({"user_id": spouse_id, "berries_delta": -fine_2, "sin_delta": sin_gain_2})
        else:
            acc_updates.append({"user_id": spouse_id, "sin_delta": sin_gain_2})

        if tot_fine > 0:
            acc_updates.append({"user_id": str(target.id), "berries_delta": tot_fine})

        await _atomic_multi_account_update(acc_updates)

        scenario_kwargs = {
            "spouse": f"<@{spouse_id}>",
            "user": target_name,
            "u1": f"<@{author_id}>",
            "u2": f"<@{spouse_id}>",
            "victim": target_name,
            "author": f"<@{author_id}>"
        }
        scenario = random.choice(DOUBLE_STEAL_CAUGHT_SCENARIOS).format(**scenario_kwargs)
        desc = (
            f"🚨 **DOUBLE-STEAL BUSTED!** 🚨\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{scenario}\n\n"
            f"💸 <@{author_id}> Fined: `-{fine_1:,}` 🫐 | +{sin_gain_1} ❤️🔥\n"
            f"💸 <@{spouse_id}> Fined: `-{fine_2:,}` 🫐 | +{sin_gain_2} ❤️🔥\n"
            f"🛡️ Restitution paid to {target_name}: `+{tot_fine:,}` 🫐\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await _safe_send_reply(message, desc)


async def handle_donate(message, client, args: list):
    """Handles y!donate <amount>."""
    author_id = str(message.author.id)
    amount = None
    for a in args:
        cleaned = a.replace(",", "")
        if cleaned.isdigit():
            amount = int(cleaned)
            break

    if amount is None or amount <= 0:
        await _safe_send_reply(
            message,
            "- *Yuna tilts her head* \"How many berries do you want to donate? Usage: `y!donate <amount>`\""
        )
        return

    author_stats = await _get_user_stats(author_id)
    author_berries = author_stats.get("berries", 0)

    if author_berries < amount:
        await _safe_send_reply(
            message,
            f"- *Yuna pouts* \"You only have **{author_berries}** 🫐! You can't donate **{amount}** 🫐 when you're broke!\""
        )
        return

    virtue_gain = 1
    if amount >= 300:
        virtue_gain = 4
    elif amount >= 150:
        virtue_gain = 3
    elif amount >= 50:
        virtue_gain = 2

    # Deduct berries & add virtue
    await _update_user_stats(author_id, berries_delta=-amount, virtue_delta=virtue_gain)

    # Track total donated for philanthropist achievement
    async with _LOCK:
        user = _USER_STATS.get(author_id)
        if user:
            user["total_donated"] = user.get("total_donated", 0) + amount
            _save_data_sync(_USER_STATS)

    candidates = []
    if message.guild:
        candidates = [m.id for m in message.guild.members if not m.bot and m.id != message.author.id]

    if not candidates:
        known_uids = [
            int(u) for u in _USER_STATS.keys()
            if u != author_id and u.isdigit() and (not client.user or u != str(client.user.id))
        ]
        candidates = known_uids

    if candidates:
        lucky_id = random.choice(candidates)
        await _update_user_stats(str(lucky_id), berries_delta=amount)
        gift_notice = f"🎁 *The berries fluttered from the heavens and landed right into <@{lucky_id}>'s pouch!*"
    else:
        gift_notice = "🎁 *The berries vanished into the divine ether to nourish wandering spirits!*"

    unlocked = await check_and_award_achievements(author_id)
    banner = format_achievement_banner(unlocked)

    response = (
        f"✨ **A Pure Act of Benevolence!** ✨\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{message.author.mention} selflessly gave away **{amount}** 🫐!\n\n"
        f"- Gained | +{virtue_gain:02d} 💖 |\n"
        f"- Gained | +00 ❤️🔥|\n\n"
        f"{gift_notice}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━{banner}"
    )
    await _safe_send_reply(message, response)
    await record_task_progress(author_id, "generosity")


async def handle_leaderboard(message, client, args: list):
    """Handles y!leaderboard."""
    global _USER_STATS
    async with _LOCK:
        _ensure_fresh_data()

    if not _USER_STATS:
        await _safe_send_reply(
            message,
            "🏆 **The leaderboard is empty!** Start interacting with `y!aid` or `y!steal` to claim your spot!"
        )
        return

    def get_user_label(uid_str: str) -> str:
        if uid_str == YUNA_USER_ID:
            return "**👑 Empress Yuna (Treasury)**"
        if uid_str.isdigit():
            uid = int(uid_str)
            if message.guild:
                member = message.guild.get_member(uid)
                if member:
                    return f"**{getattr(member, 'display_name', member.name)}**"
            return f"<@{uid}>"
        return f"**{uid_str}**"

    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]

    berry_sorted = sorted(
        [u for u in _USER_STATS.items() if u[1].get("berries", 0) > 0],
        key=lambda x: x[1].get("berries", 0),
        reverse=True
    )[:5]

    virtue_sorted = sorted(
        [u for u in _USER_STATS.items() if u[1].get("virtue", 0) > 0],
        key=lambda x: x[1].get("virtue", 0),
        reverse=True
    )[:5]

    sin_sorted = sorted(
        [u for u in _USER_STATS.items() if u[1].get("sin", 0) > 0],
        key=lambda x: x[1].get("sin", 0),
        reverse=True
    )[:5]

    streak_sorted = sorted(
        [u for u in _USER_STATS.items() if u[1].get("max_win_streak", 0) > 0],
        key=lambda x: x[1].get("max_win_streak", 0),
        reverse=True
    )[:5]

    if args and args[0].lower() in ("streak", "streaks", "win", "winstreak"):
        s_lines = [
            "🏆 **Casino Win Streak Hall of Fame** 🏆",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ]
        if streak_sorted:
            for idx, (uid, stats) in enumerate(streak_sorted):
                medal = medals[idx] if idx < len(medals) else f"`#{idx+1}`"
                label = get_user_label(uid)
                cur_s = stats.get('gamble_win_streak', 0)
                max_s = stats.get('max_win_streak', 0)
                s_lines.append(f"{medal} {label} — Peak Record: `{max_s}` wins *(Current: `{cur_s}`)*")
        else:
            s_lines.append("*No mortal has achieved a win streak yet.*")
        s_lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        await _safe_send_reply(message, "\n".join(s_lines))
        return

    lines = [
        "🏆 **Yuna's Realm Leaderboard** 🏆",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    ]

    lines.append("🫐 **Richest Berry Hoarders:**")
    if berry_sorted:
        for idx, (uid, stats) in enumerate(berry_sorted):
            medal = medals[idx] if idx < len(medals) else f"`#{idx+1}`"
            label = get_user_label(uid)
            lines.append(f"{medal} {label} — `{stats.get('berries', 0)}` 🫐")
    else:
        lines.append("*No mortals have hoarded any berries yet.*")

    lines.append("")
    lines.append("💖 **Highest Virtue (Angelic Souls):**")
    if virtue_sorted:
        for idx, (uid, stats) in enumerate(virtue_sorted):
            medal = medals[idx] if idx < len(medals) else f"`#{idx+1}`"
            label = get_user_label(uid)
            lines.append(f"{medal} {label} — `{stats.get('virtue', 0)}` 💖")
    else:
        lines.append("*No saintly acts recorded yet.*")

    lines.append("")
    lines.append("❤️🔥 **Highest Sin (Notorious Villains):**")
    if sin_sorted:
        for idx, (uid, stats) in enumerate(sin_sorted):
            medal = medals[idx] if idx < len(medals) else f"`#{idx+1}`"
            label = get_user_label(uid)
            lines.append(f"{medal} {label} — `{stats.get('sin', 0)}` ❤️🔥")
    else:
        lines.append("*No depraved sinners found yet.*")

    lines.append("")
    lines.append("🔥 **Top Win Streakers (Casino Legends):**")
    if streak_sorted:
        for idx, (uid, stats) in enumerate(streak_sorted):
            medal = medals[idx] if idx < len(medals) else f"`#{idx+1}`"
            label = get_user_label(uid)
            cur_s = stats.get('gamble_win_streak', 0)
            max_s = stats.get('max_win_streak', 0)
            lines.append(f"{medal} {label} — Peak: `{max_s}` wins *(Current: `{cur_s}`)*")
    else:
        lines.append("*No high streaks forged in fire yet.*")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    await _safe_send_reply(message, "\n".join(lines))

# ─── GAMES: BLACKJACK AGAINST YUNA ──────────────────────────────────────────

async def _check_blackjack_comedy_cards(user_id: str, cards: List[Tuple[str, int, str, str]]):
    """Awards comedy card achievements if Uno Reverse, Blue-Eyes, or Bitten 7 are drawn."""
    for c in cards:
        c_name = c[0]
        if c_name == "Uno Reverse":
            await check_and_award_achievements(user_id, specific_id="uno_reverse_card")
        elif c_name == "Blue-Eyes":
            await check_and_award_achievements(user_id, specific_id="blue_eyes_white_dragon")
        elif c_name == "Bitten 7":
            await check_and_award_achievements(user_id, specific_id="bitten_strawberry")

async def handle_blackjack(message, client, args: list):
    """Handles y!blackjack <amount> (or y!bj)."""
    author_id = str(message.author.id)

    if author_id in _ACTIVE_BLACKJACK_GAMES:
        await _safe_send_reply(
            message,
            "⚠️ You already have an active Blackjack game! Use `y!hit`, `y!stand`, or click the buttons below your table!"
        )
        return

    amount = 10
    if args:
        cleaned = args[0].replace(",", "")
        if cleaned.isdigit():
            amount = int(cleaned)

    if amount <= 0:
        await _safe_send_reply(message, "- *Yuna crosses her arms* \"Wager must be at least 1 🫐!\"")
        return

    author_stats = await _get_user_stats(author_id)
    if author_stats.get("berries", 0) < amount:
        await _safe_send_reply(
            message,
            f"- *Yuna scoffs* \"You only have **{author_stats.get('berries', 0)}** 🫐! You can't afford a **{amount}** 🫐 blackjack hand!\""
        )
        return

    # Deduct bet upfront & register gamble
    await _update_user_stats(author_id, berries_delta=-amount, is_gamble=True)

    # Karmic Absurd Death Check (if user has Sin)
    _, eff_s = get_effective_morality(author_stats)
    if eff_s > 0:
        death_chance = min(0.15, 0.02 + eff_s * 0.004)
        if random.random() < death_chance:
            death_event = random.choice(ABSURD_SIN_DEATHS)
            async with _LOCK:
                _USER_STATS[author_id]["karmic_deaths"] = _USER_STATS[author_id].get("karmic_deaths", 0) + 1
                if "shark" in death_event.lower():
                    _USER_STATS[author_id]["shark_deaths"] = _USER_STATS[author_id].get("shark_deaths", 0) + 1
                _save_data_sync(_USER_STATS)
            unlocked = await check_and_award_achievements(author_id)
            banner = format_achievement_banner(unlocked)
            desc = (
                f"💀 **ABSURD KARMIC CATASTROPHE!** 💀\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{death_event}\n\n"
                f"🔥 *Your heavy Sin ({eff_s}/30 ❤️‍🔥) triggered a horrific stroke of karmic disaster!*\n"
                f"Your blackjack hand was obliterated and your wager was forfeited: **-{amount:,}** 🫐\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━{banner}"
            )
            await _safe_send_reply(message, desc)
            return

    # Initial deal
    p_cards = [draw_card(), draw_card()]
    d_cards = [draw_card(), draw_card()]

    # Check for comedy card achievements
    await _check_blackjack_comedy_cards(author_id, p_cards)

    p_score = calculate_hand(p_cards)
    d_score = calculate_hand(d_cards)

    game_state = {
        "author_id": author_id,
        "author_mention": message.author.mention,
        "bet": amount,
        "player_cards": p_cards,
        "dealer_cards": d_cards,
        "channel_id": message.channel.id,
        "message": None,
        "finished": False
    }
    _ACTIVE_BLACKJACK_GAMES[author_id] = game_state

    # Natural 21 check
    if p_score == 21:
        game_state["finished"] = True
        _ACTIVE_BLACKJACK_GAMES.pop(author_id, None)
        if d_score == 21:
            # Push
            await _update_user_stats(author_id, berries_delta=amount)
            unlocked = await check_and_award_achievements(author_id)
            banner = format_achievement_banner(unlocked)
            desc = (
                f"🃏 **BLACKJACK — PUSH!** 🃏\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Your Hand: {' '.join(c[3] for c in p_cards)} `(Total: 21)`\n"
                f"Yuna's Hand: {' '.join(c[3] for c in d_cards)} `(Total: 21)`\n\n"
                f"Both you and Yuna got natural Blackjacks! Bet refunded: **+{amount}** 🫐.{banner}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            await _safe_send_reply(message, desc)
            return
        else:
            # Natural Blackjack pays 3:2 (rounded)
            profit = int(amount * 1.5)
            await record_gamble_win(author_id)
            bonus, bonus_txt = await get_gamble_win_bonuses(author_id, profit)
            winnings = amount + profit + bonus
            await _update_user_stats(author_id, berries_delta=winnings)
            unlocked = await check_and_award_achievements(author_id)
            banner = format_achievement_banner(unlocked)
            desc = (
                f"🃏 **NATURAL BLACKJACK!** 🃏\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Your Hand: {' '.join(c[3] for c in p_cards)} `(Total: 21)`\n"
                f"Yuna's Hand: {' '.join(c[3] for c in d_cards)} `(Total: {d_score})`\n\n"
                f"✨ Unbelievable luck! You won **+{winnings}** 🫐!{bonus_txt}{banner}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            await _safe_send_reply(message, desc)
            await record_task_progress(author_id, "gamble")
            return

    # Normal game in progress
    view = BlackjackView(author_id, game_state)
    desc = (
        f"🃏 **Yuna's Blackjack Table** 🃏\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Player: {message.author.mention} | Wager: **{amount}** 🫐\n\n"
        f"Your Hand: {' '.join(c[3] for c in p_cards)} `(Total: {p_score})`\n"
        f"Yuna's Hand: {d_cards[0][3]} `[🂠]`\n\n"
        f"*(Click **Hit** / **Stand** below, or type `y!hit` / `y!stand`)*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    sent_msg = await _safe_send_reply(message, desc, view=view)
    game_state["message"] = sent_msg


async def process_blackjack_turn(game_state: dict, action: str, interaction: Optional[discord.Interaction] = None, view: Optional[View] = None):
    author_id = game_state["author_id"]
    if game_state.get("finished"):
        return

    game_state["last_active"] = time.time()
    refresh_view_timeout(view, 300.0)

    # Karmic Absurd Death Check mid-game
    stats = await _get_user_stats(author_id)
    _, eff_s = get_effective_morality(stats)
    if eff_s > 0:
        death_chance = min(0.12, 0.02 + eff_s * 0.003)
        if random.random() < death_chance:
            game_state["finished"] = True
            _ACTIVE_BLACKJACK_GAMES.pop(author_id, None)
            await record_gamble_loss(author_id)
            death_event = random.choice(ABSURD_SIN_DEATHS)
            bet = game_state["bet"]
            async with _LOCK:
                _USER_STATS[author_id]["karmic_deaths"] = _USER_STATS[author_id].get("karmic_deaths", 0) + 1
                if "shark" in death_event.lower():
                    _USER_STATS[author_id]["shark_deaths"] = _USER_STATS[author_id].get("shark_deaths", 0) + 1
                _save_data_sync(_USER_STATS)
            unlocked = await check_and_award_achievements(author_id)
            banner = format_achievement_banner(unlocked)
            text = (
                f"💀 **ABSURD KARMIC CATASTROPHE!** 💀\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{death_event}\n\n"
                f"🔥 *Your heavy Sin ({eff_s}/30 ❤️‍🔥) triggered a horrific stroke of karmic disaster mid-game!*\n"
                f"Your game was destroyed and your wager was forfeited: **-{bet:,}** 🫐\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━{banner}"
            )
            if view:
                for item in view.children:
                    item.disabled = True
            if interaction:
                await interaction.edit_original_response(content=text, view=view)
            elif game_state.get("message"):
                await game_state["message"].edit(content=text, view=view)
            await record_task_progress(author_id, "gamble")
            return

    p_cards = game_state["player_cards"]
    d_cards = game_state["dealer_cards"]
    bet = game_state["bet"]

    if action == "hit":
        new_card = draw_card()
        p_cards.append(new_card)
        await _check_blackjack_comedy_cards(author_id, [new_card])
        p_score = calculate_hand(p_cards)

        if p_score > 21:
            # BUST!
            game_state["finished"] = True
            _ACTIVE_BLACKJACK_GAMES.pop(author_id, None)
            await record_gamble_loss(author_id)

            unlocked = await check_and_award_achievements(author_id)
            banner = format_achievement_banner(unlocked)

            text = (
                f"💥 **BUST! You went over 21!** 💥\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Your Hand: {' '.join(c[3] for c in p_cards)} `(Total: {p_score})`\n"
                f"Yuna's Hand: {' '.join(c[3] for c in d_cards)} `(Total: {calculate_hand(d_cards)})`\n\n"
                f"*Yuna giggles WUWAHAHAHAHAH~* \"Greedy mortal! You lost **{bet}** 🫐!\"{banner}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            if view:
                for item in view.children:
                    item.disabled = True
            if interaction:
                await interaction.edit_original_response(content=text, view=view)
            elif game_state.get("message"):
                await game_state["message"].edit(content=text, view=view)
            await record_task_progress(author_id, "gamble")
            return
        else:
            # Continue
            desc = (
                f"🃏 **Yuna's Blackjack Table** 🃏\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Player: {game_state['author_mention']} | Wager: **{bet}** 🫐\n\n"
                f"Your Hand: {' '.join(c[3] for c in p_cards)} `(Total: {p_score})`\n"
                f"Yuna's Hand: {d_cards[0][3]} `[🂠]`\n\n"
                f"*(Click **Hit** / **Stand** below, or type `y!hit` / `y!stand`)*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            if interaction:
                await interaction.edit_original_response(content=desc, view=view)
            elif game_state.get("message"):
                await game_state["message"].edit(content=desc, view=view)
            return

    elif action == "stand":
        game_state["finished"] = True
        _ACTIVE_BLACKJACK_GAMES.pop(author_id, None)

        p_score = calculate_hand(p_cards)
        d_score = calculate_hand(d_cards)

        # Dealer draws until >= 17
        while d_score < 17:
            d_cards.append(draw_card())
            d_score = calculate_hand(d_cards)

        if view:
            for item in view.children:
                item.disabled = True

        if d_score > 21:
            # Dealer bust -> Player wins
            profit = bet
            await record_gamble_win(author_id)
            bonus, bonus_txt = await get_gamble_win_bonuses(author_id, profit)
            winnings = bet * 2 + bonus
            await _update_user_stats(author_id, berries_delta=winnings)
            unlocked = await check_and_award_achievements(author_id)
            banner = format_achievement_banner(unlocked)

            text = (
                f"🎉 **YUNA BUSTED! YOU WIN!** 🎉\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Your Hand: {' '.join(c[3] for c in p_cards)} `(Total: {p_score})`\n"
                f"Yuna's Hand: {' '.join(c[3] for c in d_cards)} `(Total: {d_score})`\n\n"
                f"*Yuna pouts* \"Hmph! Pure beginner's luck! Take your **+{winnings}** 🫐!\"{bonus_txt}{banner}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
        elif p_score > d_score:
            # Player higher score -> Player wins
            profit = bet
            await record_gamble_win(author_id)
            bonus, bonus_txt = await get_gamble_win_bonuses(author_id, profit)
            winnings = bet * 2 + bonus
            await _update_user_stats(author_id, berries_delta=winnings)
            unlocked = await check_and_award_achievements(author_id)
            banner = format_achievement_banner(unlocked)

            text = (
                f"🎉 **YOU WON THE HAND!** 🎉\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Your Hand: {' '.join(c[3] for c in p_cards)} `(Total: {p_score})`\n"
                f"Yuna's Hand: {' '.join(c[3] for c in d_cards)} `(Total: {d_score})`\n\n"
                f"🏆 Excellent play! You won **+{winnings}** 🫐!{bonus_txt}{banner}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
        elif p_score == d_score:
            # Push -> Refund
            await _update_user_stats(author_id, berries_delta=bet)
            unlocked = await check_and_award_achievements(author_id)
            banner = format_achievement_banner(unlocked)
            text = (
                f"⚖️ **STANDOFF — PUSH!** ⚖️\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Your Hand: {' '.join(c[3] for c in p_cards)} `(Total: {p_score})`\n"
                f"Yuna's Hand: {' '.join(c[3] for c in d_cards)} `(Total: {d_score})`\n\n"
                f"A tie score! Bet refunded: **+{bet}** 🫐.{banner}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
        else:
            # Dealer wins
            await record_gamble_loss(author_id)
            unlocked = await check_and_award_achievements(author_id)
            banner = format_achievement_banner(unlocked)

            text = (
                f"🥀 **YUNA WINS!** 🥀\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Your Hand: {' '.join(c[3] for c in p_cards)} `(Total: {p_score})`\n"
                f"Yuna's Hand: {' '.join(c[3] for c in d_cards)} `(Total: {d_score})`\n\n"
                f"*Yuna winks and smirks* \"Did you really think you could beat an angel? Thanks for the **{bet}** 🫐!\"{banner}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )

        if interaction:
            await interaction.edit_original_response(content=text, view=view)
        elif game_state.get("message"):
            await game_state["message"].edit(content=text, view=view)

        await record_task_progress(author_id, "gamble")


async def handle_hit(message, client, args: list):
    """Handles text command y!hit."""
    author_id = str(message.author.id)
    if author_id not in _ACTIVE_BLACKJACK_GAMES:
        await _safe_send_reply(message, "You don't have an active Blackjack game! Start one with `y!blackjack <amount>`!")
        return
    await process_blackjack_turn(_ACTIVE_BLACKJACK_GAMES[author_id], action="hit")


async def handle_stand(message, client, args: list):
    """Handles text command y!stand."""
    author_id = str(message.author.id)
    if author_id not in _ACTIVE_BLACKJACK_GAMES:
        await _safe_send_reply(message, "You don't have an active Blackjack game! Start one with `y!blackjack <amount>`!")
        return
    await process_blackjack_turn(_ACTIVE_BLACKJACK_GAMES[author_id], action="stand")

# ─── GAMES: 📈 YUNA'S CRASH GAME ───────────────────────────────────────────

async def handle_crash(message, client, args: list):
    """Handles y!crash <amount>."""
    author_id = str(message.author.id)

    if author_id in _ACTIVE_CRASH_GAMES:
        await _safe_send_reply(
            message,
            "📈 You already have an active rocket flying! Use `y!cashout` or click **💰 Cash Out** before it crashes!"
        )
        return

    amount = 10
    if args:
        cleaned = args[0].replace(",", "")
        if cleaned.isdigit():
            amount = int(cleaned)

    if amount <= 0:
        await _safe_send_reply(message, "- *Yuna frowns* \"Wager must be at least 1 🫐!\"")
        return

    author_stats = await _get_user_stats(author_id)
    if author_stats.get("berries", 0) < amount:
        await _safe_send_reply(
            message,
            f"- *Yuna laughs* \"You only have **{author_stats.get('berries', 0)}** 🫐! You can't wager **{amount}** 🫐!\""
        )
        return

    # Deduct bet immediately & register gamble
    await _update_user_stats(author_id, berries_delta=-amount, is_gamble=True)

    # Crash point calculation: 5% instant crash at 1.00x, else exponential distribution
    r = random.random()
    if r < 0.05:
        crash_point = 1.00
    else:
        crash_point = round(max(1.05, 0.95 / (1.0 - r)), 2)
        crash_point = min(crash_point, 40.0) # Cap at 40x

    game_state = {
        "author_id": author_id,
        "author_mention": message.author.mention,
        "bet": amount,
        "crash_point": crash_point,
        "multiplier": 1.00,
        "cashed_out": False,
        "finished": False,
        "message": None
    }
    _ACTIVE_CRASH_GAMES[author_id] = game_state

    view = CrashView(author_id, game_state)
    init_text = (
        f"📈 **Yuna's Crash Game** 📈\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Player: {message.author.mention} | Wager: **{amount}** 🫐\n"
        f"Current Multiplier: **1.00x**\n\n"
        f"*(Click **💰 Cash Out** below or type `y!cashout` to lock in profits!)*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    sent_msg = await _safe_send_reply(message, init_text, view=view)
    game_state["message"] = sent_msg

    # Background ticking task
    asyncio.create_task(_run_crash_ticker(game_state, view))


async def _run_crash_ticker(game_state: dict, view: CrashView):
    author_id = game_state["author_id"]
    bet = game_state["bet"]
    crash_point = game_state["crash_point"]
    msg = game_state["message"]

    # Pre-calculated multiplier increments
    steps = [1.15, 1.35, 1.62, 1.98, 2.45, 3.10, 3.95, 5.05, 6.45, 8.20, 10.50, 13.50, 17.50, 22.80, 30.00, 40.00]

    for step in steps:
        await asyncio.sleep(1.6)

        if game_state.get("cashed_out") or game_state.get("finished"):
            return

        if step >= crash_point:
            # CRASH!
            game_state["finished"] = True
            _ACTIVE_CRASH_GAMES.pop(author_id, None)

            for item in view.children:
                item.disabled = True

            if crash_point <= 1.20:
                await check_and_award_achievements(author_id, specific_id="space_debris")

            unlocked = await check_and_award_achievements(author_id)
            banner = format_achievement_banner(unlocked)

            await record_gamble_loss(author_id)
            crash_reason = random.choice(COMEDY_CRASH_REASONS) if random.random() < 0.40 else "Held on too long!"
            crash_text = (
                f"💥 **CRASHED — {crash_point:.2f}x** 💥\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🚀 *{crash_reason}*\n"
                f"{game_state['author_mention']} lost **{bet}** 🫐.{banner}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            try:
                await msg.edit(content=crash_text, view=view)
            except Exception:
                pass
            await record_task_progress(author_id, "gamble")
            return
        else:
            game_state["multiplier"] = step
            cur_profit = int(bet * step) - bet
            update_text = (
                f"📈 **Yuna's Crash Game** 📈\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Player: {game_state['author_mention']} | Wager: **{bet}** 🫐\n"
                f"Current Multiplier: **{step:.2f}x** *(Potential Profit: +{cur_profit} 🫐)*\n\n"
                f"*(Click **💰 Cash Out** below or type `y!cashout`!)*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            try:
                await msg.edit(content=update_text, view=view)
            except Exception:
                pass


async def process_crash_cashout(game_state: dict, interaction: Optional[discord.Interaction] = None, view: Optional[View] = None):
    author_id = game_state["author_id"]
    if game_state.get("cashed_out") or game_state.get("finished"):
        return

    game_state["cashed_out"] = True
    game_state["finished"] = True
    _ACTIVE_CRASH_GAMES.pop(author_id, None)

    mult = game_state["multiplier"]
    bet = game_state["bet"]
    winnings = int(bet * mult)
    profit = winnings - bet

    await record_gamble_win(author_id)
    bonus, bonus_txt = await get_gamble_win_bonuses(author_id, profit, game="crash")
    winnings += bonus
    profit += bonus

    await _update_user_stats(author_id, berries_delta=winnings)

    # Check for "Yuna's Favorite" achievement (5.00x+) and "To The Moon!" (10.00x+)
    if mult >= 5.0:
        await check_and_award_achievements(author_id, specific_id="yunas_favorite")
    if mult >= 10.0:
        await check_and_award_achievements(author_id, specific_id="moon_walker")

    unlocked = await check_and_award_achievements(author_id)
    banner = format_achievement_banner(unlocked)

    if view:
        for item in view.children:
            item.disabled = True

    win_text = (
        f"💰 **CASHED OUT AT {mult:.2f}x!** 💰\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{game_state['author_mention']} locked in their profits!\n"
        f"🎉 **Total Won:** `+{winnings}` 🫐 *(Net Profit: +{profit} 🫐)*{bonus_txt}{banner}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    if interaction:
        await interaction.edit_original_response(content=win_text, view=view)
    elif game_state.get("message"):
        await game_state["message"].edit(content=win_text, view=view)

    await record_task_progress(author_id, "gamble")


async def handle_cashout(message, client, args: list):
    """Handles text command y!cashout."""
    author_id = str(message.author.id)
    if author_id not in _ACTIVE_CRASH_GAMES:
        await _safe_send_reply(message, "You don't have an active Crash game running! Start one with `y!crash <amount>`!")
        return
    await process_crash_cashout(_ACTIVE_CRASH_GAMES[author_id])

# ─── SOCIAL GAMBLING: BET, FIGHT, DARE, TRADE, GIFT ─────────────────────────

async def handle_bet(message, client, args: list):
    """Handles y!bet @user <amount> (Coin flip challenge)."""
    await _initiate_wager_challenge(message, client, args, challenge_type="bet")

async def handle_fight(message, client, args: list):
    """Handles y!fight @user <amount> (Absurd fight simulation wager)."""
    await _initiate_wager_challenge(message, client, args, challenge_type="fight")

async def handle_dare(message, client, args: list):
    """Handles y!dare @user <amount> [custom dare] (Dare challenge with reward pot)."""
    await _initiate_wager_challenge(message, client, args, challenge_type="dare")

async def handle_truth(message, client, args: list):
    """Handles y!truth @user <amount> [custom truth] (Truth challenge with reward pot)."""
    await _initiate_wager_challenge(message, client, args, challenge_type="truth")

async def handle_trade(message, client, args: list):
    """Handles y!trade @user <amount>."""
    await _initiate_wager_challenge(message, client, args, challenge_type="trade")

async def handle_gift(message, client, args: list):
    """Handles y!gift @user <amount> (Sweet gift alias)."""
    await handle_give(message, client, args)

async def _initiate_wager_challenge(message, client, args: list, challenge_type: str):
    author_id = str(message.author.id)
    amount = 50
    custom_text = None

    target = None
    if message.mentions:
        for m in message.mentions:
            if m.id != message.author.id and (not client.user or m.id != client.user.id):
                target = m
                break

    cleaned_tokens = []
    amount_found = False

    for a in args:
        cleaned = a.replace(",", "")
        if not amount_found and cleaned.isdigit():
            amount = int(cleaned)
            amount_found = True
            continue

        if not target:
            uid_match = re.search(r'\d{17,20}', a)
            if uid_match and message.guild:
                found_m = message.guild.get_member(int(uid_match.group()))
                if found_m:
                    target = found_m
                    continue
            elif message.guild:
                clean_name = a.lstrip("@").lower()
                found_m = discord.utils.find(
                    lambda m: m.name.lower() == clean_name or m.display_name.lower() == clean_name,
                    message.guild.members
                )
                if found_m:
                    target = found_m
                    continue
        else:
            if f"<@{target.id}>" in a or f"<@!{target.id}>" in a or str(target.id) in a:
                continue

        cleaned_tokens.append(a)

    if cleaned_tokens and challenge_type in ("dare", "truth"):
        custom_text = " ".join(cleaned_tokens).strip()
        if len(custom_text) > 300:
            custom_text = custom_text[:300]

    if not target:
        await _safe_send_reply(message, f"- *Yuna blinks* \"Who are you challenging? Usage: `y!{challenge_type} @user <amount>`\"")
        return

    if target.id == message.author.id:
        await _safe_send_reply(message, f"- *Yuna sighs* \"You can't challenge yourself to a {challenge_type}, narcissist!\"")
        return

    if getattr(target, "bot", False):
        await _safe_send_reply(message, "- *Yuna rolls her eyes* \"Bots don't participate in mortal wagers!\"")
        return

    author_stats = await _get_user_stats(author_id)
    target_stats = await _get_user_stats(str(target.id))

    if challenge_type == "fight" and author_stats.get("spouse") == str(target.id):
        await _safe_send_reply(
            message,
            "💔 *Yuna leaps between you both!* \"Domestic disputes belong in couples therapy, not the brawl arena! You cannot fight your beloved spouse! Try kissing instead.\""
        )
        return

    if author_stats.get("berries", 0) < amount:
        await _safe_send_reply(message, f"- *Yuna laughs* \"You only have **{author_stats.get('berries', 0)}** 🫐! You can't afford a **{amount}** 🫐 wager!\"")
        return

    if target_stats.get("berries", 0) < amount:
        await _safe_send_reply(message, f"- *Yuna shakes her head* \"<@{target.id}> is too broke to match your **{amount}** 🫐 wager!\"")
        return

    c_id = f"{challenge_type}_{target.id}"
    challenge_data = {
        "author_id": author_id,
        "author_mention": message.author.mention,
        "target_id": str(target.id),
        "target_mention": f"<@{target.id}>",
        "amount": amount,
        "challenge_type": challenge_type,
        "custom_text": custom_text,
        "message": None
    }
    _PENDING_CHALLENGES[c_id] = challenge_data

    view = ChallengeView(str(target.id), author_id, challenge_type, challenge_data)

    titles = {
        "bet": "🎲 Coin Flip Wager Challenge!",
        "fight": "⚔️ An Epic Deathmatch Challenge!",
        "dare": "🎭 High-Stakes Dare Challenge!",
        "truth": "🔮 High-Stakes Truth Challenge!",
        "trade": "📦 Trade Escrow Offer!"
    }
    title = titles.get(challenge_type, "👥 Wager Challenge!")

    custom_block = ""
    if custom_text:
        custom_block = f"Challenger's Custom Prompt:\n> 📢 **\"{custom_text}\"**\n\n"

    text = (
        f"**{title}**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{message.author.mention} has challenged <@{target.id}> to a **{challenge_type.upper()}** for **{amount}** 🫐!\n"
        f"*(Total Pot: **{amount * 2}** 🫐)*\n\n"
        f"{custom_block}"
        f"<@{target.id}>, do you accept? *(Click below or type `y!accept` / `y!decline`)*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    sent_msg = await _safe_send_reply(message, text, view=view)
    challenge_data["message"] = sent_msg


async def execute_challenge_resolution(data: dict, accepted: bool, interaction: Optional[discord.Interaction] = None, view: Optional[View] = None):
    c_type = data["challenge_type"]
    c_id = f"{c_type}_{data['target_id']}"
    _PENDING_CHALLENGES.pop(c_id, None)

    author_id = data["author_id"]
    target_id = data["target_id"]
    amount = data["amount"]

    if view:
        for item in view.children:
            item.disabled = True

    if not accepted:
        decline_text = (
            f"❌ **Challenge Declined!**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{data['target_mention']} backed down from {data['author_mention']}'s **{amount}** 🫐 challenge.\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        if interaction:
            await interaction.edit_original_response(content=decline_text, view=view)
        elif data.get("message"):
            await data["message"].edit(content=decline_text, view=view)
        return

    # Verify both still have funds
    s1 = await _get_user_stats(author_id)
    s2 = await _get_user_stats(target_id)
    if s1.get("berries", 0) < amount or s2.get("berries", 0) < amount:
        err = "⚠️ Challenge cancelled: One of the players no longer has enough berries!"
        if interaction:
            await interaction.edit_original_response(content=err, view=view)
        elif data.get("message"):
            await data["message"].edit(content=err, view=view)
        return

    # Execute wager based on type
    if c_type == "bet":
        coin = random.choice(["🪙 HEADS", "🪙 TAILS"])
        winner_id, loser_id = random.choice([(author_id, target_id), (target_id, author_id)])

        bonus, bonus_txt = await get_gamble_win_bonuses(winner_id, amount)
        win_delta = amount + bonus
        await _update_user_stats(winner_id, berries_delta=win_delta, is_gamble=True)
        await _update_user_stats(loser_id, berries_delta=-amount, is_gamble=True)

        unlocked = await check_and_award_achievements(winner_id)
        banner = format_achievement_banner(unlocked)

        res_text = (
            f"🎲 **COIN FLIP RESULTS** 🎲\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"The golden coin flew into the air and landed on **{coin}**!\n\n"
            f"🎉 **Winner:** <@{winner_id}> took the entire pot of **+{amount * 2 + bonus}** 🫐!{bonus_txt}\n"
            f"💀 **Loser:** <@{loser_id}> lost **{amount}** 🫐.{banner}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await record_task_progress(winner_id, "gamble")
        await record_task_progress(loser_id, "gamble")

    elif c_type == "fight":
        winner_id, loser_id = random.choice([(author_id, target_id), (target_id, author_id)])
        bonus, bonus_txt = await get_gamble_win_bonuses(winner_id, amount)
        win_delta = amount + bonus
        await _update_user_stats(winner_id, berries_delta=win_delta, is_gamble=True)
        await _update_user_stats(loser_id, berries_delta=-amount, is_gamble=True)

        async with _LOCK:
            if winner_id in _USER_STATS:
                _USER_STATS[winner_id]["fights_won"] = _USER_STATS[winner_id].get("fights_won", 0) + 1
                _save_data_sync(_USER_STATS)

        scenario = random.choice(FIGHT_SCENARIOS).format(
            u1=data["author_mention"],
            u2=data["target_mention"],
            winner=f"<@{winner_id}>",
            loser=f"<@{loser_id}>"
        )
        unlocked = await check_and_award_achievements(winner_id)
        banner = format_achievement_banner(unlocked)

        res_text = (
            f"⚔️ **THE ARENA SHOWDOWN** ⚔️\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{scenario}\n\n"
            f"🏆 **Victor:** <@{winner_id}> won the entire pot of **+{amount * 2 + bonus}** 🫐!{bonus_txt}{banner}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await record_task_progress(winner_id, "gamble")
        await record_task_progress(loser_id, "gamble")

    elif c_type in ("dare", "truth"):
        custom_text = data.get("custom_text")
        if custom_text:
            prompt_text = custom_text
            is_custom = True
        elif c_type == "truth":
            prompt_text = random.choice(TRUTHS)
            is_custom = False
        else:
            prompt_text = random.choice(DARES)
            is_custom = False

        # Deduct wager from both players into escrow
        await _update_user_stats(author_id, berries_delta=-amount, is_gamble=True)
        await _update_user_stats(target_id, berries_delta=-amount, is_gamble=True)

        # Store in _ACTIVE_DARES
        _ACTIVE_DARES[target_id] = {
            "challenger_id": author_id,
            "challenger_mention": data["author_mention"],
            "target_id": target_id,
            "target_mention": data["target_mention"],
            "amount": amount,
            "type": c_type,
            "dare": prompt_text,
            "prompt": prompt_text,
            "is_custom": is_custom,
            "rerolls_left": 0 if is_custom else 1,
            "created_at": time.time(),
            "channel_id": getattr(data.get("message"), "channel", None).id if data.get("message") else None
        }
        _save_data_sync()

        mode_name = "TRUTH" if c_type == "truth" else "DARE"
        icon = "🔮" if c_type == "truth" else "🎭"
        cmd_name = "checktruth" if c_type == "truth" else "checkdare"
        custom_badge = " *(Custom Prompt!)*" if is_custom else ""

        res_text = (
            f"{icon} **THE {mode_name} HAS BEEN UNLEASHED!** {icon}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{data['target_mention']}, your assigned {mode_name.lower()}{custom_badge} is:\n\n"
            f"> 📢 **\"{prompt_text}\"**\n\n"
            f"✨ Complete this and submit your proof using:\n"
            f"`y!{cmd_name} <what you said / proof>`\n"
            f"*(Or just post your proof/message right here and type `y!{cmd_name}`!)*\n\n"
            f"Total Pot on the line: **{amount * 2}** 🫐.\n"
            f"{data['author_mention']} can approve/reject proof or consult Yuna AI.\n"
            f"*(If you chicken out, type `y!forfeitdare`)*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

    elif c_type == "trade":
        await _update_user_stats(author_id, berries_delta=-amount)
        await _update_user_stats(target_id, berries_delta=amount)
        res_text = (
            f"📦 **Trade Completed!**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{data['author_mention']} transferred **{amount}** 🫐 to {data['target_mention']} via trade!\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

    if interaction:
        await interaction.edit_original_response(content=res_text, view=view)
    elif data.get("message"):
        await data["message"].edit(content=res_text, view=view)


async def handle_accept(message, client, args: list):
    """Handles text command y!accept for challenges."""
    target_id = str(message.author.id)
    for k, data in list(_PENDING_CHALLENGES.items()):
        if data["target_id"] == target_id:
            await execute_challenge_resolution(data, accepted=True)
            return
    await _safe_send_reply(message, "You don't have any pending challenges to accept!")


async def handle_decline(message, client, args: list):
    """Handles text command y!decline for challenges."""
    target_id = str(message.author.id)
    for k, data in list(_PENDING_CHALLENGES.items()):
        if data["target_id"] == target_id or data["author_id"] == target_id:
            await execute_challenge_resolution(data, accepted=False)
            return
    await _safe_send_reply(message, "You don't have any pending challenges to decline!")

# ─── CASINO: HIGHER OR LOWER GUESSING GAME ──────────────────────────────────

async def process_hl_reset(game_state: dict, interaction=None, view=None):
    """Resets active Higher/Lower game: refunds bet on 0-streak, cashes out if streak > 0."""
    author_id = game_state["author_id"]
    if game_state.get("finished"):
        return
    game_state["finished"] = True
    _ACTIVE_HL_GAMES.pop(author_id, None)

    if view:
        for child in view.children:
            child.disabled = True

    streak = game_state.get("streak", 0)
    bet = game_state.get("bet", 0)
    if streak > 0:
        mult = get_hl_multiplier(streak)
        pot = int(bet * mult)
        await _update_user_stats(author_id, berries_delta=pot, is_gamble=True)
        reset_text = (
            f"🔄 **HIGHER OR LOWER — RESET & CASHED OUT!** 🔄\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{game_state['author_mention']} hit reset! Your **{streak}**-streak was cashed out for **+{pot}** 🫐!\n"
            f"The table has been reset for a fresh game!\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
    else:
        await _update_user_stats(author_id, berries_delta=bet)
        reset_text = (
            f"🔄 **HIGHER OR LOWER — RESET!** 🔄\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{game_state['author_mention']} reset the board! Your wager of **{bet}** 🫐 was refunded.\n"
            f"The table has been reset for a fresh game!\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

    if interaction:
        await interaction.edit_original_response(content=reset_text, view=view)
    elif game_state.get("message"):
        await game_state["message"].edit(content=reset_text, view=view)


async def handle_higherlower(message, client, args: list):
    """Handles y!higherlower <amount> (or y!hl, y!guess, y!hl reset)."""
    author_id = str(message.author.id)

    # Check for explicit reset command: y!hl reset
    if args and args[0].lower() in ("reset", "cancel", "clear", "quit", "stop"):
        if author_id in _ACTIVE_HL_GAMES:
            await process_hl_reset(_ACTIVE_HL_GAMES[author_id])
        else:
            await _safe_send_reply(message, "- *Yuna tilts her head* \"You don't have an active Higher or Lower game to reset!\"")
        return

    # If already active, auto-reset previous game gracefully!
    if author_id in _ACTIVE_HL_GAMES:
        old_game = _ACTIVE_HL_GAMES.pop(author_id)
        old_game["finished"] = True
        old_streak = old_game.get("streak", 0)
        old_bet = old_game.get("bet", 0)
        if old_streak > 0:
            mult = get_hl_multiplier(old_streak)
            pot = int(old_bet * mult)
            await _update_user_stats(author_id, berries_delta=pot, is_gamble=True)
            await _safe_send_reply(message, f"🔄 *Previous game (streak: {old_streak}) auto-cashed out for **+{pot}** 🫐! Starting your fresh game...*")
        else:
            await _update_user_stats(author_id, berries_delta=old_bet)

    amount = 10
    if args:
        cleaned = args[0].replace(",", "")
        if cleaned.isdigit():
            amount = int(cleaned)

    if amount <= 0:
        await _safe_send_reply(message, "- *Yuna frowns* \"Wager must be at least 1 🫐!\"")
        return

    author_stats = await _get_user_stats(author_id)
    if author_stats.get("berries", 0) < amount:
        await _safe_send_reply(
            message,
            f"- *Yuna chuckles* \"You only have **{author_stats.get('berries', 0)}** 🫐! You can't afford a **{amount}** 🫐 guess!\""
        )
        return

    # Deduct bet upfront
    await _update_user_stats(author_id, berries_delta=-amount, is_gamble=True)

    # Starting card: 2 to 12 (min 1, max 13) so player always has choices on round 1!
    starting_num = random.randint(2, 12)

    game_state = {
        "author_id": author_id,
        "author_mention": message.author.mention,
        "bet": amount,
        "current_number": starting_num,
        "streak": 0,
        "channel_id": message.channel.id,
        "message": None,
        "finished": False
    }
    _ACTIVE_HL_GAMES[author_id] = game_state

    view = HigherLowerView(author_id, game_state)
    first_pot = int(amount * 1.5)
    init_text = (
        f"🎲 **Yuna's Higher or Lower Table** 🎲\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Player: {message.author.mention} | Wager: **{amount}** 🫐\n"
        f"Current Card: {format_hl_number(starting_num)} `(Range: 1 – 13)`\n\n"
        f"Streak: **0** | Next Multiplier: **1.5x** *(Pot: {first_pot} 🫐)*\n\n"
        f"Will the next secret card be **Higher** or **Lower**?\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"*(Click buttons below or type `y!higher` / `y!lower` / `y!hl reset`)*"
    )
    sent_msg = await _safe_send_reply(message, init_text, view=view)
    game_state["message"] = sent_msg


async def process_hl_turn(game_state: dict, guess: str, interaction=None, view=None):
    author_id = game_state["author_id"]
    if game_state.get("finished"):
        return

    cur_num = game_state["current_number"]
    bet = game_state["bet"]
    streak = game_state["streak"]
    guess = guess.lower()

    # ~6% Low-odds comedy event!
    comedy_event = None
    if random.random() < 0.06:
        tpl = random.choice(HL_COMEDY_EVENTS)
        c_num = random.randint(1, 13)
        comedy_event = tpl[0].format(num=format_hl_number(c_num))
        new_num = c_num
    else:
        new_num = random.randint(1, 13)

    # Check comparison
    if new_num == cur_num:
        # Exact tie: free mulligan & reshuffle card so it doesn't get stuck!
        reset_num = random.randint(2, 12)
        game_state["current_number"] = reset_num
        tie_text = (
            f"🎲 **COSMIC TIE — {format_hl_number(new_num)}!** 🎲\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"The next card was also {format_hl_number(new_num)}! Exactly identical!\n"
            f"*Yuna shrugs:* \"Cosmic berry truce! Your streak of **{streak}** is safe!\n"
            f"Deck reshuffled and reset to: {format_hl_number(reset_num)}! Guess again!\"\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        if interaction:
            await interaction.edit_original_response(content=tie_text, view=view)
        elif game_state.get("message"):
            await game_state["message"].edit(content=tie_text, view=view)
        return

    is_correct = (guess == "higher" and new_num > cur_num) or (guess == "lower" and new_num < cur_num)

    if is_correct:
        streak += 1
        game_state["streak"] = streak
        mult = get_hl_multiplier(streak)
        pot = int(bet * mult)

        # Check if card hit limit (1 or 13) -> Reset to a fresh middle card!
        reset_notice = ""
        if new_num in (1, 13):
            reset_num = random.randint(2, 12)
            game_state["current_number"] = reset_num
            limit_name = "King (13)" if new_num == 13 else "Ace (1)"
            reset_notice = f"\n🔄 *Card reached limit ({limit_name})! Deck reshuffled and reset to: {format_hl_number(reset_num)}!*"
            shown_num_str = f"{format_hl_number(new_num)} ➔ {format_hl_number(reset_num)}"
        else:
            game_state["current_number"] = new_num
            shown_num_str = format_hl_number(new_num)

        # Track max streak in stats
        async with _LOCK:
            u_stat = _USER_STATS.get(author_id, {})
            if streak > u_stat.get("hl_max_streak", 0):
                u_stat["hl_max_streak"] = streak
                _save_data_sync(_USER_STATS)

        unlocked = await check_and_award_achievements(author_id)
        banner = format_achievement_banner(unlocked)

        next_mult = get_hl_multiplier(streak + 1)
        next_pot = int(bet * next_mult)

        # Update view
        if view:
            for child in view.children:
                if hasattr(child, "label") and "Cash Out" in child.label:
                    child.label = f"💰 Cash Out ({pot} 🫐)"
                    child.disabled = False

        comedy_line = f"\n🎭 *{comedy_event}*\n" if comedy_event else ""
        win_text = (
            f"🎲 **CORRECT! The card was {format_hl_number(new_num)}!** 🎲{comedy_line}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Player: {game_state['author_mention']} | Wager: **{bet}** 🫐\n"
            f"Current Card: {shown_num_str} `(Range: 1 – 13)`{reset_notice}\n\n"
            f"🔥 Streak: **{streak}** | Current Multiplier: **{mult:.1f}x**\n"
            f"💰 **Locked Pot: {pot} 🫐** *(Next Streak: {next_pot} 🫐)*{banner}\n\n"
            f"Guess again (**Higher** / **Lower**), **💰 Cash Out**, or **🔄 Reset**!\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        if interaction:
            await interaction.edit_original_response(content=win_text, view=view)
        elif game_state.get("message"):
            await game_state["message"].edit(content=win_text, view=view)
    else:
        # BUST!
        game_state["finished"] = True
        _ACTIVE_HL_GAMES.pop(author_id, None)
        await record_gamble_loss(author_id)

        if view:
            for child in view.children:
                child.disabled = True

        unlocked = await check_and_award_achievements(author_id)
        banner = format_achievement_banner(unlocked)

        bust_text = (
            f"💥 **BUST! The card was {format_hl_number(new_num)}!** 💥\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"You guessed **{guess.upper()}**, but the card was {format_hl_number(new_num)} (previous was {format_hl_number(cur_num)}).\n\n"
            f"*Yuna giggles WUWAHAHA~* \"Greedy mortal! Your streak of **{streak}** vanished into thin air! Game reset!\"\n"
            f"💸 You lost **{bet}** 🫐.{banner}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        if interaction:
            await interaction.edit_original_response(content=bust_text, view=view)
        elif game_state.get("message"):
            await game_state["message"].edit(content=bust_text, view=view)
        await record_task_progress(author_id, "gamble")


async def process_hl_cashout(game_state: dict, interaction=None, view=None):
    author_id = game_state["author_id"]
    if game_state.get("finished"):
        return

    game_state["finished"] = True
    _ACTIVE_HL_GAMES.pop(author_id, None)

    bet = game_state["bet"]
    streak = game_state["streak"]
    mult = get_hl_multiplier(streak)
    winnings = int(bet * mult)
    profit = winnings - bet

    await record_gamble_win(author_id)
    bonus, bonus_txt = await get_gamble_win_bonuses(author_id, profit)
    winnings += bonus
    profit += bonus

    await _update_user_stats(author_id, berries_delta=winnings, is_gamble=True)

    if view:
        for child in view.children:
            child.disabled = True

    unlocked = await check_and_award_achievements(author_id)
    banner = format_achievement_banner(unlocked)

    cashout_text = (
        f"💰 **HIGHER OR LOWER — CASHED OUT!** 💰\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{game_state['author_mention']} decided to take the loot and run!\n\n"
        f"Final Streak: **{streak}** | Multiplier: **{mult:.1f}x**\n"
        f"🎉 **Total Payout: +{winnings} 🫐** *(Profit: +{profit} 🫐)*{bonus_txt}{banner}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    if interaction:
        await interaction.edit_original_response(content=cashout_text, view=view)
    elif game_state.get("message"):
        await game_state["message"].edit(content=cashout_text, view=view)

    await record_task_progress(author_id, "gamble")


async def handle_higher(message, client, args: list):
    author_id = str(message.author.id)
    if author_id not in _ACTIVE_HL_GAMES:
        await _safe_send_reply(message, "You don't have an active Higher or Lower game! Start one with `y!hl <amount>`!")
        return
    await process_hl_turn(_ACTIVE_HL_GAMES[author_id], guess="higher")


async def handle_lower(message, client, args: list):
    author_id = str(message.author.id)
    if author_id not in _ACTIVE_HL_GAMES:
        await _safe_send_reply(message, "You don't have an active Higher or Lower game! Start one with `y!hl <amount>`!")
        return
    await process_hl_turn(_ACTIVE_HL_GAMES[author_id], guess="lower")


async def handle_hl_cashout(message, client, args: list):
    author_id = str(message.author.id)
    if author_id not in _ACTIVE_HL_GAMES:
        await _safe_send_reply(message, "You don't have an active Higher or Lower game to cash out!")
        return
    await process_hl_cashout(_ACTIVE_HL_GAMES[author_id])

# ─── CASINO: ABSURDITY COIN FLIP ────────────────────────────────────────────

async def handle_coinflip(message, client, args: list):
    """Handles y!coinflip <amount> [heads/tails] [count] (or y!flip, y!cf)."""
    author_id = str(message.author.id)
    amount = 10
    guess = None
    count = 1

    digits_found = []
    for a in args:
        cleaned = a.replace(",", "")
        if cleaned.isdigit():
            digits_found.append(int(cleaned))
        elif cleaned.lower() in ("heads", "head", "h"):
            guess = "heads"
        elif cleaned.lower() in ("tails", "tail", "t"):
            guess = "tails"

    if len(digits_found) >= 2:
        amount = digits_found[0]
        count = max(1, min(5, digits_found[1]))
    elif len(digits_found) == 1:
        amount = digits_found[0]

    if amount <= 0:
        await _safe_send_reply(message, "- *Yuna crosses her arms* \"Wager must be at least 1 🫐!\"")
        return

    total_bet = amount * count
    author_stats = await _get_user_stats(author_id)
    if author_stats.get("berries", 0) < total_bet:
        await _safe_send_reply(
            message,
            f"- *Yuna snickers* \"You need **{total_bet:,}** 🫐 for {count} flip{'s' if count > 1 else ''} of {amount:,} 🫐! You only have **{author_stats.get('berries', 0):,}** 🫐!\""
        )
        return

    # If count > 1 and side wasn't chosen, prompt
    if count > 1 and not guess:
        await _safe_send_reply(
            message,
            "- *Yuna leans in* \"For multi-coinflips, please choose a side! Usage: `y!flip <amount> <heads/tails> [count]` (e.g. `y!flip 50 heads 3`)\""
        )
        return

    # If side wasn't chosen in command line, present interactive buttons
    if not guess:
        view = CoinFlipView(author_id, amount)
        prompt_text = (
            f"🪙 **Yuna's Absurd Coin Toss** 🪙\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Player: {message.author.mention} | Wager: **{amount}** 🫐\n"
            f"Will it land on **Heads** or **Tails**?\n\n"
            f"*(Beware: 40% chance of bizarre events & bird heists!)*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await _safe_send_reply(message, prompt_text, view=view)
        return

    # If multi-flip
    if count > 1:
        await execute_multi_coinflip(message, author_id, amount, guess, count)
    else:
        await execute_solo_coinflip(message, author_id, amount, guess)


async def execute_multi_coinflip(message, author_id: str, amount: int, guess: str, count: int):
    total_bet = amount * count
    s = await _get_user_stats(author_id)
    if s.get("berries", 0) < total_bet:
        await _safe_send_reply(
            message,
            f"- *Yuna snickers* \"You need **{total_bet:,}** 🫐 for {count} flips of {amount} 🫐 each! You only have **{s.get('berries', 0):,}** 🫐!\""
        )
        return

    # Check clover buff
    has_clover = s.get("clover_active", False)
    if has_clover:
        async with _LOCK:
            _USER_STATS[author_id]["clover_active"] = False
            _save_data_sync(_USER_STATS)

    # Deduct total bet upfront
    await _update_user_stats(author_id, berries_delta=-total_bet, is_gamble=True)

    flip_results = []
    total_payout = 0
    total_won_flips = 0

    opposite = "tails" if guess == "heads" else "heads"
    win_chance = 0.50 if has_clover else 0.28

    for i in range(1, count + 1):
        roll = random.random()
        if roll < 0.40:
            absurdity = random.choice(COINFLIP_ABSURDITIES)
            refund = absurdity["refund"]
            if refund:
                total_payout += amount
                flip_results.append(f"`Flip #{i}:` 🌀 *Absurd event!* Bet refunded (**+{amount}** 🫐)")
            else:
                flip_results.append(f"`Flip #{i}:` 🦅 *Bird / Sewer heist!* Bet snatched (**0** 🫐)")
            async with _LOCK:
                u_stat = _USER_STATS.get(author_id, {})
                u_stat["coin_heist_count"] = u_stat.get("coin_heist_count", 0) + 1
                _save_data_sync(_USER_STATS)
        else:
            is_win = (random.random() < win_chance)
            landing = guess if is_win else opposite
            if is_win:
                payout_flip = int(amount * 2.5)
                total_payout += payout_flip
                total_won_flips += 1
                flip_results.append(f"`Flip #{i}:` 🪙 **{landing.upper()}** — 🎉 Correct! (**+{payout_flip}** 🫐)")
            else:
                flip_results.append(f"`Flip #{i}:` 🪙 **{landing.upper()}** — 💀 Miss! (**0** 🫐)")

    net_profit = total_payout - total_bet
    bonus_str = ""
    bonus_berries = 0
    if net_profit > 0:
        await record_gamble_win(author_id)
        bonus_berries, bonus_str = await get_gamble_win_bonuses(author_id, net_profit)
        total_payout += bonus_berries
        net_profit += bonus_berries
    elif net_profit < 0:
        await record_gamble_loss(author_id)

    if total_payout > 0:
        await _update_user_stats(author_id, berries_delta=total_payout, is_gamble=True)

    unlocked = await check_and_award_achievements(author_id)
    banner = format_achievement_banner(unlocked)

    clover_tag = "\n🍀 *(Lucky Clover boosted win odds!)*" if has_clover else ""
    if net_profit > 0:
        summary_outcome = f"🎉 **JACKPOT! Net Profit: +{net_profit:,} 🫐**"
    elif net_profit == 0:
        summary_outcome = "⚖️ **TIE! Net Result: 0 🫐**"
    else:
        summary_outcome = f"💸 **Net Loss: {net_profit:,} 🫐**"

    res_lines = "\n".join(flip_results)
    desc = (
        f"🪙 **MULTI-COIN FLIP ({count} FLIPS) — {guess.upper()}** 🪙\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Total Wager: **{total_bet:,}** 🫐 (`{amount:,}` 🫐 × {count})\n\n"
        f"{res_lines}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Total Returns: **{total_payout:,}** 🫐\n"
        f"{summary_outcome}{bonus_str}{clover_tag}{banner}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    await _safe_send_reply(message, desc)
    await record_task_progress(author_id, "gamble")


async def execute_solo_coinflip(message, author_id: str, amount: int, guess: str, interaction=None, view=None):
    if view:
        for child in view.children:
            child.disabled = True

    # Double check user balance
    s = await _get_user_stats(author_id)
    if s.get("berries", 0) < amount:
        err = f"⚠️ You no longer have **{amount}** 🫐!"
        if interaction:
            await interaction.edit_original_response(content=err, view=view)
        else:
            await _safe_send_reply(message, err)
        return

    # Deduct bet upfront
    await _update_user_stats(author_id, berries_delta=-amount, is_gamble=True)

    # 40% Chance of Absurdity!
    roll = random.random()
    if roll < 0.40:
        absurdity = random.choice(COINFLIP_ABSURDITIES)
        refund = absurdity["refund"]
        text_template = absurdity["text"]

        if refund:
            # Return bet to pouch
            await _update_user_stats(author_id, berries_delta=amount)

        # Track heist for achievement
        async with _LOCK:
            u_stat = _USER_STATS.get(author_id, {})
            u_stat["coin_heist_count"] = u_stat.get("coin_heist_count", 0) + 1
            _save_data_sync(_USER_STATS)

        unlocked = await check_and_award_achievements(author_id)
        banner = format_achievement_banner(unlocked)

        final_msg = text_template.format(amount=amount) + banner
        if interaction:
            await interaction.edit_original_response(content=final_msg, view=view)
        else:
            await _safe_send_reply(message, final_msg)
        return

    # 60% Chance of Landing with Low Win Rate (28% win, 72% loss)
    is_win = (random.random() < 0.28)
    opposite = "tails" if guess == "heads" else "heads"
    landing = guess if is_win else opposite

    if is_win:
        # Tough odds payout: 2.5x
        payout = int(amount * 2.5)
        profit = payout - amount
        await record_gamble_win(author_id)
        bonus_berries, bonus_str = await get_gamble_win_bonuses(author_id, profit)
        payout += bonus_berries
        profit += bonus_berries
        await _update_user_stats(author_id, berries_delta=payout, is_gamble=True)

        unlocked = await check_and_award_achievements(author_id)
        banner = format_achievement_banner(unlocked)

        res = (
            f"🪙 **COIN FLIP — MIRACLE LANDING!** 🪙\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"The coin spun violently, dodged three pigeons and an eagle...\n"
            f"And landed cleanly on: 🪙 **{landing.upper()}**!\n\n"
            f"🎉 **JACKPOT!** You guessed correctly against impossible odds!\n"
            f"Payout: **+{payout}** 🫐 *(Profit: +{profit} 🫐)*{bonus_str}{banner}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
    else:
        await record_gamble_loss(author_id)
        unlocked = await check_and_award_achievements(author_id)
        banner = format_achievement_banner(unlocked)

        res = (
            f"🪙 **COIN FLIP RESULTS** 🪙\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"The coin bounced once, twice, and settled on: 🪙 **{landing.upper()}**!\n"
            f"You guessed **{guess.upper()}**.\n\n"
            f"*Yuna giggles:* \"The coin has spoken, and it said no berries for you!\"\n"
            f"💸 You lost **{amount}** 🫐.{banner}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

    if interaction:
        await interaction.edit_original_response(content=res, view=view)
    else:
        await _safe_send_reply(message, res)

    await record_task_progress(author_id, "gamble")


# ─── CASINO: ROULETTE (MAX 250x PAYOUT) ─────────────────────────────────────

async def handle_roulette(message, client, args: list):
    """Handles y!roulette <amount> [bet] (or y!wheel, y!spin)."""
    author_id = str(message.author.id)
    amount = 10
    bet = None

    if len(args) == 1:
        c = args[0].replace(",", "")
        if c.isdigit() and int(c) > 0:
            amount = int(c)
        else:
            bet = c.lower()
    elif len(args) >= 2:
        c0 = args[0].replace(",", "")
        c1 = args[1].replace(",", "")
        if c0.isdigit() and int(c0) > 0 and (not c1.isdigit() or (0 <= int(c1) <= 36)):
            amount = int(c0)
            bet = c1.lower()
        elif c1.isdigit() and int(c1) > 0:
            amount = int(c1)
            bet = c0.lower()
        else:
            if c0.isdigit() and int(c0) > 0:
                amount = int(c0)
            bet = c1.lower()

    if amount <= 0:
        await _safe_send_reply(message, "- *Yuna crosses her arms* \"Wager must be at least 1 🫐!\"")
        return

    author_stats = await _get_user_stats(author_id)
    if author_stats.get("berries", 0) < amount:
        await _safe_send_reply(
            message,
            f"- *Yuna snickers* \"You need **{amount:,}** 🫐 to spin the wheel! You only have **{author_stats.get('berries', 0):,}** 🫐!\""
        )
        return

    if not bet:
        view = RouletteView(author_id, amount)
        prompt_text = (
            f"🎡 **YUNA'S HIGH-STAKES ROULETTE** 🎡\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Player: {message.author.mention} | Wager: **{amount:,}** 🫐\n"
            f"Select your bet from the buttons below, or bet on any number `0`–`36`!\n\n"
            f"👑 **Golden Crown (000)** pays **250x**!\n"
            f"🔴 **Red** / ⚫ **Black** / **Even** / **Odd** / **High** / **Low** pay **1:1**\n"
            f"📦 **Dozens (1st/2nd/3rd 12)** pay **2:1**\n"
            f"🎯 **Single Number (0–36)** pays **35:1** *(with celestial lightning up to 250x!)*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await _safe_send_reply(message, prompt_text, view=view)
        return

    await execute_roulette_spin(message, author_id, amount, bet)


async def execute_roulette_spin(message, author_id: str, amount: int, bet_choice: str, interaction=None, view=None):
    if view:
        for child in view.children:
            child.disabled = True

    s = await _get_user_stats(author_id)
    if s.get("berries", 0) < amount:
        err = f"⚠️ You no longer have **{amount:,}** 🫐!"
        if interaction:
            await interaction.edit_original_response(content=err, view=view)
        else:
            await _safe_send_reply(message, err)
        return

    # Deduct bet upfront
    await _update_user_stats(author_id, berries_delta=-amount, is_gamble=True)

    # Check for silent absurdity event (~8.5% chance)
    if random.random() < 0.085:
        absurdity = random.choices(ROULETTE_ABSURDITIES, weights=[a.get("weight", 10) for a in ROULETTE_ABSURDITIES])[0]
        if absurdity.get("refund"):
            bonus = absurdity.get("bonus", 0)
            await _update_user_stats(author_id, berries_delta=amount + bonus)
            msg_text = absurdity["text"].format(amount=amount)
        elif absurdity.get("is_win_all"):
            payout = amount * 2
            profit = payout - amount
            await record_gamble_win(author_id)
            bonus_berries, bonus_str = await get_gamble_win_bonuses(author_id, profit)
            payout += bonus_berries
            profit += bonus_berries
            await _update_user_stats(author_id, berries_delta=payout, is_gamble=True)
            msg_text = absurdity["text"].format(amount=amount, payout=payout) + bonus_str
        else:
            await record_gamble_loss(author_id)
            msg_text = absurdity["text"].format(amount=amount)

        unlocked = await check_and_award_achievements(author_id)
        banner = format_achievement_banner(unlocked)
        await record_task_progress(author_id, "gamble")
        final_res = msg_text + banner
        if interaction:
            await interaction.edit_original_response(content=final_res, view=view)
        else:
            await _safe_send_reply(message, final_res)
        return

    # Standard 38-Pocket Wheel: 0, 1-36, 000 (Crown Slot)
    wheel_pockets = ["0"] + [str(i) for i in range(1, 37)] + ["000"]
    pocket = random.choice(wheel_pockets)

    if pocket == "000":
        pocket_display = "👑 000 (Golden Crown Slot)"
    elif pocket == "0":
        pocket_display = "🟢 0 (Green Zero)"
    elif int(pocket) in ROULETTE_REDS:
        pocket_display = f"🔴 {pocket} (Red)"
    else:
        pocket_display = f"⚫ {pocket} (Black)"

    choice = bet_choice.lower().strip()
    is_win = False
    multiplier = 0
    special_msg = ""

    if choice in ("crown", "gold", "golden", "jackpot", "000", "250x"):
        if pocket == "000":
            is_win = True
            multiplier = 250
            special_msg = "👑 **THE GOLDEN CROWN HAS ALIGNED!** Maximum 250x Jackpot!"
    elif choice in ("red", "r"):
        if pocket.isdigit() and int(pocket) in ROULETTE_REDS:
            is_win = True
            multiplier = 2
    elif choice in ("black", "b"):
        if pocket.isdigit() and int(pocket) in ROULETTE_BLACKS:
            is_win = True
            multiplier = 2
    elif choice in ("even", "ev"):
        if pocket.isdigit() and int(pocket) > 0 and int(pocket) % 2 == 0:
            is_win = True
            multiplier = 2
    elif choice in ("odd", "od"):
        if pocket.isdigit() and int(pocket) > 0 and int(pocket) % 2 == 1:
            is_win = True
            multiplier = 2
    elif choice in ("low", "1-18"):
        if pocket.isdigit() and 1 <= int(pocket) <= 18:
            is_win = True
            multiplier = 2
    elif choice in ("high", "19-36"):
        if pocket.isdigit() and 19 <= int(pocket) <= 36:
            is_win = True
            multiplier = 2
    elif choice in ("1st12", "first12", "1-12", "d1"):
        if pocket.isdigit() and 1 <= int(pocket) <= 12:
            is_win = True
            multiplier = 3
    elif choice in ("2nd12", "second12", "13-24", "d2"):
        if pocket.isdigit() and 13 <= int(pocket) <= 24:
            is_win = True
            multiplier = 3
    elif choice in ("3rd12", "third12", "25-36", "d3"):
        if pocket.isdigit() and 25 <= int(pocket) <= 36:
            is_win = True
            multiplier = 3
    elif choice in ("col1", "column1", "c1"):
        if pocket.isdigit() and int(pocket) > 0 and int(pocket) % 3 == 1:
            is_win = True
            multiplier = 3
    elif choice in ("col2", "column2", "c2"):
        if pocket.isdigit() and int(pocket) > 0 and int(pocket) % 3 == 2:
            is_win = True
            multiplier = 3
    elif choice in ("col3", "column3", "c3"):
        if pocket.isdigit() and int(pocket) > 0 and int(pocket) % 3 == 0:
            is_win = True
            multiplier = 3
    elif choice in [str(i) for i in range(37)]:
        if pocket == choice:
            is_win = True
            multiplier = 36
            # 12% celestial golden lightning chance on straight number
            if random.random() < 0.12:
                multiplier = 250
                special_msg = f"⚡ **CELESTIAL LIGHTNING STRIKE!** Golden energy supercharges slot {pocket}! Payout upgraded to 250x!"

    if is_win:
        if multiplier == 250:
            async with _LOCK:
                u_stat = _USER_STATS.get(author_id, {})
                u_stat["roulette_jackpots"] = u_stat.get("roulette_jackpots", 0) + 1
                _save_data_sync(_USER_STATS)

        payout = int(amount * multiplier)
        profit = payout - amount
        await record_gamble_win(author_id)
        bonus_berries, bonus_str = await get_gamble_win_bonuses(author_id, profit)
        payout += bonus_berries
        profit += bonus_berries
        await _update_user_stats(author_id, berries_delta=payout, is_gamble=True)

        unlocked = await check_and_award_achievements(author_id)
        banner = format_achievement_banner(unlocked)
        await record_task_progress(author_id, "gamble")

        if multiplier == 250:
            res = (
                f"🎡 **ROULETTE — 👑 MAXIMUM 250x JACKPOT!** 👑\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"The wheel spins at breakneck speed... and stops on: **{pocket_display}**!\n"
                f"Your Bet: **{bet_choice.upper()}**\n\n"
                f"🌟 **CELESTIAL JACKPOT ACHIEVED!** 🌟\n"
                f"{special_msg or 'The golden crown shines bright! Maximum 250x payout!'}\n"
                f"Payout: **+{payout:,}** 🫐 *(Profit: +{profit:,} 🫐)*{bonus_str}{banner}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
        else:
            res = (
                f"🎡 **ROULETTE — WINNER!** 🎡\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"The ivory ball settles on: **{pocket_display}**!\n"
                f"Your Bet: **{bet_choice.upper()}**\n\n"
                f"🎉 **YOU WON!** Multiplier: **{multiplier}x**\n"
                f"Payout: **+{payout:,}** 🫐 *(Profit: +{profit:,} 🫐)*{bonus_str}{banner}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
    else:
        await record_gamble_loss(author_id)
        unlocked = await check_and_award_achievements(author_id)
        banner = format_achievement_banner(unlocked)
        await record_task_progress(author_id, "gamble")

        res = (
            f"🎡 **ROULETTE — ROUND OVER** 🎡\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"The ivory ball settles on: **{pocket_display}**!\n"
            f"Your Bet: **{bet_choice.upper()}**\n\n"
            f"*Yuna sweeps the table:* \"The house claims the round! Better luck next spin!\"\n"
            f"💸 You lost your wager of **{amount:,}** 🫐.{banner}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

    if interaction:
        await interaction.edit_original_response(content=res, view=view)
    else:
        await _safe_send_reply(message, res)


# ─── CASINO: VIDEO POKER (5-CARD DRAW, MAX 250x ROYAL FLUSH) ─────────────────

async def handle_poker(message, client, args: list):
    """Handles y!poker <amount> (or y!vp, y!videopoker)."""
    author_id = str(message.author.id)

    if author_id in _ACTIVE_POKER_GAMES:
        await _safe_send_reply(
            message,
            "⚠️ You already have an active Video Poker hand! Click the card buttons or type `y!hold <1-5>` then `y!draw`."
        )
        return

    amount = 10
    if args:
        cleaned = args[0].replace(",", "")
        if cleaned.isdigit():
            amount = int(cleaned)

    if amount <= 0:
        await _safe_send_reply(message, "- *Yuna crosses her arms* \"Wager must be at least 1 🫐!\"")
        return

    author_stats = await _get_user_stats(author_id)
    if author_stats.get("berries", 0) < amount:
        await _safe_send_reply(
            message,
            f"- *Yuna scoffs* \"You only have **{author_stats.get('berries', 0):,}** 🫐! You can't afford a **{amount:,}** 🫐 poker hand!\""
        )
        return

    # Deduct bet upfront
    await _update_user_stats(author_id, berries_delta=-amount, is_gamble=True)

    deck = create_poker_deck()
    hand = [deck.pop() for _ in range(5)]
    game_state = {
        "author_id": author_id,
        "author_mention": message.author.mention,
        "amount": amount,
        "deck": deck,
        "hand": hand,
        "held": set(),
        "finished": False,
        "channel_id": message.channel.id
    }
    _ACTIVE_POKER_GAMES[author_id] = game_state

    view = PokerView(author_id, game_state)
    await _safe_send_reply(message, format_poker_message(game_state), view=view)


async def handle_poker_hold(message, client, args: list):
    """Handles y!hold <1-5>... (or y!keep)."""
    author_id = str(message.author.id)
    if author_id not in _ACTIVE_POKER_GAMES:
        await _safe_send_reply(message, "You don't have an active poker hand! Deal a hand with `y!poker <amount>`.")
        return

    game = _ACTIVE_POKER_GAMES[author_id]
    if not args:
        held_nums = [str(i + 1) for i in sorted(game["held"])]
        held_str = ", ".join(held_nums) if held_nums else "None"
        await _safe_send_reply(
            message,
            f"Currently held cards: **{held_str}**.\nType `y!hold 1 3 5` to toggle cards, or `y!draw` to finish the hand!"
        )
        return

    for a in args:
        low = a.lower()
        if low in ("none", "clear", "0"):
            game["held"].clear()
        elif low in ("all",):
            game["held"] = {0, 1, 2, 3, 4}
        elif low in ("1", "2", "3", "4", "5"):
            idx = int(low) - 1
            if idx in game["held"]:
                game["held"].remove(idx)
            else:
                game["held"].add(idx)

    await _safe_send_reply(message, format_poker_message(game))


async def handle_poker_draw(message, client, args: list):
    """Handles y!draw (or y!swap)."""
    author_id = str(message.author.id)
    if author_id not in _ACTIVE_POKER_GAMES:
        await _safe_send_reply(message, "You don't have an active poker hand! Start one with `y!poker <amount>`.")
        return

    await execute_poker_draw(message, author_id)


async def execute_poker_draw(message, author_id: str, interaction=None, view=None):
    if author_id not in _ACTIVE_POKER_GAMES:
        return

    game = _ACTIVE_POKER_GAMES.pop(author_id)
    if game.get("finished"):
        return
    game["finished"] = True

    if view:
        for c in view.children:
            c.disabled = True

    # Check for silent absurdity event (~8.5% chance)
    if random.random() < 0.085:
        absurdity = random.choice(POKER_ABSURDITIES)
        # Draw missing cards from deck
        for i in range(5):
            if i not in game["held"]:
                game["hand"][i] = game["deck"].pop()

        a_type = absurdity.get("type", "")
        hand_name, base_mult, desc = evaluate_poker_hand(game["hand"])

        if a_type == "uno_wild":
            mult = (base_mult * 2.0) if base_mult > 0 else 4.0
        elif a_type == "crayon_ace":
            mult = (base_mult * 1.5) if base_mult > 0 else 2.0
        else:
            mult = float(absurdity.get("multiplier", 5.0))

        amount = game["amount"]
        payout = int(amount * mult)
        profit = payout - amount
        await record_gamble_win(author_id)
        bonus_berries, bonus_str = await get_gamble_win_bonuses(author_id, profit)
        payout += bonus_berries
        profit += bonus_berries
        await _update_user_stats(author_id, berries_delta=payout, is_gamble=True)

        unlocked = await check_and_award_achievements(author_id)
        banner = format_achievement_banner(unlocked)
        await record_task_progress(author_id, "gamble")

        final_cards_str = "  ".join([f"`[{c[0]}{c[1]}]`" for c in game["hand"]])
        res = (
            f"🃏 **VIDEO POKER — {absurdity['title'].upper()}!** 🃏\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Final Hand: {final_cards_str}\n\n"
            f"{absurdity['text']}\n\n"
            f"🎉 **PAYOUT:** **+{payout:,}** 🫐 *(Profit: +{profit:,} 🫐)*{bonus_str}{banner}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        if interaction:
            await interaction.edit_original_response(content=res, view=view)
        else:
            await _safe_send_reply(message, res)
        return

    # Standard Draw: replace non-held cards
    for i in range(5):
        if i not in game["held"]:
            game["hand"][i] = game["deck"].pop()

    hand_name, mult, desc = evaluate_poker_hand(game["hand"])
    amount = game["amount"]

    if mult > 0:
        if hand_name == "Royal Flush":
            async with _LOCK:
                u_stat = _USER_STATS.get(author_id, {})
                u_stat["poker_royal_flushes"] = u_stat.get("poker_royal_flushes", 0) + 1
                _save_data_sync(_USER_STATS)

        payout = int(amount * mult)
        profit = payout - amount
        await record_gamble_win(author_id)
        bonus_berries, bonus_str = await get_gamble_win_bonuses(author_id, profit)
        payout += bonus_berries
        profit += bonus_berries
        await _update_user_stats(author_id, berries_delta=payout, is_gamble=True)

        unlocked = await check_and_award_achievements(author_id)
        banner = format_achievement_banner(unlocked)
        await record_task_progress(author_id, "gamble")

        final_cards_str = "  ".join([f"`[{c[0]}{c[1]}]`" for c in game["hand"]])
        res = (
            f"🃏 **VIDEO POKER — WINNER!** 🃏\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Final Hand: {final_cards_str}\n"
            f"Result: **{hand_name}** ({mult}x)\n"
            f"> {desc}\n\n"
            f"🎉 **YOU WON!** Payout: **+{payout:,}** 🫐 *(Profit: +{profit:,} 🫐)*{bonus_str}{banner}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
    else:
        await record_gamble_loss(author_id)
        unlocked = await check_and_award_achievements(author_id)
        banner = format_achievement_banner(unlocked)
        await record_task_progress(author_id, "gamble")

        final_cards_str = "  ".join([f"`[{c[0]}{c[1]}]`" for c in game["hand"]])
        res = (
            f"🃏 **VIDEO POKER — ROUND OVER** 🃏\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Final Hand: {final_cards_str}\n"
            f"Result: **{hand_name}**\n"
            f"> {desc}\n\n"
            f"*Yuna sweeps the table:* \"Tough break! Better cards next deal!\"\n"
            f"💸 You lost your wager of **{amount:,}** 🫐.{banner}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

    if interaction:
        await interaction.edit_original_response(content=res, view=view)
    else:
        await _safe_send_reply(message, res)


async def execute_poker_fold(message, author_id: str, interaction=None, view=None):
    if author_id not in _ACTIVE_POKER_GAMES:
        return

    game = _ACTIVE_POKER_GAMES.pop(author_id)
    if game.get("finished"):
        return
    game["finished"] = True
    await record_gamble_loss(author_id)

    if view:
        for c in view.children:
            c.disabled = True

    amount = game["amount"]
    refund = int(amount * 0.25)
    if refund > 0:
        await _update_user_stats(author_id, berries_delta=refund)

    res = (
        f"🃏 **VIDEO POKER — FOLDED** 🃏\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"You folded your poker hand.\n"
        f"🫐 Yuna returned a 25% surrender refund: **+{refund:,}** 🫐 back to your pouch.\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    if interaction:
        await interaction.edit_original_response(content=res, view=view)
    else:
        await _safe_send_reply(message, res)


# ─── CASINO: DICE ROLLING & CRAPS (2d6, PROBABILITIES & ABSURDITIES) ──────────

DICE_FACES = {
    1: "⚀",
    2: "⚁",
    3: "⚂",
    4: "⚃",
    5: "⚄",
    6: "⚅"
}

ABSURD_DICE_EVENTS = [
    {
        "text": "🌪️ **MINIATURE VORTEX!** A freak micro-tornado sweeps across the felt table! The dice spin uncontrollably on their corners and settle glowing on double golden numbers: **Double Win Surge!**",
        "is_win_all": True,
        "mult": 2.0
    },
    {
        "text": "🐱 **CAT ON THE TABLE!** Yuna's mischievous black cat swats playfully at the rolling dice! One die ends up inside your pocket! Yuna chuckles: *\"Well, table foul! Take your berries back plus a little snack fee!\"* **Bet Refunded + 50 🫐 compensation!**",
        "refund": True,
        "bonus": 50
    },
    {
        "text": "✨ **COSMIC COLLISION!** The dice hit each other mid-air with supersonic force, exploding into raspberry-scented sparkles! Yuna blinks in surprise: *\"Whoops! Fresh pair of dice, push round!\"* **Bet Refunded!**",
        "refund": True,
        "bonus": 0
    },
    {
        "text": "☕ **BOBA SPILL ACCIDENT!** Yuna accidentally knocks over her iced boba tea! A stray tapioca pearl deflects the tumbling dice straight onto a **Lucky 7**!",
        "force_seven": True
    }
]

async def handle_dice(message, client, args: list):
    """Handles y!dice <amount> [bet_choice] (or y!roll, y!craps, y!dicebet)."""
    author_id = str(message.author.id)
    amount = 10
    bet = None

    if len(args) == 1:
        c = args[0].replace(",", "")
        if c.isdigit() and int(c) > 0:
            amount = int(c)
        else:
            bet = c.lower()
    elif len(args) >= 2:
        c0 = args[0].replace(",", "")
        c1 = args[1].replace(",", "")
        if c0.isdigit() and int(c0) > 0:
            amount = int(c0)
            bet = c1.lower()
        elif c1.isdigit() and int(c1) > 0:
            amount = int(c1)
            bet = c0.lower()
        else:
            if c0.isdigit() and int(c0) > 0:
                amount = int(c0)
            bet = c1.lower()

    if amount <= 0:
        await _safe_send_reply(message, "- *Yuna crosses her arms* \"Wager must be at least 1 🫐!\"")
        return

    author_stats = await _get_user_stats(author_id)
    if author_stats.get("berries", 0) < amount:
        await _safe_send_reply(
            message,
            f"- *Yuna snickers* \"You need **{amount:,}** 🫐 to roll the bones! You only have **{author_stats.get('berries', 0):,}** 🫐!\""
        )
        return

    if not bet:
        view = DiceView(author_id, amount)
        prompt_text = (
            f"🎲 **YUNA'S ABSURD CASINO DICE** 🎲\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Player: {message.author.mention} | Wager: **{amount:,}** 🫐\n"
            f"Choose your roll prediction from the buttons below, or bet on any exact sum `2`–`12`!\n\n"
            f"🔴 **Low (2–6)**: pays **1:1**\n"
            f"⭐ **Lucky Seven (7)**: pays **4:1**\n"
            f"🔵 **High (8–12)**: pays **1:1**\n"
            f"🎲 **Even** / 🎯 **Odd**: pays **1:1**\n"
            f"✨ **Doubles**: pays **4:1**\n"
            f"⚔️ **Roll vs Yuna**: Highest 2d6 roll wins! (1:1)\n"
            f"🐍 **Snake Eyes [2]** / 🚂 **Boxcars [12]**: pays **30:1**!\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await _safe_send_reply(message, prompt_text, view=view)
        return

    await execute_dice_roll(message, author_id, amount, bet)


async def execute_dice_roll(message, author_id: str, amount: int, bet_choice: str, interaction: Optional[discord.Interaction] = None, view: Optional[View] = None):
    if view:
        for child in view.children:
            child.disabled = True

    s = await _get_user_stats(author_id)
    if s.get("berries", 0) < amount:
        err = f"⚠️ You no longer have **{amount:,}** 🫐!"
        if interaction:
            await interaction.edit_original_response(content=err, view=view)
        else:
            await _safe_send_reply(message, err)
        return

    # Deduct wager upfront
    await _update_user_stats(author_id, berries_delta=-amount, is_gamble=True)

    has_clover = s.get("clover_active", False)
    if has_clover:
        async with _LOCK:
            _USER_STATS[author_id]["clover_active"] = False
            _save_data_sync(_USER_STATS)

    has_loaded_die = s.get("loaded_die_active", False)
    if has_loaded_die:
        async with _LOCK:
            _USER_STATS[author_id]["loaded_die_active"] = False
            _save_data_sync(_USER_STATS)

    # Roll 2 dice
    d1 = random.randint(1, 6)
    d2 = random.randint(1, 6)
    total = d1 + d2
    is_doubles = (d1 == d2)

    if has_loaded_die:
        if total == 2:
            d1 = random.choice([3, 4, 5, 6])
            d2 = random.choice([3, 4])
            total = d1 + d2
        elif random.random() < 0.40:
            if random.random() < 0.5:
                d1 = random.choice([1, 2, 3, 4, 5, 6])
                d2 = 7 - d1
                total = 7
            else:
                d1 = random.choice([3, 4, 5, 6])
                d2 = d1
                total = d1 + d2
        is_doubles = (d1 == d2)

    # Check absurd event (~8% chance)
    absurd_event = None
    if random.random() < 0.08:
        absurd_event = random.choice(ABSURD_DICE_EVENTS)

    event_text = "🎲 *Lucky Loaded Die activated! The weighted bone flipped in your favor!*\n\n" if has_loaded_die else ""
    is_push = False
    is_win = False
    payout_mult = 1.0 # default 1:1 profit
    refund_bonus = 0
    yuna_d1, yuna_d2, yuna_total = 0, 0, 0
    clean_bet = bet_choice.lower().strip()
    bet_display = clean_bet

    if absurd_event:
        event_text = absurd_event["text"] + "\n\n"
        if absurd_event.get("refund"):
            is_push = True
            refund_bonus = absurd_event.get("bonus", 0)
        elif absurd_event.get("is_win_all"):
            is_win = True
            payout_mult = absurd_event.get("mult", 2.0)
            bet_display = "🌟 Golden Double Surge"
        elif absurd_event.get("force_seven"):
            d1, d2 = 3, 4
            total = 7
            is_doubles = False

    if not is_push and not is_win:
        # Determine outcome based on bet
        if clean_bet in ("low", "under", "lo", "l", "2-6"):
            is_win = (2 <= total <= 6)
            payout_mult = 1.0
            bet_display = "🔴 Low (2–6)"
        elif clean_bet in ("high", "over", "hi", "h", "8-12"):
            is_win = (8 <= total <= 12)
            payout_mult = 1.0
            bet_display = "🔵 High (8–12)"
        elif clean_bet in ("seven", "7", "mid", "lucky7"):
            is_win = (total == 7)
            payout_mult = 4.0 # 4:1 payout (5x return)
            bet_display = "⭐ Lucky Seven (7)"
        elif clean_bet in ("even", "evens"):
            is_win = (total % 2 == 0)
            payout_mult = 1.0
            bet_display = "🎲 Even"
        elif clean_bet in ("odd", "odds"):
            is_win = (total % 2 == 1)
            payout_mult = 1.0
            bet_display = "🎯 Odd"
        elif clean_bet in ("doubles", "double", "pair", "pairs"):
            is_win = is_doubles
            payout_mult = 4.0 # 4:1 payout (5x return)
            bet_display = "✨ Doubles"
        elif clean_bet in ("vs", "yuna", "duel"):
            bet_display = "⚔️ Roll vs Yuna"
            yuna_d1 = random.randint(1, 6)
            yuna_d2 = random.randint(1, 6)
            yuna_total = yuna_d1 + yuna_d2
            if total > yuna_total:
                is_win = True
                payout_mult = 1.0
            elif total == yuna_total:
                is_push = True
            else:
                is_win = False
        elif clean_bet.isdigit() and 2 <= int(clean_bet) <= 12:
            target_num = int(clean_bet)
            is_win = (total == target_num)
            bet_display = f"🎯 Exact [{target_num}]"
            # Standard exact number odds
            if target_num in (2, 12):
                payout_mult = 30.0
            elif target_num in (3, 11):
                payout_mult = 15.0
            elif target_num in (4, 10):
                payout_mult = 10.0
            elif target_num in (5, 9):
                payout_mult = 7.0
            elif target_num in (6, 8):
                payout_mult = 5.0
            elif target_num == 7:
                payout_mult = 4.0
        else:
            # Default to High/Low comparison
            is_win = (total >= 7)
            payout_mult = 1.0
            bet_display = f"🎲 Roll [{clean_bet}]"

        # Lucky Clover intervention on loss
        if not is_win and not is_push and has_clover:
            if clean_bet in ("vs", "yuna", "duel"):
                yuna_total = max(2, total - 1)
                is_win = True
            else:
                is_win = True
            event_text += "🍀 *Your Lucky Clover fluttered from your pocket! A miraculous gust altered the roll in your favor!*\n\n"

    d1_icon = DICE_FACES.get(d1, "🎲")
    d2_icon = DICE_FACES.get(d2, "🎲")
    dice_line = f"**{d1_icon} {d2_icon}** ➔ Total: **{total}**"
    if is_doubles:
        dice_line += " *(✨ Doubles!)*"

    if clean_bet in ("vs", "yuna", "duel") and yuna_total > 0:
        yd1_icon = DICE_FACES.get(yuna_d1, "🎲")
        yd2_icon = DICE_FACES.get(yuna_d2, "🎲")
        dice_line += f"\n👩 Yuna's Roll: **{yd1_icon} {yd2_icon}** ➔ Total: **{yuna_total}**"

    bonus_str = ""
    profit = 0
    bonus_amt = 0
    if is_win:
        profit = int(amount * payout_mult)
        await record_gamble_win(author_id)
        bonus_amt, bonus_tags = await get_gamble_win_bonuses(author_id, profit, game="dice")
        total_payout = amount + profit + bonus_amt
        await _update_user_stats(author_id, berries_delta=total_payout, is_gamble=True)

        if bonus_tags:
            bonus_str = f" {bonus_tags}"

        outcome_title = "🎉 YOU WON!"
        outcome_color = 0x22C55E # Green
        result_desc = (
            f"{event_text}"
            f"🎲 **Your Roll:** {dice_line}\n"
            f"🎯 **Bet:** `{bet_display}`\n"
            f"💰 **Profit:** `+{profit:,}` 🫐 *(x{payout_mult:g} payout)*{bonus_str}\n"
            f"🫐 **Total Return:** `+{total_payout:,}` 🫐"
        )
    elif is_push:
        refund_amt = amount + refund_bonus
        await _update_user_stats(author_id, berries_delta=refund_amt, is_gamble=True)
        outcome_title = "🤝 PUSH / TIE!"
        outcome_color = 0x3B82F6 # Blue
        result_desc = (
            f"{event_text}"
            f"🎲 **Your Roll:** {dice_line}\n"
            f"🎯 **Bet:** `{bet_display}`\n"
            f"🔄 **Wager Refunded:** `+{amount:,}` 🫐" + (f" *(+{refund_bonus} bonus)*" if refund_bonus > 0 else "")
        )
    else:
        # Loss: amount already deducted upfront
        await record_gamble_loss(author_id)
        await _update_user_stats(author_id, berries_delta=0, is_gamble=True)
        outcome_title = "💀 YOU LOST!"
        outcome_color = 0xEF4444 # Red
        result_desc = (
            f"{event_text}"
            f"🎲 **Your Roll:** {dice_line}\n"
            f"🎯 **Bet:** `{bet_display}`\n"
            f"💸 **Lost:** `-{amount:,}` 🫐"
        )

    # Update dice stats in _USER_STATS
    async with _LOCK:
        u = _USER_STATS[author_id]
        u["dice_games_played"] = u.get("dice_games_played", 0) + 1
        if is_win:
            u["dice_games_won"] = u.get("dice_games_won", 0) + 1
            win_profit = profit + bonus_amt
            if win_profit > u.get("dice_max_win", 0):
                u["dice_max_win"] = win_profit
            if clean_bet in ("seven", "7", "mid", "lucky7") and total == 7:
                u["dice_seven_wins"] = u.get("dice_seven_wins", 0) + 1
        if total == 2 and is_doubles:
            u["dice_snake_eyes_count"] = u.get("dice_snake_eyes_count", 0) + 1
        if total == 12 and is_doubles:
            u["dice_boxcars_count"] = u.get("dice_boxcars_count", 0) + 1
        _save_data_sync(_USER_STATS)

    await record_task_progress(author_id, "gamble")
    unlocked = await check_and_award_achievements(author_id)
    banner = format_achievement_banner(unlocked)

    fresh_s = await _get_user_stats(author_id)
    sin_warn = get_sin_warning_banner(fresh_s)

    embed = discord.Embed(
        title=f"{outcome_title} — Yuna's Absurd Dice Table",
        description=f"{result_desc}\n\n👛 **Current Balance:** `{fresh_s.get('berries', 0):,}` 🫐{sin_warn}{banner}",
        color=outcome_color
    )
    embed.set_footer(text="Yuna's Casino • y!dice <amt> [low/seven/high/even/odd/doubles/vs/2-12]")

    if interaction:
        await interaction.edit_original_response(content=None, embed=embed, view=view)
    else:
        await _safe_send_reply(message, embed=embed)


# ─── CASINO: MINES GAME ──────────────────────────────────────────────────────

async def handle_mines(message, client, args: list):
    """Handles y!mines <amount> [mines_count] (or y!mine, y!minesweeper)."""
    author_id = str(message.author.id)

    if author_id in _ACTIVE_MINES_GAMES:
        await _safe_send_reply(
            message,
            "⚠️ You already have an active Mines game running! Pick a tile or click **Cash Out** below your grid!"
        )
        return

    amount = 10
    mines_count = 3

    digits = []
    for a in args:
        cleaned = a.replace(",", "")
        if cleaned.isdigit():
            digits.append(int(cleaned))

    if len(digits) >= 2:
        amount = digits[0]
        mines_count = digits[1]
    elif len(digits) == 1:
        amount = digits[0]

    if amount <= 0:
        await _safe_send_reply(message, "- *Yuna crosses her arms* \"Wager must be at least 1 🫐!\"")
        return

    if mines_count < 1 or mines_count > 23:
        await _safe_send_reply(
            message,
            "- *Yuna scoffs* \"Number of mines must be between **1** and **23** (on a 24-tile minefield)! Default is 3.\""
        )
        return

    author_stats = await _get_user_stats(author_id)
    if author_stats.get("berries", 0) < amount:
        await _safe_send_reply(
            message,
            f"- *Yuna snickers* \"You only have **{author_stats.get('berries', 0):,}** 🫐! You can't afford a **{amount:,}** 🫐 mines run!\""
        )
        return

    # Deduct bet upfront
    await _update_user_stats(author_id, berries_delta=-amount, is_gamble=True)

    # Karmic Absurd Death Check
    _, eff_s = get_effective_morality(author_stats)
    if eff_s > 0:
        death_chance = min(0.15, 0.02 + eff_s * 0.004)
        if random.random() < death_chance:
            death_event = random.choice(ABSURD_SIN_DEATHS)
            async with _LOCK:
                _USER_STATS[author_id]["karmic_deaths"] = _USER_STATS[author_id].get("karmic_deaths", 0) + 1
                _save_data_sync(_USER_STATS)
            await record_gamble_loss(author_id)
            unlocked = await check_and_award_achievements(author_id)
            banner = format_achievement_banner(unlocked)
            desc = (
                f"💀 **ABSURD KARMIC CATASTROPHE!** 💀\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{death_event}\n\n"
                f"🔥 *Your heavy Sin ({eff_s}/30 ❤️‍🔥) blew up your minefield before you could take a step!*\n"
                f"Wager forfeited: **-{amount:,}** 🫐\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━{banner}"
            )
            await _safe_send_reply(message, desc)
            return

    # Place mines
    mine_positions = set(random.sample(range(24), mines_count))

    game_state = {
        "author_id": author_id,
        "author_mention": message.author.mention,
        "channel_id": message.channel.id,
        "bet": amount,
        "mines_count": mines_count,
        "mines": list(mine_positions),
        "revealed": [],
        "finished": False,
        "exploded_tile": None,
        "message": None,
        "view": None,
        "last_active": time.time()
    }
    _ACTIVE_MINES_GAMES[author_id] = game_state

    async with _LOCK:
        _USER_STATS[author_id]["mines_played"] = _USER_STATS[author_id].get("mines_played", 0) + 1
        _save_data_sync(_USER_STATS)

    view = MinesView(author_id, game_state)
    game_state["view"] = view
    desc = (
        f"💣 **Yuna's High-Stakes Minefield** 💣\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Player: {message.author.mention} | Wager: **{amount:,}** 🫐\n"
        f"Grid: **24 Tiles** | Hidden Mines: **{mines_count} 💣** | Safe Gems: **{24 - mines_count} 💎**\n\n"
        f"💎 Gems Uncovered: **0/{24 - mines_count}**\n"
        f"📈 Current Multiplier: **1.00x** *(Pot: {amount:,} 🫐)*\n"
        f"🔮 Next Tile Multiplier: **{get_mines_multiplier(mines_count, 1):.2f}x**\n\n"
        f"*(Click tiles below to reveal gems! Click **💰 Cash Out** anytime to secure profits.)*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    sent_msg = await _safe_send_reply(message, desc, view=view)
    game_state["message"] = sent_msg


async def process_mines_click(game_state: dict, tile_idx: int, interaction: Optional[discord.Interaction] = None, view: Optional[View] = None):
    author_id = game_state["author_id"]
    if game_state.get("finished"):
        return

    game_state["last_active"] = time.time()
    refresh_view_timeout(view, 600.0)

    if tile_idx in game_state.get("revealed", []):
        return

    bet = game_state["bet"]
    mines = set(game_state["mines"])
    revealed = game_state["revealed"]
    mines_count = game_state["mines_count"]
    total_safe = 24 - mines_count

    if tile_idx in mines:
        # BOOM! Explosion!
        game_state["finished"] = True
        game_state["exploded_tile"] = tile_idx
        _ACTIVE_MINES_GAMES.pop(author_id, None)

        await record_gamble_loss(author_id)

        if view:
            view.sync_state()

        unlocked = await check_and_award_achievements(author_id)
        banner = format_achievement_banner(unlocked)

        loss_text = (
            f"💥 **KABOOM! YOU STEPPED ON A MINE!** 💥\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Tile **#{tile_idx + 1}** was rigged with explosives! Your run has ended!\n\n"
            f"💎 Gems Found: `{len(revealed)}/{total_safe}`\n"
            f"💣 Total Mines: `{mines_count}`\n"
            f"💸 Lost Wager: **-{bet:,}** 🫐\n"
            f"🔥 Win Streak Reset to **0**!\n\n"
            f"*Yuna cackles:* \"Greed strikes again! The minefield claims another soul!\"\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━{banner}"
        )
        if interaction:
            await interaction.edit_original_response(content=loss_text, view=view)
        elif game_state.get("message"):
            await game_state["message"].edit(content=loss_text, view=view)
        await record_task_progress(author_id, "gamble")
        return

    # Safe gem uncovered!
    revealed.append(tile_idx)
    k = len(revealed)
    mult = get_mines_multiplier(mines_count, k)
    pot = int(bet * mult)

    # Check for all safe tiles found!
    if k == total_safe:
        # FULL BOARD CLEAR JACKPOT!
        game_state["finished"] = True
        _ACTIVE_MINES_GAMES.pop(author_id, None)

        profit = pot - bet
        await record_gamble_win(author_id)
        bonus, bonus_txt = await get_gamble_win_bonuses(author_id, profit, game="mines")
        total_payout = pot + bonus

        await _update_user_stats(author_id, berries_delta=total_payout, is_gamble=True)

        async with _LOCK:
            u = _USER_STATS[author_id]
            u["mines_won"] = u.get("mines_won", 0) + 1
            if total_payout > u.get("mines_max_win", 0):
                u["mines_max_win"] = total_payout
            _save_data_sync(_USER_STATS)

        if view:
            view.sync_state()

        unlocked = await check_and_award_achievements(author_id)
        banner = format_achievement_banner(unlocked)

        jackpot_text = (
            f"💎👑 **PERFECT MINEFIELD CLEAR — ALL GEMS FOUND!** 👑💎\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{game_state['author_mention']} uncovered every single safe diamond on the board!\n\n"
            f"💎 Gems Uncovered: `{k}/{total_safe}` `[PERFECT]`\n"
            f"💣 Mines Dodged: `{mines_count}`\n"
            f"⚡ Final Multiplier: **{mult:.2f}x**\n"
            f"🎉 **Total Payout: +{total_payout:,} 🫐** *(Profit: +{profit + bonus:,} 🫐)*{bonus_txt}{banner}\n\n"
            f"*Yuna bows in disbelief:* \"Incredible intuition... you conquered the entire minefield!\"\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        if interaction:
            await interaction.edit_original_response(content=jackpot_text, view=view)
        elif game_state.get("message"):
            await game_state["message"].edit(content=jackpot_text, view=view)
        await record_task_progress(author_id, "gamble")
        return

    # Normal step: update board
    next_mult = get_mines_multiplier(mines_count, k + 1)
    if view:
        view.sync_state()

    desc = (
        f"💣 **Yuna's High-Stakes Minefield** 💣\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Player: {game_state['author_mention']} | Wager: **{bet:,}** 🫐\n"
        f"Grid: **24 Tiles** | Hidden Mines: **{mines_count} 💣** | Safe Gems: **{total_safe} 💎**\n\n"
        f"💎 Gems Uncovered: **{k}/{total_safe}**\n"
        f"📈 Current Multiplier: **{mult:.2f}x** ➔ Pot: **{pot:,} 🫐**\n"
        f"🔮 Next Tile Multiplier: **{next_mult:.2f}x** *(Potential: {int(bet * next_mult):,} 🫐)*\n\n"
        f"*(Click another tile or click **💰 Cash Out** below to take your loot!)*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    if interaction:
        await interaction.edit_original_response(content=desc, view=view)
    elif game_state.get("message"):
        await game_state["message"].edit(content=desc, view=view)


async def process_mines_cashout(game_state: dict, interaction: Optional[discord.Interaction] = None, view: Optional[View] = None):
    author_id = game_state["author_id"]
    if game_state.get("finished"):
        return

    revealed = game_state.get("revealed", [])
    if not revealed:
        if interaction:
            await interaction.response.send_message("Uncover at least 1 diamond before cashing out!", ephemeral=True)
        return

    game_state["finished"] = True
    _ACTIVE_MINES_GAMES.pop(author_id, None)

    bet = game_state["bet"]
    mines_count = game_state["mines_count"]
    k = len(revealed)
    mult = get_mines_multiplier(mines_count, k)
    pot = int(bet * mult)
    profit = pot - bet

    await record_gamble_win(author_id)
    bonus, bonus_txt = await get_gamble_win_bonuses(author_id, profit, game="mines")
    total_payout = pot + bonus

    await _update_user_stats(author_id, berries_delta=total_payout, is_gamble=True)

    async with _LOCK:
        u = _USER_STATS[author_id]
        u["mines_won"] = u.get("mines_won", 0) + 1
        if total_payout > u.get("mines_max_win", 0):
            u["mines_max_win"] = total_payout
        _save_data_sync(_USER_STATS)

    if view:
        view.sync_state()

    unlocked = await check_and_award_achievements(author_id)
    banner = format_achievement_banner(unlocked)

    cashout_text = (
        f"💰 **MINES CASHOUT — SECURED THE LOOT!** 💰\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{game_state['author_mention']} stepped out of the minefield with their pockets full!\n\n"
        f"💎 Gems Collected: `{k}/{24 - mines_count}`\n"
        f"💣 Mines Avoided: `{mines_count}`\n"
        f"📈 Cashout Multiplier: **{mult:.2f}x**\n"
        f"🎉 **Total Payout: +{total_payout:,} 🫐** *(Profit: +{profit + bonus:,} 🫐)*{bonus_txt}{banner}\n\n"
        f"*Yuna nods in respect:* \"Smart gambler... know when to walk away before the blast!\"\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    if interaction:
        await interaction.edit_original_response(content=cashout_text, view=view)
    elif game_state.get("message"):
        await game_state["message"].edit(content=cashout_text, view=view)
    await record_task_progress(author_id, "gamble")


async def handle_mines_cashout(message, client, args: list):
    author_id = str(message.author.id)
    if author_id not in _ACTIVE_MINES_GAMES:
        await _safe_send_reply(message, "You don't have an active Mines game to cash out!")
        return
    await process_mines_cashout(_ACTIVE_MINES_GAMES[author_id], view=_ACTIVE_MINES_GAMES[author_id].get("view"))


# ─── CASINO: WORDLE GAMBLE SYSTEM ───────────────────────────────────────────

async def handle_wordle(message, client, args: list):
    """Handles y!wordle <amount> (or y!word). Progressive Wordle Gamble across 5 escalating stages!"""
    author_id = str(message.author.id)

    if author_id in _ACTIVE_WORDLE_GAMES:
        await _safe_send_reply(
            message,
            "⚠️ You already have an active Wordle Gamble run! Guess via the button `[✏️ Guess Word]`, type `y!guess <word>`, or click `[💰 Cash Out]`!"
        )
        return

    amount = 20
    if args:
        cleaned = args[0].replace(",", "")
        if cleaned.isdigit():
            amount = int(cleaned)

    if amount <= 0:
        await _safe_send_reply(message, "- *Yuna crosses her arms* \"Wager must be at least 1 🫐!\"")
        return

    author_stats = await _get_user_stats(author_id)
    if author_stats.get("berries", 0) < amount:
        await _safe_send_reply(
            message,
            f"- *Yuna scoffs* \"You only have **{author_stats.get('berries', 0):,}** 🫐! You can't afford a **{amount:,}** 🫐 Wordle run!\""
        )
        return

    # Deduct wager upfront
    await _update_user_stats(author_id, berries_delta=-amount, is_gamble=True)

    # Pick word for Stage 1 (4 letters, 6 guesses, 1.8x payout)
    stage = 1
    spec = WORDLE_STAGE_SPECS[1]
    word = random.choice(WORDLE_WORDS[4]).upper()

    game_state = {
        "author_id": author_id,
        "author_mention": message.author.mention,
        "channel_id": message.channel.id,
        "bet": amount,
        "stage": stage,
        "target_word": word,
        "word_length": spec["len"],
        "max_guesses": spec["max_guesses"],
        "guesses": [],
        "status": "guessing",
        "finished": False,
        "used_letters": {"correct": set(), "present": set(), "absent": set()},
        "message": None,
        "view": None,
        "last_active": time.time()
    }
    _ACTIVE_WORDLE_GAMES[author_id] = game_state

    async with _LOCK:
        _USER_STATS[author_id]["wordle_played"] = _USER_STATS[author_id].get("wordle_played", 0) + 1
        _save_data_sync(_USER_STATS)

    view = WordleView(author_id, game_state)
    game_state["view"] = view
    desc = render_wordle_embed_desc(game_state)
    sent_msg = await _safe_send_reply(message, desc, view=view)
    game_state["message"] = sent_msg


async def process_wordle_guess(game_state: dict, guess_word: str, interaction: Optional[discord.Interaction] = None, view: Optional[View] = None):
    author_id = game_state["author_id"]
    if game_state.get("finished") or game_state.get("status") != "guessing":
        return

    game_state["last_active"] = time.time()
    refresh_view_timeout(view, 600.0)

    word_len = game_state["word_length"]
    cleaned_guess = "".join(c for c in guess_word.upper() if c.isalpha())
    if len(cleaned_guess) != word_len:
        if interaction:
            await interaction.followup.send(f"⚠️ Guess must be exactly **{word_len}** letters long! You gave: `{guess_word}`", ephemeral=True)
        elif game_state.get("message"):
            await game_state["message"].channel.send(f"<@{author_id}> ⚠️ Guess must be exactly **{word_len}** letters long!", delete_after=5)
        return

    target = game_state["target_word"]
    clues = evaluate_wordle_guess(target, cleaned_guess)
    game_state["guesses"].append({"word": cleaned_guess, "clues": clues})

    for idx, char in enumerate(cleaned_guess):
        c_mark = clues[idx]
        if c_mark == "🟩":
            game_state["used_letters"]["correct"].add(char)
        elif c_mark == "🟨":
            game_state["used_letters"]["present"].add(char)
        else:
            game_state["used_letters"]["absent"].add(char)

    bet = game_state["bet"]
    stage = game_state["stage"]
    max_g = game_state["max_guesses"]

    if cleaned_guess == target:
        async with _LOCK:
            u = _USER_STATS[author_id]
            u["wordle_stages_cleared"] = u.get("wordle_stages_cleared", 0) + 1
            if stage > u.get("wordle_max_stage", 0):
                u["wordle_max_stage"] = stage
            _save_data_sync(_USER_STATS)

        if stage == 5:
            # Complete grand slam victory!
            game_state["status"] = "run_won"
            game_state["finished"] = True
            _ACTIVE_WORDLE_GAMES.pop(author_id, None)

            mult = WORDLE_STAGE_SPECS[5]["mult"]
            pot = int(bet * mult)
            profit = pot - bet

            await record_gamble_win(author_id)
            bonus, bonus_txt = await get_gamble_win_bonuses(author_id, profit, game="wordle")
            total_payout = pot + bonus

            await _update_user_stats(author_id, berries_delta=total_payout, virtue_delta=2, is_gamble=True)

            async with _LOCK:
                u = _USER_STATS[author_id]
                u["wordle_won"] = u.get("wordle_won", 0) + 1
                if total_payout > u.get("wordle_max_win", 0):
                    u["wordle_max_win"] = total_payout
                _save_data_sync(_USER_STATS)

            if view:
                for child in view.children:
                    child.disabled = True

            unlocked = await check_and_award_achievements(author_id)
            banner = format_achievement_banner(unlocked)

            win_desc = (
                f"👑⚡ **ASCENDED GOD OF WORDS — ALL 5 STAGES CONQUERED!** ⚡👑\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{game_state['author_mention']} cracked the Grand 7-Letter Anagram **{target}** on Stage 5!\n\n"
                f"🌟 Wordle Stages Completed: `5/5` `[GRAND SLAM]`\n"
                f"📈 Final Multiplier: **{mult:.1f}x**\n"
                f"💖 Divine Enlightenment: **+2 💖 Virtue**\n"
                f"🎉 **Total Payout: +{total_payout:,} 🫐** *(Profit: +{profit + bonus:,} 🫐)*{bonus_txt}{banner}\n\n"
                f"*Yuna is speechless:* \"You solved every cipher from Novice to Ascended God... A true mortal legend!\"\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            if interaction:
                await interaction.edit_original_response(content=win_desc, view=view)
            elif game_state.get("message"):
                await game_state["message"].edit(content=win_desc, view=view)
            await record_task_progress(author_id, "gamble")
            return

        game_state["status"] = "stage_cleared"
        if view:
            view.sync_buttons()

        desc = render_wordle_embed_desc(game_state)
        if interaction:
            await interaction.edit_original_response(content=desc, view=view)
        elif game_state.get("message"):
            await game_state["message"].edit(content=desc, view=view)
        return

    if len(game_state["guesses"]) >= max_g:
        game_state["status"] = "lost"
        game_state["finished"] = True
        _ACTIVE_WORDLE_GAMES.pop(author_id, None)

        await record_gamble_loss(author_id)

        if view:
            for child in view.children:
                child.disabled = True

        unlocked = await check_and_award_achievements(author_id)
        banner = format_achievement_banner(unlocked)

        loss_desc = (
            f"💀 **WORDLE GAMBLE — RUN TERMINATED!** 💀\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"You ran out of attempts in Stage {stage} ({WORDLE_STAGE_SPECS[stage]['name']})!\n\n"
            f"🔍 The secret word was: **{target}**\n"
            f"💸 Forfeited Run Pot: **-{bet:,}** 🫐\n"
            f"🔥 Win Streak Reset to **0**!\n\n"
            f"*Yuna smiles maliciously:* \"The labyrinth swallows your berries! Better study the dictionary!\"\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━{banner}"
        )
        if interaction:
            await interaction.edit_original_response(content=loss_desc, view=view)
        elif game_state.get("message"):
            await game_state["message"].edit(content=loss_desc, view=view)
        await record_task_progress(author_id, "gamble")
        return

    desc = render_wordle_embed_desc(game_state)
    if interaction:
        await interaction.edit_original_response(content=desc, view=view)
    elif game_state.get("message"):
        await game_state["message"].edit(content=desc, view=view)


async def process_wordle_advance(game_state: dict, interaction: Optional[discord.Interaction] = None, view: Optional[View] = None):
    author_id = game_state["author_id"]
    if game_state.get("finished") or game_state.get("status") != "stage_cleared":
        return

    next_stage = game_state["stage"] + 1
    if next_stage > 5:
        return

    next_spec = WORDLE_STAGE_SPECS[next_stage]

    if next_stage == 2:
        new_word = random.choice(WORDLE_WORDS[5]).upper()
    elif next_stage == 3:
        new_word = random.choice([w for w in WORDLE_WORDS[6] if len(w) == 6]).upper()
    elif next_stage == 4:
        new_word = random.choice([w for w in WORDLE_WORDS["tricky_6"] if len(w) == 6]).upper()
    elif next_stage == 5:
        new_word = random.choice([w for w in WORDLE_WORDS[7] if len(w) == 7]).upper()
    else:
        new_word = "BERRY"

    game_state["stage"] = next_stage
    game_state["target_word"] = new_word
    game_state["word_length"] = next_spec["len"]
    game_state["max_guesses"] = next_spec["max_guesses"]
    game_state["guesses"] = []
    game_state["status"] = "guessing"
    game_state["used_letters"] = {"correct": set(), "present": set(), "absent": set()}

    game_state["last_active"] = time.time()
    fresh_view = WordleView(author_id, game_state)
    game_state["view"] = fresh_view
    view = fresh_view

    desc = render_wordle_embed_desc(game_state)

    # 1. Clean up and disable buttons on the previous stage message
    old_msg = game_state.get("message")
    if interaction and getattr(interaction, "message", None):
        try:
            await interaction.edit_original_response(view=None)
        except Exception:
            try:
                await interaction.message.edit(view=None)
            except Exception:
                pass
    elif old_msg:
        try:
            await old_msg.edit(view=None)
        except Exception:
            pass

    # 2. Resend next stage as a brand new message at the bottom of the chat channel
    channel = None
    if interaction and getattr(interaction, "channel", None):
        channel = interaction.channel
    elif old_msg and getattr(old_msg, "channel", None):
        channel = old_msg.channel

    sent_msg = None
    if channel:
        try:
            sent_msg = await channel.send(content=desc, view=fresh_view)
        except Exception:
            pass

    if not sent_msg and interaction:
        try:
            sent_msg = await interaction.followup.send(content=desc, view=fresh_view)
        except Exception:
            pass

    if not sent_msg and old_msg:
        try:
            sent_msg = await old_msg.edit(content=desc, view=fresh_view)
        except Exception:
            pass

    if sent_msg:
        game_state["message"] = sent_msg



async def process_wordle_cashout(game_state: dict, interaction: Optional[discord.Interaction] = None, view: Optional[View] = None):
    author_id = game_state["author_id"]
    if game_state.get("finished"):
        return

    stage = game_state["stage"]
    if game_state.get("status") != "stage_cleared":
        if interaction:
            await interaction.response.send_message("You must solve the current stage before cashing out!", ephemeral=True)
        return

    game_state["finished"] = True
    _ACTIVE_WORDLE_GAMES.pop(author_id, None)

    bet = game_state["bet"]
    spec = WORDLE_STAGE_SPECS[stage]
    mult = spec["mult"]
    pot = int(bet * mult)
    profit = pot - bet

    await record_gamble_win(author_id)
    bonus, bonus_txt = await get_gamble_win_bonuses(author_id, profit, game="wordle")
    total_payout = pot + bonus

    await _update_user_stats(author_id, berries_delta=total_payout, is_gamble=True)

    async with _LOCK:
        u = _USER_STATS[author_id]
        u["wordle_won"] = u.get("wordle_won", 0) + 1
        if total_payout > u.get("wordle_max_win", 0):
            u["wordle_max_win"] = total_payout
        _save_data_sync(_USER_STATS)

    if view:
        for child in view.children:
            child.disabled = True

    unlocked = await check_and_award_achievements(author_id)
    banner = format_achievement_banner(unlocked)

    cashout_text = (
        f"💰 **WORDLE CASHOUT — PRODIGY OF LETTERS!** 💰\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{game_state['author_mention']} wisely banked their winnings after clearing Stage {stage}!\n\n"
        f"📚 Stage Conquered: `Stage {stage} ({spec['name']})`\n"
        f"📈 Run Multiplier: **{mult:.1f}x**\n"
        f"🎉 **Total Payout: +{total_payout:,} 🫐** *(Profit: +{profit + bonus:,} 🫐)*{bonus_txt}{banner}\n\n"
        f"*Yuna smiles warmly:* \"A sharp mind and a fuller pouch! Well played.\"\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    if interaction:
        await interaction.edit_original_response(content=cashout_text, view=view)
    elif game_state.get("message"):
        await game_state["message"].edit(content=cashout_text, view=view)
    await record_task_progress(author_id, "gamble")


async def process_wordle_give_up(game_state: dict, interaction: Optional[discord.Interaction] = None, view: Optional[View] = None):
    author_id = game_state["author_id"]
    if game_state.get("finished"):
        return

    game_state["finished"] = True
    _ACTIVE_WORDLE_GAMES.pop(author_id, None)

    bet = game_state["bet"]
    await record_gamble_loss(author_id)

    if view:
        for child in view.children:
            child.disabled = True

    desc = (
        f"🏳️ **WORDLE FORFEIT!** 🏳️\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"You surrendered the run! The secret word was: **{game_state['target_word']}**\n"
        f"Wager forfeited: **-{bet:,}** 🫐 | Win streak reset to **0**!\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    if interaction:
        await interaction.edit_original_response(content=desc, view=view)
    elif game_state.get("message"):
        await game_state["message"].edit(content=desc, view=view)


async def handle_wordle_guess(message, client, args: list):
    author_id = str(message.author.id)
    if author_id not in _ACTIVE_WORDLE_GAMES:
        await _safe_send_reply(message, "You don't have an active Wordle Gamble game! Start one with `y!wordle <amount>`!")
        return
    game = _ACTIVE_WORDLE_GAMES[author_id]
    if not args:
        await _safe_send_reply(message, f"Please specify your guess! Usage: `y!guess <{game['word_length']}-letter word>`")
        return
    guess_word = args[0]
    await process_wordle_guess(game, guess_word, view=game.get("view"))


async def handle_wordle_cashout(message, client, args: list):
    author_id = str(message.author.id)
    if author_id not in _ACTIVE_WORDLE_GAMES:
        await _safe_send_reply(message, "You don't have an active Wordle Gamble game to cash out!")
        return
    await process_wordle_cashout(_ACTIVE_WORDLE_GAMES[author_id], view=_ACTIVE_WORDLE_GAMES[author_id].get("view"))


async def handle_wordle_next(message, client, args: list):
    author_id = str(message.author.id)
    if author_id not in _ACTIVE_WORDLE_GAMES:
        await _safe_send_reply(message, "You don't have an active Wordle Gamble game to advance!")
        return
    await process_wordle_advance(_ACTIVE_WORDLE_GAMES[author_id], view=_ACTIVE_WORDLE_GAMES[author_id].get("view"))


# ─── CASINO: WIN STREAK SYSTEM ──────────────────────────────────────────────

async def handle_streak(message, client, args: list):
    """Handles y!streak [@user] (or y!winstreak, y!streaks). Displays current gamble win streak, all-time record, win rate, and bonus tier."""
    target_id = str(message.author.id)
    target_name = getattr(message.author, "display_name", message.author.name)
    if message.mentions:
        target_id = str(message.mentions[0].id)
        target_name = getattr(message.mentions[0], "display_name", message.mentions[0].name)
    elif args and args[0].isdigit():
        target_id = args[0]
        target_name = f"User {target_id}"

    stats = await _get_user_stats(target_id)
    streak = stats.get("gamble_win_streak", 0)
    max_streak = stats.get("max_win_streak", 0)
    wins = stats.get("total_gamble_wins", 0)
    losses = stats.get("total_gamble_losses", 0)
    total = wins + losses
    win_rate = f"{(wins / total * 100):.1f}%" if total > 0 else "0.0%"

    current_bonus_pct = min(50, (streak - 1) * 5) if streak >= 2 else 0

    milestones = [
        (3, "+100 🫐 & +10% Profit Bonus"),
        (5, "+300 🫐 & +20% Profit Bonus"),
        (7, "+600 🫐 & +30% Profit Bonus"),
        (10, "+1,500 🫐 & +45% Profit Bonus"),
        (15, "+3,000 🫐 & +50% Max Profit Bonus"),
        (20, "+7,500 🫐 & Grand Master Status")
    ]

    embed = discord.Embed(
        title=f"🔥 {target_name}'s Gambling Win Streak",
        color=0xFF6B00 if streak >= 3 else (0x22C55E if streak > 0 else 0x6B7280)
    )
    embed.description = (
        f"Conquer the casino tables and rack up consecutive wins to unlock increasing "
        f"**Win Streak Profit Bonuses** (up to **+50%**) and **Milestone Berry Windfalls**!\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔥 **Current Win Streak:** `{streak}` consecutive wins\n"
        f"🏆 **All-Time Peak Record:** `{max_streak}` consecutive wins\n"
        f"⚡ **Active Streak Multiplier:** `+{current_bonus_pct}%` on all gamble profits\n"
        f"📊 **Casino Record:** `{wins:,}` Wins / `{losses:,}` Losses `({win_rate} Win Rate)`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    ms_lines = []
    for ms_req, ms_reward in milestones:
        mark = "✅" if streak >= ms_req else ("⏳" if streak == ms_req - 1 else "🔒")
        ms_lines.append(f"{mark} **Streak #{ms_req}:** {ms_reward}")

    embed.add_field(
        name="🎯 Streak Milestones & Perks",
        value="\n".join(ms_lines),
        inline=False
    )
    embed.set_footer(text="Any casino loss resets your current streak to 0! Ties & pushes preserve it.")
    await _safe_send_reply(message, embed=embed)



# ─── SOCIAL: AI TRUTH & DARE SYSTEM & EVALUATION ─────────────────────────────

async def evaluate_dare_proof(
    target_id: str,
    dare_info: dict,
    proof: str,
    channel_id: int,
    guild: Optional[discord.Guild] = None,
    user_name: str = ""
) -> Tuple[bool, str]:
    """Evaluates proof/answer using AI (or hilarious fallback logic) and returns (is_pass, verdict_explanation)."""
    dare_prompt = dare_info.get("prompt") or dare_info.get("dare", "")
    c_type = dare_info.get("type", "dare")

    ai_judgment = None
    if _AI_CALLER:
        if c_type == "truth":
            eval_prompt = (
                f"You are Yuna, a cheeky, playful, and funny anime Discord bot arbitrator evaluating a TRUTH answer.\n"
                f"The question assigned to the user was:\n"
                f"\"{dare_prompt}\"\n\n"
                f"Here is the user's submitted answer:\n"
                f"\"{proof}\"\n\n"
                f"Task:\n"
                f"Determine if the user gave a genuine, funny, or real answer, or if they gave a lazy, cop-out response (e.g. 'idk', 'pass', 'nothing', 'no').\n"
                f"Rules:\n"
                f"1. Start your verdict STRICTLY with either [PASS] or [FAIL].\n"
                f"2. Follow with 1 to 2 funny, sassy sentences in your anime persona as Yuna declaring your verdict and roasting or praising them."
            )
        else:
            eval_prompt = (
                f"You are Yuna, a cheeky, playful, and funny anime Discord bot arbitrator evaluating a DARE attempt.\n"
                f"The dare assigned to the user was:\n"
                f"\"{dare_prompt}\"\n\n"
                f"Here is the user's submitted proof or attempt:\n"
                f"\"{proof}\"\n\n"
                f"Task:\n"
                f"Determine if the user reasonably, creatively, or hilariously fulfilled the spirit of the dare, or if they are chickening out, lying, or being lazy.\n"
                f"Rules:\n"
                f"1. Start your verdict STRICTLY with either [PASS] or [FAIL].\n"
                f"2. Follow with 1 to 2 funny, sassy sentences in your anime persona as Yuna declaring your verdict and roasting or praising them."
            )
        try:
            reply, err = await _AI_CALLER(
                channel_id=channel_id,
                prompt=eval_prompt,
                user_id=int(target_id) if target_id.isdigit() else 0,
                user_name=user_name,
                guild=guild,
                system_msg_override="You are Yuna, a cheeky and playful anime bot judge evaluating truth or dare completions."
            )
            if not err and reply and len(reply.strip()) > 3:
                ai_judgment = reply.strip()
        except Exception as _e:
            print(f"[YUNA DARE AI ERROR] {_e}")

    # Robust fallback judgment if AI is unavailable or offline
    if not ai_judgment:
        clean_p = proof.strip().lower()
        is_copout = clean_p in ("idk", "no", "nothing", "pass", "done", "ok", "a", "skip", "none", "i dont know", "n/a")
        if not is_copout and (len(proof) >= 12 or "http" in clean_p or "photo" in clean_p or "attachment" in clean_p):
            ai_judgment = "[PASS] *Yuna inspects the evidence closely* 'Hmm, against all odds, this actually counts! You didn't chicken out! Take the pot!'"
        else:
            ai_judgment = "[FAIL] *Yuna hits you with an oversized squeaky hammer* 'Rejected! That low-effort cop-out does not fool me! Try harder!'"

    is_pass = "[PASS]" in ai_judgment.upper() or ai_judgment.upper().startswith("PASS")
    clean_verdict = ai_judgment.replace("[PASS]", "").replace("[FAIL]", "").strip()
    return is_pass, clean_verdict


async def process_dare_reroll(user_id: str, interaction: Optional[discord.Interaction] = None, view: Optional[View] = None, message=None):
    """Processes 1 free reroll for an active challenge."""
    _ensure_fresh_data()
    if user_id not in _ACTIVE_DARES:
        msg = "- *Yuna blinks* \"You don't have an active dare or truth to reroll!\""
        if interaction:
            await interaction.followup.send(msg, ephemeral=True)
        elif message:
            await _safe_send_reply(message, msg)
        return

    dare_info = _ACTIVE_DARES[user_id]
    if dare_info.get("is_custom", False):
        msg = "⚠️ This was a custom challenge crafted personally by your challenger! You cannot reroll a custom challenge, mortal!"
        if interaction:
            await interaction.followup.send(msg, ephemeral=True)
        elif message:
            await _safe_send_reply(message, msg)
        return

    if dare_info.get("rerolls_left", 1) <= 0:
        msg = "⚠️ *Yuna wags her finger* \"You've already used your free reroll for this challenge! No more swaps!\""
        if interaction:
            await interaction.followup.send(msg, ephemeral=True)
        elif message:
            await _safe_send_reply(message, msg)
        return

    c_type = dare_info.get("type", "dare")
    pool = TRUTHS if c_type == "truth" else DARES
    current = dare_info.get("prompt") or dare_info.get("dare", "")
    choices = [p for p in pool if p != current]
    new_prompt = random.choice(choices if choices else pool)

    dare_info["dare"] = new_prompt
    dare_info["prompt"] = new_prompt
    dare_info["rerolls_left"] = 0
    _save_data_sync()

    title = "🎲 **TRUTH REROLLED!** 🎲" if c_type == "truth" else "🎲 **DARE REROLLED!** 🎲"
    text = (
        f"{title}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<@{user_id}> spun the wheel for their 1 free reroll!\n\n"
        f"Your new assigned challenge:\n"
        f"> 📢 **\"{new_prompt}\"**\n\n"
        f"✨ When completed, submit your proof using: `y!checkdare <proof>`\n"
        f"*(Pot on the line: **{dare_info['amount'] * 2}** 🫐)*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    if view:
        for item in view.children:
            if getattr(item, "label", None) == "Reroll Prompt (1 Free)":
                item.disabled = True

    if interaction:
        try:
            await interaction.edit_original_response(content=text, view=view)
        except Exception:
            await interaction.followup.send(text)
    elif message:
        await _safe_send_reply(message, text, view=SoloDareView(user_id) if dare_info.get("challenger_id") == "yuna" else None)


async def process_dare_forfeit(user_id: str, interaction: Optional[discord.Interaction] = None, view: Optional[View] = None, message=None):
    """Processes forfeiture/surrender of an active dare."""
    _ensure_fresh_data()
    if user_id not in _ACTIVE_DARES:
        msg = "- *Yuna tilts her head* \"You don't have an active challenge to forfeit!\""
        if interaction:
            await interaction.followup.send(msg, ephemeral=True)
        elif message:
            await _safe_send_reply(message, msg)
        return

    dare_info = _ACTIVE_DARES.pop(user_id)
    _save_data_sync()

    challenger_id = dare_info["challenger_id"]
    amount = dare_info["amount"]
    c_type = dare_info.get("type", "dare")

    if view:
        for item in view.children:
            item.disabled = True

    if challenger_id != "yuna":
        pot = amount * 2
        await _update_user_stats(challenger_id, berries_delta=pot)
        text = (
            f"🏳️ **CHALLENGE FORFEITED!** 🏳️\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<@{user_id}> chickened out and surrendered!\n"
            f"<@{challenger_id}> collected the entire pot of **+{pot}** 🫐!\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
    else:
        text = (
            f"🏳️ **DARE FORFEITED!** 🏳️\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<@{user_id}> surrendered to Yuna! Your **{amount}** 🫐 deposit was fed to Yuna's berry jar!\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

    if interaction:
        try:
            await interaction.edit_original_response(content=text, view=view)
        except Exception:
            await interaction.followup.send(text)
    elif message:
        await _safe_send_reply(message, text)


async def process_pvp_dare_review(
    target_id: str,
    action: str,
    interaction: Optional[discord.Interaction] = None,
    view: Optional[View] = None,
    proof: str = ""
):
    """Handles PvP Dare review actions (approve, reject, ask_ai)."""
    _ensure_fresh_data()
    if target_id not in _ACTIVE_DARES:
        err = "- *Yuna blinks* \"This challenge is no longer active!\""
        if interaction:
            await interaction.edit_original_response(content=err, view=None)
        return

    dare_info = _ACTIVE_DARES[target_id]
    challenger_id = dare_info["challenger_id"]
    amount = dare_info["amount"]
    pot = amount * 2
    prompt = dare_info.get("prompt") or dare_info.get("dare", "")
    c_type = dare_info.get("type", "dare")

    if action == "approve":
        # Target passed and wins pot!
        _ACTIVE_DARES.pop(target_id, None)
        await _update_user_stats(target_id, berries_delta=pot, virtue_delta=2, is_gamble=True)

        async with _LOCK:
            u_stat = _USER_STATS.get(target_id, {})
            u_stat["dares_completed"] = u_stat.get("dares_completed", 0) + 1
            _save_data_sync(_USER_STATS)

        unlocked = await check_and_award_achievements(target_id)
        banner = format_achievement_banner(unlocked)

        if view:
            for item in view.children:
                item.disabled = True

        res_text = (
            f"🎉 **{c_type.upper()} OFFICIALLY APPROVED!** 🎉\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<@{challenger_id}> stamped approval on the submitted proof!\n\n"
            f"🏆 <@{target_id}> conquered the challenge and won **+{pot}** 🫐! *(+2 💖 Virtue)*{banner}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        if interaction:
            await interaction.edit_original_response(content=res_text, view=view)

    elif action == "reject":
        # Dare remains active
        _save_data_sync()
        res_text = (
            f"❌ **PROOF REJECTED BY CHALLENGER!** ❌\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<@{challenger_id}> was NOT satisfied with <@{target_id}>'s proof!\n\n"
            f"Challenge remains active:\n"
            f"> 📢 **\"{prompt}\"**\n\n"
            f"<@{target_id}>, try again with `y!checkdare <new proof>` or type `y!forfeitdare` to give up.\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        if view:
            # Leave only forfeit active
            for item in view.children:
                if getattr(item, "label", None) != "Forfeit":
                    item.disabled = True
        if interaction:
            await interaction.edit_original_response(content=res_text, view=view)

    elif action == "ask_ai":
        # Invoke Yuna AI Judge
        channel_id = interaction.channel.id if interaction and interaction.channel else 0
        guild = interaction.guild if interaction else None
        user_name = interaction.user.display_name if interaction else ""

        is_pass, verdict = await evaluate_dare_proof(
            target_id=target_id,
            dare_info=dare_info,
            proof=proof,
            channel_id=channel_id,
            guild=guild,
            user_name=user_name
        )

        if is_pass:
            _ACTIVE_DARES.pop(target_id, None)
            await _update_user_stats(target_id, berries_delta=pot, virtue_delta=2, is_gamble=True)

            async with _LOCK:
                u_stat = _USER_STATS.get(target_id, {})
                u_stat["dares_completed"] = u_stat.get("dares_completed", 0) + 1
                _save_data_sync(_USER_STATS)

            unlocked = await check_and_award_achievements(target_id)
            banner = format_achievement_banner(unlocked)

            if view:
                for item in view.children:
                    item.disabled = True

            res_text = (
                f"🤖 **YUNA AI ARBITRATOR RULING: PASSED!** 🎉\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"**Verdict:** ✅ **VALID!**\n\n"
                f"> 💬 *{verdict}*\n\n"
                f"🏆 <@{target_id}> earned Yuna's seal of approval and won **+{pot}** 🫐! *(+2 💖 Virtue)*{banner}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            if interaction:
                await interaction.edit_original_response(content=res_text, view=view)
        else:
            # AI failed it
            _save_data_sync()
            if view:
                for item in view.children:
                    if getattr(item, "label", None) != "Forfeit":
                        item.disabled = True

            res_text = (
                f"🤖 **YUNA AI ARBITRATOR RULING: REJECTED!** ❌\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"**Verdict:** 🚫 **FAILED!**\n\n"
                f"> 💬 *{verdict}*\n\n"
                f"Challenge remains active: *\"{prompt}\"*\n"
                f"<@{target_id}>, try again with `y!checkdare <proof>` or type `y!forfeitdare` to surrender.\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            if interaction:
                await interaction.edit_original_response(content=res_text, view=view)


async def handle_solo_dare(message, client, args: list):
    """Handles y!dare <amount> without mentioning another user (Solo dare from Yuna!)."""
    _ensure_fresh_data()
    author_id = str(message.author.id)
    if author_id in _ACTIVE_DARES:
        d = _ACTIVE_DARES[author_id]
        c_type = d.get("type", "dare")
        cmd_name = "checktruth" if c_type == "truth" else "checkdare"
        await _safe_send_reply(
            message,
            f"🎭 You already have an active challenge!\n"
            f"> 📢 **\"{d.get('prompt') or d.get('dare')}\"**\n"
            f"Submit your proof using `y!{cmd_name} <proof>`, type `y!rerolldare` to reroll, or `y!forfeitdare`!",
            view=SoloDareView(author_id)
        )
        return

    amount = 25
    if args:
        cleaned = args[0].replace(",", "")
        if cleaned.isdigit():
            amount = int(cleaned)

    if amount <= 0:
        await _safe_send_reply(message, "- *Yuna scoffs* \"The dare deposit must be at least 1 🫐!\"")
        return

    s = await _get_user_stats(author_id)
    if s.get("berries", 0) < amount:
        await _safe_send_reply(
            message,
            f"- *Yuna shakes her head* \"You only have **{s.get('berries', 0)}** 🫐! You need **{amount}** 🫐 to accept a dare!\""
        )
        return

    # Deduct deposit
    await _update_user_stats(author_id, berries_delta=-amount, is_gamble=True)

    dare_text = random.choice(DARES)
    _ACTIVE_DARES[author_id] = {
        "challenger_id": "yuna",
        "challenger_mention": "Yuna",
        "target_id": author_id,
        "target_mention": message.author.mention,
        "amount": amount,
        "type": "dare",
        "dare": dare_text,
        "prompt": dare_text,
        "is_custom": False,
        "rerolls_left": 1,
        "created_at": time.time(),
        "channel_id": message.channel.id
    }
    _save_data_sync()

    text = (
        f"🎭 **YUNA'S PERSONAL DARE CHALLENGE!** 🎭\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{message.author.mention}, you put up **{amount}** 🫐 on the line!\n\n"
        f"Your assigned dare from Yuna:\n"
        f"> 📢 **\"{dare_text}\"**\n\n"
        f"✨ Complete it, then type: `y!checkdare <your proof or what you said>`\n"
        f"*(Or post your proof right here and type `y!checkdare`!)*\n\n"
        f"Yuna's AI arbitrator will evaluate your submission. Win Pot: **{amount * 2}** 🫐!\n"
        f"*(Have 1 free reroll available if you dislike this dare)*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    await _safe_send_reply(message, text, view=SoloDareView(author_id))


async def handle_solo_truth(message, client, args: list):
    """Handles y!truth <amount> without mentioning another user (Solo truth question from Yuna!)."""
    _ensure_fresh_data()
    author_id = str(message.author.id)
    if author_id in _ACTIVE_DARES:
        d = _ACTIVE_DARES[author_id]
        c_type = d.get("type", "dare")
        cmd_name = "checktruth" if c_type == "truth" else "checkdare"
        await _safe_send_reply(
            message,
            f"🔮 You already have an active challenge!\n"
            f"> 📢 **\"{d.get('prompt') or d.get('dare')}\"**\n"
            f"Submit your answer using `y!{cmd_name} <answer>`, type `y!rerolldare` to reroll, or `y!forfeitdare`!",
            view=SoloDareView(author_id)
        )
        return

    amount = 25
    if args:
        cleaned = args[0].replace(",", "")
        if cleaned.isdigit():
            amount = int(cleaned)

    if amount <= 0:
        await _safe_send_reply(message, "- *Yuna scoffs* \"The truth deposit must be at least 1 🫐!\"")
        return

    s = await _get_user_stats(author_id)
    if s.get("berries", 0) < amount:
        await _safe_send_reply(
            message,
            f"- *Yuna shakes her head* \"You only have **{s.get('berries', 0)}** 🫐! You need **{amount}** 🫐 to accept a truth challenge!\""
        )
        return

    # Deduct deposit
    await _update_user_stats(author_id, berries_delta=-amount, is_gamble=True)

    truth_text = random.choice(TRUTHS)
    _ACTIVE_DARES[author_id] = {
        "challenger_id": "yuna",
        "challenger_mention": "Yuna",
        "target_id": author_id,
        "target_mention": message.author.mention,
        "amount": amount,
        "type": "truth",
        "dare": truth_text,
        "prompt": truth_text,
        "is_custom": False,
        "rerolls_left": 1,
        "created_at": time.time(),
        "channel_id": message.channel.id
    }
    _save_data_sync()

    text = (
        f"🔮 **YUNA'S PERSONAL TRUTH CHALLENGE!** 🔮\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{message.author.mention}, you put up **{amount}** 🫐 on the line!\n\n"
        f"Your assigned truth question from Yuna:\n"
        f"> 📢 **\"{truth_text}\"**\n\n"
        f"✨ Answer honestly, then type: `y!checktruth <your answer>`\n"
        f"*(Or post your response right here and type `y!checktruth`!)*\n\n"
        f"Yuna's AI arbitrator will evaluate your sincerity. Win Pot: **{amount * 2}** 🫐!\n"
        f"*(Have 1 free reroll available if you dislike this question)*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    await _safe_send_reply(message, text, view=SoloDareView(author_id))


async def handle_checkdare(message, client, args: list):
    """Handles y!checkdare / y!checktruth [proof]."""
    _ensure_fresh_data()
    author_id = str(message.author.id)

    if author_id not in _ACTIVE_DARES:
        await _safe_send_reply(
            message,
            "- *Yuna blinks* \"You don't have an active dare or truth challenge right now!\n"
            "Challenge Yuna with `y!dare <amount>` / `y!truth <amount>` or challenge a player with `y!dare @user <amount> [custom dare]`!\""
        )
        return

    dare_info = _ACTIVE_DARES[author_id]
    prompt = dare_info.get("prompt") or dare_info.get("dare", "")
    amount = dare_info["amount"]
    challenger_id = dare_info["challenger_id"]
    c_type = dare_info.get("type", "dare")
    cmd_name = "checktruth" if c_type == "truth" else "checkdare"

    # Extract proof: from args, or fallback to user's recent message in channel
    proof = " ".join(args).strip()
    if not proof:
        try:
            async for prev_msg in message.channel.history(limit=10):
                if prev_msg.author.id == message.author.id and prev_msg.id != message.id:
                    if prev_msg.content and not prev_msg.content.lower().startswith("y!"):
                        proof = prev_msg.content.strip()
                        break
                    elif prev_msg.attachments:
                        proof = f"[User attached media file: {prev_msg.attachments[0].filename}]"
                        break
        except Exception:
            pass

    if not proof:
        await _safe_send_reply(
            message,
            f"- *Yuna crosses her arms* \"You need to provide proof or an explanation!\n"
            f"Usage: `y!{cmd_name} <what you said / did>` (or post your message/photo right before typing `y!{cmd_name}`)!\""
        )
        return

    # Case A: PvP Challenge (Challenger is another player)
    if challenger_id != "yuna":
        dare_info["proof"] = proof
        _save_data_sync()

        pot = amount * 2
        review_view = PvPDareReviewView(challenger_id, author_id, dare_info, proof)
        review_text = (
            f"🎭 **{c_type.upper()} PROOF SUBMITTED FOR REVIEW!** 🎭\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"**Target:** {message.author.mention}\n"
            f"**Challenger:** <@{challenger_id}>\n"
            f"**Total Pot on the Line:** **{pot}** 🫐\n\n"
            f"**Assigned Task:**\n"
            f"> 📢 **\"{prompt}\"**\n\n"
            f"**Submitted Proof / Answer:**\n"
            f"> 💬 *\"{proof}\"*\n\n"
            f"<@{challenger_id}>, review this attempt using the buttons below!\n"
            f"*(Or either player can invoke Yuna AI for an impartial ruling)*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await _safe_send_reply(message, review_text, view=review_view)
        return

    # Case B: Solo Challenge from Yuna
    wait_msg = await _safe_send_reply(
        message,
        f"🔍 *Yuna adjusts her monocle and consults her AI judge matrix to inspect {message.author.mention}'s attempt...*"
    )

    is_pass, clean_verdict = await evaluate_dare_proof(
        target_id=author_id,
        dare_info=dare_info,
        proof=proof,
        channel_id=message.channel.id,
        guild=message.guild,
        user_name=message.author.display_name
    )

    if is_pass:
        # Success! Target wins pot and virtue
        _ACTIVE_DARES.pop(author_id, None)
        pot = amount * 2
        await _update_user_stats(author_id, berries_delta=pot, virtue_delta=2, is_gamble=True)

        async with _LOCK:
            u_stat = _USER_STATS.get(author_id, {})
            u_stat["dares_completed"] = u_stat.get("dares_completed", 0) + 1
            _save_data_sync(_USER_STATS)

        unlocked = await check_and_award_achievements(author_id)
        banner = format_achievement_banner(unlocked)

        pass_text = (
            f"🎉 **{c_type.upper()} APPROVED BY YUNA'S AI!** 🎉\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"**Verdict:** ✅ **PASSED!**\n\n"
            f"> 💬 *{clean_verdict}*\n\n"
            f"🏆 {message.author.mention} conquered the challenge and won **+{pot}** 🫐! *(+2 💖 Virtue)*{banner}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        if wait_msg:
            try:
                await wait_msg.edit(content=pass_text)
                return
            except Exception:
                pass
        await _safe_send_reply(message, pass_text)
    else:
        # Fail! Dare stays active
        fail_text = (
            f"❌ **{c_type.upper()} REJECTED BY YUNA'S AI!** ❌\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"**Verdict:** 🚫 **FAILED!**\n\n"
            f"> 💬 *{clean_verdict}*\n\n"
            f"Your challenge remains active: *'{prompt}'*\n"
            f"Try again with proper proof (`y!{cmd_name} <proof>`), or click **Reroll** / **Forfeit** below.\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        solo_view = SoloDareView(author_id)
        if wait_msg:
            try:
                await wait_msg.edit(content=fail_text, view=solo_view)
                return
            except Exception:
                pass
        await _safe_send_reply(message, fail_text, view=solo_view)


async def handle_forfeitdare(message, client, args: list):
    """Handles y!forfeitdare to surrender an active challenge."""
    await process_dare_forfeit(str(message.author.id), message=message)


async def handle_rerolldare(message, client, args: list):
    """Handles y!rerolldare to reroll an active challenge (1 free reroll)."""
    await process_dare_reroll(str(message.author.id), message=message)


async def handle_active_dare(message, client, args: list):
    """Handles y!activedare / y!mydare to view current dare or truth."""
    _ensure_fresh_data()
    author_id = str(message.author.id)

    if author_id not in _ACTIVE_DARES:
        await _safe_send_reply(
            message,
            "- *Yuna blinks* \"You don't have an active dare or truth right now!\n"
            "Challenge Yuna with `y!dare [amount]` / `y!truth [amount]` or challenge another player with `y!dare @user [amount] [custom dare]`!\""
        )
        return

    d = _ACTIVE_DARES[author_id]
    c_type = d.get("type", "dare")
    prompt = d.get("prompt") or d.get("dare", "")
    amount = d.get("amount", 25)
    pot = amount * 2
    challenger_mention = d.get("challenger_mention", "Yuna")
    rerolls_left = d.get("rerolls_left", 0)
    created_at = d.get("created_at", time.time())
    elapsed_mins = int((time.time() - created_at) // 60)
    is_custom = d.get("is_custom", False)

    icon = "🔮" if c_type == "truth" else "🎭"
    cmd_name = "checktruth" if c_type == "truth" else "checkdare"
    custom_tag = " (Custom Prompt)" if is_custom else ""

    text = (
        f"{icon} **YOUR ACTIVE {c_type.upper()} CHALLENGE**{custom_tag} {icon}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"**Challenger:** {challenger_mention}\n"
        f"**Total Pot on the Line:** **{pot}** 🫐\n"
        f"**Rerolls Left:** **{rerolls_left}**\n"
        f"**Active For:** {elapsed_mins} minutes\n\n"
        f"**Assigned Task:**\n"
        f"> 📢 **\"{prompt}\"**\n\n"
        f"✨ To submit your proof, type: `y!{cmd_name} <your proof>`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    view = SoloDareView(author_id)
    await _safe_send_reply(message, text, view=view)


# ─── SOCIAL: YUNA'S MARRIAGE & DIVORCE SYSTEM ───────────────────────────────

async def handle_marry(message, client, args: list):
    """Handles y!marry @user (Completely unserious Yuna marriage system)."""
    author_id = str(message.author.id)

    target = None
    if message.mentions:
        for m in message.mentions:
            if m.id != message.author.id and (not client.user or m.id != client.user.id):
                target = m
                break

    if not target and args:
        raw_target = args[0].strip()
        uid_match = re.search(r'\d{17,20}', raw_target)
        if uid_match and message.guild:
            target = message.guild.get_member(int(uid_match.group()))
        elif message.guild:
            clean_name = raw_target.lstrip("@").lower()
            target = discord.utils.find(
                lambda m: m.name.lower() == clean_name or m.display_name.lower() == clean_name,
                message.guild.members
            )

    if not target:
        await _safe_send_reply(message, "- *Yuna tilts her head* \"Who are you proposing to? Usage: `y!marry @user`\"")
        return

    if target.id == message.author.id:
        await _safe_send_reply(message, "- *Yuna laughs hysterically* \"You want to marry yourself?! You can't be that lonely!\"")
        return

    if getattr(target, "bot", False):
        await _safe_send_reply(message, "- *Yuna scoffs* \"I am an angel, and the other bots are code. Neither of us will marry you!\"")
        return

    s1 = await _get_user_stats(author_id)
    s2 = await _get_user_stats(str(target.id))

    if s1.get("spouse"):
        await _safe_send_reply(message, f"- *Yuna gasps* \"You're already married to <@{s1['spouse']}>! Get a `y!divorce` first!\"")
        return

    if s2.get("spouse"):
        await _safe_send_reply(message, f"- *Yuna scowls* \"<@{target.id}> is already married to <@{s2['spouse']}>! No homewrecking allowed!\"")
        return

    view = MarryView(str(target.id), author_id)
    prop_text = (
        f"💍 **A WEDDING PROPOSAL!** 💍\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{message.author.mention} has dropped to one knee and asked for <@{target.id}>'s hand in marriage!\n\n"
        f"<@{target.id}>, do you take this mortal to be your lawfully chaotic internet partner?\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    await _safe_send_reply(message, prop_text, view=view)


async def resolve_marriage(author_id: str, target_id: str, accepted: bool, interaction: Optional[discord.Interaction] = None, view: Optional[View] = None):
    if view:
        for item in view.children:
            item.disabled = True

    if not accepted:
        text = (
            f"💔 **REJECTED AT THE ALTAR!** 💔\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<@{target_id}> left <@{author_id}> standing alone at the altar in utter heartbreak!\n"
            f"*Yuna whispers* \"Ouch... that was painful to watch.\"\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        if interaction:
            await interaction.edit_original_response(content=text, view=view)
        return

    # Register marriage
    now_ts = time.time()
    async with _LOCK:
        _USER_STATS[author_id]["spouse"] = target_id
        _USER_STATS[author_id]["marriage_date"] = now_ts
        _USER_STATS[author_id]["marriage_count"] = _USER_STATS[author_id].get("marriage_count", 0) + 1
        _USER_STATS[target_id]["spouse"] = author_id
        _USER_STATS[target_id]["marriage_date"] = now_ts
        _USER_STATS[target_id]["marriage_count"] = _USER_STATS[target_id].get("marriage_count", 0) + 1
        _save_data_sync(_USER_STATS)

    u1 = await check_and_award_achievements(author_id, specific_id="ball_and_chain")
    u2 = await check_and_award_achievements(target_id, specific_id="ball_and_chain")
    banner = format_achievement_banner(u1 + u2)

    wedding_text = (
        f"💒 **JUST MARRIED!** 💒\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✨ By the celestial powers vested in Yuna (and a total lack of actual legal authority):\n\n"
        f"I now pronounce <@{author_id}> and <@{target_id}> **CHAOTIC PARTNERS FOR LIFE!** 🥂\n"
        f"May your berries be plentiful and your divorces be expensive!{banner}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    if interaction:
        await interaction.edit_original_response(content=wedding_text, view=view)


async def handle_divorce(message, client, args: list):
    """Handles y!divorce (costs 10,000 berries for Yuna's legal fees)."""
    author_id = str(message.author.id)
    stats = await _get_user_stats(author_id)
    spouse_id = stats.get("spouse")

    if not spouse_id:
        await _safe_send_reply(message, "- *Yuna tilts her head* \"You aren't even married, silly! You can't divorce thin air!\"")
        return

    author_berries = stats.get("berries", 0)
    has_insurance = stats.get("inventory", {}).get("insurance", 0) > 0
    DIVORCE_FEE = 5000 if has_insurance else 10000

    if author_berries < DIVORCE_FEE:
        ins_note = " (50% off with Divorce Insurance)" if has_insurance else ""
        await _safe_send_reply(
            message,
            f"- *Yuna smirks* \"Divorce denied! You need **{DIVORCE_FEE:,}** 🫐{ins_note} to pay my legal and emotional paperwork fees! You only have **{author_berries:,}** 🫐. You're staying together until you're richer!\""
        )
        return

    # Deduct fee and consume insurance if possessed
    await _update_user_stats(author_id, berries_delta=-DIVORCE_FEE)
    if has_insurance:
        async with _LOCK:
            _USER_STATS[author_id]["inventory"]["insurance"] -= 1
            if _USER_STATS[author_id]["inventory"]["insurance"] <= 0:
                _USER_STATS[author_id]["inventory"].pop("insurance", None)
            _save_data_sync(_USER_STATS)

    vault_split_line = ""
    vkey = _get_vault_key(author_id, spouse_id)
    async with _LOCK:
        vault = _JOINT_VAULTS.get(vkey)
        if vault and vault.get("balance", 0) > 0:
            v_bal = vault["balance"]
            half_1 = v_bal // 2
            half_2 = v_bal - half_1
            _USER_STATS[author_id]["berries"] = _USER_STATS[author_id].get("berries", 0) + half_1
            if spouse_id in _USER_STATS:
                _USER_STATS[spouse_id]["berries"] = _USER_STATS[spouse_id].get("berries", 0) + half_2
            vault["balance"] = 0
            vault_split_line = f"💰 **Joint Vault Liquidation:** The shared balance of **{v_bal:,}** 🫐 was divided 50/50 (**{half_1:,}** 🫐 to each party)!\n\n"

        _USER_STATS[author_id]["spouse"] = None
        _USER_STATS[author_id]["divorce_count"] = _USER_STATS[author_id].get("divorce_count", 0) + 1
        if spouse_id in _USER_STATS:
            _USER_STATS[spouse_id]["spouse"] = None
            _USER_STATS[spouse_id]["divorce_count"] = _USER_STATS[spouse_id].get("divorce_count", 0) + 1
        _save_data_sync(_USER_STATS)

    unlocked = await check_and_award_achievements(author_id, specific_id="irreconcilable_differences")
    banner = format_achievement_banner(unlocked)

    ins_line = "📜 *(Divorce Insurance Claimed: Fee reduced from 10,000 to 5,000 🫐!)*\n" if has_insurance else ""
    divorce_text = (
        f"📄 **DIVORCE PAPERS SIGNED & FINALIZED!** 📄\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<@{author_id}> paid **{DIVORCE_FEE:,}** 🫐 to Yuna's legal firm and is officially divorced from <@{spouse_id}>!\n"
        f"{ins_line}\n"
        f"{vault_split_line}"
        f"💔 The wedding rings were sold for scrap, and freedom was restored!{banner}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    await _safe_send_reply(message, divorce_text)


async def handle_marriage(message, client, args: list):
    """Handles y!marriage, y!spouse, y!couple, y!anniversary (Marriage certificate & couple stats)."""
    author_id = str(message.author.id)
    target_id = author_id

    # Check if a user was mentioned or passed
    if message.mentions:
        for m in message.mentions:
            if not client or not getattr(client, "user", None) or m.id != client.user.id:
                target_id = str(m.id)
                break
    elif args:
        raw = args[0].strip()
        uid_m = re.search(r'\d{17,20}', raw)
        if uid_m:
            target_id = uid_m.group()
        elif getattr(message, "guild", None) and getattr(message.guild, "members", None):
            clean_name = raw.lstrip("@").lower()
            for m in message.guild.members:
                if clean_name in (getattr(m, "name", "").lower(), getattr(m, "display_name", "").lower()):
                    target_id = str(m.id)
                    break

    stats = await _get_user_stats(target_id)
    spouse_id = stats.get("spouse")

    is_self = (target_id == author_id)

    if not spouse_id:
        if is_self:
            await _safe_send_reply(
                message,
                "- *Yuna chuckles and flips through her golden book*\n"
                "\"You don't have a marriage certificate on file! You are single!\n"
                "Find yourself a partner and propose using `y!marry @user` to unlock matrimonial perks!\""
            )
        else:
            await _safe_send_reply(
                message,
                f"- *Yuna inspects the registry* \"<@{target_id}> is currently unmarried and single!\""
            )
        return

    spouse_stats = await _get_user_stats(str(spouse_id))
    m_date = stats.get("marriage_date") or time.time()
    days_married = max(0, int((time.time() - m_date) // 86400))
    date_str = time.strftime("%B %d, %Y", time.gmtime(m_date))

    # Matrimonial items check
    relics = []
    if stats.get("inventory", {}).get("ring", 0) > 0 or spouse_stats.get("inventory", {}).get("ring", 0) > 0:
        relics.append("💍 **Golden Wedding Ring** *(Stipend & Gambling Boost)*")
    if stats.get("inventory", {}).get("diamond", 0) > 0 or spouse_stats.get("inventory", {}).get("diamond", 0) > 0:
        relics.append("💎 **Eternal Diamond** *(10% Vault Love Yield)*")
    if stats.get("inventory", {}).get("insurance", 0) > 0 or spouse_stats.get("inventory", {}).get("insurance", 0) > 0:
        relics.append("📜 **Divorce Insurance** *(Legal Shield Active)*")
    relics_str = "\n".join(relics) if relics else "*None equipped yet (Browse `y!shop`!)*"

    vault = _get_joint_vault(target_id, str(spouse_id))
    vow_text = stats.get("vow") or spouse_stats.get("vow") or "*No vows written yet! Etch one with `y!vow <text>`!*"

    double_aids = stats.get("double_aid_count", 0)
    dates_count = stats.get("date_count", 0)
    kisses_count = stats.get("kiss_count", 0)

    embed = discord.Embed(
        title="💒 Matrimonial Registry • Sacred Marriage Certificate",
        description=(
            f"Official celestial union between <@{target_id}> & <@{spouse_id}>!\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=0xF43F5E
    )
    embed.add_field(name="💍 Lawful Spouses", value=f"<@{target_id}> 💞 <@{spouse_id}>", inline=True)
    embed.add_field(name="📅 Wedding Day", value=f"{date_str}\n*({days_married} days together)*", inline=True)
    embed.add_field(name="🏛️ Matrimonial Joint Vault", value=f"**{vault.get('balance', 0):,}** 🫐\n*(+5%/10% daily love yield)*", inline=False)
    embed.add_field(name="📜 Sacred Couple Vow", value=f"> *\"{vow_text}\"*", inline=False)
    embed.add_field(
        name="💞 Couple Synergy & Records",
        value=(
            f"• 💖 Super Aids: **{double_aids}**\n"
            f"• 🌹 Romantic Dates: **{dates_count}**\n"
            f"• 💋 Kisses Shared: **{kisses_count}**"
        ),
        inline=True
    )
    embed.add_field(name="✨ Consecrated Heirlooms", value=relics_str, inline=True)
    embed.set_footer(text="Yuna's Matrimony • Commands: y!vow, y!kiss, y!date, y!gift, y!shared, y!doubleaid")
    await _safe_send_reply(message, embed=embed)


async def handle_vow(message, client, args: list):
    """Handles y!vow <text> (Etch your couple's sacred wedding vow)."""
    author_id = str(message.author.id)
    stats = await _get_user_stats(author_id)
    spouse_id = stats.get("spouse")

    if not spouse_id:
        await _safe_send_reply(
            message,
            "- *Yuna tilts her head* \"You need to be married to write wedding vows! Propose with `y!marry @user` first!\""
        )
        return

    if not args:
        await _safe_send_reply(
            message,
            "- *Yuna hands you an ink quill* \"What is your vow? Usage: `y!vow <your sacred oath>` (e.g. `y!vow For richer, poorer, and all the berries in between!`).\""
        )
        return

    vow_text = " ".join(args).strip()
    if len(vow_text) > 150:
        await _safe_send_reply(
            message,
            f"- *Yuna waves a hand* \"That's an essay, not a vow! Keep it under 150 characters (current: {len(vow_text)}).\""
        )
        return

    if len(vow_text) < 3:
        await _safe_send_reply(message, "- *Yuna crosses her arms* \"Your vow is too short! Put a little heart into it!\"")
        return

    spouse_id_str = str(spouse_id)
    async with _LOCK:
        _USER_STATS[author_id]["vow"] = vow_text
        if spouse_id_str in _USER_STATS:
            _USER_STATS[spouse_id_str]["vow"] = vow_text
        _save_data_sync(_USER_STATS)

    await _update_user_stats(author_id, virtue_delta=1)

    u1 = await check_and_award_achievements(author_id)
    u2 = await check_and_award_achievements(spouse_id_str)
    banner = format_achievement_banner(u1 + u2)

    embed = discord.Embed(
        title="📜 SACRED WEDDING VOW RECORDED! 📜",
        description=(
            f"{message.author.mention} has etched a celestial vow with <@{spouse_id_str}>:\n\n"
            f"> *\"{vow_text}\"*\n\n"
            f"💖 **Virtue Earned:** `+1 💖` *(Devotion to your spouse)*\n"
            f"This oath is now engraved on your `y!marriage` certificate!{banner}"
        ),
        color=0xF43F5E
    )
    embed.set_footer(text="Yuna's Matrimonial Registry • Sacred Vows")
    await _safe_send_reply(message, embed=embed)


async def handle_kiss(message, client, args: list):
    """Handles y!kiss [@user] (Romantic or playful kiss interaction)."""
    author_id = str(message.author.id)
    stats = await _get_user_stats(author_id)
    spouse_id = stats.get("spouse")
    spouse_id_str = str(spouse_id) if spouse_id else None

    # Target resolution
    target = None
    if message.mentions:
        for m in message.mentions:
            if m.id != message.author.id and (not client or not getattr(client, "user", None) or m.id != client.user.id):
                target = m
                break
    elif args:
        raw = args[0].strip()
        uid_m = re.search(r'\d{17,20}', raw)
        if uid_m and getattr(message, "guild", None):
            target = message.guild.get_member(int(uid_m.group()))
        elif getattr(message, "guild", None) and getattr(message.guild, "members", None):
            clean_name = raw.lstrip("@").lower()
            for m in message.guild.members:
                if clean_name in (getattr(m, "name", "").lower(), getattr(m, "display_name", "").lower()):
                    target = m
                    break

    target_id_str = str(target.id) if (target and hasattr(target, "id")) else None

    # Determine if kissing spouse
    is_kissing_spouse = False
    if spouse_id_str:
        if not target_id_str or target_id_str == spouse_id_str:
            is_kissing_spouse = True

    now = time.time()
    last_kiss = _LAST_KISS_TIME.get(author_id, 0.0)
    if now - last_kiss < KISS_COOLDOWN_SECONDS:
        rem = KISS_COOLDOWN_SECONDS - (now - last_kiss)
        await _safe_send_reply(message, f"- *Yuna fans herself* \"Catch your breath! Wait **{rem:.1f}s** before kissing again!\"")
        return

    _LAST_KISS_TIME[author_id] = now

    # Case 1: Married & kissing spouse
    if is_kissing_spouse:
        scenarios = [
            ("forehead", "You pulled <@{spouse}> close and planted a soft, tender kiss upon their forehead.", 25, 0),
            ("dip", "You dramatically dipped <@{spouse}> backwards and gave them a breathtaking movie-star kiss! The crowd applauds!", 20, 1),
            ("boop", "You caught <@{spouse}> completely off guard with a playful nose boop followed by a warm kiss on the lips!", 30, 0),
            ("starlight", "Under the shimmering twilight, you shared a lingering, passionate kiss with <@{spouse}>. Love sparks fly everywhere!", 35, 1),
            ("cheek", "You snuck up behind <@{spouse}> while they were counting berries and kissed their rosy cheek!", 15, 0)
        ]
        s_type, text_tmpl, vault_berries, v_gain = random.choice(scenarios)
        action_text = text_tmpl.format(spouse=spouse_id_str)

        async with _LOCK:
            vault = _get_joint_vault(author_id, spouse_id_str)
            vault["balance"] += vault_berries
            _USER_STATS[author_id]["kiss_count"] = _USER_STATS[author_id].get("kiss_count", 0) + 1
            _USER_STATS[spouse_id_str]["kiss_count"] = _USER_STATS[spouse_id_str].get("kiss_count", 0) + 1
            _save_data_sync(_USER_STATS)

        if v_gain > 0:
            await _update_user_stats(author_id, virtue_delta=v_gain)

        u1 = await check_and_award_achievements(author_id)
        u2 = await check_and_award_achievements(spouse_id_str)
        banner = format_achievement_banner(u1 + u2)

        v_note = f" | +{v_gain} 💖 Virtue" if v_gain > 0 else ""
        embed = discord.Embed(
            title="💋 SWEET MATRIMONIAL KISS! 💋",
            description=(
                f"{message.author.mention} kissed their spouse <@{spouse_id_str}>!\n\n"
                f"*{action_text}*\n\n"
                f"✨ **Love Sparks:** `+{vault_berries} 🫐` sent straight into your Joint Vault!{v_note}{banner}"
            ),
            color=0xF43F5E
        )
        embed.set_footer(text="Yuna's Romance • Love keeps the vault growing!")
        await _safe_send_reply(message, embed=embed)
        return

    # Case 2: Married, but kissed someone else who is NOT spouse! (INFIDELITY!)
    if spouse_id_str and target and str(target.id) != spouse_id_str:
        fine = 500
        author_berries = stats.get("berries", 0)
        actual_fine = min(author_berries, fine)

        async with _LOCK:
            if actual_fine > 0:
                _USER_STATS[author_id]["berries"] = _USER_STATS[author_id].get("berries", 0) - actual_fine
                vault = _get_joint_vault(author_id, spouse_id_str)
                vault["balance"] += actual_fine
            _USER_STATS[author_id]["sin"] = _USER_STATS[author_id].get("sin", 0) + 1
            _save_data_sync(_USER_STATS)

        embed = discord.Embed(
            title="🚨 CAUGHT IN 4K! SCANDALOUS INFIDELITY! 🚨",
            description=(
                f"{message.author.mention} was caught trying to kiss <@{target.id}> behind <@{spouse_id_str}>'s back!\n\n"
                f"*Yuna gasps in theatrical horror, blows a golden whistle, and alerts the whole server!*\n\n"
                f"💸 **Emotional Distress Fine:** `-{actual_fine} 🫐` transferred directly from your wallet into your Joint Vault for your betrayed spouse!\n"
                f"❤️‍🔥 **Karmic Penalty:** `+1 ❤️‍🔥 Sin`! *Juny smiles from the shadows...*"
            ),
            color=0xEF4444
        )
        embed.set_footer(text="Yuna's Matrimonial Court • Cheating has consequences!")
        await _safe_send_reply(message, embed=embed)
        return

    # Case 3: Unmarried / friendly kiss
    if not target:
        await _safe_send_reply(
            message,
            "- *Yuna blinks in confusion*\n"
            "\"You blew a kiss into empty air... Are you okay? Find someone to marry with `y!marry @user`!\""
        )
        return

    if target.id == message.author.id:
        await _safe_send_reply(message, "- *Yuna giggles* \"Kissing yourself in the mirror again? Narcissus would be proud!\"")
        return

    # Single person kissing someone
    embed = discord.Embed(
        title="✨ A PLAYFUL KISS & BLUSH! ✨",
        description=(
            f"{message.author.mention} gave <@{target.id}> a sweet, friendly kiss on the cheek!\n\n"
            f"<@{target.id}> blushed bright pink and offered a grateful smile!\n"
            f"🫐 *A little berry treat (+10 🫐) was shared!*"
        ),
        color=0xF472B6
    )
    await _update_user_stats(author_id, berries_delta=10)
    await _safe_send_reply(message, embed=embed)


async def handle_date(message, client, args: list):
    """Handles y!date, y!datenight (Take spouse out on hilarious romantic date)."""
    author_id = str(message.author.id)
    stats = await _get_user_stats(author_id)
    spouse_id = stats.get("spouse")

    if not spouse_id:
        await _safe_send_reply(
            message,
            "- *Yuna chuckles* \"You don't have a date partner! You're single! Propose to someone with `y!marry @user` first!\""
        )
        return

    spouse_id_str = str(spouse_id)
    spouse_stats = await _get_user_stats(spouse_id_str)

    now = time.time()
    last_date_a = _LAST_DATE_TIME.get(author_id, 0.0)
    last_date_s = _LAST_DATE_TIME.get(spouse_id_str, 0.0)
    last_date = max(last_date_a, last_date_s)
    if now - last_date < DATE_COOLDOWN_SECONDS:
        rem = DATE_COOLDOWN_SECONDS - (now - last_date)
        mins = int(rem // 60)
        secs = int(rem % 60)
        await _safe_send_reply(
            message,
            f"- *Yuna smirks* \"You two just went on a date! Let the romantic memories settle! Come back in **{mins}m {secs}s** (or snack on a `chocolate` truffles box with `y!use chocolate` to reset cooldowns)!\""
        )
        return

    has_bouquet = stats.get("inventory", {}).get("bouquet", 0) > 0
    DATE_FEE = 0 if has_bouquet else 50
    user_berries = stats.get("berries", 0)

    if user_berries < DATE_FEE:
        await _safe_send_reply(
            message,
            f"- *Yuna shakes her head* \"A proper date night costs **{DATE_FEE}** 🫐 for reservations and appetizers! You only have **{user_berries}** 🫐!\""
        )
        return

    _LAST_DATE_TIME[author_id] = now
    _LAST_DATE_TIME[spouse_id_str] = now

    if DATE_FEE > 0:
        await _update_user_stats(author_id, berries_delta=-DATE_FEE)

    bouquet_bonus_text = ""
    extra_vault = 0
    extra_v = 0
    if has_bouquet:
        async with _LOCK:
            _USER_STATS[author_id]["inventory"]["bouquet"] -= 1
            if _USER_STATS[author_id]["inventory"]["bouquet"] <= 0:
                _USER_STATS[author_id]["inventory"].pop("bouquet", None)
            _save_data_sync(_USER_STATS)
        extra_vault = 1500
        extra_v = 1
        bouquet_bonus_text = "\n💐 **Starlight Bouquet Presented!** Free reservation, `+1 extra 💖 Virtue`, and an extra `+1,500 🫐` love deposit!"

    venues = [
        (
            "Le Berry Starlight Bistro",
            "🍷",
            "You booked the golden rooftop balcony. A sparkling 5-tier berry soufflé was served alongside vintage nectar as violinists serenaded you under the stars!",
            random.randint(90, 180)
        ),
        (
            "High-Roller Neon Casino VIP Suite",
            "🎰",
            "You and your spouse took over the private velvet booth. You split a bowl of sugar-glazed strawberries and high-fived as the roulette wheel landed on your lucky number!",
            random.randint(110, 220)
        ),
        (
            "Moonlight Swan Lake & Berry Pond",
            "🦢",
            "You paddled a glowing swan boat across the quiet berry pond. Luminescent lotus blossoms drifted past as you held hands under the silver moon.",
            random.randint(80, 160)
        ),
        (
            "Juny's Abandoned Celestial Cathedral",
            "😈",
            "You spread a midnight candlelit picnic blanket beneath shattered stained-glass arches. Juny descended from the rafters, judged your cheese selection, sighed, and tossed a bag of berries before vanishing!",
            random.randint(120, 240)
        ),
        (
            "Cosmic Arcade & Boba Emporium",
            "🧋",
            "You two dominated the rhythm arcade machine with a 200-note perfect synchro combo! You cashed in your prize tickets for an oversized fluffy Yuna plushie!",
            random.randint(85, 175)
        )
    ]

    venue_name, venue_icon, venue_flavor, reward_berries = random.choice(venues)
    vault_love_kickback = max(10, int(reward_berries * 0.15)) + extra_vault

    async with _LOCK:
        vault = _get_joint_vault(author_id, spouse_id_str)
        vault["balance"] += vault_love_kickback
        _USER_STATS[author_id]["date_count"] = _USER_STATS[author_id].get("date_count", 0) + 1
        _USER_STATS[spouse_id_str]["date_count"] = _USER_STATS[spouse_id_str].get("date_count", 0) + 1
        _save_data_sync(_USER_STATS)

    await _update_user_stats(author_id, berries_delta=reward_berries, virtue_delta=2 + extra_v)
    await _update_user_stats(spouse_id_str, berries_delta=reward_berries, virtue_delta=2 + extra_v)

    u1 = await check_and_award_achievements(author_id)
    u2 = await check_and_award_achievements(spouse_id_str)
    banner = format_achievement_banner(u1 + u2)

    embed = discord.Embed(
        title=f"{venue_icon} DATE NIGHT: {venue_name.upper()}! {venue_icon}",
        description=(
            f"{message.author.mention} took their beloved <@{spouse_id_str}> out on an unforgettable romantic date!\n\n"
            f"*{venue_flavor}*{bouquet_bonus_text}\n\n"
            f"💰 **Date Allowance:** `+{reward_berries:,} 🫐` to each partner!\n"
            f"💖 **Virtue Earned:** `+{2 + extra_v} 💖` each!\n"
            f"🏛️ **Joint Vault Kickback:** `+{vault_love_kickback:,} 🫐`!{banner}"
        ),
        color=0xF43F5E
    )
    embed.set_footer(text="Yuna's Romance • Take your spouse on dates every 5 minutes!")
    await _safe_send_reply(message, embed=embed)


async def handle_lovegift(message, client, args: list):
    """Handles y!gift @spouse <amount|item> [custom message] (Tax-free matrimonial gifting)."""
    author_id = str(message.author.id)
    stats = await _get_user_stats(author_id)
    spouse_id = stats.get("spouse")

    if not spouse_id:
        # Fall back to standard give if single
        await handle_give(message, client, args)
        return

    spouse_id_str = str(spouse_id)
    if not args:
        await _safe_send_reply(
            message,
            "- *Yuna taps her chin* \"What are you gifting your spouse? Usage: `y!gift @spouse <berries|item> [note]` (or `y!gift <item>` to auto-gift spouse)!\""
        )
        return

    # Check if first argument is a mention/target
    target_is_spouse = False
    tokens = list(args)
    first_token = tokens[0].strip()
    uid_m = re.search(r'\d{17,20}', first_token)
    if uid_m:
        if uid_m.group() == spouse_id_str:
            target_is_spouse = True
            tokens = tokens[1:]
        else:
            # Gifting someone else: route to normal give
            await handle_give(message, client, args)
            return
    else:
        # Check if first token matches spouse name
        clean_name = first_token.lstrip("@").lower()
        if getattr(message, "guild", None) and getattr(message.guild, "members", None):
            for m in message.guild.members:
                if str(m.id) == spouse_id_str and clean_name in (getattr(m, "name", "").lower(), getattr(m, "display_name", "").lower()):
                    target_is_spouse = True
                    tokens = tokens[1:]
                    break

    if not tokens:
        await _safe_send_reply(message, "- *Yuna tilts her head* \"What are you gifting? Specify berries or an inventory item!\"")
        return

    gift_val = tokens[0].lower().strip()
    custom_note = " ".join(tokens[1:]).strip() if len(tokens) > 1 else "With all my chaotic love!"

    # Case A: Gifting berries
    clean_num = gift_val.replace(",", "")
    if clean_num.isdigit() and int(clean_num) > 0:
        amt = int(clean_num)
        author_berries = stats.get("berries", 0)
        if author_berries < amt:
            await _safe_send_reply(message, f"- *Yuna scoffs* \"You only have **{author_berries:,}** 🫐! You cannot gift **{amt:,}** 🫐!\"")
            return

        await _update_user_stats(author_id, berries_delta=-amt, virtue_delta=1)
        await _update_user_stats(spouse_id_str, berries_delta=amt)

        embed = discord.Embed(
            title="🎁 A ROMANTIC BERRY GIFT! 🎁",
            description=(
                f"{message.author.mention} gifted **{amt:,} 🫐** to their spouse <@{spouse_id_str}>!\n\n"
                f"💌 **Note:** *\"{custom_note}\"*\n\n"
                f"✨ **Tax-Free Transfer:** `100%` delivered!\n"
                f"💖 **Generosity Reward:** `+1 💖 Virtue` to invoker!"
            ),
            color=0xF43F5E
        )
        embed.set_footer(text="Yuna's Romance • Matrimonial Gifting")
        await _safe_send_reply(message, embed=embed)
        return

    # Case B: Gifting an inventory item
    alias_map = {
        "ring": "ring", "bouquet": "bouquet", "flowers": "bouquet", "chocolate": "chocolate",
        "truffles": "chocolate", "clover": "clover", "mask": "mask", "energy": "energy",
        "diamond": "diamond", "insurance": "insurance", "crown": "crown", "mirror": "mirror",
        "magnet": "magnet", "die": "loaded_die", "loaded_die": "loaded_die", "holy_water": "holy_water"
    }
    matched_item = alias_map.get(gift_val, gift_val)
    if matched_item not in SHOP_ITEMS:
        # If not a known item or number, fallback to give
        await handle_give(message, client, args)
        return

    author_inv = stats.get("inventory", {})
    if author_inv.get(matched_item, 0) <= 0:
        await _safe_send_reply(message, f"- *Yuna blinks* \"You don't have any `{matched_item}` in your bag to gift! Buy one at `y!shop`!\"")
        return

    spouse_stats = await _get_user_stats(spouse_id_str)
    spouse_inv = spouse_stats.get("inventory", {})
    max_hold = 1 if matched_item in ("feather", "sword") else 2
    if spouse_inv.get(matched_item, 0) >= max_hold:
        await _safe_send_reply(
            message,
            f"- *Yuna holds up a hand* \"Your spouse <@{spouse_id_str}> is already holding the maximum limit of **{max_hold}x** {SHOP_ITEMS[matched_item]['emoji']} **{SHOP_ITEMS[matched_item]['name']}**!\""
        )
        return

    async with _LOCK:
        _USER_STATS[author_id]["inventory"][matched_item] -= 1
        if _USER_STATS[author_id]["inventory"][matched_item] <= 0:
            _USER_STATS[author_id]["inventory"].pop(matched_item, None)
        _USER_STATS[spouse_id_str]["inventory"][matched_item] = _USER_STATS[spouse_id_str]["inventory"].get(matched_item, 0) + 1
        _save_data_sync(_USER_STATS)

    await _update_user_stats(author_id, virtue_delta=1)
    item_obj = SHOP_ITEMS[matched_item]

    embed = discord.Embed(
        title=f"🎁 A SPECIAL GIFT: {item_obj['emoji']} {item_obj['name'].upper()}! 🎁",
        description=(
            f"{message.author.mention} wrapped up a special present for <@{spouse_id_str}>!\n\n"
            f"📦 **Gift:** {item_obj['emoji']} **{item_obj['name']}**\n"
            f"💌 **Note:** *\"{custom_note}\"*\n\n"
            f"💖 **Virtue Earned:** `+1 💖 Virtue` to invoker!"
        ),
        color=0xF43F5E
    )
    embed.set_footer(text="Yuna's Romance • Matrimonial Gifting")
    await _safe_send_reply(message, embed=embed)

# ─── ACHIEVEMENTS COMMAND ───────────────────────────────────────────────────

ACHIEVEMENT_CATEGORIES = {
    "⚖️ Morality & Karma": [
        "what_have_you_done", "local_saint", "clean_slate", "pure_soul",
        "pure_sin", "robin_hood", "philanthropist", "super_donor"
    ],
    "🫐 Berry Wealth": [
        "ballin", "berry_saver", "berry_billionaire", "down_bad", "professional_idiot"
    ],
    "🎲 Casino & Mini-games": [
        "one_more_spin", "casino_veteran", "yunas_favorite", "moon_walker",
        "space_debris", "coin_heist", "mind_reader", "oracle_status",
        "on_a_roll", "hot_streak", "minefield_master", "lexicon_gambler", "ascended_lexicon"
    ],
    "🃏 Blackjack Curiosities": [
        "uno_reverse_card", "blue_eyes_white_dragon", "bitten_strawberry"
    ],
    "💍 Marriage & Joint Life": [
        "ball_and_chain", "irreconcilable_differences", "serial_marrier",
        "dynamic_duo", "joint_investor", "lovebirds", "golden_anniversary"
    ],
    "⚔️ Dares, Arena & Lifestyle": [
        "dare_master", "arena_gladiator", "daily_streak_7", "taskmaster", "music_vibes"
    ]
}

def _get_achievement_progress_str(ach_id: str, stats: dict) -> str:
    if ach_id == "what_have_you_done":
        return f" `[{stats.get('sin', 0)}/100]`"
    elif ach_id == "local_saint":
        return f" `[{stats.get('virtue', 0)}/100]`"
    elif ach_id == "down_bad":
        return f" `[{stats.get('total_lost_berries', 0):,}/10,000]`"
    elif ach_id == "one_more_spin":
        return f" `[{stats.get('daily_gambles', 0)}/50]`"
    elif ach_id == "professional_idiot":
        return f" `[{stats.get('bankrupt_count', 0)}/3]`"
    elif ach_id == "ballin":
        return f" `[{stats.get('berries', 0):,}/1,000]`"
    elif ach_id == "berry_saver":
        return f" `[{stats.get('berries', 0):,}/2,500]`"
    elif ach_id == "berry_billionaire":
        return f" `[{stats.get('berries', 0):,}/10,000]`"
    elif ach_id == "casino_veteran":
        return f" `[{stats.get('total_gambles', 0)}/100]`"
    elif ach_id == "clean_slate":
        return f" `[{stats.get('berries', 0):,}/100 🫐, Sin: {stats.get('sin', 0)}]`"
    elif ach_id == "pure_soul":
        return f" `[{stats.get('virtue', 0)}/50 💖, Sin: {stats.get('sin', 0)}]`"
    elif ach_id == "pure_sin":
        return f" `[{stats.get('sin', 0)}/25 ❤️‍🔥, Virtue: {stats.get('virtue', 0)}]`"
    elif ach_id == "robin_hood":
        return f" `[{stats.get('steals_success', 0)}/5]`"
    elif ach_id == "philanthropist":
        return f" `[{stats.get('total_donated', 0):,}/500]`"
    elif ach_id == "super_donor":
        return f" `[{stats.get('total_donated', 0):,}/2,000]`"
    elif ach_id == "mind_reader":
        return f" `[Streak: {stats.get('hl_max_streak', 0)}/5]`"
    elif ach_id == "oracle_status":
        return f" `[Streak: {stats.get('hl_max_streak', 0)}/7]`"
    elif ach_id == "arena_gladiator":
        return f" `[{stats.get('fights_won', 0)}/3]`"
    elif ach_id == "joint_investor":
        return f" `[{stats.get('joint_deposited', 0):,}/1,000]`"
    elif ach_id == "daily_streak_7":
        return f" `[Streak: {stats.get('daily_streak', 0)}/7]`"
    elif ach_id == "music_vibes":
        return f" `[{stats.get('music_interactions', 0)}/5]`"
    elif ach_id == "on_a_roll":
        return f" `[Streak: {stats.get('max_win_streak', 0)}/3]`"
    elif ach_id == "hot_streak":
        return f" `[Streak: {stats.get('max_win_streak', 0)}/7]`"
    elif ach_id == "minefield_master":
        return f" `[{stats.get('mines_won', 0)}/1]`"
    elif ach_id == "lexicon_gambler":
        return f" `[Stage: {stats.get('wordle_max_stage', 0)}/3]`"
    elif ach_id == "ascended_lexicon":
        return f" `[Stage: {stats.get('wordle_max_stage', 0)}/5]`"
    return ""

async def handle_achievements(message, client, args: list):
    """Handles y!achievements or y!ach."""
    author_id = str(message.author.id)

    # Trigger automatic retroactive check
    await check_and_award_achievements(author_id)
    stats = await _get_user_stats(author_id)
    unlocked_keys = set(stats.get("achievements", []))

    total = len(ACHIEVEMENTS)
    unlocked_count = len(unlocked_keys)
    pct = int((unlocked_count / total) * 100) if total > 0 else 0

    embed = discord.Embed(
        title=f"🏆 {message.author.display_name}'s Trophy Hall",
        description=f"**Completion:** `{unlocked_count}/{total}` ({pct}%) unlocked\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        color=discord.Color.gold()
    )

    for cat_name, key_list in ACHIEVEMENT_CATEGORIES.items():
        field_lines = []
        for ach_id in key_list:
            if ach_id not in ACHIEVEMENTS:
                continue
            ach = ACHIEVEMENTS[ach_id]
            is_unlocked = ach_id in unlocked_keys
            icon = "✅" if is_unlocked else "❌"
            prog = _get_achievement_progress_str(ach_id, stats) if not is_unlocked else ""
            field_lines.append(f"{icon} {ach['icon']} **{ach['title']}** — *{ach['desc']}*{prog}")
        if field_lines:
            embed.add_field(name=cat_name, value="\n".join(field_lines), inline=False)

    embed.set_footer(text="Yuna's Hall of Fame • Use y!help ach for guide")
    await _safe_send_reply(message, embed=embed)

# ─── MUSIC & KIZZY RPC HANDLERS ──────────────────────────────────────────────

async def _record_music_interaction(user_id: str, message=None):
    """Increments user's music interaction counter and checks for music achievements."""
    await _get_user_stats(user_id)
    async with _LOCK:
        if user_id in _USER_STATS:
            _USER_STATS[user_id]["music_interactions"] = _USER_STATS[user_id].get("music_interactions", 0) + 1
            _save_data_sync(_USER_STATS)
    unlocked = await check_and_award_achievements(user_id)
    if message and unlocked:
        banner = format_achievement_banner(unlocked)
        if banner:
            await _safe_send_reply(message, banner)

async def handle_now_playing(message, client, args: list = None):
    """Displays Yuna's currently playing track on Spotify with live progress and album art."""
    if not YUNA_RPC_AVAILABLE or not yuna_rpc:
        await _safe_send_reply(message, "*Yuna isn't wearing her headphones right now.*")
        return
    track = await yuna_rpc.get_or_update_track()
    embed = yuna_rpc.build_now_playing_embed(track)
    await _safe_send_reply(message, embed=embed)
    await record_task_progress(str(message.author.id), "vibe")
    await _record_music_interaction(str(message.author.id), message)

async def handle_play_song(message, client, args: list = None):
    """Sets a custom song for Yuna, resolving album cover with Kizzy API and updating Discord RPC."""
    if not YUNA_RPC_AVAILABLE or not yuna_rpc:
        await _safe_send_reply(message, "*Yuna's music player is taking a nap.*")
        return
    if not args:
        await _safe_send_reply(message, "*Yuna pouts* \"Tell me what song to put on, dummy! (e.g. `y!play Telecaster B-Boy`)\"")
        return
    query = " ".join(args)
    status_msg = await _safe_send_reply(message, f"🔍 *Searching for \"{query}\" and resolving album cover via Kizzy API...*")
    ok, track, msg = await yuna_rpc.set_custom_track(query, requested_by=message.author.display_name)
    if not ok:
        if status_msg:
            try:
                await status_msg.edit(content=f"❌ *{msg}*")
            except Exception:
                await _safe_send_reply(message, f"❌ *{msg}*")
        else:
            await _safe_send_reply(message, f"❌ *{msg}*")
        return

    # Update presence immediately on client
    try:
        activity = yuna_rpc.build_discord_activity(track)
        await client.change_presence(status=discord.Status.online, activity=activity)
    except Exception as e:
        print(f"[YUNA RPC] Could not update immediate presence: {e}")

    embed = yuna_rpc.build_now_playing_embed(track)
    reply_text = f"*Yuna puts on her pink cat-ear headphones and presses play!* 🎧\n**Now Playing on Discord RPC:**"
    if status_msg:
        try:
            await status_msg.edit(content=reply_text, embed=embed)
        except Exception:
            await _safe_send_reply(message, reply_text, embed=embed)
    else:
        await _safe_send_reply(message, reply_text, embed=embed)

    await _record_music_interaction(str(message.author.id), message)

async def handle_skip_song(message, client, args: list = None):
    """Skips to the next song in the playlist."""
    if not YUNA_RPC_AVAILABLE or not yuna_rpc:
        await _safe_send_reply(message, "*Yuna's music player is taking a nap.*")
        return
    track = await yuna_rpc.get_or_update_track(force_next=True)
    try:
        activity = yuna_rpc.build_discord_activity(track)
        await client.change_presence(status=discord.Status.online, activity=activity)
    except Exception:
        pass
    embed = yuna_rpc.build_now_playing_embed(track)
    await _safe_send_reply(message, "*Yuna skips to the next track on her playlist!* ⏭️", embed=embed)
    await _record_music_interaction(str(message.author.id), message)

async def handle_playlist(message, client, args: list = None):
    """Shows Yuna's current music queue and curated playlist rotation."""
    if not YUNA_RPC_AVAILABLE or not yuna_rpc:
        await _safe_send_reply(message, "*Yuna's playlist is unavailable.*")
        return
    track = await yuna_rpc.get_or_update_track()
    embed = discord.Embed(
        title="🎵 Yuna's Favorite Tracks & Queue",
        description="Yuna's personal rotation of Vocaloid, J-Pop, and aesthetic hits:",
        color=discord.Color.from_rgb(30, 215, 96)
    )
    embed.add_field(name="▶️ Currently Playing", value=f"**{track['title']}** — {track['artist']}", inline=False)
    
    queue_preview = []
    user_q = yuna_rpc.get_queue()
    if user_q:
        for i, q in enumerate(user_q[:3], 1):
            queue_preview.append(f"`{i}.` 👤 {q['query']} *(requested by {q.get('requested_by') or 'Someone'})*")
    
    for i, s in enumerate(yuna_rpc.DEFAULT_PLAYLIST[:7], len(queue_preview) + 1):
        queue_preview.append(f"`{i}.` 💿 {s}")

    embed.add_field(name="📋 Upcoming Rotation", value="\n".join(queue_preview), inline=False)
    embed.set_footer(text="💡 Tip: Type y!play <song name> to play your own favorite song!")
    await _safe_send_reply(message, embed=embed)
    await _record_music_interaction(str(message.author.id), message)


# ─── WORK, CRIME & FISHING ACTIVITIES ───────────────────────────────────────

async def handle_work(message, client, args: list):
    """Handles y!work (Honest shifts for Yuna)."""
    author_id = str(message.author.id)
    now = time.time()
    last_time = _LAST_WORK_TIME.get(author_id, 0.0)
    if now - last_time < WORK_COOLDOWN_SECONDS:
        rem = WORK_COOLDOWN_SECONDS - (now - last_time)
        mins = int(rem // 60)
        secs = int(rem % 60)
        await _safe_send_reply(
            message,
            f"- *Yuna yawns* \"Union rules! You're on break! Come back in **{mins}m {secs}s** before starting another shift!\""
        )
        return

    _LAST_WORK_TIME[author_id] = now
    stats = await _get_user_stats(author_id)
    eff_v, _ = get_effective_morality(stats)
    spouse_id = stats.get("spouse")

    job_title, flavor, min_pay, max_pay = random.choice(WORK_JOBS)
    base_pay = random.randint(min_pay, max_pay)
    
    # Virtue bonus: scales 0.02% of balance, 0.2x per virtue, +1% per 2 virtue
    v_bonus, v_mult_str = calculate_virtue_kind_bonus(stats, base_pay)
    pay = base_pay + v_bonus

    # Marriage bonus: +15% (or +25% with Golden Wedding Ring)
    has_ring = stats.get("inventory", {}).get("ring", 0) > 0
    m_pct = 0.25 if has_ring else 0.15
    m_bonus = int(pay * m_pct) if spouse_id else 0
    total_earned = pay + m_bonus

    # Super Berry Magnet bonus: +20%
    mag_charges = stats.get("magnet_charges", 0)
    mag_bonus = 0
    if mag_charges > 0:
        mag_bonus = max(1, int(total_earned * 0.20))
        total_earned += mag_bonus
        async with _LOCK:
            _USER_STATS[author_id]["magnet_charges"] = mag_charges - 1
            _save_data_sync(_USER_STATS)

    # 25% chance of +1 Virtue for honest hard work
    gain_virtue = (random.random() < 0.25)
    v_delta = 1 if gain_virtue else 0

    await _update_user_stats(author_id, berries_delta=total_earned, virtue_delta=v_delta)

    unlocked = await check_and_award_achievements(author_id)
    banner = format_achievement_banner(unlocked)

    ring_tag = " 💍 Ring" if has_ring else ""
    m_str = f" 💍 *(Marriage Bonus +{int(m_pct*100)}%{ring_tag}: +{m_bonus:,} 🫐)*" if m_bonus > 0 else ""
    mag_str = f" 🧲 *(+20% Magnet: +{mag_bonus:,} 🫐 [{mag_charges-1} left])*" if mag_bonus > 0 else ""
    v_gain_str = "\n💖 *Your honest diligence touched Yuna's heart!* (+1 💖 Virtue)" if gain_virtue else ""

    desc = (
        f"💼 **JOB COMPLETED: {job_title.upper()}** 💼\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"*{flavor}*\n\n"
        f"🪙 **Shift Wages:** `+{total_earned:,}` 🫐{v_mult_str}{m_str}{mag_str}{v_gain_str}{banner}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    await _safe_send_reply(message, desc)
    await record_task_progress(author_id, "aid")


async def handle_crime(message, client, args: list):
    """Handles y!crime (High risk, high reward underworld missions)."""
    author_id = str(message.author.id)
    now = time.time()
    last_time = _LAST_CRIME_TIME.get(author_id, 0.0)
    if now - last_time < CRIME_COOLDOWN_SECONDS:
        rem = CRIME_COOLDOWN_SECONDS - (now - last_time)
        mins = int(rem // 60)
        secs = int(rem % 60)
        await _safe_send_reply(
            message,
            f"- *Yuna smirks* \"The city sirens are blaring! Lay low in a safehouse for **{mins}m {secs}s** before pulling another heist!\""
        )
        return

    stats = await _get_user_stats(author_id)
    has_clover = stats.get("clover_active", False)
    if has_clover:
        async with _LOCK:
            _USER_STATS[author_id]["clover_active"] = False
            _save_data_sync(_USER_STATS)

    has_mask = stats.get("mask_active", False)
    if has_mask:
        async with _LOCK:
            _USER_STATS[author_id]["mask_active"] = False
            _save_data_sync(_USER_STATS)

    _LAST_CRIME_TIME[author_id] = now
    author_berries = stats.get("berries", 0)
    spouse_id = stats.get("spouse")

    mission_name, flavor, min_pay, max_pay = random.choice(CRIME_MISSIONS)

    # Success rate: Base 65% + 25% if clover active
    success_rate = 90 if has_clover else 65
    roll = random.randint(1, 100)

    if roll <= success_rate:
        # Success!
        base_loot = random.randint(min_pay, max_pay)
        if has_mask:
            base_loot = int(base_loot * 1.30)
        m_bonus = int(base_loot * 0.15) if spouse_id else 0
        total_payout = base_loot + m_bonus
        sin_gain = 0 if has_mask else 2

        await _update_user_stats(author_id, berries_delta=total_payout, sin_delta=sin_gain)

        unlocked = await check_and_award_achievements(author_id)
        banner = format_achievement_banner(unlocked)

        mask_str = " 🎭 *(Phantom Mask: 0 Sin & +30% Loot!)*" if has_mask else ""
        clover_str = " 🍀 *(Lucky Clover Guaranteed Success!)*" if has_clover else ""
        m_str = f" 💍 *(Marriage Bonus: +{m_bonus:,} 🫐)*" if m_bonus > 0 else ""

        desc = (
            f"🏴‍☠️ **UNDERWORLD HEIST SUCCESS: {mission_name.upper()}** 🏴‍☠️\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"*{flavor}*\n\n"
            f"💰 **Loot Secured:** `+{total_payout:,}` 🫐{mask_str}{clover_str}{m_str}\n"
            f"- Gained | +{sin_gain:02d} ❤️🔥|{banner}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await _safe_send_reply(message, desc)
    else:
        # Caught!
        fine = min(author_berries, random.randint(40, 100))
        fail_reason = random.choice(CRIME_FAIL_REASONS)
        sin_gain = 0 if has_mask else 1

        if fine > 0:
            await _update_user_stats(author_id, berries_delta=-fine, sin_delta=sin_gain)
            fine_str = f"💸 **Bail / Restitution Fine:** `-{fine:,}` 🫐"
        else:
            await _update_user_stats(author_id, sin_delta=sin_gain)
            fine_str = "💸 **Fine:** `0` 🫐 *(Too broke to pay bail!)*"

        desc = (
            f"🚨 **HEIST BOTCHED: {mission_name.upper()}** 🚨\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"*{fail_reason}*\n\n"
            f"{fine_str}\n"
            f"- Gained | +{sin_gain:02d} ❤️🔥|\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await _safe_send_reply(message, desc)


async def handle_fish(message, client, args: list):
    """Handles y!fish (Fishing in Yuna's enchanted berry pond)."""
    author_id = str(message.author.id)
    now = time.time()
    last_time = _LAST_FISH_TIME.get(author_id, 0.0)
    if now - last_time < FISH_COOLDOWN_SECONDS:
        rem = FISH_COOLDOWN_SECONDS - (now - last_time)
        await _safe_send_reply(
            message,
            f"- *Yuna holds up a net* \"The fish are startled! Wait **{rem:.0f}s** for ripples to settle!\""
        )
        return

    stats = await _get_user_stats(author_id)
    has_clover = stats.get("clover_active", False)
    if has_clover:
        async with _LOCK:
            _USER_STATS[author_id]["clover_active"] = False
            _save_data_sync(_USER_STATS)

    _LAST_FISH_TIME[author_id] = now
    spouse_id = stats.get("spouse")

    if has_clover:
        # Guaranteed rare catch! (Golden Koi, Giant King Berry Salmon, or Rare Dragon Pearl)
        catch = random.choice([FISH_CATCHES[3], FISH_CATCHES[4], FISH_CATCHES[5]])
    else:
        # Weighted catch across 9 possible catches
        weights = [25, 20, 15, 10, 6, 2, 8, 8, 6]
        catch = random.choices(FISH_CATCHES, weights=weights, k=1)[0]

    name, emoji, min_v, max_v, desc = catch
    payout = random.randint(min_v, max_v)
    v_bonus, v_str = calculate_virtue_kind_bonus(stats, payout)
    m_bonus = int(payout * 0.15) if spouse_id else 0
    total_earned = payout + v_bonus + m_bonus

    is_pearl = ("Dragon Pearl" in name)
    v_delta = 1 if is_pearl else 0

    await _update_user_stats(author_id, berries_delta=total_earned, virtue_delta=v_delta)

    unlocked = await check_and_award_achievements(author_id)
    banner = format_achievement_banner(unlocked)

    m_str = f" 💍 *(Marriage Bonus: +{m_bonus:,} 🫐)*" if m_bonus > 0 else ""
    clover_str = "\n🍀 *(Lucky Clover hooked an ancient treasure!)*" if has_clover else ""
    pearl_str = "\n🔮 *The Dragon Pearl infused your soul with holy light!* (+1 💖 Virtue)" if is_pearl else ""

    reply_text = (
        f"🎣 **FISHING EXPEDITION RESULTS** 🎣\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"You cast your bamboo line into the sparkling berry pond and reeled in:\n\n"
        f"{emoji} **{name}**!\n"
        f"*{desc}*\n\n"
        f"💰 **Sold for:** `+{total_earned:,}` 🫐{v_str}{m_str}{clover_str}{pearl_str}{banner}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    await _safe_send_reply(message, reply_text)


# ─── SHOP & INVENTORY SYSTEM ───────────────────────────────────────────────

async def handle_shop(message, client, args: list):
    """Displays Yuna's Item Shop catalog."""
    embed = discord.Embed(
        title="🏪 Yuna's Curio & Black Market Shop",
        description=(
            "Welcome to the realm's finest emporium of enchanted artifacts, consumables, and flexes!\n"
            "Use `y!buy <item> [qty]` to purchase, and `y!use <item>` to activate consumables!\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=HELP_COLOR
    )
    for key, item in SHOP_ITEMS.items():
        if item["price"] == 0 or item.get("type") in ("pact", "relic", "junk"):
            continue # Don't list soul-bound relics or broken junk in regular shop
        type_badge = f"`[{item['type'].upper()}]`"
        p_display = item.get("price_display") or f"{item['price']:,}"
        embed.add_field(
            name=f"{item['emoji']} {item['name']} — {p_display} 🫐 {type_badge}",
            value=f"• Key: `{key}`\n• {item['desc']}",
            inline=False
        )
    embed.set_footer(text="Yuna's Shop • Example: y!buy clover 2 or y!buy sword")
    await _safe_send_reply(message, embed=embed)


async def handle_buy(message, client, args: list):
    """Handles y!buy <item> [qty]."""
    author_id = str(message.author.id)
    if not args:
        await _safe_send_reply(
            message,
            "- *Yuna taps the counter* \"What are you buying? Type `y!shop` to view the catalog, then `y!buy <item> [qty]`!\""
        )
        return

    item_token = args[0].lower().strip()
    qty = 1
    if len(args) > 1 and args[1].isdigit():
        qty = max(1, min(100, int(args[1])))

    # Match item token
    matched_key = None
    for k in SHOP_ITEMS:
        if item_token == k or item_token == SHOP_ITEMS[k]["name"].lower():
            matched_key = k
            break
    if not matched_key:
        alias_map = {
            "drink": "energy", "mask": "mask", "clover": "clover", "ward": "ward",
            "shield": "ward", "heavenly": "ward", "heavenlyshield": "ward", "divineward": "ward",
            "diamond": "diamond", "gem": "diamond",
            "ins": "insurance", "policy": "insurance", "crown": "crown", "tiara": "crown",
            "sword": "sword", "blade": "sword", "katana": "sword",
            "feather": "feather", "phoenix": "feather",
            "elixir": "elixir", "potion": "elixir",
            "powder": "powder", "smite": "powder",
            "ironbrew": "ironbrew", "iron": "ironbrew", "brew": "ironbrew",
            "adrenaline": "adrenaline", "injector": "adrenaline",
            "hammer": "hammer", "rubberhammer": "hammer",
            "sand": "sand", "pocketsand": "sand",
            "coupon": "coupon", "apology": "coupon",
            "ring": "ring", "weddingring": "ring", "goldring": "ring", "band": "ring",
            "bouquet": "bouquet", "flowers": "bouquet", "roses": "bouquet", "rose": "bouquet",
            "chocolate": "chocolate", "chocolates": "chocolate", "truffles": "chocolate", "choco": "chocolate",
            "mirror": "mirror", "purifyingmirror": "mirror", "glass": "mirror",
            "magnet": "magnet", "berrymagnet": "magnet",
            "loaded_die": "loaded_die", "die": "loaded_die", "dices": "loaded_die", "loadeddie": "loaded_die",
            "holy_water": "holy_water", "water": "holy_water", "holywater": "holy_water", "blessedwater": "holy_water"
        }
        matched_key = alias_map.get(item_token)

    if not matched_key or matched_key not in SHOP_ITEMS:
        await _safe_send_reply(
            message,
            f"- *Yuna tilts her head* \"I don't sell `{item_token}`! Check `y!shop` for available inventory items!\""
        )
        return

    if matched_key in ("devil_contract", "devil_horn", "cardboard_shards"):
        await _safe_send_reply(
            message,
            f"- *Yuna pushes it behind the glass* \"`{matched_key}` is a soul-bound relic! You cannot buy it here!\""
        )
        return

    stats = await _get_user_stats(author_id)
    user_berries = stats.get("berries", 0)
    user_inv = stats.get("inventory", {})

    # ── Inventory Holding Limit Enforcement ──
    # Feather: max 1 at a time; all other shop items: max 2 at a time
    max_hold_limit = 1 if matched_key == "feather" else 2
    curr_hold = user_inv.get(matched_key, 0)
    if curr_hold >= max_hold_limit:
        item_obj = SHOP_ITEMS[matched_key]
        await _safe_send_reply(
            message,
            f"- *Yuna holds up a hand* \"Your inventory is full for that item! You can only hold at most **{max_hold_limit}x** {item_obj['emoji']} **{item_obj['name']}** at a time! (You already have {curr_hold}).\""
        )
        return

    if curr_hold + qty > max_hold_limit:
        item_obj = SHOP_ITEMS[matched_key]
        allowed_qty = max_hold_limit - curr_hold
        await _safe_send_reply(
            message,
            f"- *Yuna shakes her head* \"You can only carry up to **{max_hold_limit}x** {item_obj['emoji']} **{item_obj['name']}** at a time! You already have **{curr_hold}**, so you can only purchase **{allowed_qty}** more!\""
        )
        return

    # ── Special Logic: Legendary Expensive Sword ──
    if matched_key == "sword":
        if user_inv.get("sword", 0) >= 1:
            await _safe_send_reply(
                message,
                "- *Yuna waves you away* \"You already own the one-of-a-kind Legendary Sword! Go test it in combat before trying to buy another!\""
            )
            return
        if user_berries < 1_000_000:
            await _safe_send_reply(
                message,
                "- *Yuna bursts into mocking laughter WUWAHAHAHAHAH~* \"In your dreams loser! Come back when you're not swimming in pocket lint!\""
            )
            return
        elif user_berries < 100_000_000:
            await _safe_send_reply(
                message,
                "- *Yuna rolls her eyes* \"Way too expensive for you! You can't even afford the scabbard polish!\""
            )
            return
        elif user_berries < 500_000_000:
            await _safe_send_reply(
                message,
                "- *Yuna crosses her arms with a smirk* \"Very very very very very expensive for you!\""
            )
            return
        elif user_berries < 1_000_000_000:
            await _safe_send_reply(
                message,
                "- *Yuna whispers dramatically* \"Veeeeeery expensive...\""
            )
            return
        elif user_berries < 3_000_000_000:
            await _safe_send_reply(
                message,
                "- *Yuna shakes her head* \"Still very expensive!\""
            )
            return
        elif user_berries < 5_000_000_000:
            await _safe_send_reply(
                message,
                "- *Yuna narrows her eyes* \"Close.\""
            )
            return
        else:
            # >= 5B: buys it, but drains 100% of user balance!
            total_cost = user_berries
            await _update_user_stats(author_id, berries_delta=-total_cost)
            async with _LOCK:
                u_stat = _USER_STATS.get(author_id, {})
                inv = u_stat.setdefault("inventory", {})
                inv["sword"] = inv.get("sword", 0) + 1
                u_stat["bought_expensive_item"] = True
                _save_data_sync(_USER_STATS)

            unlocked = await check_and_award_achievements(author_id)
            banner = format_achievement_banner(unlocked)

            desc = (
                f"🗡️ **LEGENDARY PURCHASE CONFIRMED!** 🗡️\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"*Yuna's hands tremble with sheer delight as she sweeps up ALL **{total_cost:,}** 🫐 of your entire life fortune into her golden vault!*\n\n"
                f"\"WUWAHAHAHA! SOLD! The mythical god-slaying blade is officially yours! You are completely penniless, but behold its majestic cardboard—er, I mean, CELESTIAL aura!\"\n\n"
                f"📦 *'Legendary Expensive Sword' added to your inventory! View with `y!inv`!*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━{banner}"
            )
            await _safe_send_reply(message, desc)
            return

    item = SHOP_ITEMS[matched_key]
    total_cost = item["price"] * qty

    if user_berries < total_cost:
        await _safe_send_reply(
            message,
            f"- *Yuna snickers* \"You need **{total_cost:,}** 🫐 for {qty}x {item['emoji']} {item['name']}! You only have **{user_berries:,}** 🫐!\""
        )
        return

    # Deduct berries and add to inventory
    await _update_user_stats(author_id, berries_delta=-total_cost)
    async with _LOCK:
        u_stat = _USER_STATS.get(author_id, {})
        inv = u_stat.setdefault("inventory", {})
        inv[matched_key] = inv.get(matched_key, 0) + qty
        if total_cost >= 3_000_000:
            u_stat["bought_expensive_item"] = True
        _save_data_sync(_USER_STATS)

    unlocked = await check_and_award_achievements(author_id)
    banner = format_achievement_banner(unlocked)

    desc = (
        f"🛍️ **PURCHASE RECEIPT** 🛍️\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Purchased: **{qty}x {item['emoji']} {item['name']}**\n"
        f"Total Paid: **-{total_cost:,}** 🫐\n\n"
        f"📦 *Item added to your pouch! View with `y!inv` or use with `y!use {matched_key}`!*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━{banner}"
    )
    await _safe_send_reply(message, desc)


async def handle_inventory(message, client, args: list):
    """Handles y!inventory (or y!inv)."""
    target_user = message.author
    if message.mentions:
        for m in message.mentions:
            if not client.user or m.id != client.user.id:
                target_user = m
                break

    stats = await _get_user_stats(str(target_user.id))
    inv = stats.get("inventory", {})
    display_name = getattr(target_user, "display_name", target_user.name)

    embed = discord.Embed(
        title=f"🎒 {display_name}'s Inventory & Bag",
        description=f"Berry Pouch: `{stats.get('berries', 0):,} 🫐`\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        color=HELP_COLOR
    )

    has_items = False
    for k, qty in inv.items():
        if qty > 0 and k in SHOP_ITEMS:
            item = SHOP_ITEMS[k]
            embed.add_field(
                name=f"{item['emoji']} {item['name']} (x{qty})",
                value=f"`{item['type'].title()}` — {item['desc']}",
                inline=False
            )
            has_items = True
        elif qty > 0 and YUNA_RPG_AVAILABLE and yuna_rpg and k in yuna_rpg.BATTLE_SHOP_ITEMS:
            b_item = yuna_rpg.BATTLE_SHOP_ITEMS[k]
            embed.add_field(
                name=f"{b_item['emoji']} {b_item['name']} (x{qty})",
                value=f"`Battle Gear ({b_item.get('slot', 'gear').title()})` — {b_item['desc']}",
                inline=False
            )
            has_items = True

    if not has_items:
        embed.add_field(
            name="💨 Empty Bag",
            value="You don't own any items yet! Visit `y!shop` or `y!battleshop` to purchase gear and tools!",
            inline=False
        )

    buffs = []
    if stats.get("clover_active"):
        buffs.append("🍀 **Lucky Clover:** Active (+25% luck on next gamble/crime/fish)")
    if stats.get("mask_active"):
        buffs.append("🎭 **Phantom Mask:** Active (0 Sin & +30% loot on next steal/crime)")
    if buffs:
        embed.add_field(name="✨ Active Status Effects", value="\n".join(buffs), inline=False)

    embed.set_footer(text="Yuna's Bag • Use consumables with y!use <item>")
    await _safe_send_reply(message, embed=embed)


async def handle_use(message, client, args: list):
    """Handles y!use <item>."""
    author_id = str(message.author.id)
    if not args:
        await _safe_send_reply(message, "- *Yuna tilts her head* \"What do you want to use? Example: `y!use clover` or `y!use energy`\"")
        return

    item_token = args[0].lower().strip()
    alias_map = {
        "drink": "energy", "energy": "energy", "mask": "mask", "clover": "clover",
        "ward": "ward", "shield": "ward", "diamond": "diamond", "insurance": "insurance", "crown": "crown",
        "ring": "ring", "weddingring": "ring", "goldring": "ring", "band": "ring",
        "bouquet": "bouquet", "flowers": "bouquet", "roses": "bouquet", "rose": "bouquet",
        "chocolate": "chocolate", "chocolates": "chocolate", "truffles": "chocolate", "choco": "chocolate",
        "mirror": "mirror", "purifyingmirror": "mirror", "glass": "mirror",
        "magnet": "magnet", "berrymagnet": "magnet",
        "loaded_die": "loaded_die", "die": "loaded_die", "dices": "loaded_die", "loadeddie": "loaded_die",
        "holy_water": "holy_water", "water": "holy_water", "holywater": "holy_water", "blessedwater": "holy_water"
    }
    matched_key = alias_map.get(item_token, item_token)

    stats = await _get_user_stats(author_id)
    inv = stats.get("inventory", {})

    if YUNA_RPG_AVAILABLE and yuna_rpg:
        b_key = matched_key if matched_key in yuna_rpg.BATTLE_SHOP_ITEMS else (item_token if item_token in yuna_rpg.BATTLE_SHOP_ITEMS else None)
        if b_key:
            b_item = yuna_rpg.BATTLE_SHOP_ITEMS[b_key]
            if b_item.get("slot") in ("weapon", "armor", "accessory"):
                await yuna_rpg.handle_equip(message, client, [b_key], sys.modules[__name__])
                return
            elif b_key == "dungeon_key":
                if inv.get("dungeon_key", 0) <= 0:
                    await _safe_send_reply(message, "You don't own any **GoD-HeLL Golden Dungeon Keys**! Buy one at `y!battleshop`!")
                    return
                inv["dungeon_key"] -= 1
                stats["last_dungeon_time"] = 0.0
                _save_data_sync()
                await _safe_send_reply(message, "🗝️ **RUNIC SEAL SHATTERED!** Your GoD-HeLL dungeon cooldown has been reset! Raid immediately with `y!godhell`!")
                return
            elif b_key == "dungeon_elixir":
                await yuna_rpg.handle_dheal(message, client, args, sys.modules[__name__])
                return

    if inv.get(matched_key, 0) <= 0:
        await _safe_send_reply(
            message,
            f"- *Yuna blinks* \"You don't have any `{matched_key}` in your inventory! Buy one at `y!shop` or `y!battleshop`!\""
        )
        return

    if matched_key == "clover":
        if stats.get("clover_active"):
            await _safe_send_reply(message, "- *Yuna winks* \"You already have a Lucky Clover buff active! Go gamble or fish to spend it!\"")
            return
        async with _LOCK:
            _USER_STATS[author_id]["inventory"]["clover"] -= 1
            if _USER_STATS[author_id]["inventory"]["clover"] <= 0:
                _USER_STATS[author_id]["inventory"].pop("clover", None)
            _USER_STATS[author_id]["clover_active"] = True
            _save_data_sync(_USER_STATS)
        await _safe_send_reply(
            message,
            "🍀 **LUCKY CLOVER ACTIVATED!** 🍀\n"
            "You rubbed the four-leaf clover for good fortune! Your **next gamble, crime, or fishing cast** gains **+25% luck**!"
        )

    elif matched_key == "energy":
        async with _LOCK:
            _USER_STATS[author_id]["inventory"]["energy"] -= 1
            if _USER_STATS[author_id]["inventory"]["energy"] <= 0:
                _USER_STATS[author_id]["inventory"].pop("energy", None)
            _LAST_WORK_TIME.pop(author_id, None)
            _LAST_CRIME_TIME.pop(author_id, None)
            _LAST_FISH_TIME.pop(author_id, None)
            _save_data_sync(_USER_STATS)
        await _safe_send_reply(
            message,
            "⚡ **ENERGY DRINK CONSUMED!** ⚡\n"
            "*Gulp gulp gulp...* Electrolyte rush! All your **work, crime, and fishing cooldowns** have been completely reset! Ready for action!"
        )

    elif matched_key == "mask":
        if stats.get("mask_active"):
            await _safe_send_reply(message, "- *Yuna winks* \"You're already wearing a Phantom Mask! Go pull off a heist with `y!steal` or `y!crime`!\"")
            return
        async with _LOCK:
            _USER_STATS[author_id]["inventory"]["mask"] -= 1
            if _USER_STATS[author_id]["inventory"]["mask"] <= 0:
                _USER_STATS[author_id]["inventory"].pop("mask", None)
            _USER_STATS[author_id]["mask_active"] = True
            _save_data_sync(_USER_STATS)
        await _safe_send_reply(
            message,
            "🎭 **PHANTOM MASK EQUIPPED!** 🎭\n"
            "You slip on the mysterious mask. Your **next steal or crime** produces **0 Sin** and grants **+30% bonus loot**!"
        )

    elif matched_key == "ward":
        await _safe_send_reply(
            message,
            "🛡️ **DIVINE WARD IS PASSIVE!**\n"
            "You don't need to manually use this! It sits in your pouch and will **automatically shatter and electrocute the next thief** who dares pickpocket you!"
        )

    elif matched_key == "diamond":
        await _safe_send_reply(
            message,
            "💎 **ETERNAL DIAMOND IS PASSIVE!**\n"
            "This precious heirloom rests in your pouch and **permanently doubles your joint vault daily love interest** from +5% up to +10%!"
        )

    elif matched_key == "insurance":
        await _safe_send_reply(
            message,
            "📜 **DIVORCE INSURANCE IS PASSIVE!**\n"
            "This signed legal policy will **automatically trigger when you use `y!divorce`**, slashing Yuna's fee from 10,000 down to 5,000 🫐!"
        )

    elif matched_key == "crown":
        await _safe_send_reply(
            message,
            "👑 **EMPRESS CROWN IS AN ETERNAL FLEX!**\n"
            "The glittering golden crown sits proudly on your head and shines brightly on your `y!balance` card and leaderboard ranks!"
        )

    elif matched_key == "ring":
        await _safe_send_reply(
            message,
            "💍 **GOLDEN WEDDING RING IS PASSIVE!**\n"
            "This 24k consecrated band gleams on your hand! While married, it:\n"
            "• Boosts daily allowance (`y!daily`) marriage stipend from +50 to **+120 🫐**!\n"
            "• Increases marriage gambling profit bonus from +15% to **+25%**!\n"
            "• Increases marriage work shift bonus from +15% to **+25%**!\n"
            "• Grants **+10% higher success rate** on `y!doubleaid`!\n"
            "• Displays a golden band on your `y!marriage` certificate!"
        )

    elif matched_key == "bouquet":
        spouse_id = stats.get("spouse")
        if not spouse_id:
            await _safe_send_reply(
                message,
                "- *Yuna chuckles* \"You're holding a gorgeous bouquet of roses, but you're single! Who are they for? Yourself?\n"
                "Self-love is great, but find a partner with `y!marry @user` to bestow these properly!\""
            )
            return
        async with _LOCK:
            _USER_STATS[author_id]["inventory"]["bouquet"] -= 1
            if _USER_STATS[author_id]["inventory"]["bouquet"] <= 0:
                _USER_STATS[author_id]["inventory"].pop("bouquet", None)
            vault = _get_joint_vault(author_id, str(spouse_id))
            vault["balance"] += 1500
            _save_data_sync(_USER_STATS)
        await _update_user_stats(author_id, virtue_delta=1)
        await _update_user_stats(str(spouse_id), virtue_delta=1)
        embed = discord.Embed(
            title="💐 A BREATHTAKING GIFT OF ROSES! 💐",
            description=(
                f"{message.author.mention} surprised their beloved <@{spouse_id}> with an enchanting armful of glowing Starlight Roses!\n\n"
                f"✨ *\"For you, my favorite person in the entire universe!\"*\n"
                f"• Both partners earned **+1 💖 Virtue**!\n"
                f"• **+1,500 🫐** deposited directly into your Joint Vault!"
            ),
            color=0xF43F5E
        )
        embed.set_footer(text="Yuna's Romance • True love pays dividends!")
        await _safe_send_reply(message, embed=embed)

    elif matched_key == "chocolate":
        async with _LOCK:
            _USER_STATS[author_id]["inventory"]["chocolate"] -= 1
            if _USER_STATS[author_id]["inventory"]["chocolate"] <= 0:
                _USER_STATS[author_id]["inventory"].pop("chocolate", None)
            _LAST_DATE_TIME.pop(author_id, None)
            _LAST_DOUBLE_AID_TIME.pop(author_id, None)
            spouse_id = stats.get("spouse")
            if spouse_id:
                _LAST_DATE_TIME.pop(str(spouse_id), None)
                _LAST_DOUBLE_AID_TIME.pop(str(spouse_id), None)
            _save_data_sync(_USER_STATS)
        await _safe_send_reply(
            message,
            "🍫 **HEART TRUFFLES BOX DEVOURED!** 🍫\n"
            "*Omnomnomnom...* Rich dark chocolate ganache and strawberry dust! A burst of sweet energy rushes through you!\n"
            "Your **`y!date` and `y!doubleaid` cooldowns** have been completely reset! Go enjoy quality time together!"
        )

    elif matched_key == "mirror":
        curr_sin = stats.get("sin", 0)
        if curr_sin <= 0:
            await _safe_send_reply(
                message,
                "- *Yuna inspects your soul* \"Your soul is already pristine with 0 Sin! Save your Purifying Mirror for when you've been naughty!\""
            )
            return
        cleansed = min(3, curr_sin)
        new_sin = curr_sin - cleansed
        async with _LOCK:
            _USER_STATS[author_id]["inventory"]["mirror"] -= 1
            if _USER_STATS[author_id]["inventory"]["mirror"] <= 0:
                _USER_STATS[author_id]["inventory"].pop("mirror", None)
            _USER_STATS[author_id]["sin"] = new_sin
            _save_data_sync(_USER_STATS)
        embed = discord.Embed(
            title="🪞 SOUL PURIFICATION: MIRROR SHATTERED! 🪞",
            description=(
                f"You gaze into the Purifying Mirror. Blinding silver moonlight washes over your spirit, absorbing **{cleansed} points** of mortal corruption!\n\n"
                f"❤️‍🔥 **Sin Level:** `{curr_sin}` ➔ **`{new_sin}`**\n"
                f"*Juny's celestial ledger recalculates in your favor.*"
            ),
            color=0xE0E7FF
        )
        embed.set_footer(text="Yuna's Morality • Karmic Cleansing")
        await _safe_send_reply(message, embed=embed)

    elif matched_key == "magnet":
        async with _LOCK:
            _USER_STATS[author_id]["inventory"]["magnet"] -= 1
            if _USER_STATS[author_id]["inventory"]["magnet"] <= 0:
                _USER_STATS[author_id]["inventory"].pop("magnet", None)
            _USER_STATS[author_id]["magnet_charges"] = _USER_STATS[author_id].get("magnet_charges", 0) + 3
            _save_data_sync(_USER_STATS)
        charges = _USER_STATS[author_id]["magnet_charges"]
        await _safe_send_reply(
            message,
            "🧲 **SUPER BERRY MAGNET CHARGED!** 🧲\n"
            f"You flipped the switch! Intense magnetic energy crackles around your pockets!\n"
            f"Your next **{charges} casino wins or work shifts** will pull in an extra **+20% bonus berries**!"
        )

    elif matched_key == "loaded_die":
        if stats.get("loaded_die_active"):
            await _safe_send_reply(message, "- *Yuna winks* \"You already have a Lucky Loaded Die ready in your hand! Go roll `y!dice` to use it!\"")
            return
        async with _LOCK:
            _USER_STATS[author_id]["inventory"]["loaded_die"] -= 1
            if _USER_STATS[author_id]["inventory"]["loaded_die"] <= 0:
                _USER_STATS[author_id]["inventory"].pop("loaded_die", None)
            _USER_STATS[author_id]["loaded_die_active"] = True
            _save_data_sync(_USER_STATS)
        await _safe_send_reply(
            message,
            "🎲 **LUCKY LOADED DIE READY!** 🎲\n"
            "You secretly palmed the weighted die! On your next `y!dice` table roll, **Snake Eyes [2] is impossible** and the odds for **Lucky 7 and Doubles are heavily boosted**!"
        )

    elif matched_key == "holy_water":
        if stats.get("shield_blessed"):
            await _safe_send_reply(message, "- *Yuna whispers* \"Your Heavenly Shield is already glistening with consecrated holy water!\"")
            return
        if stats.get("inventory", {}).get("ward", 0) <= 0:
            await _safe_send_reply(message, "- *Yuna tilts her head* \"You don't have a Heavenly Shield (`ward`) to pour this on! Buy a shield first at `y!shop`!\"")
            return
        async with _LOCK:
            _USER_STATS[author_id]["inventory"]["holy_water"] -= 1
            if _USER_STATS[author_id]["inventory"]["holy_water"] <= 0:
                _USER_STATS[author_id]["inventory"].pop("holy_water", None)
            _USER_STATS[author_id]["shield_blessed"] = True
            _save_data_sync(_USER_STATS)
        await _safe_send_reply(
            message,
            "💧 **HEAVENLY SHIELD CONSECRATED!** 💧\n"
            "You poured the sacred holy water over your Heavenly Shield! A serene golden halo envelopes it.\n"
            "The shield is now **immune to Sin corruption** and guaranteed **100% block with zero backfire** on its next activation!"
        )

    elif matched_key in ("elixir", "powder", "ironbrew", "adrenaline", "hammer", "sand"):
        await _safe_send_reply(
            message,
            f"🎒 **COMBAT CONSUMABLE!**\n"
            f"*Yuna shakes her head:* \"You can't use `{matched_key}` right now! Save it for battle when Juny, Heaven's Worst Angel, comes for your soul! Use it during combat with `y!useitem {matched_key}` or the **Item** button!\""
        )

    elif matched_key == "feather":
        await _safe_send_reply(
            message,
            "🪶 **PHOENIX FEATHER IS PASSIVE!**\n"
            "Keep it in your bag! If your HP drops to 0 during battle against Juny, the feather will automatically ignite and resurrect you with 50 HP!"
        )

    elif matched_key == "coupon":
        await _safe_send_reply(
            message,
            "🎟️ **COUPON FOR 1 FREE APOLOGY!**\n"
            "Keep it tucked in your pocket! When Juny descends to claim your soul, choose **Plead** (`y!plead`) to present this coupon for an extra +5% mercy chance!"
        )

    elif matched_key == "sword":
        await _safe_send_reply(
            message,
            "🗡️ **LEGENDARY EXPENSIVE SWORD!**\n"
            "*You admire the shimmering golden hilt.* \"Save this ultimate weapon for Juny! Attack her in battle using `y!attack` or the Attack button!\""
        )

    elif matched_key in ("devil_contract", "devil_horn", "cardboard_shards"):
        item_info = SHOP_ITEMS.get(matched_key, {})
        await _safe_send_reply(
            message,
            f"{item_info.get('emoji', '✨')} **{item_info.get('name', matched_key).upper()}**\n"
            f"*{item_info.get('desc', 'A mysterious soul-bound relic.')}*"
        )



# ─── BOSS FIGHT: JUNY, HEAVEN'S WORST ANGEL (JUNY-HWA) ─────────────────────

_PENDING_BOSS_ENCOUNTERS: Dict[str, dict] = {} # user_id -> encounter state
_ACTIVE_BOSS_FIGHTS: Dict[str, dict] = {}      # host_id -> combat state

JUNY_MOODS = [
    ("teasing", "Ara ara~ Did you really think you could run after sinning so deliciously? Let me hear you whimper!"),
    ("violent", "DIE DIE DIE! I'll grind your soul into dust and feed your remnants to the pit!"),
    ("tsundere", "H-Hmph! Don't look at me like that! I'm not doing this because I like you or anything... b-baka! Take THIS!"),
    ("melancholy", "Sigh... what is the point of any of this? Sins, virtues, berries... it's all so exhausting. Just let the void swallow us.")
]

def _render_combat_hp_bar(cur: int, max_val: int, length: int = 10) -> str:
    cur = max(0, min(max_val, cur))
    filled = int((cur / max_val) * length) if max_val > 0 else 0
    empty = length - filled
    return f"`[{'█' * filled}{'░' * empty}]` {cur}/{max_val}"

async def check_boss_trigger(message, client, user_id: str) -> bool:
    """
    Checks if Juny, Heaven's Worst Angel, appears to claim the user.
    - If 20-25 Sin: 10% chance per action.
    - If 26-30 Sin: 100% chance (Juny will come to take you).
    """
    if user_id in _ACTIVE_BOSS_FIGHTS or user_id in _PENDING_BOSS_ENCOUNTERS:
        return False
    stats = await _get_user_stats(user_id)
    _, eff_s = get_effective_morality(stats)
    if eff_s < 20:
        return False

    chance = 1.0 if eff_s >= 26 else 0.10
    if random.random() < chance:
        await start_boss_encounter(message, client, user_id, eff_s)
        return True
    return False

class JunyEncounterView(View):
    def __init__(self, user_id: str):
        super().__init__(timeout=300)
        self.user_id = user_id

    @discord.ui.button(label="Plead", emoji="🙏", style=discord.ButtonStyle.primary)
    async def plead_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("This is not your encounter with Juny!", ephemeral=True)
            return
        await interaction.response.defer()
        await process_boss_choice(interaction.message, interaction.client, self.user_id, "plead", view=self)

    @discord.ui.button(label="Fight", emoji="⚔️", style=discord.ButtonStyle.danger)
    async def fight_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("This is not your encounter with Juny!", ephemeral=True)
            return
        await interaction.response.defer()
        await process_boss_choice(interaction.message, interaction.client, self.user_id, "fight", view=self)

    @discord.ui.button(label="Call Aid", emoji="📣", style=discord.ButtonStyle.success)
    async def callaid_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("This is not your encounter with Juny!", ephemeral=True)
            return
        view = JunyCallAidSelectView(self.user_id, max_allies=3, from_encounter=True)
        await interaction.response.send_message(
            "📣 **SUMMON REINFORCEMENTS!**\nSelect up to 3 allies from the dropdown below to join you in battle against Juny!",
            view=view,
            ephemeral=True
        )

    @discord.ui.button(label="Negotiate", emoji="📜", style=discord.ButtonStyle.secondary)
    async def negotiate_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("This is not your encounter with Juny!", ephemeral=True)
            return
        await interaction.response.defer()
        await process_boss_choice(interaction.message, interaction.client, self.user_id, "negotiate", view=self)

async def start_boss_encounter(message, client, user_id: str, eff_s: int):
    """Initial encounter when Juny appears before combat."""
    _PENDING_BOSS_ENCOUNTERS[user_id] = {
        "user_id": user_id,
        "sin": eff_s,
        "time": time.time()
    }
    view = JunyEncounterView(user_id)
    embed = discord.Embed(
        title="😈⚡ JUNY, HEAVEN'S WORST ANGEL DESCENDS! ⚡😈",
        description=(
            f"Black and crimson feathers drift from a shattered dimensional rift in the sky!\n"
            f"With twisted golden halos and dark obsidian wings, **Juny** crashes to the earth before <@{user_id}>!\n\n"
            f"*\"Well, well, well... look what the underworld dragged in. You thought you could hoard **{eff_s}/30 Sin** without consequences?\n"
            f"I am **Juny, Heaven's Worst Angel**, and your soul's overdue invoice has ARRIVED!\"*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=0x990000
    )
    embed.add_field(
        name="😈 Juny's Stats",
        value="• ❤️ **HP:** `1,000 / 1,000`\n• 🛡️ **DEF:** `500`\n• ⚔️ **ATK:** `333`",
        inline=True
    )
    embed.add_field(
        name="🛡️ Your Base Combat Stats",
        value="• ❤️ **HP:** `100 / 100`\n• 🛡️ **DEF:** `25`\n• ⚔️ **ATK:** `25`\n• 💨 **Dodge:** `8%`",
        inline=True
    )
    embed.add_field(
        name="Choose Your Fate",
        value=(
            "• **🙏 Plead (`y!plead`):** Beg on your knees for mercy. Juny might spare you... for a steep price.\n"
            "• **⚔️ Fight (`y!fight`):** Refuse to submit and challenge Heaven's Worst Angel to combat!\n"
            "• **📣 Call Aid (`y!call aid`):** Summon comrades to your side before battle begins!\n"
            "• **📜 Negotiate (`y!negotiate`):** Sign a dark celestial contract with Juny."
        ),
        inline=False
    )
    embed.set_footer(text="Juny Boss Encounter • Click a button below or type y!plead / y!fight / y!call aid / y!negotiate")
    sent = await _safe_send_reply(message, embed=embed, view=view)
    _PENDING_BOSS_ENCOUNTERS[user_id]["message"] = sent

async def process_boss_choice(message, client, user_id: str, choice: str, view: Optional[View] = None):
    encounter = _PENDING_BOSS_ENCOUNTERS.pop(user_id, None)
    if not encounter:
        return

    if view:
        for child in view.children:
            child.disabled = True

    stats = await _get_user_stats(user_id)
    inv = stats.get("inventory", {})

    if choice == "plead":
        has_coupon = inv.get("coupon", 0) > 0
        base_chance = 0.20 if has_coupon else 0.15
        if has_coupon:
            async with _LOCK:
                _USER_STATS[user_id]["inventory"]["coupon"] -= 1
                if _USER_STATS[user_id]["inventory"]["coupon"] <= 0:
                    _USER_STATS[user_id]["inventory"].pop("coupon", None)
                _save_data_sync(_USER_STATS)

        if random.random() < base_chance:
            user_berries = stats.get("berries", 0)
            cost = max(1, int(user_berries * 0.65)) if user_berries > 0 else 0
            cur_virtue = stats.get("virtue", 0)

            await _update_user_stats(
                user_id,
                berries_delta=-cost,
                sin_delta=-5,
                virtue_delta=-cur_virtue
            )
            async with _LOCK:
                _USER_STATS[user_id]["bad_luck_actions"] = 15
                _USER_STATS[user_id]["pleaded_juny_success"] = _USER_STATS[user_id].get("pleaded_juny_success", 0) + 1
                _save_data_sync(_USER_STATS)

            unlocked = await check_and_award_achievements(user_id)
            banner = format_achievement_banner(unlocked)

            coupon_note = "\n🎟️ *You presented your 'Coupon for 1 Free Apology'! Juny snickered, boosting your plea chance!*" if has_coupon else ""
            desc = (
                f"🙏 **PLEA HEARD... WITH A HEFTY TOLL!** 🙏\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"*Juny stares down at you with a mocking smirk, twirling an obsidian feather.*{coupon_note}\n\n"
                f"\"Pfft! AHAHAHAHA! Look at you groveling on your knees! It's so pathetic it's almost adorable!\n"
                f"Fine! I'll spare your soul today, mortal... but as a tribute fine, **65% of your berries belong to ME**! And don't think you're innocent now—your virtue is wiped, and bad luck will dog your steps!\"\n\n"
                f"• 🫐 **Berries Confiscated:** `-{cost:,}` 🫐 (65%)\n"
                f"• ❤️‍🔥 **Sin Reduced:** `-5 Sin`\n"
                f"• 💖 **Virtue:** `Reset to 0`\n"
                f"• 🌧️ **Cursed:** `15 Actions of Bad Luck!`\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━{banner}"
            )
            await _safe_send_reply(message, desc)
            return
        else:
            desc = (
                f"⚡ **PLEA REJECTED! PREPARE TO DIE!** ⚡\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"*Juny aims her obsidian staff right at your throat and cackles maliciously!*\n\n"
                f"\"Did you really think a few crocodile tears would wipe away your filth?! Angels don't do charity!\n"
                f"Draw your weapons or prepare to be dragged straight into the abyss!\"\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            await _safe_send_reply(message, desc)
            await start_boss_combat(message, client, user_id)
            return

    elif choice == "negotiate":
        async with _LOCK:
            u_stat = _USER_STATS.get(user_id, {})
            u_stat["berries"] = 0
            u_stat["sin"] = 0
            u_stat["virtue"] = 0
            u_stat["title"] = "Devil's Slave"
            u_inv = u_stat.setdefault("inventory", {})
            u_inv["devil_contract"] = u_inv.get("devil_contract", 0) + 1
            u_stat["dark_bargain"] = True
            _save_data_sync(_USER_STATS)

        unlocked = await check_and_award_achievements(user_id)
        banner = format_achievement_banner(unlocked)

        desc = (
            f"📜 **PACT SEALED — DEVIL'S SLAVE!** 📜\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"*Juny unfurls a pitch-black parchment burning with violet hellfire.*\n\n"
            f"\"A bargain? Oh, I LOVE mortals who know how to strike a deal!\n"
            f"Sign here in your own blood. From this moment forth, every single berry in your pouch is forfeited, your karma is erased, and your soul belongs to Juny!\"\n\n"
            f"• 🫐 **Berries:** `Reset to 0 🫐`\n"
            f"• ⚖️ **Karma (Sin & Virtue):** `Reset to 0`\n"
            f"• 📜 **Item Received:** `Devil's Contract` *(Bound for eternity)*\n"
            f"• ⛓️ **Title Granted:** `Devil's Slave`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await _safe_send_reply(message, desc)
        return

    elif choice == "fight":
        await start_boss_combat(message, client, user_id)
        return

class JunyCombatView(View):
    def __init__(self, host_id: str):
        super().__init__(timeout=600)
        self.host_id = host_id

    async def on_timeout(self):
        combat = _ACTIVE_BOSS_FIGHTS.pop(self.host_id, None)
        if combat:
            for child in self.children:
                child.disabled = True

    @discord.ui.button(label="Attack", emoji="⚔️", style=discord.ButtonStyle.danger)
    async def attack_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = str(interaction.user.id)
        combat = _ACTIVE_BOSS_FIGHTS.get(self.host_id)
        if not combat or uid not in combat["party"]:
            await interaction.response.send_message("You are not part of this battle party!", ephemeral=True)
            return
        if not combat["party"][uid]["alive"]:
            await interaction.response.send_message("You have fallen in battle and cannot act!", ephemeral=True)
            return
        await interaction.response.defer()
        await execute_combat_round(interaction.message, interaction.client, self.host_id, uid, "attack", view=self)

    @discord.ui.button(label="Dodge", emoji="💨", style=discord.ButtonStyle.primary)
    async def dodge_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = str(interaction.user.id)
        combat = _ACTIVE_BOSS_FIGHTS.get(self.host_id)
        if not combat or uid not in combat["party"]:
            await interaction.response.send_message("You are not part of this battle party!", ephemeral=True)
            return
        if not combat["party"][uid]["alive"]:
            await interaction.response.send_message("You have fallen in battle and cannot act!", ephemeral=True)
            return
        await interaction.response.defer()
        await execute_combat_round(interaction.message, interaction.client, self.host_id, uid, "dodge", view=self)

    @discord.ui.button(label="Use Item", emoji="🎒", style=discord.ButtonStyle.success)
    async def item_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = str(interaction.user.id)
        combat = _ACTIVE_BOSS_FIGHTS.get(self.host_id)
        if not combat or uid not in combat["party"]:
            await interaction.response.send_message("You are not part of this battle party!", ephemeral=True)
            return
        if not combat["party"][uid]["alive"]:
            await interaction.response.send_message("You have fallen in battle and cannot act!", ephemeral=True)
            return
        stats = await _get_user_stats(uid)
        inv = stats.get("inventory", {})
        usable = [k for k in ("elixir", "powder", "ironbrew", "adrenaline", "hammer", "sand") if inv.get(k, 0) > 0]
        if not usable:
            await interaction.response.send_message("You don't have any combat consumables in your pouch! Buy some at `y!shop`!", ephemeral=True)
            return
        chosen = usable[0]
        await interaction.response.defer()
        await execute_combat_round(interaction.message, interaction.client, self.host_id, uid, "item", item_key=chosen, view=self)

    @discord.ui.button(label="Call Aid", emoji="📣", style=discord.ButtonStyle.secondary)
    async def callaid_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = str(interaction.user.id)
        combat = _ACTIVE_BOSS_FIGHTS.get(self.host_id)
        if not combat or uid not in combat["party"]:
            await interaction.response.send_message("You are not part of this battle party!", ephemeral=True)
            return
        if not combat["party"][uid]["alive"]:
            await interaction.response.send_message("You have fallen in battle and cannot act!", ephemeral=True)
            return
        current_party = len(combat["party"])
        if current_party >= 4:
            await interaction.response.send_message("Your battle party is already full (max 4 fighters)!", ephemeral=True)
            return
        max_slots = 4 - current_party
        view = JunyCallAidSelectView(self.host_id, max_allies=max_slots, from_encounter=False)
        await interaction.response.send_message(
            f"📣 **SUMMON REINFORCEMENTS!**\nSelect up to {max_slots} allies from the menu below to join the battle against Juny, or type `y!call aid @friend` in chat!",
            view=view,
            ephemeral=True
        )

class JunyAidInviteView(View):
    def __init__(self, host_id: str, target_user_id: str):
        super().__init__(timeout=300)
        self.host_id = host_id
        self.target_user_id = target_user_id

    @discord.ui.button(label="Help!", emoji="🤝", style=discord.ButtonStyle.success)
    async def help_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.target_user_id:
            await interaction.response.send_message("This summons was not meant for you!", ephemeral=True)
            return
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        await join_boss_fight(interaction.message, self.host_id, self.target_user_id, interaction.user.display_name)

    @discord.ui.button(label="Chicken Out", emoji="🐔", style=discord.ButtonStyle.danger)
    async def chicken_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.target_user_id:
            await interaction.response.send_message("This summons was not meant for you!", ephemeral=True)
            return
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        await chicken_out_boss_fight(interaction.message, self.host_id, self.target_user_id, interaction.user.display_name)

class JunyCallAidSelectView(View):
    def __init__(self, host_id: str, max_allies: int = 3, from_encounter: bool = False):
        super().__init__(timeout=300)
        self.host_id = host_id
        self.from_encounter = from_encounter
        max_val = max(1, min(3, max_allies))
        self.select = discord.ui.UserSelect(
            placeholder=f"Select up to {max_val} allies to summon...",
            min_values=1,
            max_values=max_val
        )
        self.select.callback = self.on_select_users
        self.add_item(self.select)

    async def on_select_users(self, interaction: discord.Interaction):
        selected_members = self.select.values
        if not selected_members:
            await interaction.response.send_message("No allies selected!", ephemeral=True)
            return

        # If calling aid from encounter, start combat first
        if self.from_encounter:
            encounter = _PENDING_BOSS_ENCOUNTERS.pop(self.host_id, None)
            if encounter:
                await start_boss_combat(interaction.message, interaction.client, self.host_id)

        combat = _ACTIVE_BOSS_FIGHTS.get(self.host_id)
        if not combat:
            await interaction.response.send_message("Boss fight is no longer active!", ephemeral=True)
            return

        valid_targets = []
        for m in selected_members:
            mid = str(m.id)
            if getattr(m, "bot", False):
                continue
            if mid == str(interaction.user.id) or mid in combat["party"]:
                continue
            valid_targets.append(m)
            if len(combat["party"]) + len(valid_targets) >= 4:
                break

        if not valid_targets:
            await interaction.response.send_message("All selected members are either bots, already in the party, or yourself!", ephemeral=True)
            return

        # Disable selection on this view
        for child in self.children:
            child.disabled = True

        try:
            await interaction.response.edit_message(
                content=f"📣 Summons sent to: {', '.join(t.mention for t in valid_targets)}! They can click **[Help!]** in chat to join immediately.",
                view=self
            )
        except Exception:
            try:
                await interaction.response.send_message(
                    f"📣 Summons sent to: {', '.join(t.mention for t in valid_targets)}!",
                    ephemeral=True
                )
            except Exception:
                pass

        # Send invite embeds to channel for each target
        for t in valid_targets:
            invite_view = JunyAidInviteView(self.host_id, str(t.id))
            embed = discord.Embed(
                title="📣 SUMMONS TO BATTLE: AID YOUR COMRADE!",
                description=(
                    f"{interaction.user.mention} is locked in mortal combat with **Juny, Heaven's Worst Angel**!\n"
                    f"They have called upon {t.mention} to stand by their side in the fray!\n\n"
                    f"• Click **Help!** to join the fight with 100 HP, 25 DEF, 25 ATK!\n"
                    f"• Click **Chicken Out** to flee like a coward (+1 ❤️‍🔥 Sin)!"
                ),
                color=0xF59E0B
            )
            if interaction.channel:
                await interaction.channel.send(content=f"{t.mention} **You have been summoned to battle!**", embed=embed, view=invite_view)

async def start_boss_combat(message, client, host_id: str):
    """Initializes and begins turn-based combat with Juny."""
    host_user = None
    if getattr(message, "guild", None):
        try:
            host_user = message.guild.get_member(int(host_id))
        except Exception:
            pass
    if not host_user and client:
        try:
            host_user = client.get_user(int(host_id))
        except Exception:
            pass
    if not host_user and getattr(message, "author", None) and str(message.author.id) == host_id:
        host_user = message.author
    name = getattr(host_user, "display_name", getattr(host_user, "name", "Hero"))

    combat_state = {
        "host_id": host_id,
        "channel_id": message.channel.id,
        "boss": {
            "name": "Juny, Heaven's Worst Angel",
            "hp": 1000,
            "max_hp": 1000,
            "def": 500,
            "atk": 333,
            "turn": 1,
            "blinded": False,
            "shielded": False
        },
        "party": {
            host_id: {
                "name": name,
                "hp": 100,
                "max_hp": 100,
                "atk": 25,
                "def": 25,
                "dodge": 0.08,
                "alive": True,
                "is_dodging": False,
                "iron_turns": 0,
                "adrenaline_turns": 0,
                "burn_turns": 0
            }
        },
        "log": [f"⚔️ **Battle commences!** Juny brandishes her Obsidian Staff with a wicked laugh!"],
        "message": None
    }
    _ACTIVE_BOSS_FIGHTS[host_id] = combat_state

    view = JunyCombatView(host_id)
    embed = _build_combat_embed(combat_state)
    sent = await _safe_send_reply(message, embed=embed, view=view)
    combat_state["message"] = sent

def _build_combat_embed(combat: dict) -> discord.Embed:
    boss = combat["boss"]
    turn = boss["turn"]
    mood_key, mood_quote = JUNY_MOODS[((turn - 1) // 2) % len(JUNY_MOODS)]

    embed = discord.Embed(
        title=f"⚔️ BOSS FIGHT: JUNY, HEAVEN'S WORST ANGEL ⚔️ (Turn {turn})",
        description=f"😈 *Mood: {mood_key.title()}*\n> \"{mood_quote}\"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        color=0x990000
    )

    boss_bar = _render_combat_hp_bar(boss["hp"], boss["max_hp"], 12)
    boss_status = []
    if boss.get("blinded"):
        boss_status.append("🏖️ Blinded")
    if boss.get("shielded"):
        boss_status.append("🛡️ Sacred Barrier (-50% DMG)")
    b_stat_str = f" *({' | '.join(boss_status)})*" if boss_status else ""

    embed.add_field(
        name=f"😈 {boss['name']} — {boss_bar}{b_stat_str}",
        value=f"• 🛡️ DEF: `{boss['def']}` | ⚔️ ATK: `{boss['atk']}`",
        inline=False
    )

    party_lines = []
    for uid, p in combat["party"].items():
        status_icon = "🟢" if p["alive"] else "💀"
        hp_bar = _render_combat_hp_bar(p["hp"], p["max_hp"], 8)
        buffs = []
        if p.get("is_dodging"):
            buffs.append("💨 Evasive")
        if p.get("iron_turns", 0) > 0:
            buffs.append(f"🛡️ Iron ({p['iron_turns']}t)")
        if p.get("adrenaline_turns", 0) > 0:
            buffs.append(f"💉 Adrenaline ({p['adrenaline_turns']}t)")
        if p.get("burn_turns", 0) > 0:
            buffs.append(f"🔥 Burn ({p['burn_turns']}t)")
        buff_txt = f" [{', '.join(buffs)}]" if buffs else ""
        party_lines.append(f"{status_icon} **{p['name']}**: {hp_bar}{buff_txt}")

    embed.add_field(
        name=f"🛡️ Battle Party ({len([p for p in combat['party'].values() if p['alive']])}/{len(combat['party'])} Alive)",
        value="\n".join(party_lines) if party_lines else "No fighters alive!",
        inline=False
    )

    recent_logs = combat["log"][-4:]
    embed.add_field(
        name="📜 Combat Log",
        value="\n".join(recent_logs) if recent_logs else "*Waiting for first action...*",
        inline=False
    )
    embed.set_footer(text="Combat Controls • Click Attack, Dodge, Item, or Call Aid | y!attack, y!dodge, y!useitem")
    return embed

async def execute_combat_round(message, client, host_id: str, acting_uid: str, action: str, item_key: str = "", view: Optional[View] = None):
    combat = _ACTIVE_BOSS_FIGHTS.get(host_id)
    if not combat:
        return
    boss = combat["boss"]
    party = combat["party"]
    player = party.get(acting_uid)
    if not player or not player["alive"]:
        return

    # ── Player Turn Action ──
    stats = await _get_user_stats(acting_uid)
    inv = stats.get("inventory", {})

    if action == "attack":
        # Cardboard Sword Check: snaps with a squeak!
        if inv.get("sword", 0) > 0:
            async with _LOCK:
                _USER_STATS[acting_uid]["inventory"].pop("sword", None)
                _USER_STATS[acting_uid]["inventory"]["cardboard_shards"] = _USER_STATS[acting_uid]["inventory"].get("cardboard_shards", 0) + 1
                _USER_STATS[acting_uid]["scammed_cardboard"] = True
                _save_data_sync(_USER_STATS)
            await check_and_award_achievements(acting_uid)
            combat["log"].append(
                f"🗡️ **{player['name']}** swung the 5 Billion Berry 'Legendary Sword' with all their might!\n"
                f"*SQUEEEEEAAAK! SNAP!* The blade bent like wet cardboard and burst into confetti! **0 Damage dealt! You got completely scammed!**"
            )
        else:
            base_atk = player["atk"] + (35 if player.get("adrenaline_turns", 0) > 0 else 0)
            dmg = max(15, int((base_atk * 2.8) * random.uniform(0.85, 1.25)))
            is_crit = (random.random() < 0.15)
            if is_crit:
                dmg = int(dmg * 1.8)
            if boss.get("shielded"):
                dmg = max(10, int(dmg * 0.5))
            boss["hp"] = max(0, boss["hp"] - dmg)
            crit_txt = " 💥 **CRITICAL HIT!**" if is_crit else ""
            combat["log"].append(f"⚔️ **{player['name']}** attacked Juny for **{dmg:,} DMG**!{crit_txt}")

    elif action == "dodge":
        player["is_dodging"] = True
        combat["log"].append(f"💨 **{player['name']}** took an evasive roll stance (+45% Dodge this turn)!")

    elif action == "item":
        if inv.get(item_key, 0) > 0:
            async with _LOCK:
                _USER_STATS[acting_uid]["inventory"][item_key] -= 1
                if _USER_STATS[acting_uid]["inventory"][item_key] <= 0:
                    _USER_STATS[acting_uid]["inventory"].pop(item_key, None)
                _save_data_sync(_USER_STATS)

            if item_key == "ward":
                player["shield_active"] = True
                combat["log"].append(f"🛡️ **{player['name']}** raised the Heavenly Shield, creating an impenetrable celestial barrier!")
            elif item_key == "elixir":
                heal = min(player["max_hp"] - player["hp"], 75)
                player["hp"] += heal
                combat["log"].append(f"🧪 **{player['name']}** drank Archangel's Elixir, restoring **+{heal} HP**!")
            elif item_key == "powder":
                boss["hp"] = max(0, boss["hp"] - 150)
                combat["log"].append(f"✨ **{player['name']}** detonated Smite Powder for **150 TRUE DAMAGE** directly to Juny!")
            elif item_key == "ironbrew":
                player["iron_turns"] = 3
                combat["log"].append(f"🛡️ **{player['name']}** drank Aegis Iron Brew, gaining **+50 DEF** for 3 turns!")
            elif item_key == "adrenaline":
                player["adrenaline_turns"] = 3
                combat["log"].append(f"💉 **{player['name']}** injected Adrenaline, gaining **+35 ATK & +15% Dodge** for 3 turns!")
            elif item_key == "sand":
                boss["blinded"] = True
                combat["log"].append(f"🏖️ **{player['name']}** tossed Pocket Sand into Juny's eyes! She is **Blinded** for her next turn!")
            elif item_key == "hammer":
                boss["hp"] = max(0, boss["hp"] - 1)
                combat["log"].append(f"🔨 **{player['name']}** whacked Juny with a Squeaky Rubber Hammer for **1 DMG**! *SQUEEEEAK!*")
        else:
            combat["log"].append(f"❌ **{player['name']}** reached into their bag for `{item_key}` but found nothing!")

    # Check if Juny is defeated
    if boss["hp"] <= 0:
        await resolve_boss_victory(message, client, host_id)
        return

    # ── Juny's Boss Turn ──
    boss["shielded"] = False

    # Apply player burns
    for p in party.values():
        if p["alive"] and p.get("burn_turns", 0) > 0:
            p["hp"] = max(0, p["hp"] - 10)
            p["burn_turns"] -= 1
            combat["log"].append(f"🔥 **{p['name']}** took 10 Holy Burn damage!")
            if p["hp"] <= 0:
                p["alive"] = False
                combat["log"].append(f"💀 **{p['name']}** burned to death!")

    living_players = [p for p in party.values() if p["alive"]]
    if not living_players:
        await resolve_boss_defeat(message, client, host_id)
        return

    if boss.get("blinded"):
        boss["blinded"] = False
        combat["log"].append("🏖️ Juny furiously rubbed the sand from her eyes! Her attack **MISSED COMPLETELY**!")
    else:
        # Juny Attack Selection
        is_apocalypse = (boss["hp"] < 300 and random.random() < 0.40)
        if is_apocalypse:
            combat["log"].append("🌌 **TWILIGHT APOCALYPSE!** Juny's halo shatters into a violet demonic vortex hitting the entire party!")
            for target in list(living_players):
                eff_dodge = target["dodge"] + (0.45 if target.get("is_dodging") else 0) + (0.15 if target.get("adrenaline_turns", 0) > 0 else 0)
                if random.random() < eff_dodge:
                    combat["log"].append(f"💨 **{target['name']}** dodged the apocalypse shockwave!")
                else:
                    t_uid = None
                    for uid, p in party.items():
                        if p is target:
                            t_uid = uid
                            break
                    t_stats = await _get_user_stats(t_uid) if t_uid else {}
                    has_shield = target.get("shield_active") or (t_stats.get("inventory", {}).get("ward", 0) > 0)

                    if has_shield:
                        if t_uid and t_stats.get("inventory", {}).get("ward", 0) > 0:
                            async with _LOCK:
                                _USER_STATS[t_uid]["inventory"]["ward"] -= 1
                                if _USER_STATS[t_uid]["inventory"]["ward"] <= 0:
                                    _USER_STATS[t_uid]["inventory"].pop("ward", None)
                                _save_data_sync(_USER_STATS)
                        target["shield_active"] = False

                        _, t_sin = get_effective_morality(t_stats)
                        corr_res = resolve_sin_shield_corruption(t_sin)
                        if corr_res["corrupted"]:
                            if t_uid:
                                async with _LOCK:
                                    _USER_STATS[t_uid]["ward_corrupted_count"] = _USER_STATS[t_uid].get("ward_corrupted_count", 0) + 1
                                    _save_data_sync(_USER_STATS)
                                await check_and_award_achievements(t_uid)

                            outcome = corr_res["outcome"]
                            if outcome == "catastrophic_explosion":
                                target["hp"] -= 25
                                combat["log"].append(
                                    f"💬 **{target['name']}**: *\"I have prepared for this.\"*\n"
                                    f"😈 **Juny-HWA**: *\"Have you?\"*\n"
                                    f"💥 **⚠️ Your Heavenly Shield has been corrupted by your sins! IT FUCKING EXPLODES!**"
                                )
                                eff_def = target["def"] + (50 if target.get("iron_turns", 0) > 0 else 0)
                                raw_dmg = random.randint(45, 65)
                                dmg = max(15, raw_dmg - int(eff_def * 0.3))
                                target["hp"] -= dmg
                                combat["log"].append(f"💥 **{target['name']}** took full apocalypse blast for **{dmg} DMG**!")
                                await _check_player_death(host_id, target, combat)
                            elif outcome == "partial":
                                eff_def = target["def"] + (50 if target.get("iron_turns", 0) > 0 else 0)
                                raw_dmg = random.randint(45, 65)
                                dmg = max(8, (raw_dmg - int(eff_def * 0.3)) // 2)
                                target["hp"] -= dmg
                                combat["log"].append(f"⚠️ **{target['name']}**'s corrupted Heavenly Shield absorbed 50% of the apocalypse! Took **{dmg} DMG**!")
                                await _check_player_death(host_id, target, combat)
                            elif outcome == "fails":
                                combat["log"].append(f"⚠️ **{target['name']}**'s corrupted Heavenly Shield sputtered and failed to activate!")
                                eff_def = target["def"] + (50 if target.get("iron_turns", 0) > 0 else 0)
                                raw_dmg = random.randint(45, 65)
                                dmg = max(15, raw_dmg - int(eff_def * 0.3))
                                target["hp"] -= dmg
                                combat["log"].append(f"💥 **{target['name']}** was blasted for **{dmg} DMG**!")
                                await _check_player_death(host_id, target, combat)
                            elif outcome == "breaks_after":
                                combat["log"].append(f"⚠️ **{target['name']}**'s Heavenly Shield absorbed the apocalypse shockwave, then shattered completely!")
                            elif outcome == "penalty":
                                target["hp"] -= 15
                                target["burn_turns"] = 2
                                combat["log"].append(f"⚠️ **{target['name']}**'s Heavenly Shield absorbed the apocalypse, but backlash dealt 15 recoil DMG!")
                                await _check_player_death(host_id, target, combat)
                        else:
                            combat["log"].append(f"🛡️ **{target['name']}**'s Heavenly Shield shone with pure celestial light, **BLOCKING 100% OF THE APOCALYPSE**!")
                    else:
                        eff_def = target["def"] + (50 if target.get("iron_turns", 0) > 0 else 0)
                        raw_dmg = random.randint(45, 65)
                        dmg = max(15, raw_dmg - int(eff_def * 0.3))
                        target["hp"] -= dmg
                        combat["log"].append(f"💥 **{target['name']}** was blasted for **{dmg} DMG**!")
                        await _check_player_death(host_id, target, combat)
        else:
            target = random.choice(living_players)
            attacks = [
                ("Divine Retribution", "holy flame pillars", 35, "burn"),
                ("Celestial Onslaught", "a crushing staff slam", 42, "normal"),
                ("Echoing Lament", "a soul-siphoning vampiric wail", 35, "drain"),
                ("Prismatic Wings", "exploding crystal feathers", 30, "normal"),
                ("Radiant Javelin", "a piercing holy spear", 36, "normal"),
                ("Divine Smite", "a thunderous lightning arc", 32, "normal"),
                ("Sacred Barrier", "a holy defensive shell", 0, "shield"),
                ("Halo Boomerang", "a razor-sharp spinning golden halo cleaving the air", 45, "normal"),
                ("Tears of the Fallen", "a torrential downpour of cursed acidic holy tears", 38, "burn"),
                ("Seraphic Guillotine", "a descending celestial blade slicing down from the sky", 54, "normal"),
                ("Obsidian Meteor Rain", "dark burning stardust raining violently across the field", 48, "burn"),
                ("Soul Siphon", "ethereal chains ripping life essence from your body", 40, "drain"),
                ("Cataclysmic Descent", "a sonic shockwave divebomb that shakes the earth", 50, "normal"),
                ("Black Sun Eclipse", "blinding dark ultraviolet rays blotting out the heavens", 42, "normal"),
                ("Divine Mockery", "a cruel condescending laugh echoing straight through your pride", 28, "mockery"),
                ("Judgement Pillar", "a column of blinding pure white wrath incinerating everything", 48, "burn"),
                ("Fallen Angel's Embrace", "a suffocating grip of shadow wings squeezing the breath from your lungs", 44, "drain"),
                ("Heaven's Wrath", "a deadly barrage of falling holy spears devastating the arena", 46, "normal"),
                ("Cursed Cherub Swarm", "a legion of weeping stone statues swarming your defenses", 36, "normal"),
                ("Wrath of the Exiled", "an explosion of pure malice and broken celestial vows", 50, "normal")
            ]
            atk_name, atk_desc, raw_dmg, atk_type = random.choice(attacks)

            if atk_type == "shield":
                boss["shielded"] = True
                combat["log"].append("🛡️ Juny cast **Sacred Barrier**! All incoming damage reduced by 50% next turn!")
            else:
                eff_dodge = target["dodge"] + (0.45 if target.get("is_dodging") else 0) + (0.15 if target.get("adrenaline_turns", 0) > 0 else 0)
                if random.random() < eff_dodge:
                    combat["log"].append(f"💨 Juny unleashed **{atk_name}**, but **{target['name']}** leaped aside and **DODGED**!")
                else:
                    t_uid = None
                    for uid, p in party.items():
                        if p is target:
                            t_uid = uid
                            break
                    t_stats = await _get_user_stats(t_uid) if t_uid else {}
                    has_shield = target.get("shield_active") or (t_stats.get("inventory", {}).get("ward", 0) > 0)

                    if has_shield:
                        if t_uid and t_stats.get("inventory", {}).get("ward", 0) > 0:
                            async with _LOCK:
                                _USER_STATS[t_uid]["inventory"]["ward"] -= 1
                                if _USER_STATS[t_uid]["inventory"]["ward"] <= 0:
                                    _USER_STATS[t_uid]["inventory"].pop("ward", None)
                                _save_data_sync(_USER_STATS)
                        target["shield_active"] = False

                        _, t_sin = get_effective_morality(t_stats)
                        corr_res = resolve_sin_shield_corruption(t_sin)

                        if corr_res["corrupted"]:
                            if t_uid:
                                async with _LOCK:
                                    _USER_STATS[t_uid]["ward_corrupted_count"] = _USER_STATS[t_uid].get("ward_corrupted_count", 0) + 1
                                    _save_data_sync(_USER_STATS)
                                await check_and_award_achievements(t_uid)

                            outcome = corr_res["outcome"]
                            fail_pct = int(corr_res["failure_rate"] * 100)

                            if outcome == "catastrophic_explosion":
                                recoil_dmg = 25
                                target["hp"] -= recoil_dmg
                                combat["log"].append(
                                    f"💬 **{target['name']}**: *\"I have prepared for this.\"*\n"
                                    f"😈 **Juny-HWA**: *\"Have you?\"*\n"
                                    f"💥 **⚠️ Your Heavenly Shield has been corrupted by your sins! IT FUCKING EXPLODES!**\n"
                                    f"*(The dark corruption ({t_sin} ❤️‍🔥, {fail_pct}% failure) triggered a violent blast dealing **{recoil_dmg} recoil DMG** to {target['name']}!)*"
                                )
                                eff_def = target["def"] + (50 if target.get("iron_turns", 0) > 0 else 0)
                                dmg = max(12, raw_dmg - int(eff_def * 0.3))
                                target["hp"] -= dmg
                                combat["log"].append(f"⚡ Juny struck **{target['name']}** with **{atk_name}** for **{dmg} DMG**!")
                                if atk_type == "drain":
                                    boss["hp"] = min(boss["max_hp"], boss["hp"] + 35)
                                    combat["log"].append("🩸 Juny healed **+35 HP** from your siphoned life force!")
                                elif atk_type == "burn":
                                    target["burn_turns"] = 2
                                    combat["log"].append(f"🔥 **{target['name']}** was inflicted with Holy Burn!")
                                elif atk_type == "mockery":
                                    combat["log"].append("😈 Juny points and laughs: *\"Is that really the best you've got? How pathetic!\"*")
                                await _check_player_death(host_id, target, combat)

                            elif outcome == "fails":
                                combat["log"].append(
                                    f"⚠️ **{target['name']}**'s Heavenly Shield was corrupted by their sins ({t_sin} ❤️‍🔥, {fail_pct}% failure)! "
                                    f"The holy barrier sputtered and **FAILED TO ACTIVATE**!"
                                )
                                eff_def = target["def"] + (50 if target.get("iron_turns", 0) > 0 else 0)
                                dmg = max(12, raw_dmg - int(eff_def * 0.3))
                                target["hp"] -= dmg
                                combat["log"].append(f"⚡ Juny struck **{target['name']}** with **{atk_name}** for **{dmg} DMG**!")
                                if atk_type == "drain":
                                    boss["hp"] = min(boss["max_hp"], boss["hp"] + 35)
                                    combat["log"].append("🩸 Juny healed **+35 HP** from your siphoned life force!")
                                elif atk_type == "burn":
                                    target["burn_turns"] = 2
                                    combat["log"].append(f"🔥 **{target['name']}** was inflicted with Holy Burn!")
                                elif atk_type == "mockery":
                                    combat["log"].append("😈 Juny points and laughs: *\"Is that really the best you've got? How pathetic!\"*")
                                await _check_player_death(host_id, target, combat)

                            elif outcome == "partial":
                                eff_def = target["def"] + (50 if target.get("iron_turns", 0) > 0 else 0)
                                full_dmg = max(12, raw_dmg - int(eff_def * 0.3))
                                dmg = max(6, full_dmg // 2)
                                target["hp"] -= dmg
                                combat["log"].append(
                                    f"⚠️ **{target['name']}**'s Heavenly Shield was corrupted by their sins ({t_sin} ❤️‍🔥)! "
                                    f"It cracked under the pressure, **ONLY BLOCKING 50% OF THE DAMAGE**! (**{dmg} DMG** taken)"
                                )
                                await _check_player_death(host_id, target, combat)

                            elif outcome == "breaks_after":
                                combat["log"].append(
                                    f"⚠️ **{target['name']}**'s Heavenly Shield absorbed 100% of **{atk_name}**, but **SHATTERED INTO DUST IMMEDIATELY AFTER ACTIVATION**!"
                                )

                            elif outcome == "penalty":
                                recoil_dmg = 15
                                target["hp"] -= recoil_dmg
                                target["burn_turns"] = 2
                                combat["log"].append(
                                    f"⚠️ **{target['name']}**'s Heavenly Shield blocked **{atk_name}**, but **INFLICTED A DIVINE PENALTY**: {target['name']} took **{recoil_dmg} recoil DMG** and was inflicted with Holy Burn!"
                                )
                                await _check_player_death(host_id, target, combat)

                        else:
                            combat["log"].append(
                                f"🛡️ **{target['name']}**'s Heavenly Shield shone with pure celestial light, **BLOCKING 100% OF THE ATTACK**! (0 DMG taken)"
                            )

                    else:
                        eff_def = target["def"] + (50 if target.get("iron_turns", 0) > 0 else 0)
                        dmg = max(12, raw_dmg - int(eff_def * 0.3))
                        target["hp"] -= dmg
                        combat["log"].append(f"⚡ Juny struck **{target['name']}** with **{atk_name}** for **{dmg} DMG**!")
                        if atk_type == "drain":
                            boss["hp"] = min(boss["max_hp"], boss["hp"] + 35)
                            combat["log"].append("🩸 Juny healed **+35 HP** from your siphoned life force!")
                        elif atk_type == "burn":
                            target["burn_turns"] = 2
                            combat["log"].append(f"🔥 **{target['name']}** was inflicted with Holy Burn!")
                        elif atk_type == "mockery":
                            combat["log"].append("😈 Juny points and laughs: *\"Is that really the best you've got? How pathetic!\"*")
                        await _check_player_death(host_id, target, combat)

    # Turn Cleanup
    for p in party.values():
        p["is_dodging"] = False
        if p.get("iron_turns", 0) > 0:
            p["iron_turns"] -= 1
        if p.get("adrenaline_turns", 0) > 0:
            p["adrenaline_turns"] -= 1
    boss["turn"] += 1

    # Check party wipe
    if not any(p["alive"] for p in party.values()):
        await resolve_boss_defeat(message, client, host_id)
        return

    # Check boss phase shift (< 300 HP Berserk Apocalypse Phase)
    if boss.get("hp", 0) < 300 and not boss.get("apocalypse_phase_entered"):
        boss["apocalypse_phase_entered"] = True
        combat["log"].append("🔥💀 **BOSS PHASE SHIFT: TWILIGHT ENRAGE! Juny enters her berserk final form!**")
        if combat.get("message"):
            try:
                await combat["message"].edit(view=None)
            except Exception:
                pass
        combat["message"] = None  # Forces resend as brand new message below

    # Update Embed & Message
    embed = _build_combat_embed(combat)
    if combat.get("message"):
        try:
            await combat["message"].edit(embed=embed, view=view or JunyCombatView(host_id))
        except Exception:
            sent = await _safe_send_reply(message, embed=embed, view=view or JunyCombatView(host_id))
            combat["message"] = sent
    else:
        sent = await _safe_send_reply(message, embed=embed, view=view or JunyCombatView(host_id))
        combat["message"] = sent

async def _check_player_death(host_id: str, target: dict, combat: dict):
    if target["hp"] <= 0:
        target_uid = None
        for uid, p in combat["party"].items():
            if p is target:
                target_uid = uid
                break
        if target_uid:
            t_stats = await _get_user_stats(target_uid)
            if t_stats.get("inventory", {}).get("feather", 0) > 0:
                async with _LOCK:
                    _USER_STATS[target_uid]["inventory"]["feather"] -= 1
                    if _USER_STATS[target_uid]["inventory"]["feather"] <= 0:
                        _USER_STATS[target_uid]["inventory"].pop("feather", None)
                    _save_data_sync(_USER_STATS)
                target["hp"] = 50
                target["alive"] = True
                combat["log"].append(f"🪶 **{target['name']}**'s Phoenix Feather ignited into glorious flames, **RESURRECTING** them with 50 HP!")
                return
        target["alive"] = False
        combat["log"].append(f"💀 **{target['name']}** was struck down and collapsed in battle!")

async def resolve_boss_victory(message, client, host_id: str):
    combat = _ACTIVE_BOSS_FIGHTS.pop(host_id, None)
    if not combat:
        return

    if combat.get("message"):
        try:
            await combat["message"].edit(view=None)
        except Exception:
            pass

    participants = list(combat["party"].keys())
    horn_recipient = random.choice(participants)

    for uid in participants:
        stats = await _get_user_stats(uid)
        cur_bal = stats.get("berries", 0)
        bal_bonus = max(50, int(cur_bal * 0.30))
        async with _LOCK:
            u_stat = _USER_STATS.get(uid, {})
            u_stat["berries"] = u_stat.get("berries", 0) + bal_bonus
            u_stat["boss_double_bonus_actions"] = 10
            u_stat["title"] = "Daredevil"
            u_stat["defeated_juny"] = True
            if uid == horn_recipient:
                u_stat.setdefault("inventory", {})["devil_horn"] = u_stat.setdefault("inventory", {}).get("devil_horn", 0) + 1
            _save_data_sync(_USER_STATS)
        await check_and_award_achievements(uid, specific_id="daredevil")

    horn_name = combat["party"][horn_recipient]["name"]
    embed = discord.Embed(
        title="🎉👑 VICTORY OVER JUNY, HEAVEN'S WORST ANGEL! 👑🎉",
        description=(
            f"*Juny drops her staff and falls to her knees in sheer disbelief, wings scattering dark ash!*\n\n"
            f"\"N-No way... I was defeated by mere mortals?! This is impossible... b-baka! Take your spoils and GET OUT!\"\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏆 **GLORIOUS SPOILS OF VICTORY:**\n"
            f"• ✨ **Empress Blessing:** `10 Actions of 2x Multiplier on EVERYTHING!`\n"
            f"• 💰 **War Bounty:** `+30% Berries added to pouch for all party members!`\n"
            f"• 🎖️ **Title Granted:** `Daredevil`\n"
            f"• 🏆 **Achievement Unlocked:** `Daredevil`\n"
            f"• 🦹 **Relic Awarded:** <@{horn_recipient}> (`{horn_name}`) claimed **Juny's Devil Horn**! *(+10% permanent combat stats & luck)*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=0xFFD700
    )
    await _safe_send_reply(message, embed=embed)

async def resolve_boss_defeat(message, client, host_id: str):
    combat = _ACTIVE_BOSS_FIGHTS.pop(host_id, None)
    if not combat:
        return

    if combat.get("message"):
        try:
            await combat["message"].edit(view=None)
        except Exception:
            pass

    async with _LOCK:
        h_stat = _USER_STATS.get(host_id, {})
        h_stat["berries"] = 0
        h_stat["sin"] = 0
        h_stat["virtue"] = 0
        h_stat["bad_luck_actions"] = 15
        for uid in combat["party"]:
            if uid != host_id:
                a_stat = _USER_STATS.get(uid, {})
                a_stat["berries"] = a_stat.get("berries", 0) // 2
        _save_data_sync(_USER_STATS)

    embed = discord.Embed(
        title="💀💀 PARTY WIPED — JUNY REAPS YOUR SOULS! 💀💀",
        description=(
            f"*Juny hovers over your fallen party, laughing with manic angelic malice!*\n\n"
            f"\"WUWAHAHAHAHA! Did you really think insects like you could conquer Heaven's Worst Angel?!\n"
            f"Your pouches are stripped, your karma is shattered, and 15 curses of dark luck shall torment your steps!\"\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• ☠️ **Host Penalty:** Berries & Karma wiped to 0! +15 Actions of Bad Luck!\n"
            f"• 💸 **Allies Penalty:** Lost 50% of their berries!\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=0x330000
    )
    await _safe_send_reply(message, embed=embed)

async def handle_boss_callaid(message, client, args: list):
    """Handles y!callaid / y!call aid [@user1 / id1 ...]."""
    author_id = str(message.author.id)
    combat = None
    combat_host = None
    for h_id, c in _ACTIVE_BOSS_FIGHTS.items():
        if author_id in c["party"]:
            combat = c
            combat_host = h_id
            break

    # If not in active combat, check if in pending encounter
    if not combat:
        if author_id in _PENDING_BOSS_ENCOUNTERS:
            encounter = _PENDING_BOSS_ENCOUNTERS.pop(author_id, None)
            await start_boss_combat(message, client, author_id)
            combat = _ACTIVE_BOSS_FIGHTS.get(author_id)
            combat_host = author_id
        else:
            await _safe_send_reply(message, "- *Yuna tilts her head* \"You are not in a boss fight against Juny!\"")
            return

    current_party_size = len(combat["party"])
    if current_party_size >= 4:
        await _safe_send_reply(message, "Your battle party is already full (max 4 fighters)!")
        return

    max_slots = 4 - current_party_size

    targets = []
    # 1. From direct mentions
    if message.mentions:
        for m in message.mentions:
            if not getattr(m, "bot", False) and str(m.id) not in combat["party"] and str(m.id) != author_id:
                if m not in targets:
                    targets.append(m)
                if len(combat["party"]) + len(targets) >= 4:
                    break

    # 2. From args (IDs, usernames, or <@...>)
    if len(combat["party"]) + len(targets) < 4 and args:
        for token in args:
            clean = token.strip()
            if not clean or clean.lower() == "aid":
                continue
            m_match = re.search(r'<@!?(\d{17,20})>', clean)
            target_id = m_match.group(1) if m_match else (clean if re.fullmatch(r'\d{17,20}', clean) else None)
            if target_id and target_id != author_id and target_id not in combat["party"]:
                target_obj = None
                if getattr(message, "guild", None):
                    try:
                        target_obj = message.guild.get_member(int(target_id))
                    except Exception:
                        pass
                if not target_obj and client:
                    try:
                        target_obj = client.get_user(int(target_id))
                    except Exception:
                        pass
                if target_obj and not getattr(target_obj, "bot", False) and target_obj not in targets:
                    targets.append(target_obj)
                    if len(combat["party"]) + len(targets) >= 4:
                        break
            elif not target_id and getattr(message, "guild", None) and getattr(message.guild, "members", None):
                for m in message.guild.members:
                    m_name = getattr(m, "name", "").lower()
                    m_nick = getattr(m, "display_name", "").lower()
                    if (clean.lower() in (m_name, m_nick)) and not getattr(m, "bot", False):
                        if str(m.id) != author_id and str(m.id) not in combat["party"] and m not in targets:
                            targets.append(m)
                            break
                if len(combat["party"]) + len(targets) >= 4:
                    break

    if not targets:
        view = JunyCallAidSelectView(combat_host, max_allies=max_slots, from_encounter=False)
        await _safe_send_reply(
            message,
            content=(
                f"📣 **CALL AID: SELECT ALLIES**\n"
                f"Select up to {max_slots} allies below to summon into battle with Juny, or mention them: `y!call aid @friend`"
            ),
            view=view
        )
        return

    for t in targets:
        view = JunyAidInviteView(combat_host, str(t.id))
        embed = discord.Embed(
            title="📣 SUMMONS TO BATTLE: AID YOUR COMRADE!",
            description=(
                f"{message.author.mention} is locked in mortal combat with **Juny, Heaven's Worst Angel**!\n"
                f"They have called upon {t.mention} to stand by their side in the fray!\n\n"
                f"• Click **Help!** to join the fight with 100 HP, 25 DEF, 25 ATK!\n"
                f"• Click **Chicken Out** to flee like a coward (+1 ❤️‍🔥 Sin)!"
            ),
            color=0xF59E0B
        )
        await _safe_send_reply(message, content=f"{t.mention} **You have been summoned to battle!**", embed=embed, view=view)

async def join_boss_fight(message, host_id: str, ally_id: str, ally_name: str):
    combat = _ACTIVE_BOSS_FIGHTS.get(host_id)
    if not combat:
        return
    if len(combat["party"]) >= 4 or ally_id in combat["party"]:
        return

    async with _LOCK:
        _USER_STATS[ally_id]["joined_boss_fights"] = _USER_STATS[ally_id].get("joined_boss_fights", 0) + 1
        _save_data_sync(_USER_STATS)
    await check_and_award_achievements(ally_id)

    combat["party"][ally_id] = {
        "name": ally_name,
        "hp": 100,
        "max_hp": 100,
        "atk": 25,
        "def": 25,
        "dodge": 0.08,
        "alive": True,
        "is_dodging": False,
        "iron_turns": 0,
        "adrenaline_turns": 0,
        "burn_turns": 0
    }
    combat["log"].append(f"🤝 **{ally_name}** stepped forward bravely and joined the battle party!")
    embed = _build_combat_embed(combat)
    if combat.get("message"):
        try:
            await combat["message"].edit(embed=embed, view=JunyCombatView(host_id))
        except Exception:
            await _safe_send_reply(message, embed=embed, view=JunyCombatView(host_id))
    await _safe_send_reply(message, f"🤝 <@{ally_id}> (**{ally_name}**) answered the call and joined the fight against Juny!")

async def chicken_out_boss_fight(message, host_id: str, ally_id: str, ally_name: str):
    await _update_user_stats(ally_id, sin_delta=1)
    async with _LOCK:
        _USER_STATS[ally_id]["chickened_out_count"] = _USER_STATS[ally_id].get("chickened_out_count", 0) + 1
        _save_data_sync(_USER_STATS)
    unlocked = await check_and_award_achievements(ally_id)
    banner = format_achievement_banner(unlocked)
    combat = _ACTIVE_BOSS_FIGHTS.get(host_id)
    if combat:
        combat["log"].append(f"🐔 **{ally_name}** chicken-ed out and ran away in terror! (+1 ❤️‍🔥 Sin)")
        embed = _build_combat_embed(combat)
        if combat.get("message"):
            try:
                await combat["message"].edit(embed=embed, view=JunyCombatView(host_id))
            except Exception:
                pass
    await _safe_send_reply(message, f"🐔 <@{ally_id}> chicken-ed out and ran away screaming in terror! (+1 ❤️‍🔥 Sin for cowardice!){banner}")

async def handle_boss_attack(message, client, args: list):
    author_id = str(message.author.id)
    combat_host = None
    for h_id, c in _ACTIVE_BOSS_FIGHTS.items():
        if author_id in c["party"]:
            combat_host = h_id
            break
    if not combat_host:
        await _safe_send_reply(message, "- *Yuna tilts her head* \"You are not in a battle against Juny!\"")
        return
    await execute_combat_round(message, client, combat_host, author_id, "attack")

async def handle_boss_dodge(message, client, args: list):
    author_id = str(message.author.id)
    combat_host = None
    for h_id, c in _ACTIVE_BOSS_FIGHTS.items():
        if author_id in c["party"]:
            combat_host = h_id
            break
    if not combat_host:
        await _safe_send_reply(message, "- *Yuna tilts her head* \"You are not in a battle against Juny!\"")
        return
    await execute_combat_round(message, client, combat_host, author_id, "dodge")

async def handle_boss_item(message, client, args: list):
    author_id = str(message.author.id)
    combat_host = None
    for h_id, c in _ACTIVE_BOSS_FIGHTS.items():
        if author_id in c["party"]:
            combat_host = h_id
            break
    if not combat_host:
        await _safe_send_reply(message, "- *Yuna tilts her head* \"You are not in a battle against Juny!\"")
        return

    if not args:
        stats = await _get_user_stats(author_id)
        inv = stats.get("inventory", {})
        usable = [f"`{k}`" for k in ("ward", "elixir", "powder", "ironbrew", "adrenaline", "hammer", "sand") if inv.get(k, 0) > 0]
        avail = ", ".join(usable) if usable else "None"
        await _safe_send_reply(message, f"Specify an item to use: `y!useitem <item>`\nAvailable combat items in your pouch: {avail}")
        return

    item_key = args[0].lower().strip()
    alias_map = {
        "ward": "ward", "shield": "ward", "heavenly": "ward", "heavenlyshield": "ward",
        "elixir": "elixir", "potion": "elixir",
        "powder": "powder", "smite": "powder",
        "ironbrew": "ironbrew", "iron": "ironbrew", "brew": "ironbrew",
        "adrenaline": "adrenaline", "injector": "adrenaline",
        "hammer": "hammer", "rubberhammer": "hammer",
        "sand": "sand", "pocketsand": "sand"
    }
    matched = alias_map.get(item_key, item_key)
    await execute_combat_round(message, client, combat_host, author_id, "item", item_key=matched)

async def handle_boss_status(message, client, args: list):
    author_id = str(message.author.id)
    combat = None
    for h_id, c in _ACTIVE_BOSS_FIGHTS.items():
        if author_id in c["party"]:
            combat = c
            break
    if not combat:
        await _safe_send_reply(message, "- *Yuna tilts her head* \"You do not have an active boss battle with Juny!\"")
        return
# ─── ADMIN & KARMIC CONTROLS ────────────────────────────────────────────────

async def handle_set_sin(message, client, args: list):
    """
    Admin command: y!setsin [@user/id] <amount> or y!set sin [@user/id] <amount>
    Allows the bot owner and server administrators to set/adjust anyone's Sin points (0-30).
    """
    is_admin = False
    author_id = str(message.author.id)
    owner_env = os.getenv("OWNER_ID", "966725838252933190").strip()
    if author_id in (owner_env, "966725838252933190"):
        is_admin = True
    elif message.guild and getattr(message.author.guild_permissions, "administrator", False):
        is_admin = True
    elif client and getattr(client, "is_owner", None):
        try:
            if await client.is_owner(message.author):
                is_admin = True
        except Exception:
            pass

    if not is_admin:
        await _safe_send_reply(
            message,
            "- 🚫 *Yuna slaps the Book of Sins shut!* \"Only the creator and server administrators have the authority to alter mortal sins!\""
        )
        return

    if not args:
        await _safe_send_reply(
            message,
            "- 📖 *Yuna taps the Book of Sins* \"Usage: `y!setsin [@user/ID] <amount>` or `y!set sin [@user/ID] <amount>` (Range: 0–30). Example: `y!setsin @player 20`\""
        )
        return

    target_user = None
    target_id = None
    sin_amount = None

    # 1. Check direct mentions first
    if message.mentions:
        for m in message.mentions:
            if client and client.user and m.id == client.user.id:
                continue
            target_user = m
            target_id = str(m.id)
            break

    # 2. Parse remaining tokens for amount and potential target ID
    remaining_tokens = []
    for token in args:
        clean = token.strip()
        if clean.lower() == "sin":
            continue
        m_match = re.search(r'<@!?(\d{17,20})>', clean)
        if m_match:
            if not target_id:
                target_id = m_match.group(1)
            continue
        if re.fullmatch(r'\d{17,20}', clean):
            if not target_id:
                target_id = clean
                continue
        if clean.isdigit() or (clean.startswith(("+", "-")) and clean[1:].isdigit()):
            if sin_amount is None:
                sin_amount = int(clean)
                continue
        remaining_tokens.append(clean)

    # 3. Check guild members by name if ID still unresolved
    if not target_id and message.guild and getattr(message.guild, "members", None) and remaining_tokens:
        clean_name = " ".join(remaining_tokens).lower()
        try:
            for m in message.guild.members:
                m_name = getattr(m, "name", "").lower()
                m_nick = getattr(m, "display_name", "").lower()
                if clean_name in (m_name, m_nick):
                    target_user = m
                    target_id = str(m.id)
                    break
        except Exception:
            pass

    # 4. Default target to author if only amount was passed
    if not target_id:
        target_user = message.author
        target_id = author_id

    # 5. Validate sin amount
    if sin_amount is None:
        await _safe_send_reply(
            message,
            "- ⚠️ *Yuna tilts her head* \"You must specify a valid number for Sin! Example: `y!setsin @user 20`\""
        )
        return

    new_sin = max(0, min(30, sin_amount))

    # Perform atomic update
    target_stats = await _get_user_stats(target_id)
    old_sin = target_stats.get("sin", 0)

    async with _LOCK:
        u_stat = _USER_STATS.setdefault(target_id, _create_default_user())
        _ensure_user_defaults(u_stat)
        u_stat["sin"] = new_sin
        u_stat["good_actions_needed"] = 0
        u_stat["bad_actions_needed"] = 0
        _save_data_sync(_USER_STATS)

    _log_player_stat_audit(
        target_id,
        "sin",
        old_sin,
        new_sin,
        f"admin_cmd_set_sin by author={author_id}"
    )

    if target_user:
        target_name = getattr(target_user, "display_name", getattr(target_user, "name", str(target_id)))
    else:
        target_name = f"<@{target_id}>"

    title_desc = get_sin_title(new_sin)
    warning_banner = get_sin_warning_banner({"virtue": 0, "sin": new_sin})

    embed = discord.Embed(
        title="🔮 KARMIC MANIPULATION: SIN ADJUSTED 🔮",
        description=(
            f"**Fate has been rewritten in the Celestial Records!**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **Target:** {target_name} (`{target_id}`)\n"
            f"❤️🔥 **Previous Sin:** `{old_sin}`\n"
            f"❤️🔥 **New Sin:** **`{new_sin}/30`**\n"
            f"📜 **Status:** *{title_desc}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"*- Yuna dips her feather quill in dark ink and blows gently on the parchment.*{warning_banner}"
        ),
        color=0x8B0000 if new_sin >= 20 else 0xFF4500
    )
    embed.set_footer(text=f"Admin: {getattr(message.author, 'display_name', getattr(message.author, 'name', author_id))} • Yuna's Book of Sins")
    await _safe_send_reply(message, embed=embed)

# ─── HELP CODEX & GUIDES ────────────────────────────────────────────────────

HELP_COLOR = discord.Color.from_rgb(255, 105, 180) # Yuna's signature vibrant pink

HELP_PAGES_META = [
    {
        "title": "🫐 Yuna's Codex • Economy & Morality (Page 1/6)",
        "desc": "Welcome to **Yuna's official gambling den & moral karma universe**!\nCurrency: **🫐 Berries** | Karma: **💖 Virtue** & **❤️‍🔥 Sin**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "fields": [
            (
                "🫐 Pouch, Profile & Allowance",
                "• `y!balance` (or `y!bal`, `y!profile`, `y!money`) — View berries, virtue, sin, spouse, buffs, and bankruptcies.\n"
                "• `y!daily` (or `y!claim`, `y!allowance`) — Claim daily berries (150 base + streak multiplier up to 500 + marriage bonus).\n"
                "• `y!tasks` (or `y!dailies`, `y!quests`) — Daily checklist (High Roller, Helping Hand, Kind Soul, Vibe Check) & Grand Bounty (+200 🫐, +2 💖).",
                False
            ),
            (
                "💖 Deeds of Virtue & Transfers",
                "• `y!aid @user` — Assist another player (+2% success & payout per Virtue point).\n"
                "• `y!donate <amt>` — Donate berries to randomly gift an active player & earn 💖 Virtue.\n"
                "• `y!give @user <amt>` (or `y!pay`) & `y!trade @user <amt>` — Peer-to-peer berry transfers.",
                False
            ),
            (
                "❤️‍🔥 Thievery & Karmic Records",
                "• `y!steal @user` (or `y!rob`) — Pickpocket another player (defended by Divine Wards & Karmic Aura).\n"
                "• `y!setsin [@user] <amt>` (or `y!set sin`) — [Admin] Adjust mortal Sin points (0–30) in Celestial Records.",
                False
            )
        ]
    },
    {
        "title": "🎰 Yuna's Codex • Casino & Wagering (Page 2/6)",
        "desc": "High-stakes table games, card games, and absurd betting chaos against house dealer Yuna.\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "fields": [
            (
                "💣 Mines Field & 📚 Progressive Wordle",
                "• `y!mines <amt> [mines]` (or `y!mine`) — Interactive 24-tile minefield! Uncover diamonds 💎 to build multipliers, click `💰 Cash Out` before hitting a bomb 💣!\n"
                "• `y!wordle <amt>` (or `y!word`) — Progressive Wordle Gamble across 5 escalating stages (4 to 7 letters)! Solve via `[✏️ Guess Word]` or `y!guess <word>`, cash out or risk for up to **40.0x** + 2 Virtue!\n"
                "• `y!streak [@user]` (or `y!winstreak`) — View active casino win streak, streak bonuses (up to **+50%**), and milestone windfalls!",
                False
            ),
            (
                "🎲 Dice Table & Classic Roulette",
                "• `y!dice <amt> [bet]` (or `y!roll`, `y!craps`) — Absurd 2d6 craps table! Bet Low/High, Lucky 7 (4:1), Doubles, Roll vs Yuna, Exact numbers up to 30:1!\n"
                "• `y!roulette <amt> [bet]` (or `y!wheel`) — 38-pocket wheel! Red/Black, Even/Odd, Columns, Straight number, Crown (000) pays up to **250x**!\n"
                "• `y!blackjack <amt>` (or `y!bj`) — Classic 21 vs Yuna (`y!hit`, `y!stand`) & comedy cards (Uno Reverse, Blue-Eyes Dragon).",
                False
            ),
            (
                "📈 Video Poker, Streaks & Crash",
                "• `y!poker <amt>` (or `y!vp`) — 5-Card Video Poker! Hold cards with buttons or `y!hold`, then `y!draw`! Royal Flush pays **250x**!\n"
                "• `y!higherlower <amt>` (or `y!hl`) — Guess cards (1–13) with escalating streaks up to 20x+! (`y!higher`, `y!lower`, `y!cashout`, `y!hl reset`).\n"
                "• `y!crash <amt>` — Real-time rising rocket multiplier! Click **Cash Out** (`y!cashout`) before cosmic explosion!\n"
                "• `y!coinflip <amt> [choice]` & `y!fight @user` — Absurd coinflips and PvP arena duels.",
                False
            )
        ]
    },
    {
        "title": "🏪 Yuna's Codex • Shop, Inventory & Jobs (Page 3/6)",
        "desc": "Browse mystical curios, consume potent charms, work honest shifts, or fish the pond.\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "fields": [
            (
                "🏪 Curio Shop & Inventory",
                "• `y!shop` — Browse the curio shop (Shield, Clover, Energy Drink, Mask, Diamond, Ring, Bouquet, Truffles, Mirror, Magnet, Loaded Die, Holy Water, Empress Crown).\n"
                "• `y!buy <item> [qty]` — Purchase items with berries (e.g. `y!buy ring` or `y!buy magnet 2`).\n"
                "• `y!inventory` (or `y!inv`) — Inspect your pouch, buffs, and consumable stock.\n"
                "• `y!use <item>` — Consume items: Bouquet (vault bonus), Truffles (reset dates), Mirror (-3 Sin), Magnet (+20% loot), Loaded Die (no snake eyes), Holy Water (anti-corruption).",
                False
            ),
            (
                "💼 Honest Work & Underworld Missions",
                "• `y!work` (or `y!job`, `y!shift`) — Work shifts (+2% wage per Virtue, 25% chance of +1 Virtue, +15% / +25% Ring marriage bonus, +20% Magnet).\n"
                "• `y!crime` (or `y!heist`) — High-risk underworld operations for massive berry loot (+2 Sin).\n"
                "• `y!fish` (or `y!fishing`) — Cast your line into Yuna's pond for rare catches & Dragon Pearls (+1 Virtue).",
                False
            )
        ]
    },
    {
        "title": "💍 Yuna's Codex • Romance & Matrimony (Page 4/6)",
        "desc": "Matrimonial ceremonies, vows, dates, kissing, gifts, shared vaults, and couple operations.\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "fields": [
            (
                "💒 Courtship, Matrimony & Vows",
                "• `y!marry @user` — Propose with Yuna's completely unserious marriage ceremony!\n"
                "• `y!marriage [@user]` (or `y!spouse`, `y!couple`) — View sacred certificate, anniversary & synergy records!\n"
                "• `y!vow <text>` — Etch your eternal couple vow onto the certificate (+1 Virtue)!\n"
                "• `y!divorce` — Pay 10,000 🫐 (or 5,000 with Divorce Insurance) to divorce.",
                False
            ),
            (
                "🌹 Romantic Couple Life & Gifting",
                "• `y!date` (or `y!datenight`) — Take spouse on hilarious dates (+80–220 🫐, +2 Virtue, vault savings)!\n"
                "• `y!kiss [@user]` (or `y!hug`) — Kiss spouse for vault love sparks (+15–35 🫐) or trigger 4K Infidelity alerts!\n"
                "• `y!gift @spouse <amt|item>` (or `y!lovegift`) — Send tax-free berries or shop items with custom love notes!",
                False
            ),
            (
                "💞 Vault & Power Couple Tag-Teams",
                "• `y!shared` (or `y!joint`) — Couple's shared vault with +5% (or +10% with Eternal Diamond) daily yield!\n"
                "• `y!doubleaid @user` (or `y!double aid`) — Team up with spouse for 2x Super Aid (+10% success with Ring)!\n"
                "• `y!doublesteal @victim` (or `y!double steal`) — Tag-team robbery! Snatches 25%–45% of victim's balance!",
                False
            )
        ]
    },
    {
        "title": "😈 Yuna's Codex • Juny Boss Battle (Page 5/6)",
        "desc": "Juny descends to claim your overdue soul when Sin reaches 20+. Turn-based combat & pacts.\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "fields": [
            (
                "⚡ Encounter & Decisions",
                "• `y!boss` (or `y!juny`, `y!combat`) — View active boss battle status, party members & Juny's HP.\n"
                "• `y!plead` — Beg on your knees for mercy. Juny might spare you for a heavy sacrifice.\n"
                "• `y!fight` — Refuse to kneel and challenge Heaven's Worst Angel to combat!\n"
                "• `y!negotiate` — Sign a dark celestial contract with Juny.",
                False
            ),
            (
                "⚔️ Turn-Based Combat & Summons",
                "• `y!attack` (or `y!atk`) — Strike Juny with weapon/holy damage.\n"
                "• `y!dodge` — Enter defensive evasion stance (+40% dodge for 1 round).\n"
                "• `y!useitem <item>` — Use combat consumables: Elixir (+50 HP), Holy Smite (150 True DMG), Sand (Blinds Juny), Rubber Hammer (1 DMG Squeak).\n"
                "• `y!call aid @friends` (or `y!callaid`) — Summon up to 3 allies to join your battle party! (Interactive dropdown menu supported!)",
                False
            )
        ]
    },
    {
        "title": "🎭 Yuna's Codex • Social, Music & Trophies (Page 6/6)",
        "desc": "Unhinged dares, Spotify Kizzy rich presence, server leaderboards, and achievement badges.\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "fields": [
            (
                "🎭 Truth or Dare & Social Wagers",
                "• `y!truth @user [amt] [question]` / `y!truth [amt]` — Truth challenges with peer & AI review!\n"
                "• `y!dare @user [amt] [prompt]` / `y!dare [amt]` — Unhinged dares evaluated by Yuna AI!\n"
                "• `y!checkdare <proof>` & `y!checktruth <answer>` — Submit proof for peer/AI evaluation.\n"
                "• `y!rerolldare`, `y!activedare`, `y!forfeitdare` — Challenge management.",
                False
            ),
            (
                "🎧 Spotify Kizzy RPC & Hall of Fame",
                "• `y!song` (or `y!np`) — Show what Yuna is currently listening to with live timeline progress & cover art.\n"
                "• `y!play <song>` & `y!skip` — Update Yuna's music and Discord status with real covers via Kizzy RPC!\n"
                "• `y!leaderboard` (or `y!lb`) — Top 5 Richest, Saintliest, and Most Sinful mortals.\n"
                "• `y!achievements` (or `y!ach`) — Browse your trophy room (56 collectible achievements!).",
                False
            )
        ]
    },
    {
        "title": "👑 Yuna's Codex • RPG, GoD-HeLL Co-op & Berry Auctions (Page 7/7)",
        "desc": "High-roller berry sinks, progressive co-op dungeons, arena training, and luxury auctions!\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "fields": [
            (
                "👑 Berry Auctions (Luxury Flexes & Easy Bids)",
                "• `y!auction [item]` — View active auction or spotlight an item (e.g. `y!auction spoon` or `y!auction ribbon`).\n"
                "• `y!bid <amount>` or `y!bid <alias> <amount>` — Bid easily (e.g. `y!bid 600m` or `y!bid spoon 600m`). Outbid players get instantly refunded!\n"
                "• `y!bid` Modal button `[ ✍️ Custom Bid ]` — Pop-up bidding modal directly in Discord!\n"
                "• `y!auctioncatalog` — Browse all items with short aliases (`spoon`, `sock`, `peeler`, `air`, `chair`, `toast`, `ribbon`, `crown`, `brooch`, `cup`).",
                False
            ),
            (
                "⚔️ The Arena, Training & Skills",
                "• `y!arena` — View Battle Level, EXP, stats (HP, ATK, DEF, SPD), and training costs.\n"
                "• `y!train [stat]` — Train ATK, DEF, HP, SPD, or All! Cost multiplies exponentially (100 -> 1M -> 1B+ 🫐).\n"
                "• `y!skills` — Browse unlocked Weird Skills (Quack of Doom, Pocket Sand, Cheese Wheel, etc.) and Marital Skills!",
                False
            ),
            (
                "🌋 GoD-HeLL Co-op Dungeon & Battle Shop",
                "• `y!godhell` (or `y!dungeon`) — Descend into GoD-HeLL! 10 stages with scaling monsters & 3 bosses (Mamon, Executioner, Lucifer)!\n"
                "• `y!dcallaid [@users]` (or `[ 🤝 Call Aid ]`) — Summon up to 2 allies into your raid party for +15% combo damage & shared aggro!\n"
                "• `y!djoin [@host]` — Join an open server GoD-HeLL raid party!\n"
                "• `[ ✨ Skill Select ]` Dropdown — Interactive in-combat dropdown menu to select & cast your unlocked skills!\n"
                "• `y!dattack`, `y!dskill [name]`, `y!dheal`, `y!dflee` — Combat turns with real-time party HP bars!\n"
                "• `y!battleshop` & `y!bbuy <item>` — Purchase Weapons, Armor, Accessories, and Dungeon Elixirs.\n"
                "• `y!equip <item>` — Equip combat gear. View your full combat loadout on `y!bal`!",
                False
            )
        ]
    }
]

def build_help_page_embed(page_idx: int) -> discord.Embed:
    page_idx = max(0, min(len(HELP_PAGES_META) - 1, page_idx))
    meta = HELP_PAGES_META[page_idx]
    embed = discord.Embed(
        title=meta["title"],
        description=meta["desc"],
        color=HELP_COLOR
    )
    for fname, fval, finline in meta["fields"]:
        embed.add_field(name=fname, value=fval, inline=finline)
    embed.set_footer(text=f"Page {page_idx + 1}/7 • Type y!help <1-7> or y!help <command> for deep-dive guides!")
    return embed

class YunaHelpPaginationView(View):
    def __init__(self, author_id: str, current_page: int = 0):
        super().__init__(timeout=600)
        self.author_id = author_id
        self.current_page = max(0, min(6, current_page))
        self._build_components()

    def _build_components(self):
        self.clear_items()

        # Category Select Dropdown (Row 0)
        options = [
            discord.SelectOption(
                label="Page 1: Economy & Morality",
                value="0",
                emoji="🫐",
                description="Balance, dailies, tasks, aid, steal, transfers, setsin",
                default=(self.current_page == 0)
            ),
            discord.SelectOption(
                label="Page 2: Casino & Wagers",
                value="1",
                emoji="🎰",
                description="Dice, roulette, poker, higher-lower, coinflip, blackjack, crash",
                default=(self.current_page == 1)
            ),
            discord.SelectOption(
                label="Page 3: Shop, Inventory & Jobs",
                value="2",
                emoji="🏪",
                description="Curio shop, items, consumables, work shifts, fishing",
                default=(self.current_page == 2)
            ),
            discord.SelectOption(
                label="Page 4: Romance & Matrimony",
                value="3",
                emoji="💍",
                description="Marry, divorce, joint vault, double aid, double steal",
                default=(self.current_page == 3)
            ),
            discord.SelectOption(
                label="Page 5: Boss Fight (Juny-HWA)",
                value="4",
                emoji="😈",
                description="Juny boss encounter, combat, attacks, call aid, dark pacts",
                default=(self.current_page == 4)
            ),
            discord.SelectOption(
                label="Page 6: Social, Music & Trophies",
                value="5",
                emoji="🎭",
                description="Truth or Dare, Spotify Kizzy RPC, leaderboard, achievements",
                default=(self.current_page == 5)
            ),
            discord.SelectOption(
                label="Page 7: RPG, GoD-HeLL & Auctions",
                value="6",
                emoji="👑",
                description="Berry auctions, Arena training, GoD-HeLL dungeon, Battle Shop",
                default=(self.current_page == 6)
            ),
        ]
        select = discord.ui.Select(
            placeholder="📑 Jump to category...",
            options=options,
            row=0
        )
        select.callback = self.on_select_page
        self.add_item(select)

        # Previous Button (Row 1)
        prev_btn = discord.ui.Button(
            label="Previous",
            emoji="◀️",
            style=discord.ButtonStyle.primary,
            disabled=(self.current_page <= 0),
            row=1
        )
        prev_btn.callback = self.on_prev_click
        self.add_item(prev_btn)

        # Page Indicator Button (Row 1, Disabled)
        page_btn = discord.ui.Button(
            label=f"Page {self.current_page + 1}/7",
            style=discord.ButtonStyle.secondary,
            disabled=True,
            row=1
        )
        self.add_item(page_btn)

        # Next Button (Row 1)
        next_btn = discord.ui.Button(
            label="Next",
            emoji="▶️",
            style=discord.ButtonStyle.primary,
            disabled=(self.current_page >= 6),
            row=1
        )
        next_btn.callback = self.on_next_click
        self.add_item(next_btn)

    async def _handle_page_update(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.author_id:
            await interaction.response.send_message("Type `y!help` to open your own interactive codex!", ephemeral=True)
            return
        self._build_components()
        embed = build_help_page_embed(self.current_page)
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_select_page(self, interaction: discord.Interaction):
        vals = interaction.data.get("values", [])
        if vals and vals[0].isdigit():
            self.current_page = int(vals[0])
        await self._handle_page_update(interaction)

    async def on_prev_click(self, interaction: discord.Interaction):
        if self.current_page > 0:
            self.current_page -= 1
        await self._handle_page_update(interaction)

    async def on_next_click(self, interaction: discord.Interaction):
        if self.current_page < 6:
            self.current_page += 1
        await self._handle_page_update(interaction)

async def handle_help(message, client, args: list = None):
    """Shows gambling, games & karma commands guide as rich Discord Embeds."""
    target_page = None
    if args:
        first = args[0].lower().strip()
        if first in ("1", "2", "3", "4", "5", "6"):
            target_page = int(first) - 1
        elif first in ("page", "p") and len(args) > 1 and args[1].isdigit():
            target_page = max(0, min(5, int(args[1]) - 1))

    if target_page is not None:
        author_id = str(message.author.id)
        embed = build_help_page_embed(target_page)
        view = YunaHelpPaginationView(author_id, current_page=target_page)
        await _safe_send_reply(message, embed=embed, view=view)
        return

    sub_topic = args[0].lower().lstrip("y!").strip() if args else ""

    if sub_topic in ("balance", "bal", "profile", "money", "berries", "berry"):
        embed = discord.Embed(
            title="🫐 Command Guide: y!balance",
            description="Displays your or another player's soul berry balance, morality standings, and relationship status.",
            color=HELP_COLOR
        )
        embed.add_field(name="🫐 Berries", value="Currency used for bets, casino games, and trades. Everyone starts with 0.", inline=False)
        embed.add_field(name="💖 Virtue", value="Earned through genuine help (`y!aid`) and philanthropy (`y!donate`).", inline=True)
        embed.add_field(name="❤️‍🔥 Sin", value="Accumulated from disastrous blunders (`y!aid`) and pickpocketing (`y!steal`).", inline=True)
        embed.add_field(name="💍 Marriage & Dares", value="Shows your active spouse and any pending truth-or-dare challenges.", inline=False)
        embed.add_field(name="Syntax & Aliases", value="`y!balance` or `y!balance @user`\n*Aliases:* `y!bal`, `y!profile`, `y!money`", inline=False)
        embed.set_footer(text="Yuna's Codex • Morality & Economy")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("blackjack", "bj", "hit", "stand", "21"):
        embed = discord.Embed(
            title="🃏 Command Guide: y!blackjack",
            description="Play classic 21 against dealer Yuna with interactive Discord buttons!",
            color=HELP_COLOR
        )
        embed.add_field(name="Rules", value="Player and Yuna are dealt 2 cards (Yuna's 2nd card is face-down). Hit or Stand to get as close to 21 as possible without busting!", inline=False)
        embed.add_field(name="Payouts", value="• Standard Win: **1:1**\n• Natural 21 on Deal: **3:2** payout immediately!\n• Ties (Push): Bet refunded.", inline=True)
        embed.add_field(name="Comedy Cards (~4%)", value="• Uno Reverse (10)\n• Blue-Eyes Dragon (10)\n• Bitten Strawberry Card (7)\n• Boba Discount Coupon (6)", inline=True)
        embed.add_field(name="Syntax & Controls", value="`y!blackjack <amount>` or `y!bj <amount>` (e.g. `y!bj 50`)\n*Controls:* Click **Hit** / **Stand** buttons, or type `y!hit` / `y!stand`.", inline=False)
        embed.set_footer(text="Yuna's Casino • Blackjack Table")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("crash", "cashout", "rocket"):
        embed = discord.Embed(
            title="📈 Command Guide: y!crash",
            description="Watch Yuna's rocket multiplier climb higher and higher in real-time!",
            color=HELP_COLOR
        )
        embed.add_field(name="Mechanics", value="The multiplier starts at **1.00x** and climbs exponentially every 1.5s in live-edited messages.", inline=False)
        embed.add_field(name="How to Win", value="Click **💰 Cash Out** or type `y!cashout` before the rocket explodes to secure your profits!", inline=True)
        embed.add_field(name="Comedy Crashes", value="Space geese collisions, fueling with berry smoothie, and cosmic speeding tickets!", inline=True)
        embed.add_field(name="🏆 Achievement", value="Cash out at **5.00x or higher** to unlock the rare **Yuna's Favorite** achievement!", inline=False)
        embed.add_field(name="Syntax", value="`y!crash <amount>` (e.g. `y!crash 100`)", inline=False)
        embed.set_footer(text="Yuna's Casino • Rocket Crash")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("higherlower", "hl", "guess", "higher", "lower"):
        embed = discord.Embed(
            title="🎲 Command Guide: y!higherlower",
            description="Guess whether the next playing card will be Higher or Lower!",
            color=HELP_COLOR
        )
        embed.add_field(name="Card Range (1 to 13)", value="• **Lowest:** 1 (Ace)\n• **Highest:** 13 (King)\n• Starting card is dealt between 2 and 12.", inline=False)
        embed.add_field(name="Escalating Streaks", value="`1.5x` ➔ `2.2x` ➔ `3.2x` ➔ `4.8x` ➔ `7.5x` ➔ `12.0x` ➔ `20.0x+`!", inline=True)
        embed.add_field(name="Resets & Limit Protection", value="• Hitting **1 (Ace)** or **13 (King)** automatically reshuffles to a fresh middle card!\n• Exact ties trigger a free truce and card reshuffle.", inline=True)
        embed.add_field(name="Reset Anytime", value="Click **🔄 Reset** or type `y!hl reset` to cancel anytime (refunds on 0-streak, cashes out on >0 streak). Starting a new game with `y!hl <amt>` auto-resets previous rounds!", inline=False)
        embed.add_field(name="Syntax", value="`y!higherlower <amount>` or `y!hl <amount>` (e.g. `y!hl 25`)", inline=False)
        embed.set_footer(text="Yuna's Casino • Higher or Lower Table")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("coinflip", "flip", "cf"):
        embed = discord.Embed(
            title="🪙 Command Guide: y!coinflip",
            description="Flip a berry coin with a 40% chance of complete comedic chaos!",
            color=HELP_COLOR
        )
        embed.add_field(name="40% Absurdity Events", value="• **Yuna steals the coin:** Dives across the table shouting *'mehehhehehe'* *(Refunded!)*\n• **Bald Eagle:** Snatches the coin mid-air at 90mph *(Lost!)*\n• **Sewer Drain:** Rolls into municipal sewer grate *(Lost!)*\n• **Zero Gravity:** Coin freezes motionless in mid-air *(Refunded!)*\n• **Pigeon Vacuum / Time Portal / Zeus Lightning!**", inline=False)
        embed.add_field(name="60% Landings", value="Tough odds (~28% win rate), but correctly guessing Heads/Tails awards a massive **2.5x payout**!", inline=False)
        embed.add_field(name="Syntax", value="`y!flip <amount> [heads/tails]` (e.g. `y!flip 100 heads`)\n*Tip:* Run `y!flip <amount>` to get clickable **🪙 Heads** and **🪙 Tails** buttons!", inline=False)
        embed.set_footer(text="Yuna's Casino • Absurd Coin Flip")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("roulette", "rouellete", "wheel", "spin"):
        embed = discord.Embed(
            title="🎡 Command Guide: y!roulette",
            description="Spin Yuna's luxurious 38-pocket Roulette wheel with interactive betting buttons!",
            color=HELP_COLOR
        )
        embed.add_field(
            name="Bets & Multipliers",
            value=(
                "• 🔴 **Red** / ⚫ **Black** — **1:1** payout (2x)\n"
                "• **Even** / **Odd** — **1:1** payout (2x)\n"
                "• **1–18 (Low)** / **19–36 (High)** — **1:1** payout (2x)\n"
                "• **1st 12 / 2nd 12 / 3rd 12** — **2:1** payout (3x)\n"
                "• **Columns (col1, col2, col3)** — **2:1** payout (3x)\n"
                "• **Straight Single Number (0–36)** — **35:1** (36x) *(with celestial lightning up to 250x!)*\n"
                "• 👑 **Golden Crown Slot (000)** — **250x Maximum Jackpot!**"
            ),
            inline=False
        )
        embed.add_field(
            name="Interactive Board & Controls",
            value=(
                "• Simply type `y!roulette <amount>` to open the interactive Discord betting board with clickable buttons!\n"
                "• Or place direct bets: `y!roulette <amount> <bet>` (e.g. `y!roulette 100 red`, `y!roulette 50 crown`, `y!roulette 25 17`)."
            ),
            inline=False
        )
        embed.add_field(
            name="Syntax & Aliases",
            value="`y!roulette <amount> [bet]`\n*Aliases:* `y!wheel`, `y!spin`",
            inline=False
        )
        embed.set_footer(text="Yuna's Casino • Roulette Wheel")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("poker", "videopoker", "vp", "draw", "hold"):
        embed = discord.Embed(
            title="🃏 Command Guide: y!poker",
            description="Classic 5-Card Draw Video Poker against house odds with button card holding!",
            color=HELP_COLOR
        )
        embed.add_field(
            name="Hand Payout Multipliers",
            value=(
                "• 👑 **Royal Flush**: **250x** (Maximum Jackpot!)\n"
                "• 🌟 **Straight Flush**: **50x**\n"
                "• 🔥 **Four of a Kind**: **25x**\n"
                "• 🏠 **Full House**: **9x**\n"
                "• 🌊 **Flush**: **6x**\n"
                "• ⚡ **Straight**: **4x**\n"
                "• 🎯 **Three of a Kind**: **3x**\n"
                "• ✌️ **Two Pair**: **2x**\n"
                "• 🃏 **Jacks or Better**: **1x** (Bet returned)\n"
                "• Low Pair or High Card: 0x"
            ),
            inline=False
        )
        embed.add_field(
            name="How to Play",
            value=(
                "1. Start a game with `y!poker <amount>` (or `y!vp <amount>`).\n"
                "2. You are dealt 5 cards.\n"
                "3. Click card buttons to toggle **[🔒 Hold]** on cards you wish to keep!\n"
                "4. Click **[🔄 Draw Cards]** to discard the rest and draw replacements!\n"
                "*(Or use text commands: `y!hold 1 3 5` then `y!draw` or `y!fold`)*"
            ),
            inline=False
        )
        embed.add_field(
            name="Syntax & Aliases",
            value="`y!poker <amount>`\n*Aliases:* `y!vp`, `y!videopoker`\n*Commands:* `y!hold <1-5>`, `y!draw`, `y!fold`",
            inline=False
        )
        embed.set_footer(text="Yuna's Casino • Video Poker")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("dice", "roll", "craps", "dicebet", "dices"):
        embed = discord.Embed(
            title="🎲 Command Guide: y!dice (Absurd 2d6 Casino Table)",
            description="Roll a pair of 6-sided dice against probabilities or duel Yuna head-to-head with interactive buttons!",
            color=HELP_COLOR
        )
        embed.add_field(
            name="Bets & Payouts",
            value=(
                "• 🔴 **Low (2–6)** / 🔵 **High (8–12)**: pays **1:1**\n"
                "• ⭐ **Lucky Seven (7)**: pays **4:1** (5x return!)\n"
                "• 🎲 **Even** / 🎯 **Odd**: pays **1:1**\n"
                "• ✨ **Doubles (Pair)**: pays **4:1** (5x return!)\n"
                "• ⚔️ **Roll vs Yuna**: Highest 2d6 roll wins! (1:1)\n"
                "• 🐍 **Exact Snake Eyes [2]** / 🚂 **Boxcars [12]**: pays **30:1**!\n"
                "• 🎯 **Exact 3/11 (15:1)**, **4/10 (10:1)**, **5/9 (7:1)**, **6/8 (5:1)**"
            ),
            inline=False
        )
        embed.add_field(
            name="Special Absurdities & Charms (~8%)",
            value="Cosmic gust double win surges, playful cat table fouls, raspberry spark collisions, and iced boba spills!",
            inline=False
        )
        embed.add_field(
            name="Syntax & Controls",
            value="`y!dice <amount> [bet]`\n*Aliases:* `y!roll`, `y!craps`, `y!dicebet`\n*Example:* `y!dice 100` (opens buttons), `y!dice 50 seven`, `y!roll 100 vs`, `y!dice 25 2`",
            inline=False
        )
        embed.set_footer(text="Yuna's Casino • 2d6 Dice Table")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("mines", "mine", "minesweeper"):
        embed = discord.Embed(
            title="💣 Command Guide: y!mines",
            description="Tiptoe through Yuna's 5x5 minefield to uncover sparkling gems and avoid deadly bombs!",
            color=HELP_COLOR
        )
        embed.add_field(
            name="Mechanics & Multipliers",
            value=(
                "• **Grid:** 5x5 board (25 tiles total) with configurable mines (**1 to 23**, default 3).\n"
                "• **Fair Payouts:** Every safe gem you reveal multiplies your cashout pot (96% fair RTP math)!\n"
                "• **Escalation:** The more mines you choose and the more tiles you uncover, the higher the multiplier skyrockets!\n"
                "• **Jackpot:** Uncovering all non-mine gems triggers an automatic Maximum Win!"
            ),
            inline=False
        )
        embed.add_field(
            name="Controls & Buttons",
            value=(
                "• Click any **[❔ Tile]** button on the interactive board to reveal what lies beneath!\n"
                "• Click **[💰 Cash Out]** (bottom right) or type `y!cashout` anytime to secure your current earnings.\n"
                "• If you strike a mine (**💥 BOOM**), your bet is lost and all mine locations are revealed!"
            ),
            inline=False
        )
        embed.add_field(
            name="Syntax & Aliases",
            value="`y!mines <amount> [mines]`\n*Aliases:* `y!mine`, `y!minesweeper`\n*Example:* `y!mines 50` (3 mines), `y!mines 100 5` (5 mines)",
            inline=False
        )
        embed.set_footer(text="Yuna's Casino • Minesweeper Table")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("wordle", "word", "wordlegame"):
        embed = discord.Embed(
            title="🟩 Command Guide: y!wordle (Progressive Gamble)",
            description="5-Stage escalating word-guessing gauntlet with persistent pot and skyrocketing multipliers!",
            color=HELP_COLOR
        )
        embed.add_field(
            name="5 Escalating Stages",
            value=(
                "• **Stage 1 (Novice):** 4 letters, 6 guesses ➔ **1.8x** pot\n"
                "• **Stage 2 (Adept):** 5 letters, 5 guesses ➔ **3.6x** pot\n"
                "• **Stage 3 (Master):** 6 letters, 5 guesses ➔ **8.0x** pot\n"
                "• **Stage 4 (Grandmaster):** 6 letters (tricky), 4 guesses ➔ **18.0x** pot\n"
                "• **Stage 5 (Ascended God):** 7 letters, 4 guesses ➔ **40.0x pot + 2 💖 Virtue!**"
            ),
            inline=False
        )
        embed.add_field(
            name="Between Stages & Color Clues",
            value=(
                "• Guess clues: 🟩 **Green** (correct spot), 🟨 **Yellow** (wrong spot), ⬛ **Gray** (not in word).\n"
                "• Clear a stage to choose: **[💰 Cash Out]** to walk away rich, or **[🔥 Risk & Advance]** to bet the entire accumulated pot on the next stage!\n"
                "• If you run out of guesses or forfeit, the entire accumulated pot is lost!"
            ),
            inline=False
        )
        embed.add_field(
            name="Syntax & Controls",
            value=(
                "`y!wordle <amount>` (e.g. `y!wordle 50`)\n"
                "*Guessing:* Click **[✏️ Guess Word]** modal button, or type `y!guess <word>` (or `y!w <word>`).\n"
                "*Advancing:* Click **[🔥 Risk & Advance]** or type `y!next` / `y!advance`.\n"
                "*Cashing Out:* Click **[💰 Cash Out]** or type `y!cashout`."
            ),
            inline=False
        )
        embed.set_footer(text="Yuna's Casino • Progressive Wordle Run")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("streak", "winstreak", "streaks", "winrate"):
        embed = discord.Embed(
            title="🔥 Command Guide: y!streak (Gamble Win Streaks)",
            description="Consecutive gambling victories scale your profits and grant massive milestone berry windfalls!",
            color=HELP_COLOR
        )
        embed.add_field(
            name="Streak Profit Multiplier",
            value="Every consecutive gamble win above 1 grants an extra **+5% net profit bonus** (capped at **+50%** at 11+ streak) on future wins!",
            inline=False
        )
        embed.add_field(
            name="Milestone Berry Windfalls",
            value=(
                "• 🔥 **3 Streak:** +100 🫐 windfall\n"
                "• 🔥 **5 Streak:** +300 🫐 windfall\n"
                "• 🔥 **7 Streak:** +600 🫐 windfall\n"
                "• 🔥 **10 Streak:** +1,500 🫐 windfall\n"
                "• 🔥 **15 Streak:** +3,000 🫐 windfall\n"
                "• 🔥 **20 Streak:** +7,500 🫐 windfall!"
            ),
            inline=False
        )
        embed.add_field(
            name="How Streaks Work & Leaderboard",
            value=(
                "• Supported in all gambling games: Blackjack, Crash, Higher/Lower, Coinflip, Roulette, Poker, Dice, Mines, Wordle, and PvP Fights.\n"
                "• Any gamble loss resets your active win streak to 0 (all-time highest is preserved).\n"
                "• View top streaks with `y!leaderboard streak` (or `y!lb streak`)!"
            ),
            inline=False
        )
        embed.add_field(name="Syntax & Aliases", value="`y!streak [@user]`\n*Aliases:* `y!winstreak`, `y!streaks`", inline=False)
        embed.set_footer(text="Yuna's Hall of Fame • Win Streaks")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("dare", "truth", "checkdare", "checktruth", "completedare", "proof", "reroll", "rerolldare", "activedare", "mydare"):
        embed = discord.Embed(
            title="🎭 Command Guide: Truth or Dare System",
            description="High-stakes Truth or Dare with custom prompts, peer reviews, 1 free reroll, and Yuna's AI arbitrator!",
            color=HELP_COLOR
        )
        embed.add_field(
            name="Starting a Challenge",
            value=(
                "• `y!dare @user [amt] [custom prompt]` — Challenge another player with your own custom dare (or random)!\n"
                "• `y!truth @user [amt] [custom question]` — Ask a spicy question with berries on the line!\n"
                "• `y!dare [amt]` / `y!truth [amt]` — Solo challenge against Yuna for double berries!"
            ),
            inline=False
        )
        embed.add_field(
            name="Submitting Proof & Review",
            value=(
                "• `y!checkdare <proof>` / `y!checktruth <answer>` — Submit your proof or answer.\n"
                "• **PvP Review Buttons:** The challenger can click **[✅ Approve & Payout]**, **[❌ Reject Proof]**, or either player can click **[🤖 Ask Yuna AI]** to arbitrate objectively!\n"
                "• **Solo Review:** Yuna's AI arbitrator immediately grades your submission."
            ),
            inline=False
        )
        embed.add_field(
            name="Controls & Tracking",
            value=(
                "• `y!activedare` (or `y!mydare`) — View your active challenge, pot, and time elapsed.\n"
                "• `y!rerolldare` (or `y!reroll`) — 1 free reroll per challenge if you dislike the assigned prompt!\n"
                "• `y!forfeitdare` — Chicken out and surrender the pot."
            ),
            inline=False
        )
        embed.set_footer(text="Yuna's Social • Truth or Dare Codex")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("aid", "helpout", "assist"):
        embed = discord.Embed(
            title="💖 Command Guide: y!aid",
            description="Interactive moral deed interaction helping another server member!",
            color=HELP_COLOR
        )
        embed.add_field(name="Morality Outcomes", value="• **50% Success:** Helpful deed! Gains berries, **+1 💖 Virtue**, +0 ❤️‍🔥 Sin.\n• **25% Disaster:** Chaotic blunder! Gains 0 berries, **-1 💖 Virtue**, **+1 ❤️‍🔥 Sin**.\n• **25% Refusal:** Target rudely rejects you but tosses pity berries (+0 💖, +0 ❤️‍🔥).", inline=False)
        embed.add_field(name="Syntax", value="`y!aid @user` (Supports pinging `<@user>` or username)", inline=False)
        embed.set_footer(text="Yuna's Morality • Karma System")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("steal", "rob", "pickpocket"):
        embed = discord.Embed(
            title="🦹 Command Guide: y!steal",
            description="Attempt a daring pickpocket heist on another user's berry pouch!",
            color=HELP_COLOR
        )
        embed.add_field(
            name="Outcomes & Dynamic Scaling",
            value=(
                "• **45% Success:** Snatches **15%–35%** of victim's balance! (scales dynamically with victim's wealth, **+2 ❤️‍🔥 Sin**)\n"
                "• **55% Caught:** Caught red-handed! Forced to pay **15%–30% restitution fine** scaling with your and the victim's balance (**+1 ❤️‍🔥 Sin**; broke thieves gain +3 Sin!)."
            ),
            inline=False
        )
        embed.add_field(
            name="Defenses & Buffs",
            value=(
                "• 🛡️ **Divine Ward:** Blocks theft and electrocutes the thief with a heavy scaled fine (min 50 🫐) paid to you!\n"
                "• 💖 **Virtue Aura:** Victims with high Virtue have up to 35% chance to deflect theft morally!\n"
                "• 🍀 **Lucky Clover:** +25% success rate (70% total)!\n"
                "• 🎭 **Phantom Mask:** Guarantees 0 Sin & +30% bonus loot!"
            ),
            inline=False
        )
        embed.add_field(name="Syntax", value="`y!steal @user`", inline=False)
        embed.set_footer(text="Yuna's Morality • Dynamic Balance Scaling")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("donate", "charity", "bless"):
        embed = discord.Embed(
            title="✨ Command Guide: y!donate",
            description="Donate berries to gain 💖 Virtue!",
            color=HELP_COLOR
        )
        embed.add_field(name="Mechanics", value="Donated berries randomly rain down on an active server member! Awards **+1 💖 Virtue** per 25 🫐 donated.", inline=False)
        embed.add_field(name="Syntax", value="`y!donate <amount>` (e.g. `y!donate 50`)", inline=False)
        embed.set_footer(text="Yuna's Morality • Philanthropy")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("bet", "fight", "trade", "wager"):
        embed = discord.Embed(
            title="👥 Command Guide: Social Wagers",
            description="Challenge your friends with interactive confirmation buttons!",
            color=HELP_COLOR
        )
        embed.add_field(name="Available Wagers", value="• `y!bet @user <amount>` — 50/50 Coin Flip wager against another player.\n• `y!fight @user <amount>` — Fictional absurd arena battle; winner takes the pot!\n• `y!trade @user <amount>` — Safe escrow berry transfer.\n• `y!give @user <amount>` — Direct berry gift.", inline=False)
        embed.add_field(name="Controls", value="Challenged players can click **✅ Accept** or **❌ Decline** (or type `y!accept`/`y!decline`).", inline=False)
        embed.set_footer(text="Yuna's Social • Wagers & Brawls")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("daily", "claim", "allowance", "dailyreward"):
        embed = discord.Embed(
            title="🎁 Command Guide: y!daily",
            description="Collect your daily fresh berries and streak bonuses every day!",
            color=HELP_COLOR
        )
        embed.add_field(name="Base Grant", value="`+150 🫐` per day and `+1 💖` Virtue.", inline=False)
        embed.add_field(name="Daily Streaks", value="Streak multiplier adds `+25 🫐` per consecutive day (capped at `+500 🫐`)! Reach a 7-day streak to unlock the 🔥 **Daily Devotee** badge.", inline=False)
        embed.add_field(name="💍 Matrimonial Allowance", value="Married players receive an extra **+50 🫐** daily bonus directly from Yuna!", inline=False)
        embed.add_field(name="Reset Time", value="Resets every day at **00:00 UTC**.", inline=False)
        embed.add_field(name="Syntax & Aliases", value="`y!daily` (or `y!claim`)", inline=False)
        embed.set_footer(text="Yuna's Economy • Daily Allowance")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("tasks", "task", "dailies", "tasklist", "todo", "quests", "quest"):
        embed = discord.Embed(
            title="📋 Command Guide: y!tasks (Everyday Task List)",
            description="Complete 4 everyday tasks each day to earn berry bounties and unlock the Grand Daily Bounty!",
            color=HELP_COLOR
        )
        embed.add_field(name="Daily Tasks", value=(
            "• 🎲 **High Roller:** Play any gamble game (HL, Flip, Crash, BJ, Fight) — **+75 🫐**\n"
            "• 🤝 **Helping Hand:** Aid someone with `y!aid` or `y!doubleaid` — **+50 🫐**\n"
            "• 💖 **Kind Soul:** Donate or gift berries (`y!donate` or `y!give`) — **+60 🫐**\n"
            "• 🎶 **Vibe Check:** Check profile (`y!bal`) or song (`y!song`) — **+40 🫐**"
        ), inline=False)
        embed.add_field(name="🎉 Grand Daily Bounty", value="Complete all 4 tasks to unlock an extra **+200 🫐** and **+2 💖 Virtue**! Married players receive **+40 🫐** extra bonus!", inline=False)
        embed.add_field(name="Syntax & Aliases", value="`y!tasks` (or `y!dailies`, `y!tasklist`, `y!todo`)", inline=False)
        embed.set_footer(text="Yuna's Economy • Everyday Tasks")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("shared", "joint", "vault", "jointaccount", "sharedaccount"):
        embed = discord.Embed(
            title="💍 Command Guide: y!shared (Matrimonial Joint Vault)",
            description="A shared bank vault exclusively for married couples with daily passive interest!",
            color=HELP_COLOR
        )
        embed.add_field(name="📈 Daily Love Interest", value="+5% daily passive yield (up to 500 🫐/day) on whatever balance is in the vault!", inline=False)
        embed.add_field(name="Commands", value=(
            "• `y!shared` (or `y!joint`) — View shared vault balance & stats\n"
            "• `y!shared deposit <amt|all>` — Deposit berries into joint vault\n"
            "• `y!shared withdraw <amt|all>` — Withdraw berries from joint vault"
        ), inline=False)
        embed.add_field(name="Divorce Settlement", value="If you ever divorce (`y!divorce`), the joint vault is legally liquidated and divided 50/50!", inline=False)
        embed.set_footer(text="Yuna's Romance • Shared Banking")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("doubleaid", "coupleaid", "superaid", "duoaid"):
        embed = discord.Embed(
            title="💞 Command Guide: y!doubleaid",
            description="Team up with your married partner to unleash a 2x Super Aid on another server member!",
            color=HELP_COLOR
        )
        embed.add_field(name="Requirements", value="Must be married (`y!marry @user`). Cannot target yourself or your spouse.", inline=False)
        embed.add_field(name="Outcomes", value=(
            "• **55% Power Couple Success:** Awards **60-140 🫐** + **2 💖 Virtue** to invoker, **20 🫐** + **1 💖** to spouse, plus a 10% love kickback into your Joint Vault!\n"
            "• **25% Couple Blunder:** Bickering disaster! **-2 💖 Virtue**, **+2 ❤️‍🔥 Sin**.\n"
            "• **20% Overwhelmed:** Target is intimidated by your couple energy (**15-30 🫐** consolation)."
        ), inline=False)
        embed.add_field(name="Syntax", value="`y!doubleaid @user`", inline=False)
        embed.set_footer(text="Yuna's Social • Matrimonial Teamwork")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("marry", "marriage", "spouse", "couple", "anniversary", "divorce", "vow", "kiss", "date", "datenight", "gift", "lovegift"):
        embed = discord.Embed(
            title="💍 Command Guide: Yuna's Matrimonial System",
            description="Complete directory of matrimony, vows, dates, kissing, gifting, and divorce!",
            color=HELP_COLOR
        )
        embed.add_field(
            name="💒 Courtship & Marriage",
            value=(
                "• `y!marry @user` — Propose with interactive **[💍 I Do!]** and **[💔 Reject]** buttons!\n"
                "• `y!marriage [@user]` (or `y!spouse`, `y!couple`) — View your sacred marriage certificate, wedding anniversary, days together, and synergy records!\n"
                "• `y!vow <text>` — Etch your eternal couple vow onto the certificate (+1 Virtue)!\n"
                "• `y!divorce` — Pay 10,000 🫐 (or 5,000 with Divorce Insurance) to dissolve your marriage."
            ),
            inline=False
        )
        embed.add_field(
            name="🌹 Couple Lifestyle & Interactions",
            value=(
                "• `y!date` (or `y!datenight`) — Take spouse on hilarious dates (+80–220 🫐, +2 Virtue, vault savings) every 5m (reset with `chocolate`)!\n"
                "• `y!kiss [@user]` (or `y!hug`) — Kiss spouse for vault love sparks (+15–35 🫐) or trigger 4K Infidelity alerts!\n"
                "• `y!gift @spouse <amt|item>` (or `y!lovegift`) — Send tax-free berries or inventory items with a custom love note!"
            ),
            inline=False
        )
        embed.add_field(
            name="💞 Joint Vault & Teamwork",
            value=(
                "• `y!shared` (or `y!joint`) — Shared matrimonial vault (+5%/10% daily yield).\n"
                "• `y!doubleaid @user` — 2x Super Aid (+10% success with Golden Wedding Ring)!\n"
                "• `y!doublesteal @victim` — Tag-team robbery (15% to joint vault, 50/50 split)!"
            ),
            inline=False
        )
        embed.set_footer(text="Yuna's Romance • Matrimonial Universe")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("achievements", "ach", "trophies"):
        embed = discord.Embed(
            title="🏆 Command Guide: Achievements & Badges",
            description="Track your unlocked badges, karma milestones, and trophies!",
            color=HELP_COLOR
        )
        embed.add_field(name="Trophies (56 Total)", value=(
            "• ⚖️ **Morality & Karma:** *Satan's Disciple*, *Local Saint*, *Clean Hands*, *The Long Road Home*, *Archangel's Blessing*, *Diabolical Menace*, *Master Pickpocket*, *Corrupted Aegis*, *Ghost in the Shadows*\n"
            "• 🫐 **Wealth & Luxury:** *Ballin'*, *Piggy Banker*, *Berry Tycoon*, *Berry Millionaire*, *Berry Whale*, *Big Spender*, *Down Bad Financially*, *Professional Idiot*\n"
            "• 🎲 **Casino & Dice:** *First Roll*, *Snake Eyes*, *Midnight Boxcars*, *Lucky Seven*, *Master of the Bones*, *Dice High Roller*, *One More Spin*, *Casino Regular*, *Yuna's Favorite*, *To The Moon!*, *Cosmic Dust*, *Victim of Circumstance*, *Mind Reader*, *Grand Oracle*, *High Roller Sovereign*, *Poker Royalty*\n"
            "• 😈 **Boss & Battle:** *Daredevil*, *Cardboard Warrior*, *Devil's Bargain*, *Heavenly Mercy*, *Vanguard Hero*, *Coward's Escape*, *Arena Gladiator*\n"
            "• 💀 **Karmic Disasters:** *Final Destination*, *Sharknado Casualty*\n"
            "• 🃏 **Blackjack Curiosities:** *No, U!*, *Duelist Master*, *Snack Attack*\n"
            "• 💍 **Love, Dailies & Lifestyle:** *Ball and Chain*, *Irreconcilable Differences*, *Hopeless Romantic*, *Dynamic Duo*, *Happily Ever After*, *Daily Devotee*, *Taskmaster*, *Certified Daredevil*, *Certified Audiophile*"
        ), inline=False)
        embed.add_field(name="Syntax", value="`y!achievements` or `y!ach`", inline=False)
        embed.set_footer(text="Yuna's Hall of Fame • 56 Collectible Trophies")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("leaderboard", "lb", "top"):
        embed = discord.Embed(
            title="📊 Command Guide: y!leaderboard",
            description="Displays the top 5 Richest (🫐), Saintliest (💖), and Most Sinful (❤️‍🔥) mortals in the realm!",
            color=HELP_COLOR
        )
        embed.add_field(name="Syntax", value="`y!leaderboard` or `y!lb`", inline=False)
        embed.set_footer(text="Yuna's Leaderboard")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("music", "song", "play", "rpc", "kizzy", "np", "playlist", "listen"):
        embed = discord.Embed(
            title="🎧 Command Guide: Yuna's Spotify RPC",
            description="Control Yuna's rich Discord 'Listening to Spotify' status powered by Kizzy API & real cover art!",
            color=discord.Color.from_rgb(30, 215, 96)
        )
        embed.add_field(name="y!song (or y!np)", value="Displays the currently playing song with live timeline progress bar, album artwork, and artist info.", inline=False)
        embed.add_field(name="y!play <song name>", value="Puts on any song! Searches iTunes & Deezer for high-res covers, resolves them through Kizzy API, and immediately updates Yuna's Discord RPC card.", inline=False)
        embed.add_field(name="y!skip", value="Skips to the next song in Yuna's curated playlist.", inline=True)
        embed.add_field(name="y!playlist", value="View Yuna's favorite song rotation (Vocaloid / J-Pop / Alt-Pop).", inline=True)
        embed.set_footer(text="Yuna's Music • Kizzy API Rich Presence")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("shop", "store", "market", "bazaar", "buy"):
        embed = discord.Embed(
            title="🏪 Command Guide: Yuna's Item Shop",
            description="Purchase powerful charms, shields, consumables, and status symbols!",
            color=HELP_COLOR
        )
        embed.add_field(
            name="Catalog (7 Items)",
            value=(
                "• 🛡️ **Divine Ward (500 🫐):** Passive shield! Electrocutes the next thief who tries to steal from you with a heavy scaled fine (min 50 🫐) paid to you!\n"
                "• 🍀 **Lucky Clover (350 🫐):** Consumable! `y!use clover` for +25% luck on your next gamble, crime, or fish!\n"
                "• ⚡ **Energy Drink (250 🫐):** Consumable! `y!use energy` to instantly reset your work, crime, and fishing cooldowns!\n"
                "• 🎭 **Phantom Mask (600 🫐):** Consumable! `y!use mask` grants 0 Sin & +30% loot on your next steal/crime!\n"
                "• 💎 **Eternal Diamond (2,500 🫐):** Permanent heirloom! Doubles joint vault love interest to +10% daily!\n"
                "• 📜 **Divorce Insurance (1,500 🫐):** Policy! Slashes Yuna's divorce fee from 10,000 to 5,000 🫐!\n"
                "• 👑 **Empress Crown (30,000 🫐):** Pure vanity! Displays a golden crown on your balance card!"
            ),
            inline=False
        )
        embed.add_field(name="Syntax & Commands", value="• `y!shop` — Browse catalog\n• `y!buy <item> [qty]` — Purchase items (e.g. `y!buy clover 2`)\n• `y!use <item>` — Activate consumable", inline=False)
        embed.set_footer(text="Yuna's Economy • Item Shop")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("inventory", "inv", "bag", "pouch"):
        embed = discord.Embed(
            title="🎒 Command Guide: y!inventory (or y!inv)",
            description="View your item pouch, active buffs, and consumable stock.",
            color=HELP_COLOR
        )
        embed.add_field(name="Details", value="Displays all owned shields, consumables, policies, and active temporary effects (like Lucky Clover or Phantom Mask).", inline=False)
        embed.add_field(name="Syntax & Aliases", value="`y!inventory` or `y!inv`\n*Tip:* Check someone else's bag with `y!inv @user`!", inline=False)
        embed.set_footer(text="Yuna's Economy • Inventory")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("use", "drink", "equip", "consume"):
        embed = discord.Embed(
            title="🧪 Command Guide: y!use",
            description="Activate consumable items from your inventory!",
            color=HELP_COLOR
        )
        embed.add_field(name="Usable Items", value="• `y!use clover` — +25% luck on next gamble, crime, or fish\n• `y!use energy` — Resets work, crime, and fishing cooldowns\n• `y!use mask` — 0 Sin & +30% loot on next steal/crime\n*(Passives like Ward, Diamond, Insurance, and Crown trigger automatically!)*", inline=False)
        embed.add_field(name="Syntax", value="`y!use <item>` (e.g. `y!use energy`)", inline=False)
        embed.set_footer(text="Yuna's Economy • Consumables")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("work", "job", "shift", "wage"):
        embed = discord.Embed(
            title="💼 Command Guide: y!work",
            description="Clock in for honest shifts around Yuna's district!",
            color=HELP_COLOR
        )
        embed.add_field(name="Wages & Cooldown", value="• Earn **60–150 🫐** base pay per shift!\n• Cooldown: **3 minutes**\n• Reset cooldown instantly with an **Energy Drink** (`y!use energy`)!", inline=False)
        embed.add_field(name="💖 Virtue Scaling & Karma", value="• Virtue multiplies your wage by **+2% per Virtue point**!\n• 25% chance per shift to gain **+1 💖 Virtue** for honest hard work!", inline=False)
        embed.add_field(name="💍 Marriage Bonus", value="Married players earn an extra **+15% matrimonial pay bonus**!", inline=False)
        embed.add_field(name="Syntax", value="`y!work` (or `y!job`, `y!shift`)", inline=False)
        embed.set_footer(text="Yuna's Economy • Honest Work")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("crime", "heist", "hustle"):
        embed = discord.Embed(
            title="🏴‍☠️ Command Guide: y!crime",
            description="Execute high-risk underworld operations for massive berry payouts!",
            color=HELP_COLOR
        )
        embed.add_field(name="High Stakes & Cooldown", value="• Earn **120–280 🫐** on success!\n• 65% base success rate (35% chance of bust and fine)\n• Cooldown: **4 minutes**\n• Awards **+2 ❤️‍🔥 Sin** on success", inline=False)
        embed.add_field(name="Buff Synergy", value="• 🍀 **Lucky Clover:** Guarantees 90% success rate!\n• 🎭 **Phantom Mask:** Guarantees 0 Sin and awards **+30% bonus loot**!", inline=False)
        embed.add_field(name="Syntax", value="`y!crime` (or `y!heist`)", inline=False)
        embed.set_footer(text="Yuna's Underworld • Crime Missions")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("fish", "fishing", "pond", "cast"):
        embed = discord.Embed(
            title="🎣 Command Guide: y!fish",
            description="Cast your bamboo line into Yuna's mystical berry pond!",
            color=HELP_COLOR
        )
        embed.add_field(name="Catches & Treasures", value="• Catch Golden Berry Carps, Rainbow Trout, Soggy Boots, or Ancient Relics!\n• 🔮 **Rare Dragon Pearl:** Sells for **350–500 🫐** and awards **+1 💖 Virtue**!\n• Cooldown: **1 minute**", inline=False)
        embed.add_field(name="🍀 Lucky Clover Synergy", value="Using a Lucky Clover (`y!use clover`) guarantees hooking a rare relic or dragon pearl!", inline=False)
        embed.add_field(name="Syntax", value="`y!fish` (or `y!fishing`)", inline=False)
        embed.set_footer(text="Yuna's Nature • Fishing Pond")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("doublesteal", "duosteal", "tagsteal", "couplesteal"):
        embed = discord.Embed(
            title="🦹‍♂️ Command Guide: y!doublesteal",
            description="Married couple tag-team robbery! Ambush a victim together for massive scaled loot!",
            color=HELP_COLOR
        )
        embed.add_field(name="Requirements & Dynamic Scaling", value="• Must be married (`y!marry @user`). Cannot rob spouse or self.\n• **25%–45% Loot Scaling:** Snatches a huge percentage of the victim's balance!\n• 15% of stolen loot deposits directly into your **Joint Matrimonial Vault**!\n• The remaining 85% is split 50/50 between both partners (**+2 ❤️‍🔥 Sin**).\n• **Failure Penalty:** Both thieves pay 15%–30% scaled restitution fines to the victim!", inline=False)
        embed.add_field(name="❤️‍🔥 Sin Synergy & Protections", value="• High combined Sin increases couple heist success rate up to 80%!\n• Victims with **Divine Wards** or high **Virtue** will shock or repel both thieves with scaled restitution fines!", inline=False)
        embed.add_field(name="Syntax", value="`y!doublesteal @victim`", inline=False)
        embed.set_footer(text="Yuna's Underworld • Matrimonial Heists")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("setsin", "set-sin", "sin", "set_sin"):
        embed = discord.Embed(
            title="🔮 Command Guide: y!setsin",
            description="Adjust or set mortal Sin points in the Celestial Records (Owner & Admin only).",
            color=HELP_COLOR
        )
        embed.add_field(
            name="Permissions & Limits",
            value="• **Permissions:** Bot Owner or Server Administrators.\n• **Range:** `0` to `30` Sin points.",
            inline=False
        )
        embed.add_field(
            name="Syntax & Examples",
            value=(
                "• `y!setsin @user <amount>` — Set Sin for a mentioned user\n"
                "• `y!set sin @user <amount>` — Natural language syntax\n"
                "• `y!setsin <user_id> <amount>` — Set Sin via Discord snowflake ID\n"
                "• `y!setsin <amount>` — Set Sin for yourself\n"
                "*Example:* `y!setsin @player 20` or `y!set sin 0`"
            ),
            inline=False
        )
        embed.add_field(
            name="Effects & Karmic Audit",
            value="Updates target's Sin level, resets break locks, logs to audit history, and updates their Karmic title.",
            inline=False
        )
        embed.set_footer(text="Yuna's Codex • Karmic Administration")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("boss", "juny", "combat", "callaid", "call-aid", "call_aid", "plead", "fight", "attack", "dodge", "negotiate"):
        embed = discord.Embed(
            title="😈 Command Guide: Juny Boss Encounter & Combat",
            description="When a mortal's Sin reaches 20+, Heaven's Worst Angel (Juny-HWA) descends to collect. Survive through combat, aid, or pacts!",
            color=HELP_COLOR
        )
        embed.add_field(
            name="Encounter Decisions",
            value=(
                "• **🙏 Plead (`y!plead`):** Beg Juny for mercy. 15% success (+5% with Coupon). Juny takes a cut of berries & karma.\n"
                "• **⚔️ Fight (`y!fight`):** Challenge Juny to turn-based combat! Form a raid party with `y!callaid`.\n"
                "• **📜 Negotiate (`y!negotiate`):** Dark celestial pact! Trade balance & karma to zero for soul contracts."
            ),
            inline=False
        )
        embed.add_field(
            name="Turn-Based Combat Actions",
            value=(
                "• `y!attack` (or `y!atk`) — Strike Juny with weapon/holy damage.\n"
                "• `y!dodge` — Defensive evasion stance (+40% dodge chance for 1 round).\n"
                "• `y!useitem <item>` — Use items: `elixir` (+50 HP), `smite` (150 True DMG), `sand` (blinds Juny), `feather` (angelic shield), `hammer`.\n"
                "• `y!callaid @friends` (or `y!call aid`) — Call up to 3 allies to join your raid party (supports dropdown menu or @mentions)!"
            ),
            inline=False
        )
        embed.add_field(
            name="Sin Corruption on Defensive Items",
            value="Mortal Sin (6–30) corrupts shields and feathers, causing them to crack, partially fail, or backfire violently!",
            inline=False
        )
        embed.set_footer(text="Yuna's Codex • Juny-HWA Boss Encounter")
        await _safe_send_reply(message, embed=embed)
        return

    # Default Main Codex Embed Directory (Paginated 6 Pages)
    author_id = str(message.author.id)
    embed = build_help_page_embed(0)
    view = YunaHelpPaginationView(author_id, current_page=0)
    await _safe_send_reply(message, embed=embed, view=view)

# ─── YUNA AI CONSCIOUSNESS & CONTEXT INJECTION ───────────────────────────────

def build_yuna_ai_context(user_id: Optional[str] = None) -> str:
    """Builds a comprehensive real-time knowledge block for Yuna's AI persona."""
    global _USER_STATS
    lines = [
        "=" * 50,
        "YUNA'S BERRY ECONOMY, MORALITY & GAMBLING SYSTEM KNOWLEDGE",
        "=" * 50,
        "You (Yuna) run and preside over an official Discord gambling & morality universe!",
        "All commands use the 'y!' prefix and ONLY YOU respond to them.",
        "Currency: 🫐 Berries (starts at 0) | Karma: 💖 Virtue (earned by helping/donating) & ❤️‍🔥 Sin (accumulated by failing aids or stealing).",
        "",
        "COMMANDS YOU OPERATE (Users can run these, and you can chat/banter about them naturally):",
        "• y!help — Displays your rich Interactive Codex Embed Directory with guides for all games.",
        "• y!balance (or y!bal) — Shows a player's berry pouch, virtue, sin, spouse, and joint vault.",
        "• y!daily (or y!claim) — Daily berry allowance (150 berries base + streak multipliers up to 500 + 50 marriage bonus).",
        "• y!tasks (or y!dailies) — Everyday task list (High Roller, Helping Hand, Kind Soul, Vibe Check) with Grand Completion Bounty (+200 🫐, +2 💖).",
        "• y!higherlower <amt> (y!hl) — Higher or Lower guessing game (playing cards 1 to 13, Ace to King). Streaks escalate multipliers from 1.5x up to 20x+! Hitting 1 or 13 resets/reshuffles the deck. Command 'y!hl reset' cancels/cashes out.",
        "• y!coinflip <amt> (y!flip, y!cf) — Flip a coin with 40% chance of absurdity (you diving across the table stealing the coin shouting 'mehehhehehe', bald eagle attack, sewer drain, zero gravity). Tough win odds (~28%) but pays 2.5x payout!",
        "• y!blackjack <amt> (y!bj) — Classic 21 against you. Rare comedy cards (Uno Reverse, Blue-Eyes White Dragon, bitten strawberry card, boba coupon).",
        "• y!crash <amt> — Rising rocket multiplier ticking up in real-time. Cash out before explosion! Absurd crashes (space geese, berry smoothie fuel).",
        "• y!mines <amt> [mines] (y!mine) — Interactive 5x5 minefield (1-23 mines). Click tiles to find gems (96% fair RTP multiplier) and cash out before hitting a bomb!",
        "• y!wordle <amt> — 5-stage progressive word-guessing gauntlet with persistent pot (1.8x up to 40x + 2 Virtue). Guess via modal or 'y!guess <word>', and choose to Cash Out or Risk & Advance!",
        "• y!streak [@user] (y!winstreak) — Gamble win streak tracker (+5% profit scaling per win up to +50%, plus milestone berry windfalls up to +7,500 🫐). Top streaks shown on 'y!lb streak'!",
        "• y!dare @user <amt> / y!dare <amt> — Unhinged dares. When users submit proof via 'y!checkdare <proof>', YOU evaluate and judge [PASS] or [FAIL] with cheeky commentary!",
        "• y!aid @user — Helping a user: 50% success (+berries, +1 Virtue), 25% disaster blunder (-1 Virtue, +1 Sin), 25% rude refusal.",
        "• y!doubleaid @user — Married couples team up for a 2x Super Aid (60-140 berries, +2 Virtue, vault kickback).",
        "• y!steal @user — Pickpocketing berries with risk of being caught and paying restitution (defended by Divine Wards and Karmic Aura).",
        "• y!doublesteal @victim — Married couples tag-team heist! Snatches 25-45% of victim's berries, auto-depositing 15% into your joint vault and splitting the rest 50/50!",
        "• y!work — Honest shifts around Yuna's district (60-150 berries, +2% wage per Virtue point, 25% chance of +1 Virtue).",
        "• y!crime — High-risk underworld heists for 120-280 berries (35% risk of getting busted and fined).",
        "• y!fish — Enchanted berry pond fishing for rare catches and Dragon Pearls (+1 Virtue).",
        "• y!shop & y!buy <item> [qty] — Curio shop selling Divine Ward (anti-theft zap), Lucky Clover (+25% luck), Energy Drink (resets cooldowns), Phantom Mask (0 Sin & +30% loot), Eternal Diamond (doubles vault interest to 10%), Divorce Insurance (halves divorce fee to 5k), and Empress Crown (vanity).",
        "• y!inventory (y!inv) & y!use <item> — Inspect bag and activate consumables.",
        "• y!donate <amt> — Donate berries to gain Virtue (showers a random member).",
        "• y!marry @user & y!divorce — Completely unserious marriage; divorce costs 10,000 berries in legal fees (5,000 with Insurance) and splits joint vault 50/50.",
        "• y!shared (or y!joint, y!vault) — Matrimonial shared bank account with +5% (or +10% with Diamond) daily passive love interest.",
        "• y!leaderboard (y!lb) & y!achievements (y!ach) — Ranks and 34 collectible trophies.",
        "• y!song (or y!np) — Displays your active Spotify playback with cover art.",
        "• y!play <song> — Changes your active song and Rich Presence status.",
    ]

    if YUNA_RPC_AVAILABLE and yuna_rpc:
        try:
            curr_song = yuna_rpc.get_current_track_info()
            if curr_song:
                lines.extend([
                    "",
                    f"🎧 CURRENTLY LISTENING TO: \"{curr_song['title']}\" by {curr_song['artist']} (Album: {curr_song['album']})",
                    "- You are wearing your headphones listening to this song on Spotify via Kizzy RPC.",
                    "- If users ask what you are listening to or mention music, banter and chat about this track naturally!"
                ])
        except Exception:
            pass

    if user_id:
        uid = str(user_id)
        stats = _USER_STATS.get(uid, {})
        berries = stats.get("berries", 0)
        virtue = stats.get("virtue", 0)
        sin = stats.get("sin", 0)
        spouse = stats.get("spouse")
        spouse_str = f"<@{spouse}>" if spouse else "Single"
        bankrupt = stats.get("bankrupt_count", 0)
        active_dare = _ACTIVE_DARES.get(uid, {}).get("dare", "None")
        inv = stats.get("inventory", {})
        inv_str = ", ".join(f"{k}: {v}" for k, v in inv.items() if v > 0) or "Empty"
        buffs = []
        if stats.get("clover_active"):
            buffs.append("Lucky Clover")
        if stats.get("mask_active"):
            buffs.append("Phantom Mask")
        buff_str = ", ".join(buffs) or "None"

        lines.extend([
            "",
            f"🎯 ACTIVE SPEAKER'S BERRY & MORALITY PROFILE (ID: {uid}):",
            f"  • Pouch: {berries} 🫐 Berries",
            f"  • Virtue: {virtue} 💖 | Sin: {sin} ❤️‍🔥",
            f"  • Marital Status: {spouse_str}",
            f"  • Bag / Inventory: {inv_str}",
            f"  • Active Status Buffs: {buff_str}",
            f"  • Times Bankrupt: {bankrupt}",
            f"  • Active Dare Pending: \"{active_dare}\"",
            "",
            "CONSCIOUSNESS DIRECTIVE:",
            "- You can actively see and read what commands people run and what happens in your gambling den.",
            "- If users talk to you about their berries, ask for free berries, complain about your coin theft in coinflip, or boast about their wins, RESPOND DIRECTLY using their actual stats above!",
            "- If they are broke (0 berries), tease them playfully about their bad luck or suggest they go do 'y!aid' to get more berries.",
            "- Always maintain your signature witty, cheeky, playful Yuna anime personality!"
        ])

    lines.append("=" * 50)
    return "\n".join(lines)

# ─── MAIN PREFIX DISPATCHER ─────────────────────────────────────────────────

async def handle_yuna_prefix_command(message, client, raw_content: str, ask_ai_fn=None, context_logger_fn=None) -> bool:
    """Dispatches 'y!' prefix commands."""
    global _AI_CALLER, _CONTEXT_LOGGER
    if ask_ai_fn:
        _AI_CALLER = ask_ai_fn
    if context_logger_fn:
        _CONTEXT_LOGGER = context_logger_fn

    if not raw_content.lower().startswith("y!"):
        return False

    cmd_body = raw_content[2:].strip()
    if not cmd_body:
        await handle_help(message, client, [])
        return True

    parts = cmd_body.split()
    cmd = parts[0].lower()
    args = parts[1:]
    author_id = str(message.author.id)

    # ── Normalize multi-word command aliases ──
    if cmd == "call" and args and args[0].lower() == "aid":
        cmd = "callaid"
        args = args[1:]
    elif cmd in ("call-aid", "call_aid"):
        cmd = "callaid"
    elif cmd == "set" and args and args[0].lower() == "sin":
        cmd = "setsin"
        args = args[1:]
    elif cmd in ("set-sin", "set_sin"):
        cmd = "setsin"
    elif cmd == "double" and args and args[0].lower() in ("aid", "steal"):
        cmd = f"double{args[0].lower()}"
        args = args[1:]
    elif cmd in ("double-aid", "double_aid"):
        cmd = "doubleaid"
    elif cmd in ("double-steal", "double_steal"):
        cmd = "doublesteal"
    elif cmd == "date" and args and args[0].lower() == "night":
        cmd = "datenight"
        args = args[1:]
    elif cmd == "love" and args and args[0].lower() == "gift":
        cmd = "lovegift"
        args = args[1:]
    elif cmd == "marriage" and args and args[0].lower() == "vow":
        cmd = "vow"
        args = args[1:]

    # ── Boss Encounter Traps (Juny) ──
    if author_id in _PENDING_BOSS_ENCOUNTERS:
        if cmd in ("plead", "beg", "spare"):
            await process_boss_choice(message, client, author_id, "plead")
            return True
        elif cmd in ("fight", "duel", "brawl"):
            await process_boss_choice(message, client, author_id, "fight")
            return True
        elif cmd in ("negotiate", "bargain", "pact", "deal"):
            await process_boss_choice(message, client, author_id, "negotiate")
            return True
        elif cmd in ("callaid", "summons", "summonaid"):
            await handle_boss_callaid(message, client, args)
            return True
        elif cmd in ("boss", "juny"):
            await _safe_send_reply(message, "😈 **Juny** is waiting for your decision! Choose: `y!plead`, `y!fight`, `y!call aid`, or `y!negotiate`!")
            return True
        else:
            await _safe_send_reply(
                message,
                f"⚠️ **JUNY IS BLOCKING YOUR PATH!**\n"
                f"*Juny's obsidian wings snap shut before you!* \"You cannot run or ignore your sins! Choose your fate: `y!plead`, `y!fight`, `y!call aid`, or `y!negotiate`!\""
            )
            return True

    # ── Active Boss Battle Controls ──
    if author_id in _ACTIVE_BOSS_FIGHTS or any(author_id in c.get("party", {}) for c in _ACTIVE_BOSS_FIGHTS.values()):
        if cmd in ("attack", "atk", "strike", "slash"):
            await handle_boss_attack(message, client, args)
            return True
        elif cmd in ("dodge", "evade"):
            await handle_boss_dodge(message, client, args)
            return True
        elif cmd in ("useitem", "combatitem", "bossitem"):
            await handle_boss_item(message, client, args)
            return True
        elif cmd in ("callaid", "summons", "summonaid"):
            await handle_boss_callaid(message, client, args)
            return True
        elif cmd in ("boss", "juny", "combat", "bossstatus"):
            await handle_boss_status(message, client, args)
            return True

    # ── GoD-HeLL Dungeon Combat Controls & Co-op ──
    _d_host, _d_run = (yuna_rpg.get_user_dungeon_run(author_id)) if (YUNA_RPG_AVAILABLE and yuna_rpg) else (None, None)
    if _d_run:
        if cmd in ("attack", "atk", "strike", "slash"):
            await yuna_rpg.handle_dattack(message, client, args, sys.modules[__name__])
            return True
        elif cmd in ("skill", "cast", "spell", "dskill"):
            await yuna_rpg.handle_dskill(message, client, args, sys.modules[__name__])
            return True
        elif cmd in ("heal", "potion", "elixir", "dheal"):
            await yuna_rpg.handle_dheal(message, client, args, sys.modules[__name__])
            return True
        elif cmd in ("flee", "retreat", "run", "dflee"):
            await yuna_rpg.handle_dflee(message, client, args, sys.modules[__name__])
            return True
        elif cmd in ("godhell", "dungeon", "raid", "status", "dstatus"):
            await yuna_rpg.handle_godhell(message, client, args, sys.modules[__name__])
            return True
        elif cmd in ("callaid", "call", "dcallaid", "dcoop", "dparty"):
            await yuna_rpg.handle_dcallaid(message, client, args, sys.modules[__name__])
            return True

    res = await _dispatch_yuna_command(message, client, cmd, args, author_id)
    if res and cmd not in ("help", "commands", "cmd", "cmds", "info", "guide", "boss", "juny", "plead", "fight", "negotiate", "attack", "dodge", "useitem", "callaid", "setsin", "set-sin", "set", "streak", "winstreak", "streaks", "guess", "w", "next", "advance", "continue", "auction", "auctions", "bid", "arena", "train", "skills", "godhell", "dungeon", "dattack", "dskill", "dheal", "dflee", "dcallaid", "dcoop", "dparty", "djoin", "battleshop", "bbuy", "equip"):
        if author_id not in _ACTIVE_BOSS_FIGHTS and author_id not in _PENDING_BOSS_ENCOUNTERS and author_id not in _ACTIVE_WORDLE_GAMES and author_id not in _ACTIVE_MINES_GAMES and not _d_run:
            await check_boss_trigger(message, client, author_id)
    return res

async def _dispatch_yuna_command(message, client, cmd: str, args: list, author_id: str) -> bool:
    # Balance & Profile
    if cmd in ("balance", "bal", "money", "berries", "berry", "profile"):
        await handle_balance(message, client, args)
        return True

    # Streak & Hall of Fame
    elif cmd in ("streak", "winstreak", "streaks", "winrate"):
        await handle_streak(message, client, args)
        return True

    # Daily Allowance & Everyday Tasks
    elif cmd in ("daily", "claim", "dailyreward", "allowance"):
        await handle_daily(message, client, args)
        return True

    elif cmd in ("tasks", "task", "dailies", "tasklist", "todo", "quests", "quest"):
        await handle_tasks(message, client, args)
        return True

    # Morality
    elif cmd in ("aid", "helpout", "assist", "support"):
        await handle_aid(message, client, args)
        return True

    elif cmd in ("steal", "rob", "pickpocket", "mug"):
        await handle_steal(message, client, args)
        return True

    elif cmd in ("donate", "charity", "bless", "giveaway"):
        await handle_donate(message, client, args)
        return True

    # Transfers
    elif cmd in ("give", "pay", "transfer", "send"):
        await handle_give(message, client, args)
        return True

    # Casino Games
    elif cmd in ("blackjack", "bj", "21"):
        await handle_blackjack(message, client, args)
        return True

    elif cmd == "hit":
        await handle_hit(message, client, args)
        return True

    elif cmd in ("stand", "stay"):
        await handle_stand(message, client, args)
        return True

    elif cmd in ("crash", "rocket"):
        await handle_crash(message, client, args)
        return True

    # Mines & Progressive Wordle
    elif cmd in ("mines", "mine", "minesweeper"):
        await handle_mines(message, client, args)
        return True

    elif cmd in ("wordle", "word", "wordlegame"):
        await handle_wordle(message, client, args)
        return True

    elif cmd in ("higherlower", "hl"):
        await handle_higherlower(message, client, args)
        return True

    elif cmd in ("guess", "w"):
        if author_id in _ACTIVE_WORDLE_GAMES:
            await handle_wordle_guess(message, client, args)
            return True
        elif cmd == "guess":
            await handle_higherlower(message, client, args)
            return True

    elif cmd in ("advance", "continue") or (cmd == "next" and author_id in _ACTIVE_WORDLE_GAMES):
        await handle_wordle_next(message, client, args)
        return True

    elif cmd in ("higher", "h", "up"):
        await handle_higher(message, client, args)
        return True

    elif cmd in ("lower", "l", "down"):
        await handle_lower(message, client, args)
        return True

    elif cmd in ("coinflip", "flip", "cf"):
        await handle_coinflip(message, client, args)
        return True

    elif cmd in ("roulette", "rouellete", "wheel", "spin"):
        await handle_roulette(message, client, args)
        return True

    elif cmd in ("poker", "videopoker", "vp"):
        await handle_poker(message, client, args)
        return True

    elif cmd in ("hold", "keep"):
        await handle_poker_hold(message, client, args)
        return True

    elif cmd in ("draw", "swap"):
        author_id = str(message.author.id)
        if author_id in _ACTIVE_POKER_GAMES:
            await handle_poker_draw(message, client, args)
            return True
        await _safe_send_reply(message, "You don't have an active poker hand! Deal one with `y!poker <amount>`.")
        return True

    elif cmd in ("fold", "surrender"):
        author_id = str(message.author.id)
        if author_id in _ACTIVE_POKER_GAMES:
            await execute_poker_fold(message, author_id)
            return True
        await _safe_send_reply(message, "You don't have an active poker hand to fold!")
        return True

    elif cmd in ("dice", "roll", "craps", "dicebet", "dices"):
        await handle_dice(message, client, args)
        return True

    elif cmd in ("cashout", "cash", "bail"):
        author_id = str(message.author.id)
        if author_id in _ACTIVE_MINES_GAMES:
            await handle_mines_cashout(message, client, args)
            return True
        elif author_id in _ACTIVE_WORDLE_GAMES:
            await handle_wordle_cashout(message, client, args)
            return True
        elif author_id in _ACTIVE_HL_GAMES:
            await handle_hl_cashout(message, client, args)
            return True
        elif author_id in _ACTIVE_CRASH_GAMES:
            await handle_cashout(message, client, args)
            return True
        else:
            await _safe_send_reply(message, "You don't have an active Mines, Wordle, Crash, or Higher/Lower game to cash out!")
            return True

    # Social Wagers & Challenges
    elif cmd in ("bet", "wager"):
        if message.mentions or any(a.startswith("<@") for a in args):
            await handle_bet(message, client, args)
        else:
            await handle_coinflip(message, client, args)
        return True

    elif cmd in ("fight", "duel", "brawl"):
        await handle_fight(message, client, args)
        return True

    elif cmd in ("dare", "tod"):
        if message.mentions or any(a.startswith("<@") for a in args):
            await handle_dare(message, client, args)
        else:
            await handle_solo_dare(message, client, args)
        return True

    elif cmd in ("truth", "asktruth", "truthordare"):
        if message.mentions or any(a.startswith("<@") for a in args):
            await handle_truth(message, client, args)
        else:
            await handle_solo_truth(message, client, args)
        return True

    elif cmd in ("checkdare", "checktruth", "completedare", "completetruth", "proof", "claimdare", "daredone", "truthdone"):
        await handle_checkdare(message, client, args)
        return True

    elif cmd in ("rerolldare", "rerolltruth", "reroll"):
        await handle_rerolldare(message, client, args)
        return True

    elif cmd in ("activedare", "activetruth", "mydare", "mytruth", "currentdare", "currenttruth", "truthstatus"):
        await handle_active_dare(message, client, args)
        return True

    elif cmd in ("forfeitdare", "forfeittruth", "canceldare", "canceltruth", "surrenderdare", "quitdare"):
        await handle_forfeitdare(message, client, args)
        return True

    elif cmd == "reset":
        author_id = str(message.author.id)
        if author_id in _ACTIVE_WORDLE_GAMES:
            await process_wordle_give_up(_ACTIVE_WORDLE_GAMES[author_id], view=_ACTIVE_WORDLE_GAMES[author_id].get("view"))
            return True
        elif author_id in _ACTIVE_HL_GAMES:
            await process_hl_reset(_ACTIVE_HL_GAMES[author_id])
            return True
        elif author_id in _ACTIVE_POKER_GAMES:
            await execute_poker_fold(message, author_id)
            return True
        elif author_id in _ACTIVE_DARES:
            await handle_forfeitdare(message, client, args)
            return True
        else:
            await _safe_send_reply(message, "- *Yuna tilts her head* 'You do not have an active game or dare to reset!'")
            return True

    elif cmd in ("trade", "escrow"):
        await handle_trade(message, client, args)
        return True

    elif cmd in ("accept", "yes", "agree"):
        await handle_accept(message, client, args)
        return True

    elif cmd in ("decline", "no", "deny", "refuse"):
        await handle_decline(message, client, args)
        return True

    # Marriage & Romance System
    elif cmd in ("marry", "propose"):
        await handle_marry(message, client, args)
        return True

    elif cmd in ("marriage", "spouse", "couple", "anniversary"):
        await handle_marriage(message, client, args)
        return True

    elif cmd in ("vow", "marriagevow"):
        await handle_vow(message, client, args)
        return True

    elif cmd in ("kiss", "cuddle", "hug", "smooch"):
        await handle_kiss(message, client, args)
        return True

    elif cmd in ("date", "datenight"):
        await handle_date(message, client, args)
        return True

    elif cmd in ("gift", "lovegift", "spousedonate", "spousetransfer"):
        await handle_lovegift(message, client, args)
        return True

    elif cmd in ("divorce", "breakup"):
        await handle_divorce(message, client, args)
        return True

    # Matrimonial Joint Vault & Teamwork
    elif cmd in ("shared", "joint", "vault", "jointaccount", "sharedaccount"):
        await handle_shared(message, client, args)
        return True

    elif cmd in ("doubleaid", "coupleaid", "superaid", "duoaid"):
        await handle_doubleaid(message, client, args)
        return True

    elif cmd in ("doublesteal", "doublesteak", "duosteal", "tagsteal", "couplesteal"):
        await handle_doublesteal(message, client, args)
        return True

    # Work, Crime & Fishing Activities
    elif cmd in ("work", "job", "shift"):
        await handle_work(message, client, args)
        return True

    elif cmd in ("crime", "heist", "hustle"):
        await handle_crime(message, client, args)
        return True

    elif cmd in ("fish", "fishing", "cast"):
        await handle_fish(message, client, args)
        return True

    # Shop & Inventory
    elif cmd in ("shop", "store", "market", "bazaar"):
        await handle_shop(message, client, args)
        return True

    elif cmd in ("buy", "purchase"):
        await handle_buy(message, client, args)
        return True

    elif cmd in ("inventory", "inv", "bag", "pouch"):
        await handle_inventory(message, client, args)
        return True

    elif cmd in ("use", "drink", "consume"):
        await handle_use(message, client, args)
        return True

    # ── RPG, GoD-HeLL Dungeon & Berry Auction Ecosystem ──
    elif cmd in ("auction", "auctions"):
        if YUNA_RPG_AVAILABLE and yuna_rpg:
            await yuna_rpg.handle_auction(message, client, args, sys.modules[__name__])
        else:
            await _safe_send_reply(message, "Berry Auctions are currently loading!")
        return True

    elif cmd in ("bid", "placebid"):
        if YUNA_RPG_AVAILABLE and yuna_rpg:
            await yuna_rpg.handle_bid(message, client, args, sys.modules[__name__])
        else:
            await _safe_send_reply(message, "Berry Auctions are currently loading!")
        return True

    elif cmd in ("auctioncatalog", "auctionslist", "auctionitems", "trophiescatalog"):
        if YUNA_RPG_AVAILABLE and yuna_rpg:
            await yuna_rpg.handle_auctions_catalog(message, client, args, sys.modules[__name__])
        else:
            await _safe_send_reply(message, "Auction Catalog is currently loading!")
        return True

    elif cmd in ("arena", "colosseum"):
        if YUNA_RPG_AVAILABLE and yuna_rpg:
            await yuna_rpg.handle_arena(message, client, args, sys.modules[__name__])
        else:
            await _safe_send_reply(message, "The Arena is currently loading!")
        return True

    elif cmd in ("train", "training"):
        if YUNA_RPG_AVAILABLE and yuna_rpg:
            await yuna_rpg.handle_train(message, client, args, sys.modules[__name__])
        else:
            await _safe_send_reply(message, "Arena Training is currently loading!")
        return True

    elif cmd in ("skills", "skill", "weirdskills", "marital"):
        if YUNA_RPG_AVAILABLE and yuna_rpg:
            await yuna_rpg.handle_skills(message, client, args, sys.modules[__name__])
        else:
            await _safe_send_reply(message, "Skills codex is currently loading!")
        return True

    elif cmd in ("godhell", "dungeon", "god-hell", "raid"):
        if YUNA_RPG_AVAILABLE and yuna_rpg:
            await yuna_rpg.handle_godhell(message, client, args, sys.modules[__name__])
        else:
            await _safe_send_reply(message, "GoD-HeLL is currently loading!")
        return True

    elif cmd in ("dattack", "datk", "dstrike"):
        if YUNA_RPG_AVAILABLE and yuna_rpg:
            await yuna_rpg.handle_dattack(message, client, args, sys.modules[__name__])
        else:
            await _safe_send_reply(message, "GoD-HeLL is currently loading!")
        return True

    elif cmd in ("dskill", "dcast"):
        if YUNA_RPG_AVAILABLE and yuna_rpg:
            await yuna_rpg.handle_dskill(message, client, args, sys.modules[__name__])
        else:
            await _safe_send_reply(message, "GoD-HeLL is currently loading!")
        return True

    elif cmd in ("dheal", "dpotion", "delixir"):
        if YUNA_RPG_AVAILABLE and yuna_rpg:
            await yuna_rpg.handle_dheal(message, client, args, sys.modules[__name__])
        else:
            await _safe_send_reply(message, "GoD-HeLL is currently loading!")
        return True

    elif cmd in ("dflee", "dretreat"):
        if YUNA_RPG_AVAILABLE and yuna_rpg:
            await yuna_rpg.handle_dflee(message, client, args, sys.modules[__name__])
        else:
            await _safe_send_reply(message, "GoD-HeLL is currently loading!")
        return True

    elif cmd in ("dcallaid", "dcoop", "dparty"):
        if YUNA_RPG_AVAILABLE and yuna_rpg:
            await yuna_rpg.handle_dcallaid(message, client, args, sys.modules[__name__])
        else:
            await _safe_send_reply(message, "GoD-HeLL Co-op is currently loading!")
        return True

    elif cmd in ("djoin", "joinraid"):
        if YUNA_RPG_AVAILABLE and yuna_rpg:
            await yuna_rpg.handle_djoin(message, client, args, sys.modules[__name__])
        else:
            await _safe_send_reply(message, "GoD-HeLL Co-op is currently loading!")
        return True

    elif cmd in ("battleshop", "armory", "bshop", "gearshop"):
        if YUNA_RPG_AVAILABLE and yuna_rpg:
            await yuna_rpg.handle_battleshop(message, client, args, sys.modules[__name__])
        else:
            await _safe_send_reply(message, "Battle Shop is currently loading!")
        return True

    elif cmd in ("bbuy", "battlebuy"):
        if YUNA_RPG_AVAILABLE and yuna_rpg:
            await yuna_rpg.handle_bbuy(message, client, args, sys.modules[__name__])
        else:
            await _safe_send_reply(message, "Battle Shop is currently loading!")
        return True

    elif cmd in ("equip", "gear", "equipment"):
        if YUNA_RPG_AVAILABLE and yuna_rpg:
            await yuna_rpg.handle_equip(message, client, args, sys.modules[__name__])
        else:
            await _safe_send_reply(message, "Equipment system is currently loading!")
        return True

    # Leaderboard & Achievements
    elif cmd in ("leaderboard", "lb", "top", "richest", "ranking", "rankings"):
        await handle_leaderboard(message, client, args)
        return True

    elif cmd in ("achievements", "achievement", "ach", "trophies", "trophy", "badges"):
        await handle_achievements(message, client, args)
        return True

    # Music & Kizzy RPC
    elif cmd in ("song", "np", "nowplaying", "music", "listening"):
        await handle_now_playing(message, client, args)
        return True

    elif cmd in ("play", "listen"):
        await handle_play_song(message, client, args)
        return True

    elif cmd in ("skip", "next"):
        await handle_skip_song(message, client, args)
        return True

    elif cmd in ("playlist", "queue"):
        await handle_playlist(message, client, args)
        return True

    # Boss Fight Commands (Juny - Heaven's Worst Angel)
    elif cmd in ("plead", "beg", "spare"):
        if author_id in _PENDING_BOSS_ENCOUNTERS:
            await process_boss_choice(message, client, author_id, "plead")
            return True
        await _safe_send_reply(message, "- *Yuna snickers* \"Who are you pleading to? Juny hasn't caught you yet!\"")
        return True

    elif cmd in ("negotiate", "bargain", "pact", "deal"):
        if author_id in _PENDING_BOSS_ENCOUNTERS:
            await process_boss_choice(message, client, author_id, "negotiate")
            return True
        await _safe_send_reply(message, "- *Yuna tilts her head* \"You can only negotiate dark pacts when Juny descends upon you!\"")
        return True

    elif cmd in ("attack", "atk", "strike", "slash"):
        await handle_boss_attack(message, client, args)
        return True

    elif cmd in ("dodge", "evade"):
        await handle_boss_dodge(message, client, args)
        return True

    elif cmd in ("useitem", "combatitem", "bossitem"):
        await handle_boss_item(message, client, args)
        return True

    elif cmd in ("callaid", "summons", "summonaid"):
        await handle_boss_callaid(message, client, args)
        return True

    elif cmd in ("boss", "juny", "bossstatus", "combat"):
        await handle_boss_status(message, client, args)
        return True

    # Admin & Karmic Controls
    elif cmd in ("setsin", "set-sin") or (cmd == "set" and args and args[0].lower() == "sin"):
        real_args = args[1:] if (cmd == "set" and args and args[0].lower() == "sin") else args
        await handle_set_sin(message, client, real_args)
        return True

    # Help
    elif cmd in ("help", "commands", "cmd", "cmds", "info", "guide"):
        await handle_help(message, client, args)
        return True

    else:
        await _safe_send_reply(
            message,
            f"*Yuna tilts her head* \"Huh? I don't know `y!{cmd}`! Type `y!help` to see my games, wagers, and commands!\""
        )
        return True
