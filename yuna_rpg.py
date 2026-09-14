#!/usr/bin/env python3
"""
yuna_rpg.py - Endgame RPG, GoD-HeLL Dungeon, Arena & Berry Auction Ecosystem
-----------------------------------------------------------------------------
High-roller berry sink and progression mechanics for Yuna.

Features:
1. 👑 Berry Auctions (y!auction, y!bid, y!auctions):
   - Periodic auctions of absurd luxury flexes and 🌌 Legendary items (e.g. Yuna's First Hair Ribbon).
   - Dynamic outbid refunds, escrow management, and passive stat buffs.
2. ⚔️ The Arena & Training (y!arena, y!train, y!skills):
   - Exponentially scaling training costs (100 -> 1M -> 1B+ berries).
   - Increases HP, ATK, DEF, SPD, and Battle Level.
   - Unlocks Weird Skills (Quack of Doom, Pocket Sand, Unsettling Cheese Wheel, etc.)
   - Unlocks Marital Skills (Spousal Telepathy, Wedding Cake Artillery, etc.)
3. 🌋 GoD-HeLL Dungeon (y!godhell, y!dungeon, y!dattack, y!dskill, y!dflee):
   - 10 Progressive stages with scaling monsters and 3 brutal bosses (Mamon, Fallen Executioner, Lucifer).
   - High-roller attacks and skills costing millions to billions of berries per turn!
   - Turn-based combat, loot drops, stage records, and cooldowns.
4. 🛡️ Battle Shop & Gear (y!battleshop, y!bbuy, y!equip):
   - High-tier weapons, armor, accessories, and consumables priced from 10M to 50B berries.
5. 📜 Equipment Page in y!bal:
   - Interactive UI button pagination on y!bal to view full RPG combat equipment and stats!
"""

import os
import re
import json
import time
import math
import random
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

import discord
from discord.ui import View, Button, Select, UserSelect, Modal, TextInput

SCRIPT_DIR = Path(__file__).parent.resolve()
DATA_DIR = SCRIPT_DIR / "data"
AUCTION_DATA_FILE = DATA_DIR / "yuna_auctions.json"

# Color constants
RPG_COLOR = 0xE0245E
AUCTION_COLOR = 0xF45B69
DUNGEON_COLOR = 0x8B0000
ARENA_COLOR = 0xF5A623
SHOP_COLOR = 0x4A90E2

# ─────────────────────────────────────────────────────────────────────────────
# 1. CATALOGS & ITEM DEFINITIONS
# ─────────────────────────────────────────────────────────────────────────────

# Auction Catalog: Hilarious luxury trophies and 🌌 Legendary Relics
AUCTION_CATALOG = {
    "golden_spoon": {
        "id": "golden_spoon",
        "num": 1,
        "alias": "spoon",
        "aliases": ["spoon", "gold spoon", "golden spoon", "1"],
        "name": "Slightly Used Golden Spoon",
        "emoji": "🥄",
        "starting_bid": 500_000_000,
        "is_legendary": False,
        "desc": "Empress Yuna ate chocolate pudding with this solid 24k gold spoon exactly once. Still has faint lick marks and extreme flex energy.",
        "buff_desc": "+3% Max HP & +2% ATK in GoD-HeLL",
        "buffs": {"hp_mult": 0.03, "atk_mult": 0.02}
    },
    "yuna_sock": {
        "id": "yuna_sock",
        "num": 2,
        "alias": "sock",
        "aliases": ["sock", "gym sock", "socks", "2"],
        "name": "Yuna's Left Gym Sock",
        "emoji": "🧦",
        "starting_bid": 300_000_000,
        "is_legendary": False,
        "desc": "Authentic sweaty cotton from anime convention track practice. DO NOT SNIFF under penalty of immediate bankruptcy.",
        "buff_desc": "+5% SPD & +2% Crit Rate",
        "buffs": {"spd_mult": 0.05, "crit_bonus": 0.02}
    },
    "diamond_peeler": {
        "id": "diamond_peeler",
        "num": 3,
        "alias": "peeler",
        "aliases": ["peeler", "potato peeler", "diamond peeler", "3"],
        "name": "Diamond-Encrusted Berry Peeler",
        "emoji": "🪓",
        "starting_bid": 800_000_000,
        "is_legendary": False,
        "desc": "Peels strawberries with 24-carat surgical precision. Completely unnecessary, breathtakingly expensive.",
        "buff_desc": "+5% ATK & +3% Lifesteal",
        "buffs": {"atk_mult": 0.05, "lifesteal": 0.03}
    },
    "bottled_concert_air": {
        "id": "bottled_concert_air",
        "num": 4,
        "alias": "air",
        "aliases": ["air", "concert air", "bottled air", "4"],
        "name": "Bottled Air from Yuna's First Concert",
        "emoji": "🥫",
        "starting_bid": 1_500_000_000,
        "is_legendary": False,
        "desc": "Contains 98% nitrogen, 2% aerosolized idol sweat and crushed dreams. Sealed with wax.",
        "buff_desc": "+7% Max HP & +5% Healing",
        "buffs": {"hp_mult": 0.07, "heal_mult": 0.05}
    },
    "golden_gaming_chair": {
        "id": "golden_gaming_chair",
        "num": 5,
        "alias": "chair",
        "aliases": ["chair", "gaming chair", "gold chair", "5"],
        "name": "Solid 18K Gold RGB Gaming Chair",
        "emoji": "💺",
        "starting_bid": 4_000_000_000,
        "is_legendary": False,
        "desc": "Weighs 500 lbs, completely destroys your hardwood floors, but provides unmatched posture while losing billions at crash.",
        "buff_desc": "+8% DEF & +4% Damage Reduction",
        "buffs": {"def_mult": 0.08, "dmg_reduction": 0.04}
    },
    "platinum_toast": {
        "id": "platinum_toast",
        "num": 6,
        "alias": "toast",
        "aliases": ["toast", "french toast", "platinum toast", "6"],
        "name": "Artisanal Platinum-Flaked French Toast",
        "emoji": "🍞",
        "starting_bid": 8_000_000_000,
        "is_legendary": False,
        "desc": "Indigestible, highly reflective, peak billionaire breakfast. Sparkles when hit by stage lighting.",
        "buff_desc": "+6% Max HP, +6% DEF",
        "buffs": {"hp_mult": 0.06, "def_mult": 0.06}
    },
    # ── 🌌 LEGENDARY AUCTION ITEMS ──
    "hair_ribbon": {
        "id": "hair_ribbon",
        "num": 7,
        "alias": "ribbon",
        "aliases": ["ribbon", "hair ribbon", "yuna ribbon", "7"],
        "name": "Yuna's First Hair Ribbon",
        "emoji": "🌌",
        "starting_bid": 15_000_000_000,
        "is_legendary": True,
        "desc": "The iconic crimson satin ribbon worn on the historic day Yuna opened her first berry casino. Radiates divine cosmic energy.",
        "buff_desc": "🌌 +12% ATK, +10% DEF, +10% HP, +5% Crit Rate",
        "buffs": {"atk_mult": 0.12, "def_mult": 0.10, "hp_mult": 0.10, "crit_bonus": 0.05}
    },
    "berry_archon_crown": {
        "id": "berry_archon_crown",
        "num": 8,
        "alias": "crown",
        "aliases": ["crown", "archon crown", "berry crown", "8"],
        "name": "Crown of the Berry Archon",
        "emoji": "👑",
        "starting_bid": 30_000_000_000,
        "is_legendary": True,
        "desc": "Forged in the heart of a dying strawberry pulsar. Billionaires fall to their knees and weep at its beauty.",
        "buff_desc": "🌌 +15% ATK, +15% DEF, -15% Berry Cost in GoD-HeLL",
        "buffs": {"atk_mult": 0.15, "def_mult": 0.15, "berry_cost_reduction": 0.15}
    },
    "celestial_brooch": {
        "id": "celestial_brooch",
        "num": 9,
        "alias": "brooch",
        "aliases": ["brooch", "strawberry brooch", "celestial brooch", "9"],
        "name": "Celestial Strawberry Brooch",
        "emoji": "🍓",
        "starting_bid": 50_000_000_000,
        "is_legendary": True,
        "desc": "An ancient heirloom imbued with the slumbering souls of ancient berry deities.",
        "buff_desc": "🌌 +20% HP, +15% ATK, +12% SPD",
        "buffs": {"hp_mult": 0.20, "atk_mult": 0.15, "spd_mult": 0.12}
    },
    "void_tea_cup": {
        "id": "void_tea_cup",
        "num": 10,
        "alias": "cup",
        "aliases": ["cup", "teacup", "tea cup", "void cup", "10"],
        "name": "Void-Forged Teacup of the Empress",
        "emoji": "☕",
        "starting_bid": 75_000_000_000,
        "is_legendary": True,
        "desc": "Empress Yuna sips Earl Grey from this infinite dark-matter cup while watching entire dynasties go bankrupt.",
        "buff_desc": "🌌 +25% All Stats, +15% Lifesteal in GoD-HeLL",
        "buffs": {"atk_mult": 0.25, "def_mult": 0.25, "hp_mult": 0.25, "lifesteal": 0.15}
    }
}

# Battle Shop Gear & Items
BATTLE_SHOP_ITEMS = {
    # Weapons
    "katana": {
        "id": "katana",
        "name": "Berry-Forged Katana",
        "slot": "weapon",
        "emoji": "🗡️",
        "price": 10_000_000,
        "stats": {"atk": 75, "spd": 10, "crit": 0.05},
        "desc": "Folded berry-steel katana. Lightweight and razor-sharp for swift strikes. (+75 ATK, +10 SPD, +5% Crit)"
    },
    "claymore": {
        "id": "claymore",
        "name": "Obsidian Berry Claymore",
        "slot": "weapon",
        "emoji": "⚔️",
        "price": 100_000_000,
        "stats": {"atk": 380, "crit": 0.10},
        "desc": "Massive obsidian two-hander infused with pressurized berry syrup. (+380 ATK, +10% Crit)"
    },
    "scythe": {
        "id": "scythe",
        "name": "God-Slayer Berry Scythe",
        "slot": "weapon",
        "emoji": "🪓",
        "price": 1_000_000_000,
        "stats": {"atk": 1_800, "crit": 0.15, "lifesteal": 0.10},
        "desc": "Forged by fallen reaper cherubs to harvest souls and berries alike. (+1,800 ATK, +15% Crit, +10% Lifesteal)"
    },
    "infinity_blade": {
        "id": "infinity_blade",
        "name": "Infinity Berry Blade",
        "slot": "weapon",
        "emoji": "🌌",
        "price": 25_000_000_000,
        "stats": {"atk": 7_500, "crit": 0.25, "lifesteal": 0.20},
        "desc": "A mythic blade vibrating across 11 dimensions of pure luxury. (+7,500 ATK, +25% Crit, +20% Lifesteal)"
    },
    # Armor
    "mail": {
        "id": "mail",
        "name": "Reinforced Berry Mail",
        "slot": "armor",
        "emoji": "🛡️",
        "price": 15_000_000,
        "stats": {"def": 60, "hp": 300},
        "desc": "Interlocking berry-steel chain rings that soften blunt blows. (+60 DEF, +300 Max HP)"
    },
    "aegis": {
        "id": "aegis",
        "name": "Aegis of the Billionaire",
        "slot": "armor",
        "emoji": "🥋",
        "price": 250_000_000,
        "stats": {"def": 480, "hp": 2_500},
        "desc": "Woven from reinforced bullion thread and carbon fiber. (+480 DEF, +2,500 Max HP)"
    },
    "valkyrie": {
        "id": "valkyrie",
        "name": "Celestial Valkyrie Armor",
        "slot": "armor",
        "emoji": "🦺",
        "price": 2_500_000_000,
        "stats": {"def": 2_400, "hp": 12_000, "parry": 0.10},
        "desc": "Blessed by archangels before they fled into exile. Deflects severe punishment. (+2,400 DEF, +12,000 HP, +10% Parry)"
    },
    "abyssal_plate": {
        "id": "abyssal_plate",
        "name": "GoD-HeLL Abyssal Plate",
        "slot": "armor",
        "emoji": "🖤",
        "price": 50_000_000_000,
        "stats": {"def": 9_500, "hp": 55_000, "dmg_reduction": 0.25},
        "desc": "Quenched in the magma of the 10th Stage. Shrugs off catastrophic boss attacks. (+9,500 DEF, +55,000 HP, 25% Damage Nullification)"
    },
    # Accessories
    "greedy_ring": {
        "id": "greedy_ring",
        "name": "Ring of the Greedy King",
        "slot": "accessory",
        "emoji": "💍",
        "price": 50_000_000,
        "stats": {"atk": 150, "hp": 1_000},
        "desc": "Whispers sweet promises of compound interest into your veins. (+150 ATK, +1,000 HP)"
    },
    "spousal_harmony": {
        "id": "spousal_harmony",
        "name": "Pendant of Spousal Harmony",
        "slot": "accessory",
        "emoji": "💖",
        "price": 500_000_000,
        "stats": {"marital_boost": 1.0, "def": 600},
        "desc": "Resonates with your spouse's soul. Doubles the potency of all Marital Skills! (+100% Marital Skill Power, +600 DEF)"
    },
    "annihilation_orb": {
        "id": "annihilation_orb",
        "name": "Orb of Berry Annihilation",
        "slot": "accessory",
        "emoji": "🔮",
        "price": 10_000_000_000,
        "stats": {"atk": 4_200, "berry_cost_reduction": 0.25},
        "desc": "Harvests energy from spent berries. (+4,200 ATK, -25% Attack/Skill Berry Cost in GoD-HeLL)"
    },
    # Consumables
    "dungeon_elixir": {
        "id": "dungeon_elixir",
        "name": "Dungeon Elixir of Immortality",
        "slot": "consumable",
        "emoji": "🧪",
        "price": 5_000_000,
        "desc": "Drink in GoD-HeLL with `y!dheal` or the [Heal] button to restore 50% of your maximum HP immediately!"
    },
    "adrenaline_shot": {
        "id": "adrenaline_shot",
        "name": "Billionaire's Adrenaline Shot",
        "slot": "consumable",
        "emoji": "💉",
        "price": 25_000_000,
        "desc": "Grants +100% ATK for your next 3 strikes during a GoD-HeLL dungeon run!"
    },
    "dungeon_key": {
        "id": "dungeon_key",
        "name": "GoD-HeLL Golden Dungeon Key",
        "slot": "consumable",
        "emoji": "🗝️",
        "price": 50_000_000,
        "desc": "Instantly resets your 10-minute GoD-HeLL dungeon cooldown so you can raid again immediately!"
    }
}

