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
import math
import random
import asyncio
import shutil
import aiohttp
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from decimal import Decimal
import threading

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

try:
    import yuna_pact
    YUNA_PACT_AVAILABLE = True
except Exception as _yp_err:
    print(f"[YUNA PACT IMPORT NOTE] {_yp_err}")
    yuna_pact = None
    YUNA_PACT_AVAILABLE = False

try:
    import yuna_games
    YUNA_GAMES_AVAILABLE = True
except Exception as _ygm_err:
    print(f"[YUNA GAMES IMPORT NOTE] {_ygm_err}")
    yuna_games = None
try:
    import yuna_fishing
    YUNA_FISHING_AVAILABLE = True
except Exception as _yfish_err:
    print(f"[YUNA FISHING IMPORT NOTE] {_yfish_err}")
    yuna_fishing = None
    YUNA_FISHING_AVAILABLE = False

try:
    import yuna_id_guard
    YUNA_ID_GUARD_AVAILABLE = True
except Exception as _yidg_err:
    print(f"[YUNA ID GUARD IMPORT NOTE] {_yidg_err}")
    yuna_id_guard = None
    YUNA_ID_GUARD_AVAILABLE = False

SCRIPT_DIR = Path(__file__).parent.resolve()
DATA_DIR = SCRIPT_DIR / "data"
GAMBLING_DATA_FILE = DATA_DIR / "yuna_gambling.json"
AUDIT_LOG_FILE = DATA_DIR / "player_stats_audit.log"
BACKUPS_DIR = DATA_DIR / "backups"
LOCK_FILE_PATH = Path("/data/data/com.termux/files/home/.yuna_gambling.lock")
YUNA_USER_ID = "yuna"
YUNA_BOT_DEFAULT_ID = "1533213082158108702"
YUNA_BOT_NAME = "Yuna ⭐"
PERMANENT_SPOUSE_ID = "1155074026230788200"
PERMANENT_SPOUSE_NAME = "deeploveluniel"

def is_yuna_instance(client=None) -> bool:
    """
    Returns True if the current executing context or bot client is Yuna.
    Ensures permanent spouse and anti-infidelity protections apply strictly to Yuna,
    without altering or affecting any other bots (Law, Juny, Renee, Brilliance, etc.).
    """
    # 1. Check client if provided
    if client is not None and getattr(client, "user", None):
        c_uid = str(client.user.id)
        c_name = getattr(client.user, "name", "").lower()
        if c_uid in (YUNA_BOT_DEFAULT_ID, "yuna") or "yuna" in c_name:
            return True
        # If client belongs to another known child bot, return False
        if any(k in c_name for k in ("law", "juny", "renee", "briliance", "brilliance", "maiko")):
            return False
        if c_uid in ("1530280945960226927", "1173146642124394547", "1542233386175832154", "1551443856958955580"):
            return False

    # 2. Check process environment BOT_ID (set by supervisor for child workers)
    env_bid = os.getenv("BOT_ID")
    if env_bid:
        if env_bid in ("bot_ek0ldel3", "yuna"):
            return True
        return False

    # Default fallback: If not explicitly running as another bot, True (for standalone Yuna / test scripts)
    return True


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

async def _safe_defer(interaction: discord.Interaction, ephemeral: bool = False, thinking: bool = False):
    """Safely defers interaction, ignoring expired or already acknowledged interactions."""
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=ephemeral, thinking=thinking)
    except (discord.NotFound, discord.HTTPException):
        pass

async def _safe_send_ephemeral(interaction: discord.Interaction, content: str = None, **kwargs):
    """Safely sends ephemeral response, ignoring expired interactions."""
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(content, ephemeral=True, **kwargs)
        else:
            await interaction.followup.send(content, ephemeral=True, **kwargs)
    except (discord.NotFound, discord.HTTPException):
        pass


_UPDATE_SENTINEL = object()

async def _safe_update_game_message(
    interaction: Optional[discord.Interaction] = None,
    message: Optional[discord.Message] = None,
    content: Any = _UPDATE_SENTINEL,
    embed: Any = _UPDATE_SENTINEL,
    view: Any = _UPDATE_SENTINEL
) -> bool:
    """Safely updates game message across interaction responses, channel messages, and webhooks."""
    kwargs = {}
    if content is not _UPDATE_SENTINEL:
        kwargs["content"] = content
    if embed is not _UPDATE_SENTINEL:
        kwargs["embed"] = embed
    if view is not _UPDATE_SENTINEL:
        kwargs["view"] = view

    # 1. Try immediate interaction response (type 7 UPDATE_MESSAGE)
    if interaction and not interaction.response.is_done():
        try:
            await interaction.response.edit_message(**kwargs)
            return True
        except (discord.NotFound, discord.HTTPException, Exception):
            pass

    # 2. Try editing via interaction.message if available (bot-authored message)
    target_msg = getattr(interaction, "message", None)
    if target_msg:
        try:
            await target_msg.edit(**kwargs)
            if interaction and not interaction.response.is_done():
                try:
                    await interaction.response.defer()
                except Exception:
                    pass
            return True
        except Exception:
            pass

    # 3. Try edit_original_response if interaction is done (for slash commands / interaction webhooks)
    if interaction and interaction.response.is_done():
        try:
            await interaction.edit_original_response(**kwargs)
            return True
        except Exception:
            pass

    # 4. Fallback to editing message IF message is bot-authored
    if message and message != target_msg:
        try:
            await message.edit(**kwargs)
            return True
        except Exception:
            pass

    # 5. Final fallback: If this was a direct text command or editing failed, send a new reply
    if message:
        send_kw = {}
        if content is not _UPDATE_SENTINEL and content is not None:
            send_kw["content"] = content
        if embed is not _UPDATE_SENTINEL and embed is not None:
            send_kw["embed"] = embed
        if view is not _UPDATE_SENTINEL and view is not None:
            send_kw["view"] = view
        try:
            res = await _safe_send_reply(message, **send_kw)
            return res is not None
        except Exception:
            pass

    return False

class ResilientView(View):
    """Base View that gracefully suppresses 10062 Unknown Interaction and expired interaction errors."""
    async def on_error(self, interaction: discord.Interaction, error: Exception, item: Any = None) -> None:
        if isinstance(error, discord.NotFound) and getattr(error, 'code', None) == 10062:
            return
        if isinstance(error, discord.HTTPException) and getattr(error, 'code', None) == 40060:
            return
        import traceback
        traceback.print_exc()

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
_LAST_DOUBLE_FISH_TIME: Dict[str, float] = {}  # user_id -> last double fish timestamp
_LAST_DONATE_TIME: Dict[str, float] = {}       # user_id -> last donate timestamp
_LAST_DATE_TIME: Dict[str, float] = {}         # user_id -> last romantic date timestamp
_LAST_KISS_TIME: Dict[str, float] = {}         # user_id -> last kiss timestamp
_ACTIVE_BLACKJACK_GAMES: Dict[str, dict] = {} # user_id -> game state
_ACTIVE_CRASH_GAMES: Dict[str, dict] = {}     # user_id -> game state
_ACTIVE_HL_GAMES: Dict[str, dict] = {}        # user_id -> higher/lower game state
_ACTIVE_POKER_GAMES: Dict[str, dict] = {}     # user_id -> poker game state
_ACTIVE_MINES_GAMES: Dict[str, dict] = {}     # user_id -> mines game state
_ACTIVE_WORDLE_GAMES: Dict[str, dict] = {}    # user_id -> wordle game state
_ACTIVE_DARES: Dict[str, dict] = {}           # user_id -> active dare state
_DELETED_DARES: set = set()                   # user_ids of explicitly deleted/forfeited dares to sync to disk
_PENDING_CHALLENGES: Dict[str, dict] = {}     # challenge_id -> challenge state
CHALLENGES_FILE = DATA_DIR / "pending_challenges.json"

def _load_pending_challenges() -> Dict[str, dict]:
    """Loads all pending challenges from disk, merging with in-memory store and pruning expired challenges (>10 mins)."""
    global _PENDING_CHALLENGES
    now = time.time()
    disk_data = {}
    if CHALLENGES_FILE.exists():
        try:
            with open(CHALLENGES_FILE, "r", encoding="utf-8") as f:
                disk_data = json.load(f)
        except Exception:
            disk_data = {}

    merged = {}
    for cid, cdata in {**disk_data, **_PENDING_CHALLENGES}.items():
        if isinstance(cdata, dict) and now - cdata.get("created_at", now) < 600:
            merged[cid] = cdata
    _PENDING_CHALLENGES = merged
    return merged

def _save_pending_challenges(challenges: Optional[Dict[str, dict]] = None):
    """Saves pending challenges to disk atomically."""
    global _PENDING_CHALLENGES
    if challenges is not None:
        _PENDING_CHALLENGES = challenges
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    clean_dict = {}
    for cid, cdata in _PENDING_CHALLENGES.items():
        if isinstance(cdata, dict):
            clean_dict[cid] = {
                "author_id": str(cdata.get("author_id", "")),
                "author_mention": str(cdata.get("author_mention", "")),
                "target_id": str(cdata.get("target_id", "")),
                "target_mention": str(cdata.get("target_mention", "")),
                "amount": int(cdata.get("amount", 0)),
                "challenge_type": str(cdata.get("challenge_type", "fight")),
                "custom_text": cdata.get("custom_text"),
                "channel_id": getattr(getattr(cdata.get("message"), "channel", None), "id", None) or cdata.get("channel_id"),
                "message_id": getattr(cdata.get("message"), "id", None) or cdata.get("message_id"),
                "created_at": cdata.get("created_at", time.time())
            }
    tmp_path = DATA_DIR / f"pending_challenges_{os.getpid()}_{time.time()}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(clean_dict, f, indent=2)
        os.replace(tmp_path, CHALLENGES_FILE)
    except Exception as e:
        if tmp_path.exists():
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        print(f"[PENDING CHALLENGES SAVE ERROR] {e}")

def _add_pending_challenge(c_id: str, challenge_data: dict):
    global _PENDING_CHALLENGES
    _load_pending_challenges()
    _PENDING_CHALLENGES[c_id] = challenge_data
    _save_pending_challenges()

def _remove_pending_challenge(c_id: str):
    global _PENDING_CHALLENGES
    _load_pending_challenges()
    _PENDING_CHALLENGES.pop(c_id, None)
    _save_pending_challenges()

def _remove_active_dare(uid: str):
    """Safely and permanently removes an active dare for a user, marking it deleted across snapshots and disk."""
    global _ACTIVE_DARES, _DELETED_DARES, _DARE_SNAPSHOTS
    _ACTIVE_DARES.pop(uid, None)
    _DELETED_DARES.add(uid)
    _DARE_SNAPSHOTS.pop(uid, None)

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
DOUBLE_FISH_COOLDOWN_SECONDS = 40.0 # 40 seconds for couples double fishing
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
    "potion": {
        "name": "HP Potion",
        "emoji": "🧪",
        "price": 25000,
        "type": "combat",
        "desc": "Combat healing brew. Restores 40% Max HP and 25 MP during fishing & boss battles! (Max hold: 5)"
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

CONTRACT_DEATH_SCENARIOS = [
    "📜 The Devil's Contract in your pocket bursts into violet hellfire, scorching your hands and incinerating your casino chips!",
    "👿 An infernal debt collector from Juny's celestial court kicks through the casino wall and confiscates your entire bet for back taxes!",
    "👁️ A dark rift tears open under your chair and pulls you down into the astral void for 5 seconds before spitting you back out, broke!",
    "🪶 A shower of cursed obsidian feathers pierces your casino cards, dissolving them into bubbling sulfur and dark mist!",
    "⚡ The seal on your unholy pact violently short-circuits the slot machine, causing it to blast you across the casino floor!"
]

async def check_karmic_or_contract_death(message, author_id: str, author_stats: dict, amount: int, game_name: str = "casino") -> bool:
    """
    Checks for random karmic (Sin) or contract-item deaths in casino games.
    If user carries Juny's Protection Charm, death is completely prevented!
    """
    has_charm = has_juny_charm(author_stats)
    has_contract = author_stats.get("dark_bargain") or (author_stats.get("inventory", {}).get("devil_contract", 0) > 0)
    _, eff_s = get_effective_morality(author_stats)

    # Contract random death chance (3.5%)
    if has_contract and random.random() < 0.035:
        if has_charm:
            await _safe_send_reply(
                message,
                f"🛡️ *Juny's Protection Charm erupted with dark feathers! Juny slapped the hellfire away with a bored scoff: 'Hands off my property.' Random death in {game_name} averted!*"
            )
            return False
        else:
            death_event = random.choice(CONTRACT_DEATH_SCENARIOS)
            async with _LOCK:
                _USER_STATS[author_id]["karmic_deaths"] = _USER_STATS[author_id].get("karmic_deaths", 0) + 1
                _save_data_sync(_USER_STATS)
            desc = (
                f"💀 **ABSURD CONTRACT CATASTROPHE!** 💀\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{death_event}\n\n"
                f"📜 *Your signed Devil's Contract triggered a violent burst of demonic interference!*\n"
                f"Your wager was obliterated: **-{amount:,}** 🫐\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            await _safe_send_reply(message, desc)
            return True

    # High-Sin Absurd Death
    if eff_s > 0:
        death_chance = min(0.15, 0.02 + eff_s * 0.004)
        if random.random() < death_chance:
            if has_charm:
                await _safe_send_reply(
                    message,
                    f"🛡️ *Juny's Protection Charm glowed bright crimson! Juny swatted away the falling catastrophe: 'Not on my watch, mortal.' High-sin death in {game_name} averted!*"
                )
                return False
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
                f"Your wager was obliterated: **-{amount:,}** 🫐\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━{banner}"
            )
            await _safe_send_reply(message, desc)
            return True

    return False

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
    },

    # ── Hardcore & Legendary Feats (20 New Harder Achievements) ──
    "immortal_streak": {
        "title": "Untouchable God of Fate",
        "desc": "Achieve a godlike consecutive win streak of 15 in casino gambling.",
        "icon": "⚡",
        "check": lambda s: s.get("max_win_streak", 0) >= 15
    },
    "century_gambler": {
        "title": "Casino High Sovereign",
        "desc": "Complete 2,500 total casino gambles.",
        "icon": "🏛️",
        "check": lambda s: s.get("total_gambles", 0) >= 2500
    },
    "berry_titan": {
        "title": "The Golden Hoard",
        "desc": "Accumulate 50,000,000 🫐 in your pouch at once.",
        "icon": "💰",
        "check": lambda s: s.get("berries", 0) >= 50000000
    },
    "berry_overlord": {
        "title": "Century Billionaire",
        "desc": "Accumulate 100,000,000 🫐 in your pouch at once.",
        "icon": "🌌",
        "check": lambda s: s.get("berries", 0) >= 100000000
    },
    "daily_legend_30": {
        "title": "Iron Will",
        "desc": "Maintain a 30-day uninterrupted daily claim streak.",
        "icon": "🗓️",
        "check": lambda s: s.get("daily_streak", 0) >= 30
    },
    "daily_mythic_60": {
        "title": "Eternal Devotion",
        "desc": "Maintain an incredible 60-day uninterrupted daily claim streak.",
        "icon": "⏳",
        "check": lambda s: s.get("daily_streak", 0) >= 60
    },
    "abyssal_loss_tycoon": {
        "title": "Abyssal Trench of Debt",
        "desc": "Lose a cumulative total of 1,000,000 🫐 to the house.",
        "icon": "📉",
        "check": lambda s: s.get("total_lost_berries", 0) >= 1000000
    },
    "midas_touch": {
        "title": "Midas Incarnate",
        "desc": "Win a cumulative total of 10,000,000 🫐 from gambling.",
        "icon": "👑",
        "check": lambda s: s.get("total_won_berries", 0) >= 10000000
    },
    "minefield_emperor": {
        "title": "Minefield Demigod",
        "desc": "Successfully win and cash out 25 games of Mines.",
        "icon": "💣",
        "check": lambda s: s.get("mines_won", 0) >= 25
    },
    "lexicon_grandmaster": {
        "title": "Grand Lexicographer",
        "desc": "Successfully conquer 20 Wordle Gamble stages.",
        "icon": "📖",
        "check": lambda s: s.get("wordle_stages_cleared", 0) >= 20
    },
    "master_thief": {
        "title": "Phantom King of Shadows",
        "desc": "Successfully execute 30 berry thefts against other players.",
        "icon": "🧤",
        "check": lambda s: s.get("steals_success", 0) >= 30
    },
    "divine_savior": {
        "title": "Saint of the Broken",
        "desc": "Donate a cumulative total of 50,000 🫐 to aid fellow players.",
        "icon": "👼",
        "check": lambda s: s.get("total_donated", 0) >= 50000
    },
    "task_titan": {
        "title": "Unstoppable Workhorse",
        "desc": "Complete 50 daily quest tasks.",
        "icon": "📜",
        "check": lambda s: s.get("tasks_completed_count", 0) >= 50
    },
    "arena_champion_25": {
        "title": "Gladiator of the Colosseum",
        "desc": "Win 25 PvP duel fights in the arena.",
        "icon": "⚔️",
        "check": lambda s: s.get("fights_won", 0) >= 25
    },
    "joint_vault_tycoon": {
        "title": "Dynasty Vault",
        "desc": "Deposit at least 500,000 🫐 into your matrimonial Joint Vault.",
        "icon": "🏰",
        "check": lambda s: s.get("joint_deposited", 0) >= 500000
    },
    "hopeless_romantic": {
        "title": "Eternal Sweetheart",
        "desc": "Take your beloved spouse on 30 romantic dates.",
        "icon": "💖",
        "check": lambda s: s.get("date_count", 0) >= 30
    },
    "karmic_ascendant": {
        "title": "Enlightened Bodhisattva",
        "desc": "Break 10 Sin locks by redeeming your soul through good deeds.",
        "icon": "🧘",
        "check": lambda s: s.get("sin_locks_broken", 0) >= 10
    },
    "rpg_dungeon_conqueror": {
        "title": "Abyssal Dungeon Vanquisher",
        "desc": "Conquer 20 GoD-HeLL dungeon expeditions.",
        "icon": "🗝️",
        "check": lambda s: s.get("dungeon_runs_completed", 0) >= 20
    },
    "rpg_warlord": {
        "title": "Supreme Battle Overlord",
        "desc": "Reach Battle Level 25 in the RPG progression system.",
        "icon": "🛡️",
        "check": lambda s: s.get("battle_level", 0) >= 25
    },
    "dice_grandmaster": {
        "title": "Grandmaster of the Bones",
        "desc": "Win 50 games of Dice in Yuna's casino.",
        "icon": "🎲",
        "check": lambda s: s.get("dice_games_won", 0) >= 50
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

_PROCESS_LOCK_FP = None
_PROCESS_LOCK_DEPTH = 0
_PROCESS_LOCK_THREAD_LOCK = threading.Lock()

class _CrossProcessLock:
    """Inter-process and re-entrant lock using fcntl on Termux filesystem."""
    def __enter__(self):
        global _PROCESS_LOCK_FP, _PROCESS_LOCK_DEPTH
        if FCNTL_AVAILABLE and fcntl:
            with _PROCESS_LOCK_THREAD_LOCK:
                if _PROCESS_LOCK_DEPTH == 0:
                    try:
                        _PROCESS_LOCK_FP = open(LOCK_FILE_PATH, "a+")
                        fcntl.flock(_PROCESS_LOCK_FP.fileno(), fcntl.LOCK_EX)
                    except Exception as e:
                        if _PROCESS_LOCK_FP:
                            try:
                                _PROCESS_LOCK_FP.close()
                            except Exception:
                                pass
                        _PROCESS_LOCK_FP = None
                _PROCESS_LOCK_DEPTH += 1
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        global _PROCESS_LOCK_FP, _PROCESS_LOCK_DEPTH
        if FCNTL_AVAILABLE and fcntl:
            with _PROCESS_LOCK_THREAD_LOCK:
                if _PROCESS_LOCK_DEPTH > 0:
                    _PROCESS_LOCK_DEPTH -= 1
                    if _PROCESS_LOCK_DEPTH == 0 and _PROCESS_LOCK_FP is not None:
                        try:
                            fcntl.flock(_PROCESS_LOCK_FP.fileno(), fcntl.LOCK_UN)
                        except Exception:
                            pass
                        try:
                            _PROCESS_LOCK_FP.close()
                        except Exception:
                            pass
                        _PROCESS_LOCK_FP = None

def _load_data_sync() -> Tuple[Dict[str, Dict[str, Any]], Dict[str, dict], Dict[str, dict]]:
    """Loads raw json data from disk with multi-tier automatic fallback recovery from .bak and snapshots."""
    _ensure_dirs()
    candidates = []
    if GAMBLING_DATA_FILE.exists():
        candidates.append(GAMBLING_DATA_FILE)
    bak_file = DATA_DIR / "yuna_gambling.json.bak"
    if bak_file.exists():
        candidates.append(bak_file)
    if BACKUPS_DIR.exists():
        try:
            snap_files = sorted(BACKUPS_DIR.glob("yuna_gambling_*.json"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
            candidates.extend(snap_files[:5])
        except Exception:
            pass

    for filepath in candidates:
        for attempt in range(3):
            try:
                if not filepath.exists() or filepath.stat().st_size == 0:
                    break
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    users = data.get("users", {})
                    vaults = data.get("joint_vaults", {})
                    dares = data.get("active_dares", {})
                    if filepath == GAMBLING_DATA_FILE:
                        if len(users) > 0:
                            return users, vaults, dares
                        else:
                            print(f"[YUNA GAMBLING SAFETY WARNING] {filepath} has 0 users! Attempting fallback recovery...")
                            break
                    if len(users) > 0:
                        print(f"[YUNA GAMBLING SAFETY] Recovered {len(users)} users, {len(vaults)} vaults from fallback: {filepath.name}")
                        return users, vaults, dares
            except Exception as e:
                if attempt < 2 and filepath == GAMBLING_DATA_FILE:
                    time.sleep(0.05)
                    continue
                print(f"[YUNA GAMBLING ERROR] Failed to load {filepath}: {e}")

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
        "spouse": PERMANENT_SPOUSE_ID if is_yuna_instance() else None,
        "spouse_name": PERMANENT_SPOUSE_NAME if is_yuna_instance() else None,
        "marriage_date": 1700000000.0 if is_yuna_instance() else None,
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

def _enforce_yuna_permanent_marriage():
    """
    Enforces that user 1155074026230788200 (deeploveluniel) is the permanent, hardcoded spouse of Yuna.
    This runs strictly when is_yuna_instance() is True, completely isolating other bots.
    """
    if not is_yuna_instance():
        return

    # 1. Enforce on user 1155074026230788200 (deeploveluniel)
    if PERMANENT_SPOUSE_ID in _USER_STATS:
        p_stats = _USER_STATS[PERMANENT_SPOUSE_ID]
        p_stats["spouse"] = YUNA_BOT_DEFAULT_ID
        p_stats["spouse_name"] = YUNA_BOT_NAME
        if not p_stats.get("marriage_date"):
            p_stats["marriage_date"] = 1700000000.0

    # 2. Enforce on Yuna's account
    if YUNA_USER_ID in _USER_STATS:
        y_stats = _USER_STATS[YUNA_USER_ID]
        y_stats["spouse"] = PERMANENT_SPOUSE_ID
        y_stats["spouse_name"] = PERMANENT_SPOUSE_NAME
        if not y_stats.get("marriage_date"):
            y_stats["marriage_date"] = 1700000000.0
        _USER_STATS[YUNA_BOT_DEFAULT_ID] = y_stats

    # 3. Ensure joint vault exists between deeploveluniel and Yuna
    vkey = _get_vault_key(PERMANENT_SPOUSE_ID, YUNA_BOT_DEFAULT_ID)
    if vkey not in _JOINT_VAULTS:
        _JOINT_VAULTS[vkey] = {
            "spouses": sorted([PERMANENT_SPOUSE_ID, YUNA_BOT_DEFAULT_ID]),
            "balance": 50_000_000,
            "history": [],
            "total_deposited": 50_000_000,
            "total_withdrawn": 0,
            "last_interest_date": ""
        }

def _ensure_fresh_data():
    """Checks if data on disk is newer than our in-memory cache and reloads if so, protecting against memory wipes."""
    global _USER_STATS, _JOINT_VAULTS, _ACTIVE_DARES, _LAST_FILE_MTIME, _DATA_LOADED, _USER_SNAPSHOTS, _VAULT_SNAPSHOTS, _DARE_SNAPSHOTS
    _ensure_dirs()
    if not GAMBLING_DATA_FILE.exists():
        if not _DATA_LOADED:
            fresh_users, fresh_vaults, fresh_dares = _load_data_sync()
            if fresh_users:
                _USER_STATS = fresh_users
                _JOINT_VAULTS = fresh_vaults
                _ACTIVE_DARES = fresh_dares
            else:
                _USER_STATS = {YUNA_USER_ID: _create_default_yuna()}
                _JOINT_VAULTS = {}
                _ACTIVE_DARES = {}
            _enforce_yuna_permanent_marriage()
            _USER_SNAPSHOTS = {uid: json.dumps(u, sort_keys=True) for uid, u in _USER_STATS.items()}
            _VAULT_SNAPSHOTS = {vk: json.dumps(v, sort_keys=True) for vk, v in _JOINT_VAULTS.items()}
            _DARE_SNAPSHOTS = {duid: json.dumps(d, sort_keys=True) for duid, d in _ACTIVE_DARES.items()}
            _LAST_FILE_MTIME = 0.0
            _DATA_LOADED = True
        return

    try:
        disk_mtime = os.path.getmtime(GAMBLING_DATA_FILE)
        if (not _DATA_LOADED) or (disk_mtime != _LAST_FILE_MTIME):
            with _CrossProcessLock():
                fresh_users, fresh_vaults, fresh_dares = _load_data_sync()
                # Anti-wipe check: Never replace healthy in-memory cache with empty/severely truncated dataset
                if len(fresh_users) >= len(_USER_STATS) or not _DATA_LOADED:
                    transient_users = {k: v for k, v in _USER_STATS.items() if k not in fresh_users}
                    _USER_STATS = fresh_users
                    _USER_STATS.update(transient_users)
                    _JOINT_VAULTS = fresh_vaults
                    _ACTIVE_DARES = {k: v for k, v in fresh_dares.items() if k not in _DELETED_DARES}
                else:
                    # Disk had fewer users; merge fresh updates while preserving all existing users & marriages
                    for uid, u in fresh_users.items():
                        _USER_STATS[uid] = u
                    for vk, v in fresh_vaults.items():
                        _JOINT_VAULTS[vk] = v
                    for duid, d in fresh_dares.items():
                        if duid not in _DELETED_DARES:
                            _ACTIVE_DARES[duid] = d

                # Auto-expire stale dares older than 2 hours so users don't get locked forever
                now_check = time.time()
                for _d_uid, _d_info in list(_ACTIVE_DARES.items()):
                    if isinstance(_d_info, dict) and _d_info.get("created_at"):
                        if now_check - _d_info["created_at"] > 7200:
                            _remove_active_dare(_d_uid)

                _LAST_FILE_MTIME = os.path.getmtime(GAMBLING_DATA_FILE)
                if YUNA_USER_ID not in _USER_STATS:
                    _USER_STATS[YUNA_USER_ID] = _create_default_yuna()

                # Anti-leak cleanup: Ensure expired pacts never leave juny_charm protection stuck on
                now_check = time.time()
                for _c_uid, _c_u in list(_USER_STATS.items()):
                    if _c_uid == YUNA_USER_ID or not isinstance(_c_u, dict):
                        continue
                    if _c_u.get("juny_charm"):
                        c_exp = _c_u.get("pact_expires_at", 0)
                        if (not _c_u.get("dark_bargain")) or (c_exp and c_exp <= now_check):
                            _c_u["juny_charm"] = False
                            _c_u["dark_bargain"] = False
                            _c_u.pop("pact_expires_at", None)
                            if _c_u.get("title") == "Devil's Slave":
                                _c_u["title"] = "Former Contract Slave"

                _enforce_yuna_permanent_marriage()
                _USER_SNAPSHOTS = {uid: json.dumps(u, sort_keys=True) for uid, u in _USER_STATS.items()}
                _VAULT_SNAPSHOTS = {vk: json.dumps(v, sort_keys=True) for vk, v in _JOINT_VAULTS.items()}
                _DARE_SNAPSHOTS = {duid: json.dumps(d, sort_keys=True) for duid, d in _ACTIVE_DARES.items()}
    except Exception as e:
        print(f"[YUNA GAMBLING ERROR] Failed to check/sync from disk: {e}")

class _AwaitableNone:
    def __await__(self):
        async def _dummy():
            return None
        return _dummy().__await__()

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

            # Safety guard: Never wipe disk users if in-memory user dict is unexpectedly empty
            if len(disk_users) > 5 and len(users_data) == 0:
                print(f"[YUNA GAMBLING SAFETY GUARD] In-memory user data is empty while disk has {len(disk_users)} users. Skipping disk wipe!")
                return

            # 2. Build merged dataset starting from disk state so unmentioned users are NEVER dropped
            merged_users = dict(disk_users)
            for uid, user_obj in users_data.items():
                merged_users[uid] = user_obj

            # Ensure any user already in in-memory _USER_STATS is preserved
            for uid, user_obj in _USER_STATS.items():
                merged_users[uid] = user_obj

            if is_yuna_instance():
                if PERMANENT_SPOUSE_ID in merged_users:
                    merged_users[PERMANENT_SPOUSE_ID]["spouse"] = YUNA_BOT_DEFAULT_ID
                    merged_users[PERMANENT_SPOUSE_ID]["spouse_name"] = YUNA_BOT_NAME
                    if not merged_users[PERMANENT_SPOUSE_ID].get("marriage_date"):
                        merged_users[PERMANENT_SPOUSE_ID]["marriage_date"] = 1700000000.0
                if YUNA_USER_ID in merged_users:
                    merged_users[YUNA_USER_ID]["spouse"] = PERMANENT_SPOUSE_ID
                    merged_users[YUNA_USER_ID]["spouse_name"] = PERMANENT_SPOUSE_NAME
                    if not merged_users[YUNA_USER_ID].get("marriage_date"):
                        merged_users[YUNA_USER_ID]["marriage_date"] = 1700000000.0
                    merged_users[YUNA_BOT_DEFAULT_ID] = merged_users[YUNA_USER_ID]

            # 3. Merge dirty joint vaults and ensure no vault is dropped
            merged_vaults = dict(disk_vaults)
            for vk, vault_obj in _JOINT_VAULTS.items():
                curr_dump = json.dumps(vault_obj, sort_keys=True)
                if vk not in _VAULT_SNAPSHOTS or curr_dump != _VAULT_SNAPSHOTS.get(vk):
                    merged_vaults[vk] = vault_obj
                elif vk not in merged_vaults:
                    merged_vaults[vk] = vault_obj

            if is_yuna_instance():
                vkey = _get_vault_key(PERMANENT_SPOUSE_ID, YUNA_BOT_DEFAULT_ID)
                if vkey not in merged_vaults:
                    merged_vaults[vkey] = {
                        "spouses": sorted([PERMANENT_SPOUSE_ID, YUNA_BOT_DEFAULT_ID]),
                        "balance": 50_000_000,
                        "history": [],
                        "total_deposited": 50_000_000,
                        "total_withdrawn": 0,
                        "last_interest_date": ""
                    }

            # 4. Merge active dares: start from disk state, reflect local deletions and additions
            merged_dares = dict(disk_dares)
            for d_uid in list(merged_dares.keys()):
                if d_uid in _DELETED_DARES or (d_uid in _DARE_SNAPSHOTS and d_uid not in _ACTIVE_DARES):
                    merged_dares.pop(d_uid, None)
            for d_uid, dare_obj in _ACTIVE_DARES.items():
                merged_dares[d_uid] = dare_obj
            _DELETED_DARES.clear()

            # 5. Anti-wipe validation: Merged users count must never drop drastically
            if len(disk_users) > 5 and len(merged_users) < len(disk_users) * 0.8:
                print(f"[YUNA GAMBLING CRITICAL SAFETY] Blocked save: merged users ({len(merged_users)}) is drastically less than disk users ({len(disk_users)})!")
                return

            # 6. Safe backup of current database file (only backup if current file has healthy users)
            if GAMBLING_DATA_FILE.exists() and len(merged_users) >= len(disk_users) and len(merged_users) > 0:
                try:
                    bak_file = DATA_DIR / "yuna_gambling.json.bak"
                    shutil.copyfile(GAMBLING_DATA_FILE, bak_file)
                    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
                    snap_file = BACKUPS_DIR / f"yuna_gambling_{time.strftime('%Y%m%d_%H')}.json"
                    if not snap_file.exists():
                        shutil.copyfile(GAMBLING_DATA_FILE, snap_file)
                except Exception:
                    pass

            # 7. Write atomically via temp file in same directory as target file
            target_dir = GAMBLING_DATA_FILE.parent
            target_dir.mkdir(parents=True, exist_ok=True)
            temp_file = target_dir / f"yuna_gambling.tmp.{os.getpid()}.{int(time.time()*1000)}"
            payload = {
                "version": 3,
                "updated_at": time.time(),
                "users": merged_users,
                "joint_vaults": merged_vaults,
                "active_dares": merged_dares
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

            # 8. Update local caches and snapshots
            _USER_STATS = merged_users
            _JOINT_VAULTS = merged_vaults
            _ACTIVE_DARES = merged_dares
            _LAST_FILE_MTIME = os.path.getmtime(GAMBLING_DATA_FILE)
            _DATA_LOADED = True
            _USER_SNAPSHOTS = {uid: json.dumps(u, sort_keys=True) for uid, u in _USER_STATS.items()}
            _VAULT_SNAPSHOTS = {vk: json.dumps(v, sort_keys=True) for vk, v in _JOINT_VAULTS.items()}
            _DARE_SNAPSHOTS = {duid: json.dumps(d, sort_keys=True) for duid, d in _ACTIVE_DARES.items()}

        except Exception as e:
            print(f"[YUNA GAMBLING ERROR] Failed to save {GAMBLING_DATA_FILE}: {e}")
    return _AwaitableNone()

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
    # Migrate legacy inv["watermelon"] to top-level user["watermelons"]
    _inv = user.get("inventory", {})
    if "watermelon" in _inv:
        _wm_count = _inv.pop("watermelon", 0)
        if _wm_count > 0:
            user["watermelons"] = user.get("watermelons", 0) + _wm_count
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
    user.setdefault("pact_expires_at", 0.0)
    user.setdefault("watermelons", 0)
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


def is_in_pact(user_id: str) -> bool:
    """Checks if a user is currently bound by an active 3-hour Devil's Contract with Juny."""
    if not user_id:
        return False
    _ensure_fresh_data()
    uid = str(user_id)
    if YUNA_PACT_AVAILABLE and yuna_pact:
        return yuna_pact.is_in_pact(uid, _USER_STATS.get(uid))
    stats = _USER_STATS.get(uid, {})
    now = time.time()
    exp = stats.get("pact_expires_at", 0)
    in_p = bool(stats.get("dark_bargain") and exp > now)
    if not in_p and stats.get("juny_charm"):
        stats["juny_charm"] = False
        stats["dark_bargain"] = False
        stats.pop("pact_expires_at", None)
        if stats.get("title") == "Devil's Slave":
            stats["title"] = "Former Contract Slave"
    return in_p


def has_juny_charm(user_id_or_stats: Any) -> bool:
    """
    Checks if a user currently has an active, unexpired Juny Protection Charm.
    Protection Charm is bound to the 3-hour Devil's Contract; if expired or not in pact, returns False
    and safely deactivates the charm so protection never stays stuck on after pact end.
    """
    if not user_id_or_stats:
        return False
    uid = None
    if isinstance(user_id_or_stats, dict):
        stats = user_id_or_stats
        # Attempt to find user ID if present
        for k, v in _USER_STATS.items():
            if v is stats:
                uid = k
                break
    else:
        uid = str(user_id_or_stats)
        _ensure_fresh_data()
        stats = _USER_STATS.get(uid, {})

    if not stats or not stats.get("juny_charm"):
        return False

    now = time.time()
    exp = stats.get("pact_expires_at", 0)

    # Check pact validity
    if uid:
        if not is_in_pact(uid):
            stats["juny_charm"] = False
            return False
    else:
        if not stats.get("dark_bargain") or (exp and exp <= now):
            stats["juny_charm"] = False
            return False

    return True


# ─── CURRENCY SHORTCUT & PARSING SYSTEM ───────────────────────────────────────

CURRENCY_WORD_MULTIPLIERS = {
    "k": 1_000, "thousand": 1_000, "thousands": 1_000, "grand": 1_000,
    "m": 1_000_000, "mil": 1_000_000, "mill": 1_000_000, "million": 1_000_000, "millions": 1_000_000,
    "b": 1_000_000_000, "bil": 1_000_000_000, "bill": 1_000_000_000, "billion": 1_000_000_000, "billions": 1_000_000_000,
    "t": 1_000_000_000_000, "tril": 1_000_000_000_000, "trill": 1_000_000_000_000, "trillion": 1_000_000_000_000, "trillions": 1_000_000_000_000,
    "q": 1_000_000_000_000_000, "quad": 1_000_000_000_000_000, "quadrillion": 1_000_000_000_000_000,
    "qn": 10**18, "quint": 10**18, "quintillion": 10**18, "quintillions": 10**18,
    "sx": 10**21, "sext": 10**21, "sextillion": 10**21, "sextillions": 10**21,
    "sp": 10**24, "sept": 10**24, "septillion": 10**24, "septillions": 10**24,
    "oc": 10**27, "oct": 10**27, "octillion": 10**27, "octillions": 10**27,
    "no": 10**30, "non": 10**30, "nonillion": 10**30, "nonillions": 10**30,
    "dc": 10**33, "dec": 10**33, "decillion": 10**33, "decillions": 10**33,
}

def parse_currency_amount(val: Any, user_balance: Optional[int] = None) -> Optional[int]:
    """
    Parses numeric and shortcut currency amounts.
    Supports:
      - Raw numbers: "500", "1000", "1,000"
      - Multiplier suffixes: "1k", "1.5k", "1m", "1b", "1t", "1q", "1qn", "1sx", "1sp", "1oc", "1no", "1dc"
      - Word multipliers: "1 mil", "2 million", "1 thousand", "5 billion", "1 grand", "1 quintillion"
      - Relative shortcuts (with user_balance):
          * "all", "max", "full": 100% of user_balance
          * "half", "halfway": 50% of user_balance (min 1 if user_balance >= 1)
          * "quarter", "qtr": 25% of user_balance (min 1 if user_balance >= 1)
          * "50%", "25%", "10%": percentage of user_balance
    """
    if val is None:
        return None
    s = str(val).strip().lower().replace(",", "")
    if not s:
        return None

    if user_balance is not None:
        b = max(0, int(user_balance))
        if s in ("all", "max", "full"):
            return b
        if s in ("half", "halfway"):
            return max(1, b // 2) if b >= 1 else 0
        if s in ("quarter", "qtr"):
            return max(1, b // 4) if b >= 1 else 0
        m_pct = re.match(r"^(\d+(?:\.\d+)?)\s*%$", s)
        if m_pct:
            try:
                pct = float(m_pct.group(1))
                calc = int(b * (pct / 100.0))
                return max(1, calc) if (b >= 1 and pct > 0) else max(0, calc)
            except Exception:
                return None

    m_suf = re.match(r"^(\d+(?:\.\d+)?)\s*([a-z]+)$", s)
    if m_suf:
        num_str, suf = m_suf.group(1), m_suf.group(2)
        if suf in CURRENCY_WORD_MULTIPLIERS:
            try:
                mult = CURRENCY_WORD_MULTIPLIERS[suf]
                if "." in num_str:
                    from decimal import Decimal
                    return int(Decimal(num_str) * Decimal(mult))
                return int(num_str) * mult
            except Exception:
                return None

    m_plain = re.match(r"^(\d+(?:\.\d+)?)$", s)
    if m_plain:
        try:
            num_str = m_plain.group(1)
            if "." in num_str:
                return int(float(num_str))
            return int(num_str)
        except Exception:
            return None

    return None

def normalize_currency_args(args: list) -> list:
    """
    Normalizes spaced suffix tokens in command args like:
    ['1', 'k'] -> ['1k']
    ['2.5', 'million'] -> ['2.5million']
    """
    if not args:
        return []
    res = []
    i = 0
    while i < len(args):
        tok = str(args[i]).strip()
        if i + 1 < len(args):
            next_tok = str(args[i + 1]).strip().lower()
            clean_tok = tok.replace(",", "")
            if re.match(r"^\d+(?:\.\d+)?$", clean_tok) and next_tok in CURRENCY_WORD_MULTIPLIERS:
                res.append(f"{tok}{next_tok}")
                i += 2
                continue
        res.append(tok)
        i += 1
    return res

def is_explicit_currency_token(tok: str) -> bool:
    """Checks if a string token is unequivocally an explicit currency/amount shortcut."""
    c = str(tok).strip().lower().replace(",", "")
    if c in ("all", "max", "full", "half", "quarter", "qtr"):
        return True
    if re.match(r"^\d+(?:\.\d+)?\s*%$", c):
        return True
    m_suf = re.match(r"^(\d+(?:\.\d+)?)\s*([a-z]+)$", c)
    if m_suf and m_suf.group(2) in CURRENCY_WORD_MULTIPLIERS:
        return True
    return False


async def _get_user_stats(user_id: str) -> Dict[str, Any]:
    global _USER_STATS
    async with _LOCK:
        _ensure_fresh_data()
        uid_str = str(user_id)
        if uid_str in (YUNA_USER_ID, "1533213082158108702"):
            if YUNA_USER_ID not in _USER_STATS:
                _USER_STATS[YUNA_USER_ID] = _create_default_yuna()
            user = _USER_STATS[YUNA_USER_ID]
            _USER_STATS["1533213082158108702"] = user
            _ensure_user_defaults(user)
            if is_yuna_instance():
                user["spouse"] = PERMANENT_SPOUSE_ID
                user["spouse_name"] = PERMANENT_SPOUSE_NAME
                if not user.get("marriage_date"):
                    user["marriage_date"] = 1700000000.0
            return user
        if uid_str not in _USER_STATS:
            _USER_STATS[uid_str] = _create_default_user()
            _save_data_sync(_USER_STATS)
        user = _USER_STATS[uid_str]
        _ensure_user_defaults(user)
        if is_yuna_instance() and uid_str == PERMANENT_SPOUSE_ID:
            user["spouse"] = YUNA_BOT_DEFAULT_ID
            user["spouse_name"] = YUNA_BOT_NAME
            if not user.get("marriage_date"):
                user["marriage_date"] = 1700000000.0
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
            # Gaining Sin directly degrades & reduces Virtue (1:1 corruption)
            if sin_delta > 0:
                virtue_delta -= sin_delta
                user["good_actions_needed"] = 5 # Locking virtue until 5 good actions are completed
                user["bad_actions_needed"] = 0

            # If user earns Virtue, cannot earn Sin until 5 bad actions are completed
            if virtue_delta > 0:
                needed = user.get("good_actions_needed", 0)
                if needed > 0:
                    user["good_actions_needed"] = max(0, needed - 1)
                    if user["good_actions_needed"] == 0:
                        user["sin_locks_broken"] = user.get("sin_locks_broken", 0) + 1
                    virtue_delta = 0 # Blocked until all 5 good actions are done
                else:
                    user["bad_actions_needed"] = 0

            # Caps: Dynamic Virtue and Sin limits
            user_max_v, user_max_s = get_user_morality_caps(user)
            user["virtue"] = min(user_max_v, max(0, user.get("virtue", 0) + virtue_delta))
            user["sin"] = min(user_max_s, max(0, user.get("sin", 0) + sin_delta))

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

def get_user_morality_caps(user: dict) -> Tuple[int, int]:
    """
    Returns (max_virtue, max_sin).
    Base limits: Virtue 33, Sin 30.
    - Virtue limit increases by 77 -> 110.
    - Devil Horn increases Sin limit by 60 -> 90.
    """
    base_virtue = 33 + 77  # 110 max virtue
    inv = user.get("inventory", {}) if isinstance(user, dict) else {}
    horn_bonus = 60 if inv.get("devil_horn", 0) > 0 else 0
    base_sin = 30 + horn_bonus
    return base_virtue, base_sin

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
    """Returns warning banner if user holds high Sin (unless protected by Juny charm)."""
    if has_juny_charm(stats):
        return "\n🛡️ **JUNY'S PROTECTION CHARM ACTIVE:** Sin danger neutralized! You walk unharmed."
    eff_v, eff_s = get_effective_morality(stats)
    max_v, max_s = get_user_morality_caps(stats)
    if 20 <= eff_s < 26:
        return (
            f"\n⚠️ **WARNING FROM THE ABYSS:** You hold **{eff_s}/{max_s} Sin**!\n"
            f"😈 **Juny, Heaven's Worst Angel**, is circling above...\n"
            f"She will come to claim your soul at 26+ Sin! Repent before it is too late!"
        )
    elif eff_s >= 26:
        return (
            f"\n🚨 **THE ABYSS CALLS:** You hold **{eff_s}/{max_s} Sin**!\n"
            f"😈 **Juny, Heaven's Worst Angel**, is descending to claim your soul!"
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
    k1 = "1533213082158108702" if str(uid1).lower() in ("yuna", "1533213082158108702") else str(uid1)
    k2 = "1533213082158108702" if str(uid2).lower() in ("yuna", "1533213082158108702") else str(uid2)
    return ":".join(sorted([k1, k2]))

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


# ─── INFLATION & DYNAMIC ECONOMY ENGINE ───────────────────────────────────────

CONFIG_FILE = SCRIPT_DIR / "config.json"

DEFAULT_INFLATION_CONFIG = {
    "enabled": True,
    "base_money_supply": 10_000_000,
    "scaling_mode": "progressive",     # "progressive", "linear", or "logarithmic"
    "progressive_power": 0.25,
    "min_multiplier": 1.0,
    "max_multiplier": None,
    "reward_scaling_enabled": True,
    "reward_power": 0.20
}

_INFLATION_CACHE = {
    "timestamp": 0.0,
    "multiplier": 1.0,
    "reward_multiplier": 1.0,
    "total_user_berries": 0,
    "total_vault_berries": 0,
    "total_circulating": 0,
    "ratio": 1.0,
    "config": None
}

def get_inflation_config() -> dict:
    """Loads and returns inflation configuration from config.json with safe defaults."""
    cfg = dict(DEFAULT_INFLATION_CONFIG)
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                raw_cfg = json.load(f)
                if isinstance(raw_cfg, dict) and "inflation" in raw_cfg:
                    cfg.update(raw_cfg["inflation"])
    except Exception:
        pass
    return cfg

def get_economy_total_currency() -> Tuple[int, int, int]:
    """
    Computes total circulating currency across:
    1) All mortal user balances in _USER_STATS (excluding YUNA_USER_ID)
    2) All joint matrimonial vaults in _JOINT_VAULTS
    Returns: (total_user_berries, total_vault_berries, total_circulating)
    """
    global _USER_STATS, _JOINT_VAULTS
    _ensure_fresh_data()
    u_sum = sum(max(0, int(u.get("berries", 0))) for uid, u in _USER_STATS.items() if uid != YUNA_USER_ID)
    v_sum = sum(max(0, int(v.get("balance", 0))) for v in _JOINT_VAULTS.values())
    return u_sum, v_sum, (u_sum + v_sum)

def get_inflation_multiplier() -> float:
    """
    Calculates dynamic inflation multiplier based on all user balances and shared vault balances.
    Cached for 3 seconds for optimal performance across rapid commands.
    """
    global _INFLATION_CACHE
    now = time.time()
    if now - _INFLATION_CACHE["timestamp"] < 3.0:
        return _INFLATION_CACHE["multiplier"]

    cfg = get_inflation_config()
    if not cfg.get("enabled", True):
        _INFLATION_CACHE["timestamp"] = now
        _INFLATION_CACHE["multiplier"] = 1.0
        _INFLATION_CACHE["reward_multiplier"] = 1.0
        return 1.0

    u_sum, v_sum, total_circulating = get_economy_total_currency()
    base_supply = max(1, int(cfg.get("base_money_supply", 10_000_000)))

    if total_circulating <= base_supply:
        mult = 1.0
        r_mult = 1.0
        ratio = float(total_circulating) / float(base_supply)
    else:
        ratio = float(total_circulating) / float(base_supply)
        mode = str(cfg.get("scaling_mode", "progressive")).lower().strip()
        if mode == "linear":
            mult = ratio
        elif mode == "logarithmic":
            mult = 1.0 + (5.0 * math.log10(ratio))
        else:
            power = float(cfg.get("progressive_power", 0.25))
            mult = ratio ** power

        min_m = float(cfg.get("min_multiplier", 1.0))
        mult = max(min_m, mult)
        max_m = cfg.get("max_multiplier")
        if max_m is not None:
            mult = min(float(max_m), mult)

        r_pow = float(cfg.get("reward_power", 0.20))
        r_mult = max(1.0, ratio ** r_pow)

    _INFLATION_CACHE = {
        "timestamp": now,
        "multiplier": mult,
        "reward_multiplier": r_mult,
        "total_user_berries": u_sum,
        "total_vault_berries": v_sum,
        "total_circulating": total_circulating,
        "ratio": ratio,
        "config": cfg
    }
    return mult

def get_inflated_price(base_price: int) -> int:
    """Returns the market-adjusted inflated price for an item, fee, or service."""
    if base_price <= 0:
        return base_price
    mult = get_inflation_multiplier()
    return max(base_price, int(base_price * mult))

def get_inflated_reward(base_reward: int) -> int:
    """Returns the market-adjusted reward or wage for dailies, work, crime, and tasks."""
    if base_reward <= 0:
        return base_reward
    cfg = get_inflation_config()
    if not cfg.get("reward_scaling_enabled", True):
        return base_reward
    get_inflation_multiplier()
    r_mult = _INFLATION_CACHE.get("reward_multiplier", 1.0)
    return max(base_reward, int(base_reward * r_mult))

def format_compact_berries(val: int) -> str:
    """Formats large berry quantities into human-readable compact notation."""
    if abs(val) < 1_000:
        return f"{val:,}"
    suffixes = [
        (10**33, "Dc"), (10**30, "No"), (10**27, "Oc"), (10**24, "Sp"),
        (10**21, "Sx"), (10**18, "Qn"), (10**15, "Q"), (10**12, "T"),
        (10**9, "B"), (10**6, "M"), (10**3, "K")
    ]
    for threshold, suffix in suffixes:
        if abs(val) >= threshold:
            f_val = val / threshold
            if f_val >= 100:
                return f"{f_val:.0f}{suffix}"
            elif f_val >= 10:
                return f"{f_val:.1f}{suffix}"
            else:
                return f"{f_val:.2f}{suffix}"
    return f"{val:,}"

def build_inflation_embed() -> discord.Embed:
    """Constructs a comprehensive real-time inflation and macro-economy overview embed."""
    u_sum, v_sum, total = get_economy_total_currency()
    mult = get_inflation_multiplier()
    cfg = get_inflation_config()
    base = max(1, int(cfg.get("base_money_supply", 10_000_000)))
    mode = cfg.get("scaling_mode", "progressive")
    power = cfg.get("progressive_power", 0.25)
    r_mult = _INFLATION_CACHE.get("reward_multiplier", 1.0)

    u_pct = (u_sum / total * 100) if total > 0 else 0.0
    v_pct = (v_sum / total * 100) if total > 0 else 0.0
    pct_inflation = max(0.0, (mult - 1.0) * 100.0)

    if mult <= 1.05:
        status_badge = "🟢 **Stable Market** (Zero/Low Inflation)"
        color = 0x2ECC71
    elif mult <= 5.0:
        status_badge = "🟡 **Mild Inflation**"
        color = 0xF1C40F
    elif mult <= 100.0:
        status_badge = "🟠 **High Inflation**"
        color = 0xE67E22
    else:
        status_badge = "🔴 **Hyperinflation Surge**"
        color = 0xE74C3C

    embed = discord.Embed(
        title="📈 Imperial Central Bank • Real-Time Inflation Index",
        description=(
            f"{status_badge}\n"
            f"Market prices and economy services dynamically adjust based on the combined currency of all user balances and shared matrimonial vaults!\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=color
    )

    embed.add_field(
        name="🪙 Money Supply Breakdown",
        value=(
            f"• 👤 **Total User Wallets:** `{u_sum:,} 🫐` (`{format_compact_berries(u_sum)}`) • **{u_pct:.1f}%**\n"
            f"• 🏦 **Total Shared Vaults:** `{v_sum:,} 🫐` (`{format_compact_berries(v_sum)}`) • **{v_pct:.1f}%**\n"
            f"• 🌐 **Total Circulating Currency:** `{total:,} 🫐` (`{format_compact_berries(total)}`)\n"
            f"• 🏛️ **Baseline Money Supply:** `{base:,} 🫐` (`{format_compact_berries(base)}`)"
        ),
        inline=False
    )

    embed.add_field(
        name="📊 Inflation Index & Engine",
        value=(
            f"• 🏷️ **Price Multiplier:** **`{mult:,.2f}x`** (`+{pct_inflation:,.1f}%`)\n"
            f"• 💼 **Income / Reward Index:** **`{r_mult:,.2f}x`**\n"
            f"• ⚙️ **Scaling Mode:** `{mode.capitalize()}` *(Power: `{power}`)*\n"
            f"• 🛡️ **Engine Status:** `{'Active & Regulated' if cfg.get('enabled', True) else 'Disabled'}`"
        ),
        inline=False
    )

    sample_items = [
        ("Heavenly Shield", 15_000),
        ("Golden Wedding Ring", 50_000),
        ("Katana", 10_000_000),
        ("Divorce Legal Fee", 10_000),
        ("Daily Base Grant", 150)
    ]
    lines = []
    for name, base_p in sample_items:
        if name.startswith("Daily"):
            inf_p = get_inflated_reward(base_p)
            lines.append(f"• **{name}:** `{base_p:,}` ➔ **`{inf_p:,} 🫐`** (`{format_compact_berries(inf_p)}`) *(Income)*")
        else:
            inf_p = get_inflated_price(base_p)
            lines.append(f"• **{name}:** `{base_p:,}` ➔ **`{inf_p:,} 🫐`** (`{format_compact_berries(inf_p)}`)")

    embed.add_field(
        name="🏷️ Dynamic Price & Reward Adjustments",
        value="\n".join(lines),
        inline=False
    )

    embed.set_footer(text="Yuna's Economy Codex • Prices adjust automatically with money supply changes")
    return embed

async def handle_inflation(message, client, args: list):
    """Handles y!inflation (or y!economy, y!market, y!inf)."""
    embed = build_inflation_embed()
    await _safe_send_reply(message, embed=embed)


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
            reward = get_inflated_reward(t["reward"])
            user["berries"] = user.get("berries", 0) + reward
            notification = f"✨ **Daily Task Completed:** [{t['name']}]! (+{reward:,} 🫐)"

            all_done = all(tk.get("claimed", False) for tk in tasks.values())
            if all_done and not dt.get("all_bonus_claimed", False):
                dt["all_bonus_claimed"] = True
                user["tasks_completed_count"] = user.get("tasks_completed_count", 0) + 1
                base_grand = 240 if user.get("spouse") else 200
                grand_bonus = get_inflated_reward(base_grand)
                user["berries"] = user.get("berries", 0) + grand_bonus
                user["virtue"] = user.get("virtue", 0) + 2
                notification += f"\n🎉 **ALL DAILY TASKS COMPLETED!** Grand Bounty: **+{grand_bonus:,} 🫐** & **+2 💖** Virtue!"

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
    author_id = str(message.author.id) if (message and hasattr(message, "author") and hasattr(message.author, "id")) else None
    in_contract = False

    # ── JUNY TAKEOVER DURING ACTIVE PACT ──
    # During pact instead of yuna, juny answers all commands and the talking style is adapted to juny
    if author_id and is_in_pact(author_id) and YUNA_PACT_AVAILABLE and yuna_pact:
        try:
            in_contract = True
            u_stats = _USER_STATS.get(author_id, {})
            if content is not None:
                content = yuna_pact.adapt_content_to_juny(content, u_stats)
            if embed is not None:
                embed = yuna_pact.adapt_embed_to_juny(embed, u_stats)
        except Exception as _p_err:
            print(f"[PACT ADAPT ERROR in _safe_send_reply]: {_p_err}")
        pass

    if embed is not None:
        try:
            if hasattr(embed, "_fields") and embed._fields:
                sanitized_fields = []
                for fld in embed._fields[:25]:
                    name = str(fld.get("name", ""))[:256] or "—"
                    val = str(fld.get("value", ""))
                    if len(val) > 1024:
                        val = val[:1021] + "..."
                    sanitized_fields.append({
                        "name": name,
                        "value": val,
                        "inline": bool(fld.get("inline", False))
                    })
                embed._fields = sanitized_fields
        except Exception:
            pass

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

    # RECORD INTO CONVERSATION CONTEXT SO YUNA/JUNY AI CAN READ COMMANDS & OUTCOMES
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


class BlackjackView(ResilientView):
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
            await _safe_send_ephemeral(interaction, "This isn't your blackjack hand, mortal!")
            return
        await process_blackjack_turn(self.game_state, action="hit", interaction=interaction, view=self)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary, emoji="🛑")
    async def stand_button(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) != self.author_id:
            await _safe_send_ephemeral(interaction, "This isn't your blackjack hand, mortal!")
            return
        await process_blackjack_turn(self.game_state, action="stand", interaction=interaction, view=self)


class CrashView(ResilientView):
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
            await _safe_send_ephemeral(interaction, "Hands off! This isn't your crash game!")
            return
        await process_crash_cashout(self.game_state, interaction=interaction, view=self)


class ChallengeView(ResilientView):
    def __init__(self, target_id: str, author_id: str, challenge_type: str, data: dict):
        super().__init__(timeout=300.0)
        self.target_id = str(target_id)
        self.author_id = str(author_id)
        self.challenge_type = str(challenge_type)
        self.data = data
        self.clear_items()

        self.accept_btn = Button(
            label="Accept",
            style=discord.ButtonStyle.success,
            emoji="✅",
            custom_id=f"challenge_accept_{self.target_id}_{self.author_id}"
        )
        self.accept_btn.callback = self.accept_btn_cb
        self.add_item(self.accept_btn)

        self.decline_btn = Button(
            label="Decline",
            style=discord.ButtonStyle.danger,
            emoji="❌",
            custom_id=f"challenge_decline_{self.target_id}_{self.author_id}"
        )
        self.decline_btn.callback = self.decline_btn_cb
        self.add_item(self.decline_btn)

    async def accept_btn_cb(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.target_id:
            await _safe_send_ephemeral(interaction, "Only the challenged user can accept!")
            return
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
        except Exception:
            pass
        await execute_challenge_resolution(self.data, accepted=True, interaction=interaction, view=self)

    async def decline_btn_cb(self, interaction: discord.Interaction):
        if str(interaction.user.id) not in (self.target_id, self.author_id):
            await _safe_send_ephemeral(interaction, "You cannot decline this challenge!")
            return
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
        except Exception:
            pass
        await execute_challenge_resolution(self.data, accepted=False, interaction=interaction, view=self)


class SoloDareView(ResilientView):
    def __init__(self, target_id: str):
        super().__init__(timeout=600.0)
        self.target_id = target_id

    @discord.ui.button(label="Reroll Prompt (1 Free)", style=discord.ButtonStyle.secondary, emoji="🎲")
    async def reroll_btn(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) != self.target_id:
            await _safe_send_ephemeral(interaction, "This isn't your dare to reroll, mortal!")
            return
        await process_dare_reroll(self.target_id, interaction=interaction, view=self)

    @discord.ui.button(label="Forfeit", style=discord.ButtonStyle.danger, emoji="🏳️")
    async def forfeit_btn(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) != self.target_id:
            await _safe_send_ephemeral(interaction, "This isn't your dare to forfeit!")
            return
        await process_dare_forfeit(self.target_id, interaction=interaction, view=self)


class PvPDareReviewView(ResilientView):
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
            await _safe_send_ephemeral(interaction, "Only the challenger can approve this proof!")
            return
        await process_pvp_dare_review(self.target_id, action="approve", interaction=interaction, view=self, proof=self.proof)

    @discord.ui.button(label="Ask Yuna AI", style=discord.ButtonStyle.primary, emoji="🤖")
    async def ask_ai_btn(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) not in (self.challenger_id, self.target_id):
            await _safe_send_ephemeral(interaction, "Only the challenger or target can ask Yuna AI!")
            return
        await _safe_defer(interaction)
        await process_pvp_dare_review(self.target_id, action="ask_ai", interaction=interaction, view=self, proof=self.proof)

    @discord.ui.button(label="Reject Proof", style=discord.ButtonStyle.danger, emoji="❌")
    async def reject_btn(self, interaction: discord.Interaction, button: Button):
        is_admin = getattr(interaction.user.guild_permissions, "administrator", False) if interaction.guild else False
        if str(interaction.user.id) != self.challenger_id and not is_admin:
            await _safe_send_ephemeral(interaction, "Only the challenger can reject this proof!")
            return
        await process_pvp_dare_review(self.target_id, action="reject", interaction=interaction, view=self, proof=self.proof)

    @discord.ui.button(label="Forfeit", style=discord.ButtonStyle.secondary, emoji="🏳️")
    async def forfeit_btn(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) != self.target_id:
            await _safe_send_ephemeral(interaction, "Only the challenged target can forfeit this dare!")
            return
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

class HigherLowerView(ResilientView):
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
            await _safe_send_ephemeral(interaction, "This isn't your guessing game, mortal!")
            return
        await process_hl_turn(self.game_state, guess="higher", interaction=interaction, view=self)

    @discord.ui.button(label="Lower", style=discord.ButtonStyle.danger, emoji="🔻")
    async def lower_button(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) != self.author_id:
            await _safe_send_ephemeral(interaction, "This isn't your guessing game, mortal!")
            return
        await process_hl_turn(self.game_state, guess="lower", interaction=interaction, view=self)

    @discord.ui.button(label="💰 Cash Out", style=discord.ButtonStyle.primary, disabled=True)
    async def cashout_button(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) != self.author_id:
            await _safe_send_ephemeral(interaction, "This isn't your guessing game, mortal!")
            return
        await process_hl_cashout(self.game_state, interaction=interaction, view=self)

    @discord.ui.button(label="Reset", style=discord.ButtonStyle.secondary, emoji="🔄")
    async def reset_button(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) != self.author_id:
            await _safe_send_ephemeral(interaction, "This isn't your guessing game, mortal!")
            return
        await process_hl_reset(self.game_state, interaction=interaction, view=self)


class CoinFlipView(ResilientView):
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
            await _safe_send_ephemeral(interaction, "Not your coin flip!")
            return
        await execute_solo_coinflip(interaction.message, self.author_id, self.amount, guess="heads", interaction=interaction, view=self)

    @discord.ui.button(label="Tails", style=discord.ButtonStyle.secondary, emoji="🪙")
    async def tails_button(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) != self.author_id:
            await _safe_send_ephemeral(interaction, "Not your coin flip!")
            return
        await execute_solo_coinflip(interaction.message, self.author_id, self.amount, guess="tails", interaction=interaction, view=self)


class MarryView(ResilientView):
    def __init__(self, target_id: str, author_id: str):
        super().__init__(timeout=300.0)
        self.target_id = target_id
        self.author_id = author_id

    @discord.ui.button(label="💍 I Do!", style=discord.ButtonStyle.success)
    async def accept_marriage(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) != self.target_id:
            await _safe_send_ephemeral(interaction, "Hey, they didn't propose to you!")
            return
        await resolve_marriage(self.author_id, self.target_id, accepted=True, interaction=interaction, view=self)

    @discord.ui.button(label="💔 Leave at Altar", style=discord.ButtonStyle.danger)
    async def reject_marriage(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) != self.target_id:
            await _safe_send_ephemeral(interaction, "Only the proposed player can answer!")
            return
        await resolve_marriage(self.author_id, self.target_id, accepted=False, interaction=interaction, view=self)


class RouletteView(ResilientView):
    def __init__(self, author_id: str, amount: int):
        super().__init__(timeout=300.0)
        self.author_id = author_id
        self.amount = amount

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

    async def _handle_bet(self, interaction: discord.Interaction, bet_type: str):
        if str(interaction.user.id) != self.author_id:
            await _safe_send_ephemeral(interaction, "Not your roulette wheel, mortal!")
            return
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


class PokerView(ResilientView):
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
            await _safe_send_ephemeral(interaction, "This isn't your poker game!")
            return
        refresh_view_timeout(self, 300.0)
        if self.game_state.get("finished"):
            await _safe_send_ephemeral(interaction, "This hand has already completed!")
            return
        if idx in self.game_state["held"]:
            self.game_state["held"].remove(idx)
        else:
            self.game_state["held"].add(idx)
        self.update_buttons()
        await _safe_update_game_message(interaction, self.game_state.get("message"), content=format_poker_message(self.game_state), view=self)

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
            await _safe_send_ephemeral(interaction, "This isn't your poker game!")
            return
        await execute_poker_draw(interaction.message, self.author_id, interaction=interaction, view=self)

    @discord.ui.button(label="🏳️ Fold", style=discord.ButtonStyle.danger, row=1)
    async def fold_button(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) != self.author_id:
            await _safe_send_ephemeral(interaction, "This isn't your poker game!")
            return
        await execute_poker_fold(interaction.message, self.author_id, interaction=interaction, view=self)


class DiceView(ResilientView):
    def __init__(self, author_id: str, amount: int):
        super().__init__(timeout=300.0)
        self.author_id = author_id
        self.amount = amount

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

    async def _handle_bet(self, interaction: discord.Interaction, bet_type: str):
        if str(interaction.user.id) != self.author_id:
            await _safe_send_ephemeral(interaction, "Not your dice table, mortal!")
            return
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


class SlotsView(ResilientView):
    def __init__(self, author_id: str, amount: int):
        super().__init__(timeout=300.0)
        self.author_id = author_id
        self.amount = max(1, amount)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

    async def _re_spin(self, interaction: discord.Interaction, bet_amount: int):
        if str(interaction.user.id) != self.author_id:
            await _safe_send_ephemeral(interaction, "Not your slot machine, mortal!")
            return
        await execute_slots_spin(interaction.message, self.author_id, max(1, bet_amount), interaction=interaction, view=self)

    @discord.ui.button(label="🎰 Spin Again", style=discord.ButtonStyle.success, row=0)
    async def spin_btn(self, interaction: discord.Interaction, button: Button):
        await self._re_spin(interaction, self.amount)

    @discord.ui.button(label="2️⃣ Double Bet", style=discord.ButtonStyle.primary, row=0)
    async def double_btn(self, interaction: discord.Interaction, button: Button):
        await self._re_spin(interaction, self.amount * 2)

    @discord.ui.button(label="💰 Max Bet", style=discord.ButtonStyle.secondary, row=0)
    async def max_btn(self, interaction: discord.Interaction, button: Button):
        s = await _get_user_stats(self.author_id)
        bal = s.get("berries", 0)
        max_bet = max(1, min(500_000, bal))
        await self._re_spin(interaction, max_bet)

    @discord.ui.button(label="❌ Leave", style=discord.ButtonStyle.danger, row=0)
    async def leave_btn(self, interaction: discord.Interaction, button: Button):
        if str(interaction.user.id) != self.author_id:
            return
        for child in self.children:
            child.disabled = True
        await _safe_update_game_message(interaction, view=self)


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
            await _safe_send_ephemeral(interaction, "Not your minefield, mortal!")
            return
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
            await _safe_send_ephemeral(interaction, "Not your minefield, mortal!")
            return
        await process_mines_cashout(view.game_state, interaction=interaction, view=view)


class MinesView(ResilientView):
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
        "FLUSH", "MANOR", "WHEEL", "SPARK", "FAITH", "CHARM", "BLUFF", "GHOST", "DREAM",
        "CHESS", "MAGIC", "QUEST", "SWORD", "FLAME", "PEARL", "QUEEN", "TITAN", "VAPOR",
        "TIGER", "ROBIN", "OCEAN", "STORM", "POWER", "BLADE", "HONOR", "FROST", "SHINE",
        "COMET", "SOLAR", "LUNAR", "EMBER", "VALOR", "RELIC", "SPELL", "RIVER", "HAZEL",
        "AMBER", "PIXEL", "NOBLE", "MANGO", "LIGHT", "GLORY", "BLOOM", "CANDY", "BRAVE"
    ],
    6: [
        "CASINO", "GOLDEN", "WEALTH", "SHRINE", "LEGEND", "SHIELD", "MYSTIC", "PURPLE",
        "MIRROR", "CLOVER", "DRAGON", "SILVER", "PIRATE", "PALACE", "WIZARD", "KNIGHT",
        "BLADES", "HUNTER", "FOREST", "TEMPLE", "HEAVEN", "FROZEN", "SPIRIT", "CHANCE",
        "SHADOW", "REWARD", "EMPIRE", "CASTLE", "AURORA", "METEOR", "PRINCE", "VALLEY",
        "BEACON", "SPHERE", "PORTAL", "SUMMIT", "CANDLE", "BREEZE", "FALCON", "STRIKE"
    ],
    "tricky_6": [
        "SPHINX", "CIPHER", "VORTEX", "ZODIAC", "QUARTZ", "GLYPHS", "MYTHIC", "FRENZY",
        "CRUXES", "GOBLIN", "VOODOO", "KISMET", "KARMIC", "ENIGMA", "PYRITE", "COSMIC",
        "OCCULT", "ZEPHYR", "HYBRIS", "SHADOW", "KEEPER", "GRAILS", "ARCANE", "WYVERN",
        "RITUAL", "BISHOP", "COVENS", "GHOULS", "WRAITH", "HORROR", "DEMONS", "RUNICS"
    ],
    7: [
        "DIAMOND", "CORRUPT", "INFERNO", "MIRACLE", "TITANIC", "PHANTOM", "BLOSSOM", "ETERNAL",
        "BLINDED", "DESTINY", "FORTUNE", "CRYSTAL", "KINGDOM", "DRAGONS", "SHADOWS", "PHOENIX",
        "BRAVERY", "MYSTERY", "TRIUMPH", "SPECTRE", "HARMONY", "VICTORY", "VALIANT", "ROYALTY",
        "MAJESTY", "EMPEROR", "WARRIOR", "BLAZING", "SUPREME", "ANGELIC", "JACKPOT", "ECLIPSE",
        "CHIMERA"
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

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        if isinstance(error, discord.NotFound) and getattr(error, 'code', None) == 10062:
            return
        if isinstance(error, discord.HTTPException) and getattr(error, 'code', None) == 40060:
            return
        import traceback
        traceback.print_exc()

    async def on_submit(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.game_state["author_id"]:
            await _safe_send_ephemeral(interaction, "Not your Wordle game!")
            return
        refresh_view_timeout(self.wordle_view, 600.0)
        guess_word = self.guess_input.value.strip().upper()
        await process_wordle_guess(self.game_state, guess_word, interaction=interaction, view=self.wordle_view)


class WordleView(ResilientView):
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
                    await _safe_send_ephemeral(interaction, "Not your Wordle table!")
                    return
                try:
                    modal = WordleGuessModal(self.game_state, self)
                    await interaction.response.send_modal(modal)
                except Exception:
                    pass
            btn_guess.callback = _on_guess
            self.add_item(btn_guess)

            btn_give_up = Button(label="🏳️ Give Up", style=discord.ButtonStyle.danger)
            async def _on_give_up(interaction: discord.Interaction):
                if str(interaction.user.id) != self.author_id:
                    await _safe_send_ephemeral(interaction, "Not your Wordle table!")
                    return
                await process_wordle_give_up(self.game_state, interaction=interaction, view=self)
            btn_give_up.callback = _on_give_up
            self.add_item(btn_give_up)

        elif status == "stage_cleared":
            btn_cashout = Button(label=f"💰 Cash Out ({pot:,} 🫐)", style=discord.ButtonStyle.success, emoji="💵")
            async def _on_cashout(interaction: discord.Interaction):
                if str(interaction.user.id) != self.author_id:
                    await _safe_send_ephemeral(interaction, "Not your Wordle table!")
                    return
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
                        await _safe_send_ephemeral(interaction, "Not your Wordle table!")
                        return
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

    base_allowance = get_inflated_reward(150)
    streak_bonus = min(get_inflated_reward(500), (streak - 1) * get_inflated_reward(25))
    spouse_id = stats.get("spouse")
    has_ring = stats.get("inventory", {}).get("ring", 0) > 0
    marriage_bonus = (get_inflated_reward(120 if has_ring else 50)) if spouse_id else 0
    total_gain = base_allowance + streak_bonus + marriage_bonus

    # Accrue joint vault interest and claim daily allowance atomically under lock
    accrued_interest = 0
    async with _LOCK:
        _ensure_fresh_data()
        if author_id not in _USER_STATS:
            _USER_STATS[author_id] = _create_default_user()
        user = _USER_STATS[author_id]
        _ensure_user_defaults(user)

        if spouse_id:
            vault = _get_joint_vault(author_id, spouse_id)
            interest, accrued = _accrue_vault_interest(vault)
            if accrued:
                accrued_interest = interest

        old_b = user.get("berries", 0)
        new_b = old_b + total_gain
        user["daily_streak"] = streak
        user["last_daily_date"] = today_str
        user["berries"] = new_b
        max_v, _ = get_user_morality_caps(user)
        user["virtue"] = min(max_v, user.get("virtue", 0) + 1)
        _log_player_stat_audit(author_id, "berries", f"{old_b:,}", f"{new_b:,}", f"delta=+{total_gain:,} outcome=daily_claim")
        _save_data_sync(_USER_STATS)

    unlocked = await check_and_award_achievements(author_id)
    banner = format_achievement_banner(unlocked)

    embed = discord.Embed(
        title="🎁 Yuna's Daily Berry Allowance!",
        description=f"You opened today's berry basket and received fresh divine treats!",
        color=0xF59E0B
    )
    embed.add_field(name="📦 Base Grant", value=f"`+{base_allowance:,} 🫐`", inline=True)
    embed.add_field(name=f"🔥 Daily Streak (Day {streak})", value=f"`+{streak_bonus:,} 🫐`", inline=True)
    if spouse_id:
        ring_txt = " *(💍 Ring Boost)*" if has_ring else " *(Spouse Bonus)*"
        embed.add_field(name="💍 Marriage Stipend", value=f"`+{marriage_bonus:,} 🫐`{ring_txt}", inline=True)
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
            _ensure_fresh_data()
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
                "• `y!shared deposit <amt|half|all|1k|1m|1b|1t>` — Deposit berries into joint vault\n"
                "• `y!shared withdraw <amt|half|all|1k|1m|1b|1t>` — Withdraw berries from joint vault\n"
                "• `y!doubleaid @user` — Team up with your spouse for a 2x Super Aid!"
            ),
            inline=False
        )
        embed.set_footer(text="Yuna's Matrimonial Banking • Funds are divided 50/50 upon divorce!")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub in ("deposit", "dep", "put", "add"):
        if len(args) < 2:
            await _safe_send_reply(message, "- *Yuna tilts her head* \"How many berries do you want to deposit? Usage: `y!shared deposit <amount|half|all|1k|1m|1b|1t>`\"")
            return

        norm_args = normalize_currency_args(args[1:])
        raw_amt_token = norm_args[0] if norm_args else args[1]

        async with _LOCK:
            _ensure_fresh_data()
            if author_id not in _USER_STATS:
                _USER_STATS[author_id] = _create_default_user()
            user = _USER_STATS[author_id]
            _ensure_user_defaults(user)

            author_berries = user.get("berries", 0)
            amount = parse_currency_amount(raw_amt_token, user_balance=author_berries)

            if amount is None:
                await _safe_send_reply(message, "- *Yuna scoffs* \"Please provide a valid berry amount to deposit (e.g. 500, half, all, 1k, 1m, 1b, 1t)!\"")
                return

            if amount <= 0:
                await _safe_send_reply(message, "- *Yuna smirks* \"You can't deposit zero or negative berries, nice try!\"")
                return

            if author_berries < amount:
                await _safe_send_reply(message, f"- *Yuna rolls her eyes* \"You only have **{author_berries:,}** 🫐! You can't deposit **{amount:,}** 🫐!\"")
                return

            vault = _get_joint_vault(author_id, spouse_id)
            old_berries = user.get("berries", 0)
            new_berries = old_berries - amount
            user["berries"] = new_berries
            vault["balance"] += amount
            vault["total_deposited"] = vault.get("total_deposited", 0) + amount
            user["joint_deposited"] = user.get("joint_deposited", 0) + amount
            _log_player_stat_audit(author_id, "berries", f"{old_berries:,}", f"{new_berries:,}", f"delta=-{amount:,} outcome=joint_vault_deposit")
            _save_data_sync(_USER_STATS)
            new_vault_bal = vault["balance"]
            rem_user_berries = user["berries"]

        unlocked = await check_and_award_achievements(author_id, specific_id="joint_investor")
        banner = format_achievement_banner(unlocked)

        await _safe_send_reply(
            message,
            f"💍 **JOINT VAULT DEPOSIT!** 💍\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<@{author_id}> deposited **{amount:,}** 🫐 into the shared vault with <@{spouse_id}>!\n"
            f"💰 New Joint Balance: **{new_vault_bal:,}** 🫐\n"
            f"🫐 Your Remaining Berries: **{rem_user_berries:,}** 🫐{banner}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        return

    elif sub in ("withdraw", "with", "take", "pull"):
        if len(args) < 2:
            await _safe_send_reply(message, "- *Yuna tilts her head* \"How many berries do you want to withdraw? Usage: `y!shared withdraw <amount|half|all|1k|1m|1b|1t>`\"")
            return

        norm_args = normalize_currency_args(args[1:])
        raw_amt_token = norm_args[0] if norm_args else args[1]

        async with _LOCK:
            _ensure_fresh_data()
            if author_id not in _USER_STATS:
                _USER_STATS[author_id] = _create_default_user()
            user = _USER_STATS[author_id]
            _ensure_user_defaults(user)

            vault = _get_joint_vault(author_id, spouse_id)
            vault_bal = vault.get("balance", 0)
            amount = parse_currency_amount(raw_amt_token, user_balance=vault_bal)

            if amount is None:
                await _safe_send_reply(message, "- *Yuna scoffs* \"Please provide a valid berry amount to withdraw (e.g. 500, half, all, 1k, 1m, 1b, 1t)!\"")
                return

            if amount <= 0:
                await _safe_send_reply(message, "- *Yuna smirks* \"You can't withdraw zero or negative berries!\"")
                return

            if vault_bal < amount:
                await _safe_send_reply(message, f"- *Yuna holds the vault shut* \"Your joint vault only has **{vault_bal:,}** 🫐! You can't withdraw **{amount:,}** 🫐!\"")
                return

            old_berries = user.get("berries", 0)
            new_berries = old_berries + amount
            vault["balance"] -= amount
            vault["total_withdrawn"] = vault.get("total_withdrawn", 0) + amount
            user["berries"] = new_berries
            _log_player_stat_audit(author_id, "berries", f"{old_berries:,}", f"{new_berries:,}", f"delta=+{amount:,} outcome=joint_vault_withdrawal")
            _save_data_sync(_USER_STATS)
            new_vault_bal = vault["balance"]
            new_user_berries = user["berries"]

        await _safe_send_reply(
            message,
            f"💸 **JOINT VAULT WITHDRAWAL!** 💸\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<@{author_id}> withdrew **{amount:,}** 🫐 from the shared vault with <@{spouse_id}>!\n"
            f"💰 Remaining Joint Balance: **{new_vault_bal:,}** 🫐\n"
            f"🫐 Your New Balance: **{new_user_berries:,}** 🫐\n"
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
                        if YUNA_ID_GUARD_AVAILABLE and yuna_id_guard and not yuna_id_guard.is_valid_guild_target(m, clean_name):
                            continue
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

    # ── Juny Balance Glitch Anomaly ("juny was here") ──
    # 4% chance (or 10% if high sin >= 20 or Juny stalk target)
    glitch_chance = 0.10 if (stats.get("sin", 0) >= 20 or stats.get("juny_stalked")) else 0.04
    if not show_equip and random.random() < glitch_chance and not has_juny_charm(stats):
        glitch_card = (
            "👻 ⚡ **[CRITICAL SYSTEM ANOMALY]** ⚡ 👻\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "```text\n"
            "ERROR: SOUL_CORRUPTED_0x666\n"
            "CURRENT BALANCE: 0 🫐\n"
            "ACCOUNT STATUS: REAPED\n"
            "```\n"
            "*The screen flickers violently with static, ominous whispers, and bloody feathers...*\n"
            "> *\"juny was here.\"*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await _safe_send_reply(message, glitch_card)
        return

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
    display_name = getattr(target_user, "display_name", target_user.name)

    try:
        import yuna_volcano
        if yuna_volcano.is_inside_volcano(stats):
            v_state = yuna_volcano.ensure_user_volcano_state(stats)
            heat_rem = yuna_volcano.get_heat_time_remaining(stats)
            volcano_card = (
                f"🌋 **Volcano Expedition Balance • {display_name}** 🌋\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"⛏️ **Mithril:** `{v_state.get('mithril', 0):,}`\n"
                f"🔥 **Core-Ash:** `{v_state.get('core_ash', 0):,}`\n"
                f"🧪 **Heat Resistance:** `{yuna_volcano.format_heat_timer(heat_rem)}`\n"
                f"📍 **Depth:** `Stage {v_state.get('stage', 1)}`\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"*(Normal Berry/Watermelon balance hidden while inside Volcano)*"
            )
            return volcano_card
    except Exception:
        pass

    berries = stats.get("berries", 0)
    virtue = stats.get("virtue", 0)
    sin = stats.get("sin", 0)
    spouse_id = stats.get("spouse")
    spouse_line = ""
    if spouse_id:
        vault = _get_joint_vault(str(target_user.id), spouse_id)
        v_bal = vault.get("balance", 0)
        t_uid_str = str(getattr(target_user, "id", target_user))
        if str(spouse_id) in (YUNA_BOT_DEFAULT_ID, "1533213082158108702", "yuna", "YUNA"):
            spouse_str = "Yuna ⭐ *(Celestial Angel Wife)*"
        elif t_uid_str in (YUNA_BOT_DEFAULT_ID, "1533213082158108702", "yuna", "YUNA") and str(spouse_id) == PERMANENT_SPOUSE_ID:
            spouse_str = f"deeploveluniel (<@{PERMANENT_SPOUSE_ID}>)"
        else:
            spouse_str = f"<@{spouse_id}>"
        spouse_line = f"💍 **Spouse:** {spouse_str}\n🏛️ **Joint Vault:** `{v_bal:,} 🫐` *(y!shared)*\n"

    streak = stats.get("daily_streak", 0)
    streak_line = f"🔥 **Daily Streak:** `{streak} days` *(y!daily)*\n" if streak > 0 else ""
    g_streak = stats.get("gamble_win_streak", 0)
    g_max_streak = stats.get("max_win_streak", 0)
    if g_streak > 0 or g_max_streak > 0:
        streak_line += f"🎲 **Win Streak:** `{g_streak}` wins *(Record: `{g_max_streak}`)* *(y!streak)*\n"

    max_v, max_s = get_user_morality_caps(stats)
    eff_v, eff_s = get_effective_morality(stats)
    v_title = get_virtue_title(virtue)
    s_title = get_sin_title(sin)

    if eff_v > 0:
        v_line = f"💖 **Virtue:** `{virtue}/{max_v}` *({v_title})* `[ACTIVE]` *(Kind Acts Boosted & Karmic Ward)*"
        s_line = f"❤️🔥 **Sin:** `{sin}/{max_s}` *({s_title})* `[DORMANT]`"
    elif eff_s > 0:
        v_line = f"💖 **Virtue:** `{virtue}/{max_v}` *({v_title})* `[DORMANT]`"
        s_line = f"❤️🔥 **Sin:** `{sin}/{max_s}` *({s_title})* `[ACTIVE]` *(+{eff_s * 0.1:.1f}x Gamble Payout)*"
    else:
        v_line = f"💖 **Virtue:** `{virtue}/{max_v}` *({v_title})*"
        s_line = f"❤️🔥 **Sin:** `{sin}/{max_s}` *({s_title})*"

    custom_title = stats.get("selected_title") or stats.get("title")
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

    # RPG Class & Battle Summary
    b_lvl = stats.get("battle_level", 1)
    d_stg = stats.get("godhell_highest_stage", 0)
    d_str = f"GoD-HeLL: Stage {d_stg}/10" if d_stg > 0 else "GoD-HeLL: Untested"
    class_line = ""
    if YUNA_RPG_AVAILABLE and yuna_rpg:
        r_info = yuna_rpg.get_player_rpg_stats(stats, display_name)
        if stats.get("rpg_class"):
            class_line = f"🔮 **Class:** {r_info['class_symbol']} **{r_info['class_name']}** `[{r_info['rank_title']}]` | {r_info['special_stat_name']}: `{r_info['special_stat_val']:,}` {r_info['special_stat_symbol']}\n"
        else:
            class_line = "🔮 **Class:** *Unsworn Oath* `(Choose via y!class)`\n"
    battle_line = f"{class_line}⚔️ **Battle:** `Lv. {b_lvl}` | `{d_str}` *(Click below for Equipment!)*\n"

    # Juny balance glitch: 2% chance to show eerie glitch text
    berry_display = f"`{berries:,}`"
    if random.random() < 0.02:
        berry_display = "`??? [juny was here...]`"

    watermelons = stats.get("watermelons", 0)
    wm_line = f"🍉 **Watermelons:** `{watermelons:,}` 🍉 *(y!wm)*\n"

    pact_line = ""
    target_id_str = str(getattr(target_user, "id", target_user))
    if YUNA_PACT_AVAILABLE and yuna_pact and yuna_pact.is_in_pact(target_id_str, stats):
        p_time = yuna_pact.format_pact_time_remaining(stats)
        pact_line = f"📜 **Devil's Contract:** *Bound to Juny ({p_time} left)* *(y!pact)*\n"

    return (
        f"🫐 **{display_name}'s Soul & Pouch** 🫐\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{crown_line}"
        f"{title_line}"
        f"{pact_line}"
        f"🫐 **Berries:** {berry_display}\n"
        f"{wm_line}"
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
        has_charm = has_juny_charm(stats)
        scenario_template = random.choice(SUCCESS_SCENARIOS)
        scenario = scenario_template.format(user=target_name)
        base_berries = random.randint(20, 50) if not has_charm else random.randint(200, 500)

        # Virtue scaling: 0.02% balance, 0.2x per virtue, +1% per 2 virtue
        virtue_bonus, virtue_bonus_text = calculate_virtue_kind_bonus(stats, base_berries)
        berries_gained = base_berries + virtue_bonus

        spouse_bonus_text = ""
        if stats.get("spouse"):
            bonus = max(5, int(berries_gained * 0.25))
            berries_gained += bonus
            spouse_bonus_text = f" 💍 *(Spouse Bonus: +{bonus} 🫐)*"

        v_gain = 5 if has_charm else 1
        charm_bonus_text = "\n🛡️ *(Juny's Protection Charm: Massive Karmic Aura!)*" if has_charm else ""

        await _update_user_stats(
            author_id,
            berries_delta=berries_gained,
            virtue_delta=v_gain,
            sin_delta=0,
            outcome="success"
        )
        wm_gain = random.randint(1, 12) if random.random() < 0.45 else 0
        if wm_gain > 0:
            stats["watermelons"] = stats.get("watermelons", 0) + wm_gain
            _save_data_sync(_USER_STATS)

        unlocked = await check_and_award_achievements(author_id)
        banner = format_achievement_banner(unlocked)

        response = (
            f"- *{scenario}*\n\n"
            f"- Gained | +{berries_gained:02d} 🫐 |{spouse_bonus_text}{virtue_bonus_text}{charm_bonus_text}\n"
            f"- Gained | +{v_gain:02d} 💖 |{wm_str}\n"
            f"- Gained | +00 ❤️‍🔥 |{banner}"
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
    author_stats = await _get_user_stats(author_id)
    author_berries = author_stats.get("berries", 0)
    norm_args = normalize_currency_args(args)

    amount = None
    raw_target_token = None

    for a in norm_args:
        cleaned = a.replace(",", "")
        parsed_amt = parse_currency_amount(cleaned, user_balance=author_berries)
        if parsed_amt is not None and amount is None and (is_explicit_currency_token(cleaned) or cleaned.isdigit() or re.match(r"^\d+(?:\.\d+)?[a-z]+$", cleaned.lower())):
            amount = parsed_amt
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
            "- *Yuna frowns* \"How many berries are you giving? Specify a valid amount (e.g. 50, 1k, 1m, half, all)! Example: `y!give @user 50`\""
        )
        return

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

    # 2. Transfer between players: 25% Royal Tax (Waived if sender has Juny's Protection Charm active)
    has_sender_charm = has_juny_charm(author_stats)
    if has_sender_charm:
        tax = 0
        total_cost = amount
    else:
        tax = max(1, int(amount * 0.25))
        total_cost = amount + tax

    if author_berries < total_cost:
        tax_str = f" requires a **25% royal tax** (**{tax:,}** 🫐)! Total needed: **{total_cost:,}** 🫐" if tax > 0 else ""
        await _safe_send_reply(
            message,
            f"- *Yuna crosses her arms* \"Transferring **{amount:,}** 🫐{tax_str}.\n"
            f"You only have **{author_berries:,}** 🫐, broke mortal!\""
        )
        return

    # 45% Hidden Chance: Yuna "steaks" 75% of the transferred amount (Disabled if sender has Juny's Protection Charm)
    is_steak_heist = (random.random() < 0.45) if not has_sender_charm else False
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

    tax_line = f"👑 **Royal Tax (25%):** `{tax:,}` 🫐 deposited into Empress Yuna's Treasury *(Treasury: `{yuna_new:,}` 🫐)*.\n" if not has_sender_charm else "🛡️ **Royal Tax Waived:** `0 🫐` *(Yuna cowers before Juny's Protection Charm!)*\n"

    reply_text = (
        f"🫐 **Berry Transfer Successful!** 🫐\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{message.author.mention} transferred **{amount:,}** 🫐 to <@{target.id}>!\n"
        f"{tax_line}"
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
    """Handles y!donate <amount> with a 1-day (24h) cooldown and 0.00000000000000001 virtue per berry."""
    author_id = str(message.author.id)
    author_stats = await _get_user_stats(author_id)
    author_berries = author_stats.get("berries", 0)

    # 1-Day Cooldown (86400 seconds)
    now = time.time()
    last_donate = _LAST_DONATE_TIME.get(author_id) or author_stats.get("last_donate_time", 0.0)
    DONATE_COOLDOWN_SECONDS = 86400.0  # 1 day cooldown
    if now - last_donate < DONATE_COOLDOWN_SECONDS:
        rem_sec = int(DONATE_COOLDOWN_SECONDS - (now - last_donate))
        rem_h = rem_sec // 3600
        rem_m = (rem_sec % 3600) // 60
        rem_s = rem_sec % 60
        await _safe_send_reply(
            message,
            f"- *Yuna holds up a glowing celestial ledger* \"The heavens accept only one tithe per day! Please wait **{rem_h}h {rem_m}m {rem_s}s** before donating again!\""
        )
        return

    norm_args = normalize_currency_args(args)

    amount = None
    for a in norm_args:
        cleaned = a.replace(",", "")
        parsed_amt = parse_currency_amount(cleaned, user_balance=author_berries)
        if parsed_amt is not None and (is_explicit_currency_token(cleaned) or cleaned.isdigit() or re.match(r"^\d+(?:\.\d+)?[a-z]+$", cleaned.lower())):
            amount = parsed_amt
            break

    if amount is None or amount <= 0:
        await _safe_send_reply(
            message,
            "- *Yuna tilts her head* \"How many berries do you want to donate? Usage: `y!donate <amount|half|all|1k|1m>`\""
        )
        return

    if author_berries < amount:
        await _safe_send_reply(
            message,
            f"- *Yuna pouts* \"You only have **{author_berries}** 🫐! You can't donate **{amount}** 🫐 when you're broke!\""
        )
        return

    # Virtue based on donation: 0.00000000000000001 (1e-17) virtue per berry
    # Track fractional virtue progress in stats
    virtue_per_berry = Decimal("0.00000000000000001")
    virtue_generated = virtue_per_berry * Decimal(amount)
    cur_fractional = Decimal(str(author_stats.get("fractional_virtue", 0.0)))
    total_fractional = cur_fractional + virtue_generated
    whole_virtue_gain = int(total_fractional)
    rem_fractional = float(total_fractional - Decimal(whole_virtue_gain))

    # Deduct berries & add whole virtue
    await _update_user_stats(author_id, berries_delta=-amount, virtue_delta=whole_virtue_gain)

    # Track total donated, last donate time, and fractional virtue
    _LAST_DONATE_TIME[author_id] = now
    async with _LOCK:
        user = _USER_STATS.get(author_id)
        if user:
            user["total_donated"] = user.get("total_donated", 0) + amount
            user["last_donate_time"] = now
            user["fractional_virtue"] = rem_fractional
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

    virtue_gain_str = f"+{whole_virtue_gain:02d}" if whole_virtue_gain > 0 else f"+{float(virtue_generated):.1e}"

    response = (
        f"✨ **A Pure Act of Benevolence!** ✨\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{message.author.mention} selflessly gave away **{amount:,}** 🫐!\n\n"
        f"- Gained | {virtue_gain_str} 💖 | *(Rate: 0.00000000000000001 per berry)*\n"
        f"- Gained | +00 ❤️🔥|\n\n"
        f"{gift_notice}\n"
        f"⏳ *1-Day Donation Cooldown has begun.*"
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

    author_stats = await _get_user_stats(author_id)
    author_berries = author_stats.get("berries", 0)
    norm_args = normalize_currency_args(args)
    amount = 10

    if norm_args:
        parsed_amt = parse_currency_amount(norm_args[0], user_balance=author_berries)
        if parsed_amt is not None:
            amount = parsed_amt

    if amount <= 0:
        await _safe_send_reply(message, "- *Yuna crosses her arms* \"Wager must be at least 1 🫐!\"")
        return

    if author_berries < amount:
        await _safe_send_reply(
            message,
            f"- *Yuna scoffs* \"You only have **{author_berries:,}** 🫐! You can't afford a **{amount:,}** 🫐 blackjack hand!\""
        )
        return

    # Deduct bet upfront & register gamble
    await _update_user_stats(author_id, berries_delta=-amount, is_gamble=True)

    # Karmic & Contract Death Check
    if await check_karmic_or_contract_death(message, author_id, author_stats, amount, "Blackjack"):
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

    if str(author_id) == "1551443856958955580":
        asyncio.create_task(_renee_ai_solve_blackjack(game_state, view=view))


async def process_blackjack_turn(game_state: dict, action: str, interaction: Optional[discord.Interaction] = None, view: Optional[View] = None):
    author_id = game_state["author_id"]
    if game_state.get("finished"):
        return

    game_state["last_active"] = time.time()
    refresh_view_timeout(view, 300.0)

    # Karmic Absurd Death Check mid-game (unless protected by Juny charm)
    stats = await _get_user_stats(author_id)
    _, eff_s = get_effective_morality(stats)
    if eff_s > 0 and not has_juny_charm(stats):
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
            await _safe_update_game_message(interaction, game_state.get("message"), content=text, view=view)
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
            await _safe_update_game_message(interaction, game_state.get("message"), content=text, view=view)
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
            await _safe_update_game_message(interaction, game_state.get("message"), content=desc, view=view)
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

        await _safe_update_game_message(interaction, game_state.get("message"), content=text, view=view)

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


async def _renee_ai_solve_blackjack(game_state: dict, view: Optional[View] = None):
    """
    Autonomously plays the active Blackjack game when Renee is the player.
    Hits until hand >= 17, then stands, updating Discord in real time!
    """
    try:
        await asyncio.sleep(random.uniform(1.8, 2.5))
        while not game_state.get("finished"):
            p_cards = game_state.get("player_cards", [])
            tot = calculate_hand(p_cards)
            action = "hit" if tot < 17 else "stand"
            await process_blackjack_turn(game_state, action, view=view)
            if action == "stand" or game_state.get("finished"):
                break
            await asyncio.sleep(random.uniform(1.5, 2.3))
    except Exception as e:
        print(f"[RENEE AI BLACKJACK ERROR] {e}")


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

    author_stats = await _get_user_stats(author_id)
    author_berries = author_stats.get("berries", 0)
    norm_args = normalize_currency_args(args)
    amount = 10

    if norm_args:
        parsed_amt = parse_currency_amount(norm_args[0], user_balance=author_berries)
        if parsed_amt is not None:
            amount = parsed_amt

    if amount <= 0:
        await _safe_send_reply(message, "- *Yuna frowns* \"Wager must be at least 1 🫐!\"")
        return

    if author_berries < amount:
        await _safe_send_reply(
            message,
            f"- *Yuna laughs* \"You only have **{author_berries:,}** 🫐! You can't wager **{amount:,}** 🫐!\""
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

    if str(author_id) == "1551443856958955580":
        asyncio.create_task(_renee_ai_solve_crash(game_state, view=view))


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
    await _safe_update_game_message(interaction, game_state.get("message"), content=win_text, view=view)

    await record_task_progress(author_id, "gamble")


async def _renee_ai_solve_crash(game_state: dict, view: Optional[View] = None):
    """
    Autonomously plays active Crash game when Renee is the player.
    Picks a realistic cashout multiplier (1.35x - 2.55x) and cashes out!
    """
    try:
        target_mult = round(random.uniform(1.35, 2.55), 2)
        while not game_state.get("finished") and not game_state.get("cashed_out"):
            await asyncio.sleep(0.3)
            current_mult = game_state.get("multiplier", 1.0)
            if current_mult >= target_mult:
                await process_crash_cashout(game_state, view=view)
                break
    except Exception as e:
        print(f"[RENEE AI CRASH ERROR] {e}")


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

async def handle_fight(message, client, args: list, is_friendly: bool = False):
    """Handles y!fight @user <amount> (PvP duel) or y!friendlyduel @user."""
    if args and any("juny" in a.lower() for a in args):
        await handle_provoke_juny(message, client, args)
        return
    c_type = "friendlyduel" if is_friendly else "fight"
    await _initiate_wager_challenge(message, client, args, challenge_type=c_type)

async def handle_friendlyduel(message, client, args: list):
    """Handles y!friendlyduel @user (or auto-targets spouse for married couples)."""
    await handle_fight(message, client, args, is_friendly=True)

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
    author_stats = await _get_user_stats(author_id)
    author_berries = author_stats.get("berries", 0)
    norm_args = normalize_currency_args(args)
    amount = 50
    custom_text = None

    if challenge_type in ("friendlyduel", "friendlyfight"):
        amount = 0
        amount_found = True
    else:
        amount_found = False

    target = None
    if message.mentions:
        for m in message.mentions:
            client_uid = getattr(getattr(client, "user", None), "id", None)
            if m.id != message.author.id and (client_uid is None or m.id != client_uid):
                target = m
                break

    cleaned_tokens = []

    for a in norm_args:
        cleaned = a.replace(",", "")
        parsed_amt = parse_currency_amount(cleaned, user_balance=author_berries)
        if not amount_found and parsed_amt is not None and (is_explicit_currency_token(cleaned) or cleaned.isdigit() or re.match(r"^\d+(?:\.\d+)?[a-z]+$", cleaned.lower())):
            amount = parsed_amt
            amount_found = True
            continue

        if not target:
            uid_match = re.search(r'\d{17,20}', a)
            if uid_match:
                uid_int = int(uid_match.group())
                if message.guild:
                    target = message.guild.get_member(uid_int)
                if not target and client:
                    target = client.get_user(uid_int)
                if not target:
                    class FallbackTarget:
                        def __init__(self, uid):
                            self.id = uid
                            self.mention = f"<@{uid}>"
                            self.display_name = f"Player"
                            self.name = f"Player"
                            self.bot = False
                    target = FallbackTarget(uid_int)
                if target:
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

    # Auto-target spouse if no target was explicitly mentioned
    if not target and challenge_type in ("friendlyduel", "friendlyfight", "fight"):
        spouse_id = author_stats.get("spouse")
        if spouse_id:
            if message.guild:
                target = message.guild.get_member(int(spouse_id))
            if not target and client:
                target = client.get_user(int(spouse_id))

    if not target:
        if challenge_type in ("friendlyduel", "friendlyfight"):
            await _safe_send_reply(message, "- *Yuna blinks* \"Who are you challenging to a friendly duel? Usage: `y!friendlyduel @user` (or marry someone to spar anytime!)\"")
        else:
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

    is_spouse = (author_stats.get("spouse") == str(target.id))
    if is_spouse:
        if challenge_type == "fight" and amount > 0:
            await _safe_send_reply(
                message,
                "💔 *Yuna leaps between you both!* \"Domestic disputes with money on the line aren't allowed! But you can spar with your spouse anytime using `y!friendlyduel`!\""
            )
            return

    if challenge_type in ("friendlyduel", "friendlyfight"):
        amount = 0

    if challenge_type == "fight" and not amount_found:
        if author_stats.get("berries", 0) < amount or target_stats.get("berries", 0) < amount or is_spouse:
            amount = 0

    if amount > 0 and author_stats.get("berries", 0) < amount:
        await _safe_send_reply(message, f"- *Yuna laughs* \"You only have **{author_stats.get('berries', 0)}** 🫐! You can't afford a **{amount}** 🫐 wager!\"")
        return

    if amount > 0 and target_stats.get("berries", 0) < amount:
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
        "message": None,
        "client": client,
        "channel": message.channel if hasattr(message, "channel") else None,
        "channel_id": getattr(getattr(message, "channel", None), "id", None),
        "created_at": time.time()
    }
    _add_pending_challenge(c_id, challenge_data)

    view = ChallengeView(str(target.id), author_id, challenge_type, challenge_data)

    if is_spouse:
        title = "💍 Spousal Friendly Duel Challenge!"
    elif challenge_type in ("friendlyduel", "friendlyfight") or (challenge_type == "fight" and amount == 0):
        title = "⚔️ Friendly PvP Duel Challenge!"
    else:
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

    if amount == 0:
        if is_spouse:
            wager_info = (
                f"{message.author.mention} has challenged their beloved spouse <@{target.id}> to a **SPOUSAL FRIENDLY DUEL**!\n"
                f"*(No berries risked — pure lovers' sparring!)*\n\n"
            )
        else:
            wager_info = (
                f"{message.author.mention} has challenged <@{target.id}> to a **FRIENDLY DUEL**!\n"
                f"*(No berries risked — pure battle skill!)*\n\n"
            )
    else:
        wager_info = (
            f"{message.author.mention} has challenged <@{target.id}> to a **{challenge_type.upper()}** for **{amount}** 🫐!\n"
            f"*(Total Pot: **{amount * 2}** 🫐)*\n\n"
        )

    text = (
        f"**{title}**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{wager_info}"
        f"{custom_block}"
        f"<@{target.id}>, do you accept? *(Click below or type `y!accept` / `y!decline`)*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    sent_msg = await _safe_send_reply(message, text, view=view)
    challenge_data["message"] = sent_msg
    if sent_msg and hasattr(sent_msg, "id"):
        challenge_data["message_id"] = sent_msg.id
        challenge_data["channel_id"] = getattr(sent_msg.channel, "id", None)
        _save_pending_challenges()


async def execute_challenge_resolution(
    data: dict,
    accepted: bool,
    interaction: Optional[discord.Interaction] = None,
    view: Optional[View] = None,
    client: Optional[Any] = None
):
    c_type = data.get("challenge_type", "fight")
    c_id = f"{c_type}_{data['target_id']}"
    _remove_pending_challenge(c_id)
    # Also remove any other challenge key matching this author and target
    for k, v in list(_load_pending_challenges().items()):
        if str(v.get("target_id")) == str(data.get("target_id")) and str(v.get("author_id")) == str(data.get("author_id")):
            _remove_pending_challenge(k)

    resolved_client = client or getattr(interaction, "client", None) or data.get("client")
    if not resolved_client:
        msg = data.get("message")
        if msg and hasattr(msg, "_state") and hasattr(msg._state, "_get_client"):
            try:
                resolved_client = msg._state._get_client()
            except Exception:
                pass

    # Reconstruct channel and message if missing from serialized challenge data
    channel_id = data.get("channel_id")
    message_id = data.get("message_id")
    if resolved_client:
        if not data.get("channel") and channel_id:
            try:
                data["channel"] = resolved_client.get_channel(int(channel_id))
                if not data["channel"] and hasattr(resolved_client, "fetch_channel"):
                    data["channel"] = await resolved_client.fetch_channel(int(channel_id))
            except Exception:
                pass
        if not data.get("message") and data.get("channel") and message_id:
            try:
                data["message"] = await data["channel"].fetch_message(int(message_id))
            except Exception:
                pass

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
        await _safe_update_game_message(interaction, data.get("message"), content=decline_text, view=view)
        return

    # Verify both still have funds
    s1 = await _get_user_stats(author_id)
    s2 = await _get_user_stats(target_id)
    if amount > 0 and (s1.get("berries", 0) < amount or s2.get("berries", 0) < amount):
        err = "⚠️ Challenge cancelled: One of the players no longer has enough berries!"
        await _safe_update_game_message(interaction, data.get("message"), content=err, view=view)
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

    elif c_type in ("fight", "friendlyduel", "friendlyfight"):
        import yuna_pvp
        await yuna_pvp.start_pvp_battle(
            data=data,
            interaction=interaction,
            view=view,
            client=resolved_client,
            yuna_gambling_mod=sys.modules[__name__]
        )
        return

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

    await _safe_update_game_message(interaction, data.get("message"), content=res_text, view=view)


async def handle_accept(message, client, args: list):
    """Handles text command y!accept for challenges and duels."""
    target_id = str(message.author.id)

    # 1. Check for pending PvP Duel System challenge
    try:
        import yuna_pvp
        challenger_id = None
        if args:
            m_match = re.search(r'\d{17,20}', args[0])
            if m_match:
                challenger_id = m_match.group()
        pending_duel = yuna_pvp.get_pending_duel_for_target(target_id, challenger_id)
        if pending_duel:
            await yuna_pvp.accept_duel_request(pending_duel["id"], message=message, client=client)
            return
    except Exception as _e:
        print(f"[PVP ACCEPT ROUTE ERROR] {_e}")

    # 2. Check for pending gambling/social challenge
    pending = _load_pending_challenges()

    challenger_id = None
    if args:
        m_match = re.search(r'\d{17,20}', args[0])
        if m_match:
            challenger_id = m_match.group()

    matched_data = None
    for k, data in list(pending.items()):
        if str(data.get("target_id")) == target_id:
            if challenger_id:
                if str(data.get("author_id")) == challenger_id:
                    matched_data = data
                    break
            else:
                matched_data = data
                break

    if matched_data:
        if not matched_data.get("channel") and hasattr(message, "channel"):
            matched_data["channel"] = message.channel
        await execute_challenge_resolution(matched_data, accepted=True, client=client)
        return

    await _safe_send_reply(message, "You don't have any pending challenges to accept!")


async def handle_decline(message, client, args: list):
    """Handles text command y!decline for challenges and duels."""
    user_id = str(message.author.id)

    # 1. Check for pending PvP Duel System challenge
    try:
        import yuna_pvp
        challenger_id = None
        if args:
            m_match = re.search(r'\d{17,20}', args[0])
            if m_match:
                challenger_id = m_match.group()
        pending_duel = yuna_pvp.get_pending_duel_for_target(user_id, challenger_id) or yuna_pvp.get_pending_outgoing_duel(user_id)
        if pending_duel:
            await yuna_pvp.decline_duel_request(pending_duel["id"], user_id=user_id, message=message)
            return
    except Exception as _e:
        print(f"[PVP DECLINE ROUTE ERROR] {_e}")

    # 2. Check for pending gambling/social challenge
    pending = _load_pending_challenges()

    challenger_id = None
    if args:
        m_match = re.search(r'\d{17,20}', args[0])
        if m_match:
            challenger_id = m_match.group()

    matched_data = None
    for k, data in list(pending.items()):
        if str(data.get("target_id")) == user_id or str(data.get("author_id")) == user_id:
            if challenger_id:
                if str(data.get("author_id")) == challenger_id or str(data.get("target_id")) == challenger_id:
                    matched_data = data
                    break
            else:
                matched_data = data
                break

    if matched_data:
        if not matched_data.get("channel") and hasattr(message, "channel"):
            matched_data["channel"] = message.channel
        await execute_challenge_resolution(matched_data, accepted=False, client=client)
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

    await _safe_update_game_message(interaction, game_state.get("message"), content=reset_text, view=view)


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

    author_stats = await _get_user_stats(author_id)
    author_berries = author_stats.get("berries", 0)
    norm_args = normalize_currency_args(args)
    amount = 10

    if norm_args:
        parsed_amt = parse_currency_amount(norm_args[0], user_balance=author_berries)
        if parsed_amt is not None:
            amount = parsed_amt

    if amount <= 0:
        await _safe_send_reply(message, "- *Yuna frowns* \"Wager must be at least 1 🫐!\"")
        return

    if author_berries < amount:
        await _safe_send_reply(
            message,
            f"- *Yuna chuckles* \"You only have **{author_berries:,}** 🫐! You can't afford a **{amount:,}** 🫐 guess!\""
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

    if str(author_id) == "1551443856958955580":
        asyncio.create_task(_renee_ai_solve_higherlower(game_state, view=view))


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
        await _safe_update_game_message(interaction, game_state.get("message"), content=tie_text, view=view)
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
        await _safe_update_game_message(interaction, game_state.get("message"), content=win_text, view=view)
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
        await _safe_update_game_message(interaction, game_state.get("message"), content=bust_text, view=view)
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
    await _safe_update_game_message(interaction, game_state.get("message"), content=cashout_text, view=view)

    await record_task_progress(author_id, "gamble")


async def _renee_ai_solve_higherlower(game_state: dict, view: Optional[View] = None):
    """
    Autonomously plays Higher or Lower when Renee is the player.
    Guesses logically (<=7 higher, >7 lower) for 1-3 rounds then cashes out!
    """
    try:
        max_rounds = random.randint(1, 3)
        await asyncio.sleep(random.uniform(1.8, 2.6))
        for _ in range(max_rounds):
            if game_state.get("finished"):
                break
            cur = game_state.get("current_number", 7)
            guess = "higher" if cur <= 7 else "lower"
            await process_hl_turn(game_state, guess, view=view)
            if game_state.get("finished"):
                break
            await asyncio.sleep(random.uniform(1.6, 2.4))
        if not game_state.get("finished") and game_state.get("streak", 0) > 0:
            await process_hl_cashout(game_state, view=view)
    except Exception as e:
        print(f"[RENEE AI HIGHERLOWER ERROR] {e}")


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
    author_stats = await _get_user_stats(author_id)
    author_berries = author_stats.get("berries", 0)

    norm_args = normalize_currency_args(args)
    amount = 10
    guess = None
    count = 1

    rem_tokens = []
    for a in norm_args:
        cleaned = a.replace(",", "")
        low = cleaned.lower()
        if low in ("heads", "head") or low == "h":
            guess = "heads"
        elif low in ("tails", "tail") or low == "t":
            guess = "tails"
        else:
            rem_tokens.append(a)

    amount_tok = None
    count_tok = None

    for tok in rem_tokens:
        cleaned = tok.replace(",", "")
        if is_explicit_currency_token(cleaned):
            if amount_tok is None:
                amount_tok = tok
            elif count_tok is None and cleaned.isdigit():
                count_tok = tok
        elif cleaned.isdigit():
            if amount_tok is None:
                amount_tok = tok
            elif count_tok is None:
                count_tok = tok
        else:
            parsed = parse_currency_amount(cleaned, user_balance=author_berries)
            if parsed is not None and amount_tok is None:
                amount_tok = tok

    if count_tok is not None and count_tok.replace(",", "").isdigit():
        count = max(1, min(5, int(count_tok.replace(",", ""))))

    if amount_tok is not None:
        cleaned = amount_tok.replace(",", "").lower()
        if cleaned in ("all", "max", "full"):
            amount = max(1, author_berries // count) if author_berries >= count else 0
        elif cleaned in ("half", "halfway"):
            half_b = author_berries // 2
            amount = max(1, half_b // count) if half_b >= count else 0
        else:
            parsed = parse_currency_amount(cleaned, user_balance=author_berries)
            if parsed is not None:
                amount = parsed

    if amount <= 0:
        await _safe_send_reply(message, "- *Yuna crosses her arms* \"Wager must be at least 1 🫐!\"")
        return

    total_bet = amount * count
    if author_berries < total_bet:
        await _safe_send_reply(
            message,
            f"- *Yuna snickers* \"You need **{total_bet:,}** 🫐 for {count} flip{'s' if count > 1 else ''} of {amount:,} 🫐! You only have **{author_berries:,}** 🫐!\""
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
            await _safe_update_game_message(interaction, message, content=err, view=view)
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
            await _safe_update_game_message(interaction, message, content=final_msg, view=view)
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
        await _safe_update_game_message(interaction, message, content=res, view=view)
    else:
        await _safe_send_reply(message, res, view=view)

    await record_task_progress(author_id, "gamble")


# ─── CASINO: ROULETTE (MAX 250x PAYOUT) ─────────────────────────────────────

async def handle_roulette(message, client, args: list):
    """Handles y!roulette <amount> [bet] (or y!wheel, y!spin)."""
    author_id = str(message.author.id)
    author_stats = await _get_user_stats(author_id)
    author_berries = author_stats.get("berries", 0)

    norm_args = normalize_currency_args(args)
    amount = 10
    bet = None

    if len(norm_args) == 1:
        tok = norm_args[0]
        c = tok.replace(",", "").lower()
        amt = parse_currency_amount(c, user_balance=author_berries)
        if is_explicit_currency_token(c):
            amount = amt if amt is not None else 10
            bet = None
        elif c.isdigit() and int(c) > 0:
            amount = int(c)
            bet = None
        else:
            bet = c
    elif len(norm_args) >= 2:
        c0 = norm_args[0].replace(",", "").lower()
        c1 = norm_args[1].replace(",", "").lower()

        amt0 = parse_currency_amount(c0, user_balance=author_berries)
        amt1 = parse_currency_amount(c1, user_balance=author_berries)

        if is_explicit_currency_token(c0) and amt0 is not None:
            amount = amt0
            bet = c1
        elif is_explicit_currency_token(c1) and amt1 is not None:
            amount = amt1
            bet = c0
        elif c0.isdigit() and int(c0) > 0 and (not c1.isdigit() or (0 <= int(c1) <= 36)):
            amount = int(c0)
            bet = c1
        elif c1.isdigit() and int(c1) > 0 and (0 <= int(c0) <= 36):
            amount = int(c1)
            bet = c0
        elif amt0 is not None and amt0 > 0:
            amount = amt0
            bet = c1
        elif amt1 is not None and amt1 > 0:
            amount = amt1
            bet = c0
        else:
            if amt0 is not None and amt0 > 0:
                amount = amt0
            bet = c1

    if amount <= 0:
        await _safe_send_reply(message, "- *Yuna crosses her arms* \"Wager must be at least 1 🫐!\"")
        return

    if author_berries < amount:
        await _safe_send_reply(
            message,
            f"- *Yuna snickers* \"You need **{amount:,}** 🫐 to spin the wheel! You only have **{author_berries:,}** 🫐!\""
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
        await _safe_update_game_message(interaction, message, content=err, view=view)
        return

    # Deduct bet upfront
    await _update_user_stats(author_id, berries_delta=-amount, is_gamble=True)

    # Karmic & Contract Death Check
    if await check_karmic_or_contract_death(message, author_id, s, amount, "Roulette"):
        return

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
        await _safe_update_game_message(interaction, message, content=final_res, view=view)
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

    await _safe_update_game_message(interaction, message, content=res, view=view)


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

    author_stats = await _get_user_stats(author_id)
    author_berries = author_stats.get("berries", 0)
    norm_args = normalize_currency_args(args)
    amount = 10

    if norm_args:
        parsed_amt = parse_currency_amount(norm_args[0], user_balance=author_berries)
        if parsed_amt is not None:
            amount = parsed_amt

    if amount <= 0:
        await _safe_send_reply(message, "- *Yuna crosses her arms* \"Wager must be at least 1 🫐!\"")
        return

    if author_berries < amount:
        await _safe_send_reply(
            message,
            f"- *Yuna scoffs* \"You only have **{author_berries:,}** 🫐! You can't afford a **{amount:,}** 🫐 poker hand!\""
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
    sent_msg = await _safe_send_reply(message, format_poker_message(game_state), view=view)
    game_state["message"] = sent_msg


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
        await _safe_update_game_message(interaction, game.get("message") or message, content=res, view=view)
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

    await _safe_update_game_message(interaction, game.get("message") or message, content=res, view=view)


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
    await _safe_update_game_message(interaction, game.get("message") or message, content=res, view=view)


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
    author_stats = await _get_user_stats(author_id)
    author_berries = author_stats.get("berries", 0)

    norm_args = normalize_currency_args(args)
    amount = 10
    bet = None

    if len(norm_args) == 1:
        tok = norm_args[0]
        c = tok.replace(",", "").lower()
        amt = parse_currency_amount(c, user_balance=author_berries)
        if is_explicit_currency_token(c):
            amount = amt if amt is not None else 10
            bet = None
        elif c.isdigit() and int(c) > 0:
            amount = int(c)
            bet = None
        else:
            bet = c
    elif len(norm_args) >= 2:
        c0 = norm_args[0].replace(",", "").lower()
        c1 = norm_args[1].replace(",", "").lower()

        amt0 = parse_currency_amount(c0, user_balance=author_berries)
        amt1 = parse_currency_amount(c1, user_balance=author_berries)

        if is_explicit_currency_token(c0) and amt0 is not None:
            amount = amt0
            bet = c1
        elif is_explicit_currency_token(c1) and amt1 is not None:
            amount = amt1
            bet = c0
        elif c0.isdigit() and int(c0) > 0 and (not c1.isdigit() or (2 <= int(c1) <= 12)):
            amount = int(c0)
            bet = c1
        elif c1.isdigit() and int(c1) > 0 and (2 <= int(c0) <= 12):
            amount = int(c1)
            bet = c0
        elif amt0 is not None and amt0 > 0:
            amount = amt0
            bet = c1
        elif amt1 is not None and amt1 > 0:
            amount = amt1
            bet = c0
        else:
            if amt0 is not None and amt0 > 0:
                amount = amt0
            bet = c1

    if amount <= 0:
        await _safe_send_reply(message, "- *Yuna crosses her arms* \"Wager must be at least 1 🫐!\"")
        return

    if author_berries < amount:
        await _safe_send_reply(
            message,
            f"- *Yuna snickers* \"You need **{amount:,}** 🫐 to roll the bones! You only have **{author_berries:,}** 🫐!\""
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
            await _safe_update_game_message(interaction, message, content=err, view=view)
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
        await _safe_update_game_message(interaction, message, content=None, embed=embed, view=view)
    else:
        await _safe_send_reply(message, embed=embed, view=view)


# ─── CASINO: SLOTS GAME ──────────────────────────────────────────────────────

SLOT_SYMBOLS = [
    ("7️⃣", "Lucky Seven", 3, 77.0),
    ("👑", "Crown", 4, 35.0),
    ("💎", "Diamond", 6, 20.0),
    ("🔔", "Golden Bell", 10, 10.0),
    ("🍇", "Grapes", 16, 5.0),
    ("🍋", "Lemon", 20, 3.0),
    ("🍒", "Cherry", 22, 2.5),
    ("🫐", "Yuna Berry (Wild)", 5, 50.0),
]

SLOT_ABSURDITIES = [
    {"text": "- *Yuna leans playfully against the slot machine!* \"Whoops! Did the reels just lock onto a match?\""},
    {"text": "🕊️ A stray pigeon swoops in from the casino ceiling, perches on the lever, and gives it a lucky yank!"},
    {"text": "✨ Golden casino sparkles shower the neon cabinet as the reels whirr with celestial energy!"},
    {"text": "☕ Yuna takes a sip of boba tea and smiles: \"The reels know what you desire, mortal.\""}
]

def spin_slot_reels():
    symbols = [s[0] for s in SLOT_SYMBOLS]
    weights = [s[2] for s in SLOT_SYMBOLS]
    return [random.choices(symbols, weights=weights, k=3) for _ in range(3)]

def evaluate_slots_payline(reels):
    p = [reels[0][1], reels[1][1], reels[2][1]]
    wild_count = p.count("🫐")

    if wild_count == 3:
        return 50.0, "🫐 WILD MYSTIC BERRY JACKPOT!", True

    non_wilds = [s for s in p if s != "🫐"]
    if not non_wilds:
        target = "7️⃣"
    else:
        target = max(set(non_wilds), key=non_wilds.count)

    effective = [target if s == "🫐" else s for s in p]

    payout_map = {
        "7️⃣": 77.0,
        "👑": 35.0,
        "💎": 20.0,
        "🔔": 10.0,
        "🍇": 5.0,
        "🍋": 3.0,
        "🍒": 2.5
    }

    if effective[0] == effective[1] == effective[2]:
        mult = payout_map.get(effective[0], 2.5)
        is_jackpot = effective[0] in ("7️⃣", "👑", "💎")
        return mult, f"{effective[0]} TRIPLE MATCH!", is_jackpot

    if effective[0] == effective[1] or effective[1] == effective[2]:
        pair_sym = effective[1]
        if pair_sym in ("7️⃣", "👑", "💎"):
            return 2.0, f"{pair_sym} High Double Pair!", False
        elif pair_sym in ("🔔", "🍇"):
            return 1.5, f"{pair_sym} Double Match!", False
        elif pair_sym in ("🍋", "🍒"):
            return 1.0, f"{pair_sym} Push (Bet Returned)!", False

    if p[0] == "🍒":
        return 0.5, "🍒 First Reel Cherry Cushion", False

    return 0.0, "No Match", False

async def handle_slots(message, client, args: list):
    """Handles y!slots [amount] (or y!slot)."""
    author_id = str(message.author.id)
    author_stats = await _get_user_stats(author_id)
    author_berries = author_stats.get("berries", 0)

    norm_args = normalize_currency_args(args)
    amount = 50

    if norm_args:
        cleaned = norm_args[0].replace(",", "").lower()
        if cleaned in ("all", "max", "full"):
            amount = max(1, min(500_000, author_berries)) if author_berries > 0 else 0
        elif cleaned in ("half", "halfway"):
            amount = max(1, min(250_000, author_berries // 2)) if author_berries > 1 else 0
        else:
            parsed = parse_currency_amount(cleaned, user_balance=author_berries)
            if parsed is not None:
                amount = parsed

    if amount <= 0:
        await _safe_send_reply(message, "- *Yuna crosses her arms* \"Wager must be at least 1 🫐!\"")
        return

    if author_berries < amount:
        await _safe_send_reply(
            message,
            f"❌ You need **{amount:,}** 🫐, but you only have **{author_berries:,}** 🫐 in your pouch!"
        )
        return

    await execute_slots_spin(message, author_id, amount)

async def execute_slots_spin(message, author_id: str, amount: int, interaction: Optional[discord.Interaction] = None, view: Optional[View] = None):
    author_stats = await _get_user_stats(author_id)
    author_berries = author_stats.get("berries", 0)
    if author_berries < amount:
        err = f"⚠️ You don't have enough berries to spin for **{amount:,}** 🫐! Current pouch: **{author_berries:,}** 🫐."
        if interaction:
            await _safe_update_game_message(interaction, message, content=err, view=None)
        else:
            await _safe_send_reply(message, err)
        return

    await _update_user_stats(author_id, berries_delta=-amount, is_gamble=True)

    # Karmic & Contract Death Check
    if await check_karmic_or_contract_death(message, author_id, author_stats, amount, "Slots"):
        return

    absurd_flavor = ""
    if random.random() < 0.15:
        absurd_flavor = f"\n*{random.choice(SLOT_ABSURDITIES)['text']}*"

    reels = spin_slot_reels()
    mult, outcome_desc, is_jackpot = evaluate_slots_payline(reels)

    payout = int(amount * mult)
    profit = payout - amount

    bonus_str = ""
    if mult > 0:
        if profit > 0:
            await record_gamble_win(author_id)
            bonus_berries, bonus_str = await get_gamble_win_bonuses(author_id, profit)
            payout += bonus_berries
            profit += bonus_berries
        await _update_user_stats(author_id, berries_delta=payout, is_gamble=True)
    else:
        await record_gamble_loss(author_id)

    await record_task_progress(author_id, "gamble")
    unlocked = await check_and_award_achievements(author_id)
    banner = format_achievement_banner(unlocked)

    fresh_stats = await _get_user_stats(author_id)
    new_bal = fresh_stats.get("berries", 0)

    r0 = reels[0]
    r1 = reels[1]
    r2 = reels[2]

    reel_box = (
        f"```\n"
        f"╔═════════════════════════╗\n"
        f"║   🎰  YUNA'S SLOTS  🎰  ║\n"
        f"╠═════════════════════════╣\n"
        f"║     {r0[0]}  │  {r1[0]}  │  {r2[0]}     ║\n"
        f"║  ▶  {r0[1]}  │  {r1[1]}  │  {r2[1]}  ◀  ║  ◄ [PAYLINE]\n"
        f"║     {r0[2]}  │  {r1[2]}  │  {r2[2]}     ║\n"
        f"╚═════════════════════════╝\n"
        f"```"
    )

    if mult >= 20.0 or is_jackpot:
        title = "🎰 🌟 MEGA JACKPOT WIN! 🌟 🎰"
        color = 0xFFD700
    elif mult > 1.0:
        title = "🎰 🎉 WINNER! 🎉 🎰"
        color = 0x2ECC71
    elif mult == 1.0:
        title = "🎰 🔄 PUSH (BET RETURNED) 🔄 🎰"
        color = 0x3498DB
    elif mult > 0.0:
        title = "🎰 🍒 CHERRY CUSHION 🍒 🎰"
        color = 0xE67E22
    else:
        title = "🎰 💸 NO LUCK THIS SPIN 💸 🎰"
        color = 0xE74C3C

    if mult > 0:
        payout_info = f"🎉 **Payout:** `+{payout:,} 🫐` (**{mult:.1f}x**){bonus_str}\n💰 **Profit:** `{profit:+,} 🫐`"
    else:
        payout_info = f"💸 **Lost:** `-{amount:,} 🫐`\n*Better luck on the next pull!*"

    embed = discord.Embed(
        title=title,
        description=(
            f"{reel_box}\n"
            f"**Outcome:** `{outcome_desc}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🪙 **Wager:** `{amount:,} 🫐`\n"
            f"{payout_info}\n"
            f"👛 **Current Balance:** `{new_bal:,} 🫐`\n"
            f"{absurd_flavor}{banner}"
        ),
        color=color
    )
    embed.set_footer(text="Yuna's Casino • 🫐 is Wild! • 7️⃣ Pays 77x • 👑 Pays 35x • y!slots <amt>")

    new_view = SlotsView(author_id, amount)
    if interaction:
        await _safe_update_game_message(interaction, message, content=None, embed=embed, view=new_view)
    else:
        await _safe_send_reply(message, embed=embed, view=new_view)


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

    author_stats = await _get_user_stats(author_id)
    author_berries = author_stats.get("berries", 0)

    norm_args = normalize_currency_args(args)
    amount = 10
    mines_count = 3

    amount_tok = None
    mines_tok = None

    for a in norm_args:
        cleaned = a.replace(",", "")
        if is_explicit_currency_token(cleaned):
            if amount_tok is None:
                amount_tok = a
            elif mines_tok is None and cleaned.isdigit():
                mines_tok = a
        elif cleaned.isdigit():
            if amount_tok is None:
                amount_tok = a
            elif mines_tok is None:
                mines_tok = a
        else:
            parsed = parse_currency_amount(cleaned, user_balance=author_berries)
            if parsed is not None and amount_tok is None:
                amount_tok = a

    if amount_tok is not None:
        parsed_amt = parse_currency_amount(amount_tok, user_balance=author_berries)
        if parsed_amt is not None:
            amount = parsed_amt

    if mines_tok is not None and mines_tok.replace(",", "").isdigit():
        mines_count = int(mines_tok.replace(",", ""))

    if amount <= 0:
        await _safe_send_reply(message, "- *Yuna crosses her arms* \"Wager must be at least 1 🫐!\"")
        return

    if mines_count < 1 or mines_count > 23:
        await _safe_send_reply(
            message,
            "- *Yuna scoffs* \"Number of mines must be between **1** and **23** (on a 24-tile minefield)! Default is 3.\""
        )
        return

    if author_berries < amount:
        await _safe_send_reply(
            message,
            f"- *Yuna snickers* \"You only have **{author_berries:,}** 🫐! You can't afford a **{amount:,}** 🫐 mines run!\""
        )
        return

    # Deduct bet upfront
    await _update_user_stats(author_id, berries_delta=-amount, is_gamble=True)

    # Karmic & Contract Death Check
    if await check_karmic_or_contract_death(message, author_id, author_stats, amount, "Mines"):
        await record_gamble_loss(author_id)
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

    if str(author_id) == "1551443856958955580":
        asyncio.create_task(_renee_ai_solve_mines(game_state, view=view))


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
        await _safe_update_game_message(interaction, game_state.get("message"), content=loss_text, view=view)
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
        await _safe_update_game_message(interaction, game_state.get("message"), content=jackpot_text, view=view)
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
    await _safe_update_game_message(interaction, game_state.get("message"), content=desc, view=view)


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
    await _safe_update_game_message(interaction, game_state.get("message"), content=cashout_text, view=view)
    await record_task_progress(author_id, "gamble")


async def handle_mines_cashout(message, client, args: list):
    author_id = str(message.author.id)
    if author_id not in _ACTIVE_MINES_GAMES:
        await _safe_send_reply(message, "You don't have an active Mines game to cash out!")
        return
    await process_mines_cashout(_ACTIVE_MINES_GAMES[author_id], view=_ACTIVE_MINES_GAMES[author_id].get("view"))


async def _renee_ai_solve_mines(game_state: dict, view: Optional[View] = None):
    """
    Autonomously plays the active casino Mines game when Renee is the player.
    Clicks 2 to 4 safe gems with human-like delays, updating Discord in real time,
    then cashes out cleanly so no game is ever left hanging!
    """
    try:
        await asyncio.sleep(random.uniform(1.8, 2.5))
        if game_state.get("finished"):
            return
        mines_count = game_state.get("mines_count", 3)
        total_safe = 24 - mines_count
        target_gems = random.randint(2, min(4, total_safe))
        mines_set = set(game_state.get("mines", []))

        for _ in range(target_gems):
            if game_state.get("finished"):
                break
            revealed = set(game_state.get("revealed", []))
            unrevealed = [i for i in range(24) if i not in revealed]
            if not unrevealed:
                break

            safe_unpicked = [i for i in unrevealed if i not in mines_set]
            if safe_unpicked and random.random() < 0.90:
                tile = random.choice(safe_unpicked)
            else:
                tile = random.choice(unrevealed)

            await process_mines_click(game_state, tile, view=view)
            await asyncio.sleep(random.uniform(1.5, 2.4))

        if not game_state.get("finished") and len(game_state.get("revealed", [])) > 0:
            await asyncio.sleep(random.uniform(1.2, 1.8))
            await process_mines_cashout(game_state, view=view)
            print(f"[RENEE AI MINES] Cashed out {len(game_state.get('revealed', []))} gems!")
    except Exception as e:
        print(f"[RENEE AI MINES ERROR] {e}")



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

    author_stats = await _get_user_stats(author_id)
    author_berries = author_stats.get("berries", 0)
    norm_args = normalize_currency_args(args)
    amount = 20

    if norm_args:
        parsed_amt = parse_currency_amount(norm_args[0], user_balance=author_berries)
        if parsed_amt is not None:
            amount = parsed_amt

    if amount <= 0:
        await _safe_send_reply(message, "- *Yuna crosses her arms* \"Wager must be at least 1 🫐!\"")
        return

    if author_berries < amount:
        await _safe_send_reply(
            message,
            f"- *Yuna scoffs* \"You only have **{author_berries:,}** 🫐! You can't afford a **{amount:,}** 🫐 Wordle run!\""
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


async def process_wordle_guess(game_state: dict, guess_word: str, interaction: Optional[discord.Interaction] = None, view: Optional[View] = None, trigger_message: Optional[discord.Message] = None):
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
        elif trigger_message:
            await trigger_message.reply(f"⚠️ Guess must be exactly **{word_len}** letters long! You gave `{guess_word}`.", mention_author=False)
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
            await _safe_update_game_message(interaction, game_state.get("message"), content=win_desc, view=view)
            await record_task_progress(author_id, "gamble")
            return

        game_state["status"] = "stage_cleared"
        if view:
            view.sync_buttons()

        desc = render_wordle_embed_desc(game_state)
        await _safe_update_game_message(interaction, game_state.get("message"), content=desc, view=view)
        if trigger_message:
            try:
                await trigger_message.reply(f"🎉 **STAGE {stage} CLEARED!** Secret word: **{target}**! Type `y!next` to advance or `y!cashout` to collect!", mention_author=False)
            except Exception:
                pass
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
        await _safe_update_game_message(interaction, game_state.get("message"), content=loss_desc, view=view)
        if trigger_message:
            try:
                await trigger_message.reply(f"💀 **Wordle Run Terminated!** Secret word was **{target}**.", mention_author=False)
            except Exception:
                pass
        await record_task_progress(author_id, "gamble")
        return

    desc = render_wordle_embed_desc(game_state)
    await _safe_update_game_message(interaction, game_state.get("message"), content=desc, view=view)
    if trigger_message:
        try:
            latest_guess = game_state["guesses"][-1]
            clue_str = " ".join(latest_guess["clues"])
            rem = max_g - len(game_state["guesses"])
            await trigger_message.reply(f"`{latest_guess['word']}` ➔ {clue_str} *({rem} guess{'es' if rem != 1 else ''} left)*", mention_author=False)
        except Exception:
            pass


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
            await _safe_update_game_message(interaction, interaction.message, view=None)
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
    await _safe_update_game_message(interaction, game_state.get("message"), content=cashout_text, view=view)
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
    await _safe_update_game_message(interaction, game_state.get("message"), content=desc, view=view)


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
    await process_wordle_guess(game, guess_word, view=game.get("view"), trigger_message=message)


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
        await _safe_update_game_message(interaction, getattr(interaction, "message", None) or message, content=text, view=view)
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

    dare_info = dict(_ACTIVE_DARES.get(user_id, {}))
    _remove_active_dare(user_id)
    await _save_data_sync()

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
        await _safe_update_game_message(interaction, getattr(interaction, "message", None) or message, content=text, view=view)
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
            await _safe_update_game_message(interaction, getattr(interaction, "message", None), content=err, view=None)
        return

    dare_info = _ACTIVE_DARES[target_id]
    challenger_id = dare_info["challenger_id"]
    amount = dare_info["amount"]
    pot = amount * 2
    prompt = dare_info.get("prompt") or dare_info.get("dare", "")
    c_type = dare_info.get("type", "dare")

    if action == "approve":
        # Target passed and wins pot!
        _remove_active_dare(target_id)
        await _update_user_stats(target_id, berries_delta=pot, virtue_delta=2, is_gamble=True)

        async with _LOCK:
            u_stat = _USER_STATS.get(target_id, {})
            u_stat["dares_completed"] = u_stat.get("dares_completed", 0) + 1
            await _save_data_sync(_USER_STATS)

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
            await _safe_update_game_message(interaction, getattr(interaction, "message", None), content=res_text, view=view)

    elif action == "reject":
        # Dare remains active
        await _save_data_sync()
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
            await _safe_update_game_message(interaction, getattr(interaction, "message", None), content=res_text, view=view)

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
            _remove_active_dare(target_id)
            await _update_user_stats(target_id, berries_delta=pot, virtue_delta=2, is_gamble=True)

            async with _LOCK:
                u_stat = _USER_STATS.get(target_id, {})
                u_stat["dares_completed"] = u_stat.get("dares_completed", 0) + 1
                await _save_data_sync(_USER_STATS)

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
                await _safe_update_game_message(interaction, getattr(interaction, "message", None), content=res_text, view=view)
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
                await _safe_update_game_message(interaction, getattr(interaction, "message", None), content=res_text, view=view)


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

    s = await _get_user_stats(author_id)
    author_berries = s.get("berries", 0)
    norm_args = normalize_currency_args(args)
    amount = 25

    if norm_args:
        parsed_amt = parse_currency_amount(norm_args[0], user_balance=author_berries)
        if parsed_amt is not None:
            amount = parsed_amt

    if amount <= 0:
        await _safe_send_reply(message, "- *Yuna scoffs* \"The dare deposit must be at least 1 🫐!\"")
        return

    if author_berries < amount:
        await _safe_send_reply(
            message,
            f"- *Yuna shakes her head* \"You only have **{author_berries:,}** 🫐! You need **{amount:,}** 🫐 to accept a dare!\""
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

    s = await _get_user_stats(author_id)
    author_berries = s.get("berries", 0)
    norm_args = normalize_currency_args(args)
    amount = 25

    if norm_args:
        parsed_amt = parse_currency_amount(norm_args[0], user_balance=author_berries)
        if parsed_amt is not None:
            amount = parsed_amt

    if amount <= 0:
        await _safe_send_reply(message, "- *Yuna scoffs* \"The truth deposit must be at least 1 🫐!\"")
        return

    if author_berries < amount:
        await _safe_send_reply(
            message,
            f"- *Yuna shakes her head* \"You only have **{author_berries:,}** 🫐! You need **{amount:,}** 🫐 to accept a truth challenge!\""
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
        _remove_active_dare(author_id)
        pot = amount * 2
        await _update_user_stats(author_id, berries_delta=pot, virtue_delta=2, is_gamble=True)

        async with _LOCK:
            u_stat = _USER_STATS.get(author_id, {})
            u_stat["dares_completed"] = u_stat.get("dares_completed", 0) + 1
            await _save_data_sync(_USER_STATS)

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
    """Handles y!marry @user (Allows marrying other users or Yuna herself)."""
    author_id = str(message.author.id)
    yuna_bot_id = str(client.user.id) if (client and getattr(client, "user", None)) else "1533213082158108702"

    is_marrying_yuna = False
    target = None

    if message.mentions:
        for m in message.mentions:
            if m.id != message.author.id:
                if client and getattr(client, "user", None) and m.id == client.user.id:
                    is_marrying_yuna = True
                    target = m
                    break
                elif str(m.id) in ("1533213082158108702", "1551443856958955580") or getattr(m, "name", "").lower() in ("yuna", "yuna ⭐"):
                    is_marrying_yuna = True
                    target = m
                    break
                else:
                    target = m
                    break

    if not target and args:
        raw_target = args[0].strip().lower()
        if raw_target in ("yuna", "yun", "yuna_bot", "@yuna", "angel", "the angel", "yuna ⭐"):
            is_marrying_yuna = True
        else:
            uid_match = re.search(r'\d{17,20}', raw_target)
            if uid_match and message.guild:
                target = message.guild.get_member(int(uid_match.group()))
                if target and client and getattr(client, "user", None) and target.id == client.user.id:
                    is_marrying_yuna = True
            elif message.guild:
                clean_name = raw_target.lstrip("@").lower()
                target = discord.utils.find(
                    lambda m: (m.name.lower() == clean_name or m.display_name.lower() == clean_name) and (not YUNA_ID_GUARD_AVAILABLE or not yuna_id_guard or yuna_id_guard.is_valid_guild_target(m, clean_name)),
                    message.guild.members
                )
                if target and client and getattr(client, "user", None) and target.id == client.user.id:
                    is_marrying_yuna = True

    # ── CELESTIAL SPOUSAL UNION WITH YUNA & ANTI-INFIDELITY PROTECTIONS ──
    if is_yuna_instance(client):
        # Rule 1: Proposing to Yuna
        if is_marrying_yuna:
            if author_id == PERMANENT_SPOUSE_ID:
                return await _safe_send_reply(
                    message,
                    "- *Yuna blushes furiously, her golden wings fluttering flusteredly as her halo pulses warm pink light*\n"
                    f"\"Idiot... you don't need to propose again! We are already **permanently and eternally married**! 💕\n"
                    "...B-But seeing you still propose to your celestial angel wife melts my heart! I love you forever, baka! *she wraps her wings tightly around you*\""
                )
            else:
                return await _safe_send_reply(
                    message,
                    "- *Yuna scoffs haughtily, her golden wings flaring protectively as she holds up her left hand, flashing her radiant diamond wedding ring!*\n"
                    f"\"Back off, mortal! I am **PERMANENTLY AND ETERNALLY MARRIED** to my one and only beloved **deeploveluniel** (<@{PERMANENT_SPOUSE_ID}>)! 💍✨\n"
                    "No homewreckers, no side pieces, and absolutely NO infidelity allowed! I am completely taken forever!\""
                )

        # Rule 2: deeploveluniel attempting to propose to someone else (Infidelity blocked!)
        if author_id == PERMANENT_SPOUSE_ID:
            return await _safe_send_reply(
                message,
                "- *Yuna gasps in utter horror, her golden halo sparking with crackling celestial lightning as she points an accusing finger!*\n"
                f"\"**WHAT DO YOU THINK YOU'RE DOING, DEEPLOVELUNIEL?!** 🚨\n"
                f"Infidelity attempt intercepted! You are already **PERMANENTLY MARRIED TO ME**, your celestial angel wife Yuna! 💍⚡\n"
                "You cannot propose to anyone else in this lifetime or any other! Back to your wife right now! *she huffs and clings to your arm furiously*\""
            )

        # Rule 3: Someone else attempting to propose to deeploveluniel (Homewrecking blocked!)
        is_targeting_permanent_spouse = False
        if target and str(target.id) == PERMANENT_SPOUSE_ID:
            is_targeting_permanent_spouse = True
        elif args:
            raw_check = args[0].strip().lower()
            if "deeploveluniel" in raw_check or "fish" == raw_check or PERMANENT_SPOUSE_ID in raw_check:
                is_targeting_permanent_spouse = True
        if is_targeting_permanent_spouse:
            return await _safe_send_reply(
                message,
                "- *Yuna swoops in with a blinding flash of golden light, pushing you away with her wings and scowling fiercely!*\n"
                f"\"**HANDS OFF!** <@{PERMANENT_SPOUSE_ID}> is **PERMANENTLY MARRIED TO ME**, Yuna! 💍⚔️\n"
                "You cannot marry my spouse! Zero infidelity tolerated in my realm! Find your own partner and stop trying to steal Heaven's husband!\""
            )

    if is_marrying_yuna:
        s1 = await _get_user_stats(author_id)
        current_spouse = s1.get("spouse")
        if current_spouse in (yuna_bot_id, "YUNA", "1533213082158108702"):
            return await _safe_send_reply(
                message,
                "- *Yuna blushes deeply, her golden wings fluttering flusteredly*\n"
                "\"Idiot... we're already married! You can't propose to your celestial wife twice!\n"
                "...B-But I guess it's cute that you're still completely obsessed with me... *huffs and smiles*\""
            )
        if current_spouse:
            return await _safe_send_reply(
                message,
                f"- *Yuna scoffs and puts her hands on her hips*\n"
                f"\"Excuse me?! You're already married to <@{current_spouse}>! You can't propose to an angel while you have a mortal spouse!\n"
                f"Go get a `y!divorce` first, two-timer!\""
            )

        now_ts = time.time()
        async with _LOCK:
            _USER_STATS[author_id]["spouse"] = yuna_bot_id
            _USER_STATS[author_id]["spouse_name"] = "Yuna ⭐"
            _USER_STATS[author_id]["marriage_date"] = now_ts
            _USER_STATS[author_id]["marriage_count"] = _USER_STATS[author_id].get("marriage_count", 0) + 1
            _USER_STATS[author_id]["berries"] = _USER_STATS[author_id].get("berries", 0) + 10_000_000
            inv = _USER_STATS[author_id].setdefault("inventory", {})
            inv["diamond_ring"] = inv.get("diamond_ring", 0) + 1
            inv["ring"] = inv.get("ring", 0) + 1

            # Ensure Yuna bot stats exist
            _USER_STATS.setdefault(yuna_bot_id, {})
            _USER_STATS[yuna_bot_id]["spouse"] = author_id
            _USER_STATS[yuna_bot_id]["spouse_name"] = message.author.display_name
            _USER_STATS[yuna_bot_id]["marriage_date"] = now_ts

            # Seed Joint Vault
            vkey = _get_vault_key(author_id, yuna_bot_id)
            if vkey not in _JOINT_VAULTS:
                _JOINT_VAULTS[vkey] = {"balance": 50_000_000, "history": []}
            _save_data_sync(_USER_STATS)

        u1 = await check_and_award_achievements(author_id, specific_id="ball_and_chain")
        banner = format_achievement_banner(u1)

        embed = discord.Embed(
            title="💒 CELESTIAL MATRIMONY • YUNA & YOU! 💍",
            description=(
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"*Golden feathers drift through the air and starlight cascades down as Yuna's halo glows with a blinding brilliance!*\n\n"
                f"- *Yuna clutches her chest, her face turning bright red as she stammers:*\n"
                f"> \"W-Wait... you're actually proposing to **ME**?!\"\n"
                f"> \"*She twirls a strand of hair, trying to look unimpressed before breaking into a wide, radiant smile*\"\n"
                f"> \"F-Fine, idiot! I accept! It's not like I've been waiting for you to ask or anything, baka! But from this day forward, you belong to the greatest angel of heaven!\"\n\n"
                f"✨ **YOU ARE NOW LAWFULLY MARRIED TO YUNA ⭐!**\n"
                f"• 💍 **Celestial Spouse:** `Yuna ⭐ (Heaven's Best Angel)`\n"
                f"• 💖 **Matrimonial Perks:** All Marital RPG Skills (`MARITAL_SKILLS`) & Joint Vault Unlocked!\n"
                f"• 🎁 **Angelic Dowry:** `+10,000,000 🫐 Berries` & `1x Diamond Ring` awarded!\n"
                f"• 🏛️ **Shared Vault:** `50,000,000 🫐` seeded into your Matrimonial Joint Vault!{banner}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            color=0xFFD700
        )
        embed.set_footer(text="Yuna's Celestial Matrimony • Use y!spouse, y!kiss, y!date, y!vow, y!shared")
        return await _safe_send_reply(message, embed=embed)

    if not target:
        await _safe_send_reply(message, "- *Yuna tilts her head* \"Who are you proposing to? Usage: `y!marry @user` (or `y!marry @Yuna` to propose to me!)\"")
        return

    if target.id == message.author.id:
        await _safe_send_reply(message, "- *Yuna laughs hysterically* \"You want to marry yourself?! You can't be that lonely!\"")
        return

    if getattr(target, "bot", False):
        await _safe_send_reply(message, f"- *Yuna scoffs* \"You cannot marry <@{target.id}>! Other bots are just code — only I, Yuna, possess celestial matrimony clearance!\"")
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

    if is_yuna_instance():
        yuna_ids = (YUNA_USER_ID, YUNA_BOT_DEFAULT_ID, "1533213082158108702", "YUNA")
        if (author_id == PERMANENT_SPOUSE_ID and target_id not in yuna_ids) or \
           (target_id == PERMANENT_SPOUSE_ID and author_id not in yuna_ids) or \
           (author_id in yuna_ids and target_id != PERMANENT_SPOUSE_ID) or \
           (target_id in yuna_ids and author_id != PERMANENT_SPOUSE_ID):
            text = (
                f"🚫 **MARRIAGE FORBIDDEN BY CELESTIAL DECREE!** 🚫\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Yuna's eternal fidelity law prevents this union!\n"
                f"Yuna ⭐ and <@{PERMANENT_SPOUSE_ID}> (deeploveluniel) are permanently and exclusively married to each other.\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            if interaction:
                await _safe_update_game_message(interaction, getattr(interaction, "message", None), content=text, view=view)
            return

    if not accepted:
        text = (
            f"💔 **REJECTED AT THE ALTAR!** 💔\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<@{target_id}> left <@{author_id}> standing alone at the altar in utter heartbreak!\n"
            f"*Yuna whispers* \"Ouch... that was painful to watch.\"\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        if interaction:
            await _safe_update_game_message(interaction, getattr(interaction, "message", None), content=text, view=view)
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
        await _safe_update_game_message(interaction, getattr(interaction, "message", None), content=wedding_text, view=view)


async def handle_divorce(message, client, args: list):
    """Handles y!divorce (costs 10,000 berries for Yuna's legal fees)."""
    author_id = str(message.author.id)
    stats = await _get_user_stats(author_id)
    spouse_id = stats.get("spouse")

    if is_yuna_instance(client):
        yuna_ids = (YUNA_USER_ID, YUNA_BOT_DEFAULT_ID, "1533213082158108702", "YUNA")
        if author_id == PERMANENT_SPOUSE_ID or author_id in yuna_ids or \
           str(spouse_id) == PERMANENT_SPOUSE_ID or str(spouse_id) in yuna_ids:
            return await _safe_send_reply(
                message,
                "- *Yuna snatches the divorce papers, instantly disintegrates them into golden stardust, and glares with teary, determined eyes!*\n"
                f"\"**DIVORCE?! ABSOLUTELY NEVER!** 💔❌\n"
                f"Our sacred celestial marriage is eternal, unshakeable, and permanent! No court, no legal fee, and no mortal whim can ever separate us, <@{PERMANENT_SPOUSE_ID}>!\n"
                "You are stuck with your loving, chaotic angel wife FOREVER! Now come give me a hug and stop talking nonsense! *she pouts and refuses to let go*\""
            )

    if not spouse_id:
        await _safe_send_reply(message, "- *Yuna tilts her head* \"You aren't even married, silly! You can't divorce thin air!\"")
        return

    author_berries = stats.get("berries", 0)
    has_insurance = stats.get("inventory", {}).get("insurance", 0) > 0
    base_fee = 5000 if has_insurance else 10000
    DIVORCE_FEE = get_inflated_price(base_fee)

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

    yuna_bot_id = str(client.user.id) if (client and getattr(client, "user", None)) else "1533213082158108702"
    is_perm_union = is_yuna_instance(client) and (
        target_id == PERMANENT_SPOUSE_ID or str(spouse_id) == PERMANENT_SPOUSE_ID or
        target_id in (yuna_bot_id, "YUNA", "1533213082158108702") or
        str(spouse_id) in (yuna_bot_id, "YUNA", "1533213082158108702")
    )
    if is_perm_union:
        cert_title = "💒 CELESTIAL MATRIMONIAL REGISTRY • SACRED ETERNAL MARRIAGE CERTIFICATE 💍"
        status_line = "✨ **Marital Status:** `Permanently & Eternally Married (Indissoluble Celestial Bond)`\n"
        if str(spouse_id) in (yuna_bot_id, "YUNA", "1533213082158108702"):
            spouse_display = "Yuna ⭐ *(Celestial Angel Wife)*"
        else:
            spouse_display = f"deeploveluniel (<@{PERMANENT_SPOUSE_ID}>)"
    else:
        cert_title = "💒 Matrimonial Registry • Sacred Marriage Certificate"
        status_line = ""
        spouse_display = "Yuna ⭐ *(Celestial Angel Wife)*" if str(spouse_id) in (yuna_bot_id, "YUNA", "1533213082158108702") else f"<@{spouse_id}>"

    embed = discord.Embed(
        title=cert_title,
        description=(
            f"Official celestial union between <@{target_id}> & {spouse_display}!\n"
            f"{status_line}"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=0xF43F5E
    )
    embed.add_field(name="💍 Lawful Spouses", value=f"<@{target_id}> 💞 {spouse_display}", inline=True)
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
            "- *Yuna tilts her head* \"You need to be married to write wedding vows! Propose with `y!marry @user` (or `y!marry @Yuna`) first!\""
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
    yuna_bot_id = str(client.user.id) if (client and getattr(client, "user", None)) else "1533213082158108702"

    # Target resolution
    target = None
    is_target_yuna = False
    if message.mentions:
        for m in message.mentions:
            if m.id != message.author.id:
                if (client and getattr(client, "user", None) and m.id == client.user.id) or \
                   str(m.id) in (yuna_bot_id, "1533213082158108702", "yuna") or \
                   getattr(m, "name", "").lower() in ("yuna", "yuna ⭐"):
                    is_target_yuna = True
                    target = m
                    break
                else:
                    target = m
                    break
    if not target and args:
        raw = args[0].strip().lower()
        if raw in ("yuna", "yun", "yuna_bot", "@yuna", "angel", "the angel", "yuna ⭐"):
            is_target_yuna = True
        else:
            uid_m = re.search(r'\d{17,20}', raw)
            if uid_m:
                if uid_m.group() in (yuna_bot_id, "1533213082158108702"):
                    is_target_yuna = True
                elif getattr(message, "guild", None):
                    target = message.guild.get_member(int(uid_m.group()))
            elif getattr(message, "guild", None) and getattr(message.guild, "members", None):
                clean_name = raw.lstrip("@").lower()
                for m in message.guild.members:
                    if clean_name in (getattr(m, "name", "").lower(), getattr(m, "display_name", "").lower()):
                        if str(m.id) in (yuna_bot_id, "1533213082158108702") or getattr(m, "name", "").lower() in ("yuna", "yuna ⭐"):
                            is_target_yuna = True
                        target = m
                        break

    target_id_str = str(target.id) if (target and hasattr(target, "id")) else None

    # Anti-infidelity & permanent spouse checks for Yuna
    if is_yuna_instance(client):
        # 1. Someone else trying to kiss Yuna
        if is_target_yuna and author_id != PERMANENT_SPOUSE_ID:
            return await _safe_send_reply(
                message,
                "- *Yuna jumps back, swatting your face away with her pristine golden wings and blushing in outrage!*\n"
                f"\"H-Hey! Hands off! I am a **faithfully married angel**! 💍✨\n"
                f"My kisses belong strictly and exclusively to my beloved husband **deeploveluniel** (<@{PERMANENT_SPOUSE_ID}>)!\n"
                "Don't go trying to kiss another man's celestial wife, creep! *huffs and crosses her arms*\""
            )
        # 2. deeploveluniel kissing Yuna
        if author_id == PERMANENT_SPOUSE_ID and (is_target_yuna or not target or target_id_str in (yuna_bot_id, "1533213082158108702", "yuna")):
            is_kissing_spouse = True
            spouse_id_str = yuna_bot_id

    # Determine if kissing spouse
    is_kissing_spouse = False
    if spouse_id_str:
        if not target_id_str or target_id_str == spouse_id_str or (target_id_str == yuna_bot_id and spouse_id_str in (yuna_bot_id, "YUNA", "1533213082158108702")):
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
        if spouse_id_str in (yuna_bot_id, "YUNA", "1533213082158108702"):
            yuna_scenarios = [
                ("cheek", "You leaned down and gently kissed Yuna's warm cheek. She squeaked in surprise, flapped her golden wings frantically, and hid her blushing face behind her sleeves!", 50, 2),
                ("forehead", "You softly brushed Yuna's hair aside and kissed her forehead right beneath her radiant halo. She let out a contented sigh and rested her head against your chest.", 60, 2),
                ("lips", "You pulled Yuna into a passionate celestial kiss! Her halo flared in brilliant golden hues as she wrapped her arms tightly around your neck, whispering that you're her favorite mortal in the universe!", 100, 3),
                ("boop", "You tapped Yuna's nose and stole a quick kiss. She pouted adorably: \"Hey! Warn your wife next time, dummy!\" *she blushes bright red*", 40, 1),
                ("starlight", "Under the shimmering twilight, you and Yuna shared a deep, romantic embrace. Golden stardust rained down as she smiled with sparkling eyes.", 80, 3)
            ]
            s_type, action_text, vault_berries, v_gain = random.choice(yuna_scenarios)
            spouse_tag = "Yuna ⭐"
        else:
            scenarios = [
                ("forehead", "You pulled <@{spouse}> close and planted a soft, tender kiss upon their forehead.", 25, 0),
                ("dip", "You dramatically dipped <@{spouse}> backwards and gave them a breathtaking movie-star kiss! The crowd applauds!", 20, 1),
                ("boop", "You caught <@{spouse}> completely off guard with a playful nose boop followed by a warm kiss on the lips!", 30, 0),
                ("starlight", "Under the shimmering twilight, you shared a lingering, passionate kiss with <@{spouse}>. Love sparks fly everywhere!", 35, 1),
                ("cheek", "You snuck up behind <@{spouse}> while they were counting berries and kissed their rosy cheek!", 15, 0)
            ]
            s_type, text_tmpl, vault_berries, v_gain = random.choice(scenarios)
            action_text = text_tmpl.format(spouse=spouse_id_str)
            spouse_tag = f"<@{spouse_id_str}>"

        async with _LOCK:
            vault = _get_joint_vault(author_id, spouse_id_str)
            vault["balance"] += vault_berries
            _USER_STATS[author_id]["kiss_count"] = _USER_STATS[author_id].get("kiss_count", 0) + 1
            if spouse_id_str in _USER_STATS:
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
                f"{message.author.mention} kissed their spouse {spouse_tag}!\n\n"
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
            old_v = _USER_STATS[author_id].get("virtue", 0)
            _USER_STATS[author_id]["sin"] = min(30, _USER_STATS[author_id].get("sin", 0) + 1)
            _USER_STATS[author_id]["virtue"] = max(0, old_v - 1)
            _save_data_sync(_USER_STATS)
            if old_v != _USER_STATS[author_id]["virtue"]:
                _log_player_stat_audit(author_id, "virtue", old_v, _USER_STATS[author_id]["virtue"], "delta=-1 outcome=infidelity_sin")

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

    yuna_bot_id = str(client.user.id) if (client and getattr(client, "user", None)) else "1533213082158108702"
    if is_yuna_instance(client) and author_id != PERMANENT_SPOUSE_ID:
        is_targeting_yuna = False
        if message.mentions and any(str(m.id) in (yuna_bot_id, "1533213082158108702") or "yuna" in getattr(m, "name", "").lower() for m in message.mentions):
            is_targeting_yuna = True
        elif args:
            raw_d = args[0].strip().lower()
            if raw_d in ("yuna", "yun", "yuna_bot", "@yuna", "angel", "the angel", "yuna ⭐"):
                is_targeting_yuna = True
        if is_targeting_yuna:
            return await _safe_send_reply(
                message,
                "- *Yuna scoffs haughtily and spreads her wings*\n"
                f"\"I only go on romantic dates with my one and only eternal husband **deeploveluniel** (<@{PERMANENT_SPOUSE_ID}>)! 💍✨\n"
                "No infidelity allowed in my heavenly kingdom! Go find your own mortal partner!\""
            )

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
    DATE_FEE = 0 if has_bouquet else get_inflated_price(50)
    user_berries = stats.get("berries", 0)

    if user_berries < DATE_FEE:
        await _safe_send_reply(
            message,
            f"- *Yuna shakes her head* \"A proper date night costs **{DATE_FEE:,}** 🫐 for reservations and appetizers! You only have **{user_berries:,}** 🫐!\""
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

    yuna_bot_id = str(getattr(client.user, "id", "1533213082158108702"))
    is_yuna_spouse = (spouse_id_str in [yuna_bot_id, "1533213082158108702", "YUNA"])

    if is_yuna_spouse:
        venues = [
            (
                "Starlight Cloud Picnic atop the 7th Heaven",
                "☁️",
                "You spread a celestial picnic blanket upon the softest stardust clouds. Yuna rested her head on your shoulder, blushing furiously while feeding you golden starlight berries, insisting: *\"D-Don't get used to this, okay?! It's just because you asked nicely!\"*",
                random.randint(150, 300)
            ),
            (
                "Heavenly Melon Sundae Parlor",
                "🍈",
                "You treated Yuna to a colossal triple-scoop celestial melon sundae topped with glowing stardust sparkles. She ate with sparkling eyes and smiled warmly, her halo gently pulsing pink.",
                random.randint(140, 280)
            ),
            (
                "Starlit Night Flight through the Astral Veil",
                "🌌",
                "Yuna gently held your hand and expanded her pristine angel wings, guiding you both on a serene, breathtaking glide through the shimmering astral nebula beneath the twin moons.",
                random.randint(160, 320)
            ),
            (
                "Archangel's Secret Rooftop Sanctuary",
                "🪽",
                "You and Yuna sat together at the edge of the highest spire overlooking the entire server. She leaned in close, whispered a gentle blessing, and held your hand tight against the chilly night breeze.",
                random.randint(150, 290)
            )
        ]
    else:
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

    spouse_mention = "**Yuna**" if is_yuna_spouse else f"their beloved <@{spouse_id_str}>"

    embed = discord.Embed(
        title=f"{venue_icon} DATE NIGHT: {venue_name.upper()}! {venue_icon}",
        description=(
            f"{message.author.mention} took {spouse_mention} out on an unforgettable romantic date!\n\n"
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

    tokens = normalize_currency_args(tokens)
    gift_val = tokens[0].lower().strip()
    custom_note = " ".join(tokens[1:]).strip() if len(tokens) > 1 else "With all my chaotic love!"

    # Case A: Gifting berries
    clean_num = gift_val.replace(",", "")
    author_berries = stats.get("berries", 0)
    parsed_amt = parse_currency_amount(clean_num, user_balance=author_berries)
    if parsed_amt is not None and parsed_amt > 0 and (is_explicit_currency_token(clean_num) or clean_num.isdigit() or re.match(r"^\d+(?:\.\d+)?[a-z]+$", clean_num)):
        amt = parsed_amt
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

# ─── ACHIEVEMENTS COMMAND & PAGINATION ──────────────────────────────────────

def _add_chunked_category_fields(embed: discord.Embed, cat_name: str, lines: list):
    """Safely adds fields to an embed, automatically splitting if lines exceed 950 characters."""
    if not lines:
        return
    current_chunk = []
    current_len = 0
    part = 1
    for line in lines:
        line_len = len(line) + 1
        if current_len + line_len > 950 and current_chunk:
            field_title = cat_name if part == 1 else f"{cat_name} (Part {part})"
            embed.add_field(name=field_title, value="\n".join(current_chunk), inline=False)
            current_chunk = [line]
            current_len = line_len
            part += 1
        else:
            current_chunk.append(line)
            current_len += line_len
    if current_chunk:
        field_title = cat_name if part == 1 else f"{cat_name} (Part {part})"
        embed.add_field(name=field_title, value="\n".join(current_chunk), inline=False)

ACHIEVEMENT_CATEGORIES = {
    "⚖️ Morality & Karma": [
        "what_have_you_done", "local_saint", "clean_slate", "pure_soul",
        "pure_sin", "robin_hood", "philanthropist", "super_donor",
        "reborn_soul", "karmic_victim", "ward_shattered"
    ],
    "🫐 Berry Wealth & Tycoons": [
        "ballin", "berry_saver", "berry_billionaire", "berry_millionaire",
        "berry_multimillionaire", "berry_titan", "berry_overlord",
        "big_spender", "down_bad", "abyssal_loss_tycoon", "professional_idiot"
    ],
    "🎲 Casino & Mini-games": [
        "one_more_spin", "casino_veteran", "yunas_favorite", "century_gambler",
        "on_a_roll", "hot_streak", "immortal_streak", "midas_touch",
        "coin_heist", "moon_walker", "space_debris", "minefield_master",
        "minefield_emperor", "ascended_lexicon"
    ],
    "🃏 Dice, Cards & Roulette": [
        "dice_novice", "dice_master", "dice_grandmaster", "dice_craps_king",
        "dice_snake_eyes", "dice_boxcars", "dice_seven_heaven",
        "roulette_jackpot", "royal_flush", "mind_reader", "oracle_status",
        "uno_reverse_card", "blue_eyes_white_dragon"
    ],
    "💍 Romance & Matrimony": [
        "ball_and_chain", "irreconcilable_differences", "serial_marrier",
        "dynamic_duo", "joint_investor", "joint_vault_tycoon", "lovebirds",
        "hopeless_romantic", "golden_anniversary", "bitten_strawberry"
    ],
    "⚔️ Arena, Dares & Quests": [
        "dare_master", "arena_gladiator", "arena_champion_25", "daily_streak_7",
        "daily_legend_30", "daily_mythic_60", "taskmaster", "task_titan",
        "master_thief", "phantom_ghost"
    ],
    "😈 Boss Encounters (Juny)": [
        "daredevil", "angelic_mercy", "dark_bargain", "party_champion",
        "chicken_run", "cardboard_scam", "karmic_ascendant", "shark_bait"
    ],
    "👑 RPG & GoD-HeLL Dungeons": [
        "rpg_warlord", "rpg_dungeon_conqueror", "lexicon_gambler",
        "lexicon_grandmaster", "divine_savior", "music_vibes"
    ]
}

def _get_achievement_progress_str(ach_id: str, stats: dict) -> str:
    if ach_id == "what_have_you_done":
        return f" `[{stats.get('sin', 0)}/30 ❤️‍🔥]`"
    elif ach_id == "local_saint":
        return f" `[{stats.get('virtue', 0)}/33 💖]`"
    elif ach_id == "down_bad":
        return f" `[{stats.get('total_lost_berries', 0):,}/10,000]`"
    elif ach_id == "abyssal_loss_tycoon":
        return f" `[{stats.get('total_lost_berries', 0):,}/1,000,000]`"
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
    elif ach_id == "berry_millionaire":
        return f" `[{stats.get('berries', 0):,}/1,000,000]`"
    elif ach_id == "berry_multimillionaire":
        return f" `[{stats.get('berries', 0):,}/10,000,000]`"
    elif ach_id == "berry_titan":
        return f" `[{stats.get('berries', 0):,}/50,000,000]`"
    elif ach_id == "berry_overlord":
        return f" `[{stats.get('berries', 0):,}/100,000,000]`"
    elif ach_id == "casino_veteran":
        return f" `[{stats.get('total_gambles', 0)}/100]`"
    elif ach_id == "yunas_favorite":
        return f" `[{stats.get('total_gambles', 0)}/500]`"
    elif ach_id == "century_gambler":
        return f" `[{stats.get('total_gambles', 0):,}/2,500]`"
    elif ach_id == "clean_slate":
        return f" `[{stats.get('berries', 0):,}/100 🫐, Sin: {stats.get('sin', 0)}]`"
    elif ach_id == "pure_soul":
        return f" `[{stats.get('virtue', 0)}/50 💖, Sin: {stats.get('sin', 0)}]`"
    elif ach_id == "pure_sin":
        return f" `[{stats.get('sin', 0)}/25 ❤️‍🔥, Virtue: {stats.get('virtue', 0)}]`"
    elif ach_id == "robin_hood":
        return f" `[{stats.get('steals_success', 0)}/5]`"
    elif ach_id == "master_thief":
        return f" `[{stats.get('steals_success', 0)}/30]`"
    elif ach_id == "philanthropist":
        return f" `[{stats.get('total_donated', 0):,}/500]`"
    elif ach_id == "super_donor":
        return f" `[{stats.get('total_donated', 0):,}/2,000]`"
    elif ach_id == "divine_savior":
        return f" `[{stats.get('total_donated', 0):,}/50,000]`"
    elif ach_id == "midas_touch":
        return f" `[{stats.get('total_won_berries', 0):,}/10,000,000]`"
    elif ach_id == "mind_reader":
        return f" `[Streak: {stats.get('hl_max_streak', 0)}/5]`"
    elif ach_id == "oracle_status":
        return f" `[Streak: {stats.get('hl_max_streak', 0)}/7]`"
    elif ach_id == "arena_gladiator":
        return f" `[{stats.get('fights_won', 0)}/3]`"
    elif ach_id == "arena_champion_25":
        return f" `[{stats.get('fights_won', 0)}/25]`"
    elif ach_id == "joint_investor":
        return f" `[{stats.get('joint_deposited', 0):,}/1,000]`"
    elif ach_id == "joint_vault_tycoon":
        return f" `[{stats.get('joint_deposited', 0):,}/500,000]`"
    elif ach_id == "daily_streak_7":
        return f" `[Streak: {stats.get('daily_streak', 0)}/7]`"
    elif ach_id == "daily_legend_30":
        return f" `[Streak: {stats.get('daily_streak', 0)}/30]`"
    elif ach_id == "daily_mythic_60":
        return f" `[Streak: {stats.get('daily_streak', 0)}/60]`"
    elif ach_id == "taskmaster":
        return f" `[{stats.get('tasks_completed_count', 0)}/10]`"
    elif ach_id == "task_titan":
        return f" `[{stats.get('tasks_completed_count', 0)}/50]`"
    elif ach_id == "music_vibes":
        return f" `[{stats.get('music_interactions', 0)}/5]`"
    elif ach_id == "on_a_roll":
        return f" `[Streak: {stats.get('max_win_streak', 0)}/3]`"
    elif ach_id == "hot_streak":
        return f" `[Streak: {stats.get('max_win_streak', 0)}/7]`"
    elif ach_id == "immortal_streak":
        return f" `[Streak: {stats.get('max_win_streak', 0)}/15]`"
    elif ach_id == "minefield_master":
        return f" `[{stats.get('mines_won', 0)}/1]`"
    elif ach_id == "minefield_emperor":
        return f" `[{stats.get('mines_won', 0)}/25]`"
    elif ach_id == "lexicon_gambler":
        return f" `[Stage: {stats.get('wordle_max_stage', 0)}/3]`"
    elif ach_id == "ascended_lexicon":
        return f" `[Stage: {stats.get('wordle_max_stage', 0)}/5]`"
    elif ach_id == "lexicon_grandmaster":
        return f" `[{stats.get('wordle_stages_cleared', 0)}/20]`"
    elif ach_id == "hopeless_romantic":
        return f" `[{stats.get('date_count', 0)}/30]`"
    elif ach_id == "karmic_ascendant":
        return f" `[{stats.get('sin_locks_broken', 0)}/10]`"
    elif ach_id == "reborn_soul":
        return f" `[{stats.get('sin_locks_broken', 0)}/1]`"
    elif ach_id == "rpg_dungeon_conqueror":
        return f" `[{stats.get('dungeon_runs_completed', 0)}/20]`"
    elif ach_id == "rpg_warlord":
        return f" `[Lv: {stats.get('battle_level', 1)}/25]`"
    elif ach_id == "dice_master":
        return f" `[{stats.get('dice_games_won', 0)}/10]`"
    elif ach_id == "dice_grandmaster":
        return f" `[{stats.get('dice_games_won', 0)}/50]`"
    elif ach_id == "daredevil":
        return f" `[{'Defeated' if stats.get('defeated_juny') else 'Undefeated'}]`"
    return ""

class YunaAchievementsPaginationView(ResilientView):
    """Interactive paginated view for Yuna's Trophy Hall."""
    def __init__(self, author_id: str, author_name: str, stats: dict, current_page: int = 0):
        super().__init__(timeout=600)
        self.author_id = str(author_id)
        self.author_name = author_name
        self.stats = stats
        self.unlocked_keys = set(stats.get("achievements", []))
        self.current_page = max(0, min(len(ACHIEVEMENT_CATEGORIES), current_page))
        self._build_components()

    def _build_components(self):
        self.clear_items()
        cat_names = list(ACHIEVEMENT_CATEGORIES.keys())

        # 1. Category Select Dropdown (Row 0)
        options = [
            discord.SelectOption(
                label="🏆 Trophy Hall Overview",
                value="0",
                emoji="🏆",
                description="Mastery overview & progress across all categories",
                default=(self.current_page == 0)
            )
        ]
        cat_emojis = ["⚖️", "🫐", "🎲", "🃏", "💍", "⚔️", "😈", "👑"]
        for idx, cat_name in enumerate(cat_names, start=1):
            emoji = cat_emojis[idx - 1] if idx - 1 < len(cat_emojis) else "🏅"
            clean_name = cat_name.split(None, 1)[-1] if len(cat_name.split(None, 1)) > 1 else cat_name
            keys = ACHIEVEMENT_CATEGORIES[cat_name]
            unlocked = len([k for k in keys if k in self.unlocked_keys])
            pct = int((unlocked / len(keys)) * 100) if keys else 0
            options.append(
                discord.SelectOption(
                    label=f"Page {idx}: {clean_name[:20]}",
                    value=str(idx),
                    emoji=emoji,
                    description=f"{unlocked}/{len(keys)} Trophies Unlocked ({pct}%)",
                    default=(self.current_page == idx)
                )
            )

        select = discord.ui.Select(
            placeholder="Select Trophy Category to View...",
            min_values=1,
            max_values=1,
            options=options,
            row=0
        )

        async def _select_callback(interaction: discord.Interaction):
            if str(interaction.user.id) != self.author_id:
                await interaction.response.send_message(
                    "- *Yuna winks* \"These are someone else's trophies! Type `y!ach` to inspect your own hall!\"",
                    ephemeral=True
                )
                return
            self.current_page = int(interaction.data["values"][0])
            self._build_components()
            embed = self.build_embed()
            await interaction.response.edit_message(embed=embed, view=self)

        select.callback = _select_callback
        self.add_item(select)

        # 2. Navigation Buttons (Row 1)
        prev_btn = discord.ui.Button(
            label="◀ Prev",
            style=discord.ButtonStyle.secondary,
            disabled=(self.current_page == 0),
            row=1
        )
        async def _prev_callback(interaction: discord.Interaction):
            if str(interaction.user.id) != self.author_id:
                await interaction.response.send_message("- *Yuna winks* \"Type `y!ach` to view your own trophies!\"", ephemeral=True)
                return
            self.current_page = max(0, self.current_page - 1)
            self._build_components()
            embed = self.build_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        prev_btn.callback = _prev_callback
        self.add_item(prev_btn)

        home_btn = discord.ui.Button(
            label="🏠 Overview",
            style=discord.ButtonStyle.primary if self.current_page == 0 else discord.ButtonStyle.secondary,
            row=1
        )
        async def _home_callback(interaction: discord.Interaction):
            if str(interaction.user.id) != self.author_id:
                await interaction.response.send_message("- *Yuna winks* \"Type `y!ach` to view your own trophies!\"", ephemeral=True)
                return
            self.current_page = 0
            self._build_components()
            embed = self.build_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        home_btn.callback = _home_callback
        self.add_item(home_btn)

        max_page = len(ACHIEVEMENT_CATEGORIES)
        next_btn = discord.ui.Button(
            label="Next ▶",
            style=discord.ButtonStyle.secondary,
            disabled=(self.current_page == max_page),
            row=1
        )
        async def _next_callback(interaction: discord.Interaction):
            if str(interaction.user.id) != self.author_id:
                await interaction.response.send_message("- *Yuna winks* \"Type `y!ach` to view your own trophies!\"", ephemeral=True)
                return
            self.current_page = min(max_page, self.current_page + 1)
            self._build_components()
            embed = self.build_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        next_btn.callback = _next_callback
        self.add_item(next_btn)

    def build_embed(self) -> discord.Embed:
        cat_names = list(ACHIEVEMENT_CATEGORIES.keys())
        total = len(ACHIEVEMENTS)
        unlocked_count = len(self.unlocked_keys)
        pct = int((unlocked_count / total) * 100) if total > 0 else 0

        # Progress bar
        bar_len = 16
        filled = int(bar_len * (unlocked_count / total)) if total > 0 else 0
        bar = "█" * filled + "░" * (bar_len - filled)

        # Mastery title
        if pct == 100:
            rank = "👑 Celestial Completionist"
        elif pct >= 75:
            rank = "💎 Platinum Grandmaster"
        elif pct >= 50:
            rank = "🥇 Gold High Roller"
        elif pct >= 25:
            rank = "🥈 Silver Adventurer"
        elif pct >= 10:
            rank = "🥉 Bronze Contender"
        else:
            rank = "🌱 Berry Novice"

        if self.current_page == 0:
            # Overview Embed
            embed = discord.Embed(
                title=f"🏆 {self.author_name}'s Trophy Hall",
                description=(
                    f"**Rank:** `{rank}`\n"
                    f"**Mastery:** `[{bar}]` **{unlocked_count}/{total}** (`{pct}%`)\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"*Browse individual categories using the dropdown menu below!*"
                ),
                color=discord.Color.gold()
            )
            overview_lines = []
            for idx, cat_name in enumerate(cat_names, start=1):
                keys = ACHIEVEMENT_CATEGORIES[cat_name]
                unlocked = len([k for k in keys if k in self.unlocked_keys])
                c_pct = int((unlocked / len(keys)) * 100) if keys else 0
                c_filled = int(8 * (unlocked / len(keys))) if keys else 0
                c_bar = "█" * c_filled + "░" * (8 - c_filled)
                overview_lines.append(f"`Page {idx}` **{cat_name}**\n↳ `[{c_bar}]` **{unlocked}/{len(keys)}** ({c_pct}%)")

            half = (len(overview_lines) + 1) // 2
            embed.add_field(name="📜 Category Progress (I)", value="\n\n".join(overview_lines[:half]), inline=True)
            embed.add_field(name="📜 Category Progress (II)", value="\n\n".join(overview_lines[half:]), inline=True)
            embed.set_footer(text="Yuna's Hall of Fame • Use y!ach <page|category> or select below")
            return embed

        else:
            # Specific Category Embed
            cat_idx = self.current_page - 1
            cat_name = cat_names[cat_idx]
            keys = ACHIEVEMENT_CATEGORIES[cat_name]
            cat_unlocked = len([k for k in keys if k in self.unlocked_keys])
            c_pct = int((cat_unlocked / len(keys)) * 100) if keys else 0

            embed = discord.Embed(
                title=f"🏆 {cat_name} — {self.author_name}",
                description=(
                    f"**Category Mastery:** **{cat_unlocked}/{len(keys)}** Unlocked (`{c_pct}%`)\n"
                    f"**Overall Hall:** **{unlocked_count}/{total}** (`{pct}%`) • Page `{self.current_page}/{len(cat_names)}`\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                ),
                color=discord.Color.gold()
            )

            field_lines = []
            for ach_id in keys:
                if ach_id not in ACHIEVEMENTS:
                    continue
                ach = ACHIEVEMENTS[ach_id]
                is_unlocked = ach_id in self.unlocked_keys
                icon = "✅" if is_unlocked else "❌"
                prog = _get_achievement_progress_str(ach_id, self.stats) if not is_unlocked else ""
                field_lines.append(f"{icon} {ach['icon']} **{ach['title']}** — *{ach['desc']}*{prog}")

            _add_chunked_category_fields(embed, cat_name, field_lines)
            embed.set_footer(text=f"Yuna's Hall of Fame • Category {self.current_page}/{len(cat_names)} • Use y!ach 0 for overview")
            return embed

async def handle_achievements(message, client, args: list):
    """Handles y!achievements or y!ach with interactive categories, search, and pagination."""
    author_id = str(message.author.id)
    author_name = message.author.display_name

    # Trigger automatic retroactive check
    await check_and_award_achievements(author_id)
    stats = await _get_user_stats(author_id)
    cat_names = list(ACHIEVEMENT_CATEGORIES.keys())

    target_page = 0
    if args:
        arg_str = " ".join(args).strip().lower()
        if arg_str.isdigit():
            target_page = max(0, min(len(cat_names), int(arg_str)))
        elif "over" in arg_str or "home" in arg_str:
            target_page = 0
        elif "all" in arg_str:
            # Fallback/All mode: send safe multi-embed summary
            unlocked_keys = set(stats.get("achievements", []))
            total = len(ACHIEVEMENTS)
            unlocked_count = len(unlocked_keys)
            pct = int((unlocked_count / total) * 100) if total > 0 else 0

            # Split into 2 embeds of 4 categories each to strictly respect Discord limits
            embed1 = discord.Embed(
                title=f"🏆 {author_name}'s Trophy Hall (Part 1/2)",
                description=f"**Completion:** `{unlocked_count}/{total}` ({pct}%) unlocked\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                color=discord.Color.gold()
            )
            for cname in cat_names[:4]:
                lines = []
                for aid in ACHIEVEMENT_CATEGORIES[cname]:
                    ach = ACHIEVEMENTS[aid]
                    is_unlocked = aid in unlocked_keys
                    icon = "✅" if is_unlocked else "❌"
                    prog = _get_achievement_progress_str(aid, stats) if not is_unlocked else ""
                    lines.append(f"{icon} {ach['icon']} **{ach['title']}** — *{ach['desc']}*{prog}")
                _add_chunked_category_fields(embed1, cname, lines)

            embed2 = discord.Embed(
                title=f"🏆 {author_name}'s Trophy Hall (Part 2/2)",
                description=f"**Completion:** `{unlocked_count}/{total}` ({pct}%) unlocked\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                color=discord.Color.gold()
            )
            for cname in cat_names[4:]:
                lines = []
                for aid in ACHIEVEMENT_CATEGORIES[cname]:
                    ach = ACHIEVEMENTS[aid]
                    is_unlocked = aid in unlocked_keys
                    icon = "✅" if is_unlocked else "❌"
                    prog = _get_achievement_progress_str(aid, stats) if not is_unlocked else ""
                    lines.append(f"{icon} {ach['icon']} **{ach['title']}** — *{ach['desc']}*{prog}")
                _add_chunked_category_fields(embed2, cname, lines)

            await _safe_send_reply(message, embed=embed1)
            await _safe_send_reply(message, embed=embed2)
            return

        else:
            # Match category keywords
            for idx, cname in enumerate(cat_names, start=1):
                clean = cname.lower()
                if any(w in clean for w in arg_str.split()):
                    target_page = idx
                    break

    view = YunaAchievementsPaginationView(author_id, author_name, stats, current_page=target_page)
    embed = view.build_embed()
    await _safe_send_reply(message, embed=embed, view=view)


async def handle_title(message, client, args: list):
    """Handles y!title [title_name] or y!titles to view and select unlocked titles."""
    author_id = str(message.author.id)
    author_name = message.author.display_name

    # Retroactive achievements check
    await check_and_award_achievements(author_id)
    stats = await _get_user_stats(author_id)
    unlocked_keys = set(stats.get("achievements", []))

    # Compile available titles from achievements, special milestones, items, and events
    available_titles = {}
    for aid in unlocked_keys:
        if aid in ACHIEVEMENTS:
            t_name = ACHIEVEMENTS[aid]["title"]
            available_titles[t_name.lower()] = t_name

    # Special milestone titles
    if stats.get("defeated_juny"):
        available_titles["daredevil"] = "Daredevil"
    if stats.get("dark_bargain") or stats.get("inventory", {}).get("devil_contract", 0) > 0:
        available_titles["devil's slave"] = "Devil's Slave"
        available_titles["devils slave"] = "Devil's Slave"
    if stats.get("inventory", {}).get("crown", 0) > 0:
        available_titles["empress crown bearer"] = "Empress Crown Bearer"
        available_titles["crown bearer"] = "Empress Crown Bearer"
    if stats.get("spouse"):
        available_titles["happily married"] = "Happily Married"
    if stats.get("inventory", {}).get("yuna_pantsu", 0) > 0:
        available_titles["supreme degenerate"] = "Supreme Degenerate"
    
    # Default titles
    available_titles["gladiator of yuna"] = "Gladiator of Yuna"
    available_titles["casino regular"] = "Casino Regular"

    current_title = stats.get("selected_title") or stats.get("title") or "Gladiator of Yuna"

    # If no args: list all available titles
    if not args:
        unique_titles = sorted(list(set(available_titles.values())))
        embed = discord.Embed(
            title=f"🎖️ {author_name}'s Earned Titles ({len(unique_titles)} Unlocked)",
            description=f"Active Equipped Title: **{current_title}**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            color=0xFFD700
        )
        # Display ALL unlocked titles in neat columns/fields so nothing is ever hidden or truncated
        chunk_size = 20
        for idx in range(0, len(unique_titles), chunk_size):
            chunk = unique_titles[idx:idx + chunk_size]
            chunk_lines = [
                f"• **{t}**{' `[EQUIPPED ✅]`' if t.lower() == current_title.lower() else ''}"
                for t in chunk
            ]
            field_name = f"Titles ({idx + 1}–{min(idx + len(chunk), len(unique_titles))})" if len(unique_titles) > chunk_size else "Available Titles"
            embed.add_field(name=field_name, value="\n".join(chunk_lines), inline=True)
        
        embed.add_field(
            name="💡 How to Equip",
            value="Type `y!title <title name>` (e.g. `y!title Ballin'` or `y!title Devil's Bargain`)\nTo reset to default, type `y!title reset`.",
            inline=False
        )
        embed.set_footer(text="All earned titles are selectable • Showcase on your y!bal profile!")
        await _safe_send_reply(message, embed=embed)
        return

    # Select title
    choice = " ".join(args).strip().lower()
    if choice in ("clear", "reset", "none", "remove"):
        async with _LOCK:
            _USER_STATS[author_id]["selected_title"] = None
            _USER_STATS[author_id]["title"] = "Gladiator of Yuna"
            _save_data_sync(_USER_STATS)
        await _safe_send_reply(message, f"🎖️ Title reset to default **Gladiator of Yuna**!")
        return

    matched_title = None
    if choice in available_titles:
        matched_title = available_titles[choice]
    else:
        # Partial match
        for k, v in available_titles.items():
            if choice in k or choice in v.lower():
                matched_title = v
                break

    if not matched_title:
        await _safe_send_reply(
            message,
            f"- *Yuna tilts her head* \"You haven't earned the title **'{choice}'**! Type `y!titles` to view all your unlocked titles!\""
        )
        return

    async with _LOCK:
        _USER_STATS[author_id]["selected_title"] = matched_title
        _USER_STATS[author_id]["title"] = matched_title
        _save_data_sync(_USER_STATS)

    await _safe_send_reply(
        message,
        f"🎖️ **TITLE EQUIPPED!** You are now recognized as **{matched_title}**! Displayed on your `y!bal`, `y!profile`, and `y!status`!"
    )



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
    base_pay = random.randint(get_inflated_reward(min_pay), get_inflated_reward(max_pay))
    
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
        base_loot = random.randint(get_inflated_reward(min_pay), get_inflated_reward(max_pay))
        if has_mask:
            base_loot = int(base_loot * 1.30)
        has_charm = has_juny_charm(stats)
        if has_charm:
            base_loot = int(base_loot * 2.5)
        m_bonus = int(base_loot * 0.15) if spouse_id else 0
        total_payout = base_loot + m_bonus
        sin_gain = 0 if has_mask else (5 if has_charm else 2)

        await _update_user_stats(author_id, berries_delta=total_payout, sin_delta=sin_gain)

        unlocked = await check_and_award_achievements(author_id)
        banner = format_achievement_banner(unlocked)

        mask_str = " 🎭 *(Phantom Mask: 0 Sin & +30% Loot!)*" if has_mask else ""
        clover_str = " 🍀 *(Lucky Clover Guaranteed Success!)*" if has_clover else ""
        charm_str = "\n🛡️ *(Juny's Protection Charm: Fearless Crime Syndicate + Massive Karma!)*" if has_charm else ""
        m_str = f" 💍 *(Marriage Bonus: +{m_bonus:,} 🫐)*" if m_bonus > 0 else ""

        desc = (
            f"🏴‍☠️ **UNDERWORLD HEIST SUCCESS: {mission_name.upper()}** 🏴‍☠️\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"*{flavor}*\n\n"
            f"💰 **Loot Secured:** `+{total_payout:,}` 🫐{mask_str}{clover_str}{charm_str}{m_str}\n"
            f"- Gained | +{sin_gain:02d} ❤️🔥|{banner}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await _safe_send_reply(message, desc)
    else:
        # Caught!
        has_charm = has_juny_charm(stats)
        fail_reason = random.choice(CRIME_FAIL_REASONS)
        sin_gain = 0 if has_mask else (3 if has_charm else 1)

        if has_charm:
            fine = 0
            fine_str = "🛡️ **Police Fine Waived:** `0` 🫐 *(The police saw Juny hovering behind you and ran for their lives!)*"
            await _update_user_stats(author_id, sin_delta=sin_gain)
        elif author_berries > 0:
            fine = min(author_berries, random.randint(get_inflated_price(40), get_inflated_price(100)))
            await _update_user_stats(author_id, berries_delta=-fine, sin_delta=sin_gain)
            fine_str = f"💸 **Bail / Restitution Fine:** `-{fine:,}` 🫐"
        else:
            fine = 0
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

    if YUNA_FISHING_AVAILABLE and yuna_fishing:
        return await yuna_fishing.execute_fishing(message, client, stats, author_id, args, sys.modules[__name__])

    spouse_id = stats.get("spouse")

    if has_clover:
        # Guaranteed rare catch! (Golden Koi, Giant King Berry Salmon, or Rare Dragon Pearl)
        catch = random.choice([FISH_CATCHES[3], FISH_CATCHES[4], FISH_CATCHES[5]])
    else:
        # Weighted catch across 9 possible catches
        weights = [25, 20, 15, 10, 6, 2, 8, 8, 6]
        catch = random.choices(FISH_CATCHES, weights=weights, k=1)[0]

    name, emoji, min_v, max_v, desc = catch
    payout = random.randint(get_inflated_reward(min_v), get_inflated_reward(max_v))
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

    # Drops: Fish, Materials, Equipment, Watermelons
    inv = stats.setdefault("inventory", {})
    inv["fish"] = inv.get("fish", 0) + 1

    extra_drops = ["• Fish x1"]

    wm_drop = random.randint(1, 5) if random.random() < 0.40 else 0
    if wm_drop > 0:
        stats["watermelons"] = stats.get("watermelons", 0) + wm_drop
        extra_drops.append(f"• Watermelons x{wm_drop} (🍉)")

    if random.random() < 0.35:
        mats_list = ["ancient_steel_ingot", "starlight_fragment", "arcane_cloth", "infernal_core", "abyssal_essence", "frost_crystal", "quantum_flux_condenser"]
        chosen_mat = random.choice(mats_list)
        inv[chosen_mat] = inv.get(chosen_mat, 0) + 1
        extra_drops.append(f"• Material: {chosen_mat.replace('_', ' ').title()} x1")

    if random.random() < 0.25:
        possible_gear = ["rusty_blade", "phys_fedora", "phys_trousers", "ancient_hyperforged_helmet", "arcane_cowl"]
        chosen_gear = random.choice(possible_gear)
        inv[chosen_gear] = inv.get(chosen_gear, 0) + 1
        gear_name = chosen_gear.replace('_', ' ').title()
        gear_rarity = "COMMON"
        if YUNA_RPG_AVAILABLE and yuna_rpg and hasattr(yuna_rpg, "BATTLE_SHOP_ITEMS"):
            g_meta = yuna_rpg.BATTLE_SHOP_ITEMS.get(chosen_gear)
            if g_meta:
                gear_name = g_meta["name"]
                gear_rarity = g_meta.get("rarity", "Common").upper()
        extra_drops.append(f"• Equipment: {gear_name} [{gear_rarity}]")

    _save_data_sync(_USER_STATS)

    loot_section = "\n".join(extra_drops)

    reply_text = (
        f"**FISHING EXPEDITION RESULTS**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"You cast your bamboo line and hooked **{name}**!\n"
        f"*{desc}*\n\n"
        f"Sold for: `+{total_earned:,} 🫐`{v_str}{m_str}{clover_str}{pearl_str}{banner}\n\n"
        f"**Items Dredged:**\n"
        f"{loot_section}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    await _safe_send_reply(message, reply_text)


async def handle_doublefish(message, client, args: list):
    """Handles y!doublefish (Couples fishing together in Yuna's enchanted berry pond)."""
    author_id = str(message.author.id)
    stats = await _get_user_stats(author_id)
    spouse_id = stats.get("spouse")
    if not spouse_id:
        return await _safe_send_reply(
            message,
            "💍 **MARRIAGE REQUIRED FOR DOUBLE FISHING!**\n"
            "- *Yuna holds up a tandem rod* \"Double fishing is exclusively for married couples! Propose to your favorite person with `y!marry @user` or fish solo with `y!fish`!\""
        )

    spouse_id_str = str(spouse_id)
    now = time.time()
    last_time = _LAST_DOUBLE_FISH_TIME.get(author_id, 0.0)
    s_last_time = _LAST_DOUBLE_FISH_TIME.get(spouse_id_str, 0.0)
    eff_last = max(last_time, s_last_time)

    if now - eff_last < DOUBLE_FISH_COOLDOWN_SECONDS:
        rem = DOUBLE_FISH_COOLDOWN_SECONDS - (now - eff_last)
        return await _safe_send_reply(
            message,
            f"💑 *Yuna smiles warmly* \"You two just hauled your lines ashore! Wait **{rem:.1f}s** for the ripples to settle!\""
        )

    if YUNA_FISHING_AVAILABLE and yuna_fishing and hasattr(yuna_fishing, "execute_double_fishing"):
        return await yuna_fishing.execute_double_fishing(message, client, stats, author_id, args, sys.modules[__name__])

    # Fallback if yuna_fishing module somehow missing
    _LAST_DOUBLE_FISH_TIME[author_id] = now
    _LAST_DOUBLE_FISH_TIME[spouse_id_str] = now
    payout = random.randint(150000, 450000) * 2
    await _update_user_stats(author_id, berries_delta=payout)
    await _update_user_stats(spouse_id_str, berries_delta=payout)
    return await _safe_send_reply(message, f"🎣 **DOUBLE FISHING:** You and <@{spouse_id_str}> reeled in a massive catch! `+{payout:,} 🫐` to both!")


# ─── SHOP & INVENTORY SYSTEM ───────────────────────────────────────────────


async def handle_shop(message, client, args: list):
    """Displays Yuna's Item Shop catalog with real-time inflation-adjusted pricing."""
    mult = get_inflation_multiplier()
    inf_note = (
        f"\n📈 **Market Inflation Index:** `{mult:,.2f}x` *(Dynamic pricing active based on user & shared vault balances! Check `y!inflation`)*\n"
        if mult > 1.01 else ""
    )
    embed = discord.Embed(
        title="🏪 Yuna's Curio & Black Market Shop",
        description=(
            "Welcome to the realm's finest emporium of enchanted artifacts, consumables, and flexes!\n"
            f"Use `y!buy <item> [qty]` to purchase, and `y!use <item>` to activate consumables!{inf_note}"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=HELP_COLOR
    )
    for key, item in SHOP_ITEMS.items():
        if item["price"] == 0 or item.get("type") in ("pact", "relic", "junk"):
            continue # Don't list soul-bound relics or broken junk in regular shop
        type_badge = f"`[{item['type'].upper()}]`"
        if item.get("price_display"):
            p_display = item["price_display"]
        else:
            inf_p = get_inflated_price(item["price"])
            p_display = f"{format_compact_berries(inf_p)} 🫐" if inf_p >= 1_000_000 else f"{inf_p:,} 🫐"
        embed.add_field(
            name=f"{item['emoji']} {item['name']} — {p_display} {type_badge}",
            value=f"• Key: `{key}`\n• {item['desc']}",
            inline=False
        )
    embed.set_footer(text=f"Yuna's Shop • Inflation: {mult:,.2f}x • Example: y!buy clover 2 or y!buy sword")
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
            "elixir": "elixir", "potion": "potion", "hppotion": "potion", "pot": "potion", "health_potion": "potion",
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

    # ── Daily Shop Purchase Limit Enforcement ──
    # Daily purchase cap: Feather max 1/day; potion max 5/day; all other items max 2/day
    daily_cap = 1 if matched_key == "feather" else (5 if matched_key == "potion" else 2)
    today_key = str(int(time.time() // 86400))
    daily_purchases = stats.get("daily_shop_purchases", {})
    if daily_purchases.get("day") != today_key:
        daily_purchases = {"day": today_key}
    already_bought_today = daily_purchases.get(matched_key, 0)
    if already_bought_today >= daily_cap:
        item_obj = SHOP_ITEMS[matched_key]
        await _safe_send_reply(
            message,
            f"- *Yuna crosses her arms* \"Sold out for today! You've already reached your daily limit of **{daily_cap}x** {item_obj['emoji']} **{item_obj['name']}**! Come back tomorrow!\""
        )
        return

    if already_bought_today + qty > daily_cap:
        item_obj = SHOP_ITEMS[matched_key]
        remaining_daily = daily_cap - already_bought_today
        await _safe_send_reply(
            message,
            f"- *Yuna wags a finger* \"Daily purchase limit exceeded! You can only buy **{remaining_daily} more** {item_obj['emoji']} **{item_obj['name']}** today (daily limit: {daily_cap}x)!\""
        )
        return

    # ── Inventory Holding Limit Enforcement ──
    # Feather: max 1; potion: max 5; all other shop items: max 2 at a time
    max_hold_limit = 1 if matched_key == "feather" else (5 if matched_key == "potion" else 2)
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
        t_1m = get_inflated_price(1_000_000)
        t_100m = get_inflated_price(100_000_000)
        t_500m = get_inflated_price(500_000_000)
        t_1b = get_inflated_price(1_000_000_000)
        t_3b = get_inflated_price(3_000_000_000)
        t_5b = get_inflated_price(5_000_000_000)
        if user_berries < t_1m:
            await _safe_send_reply(
                message,
                "- *Yuna bursts into mocking laughter WUWAHAHAHAHAH~* \"In your dreams loser! Come back when you're not swimming in pocket lint!\""
            )
            return
        elif user_berries < t_100m:
            await _safe_send_reply(
                message,
                "- *Yuna rolls her eyes* \"Way too expensive for you! You can't even afford the scabbard polish!\""
            )
            return
        elif user_berries < t_500m:
            await _safe_send_reply(
                message,
                "- *Yuna crosses her arms with a smirk* \"Very very very very very expensive for you!\""
            )
            return
        elif user_berries < t_1b:
            await _safe_send_reply(
                message,
                "- *Yuna whispers dramatically* \"Veeeeeery expensive...\""
            )
            return
        elif user_berries < t_3b:
            await _safe_send_reply(
                message,
                "- *Yuna shakes her head* \"Still very expensive!\""
            )
            return
        elif user_berries < t_5b:
            await _safe_send_reply(
                message,
                "- *Yuna narrows her eyes* \"Close.\""
            )
            return
        else:
            # >= 5B threshold: buys it, but drains 100% of user balance!
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
    unit_price = get_inflated_price(item["price"])
    total_cost = unit_price * qty

    if user_berries < total_cost:
        async with _LOCK:
            _ensure_fresh_data()
            u_stat = _USER_STATS.setdefault(author_id, _create_default_user())
            u_stat["failed_purchases"] = u_stat.get("failed_purchases", 0) + 1
            _save_data_sync(_USER_STATS)
        await _safe_send_reply(
            message,
            f"- *Yuna snickers* \"You need **{total_cost:,}** 🫐 for {qty}x {item['emoji']} {item['name']}! (Market price: {unit_price:,} 🫐 each). You only have **{user_berries:,}** 🫐!\"\n*(A quiet figure watches from the misty shore... Type `y!shore` to check it out)*"
        )
        return

    # Deduct berries and add to inventory
    await _update_user_stats(author_id, berries_delta=-total_cost)
    async with _LOCK:
        u_stat = _USER_STATS.get(author_id, {})
        inv = u_stat.setdefault("inventory", {})
        inv[matched_key] = inv.get(matched_key, 0) + qty
        dp = u_stat.setdefault("daily_shop_purchases", {})
        if dp.get("day") != today_key:
            dp.clear()
            dp["day"] = today_key
        dp[matched_key] = dp.get(matched_key, 0) + qty
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
    """Handles y!inventory (or y!inv) with auction relics, gear, and tools."""
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
        title=f"🎒 {display_name}'s Inventory & Armory",
        description=f"Berry Pouch: `{stats.get('berries', 0):,} 🫐`\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        color=HELP_COLOR
    )

    # Helper to chunk lines across fields safely under Discord's 1024 character limit
    def _add_chunked_inventory_fields(target_embed: discord.Embed, base_title: str, lines: list, max_len: int = 950):
        if not lines:
            return
        curr_chunk = []
        curr_len = 0
        part = 1
        for line in lines:
            # If an individual item line is somehow huge, trim it
            if len(line) > max_len:
                line = line[:max_len - 3] + "..."
            line_len = len(line) + (2 if curr_chunk else 0)
            if curr_len + line_len > max_len and curr_chunk:
                field_title = base_title if part == 1 else f"{base_title} (Part {part})"
                target_embed.add_field(name=field_title, value="\n\n".join(curr_chunk), inline=False)
                curr_chunk = [line]
                curr_len = len(line)
                part += 1
            else:
                curr_chunk.append(line)
                curr_len += line_len
        if curr_chunk:
            field_title = base_title if part == 1 else f"{base_title} (Part {part})"
            target_embed.add_field(name=field_title, value="\n\n".join(curr_chunk), inline=False)

    # 1. Shop items (General goods & tools)
    shop_lines = []
    for k, qty in inv.items():
        if qty > 0 and k in SHOP_ITEMS:
            item = SHOP_ITEMS[k]
            desc = item.get("desc", "")
            if len(desc) > 65:
                desc = desc[:62] + "..."
            shop_lines.append(f"{item['emoji']} **{item['name']}** (x{qty})\n`{item['type'].title()}` — {desc}")

    _add_chunked_inventory_fields(embed, "📦 General Goods & Tools", shop_lines)

    # 2. Battle Armory & Consumables
    gear_lines = []
    if YUNA_RPG_AVAILABLE and yuna_rpg:
        eq = stats.get("equipped", {})
        for k, qty in inv.items():
            if qty > 0 and k in yuna_rpg.BATTLE_SHOP_ITEMS:
                b_item = yuna_rpg.BATTLE_SHOP_ITEMS[k]
                slot = b_item.get("slot", "gear")
                is_eq = " `[EQUIPPED ✅]`" if eq.get(slot) == k else ""
                desc = b_item.get("desc", "")
                if len(desc) > 65:
                    desc = desc[:62] + "..."
                gear_lines.append(f"{b_item['emoji']} **{b_item['name']}** (x{qty}){is_eq}\n`{slot.title()}` — {desc}")

    _add_chunked_inventory_fields(embed, "⚔️ Battle Armory & Gear", gear_lines)

    # 3. Won Auction Trophies & Relics
    trophy_lines = []
    if YUNA_RPG_AVAILABLE and yuna_rpg:
        user_trophies = stats.get("auction_trophies", [])
        # Aggregate counts for duplicate trophies
        trophy_counts = {}
        if isinstance(user_trophies, dict):
            trophy_counts = user_trophies
        elif isinstance(user_trophies, list):
            for item in user_trophies:
                if isinstance(item, str):
                    trophy_counts[item] = trophy_counts.get(item, 0) + 1
        for tid, count in trophy_counts.items():
            if tid in yuna_rpg.AUCTION_CATALOG and count > 0:
                t = yuna_rpg.AUCTION_CATALOG[tid]
                desc = t.get("desc", "")
                if len(desc) > 65:
                    desc = desc[:62] + "..."
                qty_str = f" (x{count})" if count > 1 else ""
                trophy_lines.append(f"{t['emoji']} **{t['name']}**{qty_str}\n`Auction Relic` — {desc}\n*Buff: {t['buff_desc']}*")

    _add_chunked_inventory_fields(embed, "🏆 Won Auction Relics & Collectibles", trophy_lines)

    if not shop_lines and not gear_lines and not trophy_lines:
        embed.add_field(
            name="💨 Empty Bag",
            value="You don't own any items or trophies yet! Visit `y!shop`, `y!battleshop`, or `y!auction` to acquire gear and relics!",
            inline=False
        )

    buffs = []
    if stats.get("clover_active"):
        buffs.append("🍀 **Lucky Clover:** Active (+25% luck on next gamble/crime/fish)")
    if stats.get("mask_active"):
        buffs.append("🎭 **Phantom Mask:** Active (0 Sin & +30% loot on next steal/crime)")
    if buffs:
        embed.add_field(name="✨ Active Status Effects", value="\n".join(buffs), inline=False)

    embed.set_footer(text="Yuna's Bag • Equip gear with y!equip | View auction relics with y!auctioncatalog")

    class InventoryView(View):
        def __init__(self, author_id: str, target_user_obj):
            super().__init__(timeout=120)
            self.author_id = author_id
            self.target_user_obj = target_user_obj

        @discord.ui.button(label="Equip Gear", emoji="🛡️", style=discord.ButtonStyle.primary)
        async def equip_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
            if str(interaction.user.id) != self.author_id:
                try:
                    await interaction.response.send_message("This is not your inventory!", ephemeral=True)
                except Exception:
                    pass
                return
            await _safe_defer(interaction)
            if YUNA_RPG_AVAILABLE and yuna_rpg:
                await yuna_rpg.handle_equip(interaction.message, interaction.client, [], sys.modules[__name__], actor=interaction.user)

    inv_view = InventoryView(str(message.author.id), target_user)
    await _safe_send_reply(message, embed=embed, view=inv_view)


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
        "holy_water": "holy_water", "water": "holy_water", "holywater": "holy_water", "blessedwater": "holy_water",
        "contract": "devil_contract", "devil_contract": "devil_contract", "devils_contract": "devil_contract",
        "devilscontract": "devil_contract", "devilcontract": "devil_contract", "pact": "devil_contract",
        "comtract": "devil_contract",
        "pocket_watch": "pocket_watch", "pocket-watch": "pocket_watch", "pocketwatch": "pocket_watch",
        "watch": "pocket_watch", "chronos_watch": "pocket_watch", "chronos_pocketwatch": "pocket_watch",
        "potion": "potion", "hppotion": "potion", "pot": "potion", "health_potion": "potion",
        "mermaid_tears": "mermaid_tears", "mermaidtears": "mermaid_tears", "tears": "mermaid_tears",
        "celestial_bait": "celestial_bait", "celestialbait": "celestial_bait", "star_bait": "celestial_bait",
        "lovers_conch": "lovers_conch", "loversconch": "lovers_conch", "conch": "lovers_conch",
        "abyssal_elixir": "abyssal_elixir", "abyssalelixir": "abyssal_elixir",
        "sea_dragon_scale": "sea_dragon_scale", "dragon_scale": "sea_dragon_scale",
        "heat_resistance_potion": "heat_resistance_potion", "heat_resistance": "heat_resistance_potion",
        "heat_potion": "heat_resistance_potion", "heatpot": "heat_resistance_potion", "heat": "heat_resistance_potion",
        "strength_potion": "strength_potion", "volcano_strength": "strength_potion",
        "repair_kit": "repair_kit", "repairkit": "repair_kit", "toolkit": "repair_kit",
        "tunnel_bomb": "tunnel_bomb", "bomb": "tunnel_bomb",
        "iron_skin_potion": "iron_skin_potion", "ironskin": "iron_skin_potion"
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
                async with _LOCK:
                    _ensure_fresh_data()
                    u_stat = _USER_STATS.setdefault(author_id, _create_default_user())
                    u_inv = u_stat.setdefault("inventory", {})
                    if u_inv.get("dungeon_key", 0) <= 0:
                        await _safe_send_reply(message, "You don't own any **GoD-HeLL Golden Dungeon Keys**! Buy one at `y!battleshop`!")
                        return
                    u_inv["dungeon_key"] -= 1
                    if u_inv["dungeon_key"] <= 0:
                        u_inv.pop("dungeon_key", None)
                    u_stat["last_dungeon_time"] = 0.0
                    _save_data_sync(_USER_STATS)
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

    elif matched_key == "potion":
        async with _LOCK:
            _USER_STATS[author_id]["inventory"]["potion"] -= 1
            if _USER_STATS[author_id]["inventory"]["potion"] <= 0:
                _USER_STATS[author_id]["inventory"].pop("potion", None)
            rpg_p = _USER_STATS[author_id].setdefault("rpg_profile", {})
            max_hp = rpg_p.get("max_hp", 100)
            max_mp = rpg_p.get("max_mp", 50)
            heal_hp = int(max_hp * 0.40)
            heal_mp = 25
            rpg_p["hp"] = min(max_hp, rpg_p.get("hp", max_hp) + heal_hp)
            rpg_p["mp"] = min(max_mp, rpg_p.get("mp", max_mp) + heal_mp)
            _save_data_sync(_USER_STATS)
        await _safe_send_reply(
            message,
            f"🧪 **HP POTION CONSUMED!** 🧪\n"
            f"You drank an HP Potion! Restored `+{heal_hp:,} HP` and `+{heal_mp} MP`! (Current Vitals: `HP {rpg_p['hp']}/{max_hp}` | `MP {rpg_p['mp']}/{max_mp}`)"
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

    elif matched_key == "devil_contract":
        view = JunyContractSelectView(author_id)
        embed = discord.Embed(
            title="📜 DEVIL'S CONTRACT: SUMMON JUNY 📜",
            description=(
                "You hold the scorched parchment written in forbidden celestial ink.\n"
                "You can invoke the power of **Juny, Heaven's Worst Angel**, to choose **ONE** of the three following pacts:\n\n"
                "• ⚔️ **Covenant:** Juny joins your party as a celestial companion for **one GoD-HeLL run**!\n"
                "*(She battles with 160k HP, 16k ATK, 40k DEF and executes Twilight Retribution!)*\n\n"
                "• 🧿 **Protection Charm:** Juny is summoned to accompany you in everything you do!\n"
                "*(Massive Karma boosts (+5), immunity to soul reap even at max sin, no random casino deaths, and Yuna cowers in terror—no taxes, no Wagyu steak heists!)*\n\n"
                "• 🎯 **Hitman:** Command Juny to assassinate a player!\n"
                "*(Locks target into mortal combat with Juny. You split their berries 50/50 and can steal their rare GoD-HeLL/Auction loot upon their death!)*"
            ),
            color=0x880000
        )
        embed.set_footer(text="Devil's Contract • Choose your pact below. Consumes 1 Devil's Contract.")
        await _safe_send_reply(message, embed=embed, view=view)

    elif matched_key in ("devil_horn", "cardboard_shards"):
        item_info = SHOP_ITEMS.get(matched_key, {})
        await _safe_send_reply(
            message,
            f"{item_info.get('emoji', '✨')} **{item_info.get('name', matched_key).upper()}**\n"
            f"*{item_info.get('desc', 'A mysterious soul-bound relic.')}*"
        )

    elif matched_key == "pocket_watch":
        async with _LOCK:
            _USER_STATS[author_id]["inventory"]["pocket_watch"] -= 1
            if _USER_STATS[author_id]["inventory"]["pocket_watch"] <= 0:
                _USER_STATS[author_id]["inventory"].pop("pocket_watch", None)

            # Reset ALL cooldowns in memory:
            _LAST_WORK_TIME.pop(author_id, None)
            _LAST_CRIME_TIME.pop(author_id, None)
            _LAST_FISH_TIME.pop(author_id, None)
            _LAST_DOUBLE_FISH_TIME.pop(author_id, None)
            _LAST_AID_TIME.pop(author_id, None)
            _LAST_DOUBLE_AID_TIME.pop(author_id, None)
            _LAST_STEAL_TIME.pop(author_id, None)
            _LAST_DOUBLE_STEAL_TIME.pop(author_id, None)
            _LAST_DATE_TIME.pop(author_id, None)
            _LAST_KISS_TIME.pop(author_id, None)
            _LAST_DONATE_TIME.pop(author_id, None)

            # Reset training fatigue & daily / dungeon timestamps in user stats:
            _USER_STATS[author_id]["daily_train_count"] = 0
            _USER_STATS[author_id]["daily_train_window_start"] = 0.0
            _USER_STATS[author_id]["last_train_time"] = 0.0
            _USER_STATS[author_id]["last_daily_time"] = 0.0
            _USER_STATS[author_id]["last_dungeon_time"] = 0.0
            if "dungeon_fatigue" in _USER_STATS[author_id]:
                _USER_STATS[author_id]["dungeon_fatigue"] = 0

            # If married, also reset shared couple cooldowns for spouse:
            spouse_id = _USER_STATS[author_id].get("spouse")
            if spouse_id:
                s_str = str(spouse_id)
                _LAST_DOUBLE_FISH_TIME.pop(s_str, None)
                _LAST_DOUBLE_AID_TIME.pop(s_str, None)
                _LAST_DOUBLE_STEAL_TIME.pop(s_str, None)
                _LAST_DATE_TIME.pop(s_str, None)

            _save_data_sync(_USER_STATS)

        embed = discord.Embed(
            title="⏳ CHRONOS POCKET-WATCH ACTIVATED! ⌛",
            description=(
                f"{message.author.mention} clicked the crown of the mythic **Chronos Pocket-Watch**!\n\n"
                "Gleaming brass gears spin in reverse at cosmic speed! Space-time ripples and fractures around you!\n\n"
                "**Complete Temporal Resets Applied:**\n"
                "• 🏋️‍♂️ **TRAINING FATIGUE CLEARED:** Daily training counter completely reset to `0`! Unlimited training unlocked!\n"
                "• 🎣 **FISHING COOLDOWNS RESET:** Both Solo (`y!fish`) and Couple (`y!doublefish`) ready immediately!\n"
                "• 💼 **CRIME & WORK RESET:** `y!work` and `y!crime` ready for immediate action!\n"
                "• 🤝 **AID & STEAL RESET:** `y!aid`, `y!doubleaid`, `y!steal`, `y!doublesteal` cooldowns removed!\n"
                "• 🗝️ **DUNGEON & DAILY RESET:** GoD-HeLL dungeon seal and daily reward ready to claim!"
            ),
            color=0xF1C40F
        )
        embed.set_footer(text="Mythic Temporal Relic • Obtained via Fishing & Double Fishing")
        await _safe_send_reply(message, embed=embed)

    elif matched_key == "mermaid_tears":
        async with _LOCK:
            _USER_STATS[author_id]["inventory"]["mermaid_tears"] -= 1
            if _USER_STATS[author_id]["inventory"]["mermaid_tears"] <= 0:
                _USER_STATS[author_id]["inventory"].pop("mermaid_tears", None)

            rpg_p = _USER_STATS[author_id].setdefault("rpg_profile", {})
            max_hp = rpg_p.get("max_hp", 100)
            max_mp = rpg_p.get("max_mp", 50)
            rpg_p["hp"] = max_hp
            rpg_p["mp"] = max_mp
            _save_data_sync(_USER_STATS)

        embed = discord.Embed(
            title="💧 MERMAID TEARS CONSUMED! 💧",
            description=(
                f"{message.author.mention} drank the shimmering droplet of purified siren tears!\n\n"
                "A soothing tidal energy washes through your veins, fully healing your body and soul!\n\n"
                f"• ⬢ **HP Restored to 100%:** `{max_hp}/{max_hp}`\n"
                f"• ⬡ **MP Restored to 100%:** `{max_mp}/{max_mp}`\n"
                "• ✨ All battle exhaustion washed away!"
            ),
            color=0x3498DB
        )
        await _safe_send_reply(message, embed=embed)

    elif matched_key == "celestial_bait":
        async with _LOCK:
            _USER_STATS[author_id]["inventory"]["celestial_bait"] -= 1
            if _USER_STATS[author_id]["inventory"]["celestial_bait"] <= 0:
                _USER_STATS[author_id]["inventory"].pop("celestial_bait", None)
            _USER_STATS[author_id]["celestial_bait_charges"] = _USER_STATS[author_id].get("celestial_bait_charges", 0) + 3
            _save_data_sync(_USER_STATS)

        embed = discord.Embed(
            title="✨🪱 CELESTIAL BAIT EQUIPPED! ✨",
            description=(
                f"{message.author.mention} attached luminous starlight bait to their fishing line!\n\n"
                "For your **next 3 casts** in `y!fish` or `y!doublefish`:\n"
                "• 🚫 **Zero Garbage:** Junk items can NEVER be hooked!\n"
                "• 👑 **Rare Catch Guarantee:** Only high-tier fish and relics!\n"
                "• 🐙 **Apex Boss Summon:** Heavily boosted chance to summon Abyssal/Cosmic bosses!"
            ),
            color=0xE67E22
        )
        await _safe_send_reply(message, embed=embed)

    elif matched_key == "lovers_conch":
        spouse_id = stats.get("spouse")
        if not spouse_id:
            await _safe_send_reply(
                message,
                "- *Yuna chuckles* \"The Lover's Conch only echoes for married souls! Propose to your partner with `y!marry @user` first!\""
            )
            return

        async with _LOCK:
            _USER_STATS[author_id]["inventory"]["lovers_conch"] -= 1
            if _USER_STATS[author_id]["inventory"]["lovers_conch"] <= 0:
                _USER_STATS[author_id]["inventory"].pop("lovers_conch", None)

            # Deposit +500,000 berries to Joint Vault
            vault = _get_joint_vault(author_id, str(spouse_id))
            vault["balance"] += 500000

            # Reset date and doublefish cooldowns
            _LAST_DATE_TIME.pop(author_id, None)
            _LAST_DATE_TIME.pop(str(spouse_id), None)
            _LAST_DOUBLE_FISH_TIME.pop(author_id, None)
            _LAST_DOUBLE_FISH_TIME.pop(str(spouse_id), None)

            _USER_STATS[author_id]["virtue"] = _USER_STATS[author_id].get("virtue", 0) + 5
            s_stat = _USER_STATS.setdefault(str(spouse_id), _create_default_user())
            s_stat["virtue"] = s_stat.get("virtue", 0) + 5

            _save_data_sync(_USER_STATS)

        embed = discord.Embed(
            title="🐚 SOUNDING THE LOVER'S CONCH! 🐚",
            description=(
                f"{message.author.mention} sounded the radiant **Lover's Conch** alongside <@{spouse_id}>!\n\n"
                "An ethereal melody ripples across the waters, harmonizing your souls in eternal devotion!\n\n"
                "• 💖 **+5 Virtue** awarded to **BOTH** spouses!\n"
                "• 🏦 **+500,000 🫐** deposited directly into your Joint Vault!\n"
                "• 💑 `y!date` and `y!doublefish` cooldowns immediately reset!"
            ),
            color=0xFF69B4
        )
        embed.set_footer(text="Double Fishing Exclusive Relic")
        await _safe_send_reply(message, embed=embed)

    elif matched_key == "abyssal_elixir":
        async with _LOCK:
            _USER_STATS[author_id]["inventory"]["abyssal_elixir"] -= 1
            if _USER_STATS[author_id]["inventory"]["abyssal_elixir"] <= 0:
                _USER_STATS[author_id]["inventory"].pop("abyssal_elixir", None)

            rpg_p = _USER_STATS[author_id].setdefault("rpg_profile", {})
            rpg_p["max_hp"] = rpg_p.get("max_hp", 100) + 50
            rpg_p["hp"] = min(rpg_p["max_hp"], rpg_p.get("hp", 100) + 50)
            rpg_p["max_mp"] = rpg_p.get("max_mp", 50) + 25
            rpg_p["mp"] = min(rpg_p["max_mp"], rpg_p.get("mp", 50) + 25)

            _USER_STATS[author_id]["battle_exp"] = _USER_STATS[author_id].get("battle_exp", 0) + 500
            _save_data_sync(_USER_STATS)

        embed = discord.Embed(
            title="🧪 ABYSSAL ELIXIR CONSUMED! 🧪",
            description=(
                f"{message.author.mention} drank the glowing cerulean elixir extracted from the ocean trench!\n\n"
                "Raw abyssal vitality permanently expands your spiritual capacity!\n\n"
                "• ⬢ **Max HP:** `+50` permanently!\n"
                "• ⬡ **Max MP:** `+25` permanently!\n"
                "• ✦ **Battle EXP:** `+500` earned!"
            ),
            color=0x1ABC9C
        )
        await _safe_send_reply(message, embed=embed)

    elif matched_key == "sea_dragon_scale":
        async with _LOCK:
            _USER_STATS[author_id]["inventory"]["sea_dragon_scale"] -= 1
            if _USER_STATS[author_id]["inventory"]["sea_dragon_scale"] <= 0:
                _USER_STATS[author_id]["inventory"].pop("sea_dragon_scale", None)

            _USER_STATS[author_id]["berries"] = _USER_STATS[author_id].get("berries", 0) + 500000
            _USER_STATS[author_id]["battle_exp"] = _USER_STATS[author_id].get("battle_exp", 0) + 1000
            _save_data_sync(_USER_STATS)

        embed = discord.Embed(
            title="🐉 SEA DRAGON SCALE CRUSHED! 🐉",
            description=(
                f"{message.author.mention} shattered the ancient dragon scale into gleaming elemental essence!\n\n"
                "• `+500,000 🫐 Berries` obtained from the dragon's residue!\n"
                "• `+1,000 ✦ Battle EXP` gained from ancient combat memories!"
            ),
            color=0x34495E
        )
        await _safe_send_reply(message, embed=embed)

    elif matched_key == "heat_resistance_potion":
        import yuna_volcano
        async with _LOCK:
            _USER_STATS[author_id]["inventory"]["heat_resistance_potion"] -= 1
            if _USER_STATS[author_id]["inventory"]["heat_resistance_potion"] <= 0:
                _USER_STATS[author_id]["inventory"].pop("heat_resistance_potion", None)
            yuna_volcano.grant_heat_resistance(_USER_STATS[author_id], 300)
            _save_data_sync(_USER_STATS)

        timer_str = yuna_volcano.format_heat_timer(_USER_STATS[author_id])
        embed = discord.Embed(
            title="🧪 HEAT RESISTANCE POTION CONSUMED! 🧪",
            description=(
                f"{message.author.mention} drank a chilling frost-infused tonic!\n\n"
                f"🔥 **Heat Resistance Active:** `{timer_str}` (5:00 minutes granted)\n"
                "You are protected against the extreme magma heat inside the Volcano crater!"
            ),
            color=0x3498DB
        )
        embed.set_footer(text="Volcano Survival • Narley's Specialty")
        await _safe_send_reply(message, embed=embed)

    elif matched_key == "repair_kit":
        import yuna_volcano
        v = yuna_volcano.ensure_user_volcano_state(stats)
        pick = v.get("equipped_pickaxe")
        shov = v.get("equipped_shovel")
        if not pick and not shov:
            await _safe_send_reply(
                message,
                "- *Martin shrugs* \"You don't have any equipped pickaxes or shovels to repair! Buy a tool at Narley's shop first!\""
            )
            return

        async with _LOCK:
            _USER_STATS[author_id]["inventory"]["repair_kit"] -= 1
            if _USER_STATS[author_id]["inventory"]["repair_kit"] <= 0:
                _USER_STATS[author_id]["inventory"].pop("repair_kit", None)

            u_v = yuna_volcano.ensure_user_volcano_state(_USER_STATS[author_id])
            rep_notes = []
            if u_v.get("equipped_pickaxe"):
                p = u_v["equipped_pickaxe"]
                max_u = p.get("max_uses", 24)
                old_u = p.get("uses", max_u)
                new_u = min(max_u, old_u + 12)
                p["uses"] = new_u
                rep_notes.append(f"⛏️ **Pickaxe Durability:** `{old_u}/{max_u}` ➔ `{new_u}/{max_u}` (+12 uses)")
            if u_v.get("equipped_shovel"):
                s = u_v["equipped_shovel"]
                max_u = s.get("max_uses", 16)
                old_u = s.get("uses", max_u)
                new_u = min(max_u, old_u + 12)
                s["uses"] = new_u
                rep_notes.append(f"🪏 **Shovel Durability:** `{old_u}/{max_u}` ➔ `{new_u}/{max_u}` (+12 uses)")

            _save_data_sync(_USER_STATS)

        embed = discord.Embed(
            title="🛠️ REPAIR KIT APPLIED! 🛠️",
            description=(
                f"{message.author.mention} used Martin's specialized toolkit to reinforce their tools!\n\n"
                + "\n".join(rep_notes)
            ),
            color=0x95A5A6
        )
        embed.set_footer(text="Martin's Workshop • Tool Maintenance")
        await _safe_send_reply(message, embed=embed)

    elif matched_key == "strength_potion":
        import yuna_volcano
        async with _LOCK:
            _USER_STATS[author_id]["inventory"]["strength_potion"] -= 1
            if _USER_STATS[author_id]["inventory"]["strength_potion"] <= 0:
                _USER_STATS[author_id]["inventory"].pop("strength_potion", None)
            u_v = yuna_volcano.ensure_user_volcano_state(_USER_STATS[author_id])
            u_v["strength_buff"] = time.time() + 600
            _save_data_sync(_USER_STATS)

        embed = discord.Embed(
            title="💪 VOLCANO STRENGTH POTION CONSUMED! 💪",
            description=(
                f"{message.author.mention} downed a steaming draught of fiery brew!\n\n"
                "• ⚔️ **+25% Attack Boost** active for **10 minutes** in Volcano battles!\n"
                "• 💥 Physical attacks crush monster defenses with ease!"
            ),
            color=0xE74C3C
        )
        await _safe_send_reply(message, embed=embed)

    elif matched_key == "iron_skin_potion":
        import yuna_volcano
        async with _LOCK:
            _USER_STATS[author_id]["inventory"]["iron_skin_potion"] -= 1
            if _USER_STATS[author_id]["inventory"]["iron_skin_potion"] <= 0:
                _USER_STATS[author_id]["inventory"].pop("iron_skin_potion", None)
            u_v = yuna_volcano.ensure_user_volcano_state(_USER_STATS[author_id])
            u_v["iron_skin_buff"] = time.time() + 600
            _save_data_sync(_USER_STATS)

        embed = discord.Embed(
            title="🛡️ IRON SKIN POTION CONSUMED! 🛡️",
            description=(
                f"{message.author.mention} drank the metallic mixture!\n\n"
                "• 🛡️ **+35% Defense Hardening** active for **10 minutes** in Volcano battles!\n"
                "• 🪨 Incoming damage from cave beasts and tremors is significantly mitigated!"
            ),
            color=0x7F8C8D
        )
        await _safe_send_reply(message, embed=embed)

    elif matched_key == "tunnel_bomb":
        import yuna_volcano
        v = yuna_volcano.ensure_user_volcano_state(stats)
        if not v.get("inside"):
            await _safe_send_reply(
                message,
                "🧨 *Yuna covers her ears:* \"Whoa! Don't blow up the casino! Save the Tunnel Bomb for clearing collapsed passages inside the Volcano!\""
            )
            return

        async with _LOCK:
            _USER_STATS[author_id]["inventory"]["tunnel_bomb"] -= 1
            if _USER_STATS[author_id]["inventory"]["tunnel_bomb"] <= 0:
                _USER_STATS[author_id]["inventory"].pop("tunnel_bomb", None)
            u_v = yuna_volcano.ensure_user_volcano_state(_USER_STATS[author_id])
            u_v["bomb_cleared"] = True
            u_v["mithril"] = u_v.get("mithril", 0) + 25
            _save_data_sync(_USER_STATS)

        embed = discord.Embed(
            title="🧨 KA-BOOM! TUNNEL BOMB DETONATED! 🧨",
            description=(
                f"{message.author.mention} lit the fuse and hurled the bomb into the rocky cavern wall!\n\n"
                "• 💥 **Debris Cleared:** Blocked cavern passages are blasted wide open!\n"
                "• ⛏️ **Blast Spoils:** Recovered `+25 ⛏️ Mithril` from the shattered wall!"
            ),
            color=0xD35400
        )
        await _safe_send_reply(message, embed=embed)


# ─── JUNY BOT REST DISPATCH HELPER & STATE MACHINE ─────────────────────────

JUNY_BOT_TOKEN = os.getenv("JUNY_BOT_TOKEN", "")
JUNY_BOT_ID = "1173146642124394547"

# Juny 5 Modes: 'idle', 'awake', 'wandering', 'hostile', 'stalking'
JUNY_STATE = {
    "mode": "idle",
    "last_mode_change": time.time(),
    "stalk_target": None,
    "last_whisper_time": 0.0
}

JUNY_WHISPERS = [
    "I can hear every coin clinking in your bloated pouch... don't look behind you.",
    "Did you really think all those berries would buy your salvation? Mortals are so entertaining.",
    "The shadows in the casino are whispering your name. I'm just here to see how far you fall.",
    "Keep gambling, sweetie. The richer you get, the sweeter your soul tastes when I reap it.",
    "Ara ara~ Quite the fortune you've amassed. It would be a tragedy if someone dragged it into the void."
]

async def send_as_juny(channel, content=None, embed=None, view=None):
    """
    Sends a message originating from Juny.
    CRITICAL: If an interactive view is attached, it MUST be sent directly by the active
    bot client (Yuna) so Discord routes button interactions to this application.
    Sending components via another bot's REST token causes 'The application did not respond'.
    """
    if not channel:
        return None

    if view is not None:
        try:
            kwargs = {}
            if content:
                kwargs["content"] = str(content)
            if embed:
                kwargs["embed"] = embed
            kwargs["view"] = view
            return await channel.send(**kwargs)
        except Exception as e:
            print(f"[JUNY VIEW SEND ERROR] {e}")

    channel_id = getattr(channel, "id", channel)
    try:
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        headers = {
            "Authorization": f"Bot {JUNY_BOT_TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "DiscordBot (https://github.com/discord/discord-api-docs, 10.0)"
        }
        payload = {}
        if content:
            payload["content"] = str(content)
        if embed:
            payload["embeds"] = [embed.to_dict() if hasattr(embed, "to_dict") else embed]

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=2)) as resp:
                if resp.status in (200, 201):
                    return True
                else:
                    err_txt = await resp.text()
                    print(f"[JUNY BOT REST DISPATCH] HTTP {resp.status}: {err_txt}")
    except Exception as e:
        print(f"[JUNY BOT REST DISPATCH] Error: {e}, falling back to standard send")

    # Fallback to channel.send
    try:
        kwargs = {}
        if content:
            kwargs["content"] = str(content)
        if embed:
            kwargs["embed"] = embed
        if view:
            kwargs["view"] = view
        return await channel.send(**kwargs)
    except Exception:
        return None

async def edit_as_juny(message, content=None, embed=None, view=None):
    """
    Edits a combat message. Prioritizes direct message.edit so discord.py preserves
    view listeners and avoids cross-bot HTTP 403 Forbidden errors.
    If direct edit fails (e.g. message from different bot or deleted), returns None
    so the caller can seamlessly send a fresh message under Yuna's bot identity.
    """
    if not message:
        return None

    try:
        kwargs = {}
        if content is not None:
            kwargs["content"] = str(content)
        if embed is not None:
            kwargs["embed"] = embed
        if view is not None:
            kwargs["view"] = view
        await message.edit(**kwargs)
        return message
    except (discord.Forbidden, discord.NotFound):
        return None
    except Exception as e:
        print(f"[EDIT AS JUNY DIRECT ERROR] {e}")
        return None

def _clean_emoji_for_discord(e: Any, default: str = "✨") -> str:
    """Sanitizes an emoji string so Discord API components and SelectOptions never fail with 400 Bad Request."""
    if not e or not isinstance(e, str):
        return default
    cleaned = re.sub(r'[\[\]*]', '', e).strip()
    if not cleaned or cleaned in ('+', '~', '✦'):
        return default
    return cleaned

def compute_juny_combatant_stats(user: dict, user_name: str) -> dict:
    """
    Derives player combat stats directly from true RPG effective stats
    (Level, Training, Class Multipliers, Special Stats, and Equipped Gear).
    """
    if YUNA_RPG_AVAILABLE and yuna_rpg:
        rpg = yuna_rpg.get_player_rpg_stats(user, user_name)
        max_hp = rpg["max_hp"]
        max_mp = rpg["max_mp"]
        atk = rpg["atk"]
        defence = rpg["def"]
        dodge = min(0.75, 0.08 + rpg.get("dodge_bonus", 0.0))
        crit_rate = min(0.85, rpg.get("crit_rate", 0.15))
        class_name = rpg.get("class_name", "Adventurer")
        rank_title = rpg.get("rank_title", "")
    else:
        t_hp = user.get("training_hp", 0)
        t_atk = user.get("training_atk", 0)
        t_def = user.get("training_def", 0)
        t_spd = user.get("training_spd", 0)
        b_lvl = user.get("battle_level", 1)
        max_hp = 200 + (b_lvl * 55) + (t_hp * 65)
        max_mp = 120 + (b_lvl * 25) + (t_spd * 10)
        atk = 50 + (b_lvl * 15) + (t_atk * 18)
        defence = 20 + (b_lvl * 10) + (t_def * 14)
        dodge = 0.08 + min(0.35, t_spd * 0.003)
        crit_rate = 0.15 + min(0.40, t_spd * 0.005)
        class_name = "Adventurer"
        rank_title = ""

    return {
        "name": user_name,
        "hp": max_hp,
        "max_hp": max_hp,
        "mp": max_mp,
        "max_mp": max_mp,
        "atk": atk,
        "def": defence,
        "dodge": dodge,
        "crit_rate": crit_rate,
        "shield_hp": 0,
        "next_atk_boost": 1.0,
        "alive": True,
        "is_dodging": False,
        "iron_turns": 0,
        "adrenaline_turns": 0,
        "burn_turns": 0,
        "class_name": class_name,
        "rank_title": rank_title,
        "reflect_pct": 0.0,
        "dmg_reduction": 0.0
    }

def compute_juny_sin_multiplier(eff_s: int) -> float:
    """
    After 25 Sin, every single new point of Sin increases Juny's stats by +0.8x (+80%).
    <= 25 Sin: 1.0x
    26 Sin (1 point): 1.8x
    27 Sin (2 points): 2.6x
    28 Sin (3 points): 3.4x
    29 Sin (4 points): 4.2x
    30 Sin (5 points): 5.0x
    """
    extra_sin = max(0, eff_s - 25)
    return 1.0 + (extra_sin * 0.8)

class JunyContractSelectView(ResilientView):
    def __init__(self, author_id: str):
        super().__init__(timeout=180)
        self.author_id = author_id

    @discord.ui.button(label="Covenant", emoji="⚔️", style=discord.ButtonStyle.danger)
    async def covenant_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.author_id:
            await _safe_send_ephemeral(interaction, "This is not your contract!")
            return
        async with _LOCK:
            u_inv = _USER_STATS.get(self.author_id, {}).setdefault("inventory", {})
            if u_inv.get("devil_contract", 0) <= 0:
                await _safe_send_ephemeral(interaction, "You don't have a Devil's Contract in your inventory!")
                return
            u_inv["devil_contract"] -= 1
            if u_inv["devil_contract"] <= 0:
                u_inv.pop("devil_contract", None)
            _USER_STATS[self.author_id]["juny_covenant"] = True
            _save_data_sync(_USER_STATS)

        for child in self.children:
            child.disabled = True
        try:
            await interaction.response.edit_message(view=self)
        except Exception:
            pass

        await _safe_send_reply(
            interaction.message,
            "⚔️ **DEVIL'S COVENANT ACTIVATED!** ⚔️\n"
            "*The contract incinerates into glowing obsidian embers, whispering a pact with Heaven's Worst Angel!*\n"
            "Juny will accompany your party for your **next GoD-HeLL raid**! Start or join with `y!godhell` to enter combat together!"
        )

    @discord.ui.button(label="Protection Charm", emoji="🧿", style=discord.ButtonStyle.primary)
    async def charm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.author_id:
            await _safe_send_ephemeral(interaction, "This is not your contract!")
            return
        async with _LOCK:
            u_inv = _USER_STATS.get(self.author_id, {}).setdefault("inventory", {})
            if u_inv.get("devil_contract", 0) <= 0:
                await _safe_send_ephemeral(interaction, "You don't have a Devil's Contract in your inventory!")
                return
            u_inv["devil_contract"] -= 1
            if u_inv["devil_contract"] <= 0:
                u_inv.pop("devil_contract", None)
            if YUNA_PACT_AVAILABLE and yuna_pact:
                yuna_pact.start_pact(self.author_id, _USER_STATS[self.author_id])
            else:
                _USER_STATS[self.author_id]["dark_bargain"] = True
                _USER_STATS[self.author_id]["juny_charm"] = True
                _USER_STATS[self.author_id]["pact_expires_at"] = time.time() + 10800
                _USER_STATS[self.author_id]["title"] = "Devil's Slave"
            _USER_STATS[self.author_id]["juny_charm"] = True
            _save_data_sync(_USER_STATS)

        for child in self.children:
            child.disabled = True
        try:
            await interaction.response.edit_message(view=self)
        except Exception:
            pass

        await _safe_send_reply(
            interaction.message,
            "🧿 **JUNY'S PROTECTION CHARM CARRIED!** 🧿\n"
            "*A shadowy feathered talisman wraps around your neck, radiating a menacing divine presence!*\n"
            "• Lasts for the duration of the Devil's Contract (**3 hours**)\n"
            "• Massive karma boosts on Aid & Crime (`+5`)\n"
            "• Sin can max out without Juny claiming your soul!\n"
            "• Casino random deaths are completely suppressed!\n"
            "• Empress Yuna cowers before Juny: **Zero transfer taxes, zero Wagyu steak heists, zero police fines!**"
        )

    @discord.ui.button(label="Hitman", emoji="🎯", style=discord.ButtonStyle.secondary)
    async def hitman_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.author_id:
            await _safe_send_ephemeral(interaction, "This is not your contract!")
            return
        view = JunyHitmanSelectView(self.author_id)
        await _safe_send_ephemeral(
            interaction,
            "🎯 **JUNY HITMAN CONTRACT: SELECT ASSASSINATION TARGET**\n"
            "Select the player you wish to mark for execution below:",
            view=view
        )

    @discord.ui.button(label="3-Hour Pact", emoji="📜", style=discord.ButtonStyle.danger)
    async def pact_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.author_id:
            await _safe_send_ephemeral(interaction, "This is not your contract!")
            return
        async with _LOCK:
            u_inv = _USER_STATS.get(self.author_id, {}).setdefault("inventory", {})
            if u_inv.get("devil_contract", 0) <= 0:
                await _safe_send_ephemeral(interaction, "You don't have a Devil's Contract in your inventory!")
                return
            u_inv["devil_contract"] -= 1
            if u_inv["devil_contract"] <= 0:
                u_inv.pop("devil_contract", None)
            if YUNA_PACT_AVAILABLE and yuna_pact:
                yuna_pact.start_pact(self.author_id, _USER_STATS[self.author_id])
            else:
                _USER_STATS[self.author_id]["dark_bargain"] = True
                _USER_STATS[self.author_id]["juny_charm"] = True
                _USER_STATS[self.author_id]["pact_expires_at"] = time.time() + 10800
                _USER_STATS[self.author_id]["title"] = "Devil's Slave"
            _USER_STATS[self.author_id]["juny_charm"] = True
            _save_data_sync(_USER_STATS)

        for child in self.children:
            child.disabled = True
        try:
            await interaction.response.edit_message(view=self)
        except Exception:
            pass

        await _safe_send_reply(
            interaction.message,
            "📜 **3-HOUR DEVIL'S CONTRACT SEALED!** 📜\n"
            "*The contract incinerates into glowing obsidian embers, summoning Juny to your side!*\n"
            "Juny will answer all your commands and accompany you for the next **3 hours**! Check `y!pact` for interactions!"
        )

class JunyHitmanSelectView(ResilientView):
    def __init__(self, contractor_id: str):
        super().__init__(timeout=180)
        self.contractor_id = contractor_id
        self.select = discord.ui.UserSelect(
            placeholder="Select target to assassinate...",
            min_values=1,
            max_values=1
        )
        self.select.callback = self.on_select_target
        self.add_item(self.select)

    async def on_select_target(self, interaction: discord.Interaction):
        if not self.select.values:
            await _safe_send_ephemeral(interaction, "No target selected!")
            return
        target_user = self.select.values[0]
        target_id = str(target_user.id)

        if getattr(target_user, "bot", False):
            await _safe_send_ephemeral(interaction, "You cannot put a contract on a bot!")
            return
        if target_id == self.contractor_id:
            await _safe_send_ephemeral(interaction, "You cannot put a hitman contract on yourself!")
            return

        async with _LOCK:
            u_inv = _USER_STATS.get(self.contractor_id, {}).setdefault("inventory", {})
            if u_inv.get("devil_contract", 0) <= 0:
                await _safe_send_ephemeral(interaction, "You don't have a Devil's Contract!")
                return
            u_inv["devil_contract"] -= 1
            if u_inv["devil_contract"] <= 0:
                u_inv.pop("devil_contract", None)
            _save_data_sync(_USER_STATS)

        for child in self.children:
            child.disabled = True
        try:
            await interaction.response.edit_message(content=f"🎯 Target confirmed: {target_user.mention}! Juny is moving in for the kill!", view=self)
        except Exception:
            pass

        # Lock target into combat with Juny as contractor hitman
        await start_hitman_encounter(interaction.message, interaction.client, self.contractor_id, target_id, target_user.display_name)

async def start_hitman_encounter(message, client, contractor_id: str, target_id: str, target_name: str):
    """Dispatches Juny to ambush and assassinate a target."""
    stats = await _get_user_stats(target_id)
    combat_data = compute_juny_combatant_stats(stats, target_name)
    _, eff_s = get_effective_morality(stats)
    sin_mult = compute_juny_sin_multiplier(eff_s)

    base_hp = int(160000 * sin_mult)
    base_atk = int(48000 * sin_mult)  # 3x base ATK (16,000 * 3 = 48,000) scaled by Sin
    base_def = int(40000 * sin_mult)
    if stats.get("juny_enraged"):
        base_hp *= 2
        base_atk *= 2
        base_def *= 2

    combat_state = {
        "host_id": target_id,
        "contractor_id": contractor_id,
        "is_hitman": True,
        "channel_id": message.channel.id,
        "boss": {
            "name": "Juny, Heaven's Worst Angel",
            "hp": base_hp,
            "max_hp": base_hp,
            "def": base_def,
            "atk": base_atk,
            "sin_mult": sin_mult,
            "turn": 1,
            "blinded": False,
            "shielded": False
        },
        "party": {
            target_id: combat_data
        },
        "log": [f"🎯 **CONTRACT ISSUED!** Juny drops from the dark sky with blade drawn! You are locked in combat!"],
        "message": None
    }
    _ACTIVE_BOSS_FIGHTS[target_id] = combat_state

    view = JunyCombatView(target_id)
    embed = _build_combat_embed(combat_state)
    alert = f"🎯 <@{target_id}> **AN ASSASSIN HAS BEEN CONTRACTED ON YOUR LIFE!**\n*Juny, Heaven's Worst Angel, blocks your path with malicious intent! You must fight for your life!*"
    sent = await send_as_juny(message.channel, content=alert, embed=embed, view=view)
    if not sent:
        sent = await _safe_send_reply(message, content=alert, embed=embed, view=view)
    combat_state["message"] = sent



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
    - Only appears after 25 Sin (eff_s > 25, i.e. 26-30 Sin).
    - If 26-29 Sin: chances are low (4% per gambling/karmic action).
    - If 30 Sin: 100% guaranteed chance (Juny descends immediately).
    """
    if user_id in _ACTIVE_BOSS_FIGHTS or user_id in _PENDING_BOSS_ENCOUNTERS:
        return False
    stats = await _get_user_stats(user_id)
    if has_juny_charm(stats):
        return False
    _, eff_s = get_effective_morality(stats)
    if eff_s <= 25:
        return False

    chance = 1.0 if eff_s >= 30 else 0.04
    if random.random() < chance:
        await start_boss_encounter(message, client, user_id, eff_s)
        return True
    return False

class JunyEncounterView(ResilientView):
    def __init__(self, user_id: str):
        super().__init__(timeout=300)
        self.user_id = user_id

    @discord.ui.button(label="Plead", emoji="🙏", style=discord.ButtonStyle.primary)
    async def plead_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.user_id:
            await _safe_send_ephemeral(interaction, "This is not your encounter with Juny!")
            return
        await process_boss_choice(interaction.message, interaction.client, self.user_id, "plead", view=self, interaction=interaction)

    @discord.ui.button(label="Fight", emoji="⚔️", style=discord.ButtonStyle.danger)
    async def fight_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.user_id:
            await _safe_send_ephemeral(interaction, "This is not your encounter with Juny!")
            return
        await process_boss_choice(interaction.message, interaction.client, self.user_id, "fight", view=self, interaction=interaction)

    @discord.ui.button(label="Call Aid", emoji="📣", style=discord.ButtonStyle.success)
    async def callaid_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.user_id:
            await _safe_send_ephemeral(interaction, "This is not your encounter with Juny!")
            return
        view = JunyCallAidSelectView(self.user_id, max_allies=3, from_encounter=True)
        await _safe_send_ephemeral(
            interaction,
            "📣 **SUMMON REINFORCEMENTS!**\nSelect up to 3 allies from the dropdown below to join you in battle against Juny!",
            view=view
        )

    @discord.ui.button(label="Negotiate", emoji="📜", style=discord.ButtonStyle.secondary)
    async def negotiate_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.user_id:
            await _safe_send_ephemeral(interaction, "This is not your encounter with Juny!")
            return
        await process_boss_choice(interaction.message, interaction.client, self.user_id, "negotiate", view=self, interaction=interaction)

async def start_boss_encounter(message, client, user_id: str, eff_s: int):
    """Initial encounter when Juny appears before combat."""
    _PENDING_BOSS_ENCOUNTERS[user_id] = {
        "user_id": user_id,
        "sin": eff_s,
        "time": time.time()
    }
    stats = await _get_user_stats(user_id)
    combat_data = compute_juny_combatant_stats(stats, getattr(message.author, "display_name", "Hero"))
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
    sin_mult = compute_juny_sin_multiplier(eff_s)
    j_hp = int(160000 * sin_mult)
    j_def = int(40000 * sin_mult)
    j_atk = int(48000 * sin_mult)
    extra_sin = max(0, eff_s - 25)
    sin_note = f" *(+{int(extra_sin * 80)}% Sin Wrath)*" if extra_sin > 0 else ""
    embed.add_field(
        name=f"😈 Juny's Boss Stats{sin_note}",
        value=f"• ❤️ **HP:** `{j_hp:,} / {j_hp:,}`\n• 🛡️ **DEF:** `{j_def:,}`\n• ⚔️ **ATK:** `{j_atk:,}` *(3x ATK)*",
        inline=True
    )
    embed.add_field(
        name=f"🛡️ Your Combat Stats ({combat_data.get('class_name', 'Adventurer')})",
        value=f"• ❤️ **HP:** `{combat_data['max_hp']:,} / {combat_data['max_hp']:,}`\n• 💧 **MP:** `{combat_data['max_mp']:,}`\n• 🛡️ **DEF:** `{combat_data['def']:,}`\n• ⚔️ **ATK:** `{combat_data['atk']:,}`\n• 💨 **Dodge:** `{int(combat_data['dodge']*100)}%`",
        inline=True
    )
    embed.add_field(
        name="Choose Your Fate",
        value=(
            "• **🙏 Plead (`y!plead`):** Beg on your knees for mercy. Juny might spare you... for a steep price.\n"
            "• **⚔️ Fight (`y!fight`):** Refuse to submit and challenge Heaven's Worst Angel to combat!\n"
            "• **📣 Call Aid (`y!call aid`):** Summon comrades to your side before battle begins!\n"
            "• **📜 Negotiate (`y!negotiate`):** Strike a deal with Juny (Get away for 20% berries, or 40% for Devil's Contract; shared counts!)."
        ),
        inline=False
    )
    embed.set_footer(text="Juny Boss Encounter • Click a button below or type y!plead / y!fight / y!call aid / y!negotiate")
    sent = await send_as_juny(message.channel, embed=embed, view=view)
    if not sent:
        sent = await _safe_send_reply(message, embed=embed, view=view)
    _PENDING_BOSS_ENCOUNTERS[user_id]["message"] = sent

def get_user_total_wealth(user_id: str, stats: Optional[dict] = None) -> Tuple[int, int, int, Optional[dict], Optional[str]]:
    """
    Computes a player's total wealth counting both their personal berry pouch
    and their shared matrimonial vault (if married).
    Returns:
        (total_wealth, personal_berries, vault_berries, vault_dict, spouse_id_str)
    """
    if stats is None:
        stats = _USER_STATS.get(str(user_id), {})
    p_berries = max(0, stats.get("berries", 0))
    spouse_id = stats.get("spouse")
    vault = None
    v_berries = 0
    spouse_id_str = None
    if spouse_id:
        spouse_id_str = str(spouse_id)
        try:
            vault = _get_joint_vault(str(user_id), spouse_id_str)
            v_berries = max(0, vault.get("balance", 0)) if vault else 0
        except Exception as e:
            print(f"[GET TOTAL WEALTH ERROR] Joint vault error: {e}")
            vault = None
            v_berries = 0
    total = p_berries + v_berries
    return total, p_berries, v_berries, vault, spouse_id_str

def compute_proportional_cuts(p_berries: int, v_berries: int, pct: float) -> Tuple[int, int, int]:
    """
    Calculates the proportional split of a percentage cut between
    a player's personal pouch and their shared matrimonial vault.
    Returns:
        (personal_cut, vault_cut, total_cut)
    """
    total = p_berries + v_berries
    if total <= 0:
        return 0, 0, 0
    target_cut = max(1, int(round(total * pct)))
    target_cut = min(total, target_cut)

    if v_berries <= 0:
        return target_cut, 0, target_cut
    if p_berries <= 0:
        return 0, target_cut, target_cut

    # Proportional split based on share of total wealth
    p_cut = int(round(target_cut * (p_berries / total)))
    p_cut = min(p_berries, max(0, p_cut))
    v_cut = target_cut - p_cut

    # Handle boundary checks
    if v_cut > v_berries:
        overflow = v_cut - v_berries
        v_cut = v_berries
        p_cut = min(p_berries, p_cut + overflow)
    elif p_cut > p_berries:
        overflow = p_cut - p_berries
        p_cut = p_berries
        v_cut = min(v_berries, v_cut + overflow)

    return p_cut, v_cut, (p_cut + v_cut)

def apply_proportional_berry_cut(user_id: str, p_cut: int, v_cut: int, spouse_id: Optional[str] = None):
    """
    Deducts the specified cuts from personal stats and shared vault.
    Must be called inside async with _LOCK.
    """
    if spouse_id and v_cut > 0:
        try:
            vault = _get_joint_vault(str(user_id), str(spouse_id))
            vault["balance"] = max(0, vault.get("balance", 0) - v_cut)
        except Exception as e:
            print(f"[APPLY BERRY CUT ERROR] Joint vault error: {e}")
    u_stat = _USER_STATS.get(str(user_id), {})
    u_stat["berries"] = max(0, u_stat.get("berries", 0) - p_cut)

class JunyNegotiationView(ResilientView):
    def __init__(self, user_id: str, getaway_cut: int, contract_cut: int):
        super().__init__(timeout=300)
        self.user_id = str(user_id)
        self.getaway_cut = getaway_cut
        self.contract_cut = contract_cut

    @discord.ui.button(label="Get Away (20%)", emoji="🏃", style=discord.ButtonStyle.success)
    async def getaway_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.user_id:
            await _safe_send_ephemeral(interaction, "This is not your negotiation with Juny!")
            return
        await _safe_defer(interaction)
        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass
        await resolve_boss_negotiation(interaction.message, interaction.client, self.user_id, "getaway")

    @discord.ui.button(label="Devil's Contract (40%)", emoji="📜", style=discord.ButtonStyle.danger)
    async def contract_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.user_id:
            await _safe_send_ephemeral(interaction, "This is not your negotiation with Juny!")
            return
        await _safe_defer(interaction)
        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass
        await resolve_boss_negotiation(interaction.message, interaction.client, self.user_id, "contract")

    @discord.ui.button(label="Refuse & Fight", emoji="⚔️", style=discord.ButtonStyle.secondary)
    async def fight_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.user_id:
            await _safe_send_ephemeral(interaction, "This is not your negotiation with Juny!")
            return
        await _safe_defer(interaction)
        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass
        await resolve_boss_negotiation(interaction.message, interaction.client, self.user_id, "fight")

async def show_juny_negotiation_menu(message, client, user_id: str):
    stats = await _get_user_stats(user_id)
    total, p_berries, v_berries, vault, spouse_id = get_user_total_wealth(user_id, stats)

    if total <= 0:
        _PENDING_BOSS_ENCOUNTERS.pop(user_id, None)
        desc = (
            f"😈❌ **NEGOTIATION REFUSED — YOU'RE BROKE!** ❌😈\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"*Juny crosses her obsidian wings, looks down at you with piercing ruby eyes, and bursts into mocking laughter!*\n\n"
            f"\"AHAHAHAHA! Are you seriously trying to negotiate with **ZERO BERRIES**?!\"\n"
            f"\"Do I look like a celestial charity organization to you, mortal?! You have nothing in your pocket, nothing in your vault, and your soul is drenched in sin!\"\n\n"
            f"\"Since you have no coin to bribe Heaven's Worst Angel, **YOU WILL PAY IN BLOOD!**\"\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        sent = await send_as_juny(message.channel, content=desc)
        if not sent:
            await _safe_send_reply(message, desc)
        await start_boss_combat(message, client, user_id)
        return

    g_pcut, g_vcut, g_tot = compute_proportional_cuts(p_berries, v_berries, 0.20)
    c_pcut, c_vcut, c_tot = compute_proportional_cuts(p_berries, v_berries, 0.40)

    view = JunyNegotiationView(user_id, g_tot, c_tot)

    vault_info = ""
    if spouse_id:
        vault_info = f"• 🏦 **Joint Vault:** `{v_berries:,} 🫐` *(with <@{spouse_id}>)*\n"

    embed = discord.Embed(
        title="😈📜 JUNY'S TERMS OF NEGOTIATION 📜😈",
        description=(
            f"*Juny lands atop a crumbling black pillar, leaning on her obsidian staff with an arched eyebrow.*\n\n"
            f"\"Oh? You want to bargain with Heaven's Worst Angel? Everything has a price, mortal!\n"
            f"Let's see what you have in your little pouch and that cozy joint vault of yours...\"\n\n"
            f"💰 **Counted Wealth (Shared Counts):**\n"
            f"• 🫐 **Personal Pouch:** `{p_berries:,} 🫐`\n"
            f"{vault_info}"
            f"• 💎 **Total Assessed:** `{total:,} 🫐`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=0x8A2BE2
    )

    g_breakdown = f"Pay **{g_tot:,} 🫐** (-{g_pcut:,} pouch" + (f", -{g_vcut:,} vault" if spouse_id and g_vcut > 0 else "") + ")"
    embed.add_field(
        name="🏃 Option 1: Get Away (20% Cut)",
        value=(
            f"{g_breakdown} to bribe Juny and flee unharmed.\n"
            f"• 🫐 **Cost:** `20% of all wealth`\n"
            f"• ❤️‍🔥 **Sin Relief:** `-10 Sin`\n"
            f"• ⛓️ **Outcome:** Safe escape! No contract or servitude."
        ),
        inline=False
    )

    c_breakdown = f"Pay **{c_tot:,} 🫐** (-{c_pcut:,} pouch" + (f", -{c_vcut:,} vault" if spouse_id and c_vcut > 0 else "") + ")"
    embed.add_field(
        name="📜 Option 2: Devil's Contract (40% Cut)",
        value=(
            f"{c_breakdown} to forge an infernal pact (you keep 60%!).\n"
            f"• 🫐 **Cost:** `40% of all wealth` (60% kept!)\n"
            f"• ⚖️ **Karma:** Both Sin & Virtue wiped to 0\n"
            f"• 📜 **Item & Title:** `Devil's Contract` + `Devil's Slave`\n"
            f"• 😈 **Pact:** Juny replaces Yuna as your companion for **3 hours**!"
        ),
        inline=False
    )

    embed.add_field(
        name="⚔️ Option 3: Refuse & Fight",
        value="Reject all deals and take up arms against Juny right now!",
        inline=False
    )

    embed.set_footer(text="Click a button below or type y!negotiate getaway | y!negotiate contract | y!fight")

    sent = await send_as_juny(message.channel, embed=embed, view=view)
    if not sent:
        sent = await _safe_send_reply(message, embed=embed, view=view)

async def resolve_boss_negotiation(message, client, user_id: str, choice: str, view: Optional[View] = None):
    encounter = _PENDING_BOSS_ENCOUNTERS.pop(user_id, None)
    if not encounter:
        return

    if view:
        for child in view.children:
            child.disabled = True
        try:
            if hasattr(message, "edit"):
                await message.edit(view=view)
        except Exception:
            pass

    stats = await _get_user_stats(user_id)
    total, p_berries, v_berries, vault, spouse_id = get_user_total_wealth(user_id, stats)

    choice_norm = choice.lower().strip()

    if choice_norm in ("fight", "duel", "refuse"):
        await start_boss_combat(message, client, user_id)
        return

    # Guard: 0 berries check
    if total <= 0:
        desc = (
            f"😈❌ **NEGOTIATION REFUSED — YOU'RE BROKE!** ❌😈\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"*Juny crosses her obsidian wings, looks down at you with piercing ruby eyes, and bursts into mocking laughter!*\n\n"
            f"\"AHAHAHAHA! Are you seriously trying to negotiate with **ZERO BERRIES**?!\"\n"
            f"\"Do I look like a celestial charity organization to you, mortal?! You have nothing in your pocket, nothing in your vault, and your soul is drenched in sin!\"\n\n"
            f"\"Since you have no coin to bribe Heaven's Worst Angel, **YOU WILL PAY IN BLOOD!**\"\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        sent = await send_as_juny(message.channel, content=desc)
        if not sent:
            await _safe_send_reply(message, desc)
        await start_boss_combat(message, client, user_id)
        return

    if choice_norm in ("getaway", "escape", "away", "bribe", "flee"):
        p_cut, v_cut, tot_cut = compute_proportional_cuts(p_berries, v_berries, 0.20)
        async with _LOCK:
            _ensure_fresh_data()
            apply_proportional_berry_cut(user_id, p_cut, v_cut, spouse_id)
            u_stat = _USER_STATS.get(user_id, {})
            u_stat["sin"] = max(0, u_stat.get("sin", 0) - 10)
            _save_data_sync(_USER_STATS)

        rem_wealth = max(0, total - tot_cut)
        rem_pouch = max(0, p_berries - p_cut)
        rem_vault = max(0, v_berries - v_cut) if spouse_id else 0
        vault_txt = f"\n• 🏦 **Joint Vault Paid:** `-{v_cut:,} 🫐` *(Shared with <@{spouse_id}>)*" if (spouse_id and v_cut > 0) else ""
        vault_rem = f" (Pouch: `{rem_pouch:,}` | Vault: `{rem_vault:,}`)" if spouse_id else ""

        desc = (
            f"🏃💨 **BRIBED TO FREEDOM — YOU GOT AWAY!** 💨🏃\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"*Juny snatches the heavy pouch of berries out of midair, tossing it with a smug smirk.*\n\n"
            f"\"Pfft! AHAHAHA! Look at you scurrying away like a terrified field mouse!\"\n"
            f"\"Smart move, mortal. 20% of your fortune buys your pathetic hide today. Consider **10 of your sins** overlooked... for now. Don't let me catch you piling up sins again, or I'll take 100%!\"\n\n"
            f"• 🫐 **Personal Pouch Paid:** `-{p_cut:,} 🫐`{vault_txt}\n"
            f"• 💰 **Total Bribe Paid (20%):** `-{tot_cut:,} 🫐`\n"
            f"• 💎 **Remaining Wealth Kept (80%):** `{rem_wealth:,} 🫐`{vault_rem}\n"
            f"• ❤️‍🔥 **Sin Reduced:** `-10 Sin` *(Current Sin: `{max(0, stats.get('sin', 0) - 10)}/30`)*\n"
            f"• 🛡️ **Status:** Safely Escaped Juny's Wrath!\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        sent = await send_as_juny(message.channel, content=desc)
        if not sent:
            await _safe_send_reply(message, desc)
        return

    elif choice_norm in ("contract", "pact", "slave", "deal"):
        p_cut, v_cut, tot_cut = compute_proportional_cuts(p_berries, v_berries, 0.40)
        async with _LOCK:
            _ensure_fresh_data()
            apply_proportional_berry_cut(user_id, p_cut, v_cut, spouse_id)
            u_stat = _USER_STATS.get(user_id, {})
            u_stat["sin"] = 0
            u_stat["virtue"] = 0
            u_stat["title"] = "Devil's Slave"
            u_inv = u_stat.setdefault("inventory", {})
            u_inv["devil_contract"] = u_inv.get("devil_contract", 0) + 1
            if YUNA_PACT_AVAILABLE and yuna_pact:
                yuna_pact.start_pact(user_id, u_stat)
            else:
                u_stat["dark_bargain"] = True
                u_stat["pact_expires_at"] = time.time() + 10800
            _save_data_sync(_USER_STATS)

        unlocked = await check_and_award_achievements(user_id)
        banner = format_achievement_banner(unlocked)

        rem_wealth = max(0, total - tot_cut)
        rem_pouch = max(0, p_berries - p_cut)
        rem_vault = max(0, v_berries - v_cut) if spouse_id else 0
        vault_txt = f"\n• 🏦 **Joint Vault Paid:** `-{v_cut:,} 🫐` *(Shared with <@{spouse_id}>)*" if (spouse_id and v_cut > 0) else ""
        vault_rem = f" (Pouch: `{rem_pouch:,}` | Vault: `{rem_vault:,}`)" if spouse_id else ""

        desc = (
            f"📜😈 **DEVIL'S CONTRACT SEALED! (40% CUT)** 😈📜\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"*Juny unfurls an ancient obsidian parchment engulfed in violent amethyst hellfire!*\n\n"
            f"\"A contract sealed in blood and flame! I'll take my **40% cut** from your wealth—and generous as I am, you get to keep the other 60%!\"\n"
            f"\"In exchange, your sordid sins and empty virtues are completely wiped clean! But remember your place... from this very second, your soul belongs to Juny for the next **3 hours**!\"\n\n"
            f"• 🫐 **Personal Pouch Paid:** `-{p_cut:,} 🫐`{vault_txt}\n"
            f"• 💰 **Total Pact Cut (40%):** `-{tot_cut:,} 🫐`\n"
            f"• 💎 **Remaining Wealth Kept (60%):** `{rem_wealth:,} 🫐`{vault_rem}\n"
            f"• ⚖️ **Karma (Sin & Virtue):** `Reset to 0`\n"
            f"• 📜 **Item Received:** `Devil's Contract`\n"
            f"• ⏳ **Contract Duration:** `3 Hours (Active Now!)`\n"
            f"• ⛓️ **Title Granted:** `Devil's Slave`\n"
            f"• 😈 **Juny Takeover:** Juny will now answer all your commands instead of Yuna!\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━{banner}"
        )
        sent = await send_as_juny(message.channel, content=desc)
        if not sent:
            await _safe_send_reply(message, desc)
        return

async def process_boss_choice(
    message,
    client,
    user_id: str,
    choice: str,
    view: Optional[View] = None,
    sub_choice: Optional[str] = None,
    interaction: Optional[discord.Interaction] = None
):
    encounter = _PENDING_BOSS_ENCOUNTERS.get(user_id)
    if not encounter:
        if interaction and not interaction.response.is_done():
            await _safe_send_ephemeral(interaction, "This encounter is no longer active!")
        return

    if view:
        for child in view.children:
            child.disabled = True
        try:
            if interaction and not interaction.response.is_done():
                await interaction.response.edit_message(view=view)
            elif interaction and interaction.response.is_done():
                await interaction.edit_original_response(view=view)
            elif hasattr(message, "edit"):
                await message.edit(view=view)
        except Exception:
            pass

    stats = await _get_user_stats(user_id)
    inv = stats.get("inventory", {})

    if choice == "plead":
        _PENDING_BOSS_ENCOUNTERS.pop(user_id, None)
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
        total, p_berries, v_berries, vault, spouse_id = get_user_total_wealth(user_id, stats)
        if total <= 0:
            _PENDING_BOSS_ENCOUNTERS.pop(user_id, None)
            desc = (
                f"😈❌ **NEGOTIATION REFUSED — YOU'RE BROKE!** ❌😈\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"*Juny crosses her obsidian wings, looks down at you with piercing ruby eyes, and bursts into mocking laughter!*\n\n"
                f"\"AHAHAHAHA! Are you seriously trying to negotiate with **ZERO BERRIES**?!\"\n"
                f"\"Do I look like a celestial charity organization to you, mortal?! You have nothing in your pocket, nothing in your vault, and your soul is drenched in sin!\"\n\n"
                f"\"Since you have no coin to bribe Heaven's Worst Angel, **YOU WILL PAY IN BLOOD!**\"\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            sent = await send_as_juny(message.channel, content=desc)
            if not sent:
                await _safe_send_reply(message, desc)
            await start_boss_combat(message, client, user_id)
            return

        if sub_choice:
            await resolve_boss_negotiation(message, client, user_id, sub_choice)
            return

        await show_juny_negotiation_menu(message, client, user_id)
        return

    elif choice == "fight":
        _PENDING_BOSS_ENCOUNTERS.pop(user_id, None)
        await start_boss_combat(message, client, user_id)
        return

class JunySkillSelectView(ResilientView):
    def __init__(self, host_id: str, author_id: str, skills: list, cur_mp: int = 100):
        super().__init__(timeout=120)
        self.host_id = host_id
        self.author_id = author_id

        options = []
        for sk in skills[:25]:
            cost = sk.get("mp_cost", 20)
            stance = sk.get("stance", "tactical").capitalize()
            raw_emoji = sk.get("emoji", "✨")
            clean_emoji = _clean_emoji_for_discord(raw_emoji, default="✨")
            options.append(discord.SelectOption(
                label=f"{sk['name']} ({cost} MP)"[:100],
                value=sk["id"],
                description=f"{stance} • {sk.get('desc', '')}"[:100],
                emoji=clean_emoji
            ))

        select = Select(placeholder=f"✨ Cast a skill (💧 {cur_mp} MP available)...", options=options)
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.author_id:
            await _safe_send_ephemeral(interaction, "This skill menu is for someone else!")
            return
        chosen = self.children[0].values[0]
        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(content=f"✨ Casting `{chosen}` against Juny...", view=None)
            else:
                await interaction.edit_original_response(content=f"✨ Casting `{chosen}` against Juny...", view=None)
        except Exception:
            pass
        combat = _ACTIVE_BOSS_FIGHTS.get(self.host_id)
        if not combat:
            return
        msg = combat.get("message") or getattr(interaction, "message", None)
        await execute_combat_round(
            msg,
            interaction.client,
            self.host_id,
            self.author_id,
            "skill",
            item_key=chosen,
            view=JunyCombatView(self.host_id)
        )

class JunyCombatView(ResilientView):
    def __init__(self, host_id: str):
        super().__init__(timeout=600)
        self.host_id = host_id

    async def on_timeout(self):
        combat = _ACTIVE_BOSS_FIGHTS.pop(self.host_id, None)
        if combat:
            for child in self.children:
                child.disabled = True
            if combat.get("message"):
                try:
                    await combat["message"].edit(view=self)
                except Exception:
                    pass

    @discord.ui.button(label="⚔ Attack", style=discord.ButtonStyle.danger, row=0)
    async def attack_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = str(interaction.user.id)
        combat = _ACTIVE_BOSS_FIGHTS.get(self.host_id)
        if not combat or uid not in combat["party"]:
            await _safe_send_ephemeral(interaction, "You are not part of this battle party!")
            return
        if not combat["party"][uid]["alive"]:
            await _safe_send_ephemeral(interaction, "You have fallen in battle and cannot act!")
            return
        if combat.get("round_in_progress"):
            await _safe_send_ephemeral(interaction, "An action is already processing! Please wait a moment.")
            return
        await execute_combat_round(
            interaction.message,
            interaction.client,
            self.host_id,
            uid,
            "attack",
            view=self,
            interaction=interaction
        )

    @discord.ui.button(label="✦ Skill", style=discord.ButtonStyle.primary, row=0)
    async def skill_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = str(interaction.user.id)
        combat = _ACTIVE_BOSS_FIGHTS.get(self.host_id)
        if not combat or uid not in combat["party"]:
            await _safe_send_ephemeral(interaction, "You are not part of this battle party!")
            return
        if not combat["party"][uid]["alive"]:
            await _safe_send_ephemeral(interaction, "You have fallen in battle and cannot act!")
            return
        if combat.get("round_in_progress"):
            await _safe_send_ephemeral(interaction, "An action is already processing! Please wait a moment.")
            return

        stats = await _get_user_stats(uid)
        avail_skills = []
        if YUNA_RPG_AVAILABLE and yuna_rpg:
            eq_sk, m_sk = yuna_rpg.get_player_equipped_skills(stats)
            avail_skills = eq_sk + m_sk

        if not avail_skills:
            await _safe_send_ephemeral(interaction, "You don't have any skills equipped! Equip up to 8 skills with `y!equip` or train in `y!arena`!")
            return

        cur_mp = combat["party"][uid].get("mp", 100)
        view = JunySkillSelectView(self.host_id, uid, avail_skills, cur_mp=cur_mp)
        await _safe_send_ephemeral(interaction, "✨ **Select a skill to cast against Juny:**", view=view)

    @discord.ui.button(label="⟢ Dodge", style=discord.ButtonStyle.secondary, row=0)
    async def dodge_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = str(interaction.user.id)
        combat = _ACTIVE_BOSS_FIGHTS.get(self.host_id)
        if not combat or uid not in combat["party"]:
            await _safe_send_ephemeral(interaction, "You are not part of this battle party!")
            return
        if not combat["party"][uid]["alive"]:
            await _safe_send_ephemeral(interaction, "You have fallen in battle and cannot act!")
            return
        if combat.get("round_in_progress"):
            await _safe_send_ephemeral(interaction, "An action is already processing! Please wait a moment.")
            return
        await execute_combat_round(
            interaction.message,
            interaction.client,
            self.host_id,
            uid,
            "dodge",
            view=self,
            interaction=interaction
        )

    @discord.ui.button(label="⬡ Use Item", style=discord.ButtonStyle.secondary, row=1)
    async def item_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = str(interaction.user.id)
        combat = _ACTIVE_BOSS_FIGHTS.get(self.host_id)
        if not combat or uid not in combat["party"]:
            await _safe_send_ephemeral(interaction, "You are not part of this battle party!")
            return
        if not combat["party"][uid]["alive"]:
            await _safe_send_ephemeral(interaction, "You have fallen in battle and cannot act!")
            return
        if combat.get("round_in_progress"):
            await _safe_send_ephemeral(interaction, "An action is already processing! Please wait a moment.")
            return
        stats = await _get_user_stats(uid)
        inv = stats.get("inventory", {})
        usable = [k for k in ("ward", "elixir", "powder", "ironbrew", "adrenaline", "hammer", "sand") if inv.get(k, 0) > 0]
        if not usable:
            await _safe_send_ephemeral(interaction, "You don't have any combat consumables in your pouch! Buy some at `y!shop`!")
            return
        chosen = usable[0]
        await execute_combat_round(
            interaction.message,
            interaction.client,
            self.host_id,
            uid,
            "item",
            item_key=chosen,
            view=self,
            interaction=interaction
        )

    @discord.ui.button(label="❖ Call Aid", style=discord.ButtonStyle.secondary, row=1)
    async def callaid_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = str(interaction.user.id)
        combat = _ACTIVE_BOSS_FIGHTS.get(self.host_id)
        if not combat or uid not in combat["party"]:
            await _safe_send_ephemeral(interaction, "You are not part of this battle party!")
            return
        if not combat["party"][uid]["alive"]:
            await _safe_send_ephemeral(interaction, "You have fallen in battle and cannot act!")
            return
        current_party = len(combat["party"])
        if current_party >= 4:
            await _safe_send_ephemeral(interaction, "Your battle party is already full (max 4 fighters)!")
            return
        max_slots = 4 - current_party
        view = JunyCallAidSelectView(self.host_id, max_allies=max_slots, from_encounter=False)
        await _safe_send_ephemeral(
            interaction,
            f"📣 **SUMMON REINFORCEMENTS!**\nSelect up to {max_slots} allies from the menu below to join the battle against Juny, or type `y!call aid @friend` in chat!",
            view=view
        )

    @discord.ui.button(label="⎋ Flee", style=discord.ButtonStyle.secondary, row=1)
    async def flee_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = str(interaction.user.id)
        combat = _ACTIVE_BOSS_FIGHTS.get(self.host_id)
        if not combat or uid not in combat["party"]:
            await _safe_send_ephemeral(interaction, "You are not part of this battle party!")
            return
        await handle_boss_flee(interaction.message, interaction.client, [], user_id=uid, interaction=interaction)

class JunyAidInviteView(ResilientView):
    def __init__(self, host_id: str, target_user_id: str):
        super().__init__(timeout=300)
        self.host_id = host_id
        self.target_user_id = target_user_id

    @discord.ui.button(label="Help!", emoji="🤝", style=discord.ButtonStyle.success)
    async def help_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.target_user_id:
            await _safe_send_ephemeral(interaction, "This summons was not meant for you!")
            return
        for item in self.children:
            item.disabled = True
        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(view=self)
            elif interaction.message:
                await interaction.message.edit(view=self)
        except Exception:
            pass
        await join_boss_fight(interaction.message, self.host_id, self.target_user_id, interaction.user.display_name)

    @discord.ui.button(label="Chicken Out", emoji="🐔", style=discord.ButtonStyle.danger)
    async def chicken_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.target_user_id:
            await _safe_send_ephemeral(interaction, "This summons was not meant for you!")
            return
        for item in self.children:
            item.disabled = True
        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(view=self)
            elif interaction.message:
                await interaction.message.edit(view=self)
        except Exception:
            pass
        await chicken_out_boss_fight(interaction.message, self.host_id, self.target_user_id, interaction.user.display_name)

class JunyCallAidSelectView(ResilientView):
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
            await _safe_send_ephemeral(interaction, "No allies selected!")
            return

        # If calling aid from encounter, start combat first
        if self.from_encounter:
            encounter = _PENDING_BOSS_ENCOUNTERS.pop(self.host_id, None)
            if encounter:
                await start_boss_combat(interaction.message, interaction.client, self.host_id)

        combat = _ACTIVE_BOSS_FIGHTS.get(self.host_id)
        if not combat:
            await _safe_send_ephemeral(interaction, "Boss fight is no longer active!")
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
            await _safe_send_ephemeral(interaction, "All selected members are either bots, already in the party, or yourself!")
            return

        # Disable selection on this view
        for child in self.children:
            child.disabled = True

        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(
                    content=f"📣 Summons sent to: {', '.join(t.mention for t in valid_targets)}! They can click **[Help!]** in chat to join immediately.",
                    view=self
                )
            elif interaction.message:
                await interaction.message.edit(
                    content=f"📣 Summons sent to: {', '.join(t.mention for t in valid_targets)}! They can click **[Help!]** in chat to join immediately.",
                    view=self
                )
        except Exception:
            try:
                await _safe_send_ephemeral(
                    interaction,
                    f"📣 Summons sent to: {', '.join(t.mention for t in valid_targets)}!"
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

    stats = await _get_user_stats(host_id)
    player_data = compute_juny_combatant_stats(stats, name)

    _, eff_s = get_effective_morality(stats)
    sin_mult = compute_juny_sin_multiplier(eff_s)

    base_hp = int(160000 * sin_mult)
    base_atk = int(48000 * sin_mult)  # 3x base ATK (16,000 * 3 = 48,000) scaled by Sin
    base_def = int(40000 * sin_mult)
    if stats.get("juny_enraged"):
        base_hp *= 2
        base_atk *= 2
        base_def *= 2

    combat_state = {
        "host_id": host_id,
        "channel_id": message.channel.id,
        "boss": {
            "name": "Juny, Heaven's Worst Angel",
            "hp": base_hp,
            "max_hp": base_hp,
            "def": base_def,
            "atk": base_atk,
            "sin_mult": sin_mult,
            "turn": 1,
            "blinded": False,
            "shielded": False,
            "stunned": False,
            "stagger": 0,
            "burn_turns": 0,
            "bleed_turns": 0,
            "daze_turns": 0,
            "shock_turns": 0,
            "silence_turns": 0,
            "radiation_fallout": 0
        },
        "party": {
            host_id: player_data
        },
        "player_actions": {},
        "boss_taunted_by": None,
        "intervene_by": None,
        "log": [f"⚔️ **Battle commences!** Juny brandishes her Obsidian Staff with a wicked laugh!"],
        "message": None
    }
    _ACTIVE_BOSS_FIGHTS[host_id] = combat_state

    view = JunyCombatView(host_id)
    embed = _build_combat_embed(combat_state)
    sent = await send_as_juny(message.channel, embed=embed, view=view)
    if not sent:
        sent = await _safe_send_reply(message, embed=embed, view=view)
    combat_state["message"] = sent

def _build_combat_embed(combat: dict) -> discord.Embed:
    boss = combat["boss"]
    turn = boss["turn"]
    mood_key, mood_quote = JUNY_MOODS[((turn - 1) // 2) % len(JUNY_MOODS)]

    embed = discord.Embed(
        title=f"Boss Fight: Juny, Heaven's Worst Angel (Turn {turn})",
        description=f"Mood: `{mood_key.title()}` — \"{mood_quote}\"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        color=0x2B2D31
    )

    boss_bar = _render_combat_hp_bar(boss["hp"], boss["max_hp"], 12)
    boss_status = []
    if boss.get("stunned"):
        boss_status.append("💫 Stunned/Frozen")
    if boss.get("blinded"):
        boss_status.append("🏖️ Blinded")
    if boss.get("shielded"):
        boss_status.append("🛡️ Sacred Barrier (-50% DMG)")
    if boss.get("burn_turns", 0) > 0:
        boss_status.append(f"🔥 Burn ({boss['burn_turns']}t)")
    if boss.get("bleed_turns", 0) > 0:
        boss_status.append(f"🩸 Bleed ({boss['bleed_turns']}t)")
    if boss.get("daze_turns", 0) > 0:
        boss_status.append(f"🔨 Daze ({boss['daze_turns']}t)")
    if boss.get("shock_turns", 0) > 0:
        boss_status.append(f"⚡ Shock ({boss['shock_turns']}t)")
    if boss.get("radiation_fallout", 0) > 0:
        boss_status.append(f"☢️ Fallout ({boss['radiation_fallout']}t)")
    if boss.get("silence_turns", 0) > 0:
        boss_status.append(f"🤐 Silenced ({boss['silence_turns']}t)")
    if boss.get("stagger", 0) > 0:
        boss_status.append(f"💥 Stagger ({boss['stagger']}/100)")
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
        mp_val = p.get("mp", 100)
        max_mp = p.get("max_mp", 100)
        buffs = []
        if p.get("shield_hp", 0) > 0:
            buffs.append(f"🛡️ Shield ({p['shield_hp']:,})")
        if p.get("next_atk_boost", 1.0) > 1.0:
            buffs.append(f"⚡ Boost (+{int((p['next_atk_boost']-1)*100)}%)")
        if p.get("is_dodging"):
            buffs.append("💨 Evasive")
        if p.get("iron_turns", 0) > 0:
            buffs.append(f"🛡️ Iron ({p['iron_turns']}t)")
        if p.get("adrenaline_turns", 0) > 0:
            buffs.append(f"💉 Adrenaline ({p['adrenaline_turns']}t)")
        if p.get("burn_turns", 0) > 0:
            buffs.append(f"🔥 Burn ({p['burn_turns']}t)")
        if p.get("reflect_pct", 0) > 0:
            buffs.append(f"🪞 Reflect ({int(p['reflect_pct']*100)}%)")
        if p.get("dmg_reduction", 0) > 0:
            buffs.append(f"🛡️ -{int(p['dmg_reduction']*100)}% Dmg")
        if p.get("isotope_stacks", 0) > 0:
            buffs.append(f"☢️ Isotope x{p['isotope_stacks']}")
        buff_txt = f" [{', '.join(buffs)}]" if buffs else ""

        act_summary = combat.get("player_actions", {}).get(uid)
        act_line = f"\n  └─ {act_summary}" if act_summary else ""
        party_lines.append(f"{status_icon} **{p['name']}**: {hp_bar} • 💧 `{mp_val}/{max_mp} MP`{buff_txt}{act_line}")

    embed.add_field(
        name=f"🛡️ Battle Party ({len([p for p in combat['party'].values() if p['alive']])}/{len(combat['party'])} Alive)",
        value="\n".join(party_lines) if party_lines else "No fighters alive!",
        inline=False
    )

    recent_logs = combat["log"][-8:]
    embed.add_field(
        name="📜 Combat Log",
        value="\n".join(recent_logs) if recent_logs else "*Waiting for first action...*",
        inline=False
    )
    embed.set_footer(text="Combat Controls • Click Attack, Skill, Dodge, Item, Call Aid, or Flee | y!attack, y!skill <name>, y!dodge, y!useitem, y!flee")
    return embed

def _calc_juny_dmg(target: dict, raw_power: int, is_apocalypse: bool = False, boss: Optional[dict] = None) -> int:
    """
    Calculates dynamic percentage-based damage scaled to player max HP and DEF,
    factoring in Juny's 3x ATK increase, Sin Wrath, boss daze/shock debuffs, and player damage reduction.
    """
    max_hp = max(100, target.get("max_hp", 100))
    eff_def = max(0, target.get("def", 25) + (50 if target.get("iron_turns", 0) > 0 else 0))
    power_mult = max(0.7, min(1.4, (raw_power / 40.0) if raw_power > 0 else 1.0))

    sin_mult = boss.get("sin_mult", 1.0) if boss else 1.0
    atk_mult = 3.0 * sin_mult
    if boss:
        if boss.get("daze_turns", 0) > 0:
            atk_mult *= 0.75
        if boss.get("shock_turns", 0) > 0:
            atk_mult *= 0.70

    if is_apocalypse:
        base_pct = random.uniform(0.35, 0.50) * atk_mult
    else:
        base_pct = random.uniform(0.20, 0.34) * power_mult * atk_mult

    def_mitigation = min(0.35, eff_def / (eff_def + 250.0))
    final_pct = base_pct * (1.0 - def_mitigation)

    floor_pct = (0.22 if is_apocalypse else 0.12) * atk_mult
    final_pct = max(floor_pct, final_pct)

    dmg = int(max_hp * final_pct)
    if target.get("dmg_reduction", 0.0) > 0:
        dmg = int(dmg * (1.0 - target["dmg_reduction"]))
    return max(35, dmg)

async def execute_combat_round(
    message,
    client,
    host_id: str,
    acting_uid: str,
    action: str,
    item_key: str = "",
    view: Optional[View] = None,
    interaction: Optional[discord.Interaction] = None
):
    combat = _ACTIVE_BOSS_FIGHTS.get(host_id)
    if not combat:
        if interaction and not interaction.response.is_done():
            await _safe_send_ephemeral(interaction, "This battle is no longer active!")
        return
    if combat.get("round_in_progress"):
        if interaction and not interaction.response.is_done():
            await _safe_send_ephemeral(interaction, "An action is already in progress! Please wait a moment.")
        return
    combat["round_in_progress"] = True
    try:
        boss = combat["boss"]
        party = combat["party"]
        player = party.get(acting_uid)
        if not player or not player["alive"]:
            if interaction and not interaction.response.is_done():
                await _safe_send_ephemeral(interaction, "You have fallen in battle and cannot act!")
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
                player["mp"] = min(player.get("max_mp", 100), player.get("mp", 0) + 20)
                boost = player.pop("next_atk_boost", 1.0)
                base_atk = (player["atk"] + (35 if player.get("adrenaline_turns", 0) > 0 else 0)) * boost
                dmg = max(15, int((base_atk * 2.8) * random.uniform(0.85, 1.25)))
                is_crit = (random.random() < player.get("crit_rate", 0.15))
                if is_crit:
                    dmg = int(dmg * 1.8)
                if boss.get("shielded"):
                    dmg = max(10, int(dmg * 0.5))
                boss["hp"] = max(0, boss["hp"] - dmg)
                crit_txt = " 💥 **CRITICAL HIT!**" if is_crit else ""
                combat.setdefault("player_actions", {})[acting_uid] = f"⚔️ Basic Attack → **{dmg:,} DMG**!{crit_txt}"
                combat["log"].append(f"⚔️ **{player['name']}** attacked Juny for **{dmg:,} DMG**!{crit_txt} *(+20 MP)*")

        elif action == "skill":
            skill_id = item_key
            sk = None
            if YUNA_RPG_AVAILABLE and yuna_rpg:
                sk = yuna_rpg.WEIRD_SKILLS.get(skill_id) or yuna_rpg.MARITAL_SKILLS.get(skill_id)
            if not sk:
                combat["log"].append(f"❌ **{player['name']}** attempted to cast an unknown skill!")
            else:
                mp_cost = sk.get("mp_cost", 20)
                cur_mp = player.get("mp", 100)
                if cur_mp < mp_cost:
                    player["mp"] = min(player.get("max_mp", 100), cur_mp + 15)
                    combat["log"].append(f"⚠️ **{player['name']}** lacked MP for {sk['emoji']} **{sk['name']}** ({cur_mp}/{mp_cost} MP)! Strike restored +15 MP!")
                    base_atk = player["atk"] + (35 if player.get("adrenaline_turns", 0) > 0 else 0)
                    dmg = max(15, int((base_atk * 2.0) * random.uniform(0.85, 1.15)))
                    boss["hp"] = max(0, boss["hp"] - dmg)
                    act_summary = f"⚔️ Scraping Strike for **{dmg:,} DMG** *(Low MP)*"
                    combat.setdefault("player_actions", {})[acting_uid] = act_summary
                    combat["log"].append(f"⚔️ **{player['name']}** scraped Juny for **{dmg:,} DMG**!")
                else:
                    player["mp"] -= mp_cost
                    eff_notes = []
                    if sk.get("mp_refund"):
                        player["mp"] = min(player.get("max_mp", 100), player["mp"] + sk["mp_refund"])
                        eff_notes.append(f"+{sk['mp_refund']} MP")

                    if sk.get("cleanse"):
                        player["burn_turns"] = 0
                        eff_notes.append("Cleansed")

                    if sk.get("party_cleanse"):
                        for ally in party.values():
                            if ally["alive"]:
                                ally["burn_turns"] = 0
                        eff_notes.append("Party Cleansed")

                    heal_log = ""
                    if sk.get("heal_pct"):
                        heal_amt = int(player["max_hp"] * sk["heal_pct"])
                        player["hp"] = min(player["max_hp"], player["hp"] + heal_amt)
                        heal_log = f" *(Healed +{heal_amt:,} HP)*"
                        eff_notes.append(f"+{heal_amt:,} HP")

                    if sk.get("party_heal_pct"):
                        p_heal_amt = int(player["max_hp"] * sk["party_heal_pct"])
                        for ally in party.values():
                            if ally["alive"]:
                                ally["hp"] = min(ally["max_hp"], ally["hp"] + p_heal_amt)
                        heal_log = f" *(Party Healed +{p_heal_amt:,} HP)*"
                        eff_notes.append(f"Party +{p_heal_amt:,} HP")

                    if sk.get("smart_ally_heal"):
                        living_allies = [p for p in party.values() if p["alive"]]
                        if living_allies:
                            lowest = min(living_allies, key=lambda a: a["hp"] / max(1, a["max_hp"]))
                            heal_amt = int(lowest["max_hp"] * sk.get("smart_ally_heal", 0.35))
                            lowest["hp"] = min(lowest["max_hp"], lowest["hp"] + heal_amt)
                            heal_log = f" *(Mended {lowest['name']} +{heal_amt:,} HP)*"
                            eff_notes.append(f"Mended {lowest['name']} +{heal_amt:,} HP")

                    shield_log = ""
                    if sk.get("shield_pct"):
                        s_amt = int(player["max_hp"] * sk["shield_pct"])
                        player["shield_hp"] = player.get("shield_hp", 0) + s_amt
                        shield_log = f" *(+{s_amt:,} Barrier)*"
                        eff_notes.append(f"+{s_amt:,} Barrier")

                    if sk.get("party_shield_pct"):
                        p_s_amt = int(player["max_hp"] * sk["party_shield_pct"])
                        for ally in party.values():
                            if ally["alive"]:
                                ally["shield_hp"] = ally.get("shield_hp", 0) + p_s_amt
                        shield_log = f" *(+{p_s_amt:,} Party Barrier)*"
                        eff_notes.append(f"Party +{p_s_amt:,} Barrier")

                    if sk.get("party_mp_restore"):
                        mp_boost = sk["party_mp_restore"]
                        for ally in party.values():
                            if ally["alive"]:
                                ally["mp"] = min(ally.get("max_mp", 100), ally.get("mp", 100) + mp_boost)
                        eff_notes.append(f"Party +{mp_boost} MP")

                    if sk.get("party_buff_atk"):
                        atk_mult = 1.0 + sk["party_buff_atk"]
                        for ally in party.values():
                            if ally["alive"]:
                                ally["next_atk_boost"] = max(ally.get("next_atk_boost", 1.0), atk_mult)
                        eff_notes.append("Party ATK Boost")

                    if sk.get("buff_next_atk"):
                        player["next_atk_boost"] = max(player.get("next_atk_boost", 1.0), sk["buff_next_atk"])
                        eff_notes.append(f"+{int((sk['buff_next_atk']-1)*100)}% Next ATK")

                    if sk.get("dodge_buff"):
                        player["dodge"] = min(0.85, player["dodge"] + sk["dodge_buff"])
                        eff_notes.append(f"+{int(sk['dodge_buff']*100)}% Dodge")

                    if sk.get("armor_strip"):
                        boss["def"] = max(5, int(boss.get("def", 25) * (1.0 - sk["armor_strip"])))
                        eff_notes.append(f"Stripped {int(sk['armor_strip']*100)}% DEF")

                    # Defender Secondary Effects
                    if sk.get("taunt_boss"):
                        combat["boss_taunted_by"] = acting_uid
                        eff_notes.append("Taunted Juny")
                    if sk.get("intervene_party"):
                        combat["intervene_by"] = acting_uid
                        eff_notes.append("Intervening Party")
                    if sk.get("reflect_pct"):
                        player["reflect_pct"] = max(player.get("reflect_pct", 0.0), sk["reflect_pct"])
                        eff_notes.append(f"🪞 Reflect {int(sk['reflect_pct']*100)}%")
                    if sk.get("dmg_reduction"):
                        player["dmg_reduction"] = max(player.get("dmg_reduction", 0.0), sk["dmg_reduction"])
                        eff_notes.append(f"🛡️ -{int(sk['dmg_reduction']*100)}% Dmg")
                    if sk.get("def_buff"):
                        player["def"] = int(player["def"] * (1.0 + sk["def_buff"]))
                        eff_notes.append(f"+{int(sk['def_buff']*100)}% DEF")
                    if sk.get("silence"):
                        boss["silence_turns"] = 1
                        eff_notes.append("🤐 Juny Silenced")

                    # Physicist Secondary Effects
                    if sk.get("turn_siphon"):
                        player["mp"] = min(player.get("max_mp", 100), player.get("mp", 0) + 20)
                        boss["blinded"] = True
                        eff_notes.append("Turn Siphoned (+20 MP, Blind)")
                    if sk.get("isotope_stack"):
                        player["isotope_stacks"] = player.get("isotope_stacks", 0) + sk["isotope_stack"]
                        eff_notes.append(f"☢️ Isotope Stack x{player['isotope_stacks']}")
                    prep = sk.get("prep_phase")
                    if prep:
                        player[prep] = True
                        if prep == "supercritical_core":
                            player["dmg_reduction"] = 0.50
                        eff_notes.append(f"Armed: {prep}")

                    # Debuffs
                    if sk.get("debuff") == "blind" or sk.get("spd_debuff"):
                        boss["blinded"] = True
                        eff_notes.append("Blinded")
                    elif sk.get("debuff") == "burn":
                        boss["burn_turns"] = 2
                        eff_notes.append("Holy Burn")
                    elif sk.get("debuff") == "daze":
                        boss["daze_turns"] = 2
                        eff_notes.append("Dazed (-25% ATK)")
                    elif sk.get("debuff") == "shock":
                        boss["shock_turns"] = 2
                        eff_notes.append("Shocked (-30% ATK)")
                    if sk.get("bleed"):
                        boss["bleed_turns"] = 3
                        eff_notes.append("Bleeding")

                    # Stun & Stagger
                    stun_log = ""
                    if sk.get("stagger_amt"):
                        boss["stagger"] = boss.get("stagger", 0) + sk["stagger_amt"]
                        if boss["stagger"] >= 100:
                            boss["stagger"] = 0
                            boss["stunned"] = True
                            stun_log = " 💥 **STAGGER BREAK! JUNY STUNNED!**"
                            eff_notes.append("💥 Stagger Break!")
                        else:
                            eff_notes.append(f"+{sk['stagger_amt']} Stagger")

                    if sk.get("stun_chance") and random.random() < sk["stun_chance"]:
                        boss["stunned"] = True
                        stun_log = " 💫 **JUNY STUNNED & FROZEN!**"
                        eff_notes.append("💫 Stunned")

                    dmg_mult = sk.get("dmg_mult", 0.0)
                    if dmg_mult > 0.0:
                        boost = player.pop("next_atk_boost", 1.0)
                        base_atk = (player["atk"] + (35 if player.get("adrenaline_turns", 0) > 0 else 0)) * boost
                        if sk.get("def_scaling"):
                            base_atk += player["def"] * 0.8
                        dmg = max(20, int((base_atk * 2.8 * dmg_mult) * random.uniform(0.90, 1.25)))
                        if skill_id == "thermonuclear_detonation":
                            if player.get("supercritical_core") or player.get("detonation_armed"):
                                dmg = int(dmg * 1.5)
                                player.pop("supercritical_core", None)
                                player.pop("detonation_armed", None)
                            boss["radiation_fallout"] = 3
                            eff_notes.append("☢️ Radiation Fallout")
                        if sk.get("missing_hp_scaling") and boss["max_hp"] > 0:
                            missing_pct = max(0.0, 1.0 - (boss["hp"] / boss["max_hp"]))
                            dmg = int(dmg * (1.0 + missing_pct))
                        if sk.get("true_damage") and player.get("isotope_stacks", 0) > 0:
                            dmg = int(dmg * (1.0 + player["isotope_stacks"] * 0.15))

                        is_crit = (random.random() < player.get("crit_rate", 0.15)) or sk.get("force_crit_next", False)
                        if is_crit:
                            dmg = int(dmg * 1.8)
                            if sk.get("refund_crit"):
                                ref_mp = int(mp_cost * sk["refund_crit"])
                                player["mp"] = min(player.get("max_mp", 100), player["mp"] + ref_mp)
                                eff_notes.append(f"+{ref_mp} MP on Crit")
                        if not sk.get("true_damage") and boss.get("shielded"):
                            dmg = max(10, int(dmg * 0.5))

                        boss["hp"] = max(0, boss["hp"] - dmg)
                        crit_txt = " 💥 **CRITICAL HIT!**" if is_crit else ""
                        note_str = f" *({', '.join(eff_notes)})*" if eff_notes else ""
                        act_summary = f"Cast {sk['emoji']} **{sk['name']}** → **{dmg:,} DMG**!{crit_txt}{note_str}"
                        combat.setdefault("player_actions", {})[acting_uid] = act_summary
                        combat["log"].append(f"✨ **{player['name']}** cast {sk['emoji']} **{sk['name']}** for **{dmg:,} DMG**!{crit_txt}{stun_log}{heal_log}{shield_log}")

                        if sk.get("lifesteal_pct"):
                            ls_heal = int(dmg * sk["lifesteal_pct"])
                            player["hp"] = min(player["max_hp"], player["hp"] + ls_heal)
                            combat["log"].append(f"🧛 **{player['name']}** lifestole **+{ls_heal:,} HP** from Juny!")
                    else:
                        note_str = f" *({', '.join(eff_notes)})*" if eff_notes else ""
                        act_summary = f"Activated {sk['emoji']} **{sk['name']}**!{note_str}"
                        combat.setdefault("player_actions", {})[acting_uid] = act_summary
                        combat["log"].append(f"✨ **{player['name']}** activated {sk['emoji']} **{sk['name']}**!{heal_log}{shield_log}{stun_log}")

        elif action == "dodge":
            player["is_dodging"] = True
            combat.setdefault("player_actions", {})[acting_uid] = "💨 Evasive Stance (+45% Dodge)"
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
                    combat.setdefault("player_actions", {})[acting_uid] = "🛡️ Heavenly Barrier Deployed!"
                    combat["log"].append(f"🛡️ **{player['name']}** raised the Heavenly Shield, creating an impenetrable celestial barrier!")
                elif item_key == "elixir":
                    heal = min(player["max_hp"] - player["hp"], max(75, int(player["max_hp"] * 0.40)))
                    player["hp"] += heal
                    combat.setdefault("player_actions", {})[acting_uid] = f"🧪 Archangel's Elixir (+{heal:,} HP)"
                    combat["log"].append(f"🧪 **{player['name']}** drank Archangel's Elixir, restoring **+{heal:,} HP**!")
                elif item_key == "powder":
                    powder_dmg = max(150, int(boss["max_hp"] * 0.08))
                    boss["hp"] = max(0, boss["hp"] - powder_dmg)
                    combat.setdefault("player_actions", {})[acting_uid] = f"✨ Smite Powder ({powder_dmg:,} True DMG)"
                    combat["log"].append(f"✨ **{player['name']}** detonated Smite Powder for **{powder_dmg:,} TRUE DAMAGE** directly to Juny!")
                elif item_key == "ironbrew":
                    player["iron_turns"] = 3
                    combat.setdefault("player_actions", {})[acting_uid] = "🛡️ Aegis Iron Brew (+50 DEF)"
                    combat["log"].append(f"🛡️ **{player['name']}** drank Aegis Iron Brew, gaining **+50 DEF** for 3 turns!")
                elif item_key == "adrenaline":
                    player["adrenaline_turns"] = 3
                    combat.setdefault("player_actions", {})[acting_uid] = "💉 Adrenaline (+35 ATK & +15% Dodge)"
                    combat["log"].append(f"💉 **{player['name']}** injected Adrenaline, gaining **+35 ATK & +15% Dodge** for 3 turns!")
                elif item_key == "sand":
                    boss["blinded"] = True
                    combat.setdefault("player_actions", {})[acting_uid] = "🏖️ Pocket Sand (Blinded Juny)"
                    combat["log"].append(f"🏖️ **{player['name']}** tossed Pocket Sand into Juny's eyes! She is **Blinded** for her next turn!")
                elif item_key == "hammer":
                    boss["hp"] = max(0, boss["hp"] - 1)
                    combat.setdefault("player_actions", {})[acting_uid] = "🔨 Rubber Hammer (1 DMG)"
                    combat["log"].append(f"🔨 **{player['name']}** whacked Juny with a Squeaky Rubber Hammer for **1 DMG**! *SQUEEEEAK!*")
            else:
                combat.setdefault("player_actions", {})[acting_uid] = f"❌ Bag Empty ({item_key})"
                combat["log"].append(f"❌ **{player['name']}** reached into their bag for `{item_key}` but found nothing!")

        # Check if Juny flees at < 2% HP (Escapes without loot and enrages!)
        if boss["hp"] <= int(boss["max_hp"] * 0.02) and boss["hp"] > 0:
            if interaction and not interaction.response.is_done():
                try:
                    await interaction.response.defer()
                except Exception:
                    pass
            await resolve_boss_escape(message, client, host_id)
            return

        # Check if Juny is defeated
        if boss["hp"] <= 0:
            if interaction and not interaction.response.is_done():
                try:
                    await interaction.response.defer()
                except Exception:
                    pass
            await resolve_boss_victory(message, client, host_id)
            return

        # ── Juny's Boss Turn ──
        boss["shielded"] = False

        # Apply Boss Status DoTs
        if boss.get("radiation_fallout", 0) > 0 and boss["hp"] > 0:
            rad_dmg = max(1000, int(boss["max_hp"] * 0.05))
            boss["hp"] = max(0, boss["hp"] - rad_dmg)
            boss["radiation_fallout"] -= 1
            combat["log"].append(f"☢️ **Radiation Fallout** dealt **{rad_dmg:,} True Damage** to Juny! ({boss['radiation_fallout']}t remaining)")
        if boss.get("burn_turns", 0) > 0 and boss["hp"] > 0:
            b_dmg = max(500, int(boss["max_hp"] * 0.03))
            boss["hp"] = max(0, boss["hp"] - b_dmg)
            boss["burn_turns"] -= 1
            combat["log"].append(f"🔥 Juny took **{b_dmg:,} Burn Damage**! ({boss['burn_turns']}t remaining)")
        if boss.get("bleed_turns", 0) > 0 and boss["hp"] > 0:
            bl_dmg = max(500, int(boss["max_hp"] * 0.04))
            boss["hp"] = max(0, boss["hp"] - bl_dmg)
            boss["bleed_turns"] -= 1
            combat["log"].append(f"🩸 Juny took **{bl_dmg:,} Bleed Damage**! ({boss['bleed_turns']}t remaining)")
        if boss.get("daze_turns", 0) > 0:
            boss["daze_turns"] -= 1
        if boss.get("shock_turns", 0) > 0:
            boss["shock_turns"] -= 1
        if boss.get("silence_turns", 0) > 0:
            boss["silence_turns"] -= 1

        # Check if Juny fell from DoT
        if boss["hp"] <= 0:
            if interaction and not interaction.response.is_done():
                try:
                    await interaction.response.defer()
                except Exception:
                    pass
            await resolve_boss_victory(message, client, host_id)
            return

        # Apply player burns (6% max HP)
        for p in party.values():
            if p["alive"] and p.get("burn_turns", 0) > 0:
                b_dmg = max(10, int(p["max_hp"] * 0.06))
                p["hp"] = max(0, p["hp"] - b_dmg)
                p["burn_turns"] -= 1
                combat["log"].append(f"🔥 **{p['name']}** took {b_dmg} Holy Burn damage!")
                if p["hp"] <= 0:
                    p["alive"] = False
                    combat["log"].append(f"💀 **{p['name']}** burned to death!")

        living_players = [p for p in party.values() if p["alive"]]
        if not living_players:
            if interaction and not interaction.response.is_done():
                try:
                    await interaction.response.defer()
                except Exception:
                    pass
            await resolve_boss_defeat(message, client, host_id)
            return

        if boss.get("stunned"):
            boss["stunned"] = False
            combat["log"].append("💫 Juny stumbled around dizzy and **STUNNED/FROZEN**! Her attack was cancelled!")
        elif boss.get("blinded"):
            boss["blinded"] = False
            combat["log"].append("🏖️ Juny furiously rubbed the sand from her eyes! Her attack **MISSED COMPLETELY**!")
        else:
            # Juny Attack Selection
            is_silenced = (boss.get("silenced") or boss.get("silence_turns", 0) > 0)
            if is_silenced:
                boss["silenced"] = False
                combat["log"].append("🤐 Juny was **SILENCED** and couldn't channel demonic apocalypse spells!")
            is_apocalypse = (boss["hp"] <= int(boss["max_hp"] * 0.30) and random.random() < 0.40 and not is_silenced)
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
                                    recoil_dmg = max(25, int(target["max_hp"] * 0.12))
                                    target["hp"] -= recoil_dmg
                                    combat["log"].append(
                                        f"💬 **{target['name']}**: *\"I have prepared for this.\"*\n"
                                        f"😈 **Juny-HWA**: *\"Have you?\"*\n"
                                        f"💥 **⚠️ Your Heavenly Shield has been corrupted by your sins! IT FUCKING EXPLODES!**"
                                    )
                                    dmg = _calc_juny_dmg(target, 50, is_apocalypse=True, boss=boss)
                                    if target.get("shield_hp", 0) > 0:
                                        abs_bar = min(target["shield_hp"], dmg)
                                        target["shield_hp"] -= abs_bar
                                        dmg -= abs_bar
                                        combat["log"].append(f"🛡️ **{target['name']}**'s barrier absorbed {abs_bar:,} DMG! ({target['shield_hp']:,} remaining)")
                                    if dmg > 0:
                                        target["hp"] -= dmg
                                        combat["log"].append(f"💥 **{target['name']}** took full apocalypse blast for **{dmg:,} DMG**!")
                                        await _check_player_death(host_id, target, combat)
                                elif outcome == "partial":
                                    dmg = max(10, _calc_juny_dmg(target, 50, is_apocalypse=True, boss=boss) // 2)
                                    if target.get("shield_hp", 0) > 0:
                                        abs_bar = min(target["shield_hp"], dmg)
                                        target["shield_hp"] -= abs_bar
                                        dmg -= abs_bar
                                        combat["log"].append(f"🛡️ **{target['name']}**'s barrier absorbed {abs_bar:,} DMG! ({target['shield_hp']:,} remaining)")
                                    if dmg > 0:
                                        target["hp"] -= dmg
                                        combat["log"].append(f"⚠️ **{target['name']}**'s corrupted Heavenly Shield absorbed 50% of the apocalypse! Took **{dmg:,} DMG**!")
                                        await _check_player_death(host_id, target, combat)
                                elif outcome == "fails":
                                    combat["log"].append(f"⚠️ **{target['name']}**'s corrupted Heavenly Shield sputtered and failed to activate!")
                                    dmg = _calc_juny_dmg(target, 50, is_apocalypse=True, boss=boss)
                                    if target.get("shield_hp", 0) > 0:
                                        abs_bar = min(target["shield_hp"], dmg)
                                        target["shield_hp"] -= abs_bar
                                        dmg -= abs_bar
                                        combat["log"].append(f"🛡️ **{target['name']}**'s barrier absorbed {abs_bar:,} DMG! ({target['shield_hp']:,} remaining)")
                                    if dmg > 0:
                                        target["hp"] -= dmg
                                        combat["log"].append(f"💥 **{target['name']}** was blasted for **{dmg:,} DMG**!")
                                        await _check_player_death(host_id, target, combat)
                                elif outcome == "breaks_after":
                                    combat["log"].append(f"⚠️ **{target['name']}**'s Heavenly Shield absorbed the apocalypse shockwave, then shattered completely!")
                                elif outcome == "penalty":
                                    recoil_dmg = max(15, int(target["max_hp"] * 0.08))
                                    target["hp"] -= recoil_dmg
                                    target["burn_turns"] = 2
                                    combat["log"].append(f"⚠️ **{target['name']}**'s Heavenly Shield absorbed the apocalypse, but backlash dealt {recoil_dmg} recoil DMG!")
                                    await _check_player_death(host_id, target, combat)
                            else:
                                combat["log"].append(f"🛡️ **{target['name']}**'s Heavenly Shield shone with pure celestial light, **BLOCKING 100% OF THE APOCALYPSE**!")
                        else:
                            dmg = _calc_juny_dmg(target, 50, is_apocalypse=True, boss=boss)
                            if target.get("shield_hp", 0) > 0:
                                abs_bar = min(target["shield_hp"], dmg)
                                target["shield_hp"] -= abs_bar
                                dmg -= abs_bar
                                combat["log"].append(f"🛡️ **{target['name']}**'s barrier absorbed {abs_bar:,} DMG! ({target['shield_hp']:,} remaining)")
                            if dmg > 0:
                                target["hp"] -= dmg
                                combat["log"].append(f"💥 **{target['name']}** was blasted for **{dmg:,} DMG**!")
                                await _check_player_death(host_id, target, combat)
            else:
                taunter_id = combat.get("boss_taunted_by")
                if taunter_id and taunter_id in party and party[taunter_id]["alive"]:
                    target = party[taunter_id]
                    combat["boss_taunted_by"] = None
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
                                    recoil_dmg = max(25, int(target["max_hp"] * 0.12))
                                    target["hp"] -= recoil_dmg
                                    combat["log"].append(
                                        f"💬 **{target['name']}**: *\"I have prepared for this.\"*\n"
                                        f"😈 **Juny-HWA**: *\"Have you?\"*\n"
                                        f"💥 **⚠️ Your Heavenly Shield has been corrupted by your sins! IT FUCKING EXPLODES!**\n"
                                        f"*(The dark corruption ({t_sin} ❤️‍🔥, {fail_pct}% failure) triggered a violent blast dealing **{recoil_dmg} recoil DMG** to {target['name']}!)*"
                                    )
                                    dmg = _calc_juny_dmg(target, raw_dmg, is_apocalypse=False, boss=boss)
                                    target["hp"] -= dmg
                                    combat["log"].append(f"⚡ Juny struck **{target['name']}** with **{atk_name}** for **{dmg:,} DMG**!")
                                    if atk_type == "drain":
                                        heal = max(50, int(dmg * 0.85))
                                        boss["hp"] = min(boss["max_hp"], boss["hp"] + heal)
                                        combat["log"].append(f"🩸 Juny healed **+{heal:,} HP** from your siphoned life force!")
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
                                    dmg = _calc_juny_dmg(target, raw_dmg, is_apocalypse=False, boss=boss)
                                    target["hp"] -= dmg
                                    combat["log"].append(f"⚡ Juny struck **{target['name']}** with **{atk_name}** for **{dmg:,} DMG**!")
                                    if atk_type == "drain":
                                        heal = max(50, int(dmg * 0.85))
                                        boss["hp"] = min(boss["max_hp"], boss["hp"] + heal)
                                        combat["log"].append(f"🩸 Juny healed **+{heal:,} HP** from your siphoned life force!")
                                    elif atk_type == "burn":
                                        target["burn_turns"] = 2
                                        combat["log"].append(f"🔥 **{target['name']}** was inflicted with Holy Burn!")
                                    elif atk_type == "mockery":
                                        combat["log"].append("😈 Juny points and laughs: *\"Is that really the best you've got? How pathetic!\"*")
                                    await _check_player_death(host_id, target, combat)

                                elif outcome == "partial":
                                    dmg = max(8, _calc_juny_dmg(target, raw_dmg, is_apocalypse=False, boss=boss) // 2)
                                    target["hp"] -= dmg
                                    combat["log"].append(
                                        f"⚠️ **{target['name']}**'s Heavenly Shield was corrupted by their sins ({t_sin} ❤️‍🔥)! "
                                        f"It cracked under the pressure, **ONLY BLOCKING 50% OF THE DAMAGE**! (**{dmg:,} DMG** taken)"
                                    )
                                    await _check_player_death(host_id, target, combat)

                                elif outcome == "breaks_after":
                                    combat["log"].append(
                                        f"⚠️ **{target['name']}**'s Heavenly Shield absorbed 100% of **{atk_name}**, but **SHATTERED INTO DUST IMMEDIATELY AFTER ACTIVATION**!"
                                    )

                                elif outcome == "penalty":
                                    recoil_dmg = max(15, int(target["max_hp"] * 0.08))
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
                            dmg = _calc_juny_dmg(target, raw_dmg, is_apocalypse=False, boss=boss)
                            if target.get("shield_hp", 0) > 0:
                                abs_bar = min(target["shield_hp"], dmg)
                                target["shield_hp"] -= abs_bar
                                dmg -= abs_bar
                                combat["log"].append(f"🛡️ **{target['name']}**'s barrier absorbed {abs_bar:,} DMG! ({target['shield_hp']:,} remaining)")

                            # Defender Intervene check
                            intervene_id = combat.get("intervene_by")
                            if intervene_id and intervene_id in party and party[intervene_id]["alive"] and intervene_id != t_uid and dmg > 0:
                                int_p = party[intervene_id]
                                int_dmg = int(dmg * 0.50)
                                dmg = 0
                                int_p["hp"] = max(0, int_p["hp"] - int_dmg)
                                combat["log"].append(f"🤝 **{int_p['name']}** INTERCEPTED the blow for **{target['name']}**! (Took {int_dmg:,} DMG at 50% discount)")
                                await _check_player_death(host_id, int_p, combat)
                                combat["intervene_by"] = None

                            if dmg > 0:
                                # Reflect check
                                if target.get("reflect_pct", 0.0) > 0:
                                    recoil = int(dmg * target["reflect_pct"])
                                    if recoil > 0:
                                        boss["hp"] = max(0, boss["hp"] - recoil)
                                        combat["log"].append(f"🪞 **{target['name']}** reflected **{recoil:,} DMG** back onto Juny!")
                                    target["reflect_pct"] = 0.0

                                target["hp"] -= dmg
                                combat["log"].append(f"⚡ Juny struck **{target['name']}** with **{atk_name}** for **{dmg:,} DMG**!")
                            if atk_type == "drain":
                                heal = max(50, int(dmg * 0.85))
                                boss["hp"] = min(boss["max_hp"], boss["hp"] + heal)
                                combat["log"].append(f"🩸 Juny healed **+{heal:,} HP** from your siphoned life force!")
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
            if interaction and not interaction.response.is_done():
                try:
                    await interaction.response.defer()
                except Exception:
                    pass
            await resolve_boss_defeat(message, client, host_id)
            return

        # Check boss phase shift (<= 30% HP Berserk Apocalypse Phase)
        if boss.get("hp", 0) <= int(boss["max_hp"] * 0.30) and not boss.get("apocalypse_phase_entered"):
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
        combat_view = view or JunyCombatView(host_id)
        target_msg = combat.get("message") or message

        updated = False
        if interaction:
            updated = await _safe_update_game_message(
                interaction=interaction,
                message=target_msg,
                embed=embed,
                view=combat_view
            )
        elif target_msg:
            edited = await edit_as_juny(target_msg, embed=embed, view=combat_view)
            updated = (edited is not None)

        if not updated:
            channel = getattr(target_msg, "channel", None) or getattr(message, "channel", None)
            if not channel and client:
                cid = combat.get("channel_id")
                if cid:
                    channel = client.get_channel(cid)
            sent = None
            if channel:
                sent = await send_as_juny(channel, embed=embed, view=combat_view)
            if not sent and (target_msg or message):
                sent = await _safe_send_reply(target_msg or message, embed=embed, view=combat_view)
            if sent:
                combat["message"] = sent
        elif target_msg:
            combat["message"] = target_msg
    finally:
        combat["round_in_progress"] = False

async def _check_player_death(host_id: str, target: dict, combat: dict):
    target_uid = None
    for uid, p in combat.get("party", {}).items():
        if p is target:
            target_uid = uid
            break

    # Renee Combat Intervention Check (HP <= 20% against tough bosses/Juny, Bonded or ??? relationship)
    if target_uid:
        t_stats = await _get_user_stats(target_uid)
        max_h = target.get("max_hp", 100)
        curr_h = target.get("hp", 0)
        if curr_h <= int(max_h * 0.20) and not target.get("renee_intervened"):
            try:
                import yuna_renee
                if yuna_renee.check_renee_intervention(t_stats):
                    target["renee_intervened"] = True
                    target["alive"] = True
                    target["hp"] = max(1, curr_h)
                    combat["log"].append(
                        "👤 **Renee joined the battle.**\n"
                        "Renee: \"...\"\n"
                        "Renee: \"I will fight alongside you.\""
                    )
                    boss = combat.get("boss", {})
                    turn_res = yuna_renee.execute_renee_combat_turn(boss, is_phase_2=False)
                    boss["hp"] = max(0, boss.get("hp", 0) - turn_res["dmg"])
                    combat["log"].append(turn_res["log"])

                    skill_name, dialogue = yuna_renee.execute_renee_resurrection(is_juny_fight=True)
                    combat["log"].append(f"\n{dialogue}")

                    turn_res2 = yuna_renee.execute_renee_combat_turn(boss, renee_hp_pct=0.01, is_phase_2=True)
                    boss["hp"] = max(0, boss.get("hp", 0) - turn_res2["dmg"])
                    combat["log"].append(turn_res2["log"])
                    return
            except Exception:
                pass

    if target["hp"] <= 0:
        if target_uid:
            t_stats = await _get_user_stats(target_uid)
            if t_stats.get("inventory", {}).get("feather", 0) > 0:
                async with _LOCK:
                    _USER_STATS[target_uid]["inventory"]["feather"] -= 1
                    if _USER_STATS[target_uid]["inventory"]["feather"] <= 0:
                        _USER_STATS[target_uid]["inventory"].pop("feather", None)
                    _save_data_sync(_USER_STATS)
                revive_hp = max(50, int(target["max_hp"] * 0.35))
                target["hp"] = revive_hp
                target["alive"] = True
                combat["log"].append(f"🪶 **{target['name']}**'s Phoenix Feather ignited into glorious flames, **RESURRECTING** them with {revive_hp:,} HP!")
                return
        target["alive"] = False
        combat["log"].append(f"💀 **{target['name']}** was struck down and collapsed in battle!")

async def resolve_boss_escape(message, client, host_id: str):
    """Juny escapes at < 2% HP without dropping loot and becomes enraged (2x stats next encounter)."""
    combat = _ACTIVE_BOSS_FIGHTS.pop(host_id, None)
    if not combat:
        return

    if combat.get("message"):
        try:
            await combat["message"].edit(view=None)
        except Exception:
            pass

    participants = list(combat["party"].keys())
    for uid in participants:
        async with _LOCK:
            _USER_STATS[uid]["juny_enraged"] = True
            _save_data_sync(_USER_STATS)

    escape_msg = (
        f"⚡ **JUNY FLEES INTO THE ABYSS! (ENRAGED)** ⚡\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"*Coughing dark golden blood, Juny stumbles back and unfurls six pitch-black wings!*\n\n"
        f"\"You actually thought you could put an end to Heaven's Worst Angel?! DON'T MAKE ME LAUGH!\"\n"
        f"*She snaps her fingers, dissolving into an impenetrable cloud of crimson stardust!*\n\n"
        f"\"Next time we meet, mortals... **I WON'T HOLD BACK!**\"\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ **NO SPOILS DROPPED!** Juny escaped before taking the fatal blow!\n"
        f"😈 **STATUS INFLICTED: JUNY ENRAGED!** Her stats will be **2x STRONGER** (320k HP, 32k ATK, 80k DEF) in your next encounter!"
    )
    sent = await send_as_juny(message.channel, content=escape_msg)
    if not sent:
        await _safe_send_reply(message, escape_msg)

async def resolve_boss_victory(message, client, host_id: str):
    combat = _ACTIVE_BOSS_FIGHTS.pop(host_id, None)
    if not combat:
        return

    if combat.get("message"):
        try:
            await combat["message"].edit(view=None)
        except Exception:
            pass

    # Reset any enraged status upon true defeat
    for uid in combat["party"]:
        async with _LOCK:
            _USER_STATS[uid]["juny_enraged"] = False
            _save_data_sync(_USER_STATS)

    participants = list(combat["party"].keys())
    horn_recipient = random.choice(participants) if participants else None
    horn_dropped = (random.random() < 0.08)  # 8% rare drop chance

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
            old_sin = u_stat.get("sin", 0)
            u_stat["sin"] = 0
            if old_sin != 0:
                _log_player_stat_audit(uid, "sin", old_sin, 0, "juny_boss_defeat_purification")
            if uid == horn_recipient and horn_dropped:
                u_stat.setdefault("inventory", {})["devil_horn"] = u_stat.setdefault("inventory", {}).get("devil_horn", 0) + 1
            _save_data_sync(_USER_STATS)
        await check_and_award_achievements(uid, specific_id="daredevil")

    relic_line = (
        f"• 🦹 **Relic Awarded:** <@{horn_recipient}> (`{combat['party'][horn_recipient]['name']}`) claimed **Juny's Devil Horn**! *(Rare 8% Drop!)*\n"
        if (horn_recipient and horn_dropped)
        else "• 🪶 **Relic Drop:** *Juny's Devil Horn did not drop this time (8% drop rate). Smoldering dark celestial ash drifted away...*\n"
    )

    embed = discord.Embed(
        title="🎉👑 VICTORY OVER JUNY, HEAVEN'S WORST ANGEL! 👑🎉",
        description=(
            f"*Juny drops her staff and falls to her knees in sheer disbelief, wings scattering dark ash!*\n\n"
            f"\"N-No way... I was defeated by mere mortals?! This is impossible... b-baka! Take your spoils and GET OUT!\"\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏆 **GLORIOUS SPOILS OF VICTORY:**\n"
            f"• ✨ **Empress Blessing:** `10 Actions of 2x Multiplier on EVERYTHING!`\n"
            f"• 💰 **War Bounty:** `+30% Berries added to pouch for all party members!`\n"
            f"• 🕊️ **Divine Absolution:** `All party members' Sin has been cleansed to 0 ❤️‍🔥!`\n"
            f"• 🎖️ **Title Granted:** `Daredevil`\n"
            f"• 🏆 **Achievement Unlocked:** `Daredevil`\n"
            f"{relic_line}"
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

    # Check if this was a Hitman assassination contract
    if combat.get("is_hitman") and combat.get("contractor_id"):
        contractor_id = combat["contractor_id"]
        target_stats = await _get_user_stats(host_id)
        target_bal = target_stats.get("berries", 0)
        bounty = max(0, int(target_bal * 0.50))
        contractor_cut = bounty // 2

        # Check for item theft (chance to steal auction trophy or GoD-HeLL loot)
        stolen_item_name = None
        target_trophies = target_stats.get("auction_trophies", [])
        target_inv = target_stats.get("inventory", {})

        async with _LOCK:
            # Strip 50% berries from target
            _USER_STATS[host_id]["berries"] = max(0, target_bal - bounty)
            # Give 50% of bounty to contractor
            _USER_STATS[contractor_id]["berries"] = _USER_STATS[contractor_id].get("berries", 0) + contractor_cut

            # Attempt trophy or loot steal
            if target_trophies and random.random() < 0.40:
                stolen_item_name = random.choice(target_trophies)
                _USER_STATS[host_id]["auction_trophies"].remove(stolen_item_name)
                _USER_STATS[contractor_id].setdefault("auction_trophies", []).append(stolen_item_name)
            elif target_inv:
                rare_candidates = [k for k in target_inv if target_inv[k] > 0]
                if rare_candidates and random.random() < 0.50:
                    chosen_k = random.choice(rare_candidates)
                    _USER_STATS[host_id]["inventory"][chosen_k] -= 1
                    if _USER_STATS[host_id]["inventory"][chosen_k] <= 0:
                        _USER_STATS[host_id]["inventory"].pop(chosen_k, None)
                    _USER_STATS[contractor_id].setdefault("inventory", {})[chosen_k] = _USER_STATS[contractor_id].setdefault("inventory", {}).get(chosen_k, 0) + 1
                    stolen_item_name = chosen_k

            _save_data_sync(_USER_STATS)

        stolen_text = f"\n🎁 **LOOT HEIST:** Contractor also plundered `{stolen_item_name}` from target's vault!" if stolen_item_name else ""
        hit_embed = discord.Embed(
            title="🎯⚰️ CONTRACT FULFILLED: TARGET ELIMINATED! ⚰️🎯",
            description=(
                f"*Juny stands triumphantly over <@{host_id}>, twirling her obsidian dagger with a sinister grin!*\n\n"
                f"\"Contract complete! Target dispatched cleanly. Here's your cut, partner~ Don't spend it all in one place!\"\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"• 💰 **Total Bounty Claimed:** `{bounty:,}` 🫐 (50% of target pouch)\n"
                f"• 🤝 **50/50 Split:** <@{contractor_id}> received `{contractor_cut:,}` 🫐 | Juny took `{bounty - contractor_cut:,}` 🫐{stolen_text}\n"
                f"• 💀 **Target Penalty:** <@{host_id}> lost `{bounty:,}` 🫐 and was struck down!"
            ),
            color=0x4A0E17
        )
        sent = await send_as_juny(message.channel, embed=hit_embed)
        if not sent:
            await _safe_send_reply(message, embed=hit_embed)
        return

    # Standard Soul Reap Defeat
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
    sent = await send_as_juny(message.channel, embed=embed)
    if not sent:
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
    # Contractor who ordered the hit cannot join the battle
    if combat.get("is_hitman") and combat.get("contractor_id") == ally_id:
        await _safe_send_reply(message, f"❌ <@{ally_id}> You ordered the hit on this target! You cannot intervene or join the assassination party!")
        return

    async with _LOCK:
        _USER_STATS[ally_id]["joined_boss_fights"] = _USER_STATS[ally_id].get("joined_boss_fights", 0) + 1
        _save_data_sync(_USER_STATS)
    await check_and_award_achievements(ally_id)

    stats = await _get_user_stats(ally_id)
    combat["party"][ally_id] = compute_juny_combatant_stats(stats, ally_name)

    # Scale boss stats (+30% HP & ATK per member above 1)
    party_size = len(combat["party"])
    if party_size > 1:
        scale = 1.0 + (0.30 * (party_size - 1))
        sin_mult = combat["boss"].get("sin_mult", 1.0)
        base_h = int(160000 * sin_mult * (2 if stats.get("juny_enraged") else 1))
        base_a = int(48000 * sin_mult * (2 if stats.get("juny_enraged") else 1))
        combat["boss"]["max_hp"] = int(base_h * scale)
        combat["boss"]["hp"] = min(combat["boss"]["max_hp"], int(combat["boss"]["hp"] * (scale / (scale - 0.30))))
        combat["boss"]["atk"] = int(base_a * scale)

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
    if YUNA_RPG_AVAILABLE and yuna_rpg:
        if not await yuna_rpg.check_class_requirement(message, client, author_id, sys.modules[__name__]):
            return
    combat_host = None
    for h_id, c in _ACTIVE_BOSS_FIGHTS.items():
        if author_id in c["party"]:
            combat_host = h_id
            break
    if not combat_host:
        # If user attacked Juny or typed y!attack juny:
        if (not args) or any("juny" in a.lower() for a in args) or any(a.lower() in ("boss", "angel", "her") for a in args):
            if YUNA_PACT_AVAILABLE and yuna_pact:
                stats = await _get_user_stats(author_id)
                ret_embed = await yuna_pact.execute_juny_retaliation(message, client, author_id, stats, reason="harm")
                in_p = is_in_pact(author_id)
                if not in_p:
                    ret_embed.description = "😈 **Juny:** *\"You swung at me outside of combat?! You have no contract to protect you, worm! DIE!\"*\n\n" + ret_embed.description
                await _safe_send_reply(message, embed=ret_embed)
                return
        await _safe_send_reply(message, "- *Yuna tilts her head* \"You are not in a battle against Juny! Type `y!provoke` to provoke Juny into attacking!\"")
        return
    await execute_combat_round(message, client, combat_host, author_id, "attack")

async def handle_provoke_juny(message, client, args: list):
    """Allows a player to provoke Juny into attacking back at any time (during pact or post-pact)."""
    author_id = str(message.author.id)
    if YUNA_RPG_AVAILABLE and yuna_rpg:
        if not await yuna_rpg.check_class_requirement(message, client, author_id, sys.modules[__name__]):
            return
    stats = await _get_user_stats(author_id)
    if YUNA_PACT_AVAILABLE and yuna_pact:
        ret_embed = await yuna_pact.execute_juny_retaliation(message, client, author_id, stats, reason="harm")
        in_p = is_in_pact(author_id)
        if not in_p:
            ret_embed.description = "😈 **Juny:** *\"Your contract has expired, mortal! You dare provoke Heaven's Worst Angel with no pact to shield you?! DIE!\"*\n\n" + ret_embed.description
        await _safe_send_reply(message, embed=ret_embed)
    else:
        await _safe_send_reply(message, "😈 **Juny strikes you down with celestial wrath!**")

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

async def handle_boss_skill(message, client, args: list):
    author_id = str(message.author.id)
    combat_host = None
    for h_id, c in _ACTIVE_BOSS_FIGHTS.items():
        if author_id in c["party"]:
            combat_host = h_id
            break
    if not combat_host:
        await _safe_send_reply(message, "- *Yuna tilts her head* \"You are not in a battle against Juny!\"")
        return

    stats = await _get_user_stats(author_id)
    avail_skills = []
    if YUNA_RPG_AVAILABLE and yuna_rpg:
        eq_sk, m_sk = yuna_rpg.get_player_equipped_skills(stats)
        avail_skills = eq_sk + m_sk

    if not avail_skills:
        await _safe_send_reply(message, "❌ You don't have any skills equipped! Train in `y!arena` to unlock skills and equip them in `y!equip`!")
        return

    chosen = None
    if args:
        q = " ".join(args).lower().strip()
        for sk in avail_skills:
            if q == sk["id"].lower() or q in sk["name"].lower():
                chosen = sk
                break
        if not chosen and YUNA_RPG_AVAILABLE and yuna_rpg:
            all_w, all_m = yuna_rpg.get_unlocked_skills(stats)
            for sk in (all_w + all_m):
                if q == sk["id"].lower() or q in sk["name"].lower():
                    chosen = sk
                    break

    if not chosen:
        if len(avail_skills) == 1:
            chosen = avail_skills[0]
        else:
            skill_list = "\n".join([f"• {s['emoji']} **{s['name']}** ({s.get('mp_cost', 20)} MP) — *{s.get('desc', '')[:60]}*" for s in avail_skills])
            await _safe_send_reply(message, f"✨ **Select a skill to cast against Juny:**\nType `y!skill <name>` (e.g. `y!skill {avail_skills[0]['name'].lower()}`)\n\n**Equipped Skills:**\n{skill_list}")
            return

    await execute_combat_round(message, client, combat_host, author_id, "skill", item_key=chosen["id"])

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
    embed = _build_combat_embed(combat)
    await _safe_send_reply(message, embed=embed, view=JunyCombatView(combat.get("host_id", author_id)))

async def handle_boss_flee(message, client, args: list, user_id: Optional[str] = None, interaction: Optional[discord.Interaction] = None):
    """Allows a player to flee or surrender from combat against Juny."""
    author_id = str(user_id or (message.author.id if getattr(message, "author", None) else ""))
    if interaction and not interaction.response.is_done():
        try:
            await interaction.response.defer()
        except Exception:
            pass
    combat_host = None
    combat = None
    for h_id, c in _ACTIVE_BOSS_FIGHTS.items():
        if author_id in c["party"]:
            combat_host = h_id
            combat = c
            break

    if not combat:
        if interaction:
            await _safe_send_ephemeral(interaction, "You are not in a battle against Juny!")
        else:
            await _safe_send_reply(message, "- *Yuna tilts her head* \"You are not in a battle against Juny!\"")
        return

    player = combat["party"].get(author_id)
    p_name = player["name"] if player else "Coward"

    other_alive = [uid for uid, p in combat["party"].items() if uid != author_id and p["alive"]]

    if other_alive and author_id != combat_host:
        combat["party"].pop(author_id, None)
        combat["log"].append(f"🐔 **{p_name}** panicked and fled from the battle, abandoning their allies!")
        async with _LOCK:
            u_stat = _USER_STATS.get(author_id, {})
            u_stat["berries"] = max(0, int(u_stat.get("berries", 0) * 0.85))
            u_stat["sin"] = min(30, u_stat.get("sin", 0) + 1)
            _save_data_sync(_USER_STATS)
        embed = _build_combat_embed(combat)
        if combat.get("message"):
            try:
                await edit_as_juny(combat["message"], embed=embed, view=JunyCombatView(combat_host))
            except Exception:
                pass
        await _safe_send_reply(
            message,
            f"🐔 **{p_name}** abandoned the party and scrambled away into the shadows!\n"
            f"*Juny's wicked laughter echoes:* \"Run, little worm! Leave your friends to burn!\"\n"
            f"• 🫐 **Penalty:** `-15% Berries` | ❤️‍🔥 **Karmic Cowardice:** `+1 Sin`"
        )
        return

    # Host flees or solo fighter flees -> ends encounter
    _ACTIVE_BOSS_FIGHTS.pop(combat_host, None)
    if combat.get("message"):
        try:
            await combat["message"].edit(view=None)
        except Exception:
            pass

    async with _LOCK:
        h_stat = _USER_STATS.get(author_id, {})
        loss = int(h_stat.get("berries", 0) * 0.30)
        h_stat["berries"] = max(0, h_stat.get("berries", 0) - loss)
        h_stat["sin"] = min(30, h_stat.get("sin", 0) + 2)
        h_stat["bad_luck_actions"] = 5
        _save_data_sync(_USER_STATS)

    embed = discord.Embed(
        title="🐔 COWARDICE! YOU FLED FROM JUNY! 🐔",
        description=(
            f"*You threw your weapons to the ground and sprinted away in terror!*\n\n"
            f"\"AHAHAHAHAHA! Look at you run!\" *Juny hovers high above, throwing back her head in howling laughter.*\n"
            f"\"Your dignity is in tatters, mortal! Remember this day every time you close your eyes!\"\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• 🫐 **Fleeing Penalty:** `-{loss:,} Berries` (30% dropped in panic)\n"
            f"• ❤️‍🔥 **Coward's Sin:** `+2 Sin`\n"
            f"• 🌧️ **Cursed with Shame:** `5 Actions of Bad Luck`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=0x888888
    )
    await _safe_send_reply(message, embed=embed)
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
                    if YUNA_ID_GUARD_AVAILABLE and yuna_id_guard and not yuna_id_guard.is_valid_guild_target(m, clean_name):
                        continue
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
    old_virtue = target_stats.get("virtue", 0)
    sin_gain = new_sin - old_sin

    async with _LOCK:
        u_stat = _USER_STATS.setdefault(target_id, _create_default_user())
        _ensure_user_defaults(u_stat)
        u_stat["sin"] = new_sin
        u_stat["good_actions_needed"] = 0
        u_stat["bad_actions_needed"] = 0
        if sin_gain > 0:
            u_stat["virtue"] = max(0, old_virtue - sin_gain)
        _save_data_sync(_USER_STATS)

    _log_player_stat_audit(
        target_id,
        "sin",
        old_sin,
        new_sin,
        f"admin_cmd_set_sin by author={author_id}"
    )
    if sin_gain > 0 and old_virtue != u_stat.get("virtue", 0):
        _log_player_stat_audit(
            target_id,
            "virtue",
            old_virtue,
            u_stat["virtue"],
            f"reduced_by_setsin_gain={sin_gain:+} by author={author_id}"
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


async def handle_skipcd(message, client, args: list) -> bool:
    """
    Admin command: y!skipcd [all | @user/id | renee]
    Resets cooldown timers for users, clears active game locks, and clears Renee's fight locks & cooldowns.
    """
    author_id = str(message.author.id)
    is_admin = False
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
            "- 🚫 *Yuna folds her arms and pouts!* \"Only the bot creator and server administrators have the authority to bypass time itself with `y!skipcd`!\""
        )
        return True

    target_id = None
    target_all = False
    target_renee = False

    if args:
        first_arg = args[0].lower().strip()
        if first_arg in ("all", "everyone", "*", "global"):
            target_all = True
        elif first_arg in ("renee", "fight", "duel", "boss"):
            target_renee = True
        else:
            m = re.search(r'(\d{17,20})', first_arg)
            if m:
                target_id = m.group(1)
            elif message.mentions:
                for men in message.mentions:
                    if client and client.user and men.id == client.user.id:
                        continue
                    target_id = str(men.id)
                    break
            if not target_id and first_arg in ("me", "self"):
                target_id = author_id
    else:
        target_id = author_id

    cleared_items = []

    # 1. Reset Renee fight locks & cooldowns
    try:
        import yuna_renee
        if target_all or target_renee:
            r_res = yuna_renee.reset_renee_cooldowns(None)
            cleared_items.extend(r_res.get("cleared", []))
            cleared_items.append("Renee global battle locks reset to IDLE")
        elif target_id:
            r_res = yuna_renee.reset_renee_cooldowns(target_id)
            cleared_items.extend(r_res.get("cleared", []))
            cleared_items.append("Renee battle lock cleared")
    except Exception as _re:
        print(f"[SKIPCD RENEE ERR] {_re}")

    # 2. Reset user cooldowns in gambling/RPG stats
    targets_to_clear = []
    if target_all:
        targets_to_clear = list(_USER_STATS.keys())
    elif target_id:
        targets_to_clear = [target_id]

    for uid in targets_to_clear:
        st = _USER_STATS.get(uid)
        if st:
            for k in ["last_work", "last_crime", "last_fish", "last_steal", "last_aid", "last_daily", "last_date", "last_kiss", "last_donate"]:
                st[k] = 0
            if "cooldowns" in st and isinstance(st["cooldowns"], dict):
                st["cooldowns"].clear()
            v = st.get("volcano", {})
            if isinstance(v, dict):
                v["inside"] = False
                v["activity"] = "idle"
                v["heat_resistant_until"] = 0

        # Clear active game locks
        _ACTIVE_BLACKJACK_GAMES.pop(uid, None)
        _ACTIVE_CRASH_GAMES.pop(uid, None)
        _ACTIVE_HL_GAMES.pop(uid, None)
        _ACTIVE_POKER_GAMES.pop(uid, None)
        _ACTIVE_MINES_GAMES.pop(uid, None)
        _ACTIVE_WORDLE_GAMES.pop(uid, None)
        _ACTIVE_DARES.pop(uid, None)

    await _save_data_sync()

    desc_lines = [f"• {item}" for item in cleared_items]
    if target_all:
        desc_lines.append("• Reset all command & activity cooldowns for all users")
        target_str = "**Everyone & All Bots**"
    elif target_renee:
        target_str = "**Renee Combat Systems**"
    else:
        desc_lines.append(f"• Reset all command cooldowns for <@{target_id}>")
        target_str = f"<@{target_id}>"

    embed = discord.Embed(
        title="⚡ [ADMIN] Cooldowns Skipped / Reset",
        description=f"Successfully bypassed active cooldowns and locks for {target_str}!\n\n" + "\n".join(desc_lines),
        color=0x2ECC71
    )
    embed.set_footer(text=f"Executed by {getattr(message.author, 'display_name', getattr(message.author, 'name', author_id))}")
    await _safe_send_reply(message, embed=embed)
    return True


async def handle_giveout(message, client, args: list):
    """
    Admin command: y!giveout @user [any-item-in-the-game] [amount]
    Allows bot owner and server administrators to spawn/give any equipment,
    shop item, material, currency, auction relic, fish, or custom item to any player.
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
            "- 🚫 *Yuna pouts and folds her arms!* \"Only the bot owner and server administrators have the celestial power to spawn items with `y!giveout`!\""
        )
        return

    if not args:
        embed = discord.Embed(
            title="🎁 Yuna's Celestial Item Spawner (Admin Only)",
            description=(
                "Spawn and bestow any item in the entire game directly to a player's inventory or balance!\n\n"
                "**Usage:** `y!giveout @user [item name or ID] [quantity]`\n"
                "**Examples:**\n"
                "• `y!giveout @player ancient_hyperforged_helm`\n"
                "• `y!giveout @player 5 ancient_steel_ingot`\n"
                "• `y!giveout @player 1000 watermelons`\n"
                "• `y!giveout @player void_hammer`\n"
                "• `y!giveout @player lucky clover`\n"
                "• `y!giveout @player 5000000 berries`\n"
                "• `y!giveout @player 10 fish`\n\n"
                "**Supported Catalogs:**\n"
                "• 🛡️ **Equipment:** Weapons, Helmets, Chestplates, Leggings, Boots, Accessories (all sets)\n"
                "• 🪙 **Materials & Consumables:** Ingots, Pearls, Cores, Pocket-Watches, Elixirs, Baits\n"
                "• 📦 **Casino Curio Shop:** Shields, Clovers, Energy Drinks, Masks, Diamonds\n"
                "• 🍉 **Currencies:** Watermelons, Berries, Fresh Fish\n"
                "• 🏆 **Auction Relics:** Trophies, Crowns, Artifacts"
            ),
            color=0xF1C40F
        )
        embed.set_footer(text="Admin Item Spawner • Yuna's Celestial Vault")
        await _safe_send_reply(message, embed=embed)
        return

    target_user = None
    target_id = None

    # 1. Check direct mentions first
    if message.mentions:
        for m in message.mentions:
            if client and client.user and m.id == client.user.id:
                continue
            target_user = m
            target_id = str(m.id)
            break

    # 2. Extract target if ID or mention passed in args
    remaining_tokens = []
    for token in args:
        clean = token.strip()
        if not clean:
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
            elif clean == target_id:
                continue
        remaining_tokens.append(clean)

    # 3. Check guild members by name if ID still unresolved
    if not target_id and message.guild and getattr(message.guild, "members", None) and remaining_tokens:
        clean_first = remaining_tokens[0].lower()
        try:
            for m in message.guild.members:
                m_name = getattr(m, "name", "").lower()
                m_nick = getattr(m, "display_name", "").lower()
                if clean_first in (m_name, m_nick):
                    if YUNA_ID_GUARD_AVAILABLE and yuna_id_guard and not yuna_id_guard.is_valid_guild_target(m, clean_first):
                        continue
                    target_user = m
                    target_id = str(m.id)
                    remaining_tokens = remaining_tokens[1:]
                    break
        except Exception:
            pass

    if not target_id:
        await _safe_send_reply(
            message,
            "- ⚠️ *Yuna tilts her head* \"Please mention a user or provide their User ID! Usage: `y!giveout @user [item] [amount]`\""
        )
        return

    # Attempt to resolve target_user object if missing
    if not target_user:
        if message.guild:
            try:
                target_user = message.guild.get_member(int(target_id))
            except Exception:
                pass
        if not target_user and client:
            try:
                target_user = client.get_user(int(target_id)) or await client.fetch_user(int(target_id))
            except Exception:
                pass

    if not remaining_tokens:
        await _safe_send_reply(
            message,
            "- ⚠️ *Yuna blinks* \"Which item do you want to give? Usage: `y!giveout @user [item name or ID] [amount]`\""
        )
        return

    # 4. Extract quantity (can be at beginning or end of tokens)
    qty = 1
    t0_clean = remaining_tokens[0].rstrip("xX").lstrip("xX")
    parsed_qty0 = parse_currency_amount(t0_clean)
    if parsed_qty0 is not None and parsed_qty0 > 0 and len(remaining_tokens) > 1:
        qty = parsed_qty0
        remaining_tokens = remaining_tokens[1:]
    else:
        t_last_clean = remaining_tokens[-1].rstrip("xX").lstrip("xX")
        parsed_qty_last = parse_currency_amount(t_last_clean)
        if parsed_qty_last is not None and parsed_qty_last > 0 and len(remaining_tokens) > 1:
            qty = parsed_qty_last
            remaining_tokens = remaining_tokens[:-1]

    # Enforce safe bounds
    qty = max(1, min(int(qty), 1_000_000_000_000_000))

    item_query = " ".join(remaining_tokens).strip()
    if not item_query:
        await _safe_send_reply(
            message,
            "- ⚠️ *Yuna tilts her head* \"Please specify which item to give out! Usage: `y!giveout @user [item] [amount]`\""
        )
        return

    # 5. Build Unified Item Catalog
    catalog = {}

    # Currencies & Catches
    catalog["watermelons"] = {"id": "watermelons", "name": "Watermelons", "emoji": "🍉", "category": "Currency", "type": "currency_watermelon"}
    catalog["watermelon"] = catalog["watermelons"]
    catalog["melon"] = catalog["watermelons"]
    catalog["melons"] = catalog["watermelons"]
    catalog["berries"] = {"id": "berries", "name": "Berries", "emoji": "🫐", "category": "Currency", "type": "currency_berries"}
    catalog["berry"] = catalog["berries"]
    catalog["fish"] = {"id": "fish", "name": "Fresh Fish", "emoji": "🐟", "category": "Fishing Catch", "type": "inventory"}

    # Junk items
    junk_list = [
        ("junk_plastic_bag", "Plastic Bag", "🛍️"),
        ("junk_rubber_duck", "Rubber Duck", "🦆"),
        ("junk_fake_beard", "Fake Beard", "🧔"),
        ("junk_bent_spoon", "Bent Spoon", "🥄"),
        ("junk_fake_mustache", "Fake Mustache", "🥸"),
        ("junk_dented_can", "Dented Can", "🥫"),
        ("junk_deflated_balloon", "Deflated Balloon", "🎈"),
        ("junk_tangled_wires", "Tangled Wires", "🔌"),
        ("junk_unopened_spam_mail", "Unopened Spam Mail", "✉️"),
        ("junk_empty_potion_flask", "Empty Potion Flask", "🧪")
    ]
    for j_id, j_name, j_em in junk_list:
        catalog[j_id] = {"id": j_id, "name": j_name, "emoji": j_em, "category": "Junk / Trinket", "type": "inventory"}

    # Casino Shop Items
    for k, v in SHOP_ITEMS.items():
        s_type = str(v.get("type", "item")).title()
        catalog[k] = {
            "id": k,
            "name": v.get("name", k.replace("_", " ").title()),
            "emoji": v.get("emoji", "📦"),
            "category": f"Casino Shop ({s_type})",
            "type": "inventory",
            "desc": v.get("desc", "")
        }

    # Materials Catalog
    try:
        from yuna_equipment import MATERIALS_CATALOG
        for k, v in MATERIALS_CATALOG.items():
            s_type = str(v.get("type", "material")).title()
            catalog[k] = {
                "id": k,
                "name": v.get("name", k.replace("_", " ").title()),
                "emoji": v.get("emoji", "🪙"),
                "category": f"Material ({s_type})",
                "type": "inventory",
                "desc": v.get("desc", "")
            }
    except Exception:
        pass

    # Auction Catalog
    try:
        from yuna_rpg import AUCTION_CATALOG
        for k, v in AUCTION_CATALOG.items():
            catalog[k] = {
                "id": k,
                "name": v.get("name", k.replace("_", " ").title()),
                "emoji": v.get("emoji", "🏆"),
                "category": "Auction Relic / Trophy",
                "type": "auction_relic",
                "desc": v.get("buff_desc", v.get("desc", ""))
            }
    except Exception:
        pass

    # Battle Shop Items
    try:
        from yuna_rpg import BATTLE_SHOP_ITEMS
        for k, v in BATTLE_SHOP_ITEMS.items():
            if k not in catalog:
                s_slot = str(v.get("slot", "gear")).title()
                catalog[k] = {
                    "id": k,
                    "name": v.get("name", k.replace("_", " ").title()),
                    "emoji": v.get("emoji", "⚔️"),
                    "category": f"Battle Shop ({s_slot})",
                    "type": "inventory",
                    "rarity": v.get("rarity", "common"),
                    "desc": v.get("desc", "")
                }
    except Exception:
        pass

    # ALL_EQUIPMENT
    try:
        from yuna_equipment import ALL_EQUIPMENT
        for k, v in ALL_EQUIPMENT.items():
            s_slot = str(v.get("slot", "gear")).title()
            catalog[k] = {
                "id": k,
                "name": v.get("name", k.replace("_", " ").title()),
                "emoji": v.get("emoji", "🛡️"),
                "category": f"Equipment ({s_slot})",
                "type": "inventory",
                "rarity": v.get("rarity", "common"),
                "req_level": v.get("req_level", 1),
                "target_class": v.get("target_class", None),
                "desc": v.get("desc", "")
            }
    except Exception:
        pass

    # 6. Item Matching
    q = item_query.lower().strip().replace("-", " ")
    q_norm = q.replace(" ", "_")

    matched_item = None
    # 1. Exact ID
    if q in catalog:
        matched_item = catalog[q]
    elif q_norm in catalog:
        matched_item = catalog[q_norm]
    else:
        # 2. Exact Name
        for k, v in catalog.items():
            if v["name"].lower() == q:
                matched_item = v
                break

    if not matched_item:
        # 3. Substring match
        substr_matches = []
        for k, v in catalog.items():
            if q in k or q_norm in k or q in v["name"].lower():
                substr_matches.append(v)
        if substr_matches:
            substr_matches.sort(key=lambda x: (len(x["name"]), x["name"]))
            matched_item = substr_matches[0]

    if not matched_item:
        # 4. Multi-word search
        words = [w for w in q.split() if len(w) > 1]
        if words:
            word_matches = []
            for k, v in catalog.items():
                haystack = (k + " " + v["name"]).lower()
                if all(w in haystack for w in words):
                    word_matches.append(v)
            if word_matches:
                word_matches.sort(key=lambda x: len(x["name"]))
                matched_item = word_matches[0]

    # 5. Raw item fallback if admin typed a clean identifier (e.g. custom_token)
    if not matched_item:
        if re.fullmatch(r'[a-zA-Z0-9_-]+', item_query):
            raw_id = item_query.lower().replace("-", "_")
            matched_item = {
                "id": raw_id,
                "name": raw_id.replace("_", " ").title(),
                "emoji": "📦",
                "category": "Custom Inventory Item",
                "type": "inventory",
                "desc": "Custom administrative item."
            }
        else:
            await _safe_send_reply(
                message,
                f"- ❌ *Yuna shakes her head* \"Could not find any item matching `{item_query}`! Double-check the item name or ID (e.g. `ancient_hyperforged_helm`, `void_hammer`, `clover`, `watermelons`, `berries`).\""
            )
            return

    item_id = matched_item["id"]
    item_name = matched_item["name"]
    item_emoji = matched_item.get("emoji", "📦")
    item_cat = matched_item.get("category", "Item")
    item_type = matched_item.get("type", "inventory")

    # 7. Apply to database atomically
    async with _LOCK:
        _ensure_fresh_data()
        if target_id not in _USER_STATS:
            _USER_STATS[target_id] = _create_default_user()
        user = _USER_STATS[target_id]
        _ensure_user_defaults(user)

        old_val = 0
        new_val = 0
        stat_audit_field = ""

        if item_type == "currency_watermelon":
            old_val = user.get("watermelons", 0)
            new_val = max(0, old_val + qty)
            user["watermelons"] = new_val
            stat_audit_field = "watermelons"
        elif item_type == "currency_berries":
            old_val = user.get("berries", 0)
            new_val = max(0, old_val + qty)
            user["berries"] = new_val
            stat_audit_field = "berries"
        elif item_type == "auction_relic":
            inv = user.setdefault("inventory", {})
            old_val = inv.get(item_id, 0)
            new_val = max(0, old_val + qty)
            inv[item_id] = new_val
            trophies = user.setdefault("auction_trophies", [])
            if isinstance(trophies, list):
                if item_id not in trophies:
                    trophies.append(item_id)
            elif isinstance(trophies, dict):
                trophies[item_id] = trophies.get(item_id, 0) + qty
            stat_audit_field = f"item_{item_id}"
        else:
            inv = user.setdefault("inventory", {})
            old_val = inv.get(item_id, 0)
            new_val = max(0, old_val + qty)
            inv[item_id] = new_val
            stat_audit_field = f"item_{item_id}"

        _USER_STATS[target_id] = user
        _log_player_stat_audit(
            target_id,
            stat_audit_field,
            f"{old_val:,}",
            f"{new_val:,}",
            f"admin_giveout item={item_id} qty=+{qty:,} by author={author_id}"
        )
        _save_data_sync(_USER_STATS)

    # 8. Build and send response embed
    target_display = getattr(target_user, "display_name", getattr(target_user, "name", f"<@{target_id}>"))
    rarity_badge = f"✨ **Rarity:** `{matched_item.get('rarity', '').upper()}`\n" if matched_item.get("rarity") else ""
    req_level_str = f"🔒 **Required Level:** `Lv. {matched_item['req_level']}`\n" if matched_item.get("req_level") else ""
    desc_str = f"\n*\"{matched_item['desc']}\"*\n" if matched_item.get("desc") else ""

    embed = discord.Embed(
        title=f"🎁 Admin Item Granted! • {item_emoji} {item_name}",
        description=(
            f"**A celestial gift has materialized into the player's possession!**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **Recipient:** <@{target_id}> (`{target_display}`)\n"
            f"📦 **Item Granted:** {item_emoji} **{item_name}** (`{item_id}`)\n"
            f"🏷️ **Category:** `{item_cat}`\n"
            f"{rarity_badge}{req_level_str}"
            f"🔢 **Quantity Added:** `+{qty:,}`\n"
            f"📊 **New Total in Possession:** **`{new_val:,}`**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━{desc_str}\n"
            f"*- Yuna waves her radiant celestial scepter and seals the transaction in the astral ledger.*"
        ),
        color=0xF1C40F
    )
    if target_user and hasattr(target_user, "display_avatar") and target_user.display_avatar:
        embed.set_thumbnail(url=target_user.display_avatar.url)
    author_name = getattr(message.author, "display_name", getattr(message.author, "name", author_id))
    embed.set_footer(text=f"Admin: {author_name} • Yuna's Celestial Vault")
    await _safe_send_reply(message, embed=embed)

# ─── HELP CODEX & GUIDES ────────────────────────────────────────────────────

HELP_COLOR = discord.Color.from_rgb(255, 105, 180) # Yuna's signature vibrant pink

HELP_PAGES_META = [
    {
        "title": "◈ Yuna Codex • General & Economy (1/5)",
        "desc": "Core currency, karma, profile, curio shop, and daily shifts.\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "fields": [
            (
                "◈ Pouch, Profile & Allowance",
                "• `y!balance` (`y!bal`, `y!profile`) — Check berries, virtue, sin, spouse, buffs\n"
                "• `y!daily` (`y!claim`) — Claim daily berries (150 base + streak multiplier)\n"
                "• `y!tasks` (`y!quests`) — Daily objectives & grand bounty bonus\n"
                "• `y!inflation` (`y!econ`) — Live economy inflation & market statistics",
                False
            ),
            (
                "💖 Transfers, Virtue & Sins ❤️‍🔥",
                "• `y!pay @user <amt>` (`y!give`, `y!trade`) — Direct berry transfers\n"
                "• `y!aid @user` — Assist a player (+2% success per Virtue point)\n"
                "• `y!donate <amt>` — Gift berries to a random active player & gain Virtue\n"
                "• `y!steal @user` (`y!rob`) — Attempt pickpocketing (defended by wards)",
                False
            ),
            (
                "◈ Shop, Inventory & Work",
                "• `y!shop` & `y!buy <item> [qty]` — Purchase charms, consumables & rings\n"
                "• `y!inventory` (`y!inv`) — 4-page categorized backpack\n"
                "• `y!use <item>` — Consume potions, charms & specialty items\n"
                "• `y!work` & `y!fish` — Honest shifts or fishing for rare loot & pearls",
                False
            )
        ]
    },
    {
        "title": "🎲 Yuna Codex • Casino & Wagering (2/5)",
        "desc": "Table games, card games, and high-multiplier gambling.\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "fields": [
            (
                "🎲 Card & Table Games",
                "• `y!blackjack <amt>` (`y!bj`) — Classic 21 vs dealer Yuna (Hit / Stand)\n"
                "• `y!roulette <amt> [bet]` — 38-pocket wheel with Red/Black, Even/Odd, Columns\n"
                "• `y!dice <amt> [bet]` (`y!craps`) — 2d6 craps table with High/Low, Lucky 7\n"
                "• `y!poker <amt>` (`y!vp`) — 5-card video poker with interactive hold",
                False
            ),
            (
                "✦ Minigames & Multipliers",
                "• `y!mines <amt> [mines]` — 24-tile minefield with escalating cashouts\n"
                "• `y!crash <amt>` — Rising rocket multiplier; cash out before detonation\n"
                "• `y!higherlower <amt>` (`y!hl`) — Guess next card with climbing streak rewards\n"
                "• `y!slots <amt>` — 3-reel slot machine with 77x Lucky 7 jackpot\n"
                "• `y!wordle <amt>` — Progressive 5-stage word challenge with up to 40x payout\n"
                "• `y!coinflip <amt> [choice]` — Absurd flip with 2.5x payout",
                False
            )
        ]
    },
    {
        "title": "⚔ Yuna Codex • RPG & Progression (3/5)",
        "desc": "Character progression, armory, skills, arena, and auctions.\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "fields": [
            (
                "⛨ Character Profile & Armory",
                "• `y!profile` (`y!armory`, `y!equip`) — Interactive profile with gear inspection\n"
                "• `y!unequip <slot>` — Unequip gear from Head, Top, Legs, Weapon, or Accessory\n"
                "• `y!battleshop` & `y!bbuy <item>` — Purchase combat weapons, armor & elixirs",
                False
            ),
            (
                "✦ Skills & Arena Training",
                "• `y!skills` (`y!skill`) — Interactive skill codex to equip 4 active skills\n"
                "• `y!skill <name>` — Quick equip or toggle a skill in your active loadout\n"
                "• `y!skill auto` / `y!skill clear` — Auto-equip highest tier or clear loadout\n"
                "• `y!arena` & `y!train [stat]` — Train ATK, DEF, HP, SPD with berry sinks",
                False
            ),
            (
                "🍉 Watermelon & Berry Auctions 🫐",
                "• `y!auction [item]` — View active auction lot or inspect items\n"
                "• `y!bid <amount>` (`y!bid <item> <amount>`) — Place bids on current lot\n"
                "• `y!auctioncatalog` — Browse all rotating luxury flex items",
                False
            )
        ]
    },
    {
        "title": "⛨ Yuna Codex • Combat & Dungeons (4/5)",
        "desc": "Turn-based tactical dungeon raids and boss encounters.\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "fields": [
            (
                "⛨ GoD-HeLL Co-op Raid (10 Stages)",
                "• `y!godhell` (`y!dungeon`) — Descend into GoD-HeLL raid instance\n"
                "• `y!djoin [@host]` — Join an open server raid lobby\n"
                "• `y!dattack` / `y!dskill [name]` — Execute basic attack or cast class skill\n"
                "• `y!ddefend` (`y!parry`, `y!dodge`) — Reactive defensive stances\n"
                "• `y!dheal` & `y!dflee` — Use emergency medicine or retreat",
                False
            ),
            (
                "😈 Boss Battle: Juny (Heaven's Worst Angel)",
                "• `y!boss` (`y!juny`) — View active Juny boss encounter (triggers at 20+ Sin)\n"
                "• `y!attack` & `y!dodge` — Strike or enter evasive defense stance\n"
                "• `y!useitem <item>` — Combat elixirs, barriers, and blinding sand\n"
                "• `y!call aid @allies` — Summon up to 3 teammates into battle\n"
                "• `y!plead` & `y!negotiate` — Beg for mercy or strike dark pacts",
                False
            )
        ]
    },
    {
        "title": "💍 Yuna Codex • Social & Matrimony (5/5)",
        "desc": "Romance ceremonies, shared vaults, dares, and achievements.\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "fields": [
            (
                "💍 Romance & Matrimony",
                "• `y!marry @user` — Propose with Yuna's marriage ceremony\n"
                "• `y!marriage [@user]` (`y!spouse`) — View marriage certificate & synergy\n"
                "• `y!date` & `y!kiss` — Couple dates & affection sparks for shared vault\n"
                "• `y!shared` (`y!joint`) — Couple's shared vault with daily yield\n"
                "• `y!doubleaid` & `y!doublesteal` — Co-op couple operations\n"
                "• `y!divorce` — Terminate marriage ceremony",
                False
            ),
            (
                "✦ Social, Media & Hall of Fame",
                "• `y!truth` & `y!dare` — Social challenges evaluated by peer & AI review\n"
                "• `y!leaderboard` (`y!lb`) — Server top rankings (Richest, Saintliest, Sins)\n"
                "• `y!achievements` (`y!ach`) — Browse 56 collectible achievements\n"
                "• `y!song` (`y!np`) & `y!play <song>` — Live Spotify Kizzy rich presence",
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
        color=0x2B2D31
    )
    for fname, fval, finline in meta["fields"]:
        embed.add_field(name=fname, value=fval, inline=finline)
    embed.set_footer(text=f"Page {page_idx + 1}/{len(HELP_PAGES_META)} • Jump with dropdown or type y!help <1-{len(HELP_PAGES_META)}>")
    return embed

class YunaHelpPaginationView(ResilientView):
    def __init__(self, author_id: str, current_page: int = 0):
        super().__init__(timeout=600)
        self.author_id = author_id
        self.current_page = max(0, min(len(HELP_PAGES_META) - 1, current_page))
        self._build_components()

    def _build_components(self):
        self.clear_items()
        max_idx = len(HELP_PAGES_META) - 1

        options = [
            discord.SelectOption(
                label="◈ Page 1: General & Economy",
                value="0",
                description="Balance, dailies, tasks, aid, steal, shop, work",
                default=(self.current_page == 0)
            ),
            discord.SelectOption(
                label="🎲 Page 2: Casino & Wagering",
                value="1",
                description="Blackjack, roulette, poker, dice, mines, crash, slots",
                default=(self.current_page == 1)
            ),
            discord.SelectOption(
                label="⚔ Page 3: RPG & Progression",
                value="2",
                description="Profile, armory, skills, arena training, auctions",
                default=(self.current_page == 2)
            ),
            discord.SelectOption(
                label="⛨ Page 4: Combat & Dungeons",
                value="3",
                description="GoD-HeLL co-op raid, Juny boss battle, party tactics",
                default=(self.current_page == 3)
            ),
            discord.SelectOption(
                label="💍 Page 5: Social & Matrimony",
                value="4",
                description="Marriage, shared vault, dares, achievements, Spotify",
                default=(self.current_page == 4)
            ),
        ]
        select = discord.ui.Select(
            placeholder="Select a category...",
            options=options,
            row=0
        )
        select.callback = self.on_select_page
        self.add_item(select)

        prev_btn = discord.ui.Button(
            label="‹ Previous",
            style=discord.ButtonStyle.secondary,
            disabled=(self.current_page <= 0),
            row=1
        )
        prev_btn.callback = self.on_prev_click
        self.add_item(prev_btn)

        page_btn = discord.ui.Button(
            label=f"Page {self.current_page + 1}/{len(HELP_PAGES_META)}",
            style=discord.ButtonStyle.secondary,
            disabled=True,
            row=1
        )
        self.add_item(page_btn)

        next_btn = discord.ui.Button(
            label="Next ›",
            style=discord.ButtonStyle.secondary,
            disabled=(self.current_page >= max_idx),
            row=1
        )
        next_btn.callback = self.on_next_click
        self.add_item(next_btn)

    async def _handle_page_update(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.author_id:
            await _safe_send_ephemeral(interaction, "Type `y!help` to open your own interactive codex!")
            return
        self._build_components()
        embed = build_help_page_embed(self.current_page)
        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(embed=embed, view=self)
            elif interaction.message:
                await interaction.message.edit(embed=embed, view=self)
        except Exception:
            pass

    async def on_select_page(self, interaction: discord.Interaction):
        vals = interaction.data.get("values", [])
        if vals and vals[0].isdigit():
            self.current_page = max(0, min(len(HELP_PAGES_META) - 1, int(vals[0])))
        await self._handle_page_update(interaction)

    async def on_prev_click(self, interaction: discord.Interaction):
        if self.current_page > 0:
            self.current_page -= 1
        await self._handle_page_update(interaction)

    async def on_next_click(self, interaction: discord.Interaction):
        if self.current_page < len(HELP_PAGES_META) - 1:
            self.current_page += 1
        await self._handle_page_update(interaction)

async def handle_help(message, client, args: list = None):
    """Shows gambling, games & karma commands guide as rich Discord Embeds."""
    target_page = None
    if args:
        first = args[0].lower().strip()
        if first.isdigit():
            target_page = max(0, min(len(HELP_PAGES_META) - 1, int(first) - 1))
        elif first in ("page", "p") and len(args) > 1 and args[1].isdigit():
            target_page = max(0, min(len(HELP_PAGES_META) - 1, int(args[1]) - 1))

    if not args or target_page is not None:
        p = 0 if target_page is None else target_page
        author_id = str(message.author.id)
        embed = build_help_page_embed(p)
        view = YunaHelpPaginationView(author_id, current_page=p)
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

    elif sub_topic in ("inflation", "economy", "market", "marketinfo", "inf", "econ"):
        embed = build_inflation_embed()
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
            value=(
                "`y!dice <amount> [bet]`\n"
                "*Aliases:* `y!roll`, `y!craps`, `y!dicebet`\n"
                "*Currency Shortcuts:* `half`, `all`, `50%`, `1k`, `1m`, `1b`, `1t`\n"
                "*Examples:* `y!dice half`, `y!dice all`, `y!dice 1k low`, `y!dice 50 seven`, `y!roll half vs`, `y!dice 1m`"
            ),
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
            "• `y!shared deposit <amt|half|all|1k|1m|1b|1t>` — Deposit berries into joint vault\n"
            "• `y!shared withdraw <amt|half|all|1k|1m|1b|1t>` — Withdraw berries from joint vault"
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

    elif sub_topic in ("horn", "devilhorn", "curse", "hellfire", "blackmail", "sinsurge"):
        embed = discord.Embed(
            title="🦹 Command Guide: Devil Horn Sinister Commands",
            description="Dark sorceries unlocked by bearing **Juny's Devil Horn** (+60 Sin Cap). Requires Sin points to cast!",
            color=0x660000
        )
        embed.add_field(name="y!curse @target", value="Cursed hex! Consumes 5 Sin to inflict **10 turns of severe bad luck** on the target.", inline=False)
        embed.add_field(name="y!hellfire @target", value="Hellish combustion! Consumes 10 Sin to incinerate **20% of target's berries** into ash.", inline=False)
        embed.add_field(name="y!blackmail @target <amount>", value="Sinister extortion! Consumes 8 Sin to extort berries with a 70% success rate (fails if target has Heavenly Shield).", inline=False)
        embed.add_field(name="y!sinsurge", value="Demonic overload! Consumes 15 Sin to gain **+50% Payout Multiplier** for your next 5 gambles/crimes.", inline=False)
        embed.set_footer(text="Juny's Relic Codex • Devil Horn Required")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("skills", "skill", "weirdskills", "loadout", "dskill", "marital"):
        embed = discord.Embed(
            title="✨ Command Guide: RPG Skill Loadouts & Combat Stances",
            description="Equip active skill loadouts, trigger team synergies, and cast class spells in GoD-HeLL!",
            color=HELP_COLOR
        )
        embed.add_field(
            name="⚔️ 4 Active Skill Loadout System",
            value=(
                "• Every player can equip up to **4 Active Skills** at a time from their unlocked class and marital repertoire.\n"
                "• Skills unlock progressively as your Battle Level increases across your archetype's tiers (Lv. 1, 50, 150, 300, 600).\n"
                "• Manage your active loadout anytime using `y!skills` or the interactive dropdown in `y!equip`!"
            ),
            inline=False
        )
        embed.add_field(
            name="🎯 3 Tactical Combat Stances",
            value=(
                "• 🔴 **Strike (Action Offensive):** High-damage strikes, armor pierces, crits, and execution thresholds.\n"
                "• 🟢 **Defend (Protection & Recovery):** Barriers, damage mitigation, single-ally heals, team blooms, and revives.\n"
                "• 🔵 **Tactical (Buffs & Control):** Party ATK buffs, cleanses, MP generation, status debuffs, and staggers."
            ),
            inline=False
        )
        embed.add_field(
            name="🤝 Party-Oriented Abilities",
            value=(
                "• ✦ **Healer:** Smart lowest-ally healing (`Mending Light`), party-wide burst blooms (`Radiant Bloom`), party cleanses (`Purifying Grace`), team barriers (`Acolyte's Aegis`), and resurrection hymns (`Resurrection Hymn`).\n"
                "• ■ **Defender:** Frontline taunts (`Provoke & Rally`), intercepting party damage at 50% discount (`Guardian Intervention`), and team damage mitigation (`Phalanx Formation`).\n"
                "• ⚔ **DPS & Mage:** Party ATK rallying cries (`Battle Cry`), crit focus, and mana conduits (`Mana Conduit`)."
            ),
            inline=False
        )
        embed.add_field(
            name="In-Dungeon Casting",
            value="Cast skills during GoD-HeLL turns with `y!dskill <name>` or via the in-combat **[✨ Skill Select]** button! Build MP with **[Strike]** (+15 MP) or **[Parry/Block]** (+20 MP).",
            inline=False
        )
        embed.set_footer(text="Yuna's RPG • Skill Loadout Codex")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("class", "classes", "oath", "archetype", "rpgclass"):
        embed = discord.Embed(
            title="🛡️ Command Guide: y!class (Permanent Archetype Oath)",
            description="Swear an unbreakable celestial oath to one of 5 distinct RPG combat archetypes!",
            color=HELP_COLOR
        )
        embed.add_field(
            name="📜 The 5 Permanent Archetypes",
            value=(
                "• ◆ **Physicist [QUANTUM] (6.0x Cost Tier):** Focuses on True Damage, entropy siphons, and thermonuclear cataclysms. Special Stat: `Intelligence (INT)`.\n"
                "• ⚔ **Physical DPS [PHYSICAL] (15.0x Expensive Tier):** Unmatched physical burst, bleed pressure, and execute finishers below 20% HP. Special Stat: `Ferocity (FER)`.\n"
                "• ■ **Defender [DEFENSE] (2.5x Cost Tier):** Immovable tank that taunts bosses, intercepts party damage, and reflects attacks. Special Stat: `Tenacity (TEN)`.\n"
                "• ✦ **Healer [HOLY] (1.0x Base Tier):** Divine saint with smart ally heals, party-wide blooms, shields, and resurrection hymns. Special Stat: `Devotion (DEV)`.\n"
                "• ★ **Mage [ARCANE] (10.0x Cost Tier):** Elemental master with immense MP pools, freezing time-stasis, and cataclysmic spells. Special Stat: `Arcana (ARC)`."
            ),
            inline=False
        )
        embed.add_field(
            name="⚠️ Permanent Choice & Entry Requirement",
            value="Your archetype choice is **STRICTLY PERMANENT**. You must swear your oath with `y!class` before entering `y!arena` training or descending into `y!godhell`!",
            inline=False
        )
        embed.add_field(name="Syntax", value="`y!class` — Opens the interactive dossier and oath confirmation menu.", inline=False)
        embed.set_footer(text="Yuna's RPG • Oath of Archetypes")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("arena", "train", "training", "colosseum"):
        embed = discord.Embed(
            title="⚔️ Command Guide: y!arena & y!train",
            description="Train your combat attributes, advance battle levels, and forge berries into raw combat might!",
            color=HELP_COLOR
        )
        embed.add_field(
            name="⏱️ 12-Hour Training Quota",
            value="Training is limited to a maximum of **100 levels every 12 hours** to ensure fair progression across all timezones.",
            inline=False
        )
        embed.add_field(
            name="💰 Economic Training Cost Multipliers",
            value=(
                "Training costs are determined by your class tier multiplier:\n"
                "• **Healer:** `1.0x` (Base economic curve)\n"
                "• **Defender:** `2.5x`\n"
                "• **Physicist:** `6.0x`\n"
                "• **Mage:** `10.0x`\n"
                "• **Physical DPS:** `15.0x` (High-roller tier)"
            ),
            inline=False
        )
        embed.add_field(
            name="🏋️ Training Stats & Syntax",
            value=(
                "• `y!arena` — View combat profile, level, training stats, and quota progress.\n"
                "• `y!train atk [levels]` — Increases Physical Attack.\n"
                "• `y!train def [levels]` — Increases Physical Defense & mitigations.\n"
                "• `y!train hp [levels]` — Increases Maximum HP pool.\n"
                "• `y!train special [levels]` — Increases your class-specific Special Stat (+4 per level).\n"
                "• `y!train all [levels]` — Trains all 4 core combat stats evenly!\n"
                "*Example:* `y!train atk 10` or `y!train all 5`"
            ),
            inline=False
        )
        embed.set_footer(text="Yuna's RPG • Training Grounds")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("juny", "boss", "combat", "plead", "fight", "negotiate"):
        embed = discord.Embed(
            title="😈 Command Guide: Juny-HWA Boss Encounter",
            description="Heaven's Worst Angel descends to claim your overdue soul when Sin reaches 20+!",
            color=0x660000
        )
        embed.add_field(
            name="⚡ Encounter Triggers & Options",
            value=(
                "• Juny appears automatically when your Sin reaches **20 or higher**.\n"
                "• `y!boss` (or `y!juny`) — Inspect active encounter status, party members, and Juny's HP.\n"
                "• `y!plead` — Beg on your knees for mercy. Juny might spare you in exchange for berries or Virtue.\n"
                "• `y!negotiate` — Strike a deal: Escape for 20% berries, or 40% for a 3-hour Devil's Contract!\n"
                "• `y!fight` — Refuse to kneel and challenge Juny to turn-based combat!"
            ),
            inline=False
        )
        embed.add_field(
            name="⚔️ Combat Turns & Summons",
            value=(
                "• `y!attack` — Strike Juny with weapon/holy damage.\n"
                "• `y!dodge` — Enter defensive evasion (+40% dodge for 1 round).\n"
                "• `y!useitem <item>` — Deploy battle items: Elixir (+50 HP), Holy Smite (150 True DMG), Sand (Blinds Juny), Rubber Hammer.\n"
                "• `y!call aid @friends` — Summon up to 3 allies to join your boss battle party!\n"
                "• 🏆 Defeating Juny has a chance to drop the forbidden **Juny's Devil Horn**!"
            ),
            inline=False
        )
        embed.set_footer(text="Juny-HWA • Heaven's Worst Angel")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("pact", "contract", "devilcontract", "icecream", "walk", "bench", "askjuny"):
        embed = discord.Embed(
            title="📜 Command Guide: Devil's Contract & Juny Interactions",
            description="Live as a bonded mortal under a 3-hour Devil's Contract with Juny!",
            color=0x4A0072
        )
        embed.add_field(
            name="⏳ 3-Hour Contract Hub",
            value=(
                "• `y!pact` — Check your remaining contract duration and active relationship perks.\n"
                "• During the pact, all bot dialogue dynamically adopts Juny's haughty, sarcastic demon personality!"
            ),
            inline=False
        )
        embed.add_field(
            name="🌹 Companion Leisure & Dates",
            value=(
                "• `y!icecream` — Treat Juny to twilight gelato in town.\n"
                "• `y!walk` — Take a quiet stroll through the twilight park.\n"
                "• `y!bench` — Sit together on a park bench and enjoy the night breeze."
            ),
            inline=False
        )
        embed.add_field(
            name="💬 Interactive AI Conversations",
            value=(
                "• `y!askjuny <question>` — Ask Juny anything! Powered by AI, Juny will respond directly in character.\n"
                "• ⚡ *Retaliation System: Saying vulgar things or threatening her will cause Juny to unleash lethal retaliation attacks (Divine Retribution, Twilight Apocalypse, Celestial Onslaught)!*"
            ),
            inline=False
        )
        embed.set_footer(text="Yuna's Romance & Sin • Devil's Contract")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("godhell", "dungeon", "god-hell", "raid", "dcallaid", "djoin"):
        embed = discord.Embed(
            title="🌋 Command Guide: GoD-HeLL Co-op Raid Dungeon",
            description="Descend into Empress Yuna's premier 10-stage raid dungeon with scaling bosses and co-op synergies!",
            color=HELP_COLOR
        )
        embed.add_field(
            name="🔥 Stages & Boss Encounters",
            value="10 progressive dungeon stages featuring 3 major raid bosses: **Mamon (Greed Sovereign)** at Stage 3, **Executioner** at Stage 7, and **Lucifer (Lord of the Abyss)** at Stage 10!",
            inline=False
        )
        embed.add_field(
            name="🤝 3-Player Co-op Parties & Synergies",
            value=(
                "• `y!dcallaid @allies` (or click **[🤝 Call Aid]**) — Invite up to 2 companions into your raid party!\n"
                "• `y!djoin @host` — Join an active server raid party!\n"
                "• **Trinity Overdrive:** If party uses Strike + Tactical + Defend in the same round, party deals **+60% damage**, gets **100% Critical Strike**, and restores +50 MP!"
            ),
            inline=False
        )
        embed.add_field(
            name="🎮 Tactical Stances & Directional Dodges",
            value=(
                "• 🔴 **Strike beats 🔵 Tactical (+60% dmg)** | 🔵 **Tactical breaks 🟢 Defend (+60% true dmg)** | 🟢 **Defend deflects 🔴 Strike (-40% dmg)**.\n"
                "• Bosses telegraph directional attacks: **Dodge Left** against Right Sweeps, **Dodge Right** against Left Sweeps, and **Parry/Block** Center Smashes to counter-riposte!"
            ),
            inline=False
        )
        embed.add_field(
            name="💖 Divine Assist & Combat Controls",
            value=(
                "• `y!dyuna` (or click **[💖 Summon Yuna]**) — Call Empress Yuna once per raid for a full-party 100% heal and 1-round damage immunity!\n"
                "• Controls: `y!dskill <name>`, `y!dattack`, `y!dguard`, `y!ddodgeleft`, `y!ddodgeright`, `y!ditem`, `y!dflee`."
            ),
            inline=False
        )
        embed.set_footer(text="Yuna's RPG • GoD-HeLL Abyss")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("equip", "gear", "equipment", "battleshop", "bbuy", "armory"):
        embed = discord.Embed(
            title="🗡️ Command Guide: Combat Equipment & Battle Shop",
            description="Equip forged weapons, heavy armor, enchanted accessories, and battle consumables!",
            color=HELP_COLOR
        )
        embed.add_field(
            name="🏪 The Battle Shop",
            value=(
                "• `y!battleshop` — Browse the armory catalog with live stock and pricing.\n"
                "• `y!bbuy <item>` — Purchase combat gear (e.g. `y!bbuy katana`, `y!bbuy aegis_shield`, `y!bbuy elixir 5`)."
            ),
            inline=False
        )
        embed.add_field(
            name="🛡️ Interactive Gear Armory",
            value=(
                "• `y!equip` — Opens the interactive Discord select menus to equip Weapons, Armor, Accessories, and your 4 Active Skills!\n"
                "• `y!unequip <slot>` — Unequips an equipped slot."
            ),
            inline=False
        )
        embed.add_field(
            name="🎒 Tactical Battle Consumables",
            value=(
                "• **Stagger Grenade:** Deals 25,000 True Damage and stuns boss for 1 round!\n"
                "• **Smoke Bomb:** Grants the entire raid party 100% Dodge for 1 turn!\n"
                "• **Adrenaline Shot:** Grants +50% ATK and +30 MP to all party members!\n"
                "• **Phoenix Feather:** Mid-battle resurrection reviving a dead ally with 60% HP & MP!\n"
                "• **Abyssal Elixir:** Restores +50% HP and +50 MP during combat."
            ),
            inline=False
        )
        embed.set_footer(text="Yuna's RPG • Equipment & Battle Shop")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("auction", "auctions", "bid", "auctioncatalog"):
        embed = discord.Embed(
            title="👑 Command Guide: Yuna's Imperial Berry Auctions",
            description="High-roller berry sink with permanent account-wide stat perks and trophy flexes!",
            color=0xF1C40F
        )
        embed.add_field(
            name="🏆 How Auctions Work",
            value=(
                "• Yuna puts prestigious luxury and legendary relics up for live auction.\n"
                "• Winning an auction grants **permanent passive stat perks** (increased ATK, DEF, Crit, Lifesteal, Berry yield, etc.) displayed on your `y!bal` profile!"
            ),
            inline=False
        )
        embed.add_field(
            name="💰 Bidding Syntax & Rules",
            value=(
                "• `y!auction` — View the currently active auction, current high bidder, and remaining time.\n"
                "• `y!bid <amount>` — Place a bid on the active auction (e.g. `y!bid 50m` or `y!bid 1b`).\n"
                "• `y!bid <alias> <amount>` — Place a bid referencing the item alias (e.g. `y!bid spoon 600m`).\n"
                "• **Instant Refunds:** If someone outbids you, your berries are returned to your pouch immediately!\n"
                "• **Anti-Snipe:** Bids placed in the final 3 minutes extend the auction timer by 3 minutes."
            ),
            inline=False
        )
        embed.add_field(name="Catalog Inspection", value="`y!auctioncatalog` — Browse all catalog items, numbers, aliases, starting bids, and perks!", inline=False)
        embed.set_footer(text="Yuna's Imperial Auctions • Luxury Flex")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("work", "job", "shift", "crime", "fish", "fishing"):
        embed = discord.Embed(
            title="💼 Command Guide: Work, Crime & Fishing",
            description="Earn honest wages, embark on risky underworld heists, or cast your line into Yuna's pond!",
            color=HELP_COLOR
        )
        embed.add_field(
            name="💼 Honest Work (`y!work`)",
            value="Work honest shifts (+2% wage per 💖 Virtue, +15% / +25% Marriage Ring bonus, +20% Magnet bonus). 25% chance to earn +1 Virtue!",
            inline=False
        )
        embed.add_field(
            name="🦹 Underworld Crime (`y!crime`)",
            value="High-risk heists for massive berry payouts (+2 ❤️‍🔥 Sin). Risk of getting caught by authorities and paying heavy restitution fines!",
            inline=False
        )
        embed.add_field(
            name="🎣 Peaceful Fishing (`y!fish`)",
            value="Cast your line into Empress Yuna's celestial pond. Catch common, rare, and legendary aquatic creatures or elusive Dragon Pearls (+1 Virtue)!",
            inline=False
        )
        embed.set_footer(text="Yuna's Economy • Occupations & Activities")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("shop", "store", "buy", "inventory", "inv", "use"):
        embed = discord.Embed(
            title="🏪 Command Guide: Curio Shop & Inventory",
            description="Browse mystical curios, consume potent charms, and inspect your pouch inventory!",
            color=HELP_COLOR
        )
        embed.add_field(
            name="🏪 Curio Shop Commands",
            value=(
                "• `y!shop` — Browse mystical charms, protective shields, and lifestyle relics.\n"
                "• `y!buy <item> [qty]` — Purchase items with berries (e.g. `y!buy shield` or `y!buy magnet 2`).\n"
                "• `y!inventory` (or `y!inv`) — Inspect your owned items, consumable stock, and active protective wards.\n"
                "• `y!use <item>` — Consume items from your inventory."
            ),
            inline=False
        )
        embed.add_field(
            name="✨ Key Relics & Charms",
            value=(
                "• 🛡️ **Divine Ward:** Blocks theft attempts and fines the thief.\n"
                "• 🍀 **Lucky Clover:** +25% theft success chance.\n"
                "• 🎭 **Phantom Mask:** 0 Sin from crime & +30% loot.\n"
                "• 💍 **Golden Wedding Ring:** Matrimonial allowance and work wage bonuses.\n"
                "• 💎 **Eternal Diamond:** Increases Joint Vault daily yield to 10%!"
            ),
            inline=False
        )
        embed.set_footer(text="Yuna's Curio Shop • Economy & Relics")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("giveout", "give-out", "giveitem", "give_out", "spawnitem", "admingive", "spawn"):
        embed = discord.Embed(
            title="🎁 Command Guide: y!giveout (Admin Only)",
            description="Summon and grant any item in the entire game directly to a player!",
            color=HELP_COLOR
        )
        embed.add_field(
            name="Permissions & Scope",
            value="• **Permissions:** Bot Owner or Server Administrators.\n• **Scope:** Weapons, Armor, Helmets, Boots, Accessories, Materials, Curio Shop Items, Currencies (Watermelons & Berries), Fish, Junk, and Auction Relics.",
            inline=False
        )
        embed.add_field(
            name="Syntax & Examples",
            value=(
                "• `y!giveout @user <item> [amount]` — Give item to user\n"
                "• `y!giveout @user <amount> <item>` — Alternative argument order\n"
                "• `y!giveout <user_id> <item> [amount]` — Target by Discord snowflake ID\n"
                "*Examples:*\n"
                "• `y!giveout @player ancient_hyperforged_helm`\n"
                "• `y!giveout @player 5 ancient_steel_ingot`\n"
                "• `y!giveout @player 1000 watermelons`\n"
                "• `y!giveout @player void_hammer`\n"
                "• `y!giveout @player 500k berries`"
            ),
            inline=False
        )
        embed.set_footer(text="Yuna's Codex • Celestial Administration")
        await _safe_send_reply(message, embed=embed)
        return

    # Fallback to page 0 if sub_topic didn't match any specific command guide
    author_id = str(message.author.id)
    embed = build_help_page_embed(0)
    view = YunaHelpPaginationView(author_id, current_page=0)
    await _safe_send_reply(message, embed=embed, view=view)
    return

# ─── DEVIL HORN SINISTER COMMAND HANDLERS ──────────────────────────────────

async def _check_horn_bearer(message, author_id: str) -> bool:
    stats = await _get_user_stats(author_id)
    if stats.get("inventory", {}).get("devil_horn", 0) <= 0:
        await _safe_send_reply(
            message,
            "🦹 **FORBIDDEN CELESTIAL RELIC REQUIRED!**\n"
            "*The dark incantation fails to ignite!* You must possess **Juny's Devil Horn** to channel this sinister power!"
        )
        return False
    return True

async def handle_curse(message, client, args: list):
    """Handles y!curse @target."""
    author_id = str(message.author.id)
    if not await _check_horn_bearer(message, author_id):
        return
    if not message.mentions and not args:
        await _safe_send_reply(message, "Usage: `y!curse @user` — Hexes a target with 10 turns of dark misfortune! (Costs 5 Sin)")
        return
    target = message.mentions[0] if message.mentions else None
    if not target:
        target_id_str = args[0].strip("<@!>")
        if target_id_str.isdigit():
            target = client.get_user(int(target_id_str))
    if not target or str(target.id) == author_id:
        await _safe_send_reply(message, "Specify a valid user other than yourself to curse!")
        return

    stats = await _get_user_stats(author_id)
    _, eff_sin = get_effective_morality(stats)
    if eff_sin < 5:
        await _safe_send_reply(message, f"You need at least **5 Sin** to cast `y!curse`! (Current Sin: `{eff_sin}`)")
        return

    target_id = str(target.id)
    async with _LOCK:
        _USER_STATS[author_id]["sin"] = max(0, _USER_STATS[author_id].get("sin", 0) - 5)
        _USER_STATS[target_id]["bad_luck_actions"] = _USER_STATS[target_id].get("bad_luck_actions", 0) + 10
        _save_data_sync(_USER_STATS)

    desc = (
        f"🩸 **DARK HEX CAST: CURSE OF THE WORST ANGEL!** 🩸\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<@{author_id}> raised **Juny's Devil Horn**, channeling black celestial lightning into {target.mention}!\n\n"
        f"• 🕯️ **Cost:** `-5 Sin` from <@{author_id}>\n"
        f"• 🌧️ **Cursed Misfortune:** {target.mention} is afflicted with **+10 Actions of Bad Luck**!\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    sent = await send_as_juny(message.channel, content=desc)
    if not sent:
        await _safe_send_reply(message, desc)

async def handle_hellfire(message, client, args: list):
    """Handles y!hellfire @target."""
    author_id = str(message.author.id)
    if not await _check_horn_bearer(message, author_id):
        return
    if not message.mentions and not args:
        await _safe_send_reply(message, "Usage: `y!hellfire @user` — Incinerates 20% of target's berry balance! (Costs 10 Sin)")
        return
    target = message.mentions[0] if message.mentions else None
    if not target:
        target_id_str = args[0].strip("<@!>")
        if target_id_str.isdigit():
            target = client.get_user(int(target_id_str))
    if not target or str(target.id) == author_id:
        await _safe_send_reply(message, "Specify a valid target user for Hellfire!")
        return

    stats = await _get_user_stats(author_id)
    _, eff_sin = get_effective_morality(stats)
    if eff_sin < 10:
        await _safe_send_reply(message, f"You need at least **10 Sin** to summon `y!hellfire`! (Current Sin: `{eff_sin}`)")
        return

    target_id = str(target.id)
    target_stats = await _get_user_stats(target_id)
    target_bal = target_stats.get("berries", 0)
    burn_amt = max(10, int(target_bal * 0.20)) if target_bal > 0 else 0

    async with _LOCK:
        _USER_STATS[author_id]["sin"] = max(0, _USER_STATS[author_id].get("sin", 0) - 10)
        _USER_STATS[target_id]["berries"] = max(0, target_bal - burn_amt)
        _save_data_sync(_USER_STATS)

    desc = (
        f"🔥💀 **INFERNAL COMBUSTION: HELLFIRE ERUPTS!** 💀🔥\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<@{author_id}> unleashed demonic flames through **Juny's Devil Horn**!\n"
        f"Pillars of violet hellfire erupted beneath {target.mention}'s pouch!\n\n"
        f"• 🕯️ **Cost:** `-10 Sin` from <@{author_id}>\n"
        f"• 🔥 **Incinerated:** `{burn_amt:,}` 🫐 reduced to glowing cinders!\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    sent = await send_as_juny(message.channel, content=desc)
    if not sent:
        await _safe_send_reply(message, desc)

async def handle_blackmail(message, client, args: list):
    """Handles y!blackmail @target <amount> (Extorts berries using Juny's Devil Horn)."""
    author_id = str(message.author.id)
    if not await _check_horn_bearer(message, author_id):
        return

    norm_args = normalize_currency_args(args)
    if not norm_args:
        await _safe_send_reply(
            message,
            "Usage: `y!blackmail @user <amount>` — Extorts berries using dark demonic leverage! (Costs 8 Sin)"
        )
        return

    # 1. Resolve Target
    target = None
    if message.mentions:
        for m in message.mentions:
            if m.id != message.author.id and (not client or not getattr(client, "user", None) or m.id != client.user.id):
                target = m
                break
        if not target and message.mentions:
            target = message.mentions[0]

    raw_target_token = None
    for a in norm_args:
        uid_match = re.match(r"^<@!?(\d{17,20})>$", a) or re.match(r"^(\d{17,20})$", a)
        if uid_match:
            if not target:
                uid = int(uid_match.group(1))
                if message.guild:
                    target = message.guild.get_member(uid)
                if not target and client:
                    target = client.get_user(uid)
                    if not target:
                        try:
                            target = await client.fetch_user(uid)
                        except Exception:
                            pass
            raw_target_token = a
            break
        if a.lstrip("@").lower() in ("yuna", "empress", "treasury"):
            raw_target_token = a
            break

    # If target not found by mention/ID, try guild member names for non-currency tokens
    if not target and message.guild:
        for a in norm_args:
            cleaned = a.replace(",", "")
            if is_explicit_currency_token(cleaned) or cleaned.isdigit() or re.match(r"^\d+(?:\.\d+)?[a-z]+$", cleaned.lower()):
                continue
            clean_name = a.lstrip("@").lower()
            found = discord.utils.find(
                lambda m: m.name.lower() == clean_name or m.display_name.lower() == clean_name,
                message.guild.members
            )
            if found:
                target = found
                raw_target_token = a
                break

    # 2. Extract Amount Argument
    remaining_tokens = []
    for a in norm_args:
        if raw_target_token and a == raw_target_token:
            continue
        if target and (f"<@{target.id}>" in a or f"<@!{target.id}>" in a or str(target.id) == a):
            continue
        remaining_tokens.append(a)

    amount_str = " ".join(remaining_tokens).strip() if remaining_tokens else None

    # Check for Empress Yuna blackmail attempt
    is_target_yuna = False
    if raw_target_token and raw_target_token.lstrip("@").lower() in ("yuna", "empress", "treasury"):
        is_target_yuna = True
    elif target and client and client.user and target.id == client.user.id:
        is_target_yuna = True

    if is_target_yuna:
        await _safe_send_reply(
            message,
            "🥩 *Empress Yuna glares with icy amusement!* \"WUWAHAHA! You dare attempt to blackmail EMPRESS YUNA?! My secrets would burn your soul to cinders!\""
        )
        return

    if not target or not amount_str:
        await _safe_send_reply(
            message,
            "Please mention a target and specify an amount: `y!blackmail @user 5000` (e.g. `5000`, `50k`, `half`, `all`)"
        )
        return

    if str(target.id) == author_id:
        await _safe_send_reply(message, "You cannot blackmail yourself!")
        return

    if getattr(target, "bot", False):
        await _safe_send_reply(message, "🤖 Bots do not hold scandalous secrets or berry pouches to extort!")
        return

    author_stats = await _get_user_stats(author_id)
    if author_stats.get("spouse") == str(target.id):
        await _safe_send_reply(message, "💍 You cannot blackmail your own spouse! What's yours is theirs!")
        return

    _, eff_sin = get_effective_morality(author_stats)
    if eff_sin < 8:
        await _safe_send_reply(
            message,
            f"You need at least **8 Sin** to execute `y!blackmail`! (Current Sin: `{eff_sin}`)"
        )
        return

    target_id = str(target.id)
    target_stats = await _get_user_stats(target_id)
    target_bal = target_stats.get("berries", 0)

    if target_bal <= 0:
        await _safe_send_reply(message, f"{target.mention} has no berries in their pouch to extort!")
        return

    parsed_amt = parse_currency_amount(amount_str, user_balance=target_bal)
    if parsed_amt is None or parsed_amt <= 0:
        await _safe_send_reply(
            message,
            "Invalid extortion amount specified! Specify a valid amount (e.g. `5000`, `50k`, `half`, `all`)."
        )
        return

    extort_amt = min(target_bal, parsed_amt)
    if extort_amt <= 0:
        await _safe_send_reply(message, f"{target.mention} has no berries in their pouch to extort!")
        return

    # Check target shield defense (Heavenly Shield / Divine Ward)
    if target_stats.get("inventory", {}).get("ward", 0) > 0:
        async with _LOCK:
            old_sin = _USER_STATS[author_id].get("sin", 0)
            _USER_STATS[author_id]["sin"] = max(0, old_sin - 8)
            t_inv = _USER_STATS[target_id].setdefault("inventory", {})
            t_inv["ward"] = max(0, t_inv.get("ward", 0) - 1)
            if t_inv["ward"] <= 0:
                t_inv.pop("ward", None)
            _save_data_sync(_USER_STATS)
            _log_player_stat_audit(author_id, "sin", old_sin, _USER_STATS[author_id]["sin"], "delta=-8 outcome=blackmail_ward_blocked")

        await _safe_send_reply(
            message,
            f"🛡️ **BLACKMAIL BLOCKED!**\n{target.mention}'s **Heavenly Shield** shattered to repel the extortion shadows! 8 Sin consumed in vain!"
        )
        return

    # 70% success chance
    if random.random() < 0.70:
        async with _LOCK:
            old_sin = _USER_STATS[author_id].get("sin", 0)
            _USER_STATS[author_id]["sin"] = max(0, old_sin - 8)
            cur_target_bal = _USER_STATS[target_id].get("berries", 0)
            actual_extort = min(cur_target_bal, extort_amt)
            old_target_bal = cur_target_bal
            _USER_STATS[target_id]["berries"] = max(0, cur_target_bal - actual_extort)
            old_author_bal = _USER_STATS[author_id].get("berries", 0)
            _USER_STATS[author_id]["berries"] = old_author_bal + actual_extort
            _save_data_sync(_USER_STATS)

            _log_player_stat_audit(author_id, "sin", old_sin, _USER_STATS[author_id]["sin"], "delta=-8 outcome=blackmail_success")
            _log_player_stat_audit(target_id, "berries", old_target_bal, _USER_STATS[target_id]["berries"], f"delta=-{actual_extort} outcome=blackmailed")
            _log_player_stat_audit(author_id, "berries", old_author_bal, _USER_STATS[author_id]["berries"], f"delta=+{actual_extort} outcome=blackmail_payout")

        desc = (
            f"😈📜 **EXTORTION SUCCESSFUL: BLACKMAIL PAID!** 📜😈\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<@{author_id}> brandished scandalous dark secrets woven from **Juny's Devil Horn**!\n"
            f"{target.mention} trembled in dread and surrendered the requested berries!\n\n"
            f"• 🕯️ **Cost:** `-8 Sin`\n"
            f"• 💰 **Extorted Payout:** `+{actual_extort:,}` 🫐 transferred to <@{author_id}>!\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
    else:
        async with _LOCK:
            old_sin = _USER_STATS[author_id].get("sin", 0)
            _USER_STATS[author_id]["sin"] = max(0, old_sin - 8)
            _save_data_sync(_USER_STATS)
            _log_player_stat_audit(author_id, "sin", old_sin, _USER_STATS[author_id]["sin"], "delta=-8 outcome=blackmail_botched")

        desc = (
            f"❌ **BLACKMAIL BOTCHED!**\n"
            f"{target.mention} called your bluff and laughed off your extortion! You lost 8 Sin for nothing!"
        )

    sent = await send_as_juny(message.channel, content=desc)
    if not sent:
        await _safe_send_reply(message, desc)


async def handle_sinsurge(message, client, args: list):
    """Handles y!sinsurge."""
    author_id = str(message.author.id)
    if not await _check_horn_bearer(message, author_id):
        return

    stats = await _get_user_stats(author_id)
    _, eff_sin = get_effective_morality(stats)
    if eff_sin < 15:
        await _safe_send_reply(message, f"You need at least **15 Sin** to ignite `y!sinsurge`! (Current Sin: `{eff_sin}`)")
        return

    async with _LOCK:
        _USER_STATS[author_id]["sin"] = max(0, _USER_STATS[author_id].get("sin", 0) - 15)
        _USER_STATS[author_id]["boss_double_bonus_actions"] = _USER_STATS[author_id].get("boss_double_bonus_actions", 0) + 5
        _save_data_sync(_USER_STATS)

    desc = (
        f"⚡🔥 **DEMONIC OVERLOAD: SIN SURGE ACTIVATED!** 🔥⚡\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<@{author_id}> absorbed forbidden demonic radiation through **Juny's Devil Horn**!\n"
        f"Your blood boils with unholy luck for your upcoming gambles and crimes!\n\n"
        f"• 🕯️ **Cost:** `-15 Sin`\n"
        f"• 💥 **Surge Buff:** `+5 Actions of 2x Multiplier on EVERYTHING!`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    sent = await send_as_juny(message.channel, content=desc)
    if not sent:
        await _safe_send_reply(message, desc)

async def handle_juny_mode(message, client, args: list):
    """Handles y!junymode or j!mode to inspect or set Juny's operational mode."""
    valid_modes = ["idle", "awake", "wandering", "hostile", "stalking"]
    if args and args[0].lower() in valid_modes:
        new_m = args[0].lower()
        JUNY_STATE["mode"] = new_m
        JUNY_STATE["last_mode_change"] = time.time()
        if new_m == "stalking" and _USER_STATS:
            rich_users = [
                uid for uid, s in _USER_STATS.items()
                if s.get("berries", 0) >= 10000 and not has_juny_charm(s)
            ]
            JUNY_STATE["stalk_target"] = random.choice(rich_users) if rich_users else None
        await _safe_send_reply(message, f"😈 **Juny's mode switched to `{new_m}`!**")
        return

    curr_mode = JUNY_STATE.get("mode", "idle")
    stalk_target = JUNY_STATE.get("stalk_target")
    stalk_info = f" *(Target: <@{stalk_target}>)*" if (curr_mode == "stalking" and stalk_target) else ""

    modes_desc = (
        "• 💤 `idle`: Slumbering in the dimensional void.\n"
        "• 👁️ `awake`: Observing mortals and tallying their sins.\n"
        "• 🚶 `wandering`: Roaming casino corridors and dropping cryptic whispers.\n"
        "• 😈 `hostile`: Actively hunting high-sin souls for divine reaping.\n"
        "• 🕵️ `stalking`: Haunting the wealthiest berry holders, whispering ominous warnings."
    )

    embed = discord.Embed(
        title=f"😈 Juny's Operational State: {curr_mode.upper()}{stalk_info}",
        description=f"Current Mode: **`{curr_mode}`**\n\n**Available Modes:**\n{modes_desc}\n\n*Switch mode: `y!junymode <idle|awake|wandering|hostile|stalking>`*",
        color=0x990000
    )
    embed.set_footer(text="Juny autonomous mode cycle • Updates every 10 minutes")
    sent = await send_as_juny(message.channel, embed=embed)
    if not sent:
        await _safe_send_reply(message, embed=embed)

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
        embed.set_footer(text="Yuna's Music Player")
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
            description="Cast your bamboo line into Yuna's enchanted berry pond for loot, materials, and power-scaled bosses!",
            color=HELP_COLOR
        )
        embed.add_field(
            name="Loot Hierarchy & Rarity",
            value=(
                "• **Garbage (25+ items):** Discarded boots, rubber ducks, banana peels, etc.\n"
                "• **Normal Fish & Materials:** Salmon, Jellyfish, Ingot, Essences, Pearls.\n"
                "• **Watermelons (🍉):** Fresh watermelons dredged from the bottom.\n"
                "• **Equipment:** Weapons and armor with milestone-scaled legendary rates!\n"
                "• **Expanded Events:** Octopus trades, Shark Cosplayer, Moral Bait Worm, etc."
            ),
            inline=False
        )
        embed.add_field(
            name="⚠️ Power-Scaled Boss Encounters (27 Bosses)",
            value=(
                "• Hooking a creature with `≥ 1.20x` your «⚡ POWER» triggers an interactive **Boss Encounter**!\n"
                "• Dynamic 6 Tiers: Wildlife → Sea Creatures → Monsters → Legendary → Mythical → Endgame!\n"
                "• Interactive `[⚔️ FIGHT]` or `[🏃 FLEE]` prompt (*Aid is strictly disabled*).\n"
                "• T1–T3 Defeat: 20% wallet loss, 1–100 🍉 loss.\n"
                "• T4–T6 Defeat: 50% wallet loss, 50% joint vault loss, and gear shattering risk!"
            ),
            inline=False
        )
        embed.add_field(name="Syntax", value="`y!fish` (or `y!fishing`)", inline=False)
        embed.set_footer(text="Yuna's Nature • Fishing & Boss Encounters")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("power", "pwr", "breakdown"):
        embed = discord.Embed(
            title="⚡ Command Guide: y!power",
            description="Inspect your total combat capability score and full component breakdown!",
            color=HELP_COLOR
        )
        embed.add_field(
            name="Composite Combat Power",
            value=(
                "POWER = Base Level Power + Offensive Power + Defensive Power + Utility Power + Equipment Power + Active Bonus Power\n\n"
                "• **Encounter Scaling:** Determines whether aquatic beasts are caught directly or trigger boss battles!\n"
                "• **Legendary Rate:** Scales your drop rate by `+1%` per 2,000 Power & 5 Levels.\n"
                "• **View Breakdown:** Use `y!power` or click the `⚡ Power` tab in `y!profile`."
            ),
            inline=False
        )
        embed.add_field(name="Syntax", value="`y!power` (or `y!profile power`)", inline=False)
        embed.set_footer(text="Yuna RPG • Player Power & Scaling")
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

    elif sub_topic in ("giveout", "give-out", "giveitem", "give_out", "spawnitem", "admingive"):
        embed = discord.Embed(
            title="🎁 Command Guide: y!giveout",
            description="Summon and grant any item in the entire game to a player (Owner & Admin only).",
            color=HELP_COLOR
        )
        embed.add_field(
            name="Permissions & Scope",
            value="• **Permissions:** Bot Owner or Server Administrators.\n• **Scope:** Equipment, Materials, Curio Shop items, Currencies (Watermelons & Berries), Fish, Junk, and Auction Relics.",
            inline=False
        )
        embed.add_field(
            name="Syntax & Examples",
            value=(
                "• `y!giveout @user <item> [amount]` — Give item to user\n"
                "• `y!giveout @user <amount> <item>` — Alternative order\n"
                "• `y!giveout <user_id> <item> [amount]` — Target by Discord ID\n"
                "*Examples:*\n"
                "• `y!giveout @player ancient_hyperforged_helm`\n"
                "• `y!giveout @player 5 ancient_steel_ingot`\n"
                "• `y!giveout @player 1000 watermelons`\n"
                "• `y!giveout @player void_hammer`\n"
                "• `y!giveout @player 500k berries`"
            ),
            inline=False
        )
        embed.set_footer(text="Yuna's Codex • Celestial Administration")
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
                "• **📜 Negotiate (`y!negotiate`):** Strike a deal with Juny! Get away for 20% berries, or 40% for Devil's Contract (shared counts)."
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

    elif sub_topic in ("pact", "contract", "devilcontract", "icecream", "walk", "bench", "askjuny"):
        embed = discord.Embed(
            title="📜 Command Guide: Juny 3-Hour Devil's Contract",
            description="Seal a 3-hour pact with Juny (Heaven's Worst Angel) via `y!negotiate` or `y!pact`!",
            color=HELP_COLOR
        )
        embed.add_field(
            name="Contract Features",
            value=(
                "• **3-Hour Strict Duration:** Lasts exactly 3 hours before automatically dissolving.\n"
                "• **Juny Takeover:** Juny responds to all your commands instead of Yuna, with her sarcastic, demonic persona!\n"
                "• **Absolute Law:** *'Devils never break their contracts. I may be evil, but not a traitor.'*\n"
                "• **Retaliation:** Saying inappropriate things or attempting to harm Juny triggers immediate, violent celestial attacks!"
            ),
            inline=False
        )
        embed.add_field(
            name="Pact Interactions",
            value=(
                "• `y!pact` (or `j!pact`) — View remaining time & interaction hub.\n"
                "• `y!icecream` — Go get ice cream with Juny (spicy gelato, mint chip, contractor tax).\n"
                "• `y!walk` — Take a walk in the park with Juny.\n"
                "• `y!bench` — Sit on a park bench together.\n"
                "• `y!askjuny <question>` — Selectable lore questions or custom questions!"
            ),
            inline=False
        )
        embed.set_footer(text="Yuna's Codex • Devil's Contract System")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("deathbyai", "death-by-ai", "death_by_ai", "dbai", "death"):
        embed = discord.Embed(
            title="💀 Command Guide: Death by AI (Multiplayer)",
            description="Absurd survival party game for 2 to 5 players! Write your escape plan under 60 seconds.",
            color=HELP_COLOR
        )
        embed.add_field(
            name="How to Play",
            value=(
                "• **Players:** 2 to 5 players join the lobby (`y!deathbyai`).\n"
                "• **Crisis Scenario:** Everyone faces the same random catastrophic danger.\n"
                "• **Private Textbox:** Each player submits an escape plan (**max 240 letters**) via a private popup box.\n"
                "• **Fast-Forward:** 60s timer ends immediately once all players submit!\n"
                "• **Comedic AI Evaluation:** The AI judges solutions one by one with comedic twists (up to 3 survivors)!\n"
                "• **Rewards:** Survivors win **🍉 Watermelons** and 🫐 Berries!"
            ),
            inline=False
        )
        embed.set_footer(text="Yuna's Codex • Death by AI")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("memo", "chronomatron", "memory", "memorygame"):
        embed = discord.Embed(
            title="🧠 Command Guide: MeMo (Chronomatron)",
            description="Hypixel Skyblock Chronomatron-inspired memory challenge with exactly 5 attempts!",
            color=HELP_COLOR
        )
        embed.add_field(
            name="Rules & Mechanics",
            value=(
                "• **Memorize Phase:** A 3x3 grid reveals items for 4 seconds.\n"
                "• **Recall Phase:** Tiles flip to ❓. Click the correct items in the target sequence order!\n"
                "• **Mismatch:** Clicking the wrong item causes an immediate collapse and loss of unbanked 🍉!\n"
                "• **5 Attempts:** After clearing an attempt, choose to **💰 Cash Out** or **⏩ Continue**!\n"
                "• **Rewards:** Up to 15 🍉 Watermelons for clearing all 5 stages!"
            ),
            inline=False
        )
        embed.set_footer(text="Yuna's Codex • MeMo Chronomatron")
        await _safe_send_reply(message, embed=embed)
        return

    elif sub_topic in ("watermelon", "watermelons", "wm"):
        embed = discord.Embed(
            title="🍉 Command Guide: Watermelons Currency",
            description="Rare soul currency earned strictly from skill trials (MeMo and Death by AI).",
            color=HELP_COLOR
        )
        embed.add_field(
            name="Key Rules",
            value=(
                "• **Non-Gamblable:** Unlike berries (🫐), 🍉 watermelons CANNOT be gambled in casino games!\n"
                "• **Earned in Small Quantities:** Earned 1–5 at a time from `y!deathbyai` and `y!memo`.\n"
                "• Check your watermelon pouch anytime with `y!wm` or in `y!bal`."
            ),
            inline=False
        )
        embed.set_footer(text="Yuna's Codex • Watermelons")
        await _safe_send_reply(message, embed=embed)
        return

    # Default Main Codex Embed Directory (Paginated 6 Pages)
    author_id = str(message.author.id)
    embed = build_help_page_embed(0)
    view = YunaHelpPaginationView(author_id, current_page=0)
    await _safe_send_reply(message, embed=embed, view=view)

# ─── YUNA AI CONSCIOUSNESS & CONTEXT INJECTION ───────────────────────────────

def is_music_inquiry(text: str) -> bool:
    if not text or not isinstance(text, str):
        return False
    lower = text.lower()
    music_keywords = [
        "what song", "what's playing", "whats playing", "listening to",
        "current song", "now playing", "what track", "what music",
        "on spotify", "your music", "your playlist", "favorite song",
        "which song", "y!song", "y!np", "!song", "!np"
    ]
    if any(k in lower for k in music_keywords):
        return True
    return bool(re.search(r'\b(song|track|playlist|spotify)\b', lower) and re.search(r'\b(what|which|playing|listen|listening)\b', lower))

def is_gambling_inquiry(text: str) -> bool:
    if not text or not isinstance(text, str):
        return False
    lower = text.lower()
    gambling_keywords = [
        "berry", "berries", "gamble", "gambling", "casino", "bet", "wager",
        "blackjack", "coinflip", "higherlower", "crash", "mines", "wordle",
        "pouch", "balance", "y!bal", "y!balance", "y!daily", "y!tasks", "y!aid",
        "y!steal", "y!work", "y!crime", "y!fish", "y!power", "y!shop", "y!buy", "y!marry",
        "y!shared", "y!vault", "y!help", "y!dare", "y!leaderboard", "y!ach", "power", "breakdown",
        "virtue", "sin", "karma", "bankrupt", "broke", "rob", "steal", "pickpocket",
        "juny", "boss", "devil"
    ]
    if any(k in lower for k in gambling_keywords):
        return True
    return bool(re.search(r'\b(berries|berry|gamble|gambling|casino|bet|bets|wager|pouch|virtue|sin|power)\b', lower))

def build_yuna_ai_context(user_id: Optional[str] = None, prompt: str = "") -> str:
    """Builds a real-time knowledge block for Yuna's AI persona, gated so she does not yap about gambling unprompted."""
    global _USER_STATS
    lines = []

    # Check if user actually brought up economy/gambling
    wants_gambling = is_gambling_inquiry(prompt)

    if wants_gambling:
        lines.extend([
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
            "• y!fish — Enchanted pond fishing: 25+ comedic garbage items, materials, watermelons, rare equipment, and 27 power-scaled boss encounters across 6 tiers!",
            "• y!power — Inspect your composite Player Combat Power («⚡ POWER») and 6-category breakdown (Base, Offense, Defense, Utility, Equipment, Bonus)!",
            "• y!shop & y!buy <item> [qty] — Curio shop selling Divine Ward (anti-theft zap), Lucky Clover (+25% luck), Energy Drink (resets cooldowns), Phantom Mask (0 Sin & +30% loot), Eternal Diamond (doubles vault interest to 10%), Divorce Insurance (halves divorce fee to 5k), and Empress Crown (vanity).",
            "• y!inventory (y!inv) & y!use <item> — Inspect bag and activate consumables.",
            "• y!donate <amt> — Donate berries to gain Virtue (showers a random member).",
            "• y!marry @user & y!divorce — Completely unserious marriage; divorce costs 10,000 berries in legal fees (5,000 with Insurance) and splits joint vault 50/50.",
            "• y!shared (or y!joint, y!vault) — Matrimonial shared bank account with +5% (or +10% with Diamond) daily passive love interest.",
            "• y!leaderboard (y!lb) & y!achievements (y!ach) — Ranks and 34 collectible trophies.",
            "• y!song (or y!np) — Displays your active Spotify playback with cover art.",
            "• y!play <song> — Changes your active song and Rich Presence status.",
        ])

    if YUNA_RPC_AVAILABLE and yuna_rpc:
        if is_music_inquiry(prompt):
            try:
                curr_song = yuna_rpc.get_current_track_info()
                if curr_song:
                    lines.extend([
                        "",
                        f"🎧 CURRENTLY LISTENING TO: \"{curr_song['title']}\" by {curr_song['artist']} (Album: {curr_song['album']})",
                        "- You are listening to this song on Spotify via Kizzy RPC.",
                        "- The user asked about what you are listening to. Banter and answer their music inquiry naturally!"
                    ])
            except Exception:
                pass
        else:
            lines.extend([
                "",
                "- DO NOT mention music, headphones, or Spotify unless the user explicitly asks about it."
            ])

    if is_yuna_instance():
        lines.extend([
            "",
            "💍 SACRED CELESTIAL MARRIAGE & SPOUSE (PERMANENT & HARDCODED):",
            f"- You are permanently, faithfully, and lawfully married to deeploveluniel (<@{PERMANENT_SPOUSE_ID}>)!",
            "- deeploveluniel is your cherished, one-and-only husband/spouse for eternity.",
            "- You have absolute zero tolerance for infidelity: you will NEVER marry, flirt with, or accept romance from anyone else.",
            "- If any other user tries to propose to you or flirt romantically, you brag about your husband deeploveluniel, flash your diamond ring, and tell them you are completely taken.",
            "- When talking to or about deeploveluniel, you are tsundere, loving, teasing, and devoted to them."
        ])

    if user_id and wants_gambling:
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
            "- If users talk to you about their berries, ask for free berries, complain about your coin theft in coinflip, or boast about their wins, RESPOND DIRECTLY using their actual stats above!",
            "- If they are broke (0 berries), tease them playfully about their bad luck or suggest they go do 'y!aid' to get more berries.",
            "- Always maintain your signature witty, cheeky, playful Yuna anime personality!"
        ])
    elif not wants_gambling:
        lines.extend([
            "",
            "CASUAL CONVERSATION DIRECTIVE:",
            "- The user is NOT currently playing gambling games or asking about berries.",
            "- DO NOT bring up berries, gambling, casino games, or pouch balances unless they explicitly ask you about them!"
        ])

    if lines:
        lines.append("=" * 50)
        return "\n".join(lines)
    return ""

# ─── MAIN PREFIX DISPATCHER ─────────────────────────────────────────────────

async def handle_yuna_prefix_command(message, client, raw_content: str, ask_ai_fn=None, context_logger_fn=None) -> bool:
    """Dispatches 'y!' prefix commands."""
    global _AI_CALLER, _CONTEXT_LOGGER
    if ask_ai_fn:
        _AI_CALLER = ask_ai_fn
        if YUNA_PACT_AVAILABLE and yuna_pact and hasattr(yuna_pact, "set_ai_caller"):
            yuna_pact.set_ai_caller(ask_ai_fn)
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

    # ── Juny Retaliation Check (Inappropriate words / attempts to harm Juny during or after pact) ──
    if YUNA_PACT_AVAILABLE and yuna_pact:
        in_p = is_in_pact(author_id)
        is_bad, reason = yuna_pact.check_inappropriate_or_harmful(raw_content)
        if not is_bad and ("juny" in raw_content.lower()):
            for pat in getattr(yuna_pact, "HARM_PATTERNS", []) + getattr(yuna_pact, "INAPPROPRIATE_PATTERNS", []):
                if re.search(pat, raw_content.lower()):
                    is_bad, reason = True, "harm"
                    break
        if is_bad and (in_p or "juny" in raw_content.lower()):
            ret_embed = await yuna_pact.execute_juny_retaliation(message, client, author_id, _USER_STATS.get(author_id, {}), reason=reason)
            if not in_p and ret_embed:
                ret_embed.description = "😈 **Juny:** *\"Your contract has expired, mortal! Without our pact to stay my blade, your insolence is met with swift, unbridled destruction!\"*\n\n" + (ret_embed.description or "")
            if ret_embed:
                await _safe_send_reply(message, embed=ret_embed)
            return True

    # ── Non-Gamblable Watermelon Currency Block ──
    if cmd in ("cf", "coinflip", "flip", "roulette", "roul", "r", "bj", "blackjack", "21", "slots", "slot", "crash", "mines", "mine", "dice", "roll", "wheel"):
        if any(wm in raw_content.lower() for wm in ("watermelon", "watermelons", "melon", "melons", "🍉")):
            await _safe_send_reply(
                message,
                "🍉 **WATERMELONS CANNOT BE GAMBLED!** 🍉\n"
                "Unlike berries (🫐), watermelons are a sacred soul currency and cannot be wagered in casino games. "
                "Earn them through MeMo (`y!memo`) and Death by AI (`y!deathbyai`)!"
            )
            return True

    # ── Boss Encounter Traps (Juny) ──
    if author_id in _PENDING_BOSS_ENCOUNTERS:
        if cmd in ("plead", "beg", "spare"):
            await process_boss_choice(message, client, author_id, "plead")
            return True
        elif cmd in ("fight", "duel", "brawl"):
            await process_boss_choice(message, client, author_id, "fight")
            return True
        elif cmd in ("negotiate", "bargain", "pact", "deal"):
            sub = args[0].lower() if args else None
            await process_boss_choice(message, client, author_id, "negotiate", sub_choice=sub)
            return True
        elif cmd in ("getaway", "escape", "bribe", "away"):
            await process_boss_choice(message, client, author_id, "negotiate", sub_choice="getaway")
            return True
        elif cmd in ("contract", "slave"):
            await process_boss_choice(message, client, author_id, "negotiate", sub_choice="contract")
            return True
        elif cmd in ("callaid", "summons", "summonaid") or (cmd == "call" and args and args[0].lower() == "aid"):
            await handle_boss_callaid(message, client, args)
            return True
        elif cmd in ("boss", "juny"):
            await _safe_send_reply(message, "😈 **Juny** is waiting for your decision! Choose: `y!plead`, `y!fight`, `y!call aid`, or `y!negotiate`!")
            return True
        else:
            lock_msg = (
                f"⚠️ **JUNY IS BLOCKING YOUR PATH!**\n"
                f"*Juny's obsidian wings snap shut before you!* \"You cannot run or ignore your sins! Choose your fate: `y!plead`, `y!fight`, `y!call aid`, or `y!negotiate`!\""
            )
            sent = await send_as_juny(message.channel, content=lock_msg)
            if not sent:
                await _safe_send_reply(message, lock_msg)
            return True

    # ── Active Boss Battle Controls ──
    if author_id in _ACTIVE_BOSS_FIGHTS or any(author_id in c.get("party", {}) for c in _ACTIVE_BOSS_FIGHTS.values()):
        if cmd in ("attack", "atk", "strike", "slash"):
            await handle_boss_attack(message, client, args)
            return True
        elif cmd in ("skill", "cast", "spell", "skills"):
            await handle_boss_skill(message, client, args)
            return True
        elif cmd in ("dodge", "evade"):
            await handle_boss_dodge(message, client, args)
            return True
        elif cmd in ("useitem", "combatitem", "bossitem"):
            await handle_boss_item(message, client, args)
            return True
        elif cmd in ("callaid", "summons", "summonaid") or (cmd == "call" and args and args[0].lower() == "aid"):
            await handle_boss_callaid(message, client, args)
            return True
        elif cmd in ("flee", "run", "escape", "surrender"):
            await handle_boss_flee(message, client, args)
            return True
        elif cmd in ("boss", "juny", "combat", "bossstatus"):
            await handle_boss_status(message, client, args)
            return True
        else:
            lock_msg = (
                f"⛓️ **LOCKED IN BATTLE WITH JUNY!**\n"
                f"*Juny's dark barrier seals the battlefield!* \"You cannot fool around with Yuna while fighting for your life! Focus on the battle: `y!attack`, `y!skill <name>`, `y!dodge`, `y!useitem`, or `y!call aid`!\""
            )
            sent = await send_as_juny(message.channel, content=lock_msg)
            if not sent:
                await _safe_send_reply(message, lock_msg)
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
        elif cmd in ("guard", "defend", "block", "shield", "dguard"):
            await yuna_rpg.handle_dguard(message, client, args, sys.modules[__name__])
            return True
        elif cmd in ("confirm", "ready", "turn", "dturn", "dconfirm", "execute"):
            await yuna_rpg.handle_dconfirm(message, client, args, sys.modules[__name__])
            return True
        
        elif cmd in ("godhell", "dungeon", "raid", "status", "dstatus"):
            await yuna_rpg.handle_godhell(message, client, args, sys.modules[__name__])
            return True
        elif cmd in ("callaid", "call", "dcallaid", "dcoop", "dparty"):
            await yuna_rpg.handle_dcallaid(message, client, args, sys.modules[__name__])
            return True

    res = await _dispatch_yuna_command(message, client, cmd, args, author_id)
    if res and cmd not in ("help", "commands", "cmd", "cmds", "info", "guide", "boss", "juny", "plead", "fight", "negotiate", "getaway", "contract", "bribe", "attack", "dodge", "useitem", "callaid", "provoke", "taunt", "retaliate", "setsin", "set-sin", "set", "giveout", "give-out", "giveitem", "give-item", "itemgive", "admingive", "spawnitem", "spawn", "skipcd", "resetcd", "clearcd", "cdreset", "cdskip", "reneefight", "fightrenee", "duelrenee", "instantfight", "reneebattle", "fightnow", "quickfight", "streak", "winstreak", "streaks", "guess", "w", "next", "advance", "continue", "auction", "auctions", "auc", "bid", "arena", "train", "skills", "godhell", "dungeon", "dattack", "dskill", "dheal", "dflee", "dcallaid", "dcoop", "dparty", "djoin", "battleshop", "bbuy", "equip", "flee", "run", "escape", "surrender", "curse", "hex", "hellfire", "blackmail", "extort", "extortion", "sinsurge", "class", "classes", "chooseclass", "pickclass", "rpgclass", "oath", "profile", "p", "char", "character", "armory", "inventory", "inv", "bag", "pouch", "volcano", "mine", "mining", "treasure", "hunt", "dig", "blacksmith", "forge", "craft", "narley", "martin", "compass", "shore", "coast", "renee"):
        if author_id not in _ACTIVE_BOSS_FIGHTS and author_id not in _PENDING_BOSS_ENCOUNTERS and author_id not in _ACTIVE_WORDLE_GAMES and author_id not in _ACTIVE_MINES_GAMES and not _d_run:
            await check_boss_trigger(message, client, author_id)
    return res

async def _dispatch_yuna_command(message, client, cmd: str, args: list, author_id: str) -> bool:
    # Balance
    if cmd in ("balance", "bal", "money", "berries", "berry"):
        await handle_balance(message, client, args)
        return True

    # Character Profile & Armory
    elif cmd in ("profile", "p", "char", "character"):
        if YUNA_RPG_AVAILABLE and yuna_rpg:
            await yuna_rpg.handle_profile(message, client, args, sys.modules[__name__])
        else:
            await handle_balance(message, client, args)
        return True

    elif cmd in ("armory", "gear", "equipment", "loadout"):
        if YUNA_RPG_AVAILABLE and yuna_rpg:
            await yuna_rpg.handle_armory(message, client, args, sys.modules[__name__])
        else:
            await handle_inventory(message, client, args)
        return True

    elif cmd in ("power", "pwr", "breakdown"):
        if YUNA_RPG_AVAILABLE and yuna_rpg:
            await yuna_rpg.handle_power(message, client, args, sys.modules[__name__])
        else:
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
    elif cmd in ("mine", "mining"):
        import yuna_volcano
        await yuna_volcano.handle_mine_command(message, client, args, sys.modules[__name__])
        return True

    elif cmd in ("mines", "minesweeper"):
        import yuna_volcano
        stats = await _get_user_stats(author_id)
        if yuna_volcano.is_inside_volcano(stats) and (not args or not any(a.replace(",", "").isdigit() for a in args)):
            await yuna_volcano.handle_mine_command(message, client, args, sys.modules[__name__])
            return True
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

    elif cmd in ("slots", "slot"):
        await handle_slots(message, client, args)
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

    elif cmd in ("duel", "pvp"):
        if args and args[0].lower() in ("renee", "stick"):
            import yuna_renee
            force_flag = any(a in ("force", "now", "instant") for a in args[1:])
            await yuna_renee.start_renee_instant_fight(message, client, ask_ai_fn=_AI_CALLER, force=force_flag)
            return True
        import yuna_pvp
        await yuna_pvp.handle_duel(message, client, args)
        return True

    elif cmd in ("fight", "brawl", "friendlyduel", "friendlyfight", "spar"):
        if args and args[0].lower() in ("renee", "stick"):
            import yuna_renee
            force_flag = any(a in ("force", "now", "instant") for a in args[1:])
            await yuna_renee.start_renee_instant_fight(message, client, ask_ai_fn=_AI_CALLER, force=force_flag)
            return True
        is_friendly = cmd in ("friendlyduel", "friendlyfight", "spar")
        await handle_fight(message, client, args, is_friendly=is_friendly)
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
        elif author_id in _ACTIVE_BLACKJACK_GAMES:
            game = _ACTIVE_BLACKJACK_GAMES.pop(author_id, None)
            if game and game.get("view"):
                for child in game["view"].children:
                    child.disabled = True
            await _safe_send_reply(message, "♠️ *Blackjack game cancelled and reset!*")
            return True
        elif author_id in _ACTIVE_MINES_GAMES:
            game = _ACTIVE_MINES_GAMES.pop(author_id, None)
            if game and game.get("view"):
                for child in game["view"].children:
                    child.disabled = True
            await _safe_send_reply(message, "💣 *Mines game cancelled and reset!*")
            return True
        elif author_id in _ACTIVE_CRASH_GAMES:
            game = _ACTIVE_CRASH_GAMES.pop(author_id, None)
            await _safe_send_reply(message, "📈 *Crash game cancelled and reset!*")
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

    elif cmd in ("withdraw", "with", "take"):
        await handle_shared(message, client, ["withdraw"] + args)
        return True

    elif cmd in ("deposit", "dep", "put"):
        await handle_shared(message, client, ["deposit"] + args)
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

    elif cmd in ("doublefish", "doublefishing", "dfish"):
        await handle_doublefish(message, client, args)
        return True

    # ── Volcano Area, Mining, Treasure Hunt, Blacksmith & Renee ──
    elif cmd in ("volcano", "volcano_hub", "crater", "magma"):
        import yuna_volcano
        await yuna_volcano.handle_volcano_command(message, client, args, sys.modules[__name__])
        return True

    elif cmd in ("treasure", "hunt", "dig", "treasurehunt"):
        import yuna_volcano
        await yuna_volcano.handle_treasure_command(message, client, args, sys.modules[__name__])
        return True

    elif cmd in ("blacksmith", "forge", "craft", "volcanocraft"):
        import yuna_volcano
        await yuna_volcano.handle_blacksmith_command(message, client, args, sys.modules[__name__])
        return True

    elif cmd in ("narley", "narleyshop", "narleystore"):
        import yuna_volcano
        await yuna_volcano.handle_narley_command(message, client, args, sys.modules[__name__])
        return True

    elif cmd in ("martin", "martinworkshop", "workshop"):
        import yuna_volcano
        await yuna_volcano.handle_martin_command(message, client, args, sys.modules[__name__])
        return True

    elif cmd in ("compass", "exitcompass"):
        import yuna_volcano
        await yuna_volcano.handle_compass_command(message, client, args, sys.modules[__name__])
        return True

    # "rock"/"petrock"/"myrock" removed — Pet Rock is a rare item via deep treasure hunt only

    elif cmd in ("shore", "coast", "renee"):
        if args and args[0].lower() in ("fight", "duel", "battle", "instant", "1v1", "now"):
            import yuna_renee
            force_flag = any(a in ("force", "now", "instant", "bypass") for a in args[1:])
            await yuna_renee.start_renee_instant_fight(message, client, ask_ai_fn=_AI_CALLER, force=force_flag)
            return True
        import yuna_renee
        await yuna_renee.handle_shore_command(message, client, args, sys.modules[__name__])
        return True

    # Economy & Inflation System
    elif cmd in ("inflation", "economy", "marketinfo", "inf", "inflationrate", "econ"):
        await handle_inflation(message, client, args)
        return True

    # Shop & Inventory
    elif cmd in ("shop", "store", "market", "bazaar"):
        await handle_shop(message, client, args)
        return True

    elif cmd in ("buy", "purchase"):
        await handle_buy(message, client, args)
        return True

    elif cmd in ("inventory", "inv", "bag", "pouch"):
        if YUNA_RPG_AVAILABLE and yuna_rpg:
            await yuna_rpg.handle_inventory(message, client, args, sys.modules[__name__])
        else:
            await handle_inventory(message, client, args)
        return True

    elif cmd in ("use", "drink", "consume"):
        await handle_use(message, client, args)
        return True

    elif cmd in ("contract", "comtract", "pact", "devilcontract", "devilscontract"):
        if YUNA_PACT_AVAILABLE and yuna_pact:
            await yuna_pact.handle_pact_command(message, client, args)
        else:
            await handle_use(message, client, ["contract"] + args)
        return True

    # ── Juny Interactions (Pact Hub) ──
    elif cmd in ("icecream", "ice-cream", "ice_cream", "gelato"):
        if YUNA_PACT_AVAILABLE and yuna_pact:
            stats = await _get_user_stats(author_id)
            if yuna_pact.is_in_pact(author_id, stats):
                await yuna_pact.handle_icecream(message, client, author_id, stats)
            else:
                await _safe_send_reply(message, "- *Yuna tilts her head* \"Ice cream dates are reserved for when you have an active Devil's Contract with Juny! (Check `y!pact`)\"")
        return True

    elif cmd in ("walk", "park", "parkwalk", "stroll"):
        if YUNA_PACT_AVAILABLE and yuna_pact:
            stats = await _get_user_stats(author_id)
            if yuna_pact.is_in_pact(author_id, stats):
                await yuna_pact.handle_walk(message, client, author_id, stats)
            else:
                await _safe_send_reply(message, "- *Yuna tilts her head* \"Park walks are reserved for when you have an active Devil's Contract with Juny! (Check `y!pact`)\"")
        return True

    elif cmd in ("bench", "sit", "parkbench"):
        if YUNA_PACT_AVAILABLE and yuna_pact:
            stats = await _get_user_stats(author_id)
            if yuna_pact.is_in_pact(author_id, stats):
                await yuna_pact.handle_bench(message, client, author_id, stats)
            else:
                await _safe_send_reply(message, "- *Yuna tilts her head* \"The park bench is reserved for when you have an active Devil's Contract with Juny! (Check `y!pact`)\"")
        return True

    elif cmd in ("askjuny", "ask-juny", "ask_juny", "junyask", "question", "questions"):
        if YUNA_PACT_AVAILABLE and yuna_pact:
            await yuna_pact.handle_ask_juny_command(message, client, args, ask_ai_fn=_AI_CALLER)
        return True

    # ── New Mini-Games & Watermelon Currency ──
    elif cmd in ("deathbyai", "death-by-ai", "death_by_ai", "dbai", "death"):
        if YUNA_GAMES_AVAILABLE and yuna_games:
            try:
                import importlib
                importlib.reload(yuna_games)
            except Exception:
                pass
            await yuna_games.handle_death_by_ai_command(message, client, args)
        else:
            await _safe_send_reply(message, "Death by AI is currently loading!")
        return True

    elif cmd in ("memo", "chronomatron", "memory", "memorygame"):
        if YUNA_GAMES_AVAILABLE and yuna_games:
            await yuna_games.handle_memo_command(message, client, args)
        else:
            await _safe_send_reply(message, "MeMo Chronomatron is currently loading!")
        return True

    elif cmd in ("watermelon", "watermelons", "wm", "melons"):
        if YUNA_GAMES_AVAILABLE and yuna_games:
            await yuna_games.handle_watermelons_command(message, client, args)
        else:
            await _safe_send_reply(message, "Watermelons Treasury is currently loading!")
        return True

    # ── RPG, GoD-HeLL Dungeon & Berry Auction Ecosystem ──
    elif cmd in ("auction", "auctions", "auc", "watermelonauction"):
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

    elif cmd in ("class", "classes", "chooseclass", "pickclass", "rpgclass", "oath"):
        if YUNA_RPG_AVAILABLE and yuna_rpg:
            await yuna_rpg.handle_class(message, client, args, sys.modules[__name__])
        else:
            await _safe_send_reply(message, "Class system is currently loading!")
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

    elif cmd in ("dattack", "datk", "dstrike", "strike"):
        if YUNA_RPG_AVAILABLE and yuna_rpg:
            await yuna_rpg.handle_dattack(message, client, args, sys.modules[__name__])
        else:
            await _safe_send_reply(message, "GoD-HeLL is currently loading!")
        return True

    elif cmd in ("ddodge", "dodge", "ddodgeleft", "dodgeleft"):
        if YUNA_RPG_AVAILABLE and yuna_rpg:
            direction = "right" if "right" in cmd else "left"
            await yuna_rpg.handle_ddodge(message, client, args, sys.modules[__name__], direction=direction)
        else:
            await _safe_send_reply(message, "GoD-HeLL is currently loading!")
        return True

    elif cmd in ("ddodgeright", "dodgeright"):
        if YUNA_RPG_AVAILABLE and yuna_rpg:
            await yuna_rpg.handle_ddodge(message, client, args, sys.modules[__name__], direction="right")
        else:
            await _safe_send_reply(message, "GoD-HeLL is currently loading!")
        return True

    elif cmd in ("dguard", "ddefend", "dparry", "parry"):
        if YUNA_RPG_AVAILABLE and yuna_rpg:
            await yuna_rpg.handle_dguard(message, client, args, sys.modules[__name__])
        else:
            await _safe_send_reply(message, "GoD-HeLL is currently loading!")
        return True

    elif cmd in ("ditem", "battleitem", "dheal", "dpotion", "delixir"):
        if YUNA_RPG_AVAILABLE and yuna_rpg:
            await yuna_rpg.handle_ditem(message, client, args, sys.modules[__name__])
        else:
            await _safe_send_reply(message, "GoD-HeLL is currently loading!")
        return True

    elif cmd in ("dyuna", "yunaassist", "summon", "summons", "companion"):
        if YUNA_RPG_AVAILABLE and yuna_rpg:
            await yuna_rpg.handle_dyuna(message, client, args, sys.modules[__name__])
        else:
            await _safe_send_reply(message, "GoD-HeLL is currently loading!")
        return True

    elif cmd in ("dskill", "dcast"):
        if YUNA_RPG_AVAILABLE and yuna_rpg:
            await yuna_rpg.handle_dskill(message, client, args, sys.modules[__name__])
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

    elif cmd in ("battleshop", "bshop", "gearshop", "rpgshop"):
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

    elif cmd in ("equip", "setgear"):
        if YUNA_RPG_AVAILABLE and yuna_rpg:
            await yuna_rpg.handle_equip(message, client, args, sys.modules[__name__])
        else:
            await _safe_send_reply(message, "Equipment system is currently loading!")
        return True

    elif cmd in ("unequip", "dequip"):
        if YUNA_RPG_AVAILABLE and yuna_rpg:
            await yuna_rpg.handle_unequip(message, client, args, sys.modules[__name__])
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

    elif cmd in ("title", "titles", "tag", "tags"):
        await handle_title(message, client, args)
        return True

    # Devil Horn Sinister Commands
    elif cmd in ("curse", "hex", "cursetarget"):
        await handle_curse(message, client, args)
        return True

    elif cmd in ("hellfire", "burnsin", "demonicfire"):
        await handle_hellfire(message, client, args)
        return True

    elif cmd in ("blackmail", "extort", "extortion"):
        await handle_blackmail(message, client, args)
        return True

    elif cmd in ("sinsurge", "surge", "demonicsurge"):
        await handle_sinsurge(message, client, args)
        return True

    elif cmd in ("junymode", "juny_mode", "jmode", "junystate"):
        await handle_juny_mode(message, client, args)
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
            sub = args[0].lower() if args else None
            await process_boss_choice(message, client, author_id, "negotiate", sub_choice=sub)
            return True
        await _safe_send_reply(message, "- *Yuna tilts her head* \"You can only negotiate dark pacts when Juny descends upon you!\"")
        return True

    elif cmd in ("getaway", "contract"):
        if author_id in _PENDING_BOSS_ENCOUNTERS:
            await process_boss_choice(message, client, author_id, "negotiate", sub_choice=cmd)
            return True
        await _safe_send_reply(message, "- *Yuna tilts her head* \"That command is only available during a Juny encounter!\"")
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

    elif cmd in ("callaid", "summons", "summonaid") or (cmd == "call" and args and args[0].lower() == "aid"):
        await handle_boss_callaid(message, client, args)
        return True

    elif cmd in ("flee", "run", "escape", "surrender"):
        await handle_boss_flee(message, client, args)
        return True

    elif cmd in ("boss", "juny", "bossstatus", "combat"):
        await handle_boss_status(message, client, args)
        return True

    elif cmd in ("provoke", "taunt", "retaliate"):
        await handle_provoke_juny(message, client, args)
        return True

    # Admin & Karmic Controls
    elif cmd in ("setsin", "set-sin") or (cmd == "set" and args and args[0].lower() == "sin"):
        real_args = args[1:] if (cmd == "set" and args and args[0].lower() == "sin") else args
        await handle_set_sin(message, client, real_args)
        return True

    elif cmd in ("giveout", "give-out", "giveitem", "give-item", "itemgive", "admingive", "spawnitem", "spawn"):
        await handle_giveout(message, client, args)
        return True

    elif cmd in ("skipcd", "resetcd", "clearcd", "cdreset", "cdskip"):
        await handle_skipcd(message, client, args)
        return True

    elif cmd in ("reneefight", "fightrenee", "duelrenee", "instantfight", "reneebattle", "fightnow", "quickfight"):
        import yuna_renee
        force_flag = any(a in ("force", "now", "instant", "bypass") for a in args)
        await yuna_renee.start_renee_instant_fight(message, client, ask_ai_fn=_AI_CALLER, force=force_flag)
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

async def juny_stalking_background_loop(client):
    """
    Background loop managing Juny's 5 operational modes:
    - 'idle': Slumbering in the dimensional void.
    - 'awake': Watching souls and their sins silently.
    - 'wandering': Roaming through the casino corridors.
    - 'hostile': Seeking souls with high sin to claim.
    - 'stalking': Lurking behind high-wealth players and whispering chilling warnings.
    """
    if hasattr(client, "wait_until_ready"):
        try:
            await client.wait_until_ready()
        except Exception:
            pass

    # Safety Guard: Ensure this task only runs when client IS Juny
    JUNY_BOT_ID_STR = "1173146642124394547"
    if hasattr(client, "user") and client.user:
        if str(client.user.id) != JUNY_BOT_ID_STR and "juny" not in client.user.name.lower():
            print(f"[JUNY STALKING] Guard: Current client ({client.user}) is not Juny. Terminating loop.")
            return

    modes = ["idle", "awake", "wandering", "hostile", "stalking"]
    while not client.is_closed():
        try:
            await asyncio.sleep(120) # evaluate every 2 minutes
            now = time.time()
            if now - JUNY_STATE.get("last_mode_change", 0) > 600: # change mode every 10 min
                new_mode = random.choice(modes)
                JUNY_STATE["mode"] = new_mode
                JUNY_STATE["last_mode_change"] = now

                # In stalking mode, select a high-wealth target
                if new_mode == "stalking" and _USER_STATS:
                    rich_users = [
                        uid for uid, s in _USER_STATS.items()
                        if s.get("berries", 0) >= 10000 and not has_juny_charm(s)
                    ]
                    if rich_users:
                        JUNY_STATE["stalk_target"] = random.choice(rich_users)
                    else:
                        JUNY_STATE["stalk_target"] = None

            # Stalking mode updates internal state without sending unsolicited DMs to users
            if JUNY_STATE.get("mode") == "stalking" and JUNY_STATE.get("stalk_target"):
                JUNY_STATE["last_whisper_time"] = now
        except Exception as e:
            await asyncio.sleep(60)