# Weird Skills (Unlocked via Battle Level)
WEIRD_SKILLS = {
    "quack_of_doom": {
        "id": "quack_of_doom",
        "name": "Quack of Doom",
        "emoji": "🦆",
        "req_level": 2,
        "berry_cost": 2_000_000,
        "dmg_mult": 1.5,
        "stun_chance": 0.20,
        "desc": "Utters an eldritch demonic waterfowl quack. Deals 150% Sonic Psychic damage and has a 20% chance to stun the enemy for 1 turn."
    },
    "pocket_sand": {
        "id": "pocket_sand",
        "name": "Pocket Sand",
        "emoji": "💥",
        "req_level": 5,
        "berry_cost": 5_000_000,
        "dmg_mult": 1.1,
        "debuff": "blind",
        "desc": "Throws coarse playground gravel directly into the target's eyes! Deals 110% damage and reduces the enemy's next strike damage by 50%."
    },
    "berry_tornado": {
        "id": "berry_tornado",
        "name": "Berry Tornado",
        "emoji": "🌪️",
        "req_level": 8,
        "berry_cost": 15_000_000,
        "dmg_mult": 2.4,
        "hits": 3,
        "desc": "Summons a vortex of razor-sharp crystallized strawberries. Hits 3 times for a total of 240% damage plus a 15% bleeding tick."
    },
    "cheese_wheel": {
        "id": "cheese_wheel",
        "name": "Unsettling Cheese Wheel",
        "emoji": "🧀",
        "req_level": 12,
        "berry_cost": 40_000_000,
        "dmg_mult": 2.8,
        "heal_pct": 0.20,
        "desc": "Hurls a solid 50-pound wheel of 10-year aged Dutch Gouda. Deals 280% blunt trauma and heals yourself for 20% Max HP from sheer dairy satisfaction."
    },
    "dramatic_monologue": {
        "id": "dramatic_monologue",
        "name": "Dramatic Monologue",
        "emoji": "🎭",
        "req_level": 16,
        "berry_cost": 100_000_000,
        "dmg_mult": 0.0,
        "stun_chance": 1.0,
        "buff_next_atk": 2.5,
        "desc": "Recites an excruciatingly long 12-page tragic villain monologue. Skips the enemy's turn completely and charges your next strike by +150%!"
    },
    "existential_crisis": {
        "id": "existential_crisis",
        "name": "Existential Crisis Ray",
        "emoji": "⚡",
        "req_level": 20,
        "berry_cost": 250_000_000,
        "dmg_mult": 4.5,
        "true_damage": True,
        "desc": "Forces the enemy to question if they are just an array of numbers in a Python bot. Deals 450% TRUE VOID DAMAGE, completely ignoring enemy DEF!"
    },
    "supernova_berry": {
        "id": "supernova_berry",
        "name": "Supernova Berry Blast",
        "emoji": "🌌",
        "req_level": 25,
        "berry_cost": 750_000_000,
        "dmg_mult": 7.0,
        "desc": "Compresses 1 billion berries into a nuclear singularity and detonates it point-blank. Deals a staggering 700% Cosmic Damage!"
    }
}

# Marital Skills (Unlocked if married via y!marry)
MARITAL_SKILLS = {
    "spousal_telepathy": {
        "id": "spousal_telepathy",
        "name": "Spousal Telepathy",
        "emoji": "💍",
        "berry_cost": 25_000_000,
        "dmg_mult": 0.0,
        "heal_pct": 0.25,
        "shield_pct": 0.40,
        "desc": "Channels your spouse's loving aura through the matrimonial tether. Restores 25% Max HP and creates a barrier absorbing 40% incoming damage."
    },
    "wedding_cake_artillery": {
        "id": "wedding_cake_artillery",
        "name": "Wedding Cake Artillery",
        "emoji": "🍰",
        "berry_cost": 75_000_000,
        "dmg_mult": 3.6,
        "desc": "Launches a ballistic 5-tier buttercream wedding cake directly at the target. Deals 360% sweet burst damage (boosted to 450% if spouse is in server!)."
    },
    "nagging_thunder": {
        "id": "nagging_thunder",
        "name": "Nagging Thunder",
        "emoji": "⚡",
        "berry_cost": 150_000_000,
        "dmg_mult": 4.2,
        "armor_pierce": 0.50,
        "desc": "Unleashes an overwhelming storm of domestic grievances. Pierces 50% of enemy DEF and electrocutes for 420% lightning damage."
    },
    "till_death": {
        "id": "till_death",
        "name": "Till Death Do Us Part",
        "emoji": "💖",
        "berry_cost": 400_000_000,
        "passive_revive": True,
        "desc": "Eternal vow of love. If you take lethal damage in GoD-HeLL, your spouse's phantom will immediately revive you with 50% HP! (Once per run)"
    }
}

# GoD-HeLL 10 Stages & Bosses
DUNGEON_STAGES = [
    {
        "stage": 1,
        "name": "Imps of Inflation",
        "emoji": "👾",
        "level": 10,
        "max_hp": 1_400,
        "atk": 55,
        "def": 15,
        "attack_cost": 1_000_000,
        "reward_exp": 120,
        "reward_title": "Inflation Dodger",
        "is_boss": False
    },
    {
        "stage": 2,
        "name": "Debt-Collector Specters",
        "emoji": "👻",
        "level": 22,
        "max_hp": 4_000,
        "atk": 130,
        "def": 35,
        "attack_cost": 2_500_000,
        "reward_exp": 280,
        "reward_title": "Debt Free",
        "is_boss": False
    },
    {
        "stage": 3,
        "name": "Molten Berry Golem",
        "emoji": "🗿",
        "level": 35,
        "max_hp": 11_000,
        "atk": 290,
        "def": 95,
        "attack_cost": 6_000_000,
        "reward_exp": 550,
        "reward_title": "Golem Breaker",
        "is_boss": False
    },
    {
        "stage": 4,
        "name": "The Greedy Arch-Demon Mamon",
        "emoji": "😈",
        "level": 50,
        "max_hp": 38_000,
        "atk": 820,
        "def": 240,
        "attack_cost": 18_000_000,
        "reward_exp": 1_200,
        "reward_title": "Mamon's Scourge",
        "is_boss": True,
        "boss_desc": "BOSS ENCOUNTER 1: Mamon periodically casts *Berry Extortion*, draining an extra 10M berries to heal himself!"
    },
    {
        "stage": 5,
        "name": "Hellfire Cerberus",
        "emoji": "🐕‍🦺",
        "level": 68,
        "max_hp": 85_000,
        "atk": 1_750,
        "def": 460,
        "attack_cost": 35_000_000,
        "reward_exp": 2_200,
        "reward_title": "Hound Tamer",
        "is_boss": False
    },
    {
        "stage": 6,
        "name": "Shadow of the Bankrupt",
        "emoji": "👤",
        "level": 85,
        "max_hp": 180_000,
        "atk": 3_500,
        "def": 1_050,
        "attack_cost": 75_000_000,
        "reward_exp": 4_000,
        "reward_title": "Solvent Survivor",
        "is_boss": False
    },
    {
        "stage": 7,
        "name": "Juny's Fallen Executioner",
        "emoji": "⚔️",
        "level": 105,
        "max_hp": 420_000,
        "atk": 7_500,
        "def": 2_300,
        "attack_cost": 160_000_000,
        "reward_exp": 8_500,
        "reward_title": "Executioner of Sins",
        "is_boss": True,
        "boss_desc": "BOSS ENCOUNTER 2: Wields *Sin Guillotine*, landing brutal 200% critical slashes that slice through armor!"
    },
    {
        "stage": 8,
        "name": "Abyssal Leviathan",
        "emoji": "🐉",
        "level": 125,
        "max_hp": 950_000,
        "atk": 15_500,
        "def": 4_800,
        "attack_cost": 320_000_000,
        "reward_exp": 16_000,
        "reward_title": "Leviathan Cleaver",
        "is_boss": False
    },
    {
        "stage": 9,
        "name": "Void-Touched Cherubim",
        "emoji": "👼",
        "level": 145,
        "max_hp": 2_000_000,
        "atk": 30_000,
        "def": 9_500,
        "attack_cost": 650_000_000,
        "reward_exp": 32_000,
        "reward_title": "Heaven's Reckoning",
        "is_boss": False
    },
    {
        "stage": 10,
        "name": "Lucifer of the Berry Void (The Billionaire Consumer)",
        "emoji": "👑",
        "level": 175,
        "max_hp": 5_000_000,
        "atk": 65_000,
        "def": 22_000,
        "attack_cost": 1_250_000_000,
        "reward_exp": 100_000,
        "reward_title": "Conqueror of GoD-HeLL",
        "is_boss": True,
        "boss_desc": "FINAL TITAN BOSS: The ultimate consumer of wealth. Casts *Billion-Berry Cataclysm*, incinerating wealth and dealing cataclysmic void damage!"
    }
]

# In-Memory Active Dungeon Runs: user_id -> run_dict
ACTIVE_DUNGEON_RUNS: Dict[str, dict] = {}
DUNGEON_COOLDOWN_SECONDS = 600.0  # 10 minutes

def get_user_dungeon_run(user_id: Union[str, int]) -> Tuple[Optional[str], Optional[dict]]:
    """Returns (host_id, run_dict) for a user whether they are the host or a joined party ally."""
    user_id_str = str(user_id)
    if user_id_str in ACTIVE_DUNGEON_RUNS:
        return user_id_str, ACTIVE_DUNGEON_RUNS[user_id_str]
    for h_id, run in ACTIVE_DUNGEON_RUNS.items():
        if user_id_str in run.get("party", {}):
            return h_id, run
    return None, None



def find_auction_item(query: str) -> Optional[dict]:
    """Finds an auction item by key, number, full name, or short alias."""
    if not query:
        return None
    q = query.lower().strip()
    if q in AUCTION_CATALOG:
        return AUCTION_CATALOG[q]
    for k, item in AUCTION_CATALOG.items():
        if q == str(item.get("num")):
            return item
        if q == item.get("alias", "").lower():
            return item
        if q in item.get("aliases", []):
            return item
        if q == item["name"].lower() or q in item["name"].lower():
            return item
    return None

def parse_bid_arguments(args: list) -> Tuple[Optional[str], Optional[int]]:
    """
    Parses (optional_item_query, bid_amount) from user args in any order.
    Examples:
      ['600m'] -> (None, 600_000_000)
      ['spoon', '600m'] -> ('spoon', 600_000_000)
      ['600m', 'spoon'] -> ('spoon', 600_000_000)
      ['on', 'ribbon', '50b'] -> ('ribbon', 50_000_000_000)
      ['1', '750m'] -> ('1', 750_000_000)
      ['750m', '1'] -> ('1', 750_000_000)
      ['1', '600000000'] -> ('1', 600_000_000)
    """
    if not args:
        return None, None

    cleaned_tokens = []
    for token in args:
        clean = str(token).lower().replace(",", "").replace("_", "").strip()
        if clean in ("on", "for", "at", "berries", "berry"):
            continue
        if clean:
            cleaned_tokens.append(clean)

    if not cleaned_tokens:
        return None, None

    def try_parse_amount(tok: str) -> Optional[int]:
        m = re.match(r"^(\d+(?:\.\d+)?)([kmbt]?)$", tok)
        if not m:
            return None
        val_str, suf = m.group(1), m.group(2)
        try:
            val = float(val_str)
            mult = 1
            if suf == "k": mult = 1_000
            elif suf == "m": mult = 1_000_000
            elif suf == "b": mult = 1_000_000_000
            elif suf == "t": mult = 1_000_000_000_000
            return int(val * mult)
        except Exception:
            return None

    # Case 1: single token
    if len(cleaned_tokens) == 1:
        amt = try_parse_amount(cleaned_tokens[0])
        if amt is not None and (re.search(r"[kmbt]", cleaned_tokens[0]) or amt > 50):
            return None, amt
        return cleaned_tokens[0], None

    # Case 2: multiple tokens. First pass for explicit unit suffixes
    amount_idx = None
    parsed_amount = None
    for idx, tok in enumerate(cleaned_tokens):
        if re.search(r"^\d+(?:\.\d+)?[kmbt]$", tok):
            amt = try_parse_amount(tok)
            if amt is not None:
                parsed_amount = amt
                amount_idx = idx
                break

    # Second pass: largest number > 50 (prevents numeric catalog IDs like '1'..'10' from consuming the bid)
    if amount_idx is None:
        candidates = []
        for idx, tok in enumerate(cleaned_tokens):
            amt = try_parse_amount(tok)
            if amt is not None:
                candidates.append((amt, idx))
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            if candidates[0][0] > 50:
                parsed_amount = candidates[0][0]
                amount_idx = candidates[0][1]

    # Fallback pass: any valid number
    if amount_idx is None:
        for idx, tok in enumerate(cleaned_tokens):
            amt = try_parse_amount(tok)
            if amt is not None:
                parsed_amount = amt
                amount_idx = idx
                break

    if amount_idx is not None:
        item_tokens = [tok for i, tok in enumerate(cleaned_tokens) if i != amount_idx]
        item_query = " ".join(item_tokens).strip() if item_tokens else None
        return item_query, parsed_amount

    return " ".join(cleaned_tokens).strip(), None


class CustomBidModal(Modal, title="👑 Place Your Auction Bid"):
    bid_input = TextInput(
        label="Bid Amount in Berries (🫐)",
        placeholder="e.g. 600M, 25B, 1.5B, or 750000000",
        min_length=1,
        max_length=32,
        required=True
    )

    def __init__(self, yuna_gambling_mod):
        super().__init__()
        self.yuna_gambling_mod = yuna_gambling_mod

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        raw_val = self.bid_input.value.strip()
        await handle_bid(
            interaction.message,
            interaction.client,
            [raw_val],
            self.yuna_gambling_mod,
            actor=interaction.user
        )

# ─────────────────────────────────────────────────────────────────────────────
# 2. AUCTION PERSISTENCE & HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _load_auction_data() -> dict:
    """Loads active auction state from disk."""
    if AUCTION_DATA_FILE.exists():
        try:
            with open(AUCTION_DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_auction_data(data: dict):
    """Saves auction state atomically to disk."""
    try:
        AUCTION_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = AUCTION_DATA_FILE.with_suffix(f".tmp.{os.getpid()}")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        tmp.replace(AUCTION_DATA_FILE)
    except Exception as e:
        print(f"[AUCTION SAVE ERROR] {e}")

def get_or_create_active_auction(yuna_gambling_mod=None) -> dict:
    """Returns the current active auction, or seeds a new one if expired or none exists."""
    data = _load_auction_data()
    now = time.time()
    curr = data.get("current_auction")

    # Check if current auction has expired
    if curr and curr.get("end_time", 0) <= now:
        # Award winner trophy
        winner_id = curr.get("highest_bidder_id")
        if winner_id:
            try:
                g_file = DATA_DIR / "yuna_gambling_data.json"
                if g_file.exists():
                    with open(g_file, "r", encoding="utf-8") as gf:
                        g_data = json.load(gf)
                    u_dict = g_data.get("users", {})
                    if winner_id in u_dict:
                        u = u_dict[winner_id]
                        trophies = u.setdefault("auction_trophies", [])
                        if curr["item_id"] not in trophies:
                            trophies.append(curr["item_id"])
                        with open(g_file, "w", encoding="utf-8") as gf:
                            json.dump(g_data, gf, indent=2)
                if yuna_gambling_mod and hasattr(yuna_gambling_mod, "_USER_STATS"):
                    if winner_id in yuna_gambling_mod._USER_STATS:
                        trophies = yuna_gambling_mod._USER_STATS[winner_id].setdefault("auction_trophies", [])
                        if curr["item_id"] not in trophies:
                            trophies.append(curr["item_id"])
            except Exception as _trophy_err:
                print(f"[AUCTION TROPHY AWARD ERROR] {_trophy_err}")

        # Finalize history
        history = data.setdefault("history", [])
        history.append({
            "item_id": curr.get("item_id"),
            "winner_id": curr.get("highest_bidder_id"),
            "winner_name": curr.get("highest_bidder_name", "Nobody"),
            "final_bid": curr.get("current_bid", 0),
            "closed_at": now
        })
        curr = None

    if not curr:
        # Pick next item (25% chance of 🌌 Legendary Item, 75% Luxury Flex)
        is_legendary = random.random() < 0.25
        pool = [k for k, v in AUCTION_CATALOG.items() if v.get("is_legendary") == is_legendary]
        if not pool:
            pool = list(AUCTION_CATALOG.keys())
        picked_key = random.choice(pool)
        item = AUCTION_CATALOG[picked_key]

        # Auctions last 3 hours
        duration_sec = 3 * 3600
        curr = {
            "item_id": picked_key,
            "item_name": item["name"],
            "emoji": item["emoji"],
            "is_legendary": item.get("is_legendary", False),
            "starting_bid": item["starting_bid"],
            "current_bid": item["starting_bid"],
            "highest_bidder_id": None,
            "highest_bidder_name": None,
            "start_time": now,
            "end_time": now + duration_sec,
            "bid_count": 0
        }
        data["current_auction"] = curr
        _save_auction_data(data)

    return curr

# ─────────────────────────────────────────────────────────────────────────────
# 3. STATS & RPG CALCULATION ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def ensure_player_rpg(user: dict) -> dict:
    """Ensures RPG fields are populated on user stats dict."""
    user.setdefault("battle_level", 1)
    user.setdefault("battle_exp", 0)
    user.setdefault("training_level", 0)
    user.setdefault("training_atk", 0)
    user.setdefault("training_def", 0)
    user.setdefault("training_hp", 0)
    user.setdefault("training_spd", 0)
    user.setdefault("equipped", {"weapon": None, "armor": None, "accessory": None})
    user.setdefault("auction_trophies", [])
    user.setdefault("godhell_highest_stage", 0)
    user.setdefault("dungeon_runs_completed", 0)
    user.setdefault("last_dungeon_time", 0.0)
    user.setdefault("last_train_time", 0.0)
    return user

def get_training_cost(training_level: int) -> int:
    """
    Computes exponential training cost in Berries.
    Starts at 100 🫐 and scales exponentially to act as the ultimate billionaire sink.
    """
    if training_level <= 0:
        return 100
    return int(100 * (1.68 ** min(60, training_level)))

def get_player_rpg_stats(user: dict) -> dict:
    """
    Computes effective HP, ATK, DEF, SPD, Crit, Lifesteal, and Cost Reductions
    combining Training Levels, Battle Level, Equipped Gear, and Won Auction Trophies.
    """
    ensure_player_rpg(user)
    t_atk = user.get("training_atk", 0)
    t_def = user.get("training_def", 0)
    t_hp = user.get("training_hp", 0)
    t_spd = user.get("training_spd", 0)
    b_lvl = user.get("battle_level", 1)

    # Base attributes
    base_hp = 120 + (b_lvl * 35) + (t_hp * 30)
    base_atk = 20 + (b_lvl * 8) + (t_atk * 7)
    base_def = 10 + (b_lvl * 5) + (t_def * 5)
    base_spd = 10 + (b_lvl * 2) + (t_spd * 3)

    crit_rate = 0.05 + min(0.40, base_spd * 0.001)
    lifesteal = 0.0
    dmg_reduction = 0.0
    berry_cost_reduc = 0.0
    marital_boost = 1.0

    # Apply Equipped Equipment
    eq = user.get("equipped", {})
    eq_names = {}
    for slot in ("weapon", "armor", "accessory"):
        item_id = eq.get(slot)
        if item_id and item_id in BATTLE_SHOP_ITEMS:
            item = BATTLE_SHOP_ITEMS[item_id]
            eq_names[slot] = f"{item['emoji']} {item['name']}"
            istats = item.get("stats", {})
            base_hp += istats.get("hp", 0)
            base_atk += istats.get("atk", 0)
            base_def += istats.get("def", 0)
            base_spd += istats.get("spd", 0)
            crit_rate += istats.get("crit", 0.0)
            lifesteal += istats.get("lifesteal", 0.0)
            dmg_reduction += istats.get("dmg_reduction", 0.0)
            berry_cost_reduc += istats.get("berry_cost_reduction", 0.0)
            marital_boost += istats.get("marital_boost", 0.0)

    # Apply Auction Trophies (Multiplicative buffs)
    trophies = user.get("auction_trophies", [])
    for t_id in trophies:
        if t_id in AUCTION_CATALOG:
            buffs = AUCTION_CATALOG[t_id].get("buffs", {})
            base_hp += int(base_hp * buffs.get("hp_mult", 0.0))
            base_atk += int(base_atk * buffs.get("atk_mult", 0.0))
            base_def += int(base_def * buffs.get("def_mult", 0.0))
            base_spd += int(base_spd * buffs.get("spd_mult", 0.0))
            crit_rate += buffs.get("crit_bonus", 0.0)
            lifesteal += buffs.get("lifesteal", 0.0)
            dmg_reduction += buffs.get("dmg_reduction", 0.0)
            berry_cost_reduc += buffs.get("berry_cost_reduction", 0.0)

    return {
        "level": b_lvl,
        "exp": user.get("battle_exp", 0),
        "max_hp": max(100, int(base_hp)),
        "atk": max(10, int(base_atk)),
        "def": max(5, int(base_def)),
        "spd": max(5, int(base_spd)),
        "crit_rate": round(min(0.75, crit_rate), 3),
        "lifesteal": round(min(0.60, lifesteal), 2),
        "dmg_reduction": round(min(0.50, dmg_reduction), 2),
        "berry_cost_reduction": round(min(0.50, berry_cost_reduc), 2),
        "marital_boost": marital_boost,
        "equipped_names": eq_names
    }

def get_unlocked_skills(user: dict) -> Tuple[List[dict], List[dict]]:
    """Returns list of unlocked weird skills and marital skills for user."""
    b_lvl = user.get("battle_level", 1)
    has_spouse = bool(user.get("spouse"))

    unlocked_weird = []
    for k, sk in WEIRD_SKILLS.items():
        if b_lvl >= sk["req_level"]:
            unlocked_weird.append(sk)

    unlocked_marital = []
    if has_spouse:
        for k, sk in MARITAL_SKILLS.items():
            unlocked_marital.append(sk)

    return unlocked_weird, unlocked_marital

# ─────────────────────────────────────────────────────────────────────────────
# 4. ARENA & TRAINING COMMANDS
# ─────────────────────────────────────────────────────────────────────────────

async def handle_arena(message, client, args: list, yuna_gambling_mod, actor: Optional[discord.User] = None):
    """Displays the Arena, training options, stats, and skill progression."""
    target_user = actor or message.author
    author_id = str(target_user.id)
    author_name = getattr(target_user, "display_name", target_user.name)
    stats = await yuna_gambling_mod._get_user_stats(author_id)
    ensure_player_rpg(stats)
    rpg = get_player_rpg_stats(stats)
    cost = get_training_cost(stats.get("training_level", 0))

    unlocked_w, unlocked_m = get_unlocked_skills(stats)

    w_str = ", ".join(f"{s['emoji']} `{s['name']}`" for s in unlocked_w) if unlocked_w else "*None yet (Unlocks at Lv. 2)*"
    m_str = ", ".join(f"{s['emoji']} `{s['name']}`" for s in unlocked_m) if unlocked_m else ("*Requires Marriage (y!marry)*" if not stats.get("spouse") else "*All active!*")

    embed = discord.Embed(
        title="⚔️ The Grand Arena of Yuna",
        description=(
            f"Welcome to the training grounds, gladiator **{author_name}**!\n"
            f"Here, berries are forged into raw combat might. Training cost scales exponentially!\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎖️ **Battle Level:** `Lv. {rpg['level']}` | **EXP:** `{rpg['exp']:,}`\n"
            f"🏋️ **Training Sessions:** `{stats.get('training_level', 0)} completed`\n"
            f"🫐 **Next Training Cost:** `{cost:,} 🫐`\n\n"
            f"❤️ **Max HP:** `{rpg['max_hp']:,}`\n"
            f"⚔️ **Attack (ATK):** `{rpg['atk']:,}`\n"
            f"🛡️ **Defense (DEF):** `{rpg['def']:,}`\n"
            f"⚡ **Speed (SPD):** `{rpg['spd']:,}` *(Crit: {rpg['crit_rate']*100:.1f}%)*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎭 **Weird Skills:** {w_str}\n"
            f"💍 **Marital Skills:** {m_str}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Train with `y!train [stat]` (e.g. `y!train atk`, `y!train hp`, `y!train all`) or click below!"
        ),
        color=ARENA_COLOR
    )
    view = ArenaTrainView(author_id, yuna_gambling_mod)
    await yuna_gambling_mod._safe_send_reply(message, embed=embed, view=view)

async def handle_train(message, client, args: list, yuna_gambling_mod, actor: Optional[discord.User] = None):
    """Handles y!train [stat]."""
    target_user = actor or message.author
    author_id = str(target_user.id)
    author_name = getattr(target_user, "display_name", target_user.name)
    stats = await yuna_gambling_mod._get_user_stats(author_id)
    ensure_player_rpg(stats)

    target_stat = "all"
    if args:
        first = args[0].lower().strip()
        if first in ("atk", "attack", "damage", "str"):
            target_stat = "atk"
        elif first in ("def", "defense", "armor", "shield"):
            target_stat = "def"
        elif first in ("hp", "health", "life", "vitality"):
            target_stat = "hp"
        elif first in ("spd", "speed", "crit", "agility"):
            target_stat = "spd"
        elif first in ("all", "even", "balanced"):
            target_stat = "all"

    t_level = stats.get("training_level", 0)
    cost = get_training_cost(t_level)

    berries = stats.get("berries", 0)
    if berries < cost:
        await yuna_gambling_mod._safe_send_reply(
            message,
            f"- *Yuna flexes with a golden barbell* \"You need **{cost:,} 🫐** for training session #{t_level+1}, but you only have **{berries:,} 🫐**! Go gamble or raid GoD-HeLL!\""
        )
        return

    # Deduct berries and apply training stats
    stats["berries"] = berries - cost
    stats["training_level"] = t_level + 1
    stats["last_train_time"] = time.time()

    stat_gains = []
    if target_stat == "atk":
        stats["training_atk"] = stats.get("training_atk", 0) + 1
        stat_gains.append("+7 ATK")
    elif target_stat == "def":
        stats["training_def"] = stats.get("training_def", 0) + 1
        stat_gains.append("+5 DEF")
    elif target_stat == "hp":
        stats["training_hp"] = stats.get("training_hp", 0) + 1
        stat_gains.append("+30 Max HP")
    elif target_stat == "spd":
        stats["training_spd"] = stats.get("training_spd", 0) + 1
        stat_gains.append("+3 SPD (+0.3% Crit)")
    else: # all
        stats["training_atk"] = stats.get("training_atk", 0) + 1
        stats["training_def"] = stats.get("training_def", 0) + 1
        stats["training_hp"] = stats.get("training_hp", 0) + 1
        stats["training_spd"] = stats.get("training_spd", 0) + 1
        stat_gains.append("+7 ATK, +5 DEF, +30 HP, +3 SPD")

    # Battle Level Progression (every 2 training sessions)
    old_lvl = stats.get("battle_level", 1)
    new_lvl = 1 + (stats["training_level"] // 2)
    leveled_up = new_lvl > old_lvl
    if leveled_up:
        stats["battle_level"] = new_lvl

    yuna_gambling_mod._save_data_sync()

    # Check newly unlocked skills
    unlock_notices = []
    if leveled_up:
        for sk in WEIRD_SKILLS.values():
            if sk["req_level"] == new_lvl:
                unlock_notices.append(f"🎭 **NEW WEIRD SKILL UNLOCKED:** {sk['emoji']} **{sk['name']}**!\n*{sk['desc']}*")

    lvl_str = f"\n🎉 **BATTLE LEVEL UP!** You reached **Battle Level {new_lvl}**!" if leveled_up else ""
    unlock_str = f"\n\n" + "\n".join(unlock_notices) if unlock_notices else ""

    next_cost = get_training_cost(stats["training_level"])
    await yuna_gambling_mod._safe_send_reply(
        message,
        f"🏋️ **INTENSE TRAINING COMPLETE!**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Spent: `{cost:,} 🫐`\n"
        f"Gains: **{', '.join(stat_gains)}**{lvl_str}{unlock_str}\n"
        f"Next Training Session Cost: `{next_cost:,} 🫐` *(y!train {target_stat})*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

async def handle_skills(message, client, args: list, yuna_gambling_mod, actor: Optional[discord.User] = None):
    """Displays all Weird Skills and Marital Skills."""
    target_user = actor or message.author
    author_id = str(target_user.id)
    author_name = getattr(target_user, "display_name", target_user.name)
    stats = await yuna_gambling_mod._get_user_stats(author_id)
    ensure_player_rpg(stats)
    b_lvl = stats.get("battle_level", 1)
    has_spouse = bool(stats.get("spouse"))

    embed = discord.Embed(
        title="📜 Yuna's Codex of Weird & Marital Skills",
        description="Skills can be unleashed in **GoD-HeLL** dungeon stages for devastating tactical effects!",
        color=RPG_COLOR
    )

    # Weird Skills
    w_lines = []
    for sk in WEIRD_SKILLS.values():
        unlocked = b_lvl >= sk["req_level"]
        status = "✅ `[UNLOCKED]`" if unlocked else f"🔒 `[Requires Battle Lv. {sk['req_level']}]`"
        cost_display = f"{sk['berry_cost']:,} 🫐"
        w_lines.append(f"{sk['emoji']} **{sk['name']}** — {status}\n• Cost: `{cost_display}` | {sk['desc']}")
    embed.add_field(name="🎭 Weird Skills", value="\n\n".join(w_lines), inline=False)

    # Marital Skills
    m_lines = []
    m_status = "✅ `[ACTIVE]`" if has_spouse else "🔒 `[Requires Marriage via y!marry]`"
    for sk in MARITAL_SKILLS.values():
        cost_display = f"{sk['berry_cost']:,} 🫐"
        m_lines.append(f"{sk['emoji']} **{sk['name']}** — {m_status}\n• Cost: `{cost_display}` | {sk['desc']}")
    embed.add_field(name="💍 Marital Skills (Spouse Synergy)", value="\n\n".join(m_lines), inline=False)

    embed.set_footer(text="Skills are used in GoD-HeLL during combat turns via y!dskill or the [Skill] button!")
    await yuna_gambling_mod._safe_send_reply(message, embed=embed)

class ArenaTrainView(View):
    def __init__(self, user_id: str, yuna_gambling_mod):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.yuna_gambling_mod = yuna_gambling_mod

    @discord.ui.button(label="Train ATK", emoji="⚔️", style=discord.ButtonStyle.primary)
    async def train_atk(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("This is not your training session!", ephemeral=True)
            return
        await interaction.response.defer()
        await handle_train(interaction.message, interaction.client, ["atk"], self.yuna_gambling_mod, actor=interaction.user)

    @discord.ui.button(label="Train DEF", emoji="🛡️", style=discord.ButtonStyle.secondary)
    async def train_def(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("This is not your training session!", ephemeral=True)
            return
        await interaction.response.defer()
        await handle_train(interaction.message, interaction.client, ["def"], self.yuna_gambling_mod, actor=interaction.user)

    @discord.ui.button(label="Train HP", emoji="❤️", style=discord.ButtonStyle.success)
    async def train_hp(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("This is not your training session!", ephemeral=True)
            return
        await interaction.response.defer()
        await handle_train(interaction.message, interaction.client, ["hp"], self.yuna_gambling_mod, actor=interaction.user)

    @discord.ui.button(label="Train All Stats", emoji="⭐", style=discord.ButtonStyle.danger)
    async def train_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("This is not your training session!", ephemeral=True)
            return
        await interaction.response.defer()
        await handle_train(interaction.message, interaction.client, ["all"], self.yuna_gambling_mod, actor=interaction.user)

# ─────────────────────────────────────────────────────────────────────────────
# 5. 👑 BERRY AUCTION COMMANDS
# ─────────────────────────────────────────────────────────────────────────────

async def handle_auction(message, client, args: list, yuna_gambling_mod, actor: Optional[discord.User] = None):
    """Displays the active Berry Auction, or spotlights a specific catalog item if queried."""
    target_user = actor or message.author
    author_id = str(target_user.id)

    # Check if user queried a specific item (e.g. y!auction spoon, y!auction 1, y!auction ribbon)
    if args:
        query = " ".join(args).strip()
        matched = find_auction_item(query)
        if matched:
            badge = "🌌 **LEGENDARY RELIC**" if matched.get("is_legendary") else "🏆 **LUXURY TROPHY**"
            embed = discord.Embed(
                title=f"{badge} • {matched['emoji']} {matched['name']}",
                description=(
                    f"*{matched['desc']}*\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🔢 **Catalog ID:** `[{matched.get('num', '?')}]` • **Short Alias:** `{matched.get('alias', matched['id'])}`\n"
                    f"💰 **Starting Bid:** `{matched['starting_bid']:,} 🫐`\n"
                    f"✨ **Permanent Stat Perk:** `{matched['buff_desc']}`\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"Check the live auction with `y!auction` or place a bid with `y!bid {matched.get('alias', matched['id'])} <amount>`!"
                ),
                color=AUCTION_COLOR
            )
            await yuna_gambling_mod._safe_send_reply(message, embed=embed)
            return

    auction = get_or_create_active_auction(yuna_gambling_mod)
    item_id = auction["item_id"]
    item = AUCTION_CATALOG.get(item_id, {})

    now = time.time()
    time_left_sec = max(0, int(auction["end_time"] - now))
    hrs = time_left_sec // 3600
    mins = (time_left_sec % 3600) // 60
    secs = time_left_sec % 60
    time_str = f"{hrs}h {mins}m {secs}s"

    bidder_str = f"<@{auction['highest_bidder_id']}> ({auction['highest_bidder_name']})" if auction.get("highest_bidder_id") else "*No bids placed yet!*"
    badge = "🌌 **LEGENDARY ITEM**" if auction.get("is_legendary") else "🏆 **YUNA'S LUXURY AUCTION**"
    item_num = item.get("num", 1)
    short_alias = item.get("alias", item_id)

    embed = discord.Embed(
        title=f"{badge} • {auction['emoji']} {auction['item_name']}",
        description=(
            f"*{item.get('desc')}*\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔢 **Item Code:** `[{item_num}]` • **Alias:** `{short_alias}`\n"
            f"💰 **Current Bid:** `{auction['current_bid']:,} 🫐`\n"
            f"👑 **High Bidder:** {bidder_str}\n"
            f"⏳ **Time Remaining:** `{time_str}`\n"
            f"🔢 **Total Bids:** `{auction.get('bid_count', 0)}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✨ **Permanent Stat Perks:**\n`{item.get('buff_desc')}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Bid easily with `y!bid <amount>` (e.g. `y!bid {int(auction['current_bid'] * 1.1):,}`) or click **Custom Bid** below!"
        ),
        color=AUCTION_COLOR
    )
    view = AuctionView(author_id, yuna_gambling_mod)
    await yuna_gambling_mod._safe_send_reply(message, embed=embed, view=view)

async def handle_bid(message, client, args: list, yuna_gambling_mod, actor: Optional[discord.User] = None):
    """Handles y!bid <amount> or y!bid <item> <amount>."""
    target_user = actor or message.author
    author_id = str(target_user.id)
    author_name = getattr(target_user, "display_name", target_user.name)

    if not args:
        await yuna_gambling_mod._safe_send_reply(
            message,
            "- *Yuna holds out a golden gavel* \"How much are you bidding? Use `y!bid <amount>` (e.g. `y!bid 600m`)! Check `y!auction` for the current bid!\""
        )
        return

    item_query, bid_amount = parse_bid_arguments(args)

    if bid_amount is None or bid_amount <= 0:
        await yuna_gambling_mod._safe_send_reply(
            message,
            "- *Yuna tilts her head* \"Please enter a valid bid amount (e.g. `y!bid 600m`, `y!bid 25b`, or `y!bid spoon 750m`)!\""
        )
        return

    data = _load_auction_data()
    curr = data.get("current_auction")
    now = time.time()
    if not curr or curr.get("end_time", 0) <= now:
        await yuna_gambling_mod._safe_send_reply(message, "The previous auction just closed! Type `y!auction` to launch the next one!")
        return

    # If user specified an item name or alias, verify it matches the current item
    if item_query:
        matched_item = find_auction_item(item_query)
        if matched_item and matched_item["id"] != curr["item_id"]:
            await yuna_gambling_mod._safe_send_reply(
                message,
                f"- *Yuna shakes her head* \"Item `{item_query}` is not the active auction! The active item is {curr['emoji']} **{curr['item_name']}**! Bid on it with `y!bid {bid_amount:,}`!\""
            )
            return

    stats = await yuna_gambling_mod._get_user_stats(author_id)
    user_berries = stats.get("berries", 0)
    if user_berries < bid_amount:
        await yuna_gambling_mod._safe_send_reply(
            message,
            f"- *Yuna chuckles* \"You cannot bid **{bid_amount:,} 🫐**! You only have **{user_berries:,} 🫐** in your pouch!\""
        )
        return

    if curr.get("highest_bidder_id") == author_id:
        await yuna_gambling_mod._safe_send_reply(message, "You are already the highest bidder on this auction!")
        return

    # Min increment: at least +5% over current bid
    min_required = int(curr["current_bid"] * 1.05) if curr.get("highest_bidder_id") else curr["starting_bid"]
    if bid_amount < min_required:
        await yuna_gambling_mod._safe_send_reply(
            message,
            f"Your bid is too low! You must bid at least **{min_required:,} 🫐** (current bid: `{curr['current_bid']:,}`)."
        )
        return

    # Refund previous bidder immediately
    prev_bidder_id = curr.get("highest_bidder_id")
    prev_bid = curr.get("current_bid", 0)
    if prev_bidder_id and prev_bid > 0:
        prev_stats = await yuna_gambling_mod._get_user_stats(prev_bidder_id)
        prev_stats["berries"] = prev_stats.get("berries", 0) + prev_bid

    # Deduct berries from new high bidder
    stats["berries"] = user_berries - bid_amount

    # Update auction
    curr["current_bid"] = bid_amount
    curr["highest_bidder_id"] = author_id
    curr["highest_bidder_name"] = author_name
    curr["bid_count"] = curr.get("bid_count", 0) + 1

    # Anti-snipe: if less than 3 minutes left, extend by 3 minutes
    if curr["end_time"] - now < 180:
        curr["end_time"] = now + 180

    data["current_auction"] = curr
    _save_auction_data(data)
    yuna_gambling_mod._save_data_sync()

    prev_alert = f" (Previous bidder <@{prev_bidder_id}> was refunded `{prev_bid:,} 🫐`!)" if prev_bidder_id else ""
    await yuna_gambling_mod._safe_send_reply(
        message,
        f"👑 **NEW HIGHEST BID ACCEPTED!**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Bidder: **{author_name}** (<@{author_id}>)\n"
        f"Item: {curr['emoji']} **{curr['item_name']}**\n"
        f"New Price: `{bid_amount:,} 🫐`{prev_alert}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"*- Yuna bangs her golden gavel* \"Bid recognized! Going once, going twice...!\""
    )

async def handle_auctions_catalog(message, client, args: list, yuna_gambling_mod, actor: Optional[discord.User] = None):
    """Displays the catalogue of all luxury and legendary auction items and their simple aliases."""
    embed = discord.Embed(
        title="🏆 Yuna's Imperial Auction Catalog",
        description=(
            "All items won at auction grant **permanent passive stat perks** in GoD-HeLL and display on your `y!bal` profile!\n"
            "You can bid or inspect any item using its **Number** or **Short Alias** (e.g. `y!bid spoon 600m` or `y!auction ribbon`)!\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=AUCTION_COLOR
    )
    for k, item in AUCTION_CATALOG.items():
        tag = "🌌 `[LEGENDARY]`" if item.get("is_legendary") else "🏆 `[LUXURY]`"
        num = item.get("num", "?")
        alias = item.get("alias", k)
        embed.add_field(
            name=f"[{num}] {item['emoji']} {item['name']} • `{alias}` — `{item['starting_bid']:,} 🫐` {tag}",
            value=f"• {item['desc']}\n• **Perk:** `{item['buff_desc']}`",
            inline=False
        )
    embed.set_footer(text="Check the active auction with y!auction and place bids with y!bid <amount> or y!bid <alias> <amount>!")
    await yuna_gambling_mod._safe_send_reply(message, embed=embed)

class AuctionView(View):
    def __init__(self, user_id: str, yuna_gambling_mod):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.yuna_gambling_mod = yuna_gambling_mod

    @discord.ui.button(label="Bid +10%", emoji="💰", style=discord.ButtonStyle.success, row=0)
    async def bid_quick(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        curr = get_or_create_active_auction(self.yuna_gambling_mod)
        bid_target = int(curr["current_bid"] * 1.10) if curr.get("highest_bidder_id") else curr["starting_bid"]
        await handle_bid(interaction.message, interaction.client, [str(bid_target)], self.yuna_gambling_mod, actor=interaction.user)

    @discord.ui.button(label="Custom Bid", emoji="✍️", style=discord.ButtonStyle.primary, row=0)
    async def custom_bid_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CustomBidModal(self.yuna_gambling_mod))

    @discord.ui.button(label="Refresh", emoji="🔄", style=discord.ButtonStyle.secondary, row=0)
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await handle_auction(interaction.message, interaction.client, [], self.yuna_gambling_mod, actor=interaction.user)

    @discord.ui.button(label="Catalog", emoji="📜", style=discord.ButtonStyle.secondary, row=0)
    async def catalog_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await handle_auctions_catalog(interaction.message, interaction.client, [], self.yuna_gambling_mod, actor=interaction.user)

# ─────────────────────────────────────────────────────────────────────────────
# 6. 🌋 GoD-HeLL DUNGEON ENGINE & CO-OP SYSTEM
# ─────────────────────────────────────────────────────────────────────────────

class DungeonSkillSelect(Select):
    """Dropdown for players to select and cast their unlocked Weird Skills and Marital Skills."""
    def __init__(self, user_skills: list, cost_reduc: float = 0.0, disabled: bool = False):
        options = []
        if user_skills:
            for sk in user_skills:
                eff_cost = int(sk["berry_cost"] * (1.0 - cost_reduc))
                desc = sk.get("desc", "")
                if len(desc) > 85:
                    desc = desc[:82] + "..."
                label = f"{sk['name']} ({eff_cost:,} 🫐)"
                if len(label) > 100:
                    label = label[:100]
                options.append(discord.SelectOption(
                    label=label,
                    value=sk["id"],
                    description=desc,
                    emoji=sk.get("emoji", "✨")
                ))
        else:
            options.append(discord.SelectOption(
                label="No Skills Unlocked Yet",
                value="none",
                description="Train in y!arena to Battle Lv. 2+ or marry via y!marry!",
                emoji="🔒",
                default=True
            ))

        super().__init__(
            placeholder="✨ Choose a Skill to Unleash...",
            min_values=1,
            max_values=1,
            options=options[:25],
            disabled=disabled or (len(user_skills) == 0),
            row=0
        )

    async def callback(self, interaction: discord.Interaction):
        if not self.values or self.values[0] == "none":
            await interaction.response.send_message("You don't have any unlocked skills to cast! Train in `y!arena` to unlock them!", ephemeral=True)
            return

        skill_id = self.values[0]
        await interaction.response.defer()
        await handle_dskill(
            interaction.message,
            interaction.client,
            [skill_id],
            self.view.yuna_gambling_mod,
            actor=interaction.user,
            interaction=interaction
        )

class DungeonAidInviteView(View):
    """View sent when inviting a specific ally into GoD-HeLL."""
    def __init__(self, host_id: str, target_id: str, yuna_gambling_mod):
        super().__init__(timeout=300)
        self.host_id = host_id
        self.target_id = target_id
        self.yuna_gambling_mod = yuna_gambling_mod

    @discord.ui.button(label="Join Raid!", emoji="⚔️", style=discord.ButtonStyle.success)
    async def accept_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.target_id:
            await interaction.response.send_message("This summons was sent to someone else!", ephemeral=True)
            return
        await interaction.response.defer()
        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass
        await join_dungeon_raid(interaction.message, interaction.client, self.host_id, interaction.user, self.yuna_gambling_mod)

    @discord.ui.button(label="Decline", emoji="❌", style=discord.ButtonStyle.secondary)
    async def decline_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.target_id:
            await interaction.response.send_message("This summons was sent to someone else!", ephemeral=True)
            return
        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass
        await interaction.response.send_message(f"You declined the summons from <@{self.host_id}>.", ephemeral=True)

class DungeonLfgView(View):
    """Open LFG broadcast view allowing any server member to join the raid party."""
    def __init__(self, host_id: str, yuna_gambling_mod):
        super().__init__(timeout=600)
        self.host_id = host_id
        self.yuna_gambling_mod = yuna_gambling_mod

    @discord.ui.button(label="Join Raid!", emoji="⚔️", style=discord.ButtonStyle.success)
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) == self.host_id:
            await interaction.response.send_message("You are already the host of this raid party!", ephemeral=True)
            return
        await interaction.response.defer()
        await join_dungeon_raid(interaction.message, interaction.client, self.host_id, interaction.user, self.yuna_gambling_mod)

class DungeonCallAidSelectView(View):
    """UserSelect menu for selecting allies to invite from the server."""
    def __init__(self, host_id: str, yuna_gambling_mod):
        super().__init__(timeout=300)
        self.host_id = host_id
        self.yuna_gambling_mod = yuna_gambling_mod

    @discord.ui.select(
        cls=UserSelect,
        placeholder="Select allies to recruit into GoD-HeLL...",
        min_values=1,
        max_values=2
    )
    async def user_select_callback(self, interaction: discord.Interaction, select: UserSelect):
        if str(interaction.user.id) != self.host_id:
            await interaction.response.send_message("Only the dungeon raid party can recruit allies!", ephemeral=True)
            return
        await interaction.response.defer()
        for user in select.values:
            if getattr(user, "bot", False) or str(user.id) == self.host_id:
                continue
            run = ACTIVE_DUNGEON_RUNS.get(self.host_id)
            if not run:
                break
            stage_info = DUNGEON_STAGES[run["stage_idx"]]
            view = DungeonAidInviteView(self.host_id, str(user.id), self.yuna_gambling_mod)
            embed = discord.Embed(
                title=f"🌋 SUMMONS TO GoD-HeLL: AID <@{self.host_id}>!",
                description=(
                    f"⚔️ <@{self.host_id}> is locked in combat with {stage_info['emoji']} **{stage_info['name']}** on Stage `{stage_info['stage']}/10`!\n"
                    f"They have summoned {user.mention} to fight by their side!\n\n"
                    f"• **Co-op Perks:** +15% Combo ATK & Shared Retribution!\n"
                    f"• Click **Join Raid!** to equip your gear and enter the fray!"
                ),
                color=DUNGEON_COLOR
            )
            await self.yuna_gambling_mod._safe_send_reply(
                interaction.message,
                content=f"{user.mention} **You have been summoned to GoD-HeLL!**",
                embed=embed,
                view=view
            )

async def join_dungeon_raid(message, client, host_id: str, ally_user: discord.User, yuna_gambling_mod):
    """Adds an ally into the host's active GoD-HeLL party with their real RPG stats."""
    ally_id = str(ally_user.id)
    ally_name = getattr(ally_user, "display_name", ally_user.name)

    if host_id not in ACTIVE_DUNGEON_RUNS:
        await yuna_gambling_mod._safe_send_reply(message, "The dungeon raid has already ended or disbanded!")
        return

    run = ACTIVE_DUNGEON_RUNS[host_id]
    party = run.setdefault("party", {})

    if ally_id in party:
        await yuna_gambling_mod._safe_send_reply(message, f"**{ally_name}** is already in this raid party!")
        return

    other_host, other_run = get_user_dungeon_run(ally_id)
    if other_run and other_host != host_id:
        await yuna_gambling_mod._safe_send_reply(message, f"**{ally_name}** is currently locked in another active dungeon raid!")
        return

    if len(party) >= 3:
        await yuna_gambling_mod._safe_send_reply(message, "This GoD-HeLL raid party is already full (max 3 fighters)!")
        return

    now = time.time()
    ally_stats = await yuna_gambling_mod._get_user_stats(ally_id)
    ensure_player_rpg(ally_stats)

    # Cooldown Check
    last_run = ally_stats.get("last_dungeon_time", 0.0)
    if (now - last_run) < DUNGEON_COOLDOWN_SECONDS:
        rem = int(DUNGEON_COOLDOWN_SECONDS - (now - last_run))
        mins, secs = rem // 60, rem % 60
        inv = ally_stats.get("inventory", {})
        if inv.get("dungeon_key", 0) > 0:
            inv["dungeon_key"] -= 1
            ally_stats["last_dungeon_time"] = 0.0
            yuna_gambling_mod._save_data_sync()
            key_msg = " (Consumed 1 **GoD-HeLL Golden Dungeon Key** to bypass cooldown!)"
        else:
            await yuna_gambling_mod._safe_send_reply(
                message,
                f"⏳ **RUNIC WARDS!** **{ally_name}** must wait **{mins}m {secs}s** before descending into GoD-HeLL! (Buy a `dungeon_key` in `y!battleshop` to skip!)"
            )
            return
    else:
        key_msg = ""

    ally_rpg = get_player_rpg_stats(ally_stats)
    party[ally_id] = {
        "id": ally_id,
        "name": ally_name,
        "hp": ally_rpg["max_hp"],
        "max_hp": ally_rpg["max_hp"],
        "alive": True,
        "is_host": False,
        "revive_used": False,
        "next_atk_boost": 1.0
    }
    ally_stats["last_dungeon_time"] = now
    yuna_gambling_mod._save_data_sync()

    stage_info = DUNGEON_STAGES[run["stage_idx"]]
    join_log = f"🤝 **{ally_name}** entered GoD-HeLL to reinforce the raid party! (+15% Co-op Combo ATK active){key_msg}"
    await yuna_gambling_mod._safe_send_reply(
        message,
        f"🤝 **REINFORCEMENTS HAVE ARRIVED!**\n"
        f"**{ally_name}** (<@{ally_id}>) joined <@{host_id}>'s raid against {stage_info['emoji']} **{stage_info['name']}**!\n"
        f"Party Size: `{len(party)}/3 Fighters` • Ready your strikes!"
    )
    host_stats = await yuna_gambling_mod._get_user_stats(host_id)
    host_rpg = get_player_rpg_stats(host_stats)
    await render_dungeon_screen(message, host_id, run, host_rpg, yuna_gambling_mod, battle_log=join_log)

async def handle_godhell(message, client, args: list, yuna_gambling_mod, actor: Optional[discord.User] = None):
    """Enters or resumes the GoD-HeLL dungeon for the user."""
    target_user = actor or message.author
    author_id = str(target_user.id)
    author_name = getattr(target_user, "display_name", target_user.name)
    now = time.time()

    # Check if user is already participating in any active run (host or ally)
    existing_host, existing_run = get_user_dungeon_run(author_id)
    if existing_run:
        stats = await yuna_gambling_mod._get_user_stats(author_id)
        rpg = get_player_rpg_stats(stats)
        await render_dungeon_screen(message, existing_host, existing_run, rpg, yuna_gambling_mod, actor=target_user)
        return

    stats = await yuna_gambling_mod._get_user_stats(author_id)
    ensure_player_rpg(stats)
    rpg = get_player_rpg_stats(stats)

    # Cooldown Check (10 mins)
    last_run = stats.get("last_dungeon_time", 0.0)
    if (now - last_run) < DUNGEON_COOLDOWN_SECONDS:
        rem = int(DUNGEON_COOLDOWN_SECONDS - (now - last_run))
        mins, secs = rem // 60, rem % 60
        inv = stats.get("inventory", {})
        has_key = inv.get("dungeon_key", 0) > 0
        key_str = f" (You can consume a **GoD-HeLL Golden Dungeon Key** from `y!battleshop` to reset it!)" if not has_key else " (Consume your `dungeon_key` with `y!bbuy` or inventory to skip!)"
        await yuna_gambling_mod._safe_send_reply(
            message,
            f"⏳ **GoD-HeLL IS SEALED BY RUNIC WARDS!**\n"
            f"You must wait **{mins}m {secs}s** before descending into the abyss again!{key_str}"
        )
        return

    # Initialize new active run
    ACTIVE_DUNGEON_RUNS[author_id] = {
        "host_id": author_id,
        "stage_idx": 0,
        "enemy_hp": DUNGEON_STAGES[0]["max_hp"],
        "turns": 0,
        "berries_burned": 0,
        "start_time": now,
        "party": {
            author_id: {
                "id": author_id,
                "name": author_name,
                "hp": rpg["max_hp"],
                "max_hp": rpg["max_hp"],
                "alive": True,
                "is_host": True,
                "revive_used": False,
                "next_atk_boost": 1.0
            }
        }
    }
    stats["last_dungeon_time"] = now
    yuna_gambling_mod._save_data_sync()

    run = ACTIVE_DUNGEON_RUNS[author_id]
    await render_dungeon_screen(message, author_id, run, rpg, yuna_gambling_mod, actor=target_user)

async def handle_dcallaid(message, client, args: list, yuna_gambling_mod, actor: Optional[discord.User] = None):
    """Handles y!dcallaid / y!callaid [@user1 ...] to recruit allies into GoD-HeLL."""
    target_user = actor or message.author
    author_id = str(target_user.id)
    author_name = getattr(target_user, "display_name", target_user.name)

    host_id, run = get_user_dungeon_run(author_id)
    if not run:
        await yuna_gambling_mod._safe_send_reply(message, "You are not currently in an active GoD-HeLL raid! Enter with `y!godhell`!")
        return

    party = run.setdefault("party", {})
    if len(party) >= 3:
        await yuna_gambling_mod._safe_send_reply(message, "Your dungeon party is already full (max 3 fighters)!")
        return

    stage_info = DUNGEON_STAGES[run["stage_idx"]]
    targets = []

    # 1. From mentions
    if message.mentions:
        for m in message.mentions:
            if not getattr(m, "bot", False) and str(m.id) not in party and str(m.id) != author_id:
                if m not in targets:
                    targets.append(m)
                if len(party) + len(targets) >= 3:
                    break

    # 2. From args
    if len(party) + len(targets) < 3 and args:
        for token in args:
            clean = token.strip()
            if not clean or clean.lower() in ("aid", "call", "coop", "dcallaid"):
                continue
            m_match = re.search(r'<@!?(\d{17,20})>', clean)
            target_id = m_match.group(1) if m_match else (clean if re.fullmatch(r'\d{17,20}', clean) else None)
            if target_id and target_id != author_id and target_id not in party:
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
                    if len(party) + len(targets) >= 3:
                        break

    if targets:
        for t in targets:
            view = DungeonAidInviteView(host_id, str(t.id), yuna_gambling_mod)
            embed = discord.Embed(
                title=f"🌋 SUMMONS TO GoD-HeLL: AID {author_name}!",
                description=(
                    f"⚔️ **{author_name}** (<@{author_id}>) is locked in combat with {stage_info['emoji']} **{stage_info['name']}** on **Stage {stage_info['stage']}/10**!\n"
                    f"They have summoned {t.mention} to stand by their side in the abyss!\n\n"
                    f"• **Co-op Perks:** +15% Combo ATK & Shared Retribution!\n"
                    f"• Click **Join Raid!** to equip your gear and enter the fray!\n"
                    f"• Click **Decline** if you fear the flames of GoD-HeLL."
                ),
                color=DUNGEON_COLOR
            )
            await yuna_gambling_mod._safe_send_reply(
                message,
                content=f"{t.mention} **You have been summoned to GoD-HeLL!**",
                embed=embed,
                view=view
            )
    else:
        view = DungeonLfgView(host_id, yuna_gambling_mod)
        embed = discord.Embed(
            title="🌋 GoD-HeLL RECRUITMENT • OPEN LFG RAID PARTY",
            description=(
                f"⚔️ **{author_name}** (<@{author_id}>) has opened their GoD-HeLL battle party!\n"
                f"Currently fighting: {stage_info['emoji']} **{stage_info['name']}** (Stage `{stage_info['stage']}/10`)\n"
                f"Party Slots: `{len(party)}/3 Fighters`\n\n"
                f"✨ **Co-op Bonus:** Joining allies add +15% combo damage and split enemy retribution!\n"
                f"Click **Join Raid!** below to jump into the fray, or use `y!dcallaid @user`!"
            ),
            color=DUNGEON_COLOR
        )
        await yuna_gambling_mod._safe_send_reply(message, embed=embed, view=view)

async def handle_djoin(message, client, args: list, yuna_gambling_mod, actor: Optional[discord.User] = None):
    """Handles y!djoin [@host] to join an active GoD-HeLL raid party."""
    target_user = actor or message.author
    target_host_id = None

    if message.mentions:
        target_host_id = str(message.mentions[0].id)
    elif args:
        clean = args[0].strip()
        m_match = re.search(r'<@!?(\d{17,20})>', clean)
        target_host_id = m_match.group(1) if m_match else (clean if re.fullmatch(r'\d{17,20}', clean) else None)

    if not target_host_id:
        for h_id, r in ACTIVE_DUNGEON_RUNS.items():
            if len(r.get("party", {})) < 3 and str(target_user.id) not in r.get("party", {}):
                target_host_id = h_id
                break

    if not target_host_id or target_host_id not in ACTIVE_DUNGEON_RUNS:
        await yuna_gambling_mod._safe_send_reply(message, "No open GoD-HeLL raids found! Start your own with `y!godhell`!")
        return

    await join_dungeon_raid(message, client, target_host_id, target_user, yuna_gambling_mod)

async def render_dungeon_screen(message, host_id: str, run: dict, rpg: dict, yuna_gambling_mod, battle_log: str = "", interaction: Optional[discord.Interaction] = None, actor: Optional[discord.User] = None, resend_as_new: bool = False):
    """Renders the GoD-HeLL encounter state with individual party health bars and selectable skills."""
    stage_info = DUNGEON_STAGES[run["stage_idx"]]
    stage_num = stage_info["stage"]

    cost_reduc = rpg.get("berry_cost_reduction", 0.0)
    base_cost = stage_info["attack_cost"]
    eff_cost = int(base_cost * (1.0 - cost_reduc))

    e_hp = run["enemy_hp"]
    e_max = stage_info["max_hp"]

    def make_bar(cur, mx, length=10):
        frac = max(0.0, min(1.0, cur / max(1, mx)))
        filled = int(round(frac * length))
        return "█" * filled + "░" * (length - filled)

    e_bar = make_bar(e_hp, e_max, length=12)

    party = run.setdefault("party", {})
    party_lines = []
    for pid, fighter in party.items():
        f_cur = fighter.get("hp", 0)
        f_mx = fighter.get("max_hp", 100)
        f_bar = make_bar(f_cur, f_mx, length=10)
        badge = "👑" if fighter.get("is_host") else "⚔️"
        if not fighter.get("alive", True):
            badge = "💀"
        party_lines.append(f"{badge} **{fighter['name']}:** `{f_cur:,} / {f_mx:,} HP` `[{f_bar}]`")

    party_display = "\n".join(party_lines) if party_lines else f"❤️ **Your HP:** `{run.get('player_hp', 100):,} / {rpg['max_hp']:,}`"

    boss_tag = "👑 **[BOSS ENCOUNTER]**" if stage_info.get("is_boss") else f"Stage `{stage_num}/10`"
    coop_tag = "✨ **Co-op Synergy:** `+15% Combo Damage & Shared Aggro Active!`\n" if len(party) > 1 else ""
    log_section = f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n📜 **Combat Log:**\n{battle_log}" if battle_log else ""

    embed = discord.Embed(
        title=f"🌋 GoD-HeLL Dungeon • {stage_info['emoji']} {stage_info['name']}",
        description=(
            f"{boss_tag}\n"
            f"*{stage_info.get('boss_desc', 'The air reeks of sulfur and burnt billions of berries.')}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 **RAID PARTY ({len(party)}/3):**\n{party_display}\n\n"
            f"👾 **{stage_info['name']} HP:** `{e_hp:,} / {e_max:,}`\n`[{e_bar}]`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{coop_tag}"
            f"🫐 **Strike Berry Cost:** `{eff_cost:,} 🫐` per attack\n"
            f"🔥 **Total Berries Burned This Raid:** `{run.get('berries_burned', 0):,} 🫐`\n"
            f"⚔️ **Party Stats:** `{rpg['atk']:,} ATK` | `{rpg['def']:,} DEF` | `{rpg['crit_rate']*100:.1f}% Crit`"
            f"{log_section}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Choose an action: Select a **Skill** above or click **[Attack]**, **[Heal]**, **[Call Aid]**, or **[Flee]**!"
        ),
        color=DUNGEON_COLOR
    )

    # Determine skills for the active viewer / interactor
    viewer = actor or getattr(message, "author", None)
    viewer_id = str(viewer.id) if viewer else host_id
    viewer_stats = await yuna_gambling_mod._get_user_stats(viewer_id)
    ensure_player_rpg(viewer_stats)
    unlocked_w, unlocked_m = get_unlocked_skills(viewer_stats)
    viewer_skills = unlocked_w + unlocked_m
    viewer_rpg = get_player_rpg_stats(viewer_stats)

    view = DungeonCombatView(host_id, yuna_gambling_mod, user_skills=viewer_skills, cost_reduc=viewer_rpg.get("berry_cost_reduction", 0.0))

    if not resend_as_new:
        if interaction and getattr(interaction, "message", None):
            try:
                await interaction.message.edit(embed=embed, view=view)
                run["message"] = interaction.message
                return
            except Exception:
                pass
        if run.get("message"):
            try:
                await run["message"].edit(embed=embed, view=view)
                return
            except Exception:
                pass

    channel = None
    if interaction and getattr(interaction, "channel", None):
        channel = interaction.channel
    elif getattr(message, "channel", None):
        channel = message.channel
    elif run.get("message") and getattr(run["message"], "channel", None):
        channel = run["message"].channel

    sent_msg = None
    if channel:
        try:
            sent_msg = await channel.send(embed=embed, view=view)
        except Exception:
            pass

    if not sent_msg:
        sent_msg = await yuna_gambling_mod._safe_send_reply(message, embed=embed, view=view)

    if sent_msg:
        run["message"] = sent_msg

async def handle_dattack(message, client, args: list, yuna_gambling_mod, actor: Optional[discord.User] = None, interaction: Optional[discord.Interaction] = None):
    """Executes a standard berry-infused basic attack in GoD-HeLL with co-op combo scaling."""
    target_user = actor or message.author
    author_id = str(target_user.id)
    author_name = getattr(target_user, "display_name", target_user.name)

    host_id, run = get_user_dungeon_run(author_id)
    if not run:
        await yuna_gambling_mod._safe_send_reply(message, "You are not currently inside GoD-HeLL! Enter with `y!godhell`!")
        return

    party = run.setdefault("party", {})
    if author_id not in party:
        party[author_id] = {
            "id": author_id,
            "name": author_name,
            "hp": run.get("player_hp", 1000),
            "max_hp": run.get("player_hp", 1000),
            "alive": True,
            "is_host": True
        }

    fighter = party[author_id]
    if not fighter.get("alive", True):
        await yuna_gambling_mod._safe_send_reply(
            message,
            f"💀 **{author_name} is currently slain!** You cannot strike until the party clears this stage to revive you!"
        )
        return

    stats = await yuna_gambling_mod._get_user_stats(author_id)
    rpg = get_player_rpg_stats(stats)
    stage_info = DUNGEON_STAGES[run["stage_idx"]]

    cost_reduc = rpg.get("berry_cost_reduction", 0.0)
    base_cost = stage_info["attack_cost"]
    eff_cost = int(base_cost * (1.0 - cost_reduc))

    # Check Berry Balance
    berries = stats.get("berries", 0)
    if berries < eff_cost:
        await yuna_gambling_mod._safe_send_reply(
            message,
            f"❌ **INSUFFICIENT BERRIES!**\n"
            f"**{author_name}**, your attack requires **{eff_cost:,} 🫐**, but you only have **{berries:,} 🫐**!\n"
            f"Deposit more berries or ask your allies to strike!"
        )
        return

    stats["berries"] = berries - eff_cost
    run["berries_burned"] = run.get("berries_burned", 0) + eff_cost

    # Strike calculation
    is_crit = random.random() < rpg["crit_rate"]
    crit_mult = 1.75 if is_crit else 1.0
    boost = fighter.pop("next_atk_boost", 1.0)
    coop_mult = 1.15 if len(party) > 1 else 1.0

    raw_dmg = (rpg["atk"] * crit_mult * boost * coop_mult * random.uniform(0.92, 1.08)) - (stage_info["def"] * 0.45)
    player_dmg = max(20, int(raw_dmg))
    run["enemy_hp"] = max(0, run["enemy_hp"] - player_dmg)

    # Lifesteal
    lifesteal_heal = 0
    if rpg.get("lifesteal", 0) > 0:
        lifesteal_heal = int(player_dmg * rpg["lifesteal"])
        fighter["hp"] = min(fighter["max_hp"], fighter["hp"] + lifesteal_heal)

    crit_str = " 💥 **CRITICAL HIT!**" if is_crit else ""
    combo_str = " *(+15% Co-op Combo!)*" if len(party) > 1 else ""
    heal_str = f" *(Healed +{lifesteal_heal:,} HP!)*" if lifesteal_heal > 0 else ""
    log = f"⚔️ **{author_name}** struck {stage_info['name']} for **{player_dmg:,} dmg**!{crit_str}{combo_str}{heal_str}"

    # Check Enemy Defeated
    if run["enemy_hp"] <= 0:
        await process_stage_victory(message, host_id, run, rpg, stage_info, stats, yuna_gambling_mod, interaction=interaction, actor=target_user)
        return

    # Enemy Retaliation
    alive_fighters = [f for f in party.values() if f.get("alive", True)]
    if not alive_fighters:
        del ACTIVE_DUNGEON_RUNS[host_id]
        yuna_gambling_mod._save_data_sync()
        await yuna_gambling_mod._safe_send_reply(message, f"💀 **THE ENTIRE RAID PARTY WAS WIPED OUT ON STAGE {stage_info['stage']}!**")
        return

    if random.random() < 0.60 or len(alive_fighters) == 1:
        target_fighter = fighter
    else:
        target_fighter = random.choice(alive_fighters)

    target_stats = await yuna_gambling_mod._get_user_stats(target_fighter["id"])
    target_rpg = get_player_rpg_stats(target_stats)

    e_atk = stage_info["atk"]
    if stage_info.get("is_boss") and random.random() < 0.35:
        if run["stage_idx"] == 3: # Mamon
            extort = 10_000_000
            target_stats["berries"] = max(0, target_stats.get("berries", 0) - extort)
            run["enemy_hp"] = min(stage_info["max_hp"], run["enemy_hp"] + 5_000)
            log += f"\n😈 **Mamon cast Berry Extortion!** Drained 10M 🫐 from {target_fighter['name']} and healed 5,000 HP!"
        elif run["stage_idx"] == 6: # Executioner
            e_atk = int(e_atk * 1.8)
            log += f"\n⚔️ **Executioner cast Sin Guillotine!** A brutal armor-piercing slice against {target_fighter['name']}!"
        elif run["stage_idx"] == 9: # Lucifer
            cataclysm = 50_000_000
            target_stats["berries"] = max(0, target_stats.get("berries", 0) - cataclysm)
            e_atk = int(e_atk * 2.2)
            log += f"\n👑 **Lucifer unleashed Billion-Berry Cataclysm!** Obliterated 50M 🫐 and burned the party with void flames!"

    enemy_raw = (e_atk * random.uniform(0.9, 1.1)) - (target_rpg["def"] * 0.5)
    enemy_dmg = max(10, int(enemy_raw * (1.0 - target_rpg.get("dmg_reduction", 0.0))))

    target_fighter["hp"] = max(0, target_fighter["hp"] - enemy_dmg)
    log += f"\n🩸 {stage_info['name']} retaliated against **{target_fighter['name']}** for **{enemy_dmg:,} damage**!"

    # Fatal check
    if target_fighter["hp"] <= 0:
        if not target_fighter.get("revive_used") and target_stats.get("spouse"):
            target_fighter["revive_used"] = True
            target_fighter["hp"] = int(target_fighter["max_hp"] * 0.50)
            log += f"\n💖 **TILL DEATH DO US PART!** {target_fighter['name']}'s spouse intercepted the killing blow and revived them to 50% HP!"
        else:
            target_fighter["alive"] = False
            log += f"\n💀 **{target_fighter['name']} was slain in combat!**"

    if all(not f.get("alive", True) for f in party.values()):
        del ACTIVE_DUNGEON_RUNS[host_id]
        yuna_gambling_mod._save_data_sync()
        await yuna_gambling_mod._safe_send_reply(
            message,
            f"💀 **TOTAL PARTY WIPE IN GoD-HeLL!**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{stage_info['emoji']} **{stage_info['name']}** slaughtered the entire raid party on Stage {stage_info['stage']}!\n"
            f"Total Berries Burned: `{run.get('berries_burned', 0):,} 🫐`\n"
            f"Train up in `y!arena` and regroup before attempting the descent again!"
        )
        return

    yuna_gambling_mod._save_data_sync()
    await render_dungeon_screen(message, host_id, run, rpg, yuna_gambling_mod, battle_log=log, interaction=interaction, actor=target_user)

async def handle_dskill(message, client, args: list, yuna_gambling_mod, actor: Optional[discord.User] = None, interaction: Optional[discord.Interaction] = None):
    """Unleashes a chosen Weird Skill or Marital Skill in GoD-HeLL."""
    target_user = actor or message.author
    author_id = str(target_user.id)
    author_name = getattr(target_user, "display_name", target_user.name)

    host_id, run = get_user_dungeon_run(author_id)
    if not run:
        await yuna_gambling_mod._safe_send_reply(message, "You are not currently in GoD-HeLL! Enter with `y!godhell`!")
        return

    party = run.setdefault("party", {})
    if author_id not in party:
        party[author_id] = {
            "id": author_id,
            "name": author_name,
            "hp": run.get("player_hp", 1000),
            "max_hp": run.get("player_hp", 1000),
            "alive": True,
            "is_host": True
        }

    fighter = party[author_id]
    if not fighter.get("alive", True):
        await yuna_gambling_mod._safe_send_reply(message, f"💀 **{author_name} is currently slain!** An ally must clear the stage to revive you!")
        return

    stats = await yuna_gambling_mod._get_user_stats(author_id)
    rpg = get_player_rpg_stats(stats)
    stage_info = DUNGEON_STAGES[run["stage_idx"]]

    unlocked_w, unlocked_m = get_unlocked_skills(stats)
    all_skills = {s["id"]: s for s in (unlocked_w + unlocked_m)}

    if not all_skills:
        await yuna_gambling_mod._safe_send_reply(message, f"**{author_name}**, you haven't unlocked any Weird or Marital Skills yet! Train in `y!arena` to reach Battle Lv. 2+!")
        return

    target_id = args[0].lower().strip() if args else list(all_skills.keys())[-1]
    sk = all_skills.get(target_id)
    if not sk:
        for k, v in all_skills.items():
            if target_id in k or target_id in v["name"].lower():
                sk = v
                break

    if not sk:
        await yuna_gambling_mod._safe_send_reply(message, f"You do not know the skill `{target_id}`! Select one from the dropdown or check `y!skills`!")
        return

    cost_reduc = rpg.get("berry_cost_reduction", 0.0)
    eff_cost = int(sk["berry_cost"] * (1.0 - cost_reduc))

    berries = stats.get("berries", 0)
    if berries < eff_cost:
        await yuna_gambling_mod._safe_send_reply(
            message,
            f"❌ **NOT ENOUGH BERRIES!** Casting {sk['emoji']} **{sk['name']}** requires **{eff_cost:,} 🫐**, but you have **{berries:,} 🫐**!"
        )
        return

    stats["berries"] = berries - eff_cost
    run["berries_burned"] = run.get("berries_burned", 0) + eff_cost

    m_boost = rpg.get("marital_boost", 1.0) if sk in unlocked_m else 1.0
    coop_mult = 1.15 if len(party) > 1 else 1.0
    dmg_mult = sk.get("dmg_mult", 1.0) * m_boost * coop_mult

    log = f"✨ **{author_name}** cast {sk['emoji']} **{sk['name']}**! ({eff_cost:,} 🫐)"

    if dmg_mult > 0:
        raw = (rpg["atk"] * dmg_mult * random.uniform(0.95, 1.05))
        if not sk.get("true_damage"):
            raw -= (stage_info["def"] * (0.2 if sk.get("armor_pierce") else 0.4))
        skill_dmg = max(25, int(raw))
        run["enemy_hp"] = max(0, run["enemy_hp"] - skill_dmg)
        combo_str = " *(+15% Co-op Combo!)*" if len(party) > 1 else ""
        log += f"\n💥 Blasted {stage_info['name']} for **{skill_dmg:,} damage**!{combo_str}"

    if sk.get("heal_pct"):
        heal = int(fighter["max_hp"] * sk["heal_pct"] * m_boost)
        fighter["hp"] = min(fighter["max_hp"], fighter["hp"] + heal)
        log += f"\n💚 **{author_name}** restored **+{heal:,} HP**!"
        if len(party) > 1:
            ally_heal = max(1, int(heal * 0.5))
            for pid, f in party.items():
                if pid != author_id and f.get("alive", True):
                    f["hp"] = min(f["max_hp"], f["hp"] + ally_heal)
            log += f" *(Allies restored +{ally_heal:,} HP from aura!)*"

    if sk.get("buff_next_atk"):
        fighter["next_atk_boost"] = sk["buff_next_atk"]
        log += f"\n⚡ Next strike charged by **+{int((sk['buff_next_atk']-1)*100)}%**!"

    # Check Enemy Defeated
    if run["enemy_hp"] <= 0:
        await process_stage_victory(message, host_id, run, rpg, stage_info, stats, yuna_gambling_mod, interaction=interaction, actor=target_user)
        return

    # Check Stun / Turn Skip
    if sk.get("stun_chance") and random.random() < sk["stun_chance"]:
        log += f"\n💫 {stage_info['name']} is completely stunned and misses their turn!"
    else:
        alive_fighters = [f for f in party.values() if f.get("alive", True)]
        if random.random() < 0.60 or len(alive_fighters) == 1:
            target_fighter = fighter
        else:
            target_fighter = random.choice(alive_fighters)

        target_stats = await yuna_gambling_mod._get_user_stats(target_fighter["id"])
        target_rpg = get_player_rpg_stats(target_stats)
        e_atk = stage_info["atk"]
        enemy_dmg = max(10, int((e_atk * random.uniform(0.9, 1.1)) - (target_rpg["def"] * 0.5)))
        target_fighter["hp"] = max(0, target_fighter["hp"] - enemy_dmg)
        log += f"\n🩸 {stage_info['name']} retaliated against **{target_fighter['name']}** for **{enemy_dmg:,} damage**!"

        if target_fighter["hp"] <= 0:
            if not target_fighter.get("revive_used") and target_stats.get("spouse"):
                target_fighter["revive_used"] = True
                target_fighter["hp"] = int(target_fighter["max_hp"] * 0.50)
                log += f"\n💖 **TILL DEATH DO US PART!** {target_fighter['name']}'s spouse intercepted the killing blow and revived them to 50% HP!"
            else:
                target_fighter["alive"] = False
                log += f"\n💀 **{target_fighter['name']} was slain in combat!**"

    if all(not f.get("alive", True) for f in party.values()):
        del ACTIVE_DUNGEON_RUNS[host_id]
        yuna_gambling_mod._save_data_sync()
        await yuna_gambling_mod._safe_send_reply(message, f"💀 All members of the raid party were slain in GoD-HeLL on Stage {stage_info['stage']}!")
        return

    yuna_gambling_mod._save_data_sync()
    await render_dungeon_screen(message, host_id, run, rpg, yuna_gambling_mod, battle_log=log, interaction=interaction, actor=target_user)

async def handle_dheal(message, client, args: list, yuna_gambling_mod, actor: Optional[discord.User] = None, interaction: Optional[discord.Interaction] = None):
    """Drinks a Dungeon Elixir of Immortality in GoD-HeLL."""
    target_user = actor or message.author
    author_id = str(target_user.id)
    author_name = getattr(target_user, "display_name", target_user.name)

    host_id, run = get_user_dungeon_run(author_id)
    if not run:
        await yuna_gambling_mod._safe_send_reply(message, "You are not currently in GoD-HeLL!")
        return

    party = run.setdefault("party", {})
    if author_id not in party:
        party[author_id] = {
            "id": author_id,
            "name": author_name,
            "hp": run.get("player_hp", 1000),
            "max_hp": run.get("player_hp", 1000),
            "alive": True,
            "is_host": True
        }

    fighter = party[author_id]
    stats = await yuna_gambling_mod._get_user_stats(author_id)
    inv = stats.get("inventory", {})
    if inv.get("dungeon_elixir", 0) <= 0:
        await yuna_gambling_mod._safe_send_reply(message, f"**{author_name}**, you don't have any **Dungeon Elixirs**! Buy them from `y!battleshop`!")
        return

    inv["dungeon_elixir"] -= 1
    rpg = get_player_rpg_stats(stats)
    heal = int(fighter["max_hp"] * 0.50)
    fighter["hp"] = min(fighter["max_hp"], fighter["hp"] + heal)
    fighter["alive"] = True

    yuna_gambling_mod._save_data_sync()
    log = f"🧪 **{author_name}** drank a **Dungeon Elixir of Immortality** and restored **+{heal:,} HP**!"
    await render_dungeon_screen(message, host_id, run, rpg, yuna_gambling_mod, battle_log=log, interaction=interaction, actor=target_user)

async def handle_dflee(message, client, args: list, yuna_gambling_mod, actor: Optional[discord.User] = None):
    """Safely retreats from the GoD-HeLL dungeon."""
    target_user = actor or message.author
    author_id = str(target_user.id)
    author_name = getattr(target_user, "display_name", target_user.name)

    host_id, run = get_user_dungeon_run(author_id)
    if not run:
        await yuna_gambling_mod._safe_send_reply(message, "You are not currently in GoD-HeLL!")
        return

    party = run.setdefault("party", {})
    stage = DUNGEON_STAGES[run["stage_idx"]]["stage"]

    # If author is an ally
    if len(party) > 1 and author_id in party and not party[author_id].get("is_host"):
        del party[author_id]
        await yuna_gambling_mod._safe_send_reply(
            message,
            f"🏃 **TACTICAL RETREAT!**\n**{author_name}** abandoned the raid party and fled from Stage {stage}!"
        )
        return

    # If host flees
    if len(party) > 1 and author_id in party and party[author_id].get("is_host"):
        del party[author_id]
        new_host_id = list(party.keys())[0]
        party[new_host_id]["is_host"] = True
        del ACTIVE_DUNGEON_RUNS[host_id]
        ACTIVE_DUNGEON_RUNS[new_host_id] = run
        run["host_id"] = new_host_id
        await yuna_gambling_mod._safe_send_reply(
            message,
            f"🏃 **HOST RETREATED!** **{author_name}** fled from Stage {stage}! Leadership transferred to <@{new_host_id}>!"
        )
        return

    del ACTIVE_DUNGEON_RUNS[host_id]
    await yuna_gambling_mod._safe_send_reply(
        message,
        f"🏃 **TACTICAL RETREAT!**\nYou fled from GoD-HeLL Stage {stage}! Total berries burned: `{run.get('berries_burned', 0):,} 🫐`."
    )

async def process_stage_victory(message, host_id: str, run: dict, rpg: dict, stage_info: dict, stats: dict, yuna_gambling_mod, interaction: Optional[discord.Interaction] = None, actor: Optional[discord.User] = None):
    """Handles stage progression, EXP, titles, and fallen ally revives. Resends next stage as a brand new chat message."""
    stage_num = stage_info["stage"]
    exp_gain = stage_info["reward_exp"]
    title_award = stage_info.get("reward_title")

    party = run.get("party", {})
    for pid, fighter in party.items():
        p_stats = await yuna_gambling_mod._get_user_stats(pid)
        p_stats["battle_exp"] = p_stats.get("battle_exp", 0) + exp_gain
        if stage_num > p_stats.get("godhell_highest_stage", 0):
            p_stats["godhell_highest_stage"] = stage_num
            if title_award:
                p_stats["title"] = title_award
        if not fighter.get("alive"):
            fighter["alive"] = True
            fighter["hp"] = int(fighter["max_hp"] * 0.50)

    # Check if final Titan Boss defeated
    if run["stage_idx"] >= len(DUNGEON_STAGES) - 1:
        del ACTIVE_DUNGEON_RUNS[host_id]
        for pid in party:
            p_stats = await yuna_gambling_mod._get_user_stats(pid)
            p_stats["dungeon_runs_completed"] = p_stats.get("dungeon_runs_completed", 0) + 1
            p_stats["title"] = "Conqueror of GoD-HeLL"
        yuna_gambling_mod._save_data_sync()

        # Clean up and disable buttons on previous stage message
        cleared_embed = discord.Embed(
            title=f"👑 TITAN BOSS SLAIN • Stage {stage_num}: {stage_info['emoji']} {stage_info['name']}",
            description=(
                f"💀 **{stage_info['name']}** has been vanquished!\n"
                f"✨ **Final Stage Reward:** `+{exp_gain:,} EXP` for all party members!\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🏆 *The GoD-HeLL Raid has been conquered! Victory proclamation below...*"
            ),
            color=0xf1c40f
        )
        old_msg = run.get("message") or (interaction.message if interaction else None)
        if interaction and getattr(interaction, "message", None):
            try:
                await interaction.edit_original_response(embed=cleared_embed, view=None)
            except Exception:
                try:
                    await interaction.message.edit(embed=cleared_embed, view=None)
                except Exception:
                    pass
        elif old_msg:
            try:
                await old_msg.edit(embed=cleared_embed, view=None)
            except Exception:
                pass

        party_names = ", ".join(f"**{f['name']}**" for f in party.values())
        await yuna_gambling_mod._safe_send_reply(
            message,
            f"🏆👑 **CONGRATULATIONS! THE RAID PARTY HAS CONQUERED GoD-HeLL!** 👑🏆\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Fighters: {party_names}\n"
            f"You vanquished **Lucifer of the Berry Void** and conquered all 10 stages!\n"
            f"🎖️ **Earned Title:** `Conqueror of GoD-HeLL`\n"
            f"✨ **EXP Gained:** `+{exp_gain:,} EXP` for all party members!\n"
            f"🔥 **Total Berries Burned:** `{run.get('berries_burned', 0):,} 🫐`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"*- Empress Yuna crowns your entire raid party with eternal gladiator glory!*"
        )
        return

    # 1. Clean up and disable buttons on the previous stage/wave/boss message, marking it cleared
    stage_type = "BOSS" if stage_info.get("is_boss") else "WAVE"
    cleared_embed = discord.Embed(
        title=f"✅ {stage_type} CLEARED • Stage {stage_num}: {stage_info['emoji']} {stage_info['name']}",
        description=(
            f"💀 **{stage_info['name']}** was vanquished!\n"
            f"✨ **Party Reward:** `+{exp_gain:,} EXP` earned by all raid members!\n"
            f"❤️ All fallen raid members revived to 50% HP!\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⬇️ *Entering the next encounter below...*"
        ),
        color=0x2ecc71
    )
    old_msg = run.get("message") or (interaction.message if interaction else None)
    if interaction and getattr(interaction, "message", None):
        try:
            await interaction.edit_original_response(embed=cleared_embed, view=None)
        except Exception:
            try:
                await interaction.message.edit(embed=cleared_embed, view=None)
            except Exception:
                pass
    elif old_msg:
        try:
            await old_msg.edit(embed=cleared_embed, view=None)
        except Exception:
            pass

    # 2. Advance to next stage!
    run["stage_idx"] += 1
    next_stage = DUNGEON_STAGES[run["stage_idx"]]
    run["enemy_hp"] = next_stage["max_hp"]

    yuna_gambling_mod._save_data_sync()
    next_is_boss = next_stage.get("is_boss", False)
    next_type = "👑 BOSS ENCOUNTER" if next_is_boss else "👾 ENEMY WAVE"
    victory_log = (
        f"🎉 **STAGE {stage_num} CLEARED!** Defeated {stage_info['emoji']} {stage_info['name']}!\n"
        f"All party members gained `+{exp_gain:,} EXP`! (Fallen allies revived to 50% HP)\n"
        f"⚔️ **ENTERING {next_type}: Stage {next_stage['stage']} — {next_stage['emoji']} {next_stage['name']}!**"
    )

    # 3. Resend the next stage encounter as a brand new message at the bottom of the chat channel
    await render_dungeon_screen(
        message,
        host_id,
        run,
        rpg,
        yuna_gambling_mod,
        battle_log=victory_log,
        interaction=None,
        actor=actor,
        resend_as_new=True
    )

class DungeonCombatView(View):
    def __init__(self, host_id: str, yuna_gambling_mod, user_skills: list = None, cost_reduc: float = 0.0):
        super().__init__(timeout=600)
        self.host_id = host_id
        self.yuna_gambling_mod = yuna_gambling_mod
        if user_skills is None:
            user_skills = []
        self.skill_select = DungeonSkillSelect(user_skills, cost_reduc=cost_reduc)
        self.add_item(self.skill_select)

    async def on_timeout(self):
        if self.host_id in ACTIVE_DUNGEON_RUNS:
            ACTIVE_DUNGEON_RUNS.pop(self.host_id, None)
        for child in self.children:
            child.disabled = True

    @discord.ui.button(label="Attack", emoji="⚔️", style=discord.ButtonStyle.danger, row=1)
    async def atk_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        host_id, run = get_user_dungeon_run(str(interaction.user.id))
        if not run or host_id != self.host_id:
            await interaction.response.send_message("This is not your GoD-HeLL raid! Join with `y!djoin` or ask the host for an invite!", ephemeral=True)
            return
        await interaction.response.defer()
        await handle_dattack(interaction.message, interaction.client, [], self.yuna_gambling_mod, actor=interaction.user, interaction=interaction)

    @discord.ui.button(label="Heal (Potion)", emoji="🧪", style=discord.ButtonStyle.success, row=1)
    async def heal_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        host_id, run = get_user_dungeon_run(str(interaction.user.id))
        if not run or host_id != self.host_id:
            await interaction.response.send_message("This is not your GoD-HeLL raid!", ephemeral=True)
            return
        await interaction.response.defer()
        await handle_dheal(interaction.message, interaction.client, [], self.yuna_gambling_mod, actor=interaction.user, interaction=interaction)

    @discord.ui.button(label="Call Aid", emoji="🤝", style=discord.ButtonStyle.primary, row=1)
    async def call_aid_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        host_id, run = get_user_dungeon_run(str(interaction.user.id))
        if not run or host_id != self.host_id:
            await interaction.response.send_message("This is not your GoD-HeLL raid!", ephemeral=True)
            return
        await interaction.response.defer()
        await handle_dcallaid(interaction.message, interaction.client, [], self.yuna_gambling_mod, actor=interaction.user)

    @discord.ui.button(label="Flee", emoji="🏃", style=discord.ButtonStyle.secondary, row=1)
    async def flee_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        host_id, run = get_user_dungeon_run(str(interaction.user.id))
        if not run or host_id != self.host_id:
            await interaction.response.send_message("This is not your GoD-HeLL raid!", ephemeral=True)
            return
        await interaction.response.defer()
        await handle_dflee(interaction.message, interaction.client, [], self.yuna_gambling_mod, actor=interaction.user)

# ─────────────────────────────────────────────────────────────────────────────
# 7. 🛡️ BATTLE SHOP & EQUIPMENT COMMANDS
# ─────────────────────────────────────────────────────────────────────────────

async def handle_battleshop(message, client, args: list, yuna_gambling_mod, actor: Optional[discord.User] = None):
    """Displays the high-tier Battle Shop containing Weapons, Armor, and Consumables."""
    embed = discord.Embed(
        title="🛡️ Yuna's Elite Battle Armory & High-Roller Shop",
        description=(
            "Equip yourself with mythic gear to conquer **GoD-HeLL** and dominate the Arena!\n"
            "Purchase with `y!bbuy <item>` and equip with `y!equip <item>`!\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=SHOP_COLOR
    )

    weapons = [f"{v['emoji']} **{v['name']}** — `{v['price']:,} 🫐`\n• Key: `{k}` | {v['desc']}" for k, v in BATTLE_SHOP_ITEMS.items() if v.get("slot") == "weapon"]
    armor = [f"{v['emoji']} **{v['name']}** — `{v['price']:,} 🫐`\n• Key: `{k}` | {v['desc']}" for k, v in BATTLE_SHOP_ITEMS.items() if v.get("slot") == "armor"]
    accessories = [f"{v['emoji']} **{v['name']}** — `{v['price']:,} 🫐`\n• Key: `{k}` | {v['desc']}" for k, v in BATTLE_SHOP_ITEMS.items() if v.get("slot") == "accessory"]
    consumables = [f"{v['emoji']} **{v['name']}** — `{v['price']:,} 🫐`\n• Key: `{k}` | {v['desc']}" for k, v in BATTLE_SHOP_ITEMS.items() if v.get("slot") == "consumable"]

    embed.add_field(name="⚔️ Weapons", value="\n\n".join(weapons), inline=False)
    embed.add_field(name="🛡️ Armor", value="\n\n".join(armor), inline=False)
    embed.add_field(name="💍 Accessories", value="\n\n".join(accessories), inline=False)
    embed.add_field(name="🧪 Dungeon Consumables", value="\n\n".join(consumables), inline=False)

    embed.set_footer(text="Battle Shop • Example: y!bbuy katana or y!bbuy dungeon_elixir")
    await yuna_gambling_mod._safe_send_reply(message, embed=embed)

async def handle_bbuy(message, client, args: list, yuna_gambling_mod, actor: Optional[discord.User] = None):
    """Handles y!bbuy <item>."""
    target_user = actor or message.author
    author_id = str(target_user.id)
    if not args:
        await yuna_gambling_mod._safe_send_reply(message, "What are you buying? Type `y!battleshop` to view items, then `y!bbuy <item>`!")
        return

    item_token = args[0].lower().strip()
    matched_key = None
    for k in BATTLE_SHOP_ITEMS:
        if item_token == k or item_token == BATTLE_SHOP_ITEMS[k]["name"].lower():
            matched_key = k
            break

    if not matched_key:
        await yuna_gambling_mod._safe_send_reply(message, f"Item `{item_token}` not found in the Battle Shop! Check `y!battleshop`!")
        return

    item = BATTLE_SHOP_ITEMS[matched_key]
    price = item["price"]

    stats = await yuna_gambling_mod._get_user_stats(author_id)
    ensure_player_rpg(stats)
    berries = stats.get("berries", 0)

    if berries < price:
        await yuna_gambling_mod._safe_send_reply(
            message,
            f"- *Yuna slides the weapon back* \"You need **{price:,} 🫐** for {item['emoji']} **{item['name']}**, but you only have **{berries:,} 🫐**!\""
        )
        return

    inv = stats.setdefault("inventory", {})
    # For gear: weapons/armor/accessories max hold 1
    if item["slot"] in ("weapon", "armor", "accessory"):
        if inv.get(matched_key, 0) >= 1:
            await yuna_gambling_mod._safe_send_reply(message, f"You already own {item['emoji']} **{item['name']}**! Equip it with `y!equip {matched_key}`!")
            return

    stats["berries"] = berries - price
    inv[matched_key] = inv.get(matched_key, 0) + 1

    # Auto-equip if slot is empty
    eq = stats.setdefault("equipped", {})
    slot = item.get("slot")
    auto_eq_str = ""
    if slot in ("weapon", "armor", "accessory") and not eq.get(slot):
        eq[slot] = matched_key
        auto_eq_str = f" Automatically equipped into your **{slot.title()}** slot!"

    yuna_gambling_mod._save_data_sync()
    await yuna_gambling_mod._safe_send_reply(
        message,
        f"🛍️ **BATTLE SHOP PURCHASE SUCCESSFUL!**\n"
        f"Bought: {item['emoji']} **{item['name']}** for `{price:,} 🫐`!{auto_eq_str}\n"
        f"View your equipped gear on `y!bal`!"
    )

async def handle_equip(message, client, args: list, yuna_gambling_mod, actor: Optional[discord.User] = None):
    """Handles y!equip <item>."""
    target_user = actor or message.author
    author_id = str(target_user.id)
    author_name = getattr(target_user, "display_name", target_user.name)
    stats = await yuna_gambling_mod._get_user_stats(author_id)
    ensure_player_rpg(stats)

    if not args:
        # If no arguments, display current equipment page
        embed = build_equipment_embed(stats, message.author, message.guild)
        view = BalanceView(author_id, target_user=message.author, yuna_gambling_mod=yuna_gambling_mod, current_page="equip")
        await yuna_gambling_mod._safe_send_reply(message, embed=embed, view=view)
        return

    item_token = args[0].lower().strip()
    inv = stats.get("inventory", {})

    matched_key = None
    for k in BATTLE_SHOP_ITEMS:
        if (item_token == k or item_token in BATTLE_SHOP_ITEMS[k]["name"].lower()) and inv.get(k, 0) > 0:
            matched_key = k
            break

    if not matched_key:
        await yuna_gambling_mod._safe_send_reply(message, f"You don't own any equipment matching `{item_token}`! Check `y!inv` or `y!battleshop`!")
        return

    item = BATTLE_SHOP_ITEMS[matched_key]
    slot = item.get("slot")
    if slot not in ("weapon", "armor", "accessory"):
        await yuna_gambling_mod._safe_send_reply(message, f"{item['emoji']} **{item['name']}** is a consumable item, not equippable gear!")
        return

    eq = stats.setdefault("equipped", {})
    eq[slot] = matched_key

    yuna_gambling_mod._save_data_sync()
    await yuna_gambling_mod._safe_send_reply(
        message,
        f"🛡️ **EQUIPPED {slot.upper()}!**\n"
        f"You have equipped {item['emoji']} **{item['name']}** into your {slot} slot!\n"
        f"Check your updated attributes with `y!bal`!"
    )

# ─────────────────────────────────────────────────────────────────────────────
# 8. 📜 EQUIPMENT PAGE IN Y!BAL
# ─────────────────────────────────────────────────────────────────────────────

def build_equipment_embed(stats: dict, target_user: discord.User, guild: Optional[discord.Guild]) -> discord.Embed:
    """Builds the comprehensive RPG Equipment Page embed for y!bal."""
    ensure_player_rpg(stats)
    rpg = get_player_rpg_stats(stats)
    display_name = getattr(target_user, "display_name", target_user.name)

    eq = stats.get("equipped", {})
    w_name = f"{BATTLE_SHOP_ITEMS[eq['weapon']]['emoji']} **{BATTLE_SHOP_ITEMS[eq['weapon']]['name']}**" if eq.get('weapon') in BATTLE_SHOP_ITEMS else "*None Equipped*"
    a_name = f"{BATTLE_SHOP_ITEMS[eq['armor']]['emoji']} **{BATTLE_SHOP_ITEMS[eq['armor']]['name']}**" if eq.get('armor') in BATTLE_SHOP_ITEMS else "*None Equipped*"
    acc_name = f"{BATTLE_SHOP_ITEMS[eq['accessory']]['emoji']} **{BATTLE_SHOP_ITEMS[eq['accessory']]['name']}**" if eq.get('accessory') in BATTLE_SHOP_ITEMS else "*None Equipped*"

    unlocked_w, unlocked_m = get_unlocked_skills(stats)
    w_skills_str = ", ".join(f"{s['emoji']} `{s['name']}`" for s in unlocked_w) if unlocked_w else "*None (Unlocks at Battle Lv. 2)*"
    m_skills_str = ", ".join(f"{s['emoji']} `{s['name']}`" for s in unlocked_m) if unlocked_m else ("*Requires Marriage (y!marry)*" if not stats.get("spouse") else "*All active!*")

    # Auction Trophies & Buffs
    trophies = stats.get("auction_trophies", [])
    t_lines = []
    for tid in trophies:
        if tid in AUCTION_CATALOG:
            t = AUCTION_CATALOG[tid]
            t_lines.append(f"{t['emoji']} **{t['name']}** *({t['buff_desc']})*")
    trophy_str = "\n".join(t_lines) if t_lines else "*No auction collectibles owned yet (Check y!auction)*"

    dungeon_highest = stats.get("godhell_highest_stage", 0)
    dungeon_str = f"Stage `{dungeon_highest}/10`" if dungeon_highest > 0 else "*Not entered yet (y!godhell)*"

    custom_title = stats.get("title", f"Gladiator of Yuna")

    embed = discord.Embed(
        title=f"🛡️ {display_name}'s Combat Equipment & RPG Stats",
        description=(
            f"🎖️ **Title:** *{custom_title}*\n"
            f"⚔️ **Battle Level:** `Lv. {rpg['level']}` | **EXP:** `{rpg['exp']:,}`\n"
            f"🌋 **GoD-HeLL Record:** {dungeon_str}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"❤️ **Max HP:** `{rpg['max_hp']:,}`\n"
            f"⚔️ **Attack (ATK):** `{rpg['atk']:,}`\n"
            f"🛡️ **Defense (DEF):** `{rpg['def']:,}`\n"
            f"⚡ **Speed (SPD):** `{rpg['spd']:,}` *(Crit: {rpg['crit_rate']*100:.1f}%)*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🗡️ **Weapon:** {w_name}\n"
            f"🦺 **Armor:** {a_name}\n"
            f"💍 **Accessory:** {acc_name}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎭 **Weird Skills:** {w_skills_str}\n"
            f"💖 **Marital Skills:** {m_skills_str}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏆 **Auction Relics & Buffs:**\n{trophy_str}"
        ),
        color=RPG_COLOR
    )
    avatar = getattr(target_user, "display_avatar", None)
    if avatar and hasattr(avatar, "url"):
        embed.set_thumbnail(url=avatar.url)
    embed.set_footer(text="Use y!battleshop to buy gear, y!arena to train, and y!godhell to raid!")
    return embed

class BalanceView(View):
    """Two-page View toggling between Soul & Pouch and Equipment & RPG stats."""
    def __init__(self, author_id: str, target_user: discord.User, yuna_gambling_mod, current_page: str = "pouch"):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.target_user = target_user
        self.yuna_gambling_mod = yuna_gambling_mod
        self.current_page = current_page
        self._update_buttons()

    def _update_buttons(self):
        self.pouch_btn.disabled = (self.current_page == "pouch")
        self.equip_btn.disabled = (self.current_page == "equip")

    @discord.ui.button(label="Soul & Pouch", emoji="🫐", style=discord.ButtonStyle.primary)
    async def pouch_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.current_page = "pouch"
        self._update_buttons()

        stats = await self.yuna_gambling_mod._get_user_stats(str(self.target_user.id))
        pouch_text = self.yuna_gambling_mod.format_balance_card_text(self.target_user, stats)
        await interaction.message.edit(content=pouch_text, embed=None, view=self)

    @discord.ui.button(label="Equipment & RPG", emoji="🛡️", style=discord.ButtonStyle.secondary)
    async def equip_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.current_page = "equip"
        self._update_buttons()

        stats = await self.yuna_gambling_mod._get_user_stats(str(self.target_user.id))
        embed = build_equipment_embed(stats, self.target_user, interaction.guild)
        await interaction.message.edit(content=None, embed=embed, view=self)
