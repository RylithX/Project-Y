"""
showdown_tactics.py: Competitive Pokémon Battle Intelligence Engine.
Features:
- Complete 18x18 type effectiveness matrix (super effective, resisted, immune)
- Comprehensive move database with BP, category, priority, and tactical effects
- Species typing and ability immunity awareness (Wonder Guard, Levitate, Flash Fire, Volt Absorb, Water Absorb, etc.)
- Dynamic battle state parsing (HP %, boosts, immunities discovered during combat)
- Tactical move ranking (STAB, effectiveness, execute bonuses, setup thresholds, recovery triggers)
- Tactical switching when active Pokémon is walled or countered
- Anti-repetition blacklist when a move fails or is immune
"""

import os
import json
import urllib.request
import re
from typing import Dict, List, Any, Optional, Tuple, Set

# Base directory for cached showdown data
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memories", "showdown")
POKEDEX_PATH = os.path.join(DATA_DIR, "pokedex.json")
MOVES_PATH = os.path.join(DATA_DIR, "moves.json")

POKEDEX_DATA: Dict[str, Dict[str, Any]] = {}
MOVES_DATA: Dict[str, Dict[str, Any]] = {}

def load_data():
    global POKEDEX_DATA, MOVES_DATA
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        for fpath, url in [
            (POKEDEX_PATH, "https://play.pokemonshowdown.com/data/pokedex.json"),
            (MOVES_PATH, "https://play.pokemonshowdown.com/data/moves.json")
        ]:
            if not os.path.exists(fpath):
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        with open(fpath, "wb") as f:
                            f.write(resp.read())
                except Exception:
                    pass

        if os.path.exists(POKEDEX_PATH):
            with open(POKEDEX_PATH, "r", encoding="utf-8") as f:
                POKEDEX_DATA = json.load(f)
        if os.path.exists(MOVES_PATH):
            with open(MOVES_PATH, "r", encoding="utf-8") as f:
                MOVES_DATA = json.load(f)
    except Exception as e:
        print(f"[showdown_tactics] Warning: could not load json data: {e}")

load_data()

# ─── COMPLETE 18-TYPE MATCHUP CHART ─────────────────────────────
TYPE_CHART: Dict[str, Dict[str, float]] = {
    "Normal": {"Rock": 0.5, "Ghost": 0.0, "Steel": 0.5},
    "Fire": {
        "Fire": 0.5, "Water": 0.5, "Grass": 2.0, "Ice": 2.0,
        "Bug": 2.0, "Rock": 0.5, "Dragon": 0.5, "Steel": 2.0
    },
    "Water": {
        "Fire": 2.0, "Water": 0.5, "Grass": 0.5, "Ground": 2.0,
        "Rock": 2.0, "Dragon": 0.5
    },
    "Grass": {
        "Fire": 0.5, "Water": 2.0, "Grass": 0.5, "Poison": 0.5,
        "Ground": 2.0, "Flying": 0.5, "Bug": 0.5, "Rock": 2.0,
        "Dragon": 0.5, "Steel": 0.5
    },
    "Electric": {
        "Water": 2.0, "Electric": 0.5, "Grass": 0.5, "Ground": 0.0,
        "Flying": 2.0, "Dragon": 0.5
    },
    "Ice": {
        "Fire": 0.5, "Water": 0.5, "Grass": 2.0, "Ice": 0.5,
        "Ground": 2.0, "Flying": 2.0, "Dragon": 2.0, "Steel": 0.5
    },
    "Fighting": {
        "Normal": 2.0, "Ice": 2.0, "Poison": 0.5, "Flying": 0.5,
        "Psychic": 0.5, "Bug": 0.5, "Rock": 2.0, "Ghost": 0.0,
        "Dark": 2.0, "Steel": 2.0, "Fairy": 0.5
    },
    "Poison": {
        "Grass": 2.0, "Poison": 0.5, "Ground": 0.5, "Rock": 0.5,
        "Ghost": 0.5, "Steel": 0.0, "Fairy": 2.0
    },
    "Ground": {
        "Fire": 2.0, "Electric": 2.0, "Grass": 0.5, "Poison": 2.0,
        "Flying": 0.0, "Bug": 0.5, "Rock": 2.0, "Steel": 2.0
    },
    "Flying": {
        "Electric": 0.5, "Grass": 2.0, "Fighting": 2.0, "Bug": 2.0,
        "Rock": 0.5, "Steel": 0.5
    },
    "Psychic": {
        "Fighting": 2.0, "Poison": 2.0, "Psychic": 0.5, "Dark": 0.0,
        "Steel": 0.5
    },
    "Bug": {
        "Fire": 0.5, "Grass": 2.0, "Fighting": 0.5, "Poison": 0.5,
        "Flying": 0.5, "Psychic": 2.0, "Ghost": 0.5, "Dark": 2.0,
        "Steel": 0.5, "Fairy": 0.5
    },
    "Rock": {
        "Fire": 2.0, "Ice": 2.0, "Fighting": 0.5, "Ground": 0.5,
        "Flying": 2.0, "Bug": 2.0, "Steel": 0.5
    },
    "Ghost": {
        "Normal": 0.0, "Psychic": 2.0, "Ghost": 2.0, "Dark": 0.5
    },
    "Dragon": {
        "Dragon": 2.0, "Steel": 0.5, "Fairy": 0.0
    },
    "Steel": {
        "Fire": 0.5, "Water": 0.5, "Electric": 0.5, "Ice": 2.0,
        "Rock": 2.0, "Steel": 0.5, "Fairy": 2.0
    },
    "Dark": {
        "Fighting": 0.5, "Psychic": 2.0, "Ghost": 2.0, "Dark": 0.5,
        "Fairy": 0.5
    },
    "Fairy": {
        "Fire": 0.5, "Fighting": 2.0, "Poison": 0.5, "Dragon": 2.0,
        "Dark": 2.0, "Steel": 0.5
    }
}

# ─── SPECIES TYPING DATABASE (Standard & Competitive Archetypes) ─
SPECIES_TYPES: Dict[str, List[str]] = {
    "rayquaza": ["Dragon", "Flying"], "rayquazamega": ["Dragon", "Flying"],
    "groudon": ["Ground"], "groudonprimal": ["Ground", "Fire"],
    "kyogre": ["Water"], "kyogreprimal": ["Water"],
    "necrozma": ["Psychic"], "necrozmaultra": ["Psychic", "Dragon"], "necrozmaduskmane": ["Psychic", "Steel"], "necrozmadawnwings": ["Psychic", "Ghost"],
    "gengar": ["Ghost", "Poison"], "gengarmega": ["Ghost", "Poison"],
    "deoxys": ["Psychic"], "deoxysspeed": ["Psychic"], "deoxysattack": ["Psychic"], "deoxysdefense": ["Psychic"],
    "miraidon": ["Electric", "Dragon"], "koraidon": ["Fighting", "Dragon"],
    "calyrex": ["Psychic", "Grass"], "calyrexshadow": ["Psychic", "Ghost"], "calyrexice": ["Psychic", "Ice"],
    "arceus": ["Normal"], "zacian": ["Fairy"], "zaciancrowned": ["Fairy", "Steel"], "zamazenta": ["Fighting"], "zamazentacrowned": ["Fighting", "Steel"],
    "greattusk": ["Ground", "Fighting"], "kingambit": ["Dark", "Steel"], "gholdengo": ["Steel", "Ghost"],
    "ogerpon": ["Grass"], "ogerponwellspring": ["Grass", "Water"], "ogerponhearthflame": ["Grass", "Fire"], "ogerponcornerstone": ["Grass", "Rock"],
    "dragonite": ["Dragon", "Flying"], "ironvaliant": ["Fairy", "Fighting"], "ironhands": ["Fighting", "Electric"],
    "tinglu": ["Dark", "Ground"], "fluttermane": ["Ghost", "Fairy"], "chiyu": ["Dark", "Fire"], "chienpao": ["Dark", "Ice"], "wochien": ["Dark", "Grass"],
    "landorus": ["Ground", "Flying"], "landorustherian": ["Ground", "Flying"], "tornadus": ["Flying"], "thundurus": ["Electric", "Flying"],
    "greninja": ["Water", "Dark"], "greninjaash": ["Water", "Dark"], "heatran": ["Fire", "Steel"], "ferrothorn": ["Grass", "Steel"],
    "clefable": ["Fairy"], "weavile": ["Dark", "Ice"], "toxapex": ["Poison", "Water"], "magearna": ["Steel", "Fairy"], "kartana": ["Grass", "Steel"],
    "garchomp": ["Dragon", "Ground"], "dragapult": ["Dragon", "Ghost"], "volcarona": ["Bug", "Fire"], "corviknight": ["Flying", "Steel"],
    "gliscor": ["Ground", "Flying"], "skeledirge": ["Fire", "Ghost"], "meowscarada": ["Grass", "Dark"], "quaquaval": ["Water", "Fighting"],
    "roaringmoon": ["Dragon", "Dark"], "ironbundle": ["Ice", "Water"], "ironmoth": ["Fire", "Poison"], "irontreads": ["Ground", "Steel"],
    "dondozo": ["Water"], "tatsugiri": ["Dragon", "Water"], "annihilape": ["Fighting", "Ghost"], "ursaluna": ["Ground", "Normal"], "ursalunabloodmoon": ["Ground", "Normal"],
    "shedinja": ["Bug", "Ghost"], "blissey": ["Normal"], "chansey": ["Normal"], "scizor": ["Bug", "Steel"], "tyranitar": ["Rock", "Dark"], "salamence": ["Dragon", "Flying"],
    "zapdos": ["Electric", "Flying"], "moltres": ["Fire", "Flying"], "articuno": ["Ice", "Flying"], "mewtwo": ["Psychic"], "mew": ["Psychic"],
    "dialga": ["Steel", "Dragon"], "palkia": ["Water", "Dragon"], "giratina": ["Ghost", "Dragon"], "giratinaorigin": ["Ghost", "Dragon"],
    "xerneas": ["Fairy"], "yveltal": ["Dark", "Flying"], "zygarde": ["Dragon", "Ground"], "marshadow": ["Fighting", "Ghost"], "zeraora": ["Electric"],
    "eternatus": ["Poison", "Dragon"], "urshifu": ["Fighting", "Dark"], "urshifurapidstrike": ["Fighting", "Water"]
}

# ─── MOVE DATABASE & METRICS ────────────────────────────────────
MOVE_DATABASE: Dict[str, Dict[str, Any]] = {
    # Ground
    "earthquake": {"type": "Ground", "category": "physical", "bp": 100, "priority": 0},
    "headlongrush": {"type": "Ground", "category": "physical", "bp": 120, "priority": 0},
    "earthpower": {"type": "Ground", "category": "special", "bp": 90, "priority": 0},
    "precipiceblades": {"type": "Ground", "category": "physical", "bp": 120, "priority": 0},
    "thousandarrows": {"type": "Ground", "category": "physical", "bp": 90, "priority": 0, "hits_flying": True},
    "stompingtantrum": {"type": "Ground", "category": "physical", "bp": 75, "priority": 0},

    # Flying
    "dragonascent": {"type": "Flying", "category": "physical", "bp": 120, "priority": 0},
    "bravebird": {"type": "Flying", "category": "physical", "bp": 120, "priority": 0},
    "hurricane": {"type": "Flying", "category": "special", "bp": 110, "priority": 0},
    "bleakwindstorm": {"type": "Flying", "category": "special", "bp": 100, "priority": 0},
    "airslash": {"type": "Flying", "category": "special", "bp": 75, "priority": 0},

    # Fire
    "vcreate": {"type": "Fire", "category": "physical", "bp": 180, "priority": 0},
    "flareblitz": {"type": "Fire", "category": "physical", "bp": 120, "priority": 0},
    "fireblast": {"type": "Fire", "category": "special", "bp": 110, "priority": 0},
    "flamethrower": {"type": "Fire", "category": "special", "bp": 90, "priority": 0},
    "overheat": {"type": "Fire", "category": "special", "bp": 130, "priority": 0},
    "heatwave": {"type": "Fire", "category": "special", "bp": 95, "priority": 0},
    "magmastorm": {"type": "Fire", "category": "special", "bp": 100, "priority": 0},

    # Water
    "waterpulse": {"type": "Water", "category": "special", "bp": 60, "priority": 0},
    "hydropump": {"type": "Water", "category": "special", "bp": 110, "priority": 0},
    "surf": {"type": "Water", "category": "special", "bp": 90, "priority": 0},
    "scald": {"type": "Water", "category": "special", "bp": 80, "priority": 0},
    "originpulse": {"type": "Water", "category": "special", "bp": 110, "priority": 0},
    "waterspout": {"type": "Water", "category": "special", "bp": 150, "priority": 0},
    "ivycudgel": {"type": "Water", "category": "physical", "bp": 100, "priority": 0},
    "aquajet": {"type": "Water", "category": "physical", "bp": 40, "priority": 1},
    "watershuriken": {"type": "Water", "category": "special", "bp": 60, "priority": 1},

    # Electric
    "electrodrift": {"type": "Electric", "category": "special", "bp": 100, "priority": 0},
    "thunderbolt": {"type": "Electric", "category": "special", "bp": 90, "priority": 0},
    "thunder": {"type": "Electric", "category": "special", "bp": 110, "priority": 0},
    "voltswitch": {"type": "Electric", "category": "special", "bp": 70, "priority": 0},
    "wildcharge": {"type": "Electric", "category": "physical", "bp": 90, "priority": 0},

    # Dragon
    "dracometeor": {"type": "Dragon", "category": "special", "bp": 130, "priority": 0},
    "dragonpulse": {"type": "Dragon", "category": "special", "bp": 85, "priority": 0},
    "dragonclaw": {"type": "Dragon", "category": "physical", "bp": 80, "priority": 0},
    "outrage": {"type": "Dragon", "category": "physical", "bp": 120, "priority": 0},

    # Ghost
    "astralbarrage": {"type": "Ghost", "category": "special", "bp": 120, "priority": 0},
    "shadowball": {"type": "Ghost", "category": "special", "bp": 80, "priority": 0},
    "poltergeist": {"type": "Ghost", "category": "physical", "bp": 110, "priority": 0},
    "shadowclaw": {"type": "Ghost", "category": "physical", "bp": 70, "priority": 0},
    "destinybond": {"type": "Ghost", "category": "status", "bp": 0, "priority": 0},

    # Fighting
    "closecombat": {"type": "Fighting", "category": "physical", "bp": 120, "priority": 0},
    "collisioncourse": {"type": "Fighting", "category": "physical", "bp": 100, "priority": 0},
    "focusblast": {"type": "Fighting", "category": "special", "bp": 120, "priority": 0},
    "drainpunch": {"type": "Fighting", "category": "physical", "bp": 75, "priority": 0},
    "sacredsword": {"type": "Fighting", "category": "physical", "bp": 90, "priority": 0},
    "lowkick": {"type": "Fighting", "category": "physical", "bp": 80, "priority": 0},

    # Steel
    "makeitrain": {"type": "Steel", "category": "special", "bp": 120, "priority": 0},
    "behemothblade": {"type": "Steel", "category": "physical", "bp": 100, "priority": 0},
    "flashcannon": {"type": "Steel", "category": "special", "bp": 80, "priority": 0},
    "ironhead": {"type": "Steel", "category": "physical", "bp": 80, "priority": 0},

    # Dark
    "knockoff": {"type": "Dark", "category": "physical", "bp": 65, "priority": 0},
    "darkpulse": {"type": "Dark", "category": "special", "bp": 80, "priority": 0},
    "suckerpunch": {"type": "Dark", "category": "physical", "bp": 70, "priority": 1},
    "kowtowcleave": {"type": "Dark", "category": "physical", "bp": 85, "priority": 0},
    "foulplay": {"type": "Dark", "category": "physical", "bp": 95, "priority": 0},

    # Psychic
    "photongeyser": {"type": "Psychic", "category": "special", "bp": 100, "priority": 0},
    "psychic": {"type": "Psychic", "category": "special", "bp": 90, "priority": 0},
    "psyshock": {"type": "Psychic", "category": "special", "bp": 80, "priority": 0},

    # Fairy
    "moonblast": {"type": "Fairy", "category": "special", "bp": 95, "priority": 0},
    "dazzlinggleam": {"type": "Fairy", "category": "special", "bp": 80, "priority": 0},
    "playrough": {"type": "Fairy", "category": "physical", "bp": 90, "priority": 0},
    "fleurcannon": {"type": "Fairy", "category": "special", "bp": 130, "priority": 0},

    # Ice
    "icebeam": {"type": "Ice", "category": "special", "bp": 90, "priority": 0},
    "blizzard": {"type": "Ice", "category": "special", "bp": 110, "priority": 0},
    "icespinner": {"type": "Ice", "category": "physical", "bp": 80, "priority": 0},
    "iceshard": {"type": "Ice", "category": "physical", "bp": 40, "priority": 1},
    "tripleaxel": {"type": "Ice", "category": "physical", "bp": 120, "priority": 0},

    # Grass
    "hornleech": {"type": "Grass", "category": "physical", "bp": 75, "priority": 0},
    "energyball": {"type": "Grass", "category": "special", "bp": 90, "priority": 0},
    "leafblade": {"type": "Grass", "category": "physical", "bp": 90, "priority": 0},
    "powerwhip": {"type": "Grass", "category": "physical", "bp": 120, "priority": 0},

    # Normal
    "extremespeed": {"type": "Normal", "category": "physical", "bp": 80, "priority": 2},
    "rapidspin": {"type": "Normal", "category": "physical", "bp": 50, "priority": 0},

    # Status / Recovery / Setup / Meta Utility
    "swordsdance": {"type": "Normal", "category": "status", "bp": 0, "priority": 0, "effect": "setup"},
    "nastyplot": {"type": "Dark", "category": "status", "bp": 0, "priority": 0, "effect": "setup"},
    "calmmind": {"type": "Psychic", "category": "status", "bp": 0, "priority": 0, "effect": "setup"},
    "dragondance": {"type": "Dragon", "category": "status", "bp": 0, "priority": 0, "effect": "setup"},
    "quiverdance": {"type": "Bug", "category": "status", "bp": 0, "priority": 0, "effect": "setup"},
    "shiftgear": {"type": "Steel", "category": "status", "bp": 0, "priority": 0, "effect": "setup"},
    "shellsmash": {"type": "Normal", "category": "status", "bp": 0, "priority": 0, "effect": "setup"},
    "bellydrum": {"type": "Normal", "category": "status", "bp": 0, "priority": 0, "effect": "setup"},
    "recover": {"type": "Normal", "category": "status", "bp": 0, "priority": 0, "effect": "heal"},
    "roost": {"type": "Flying", "category": "status", "bp": 0, "priority": 0, "effect": "heal"},
    "softboiled": {"type": "Normal", "category": "status", "bp": 0, "priority": 0, "effect": "heal"},
    "morningsun": {"type": "Normal", "category": "status", "bp": 0, "priority": 0, "effect": "heal"},
    "strengthsap": {"type": "Grass", "category": "status", "bp": 0, "priority": 0, "effect": "heal", "accuracy": 100},
    "protect": {"type": "Normal", "category": "status", "bp": 0, "priority": 4, "effect": "protect"},
    "detect": {"type": "Fighting", "category": "status", "bp": 0, "priority": 4, "effect": "protect"},
    "substitute": {"type": "Normal", "category": "status", "bp": 0, "priority": 0, "effect": "substitute"},
    "stealthrock": {"type": "Rock", "category": "status", "bp": 0, "priority": 0, "effect": "hazard"},
    "spikes": {"type": "Ground", "category": "status", "bp": 0, "priority": 0, "effect": "hazard"},
    "toxicspikes": {"type": "Poison", "category": "status", "bp": 0, "priority": 0, "effect": "hazard"},
    "ceaselessedge": {"type": "Dark", "category": "physical", "bp": 65, "priority": 0, "effect": "hazard_spikes"},
    "stoneaxe": {"type": "Rock", "category": "physical", "bp": 65, "priority": 0, "effect": "hazard_rock"},
    "thunderwave": {"type": "Electric", "category": "status", "bp": 0, "priority": 0, "effect": "paralyze", "accuracy": 90},
    "glare": {"type": "Normal", "category": "status", "bp": 0, "priority": 0, "effect": "paralyze", "accuracy": 100},
    "nuzzle": {"type": "Electric", "category": "physical", "bp": 20, "priority": 0, "effect": "paralyze", "accuracy": 100},
    "spore": {"type": "Grass", "category": "status", "bp": 0, "priority": 0, "effect": "sleep", "accuracy": 100, "is_powder": True, "is_reflectable": True},
    "sing": {"type": "Normal", "category": "status", "bp": 0, "priority": 0, "effect": "sleep", "accuracy": 55, "is_sound": True, "is_reflectable": True},
    "hypnosis": {"type": "Psychic", "category": "status", "bp": 0, "priority": 0, "effect": "sleep", "accuracy": 60, "is_reflectable": True},
    "sleeppowder": {"type": "Grass", "category": "status", "bp": 0, "priority": 0, "effect": "sleep", "accuracy": 75, "is_powder": True, "is_reflectable": True},
    "darkvoid": {"type": "Dark", "category": "status", "bp": 0, "priority": 0, "effect": "sleep", "accuracy": 50, "is_reflectable": True},
    "yawn": {"type": "Normal", "category": "status", "bp": 0, "priority": 0, "effect": "sleep", "accuracy": 100, "is_reflectable": True},
    "willowisp": {"type": "Fire", "category": "status", "bp": 0, "priority": 0, "effect": "burn", "accuracy": 85, "is_reflectable": True},
    "toxic": {"type": "Poison", "category": "status", "bp": 0, "priority": 0, "effect": "toxic", "accuracy": 90, "is_reflectable": True},
    "taunt": {"type": "Dark", "category": "status", "bp": 0, "priority": 0, "effect": "taunt", "is_reflectable": True},
    "encore": {"type": "Normal", "category": "status", "bp": 0, "priority": 0, "effect": "encore", "is_reflectable": True},
    "whirlwind": {"type": "Normal", "category": "status", "bp": 0, "priority": -6, "effect": "phaze"},
    "roar": {"type": "Normal", "category": "status", "bp": 0, "priority": -6, "effect": "phaze", "is_sound": True},
    "ruination": {"type": "Dark", "category": "special", "bp": 80, "priority": 0},
    "mortalspin": {"type": "Poison", "category": "physical", "bp": 30, "priority": 0, "effect": "clear_hazards"},
    "defog": {"type": "Flying", "category": "status", "bp": 0, "priority": 0, "effect": "clear_hazards"},
    "courtchange": {"type": "Normal", "category": "status", "bp": 0, "priority": 0, "effect": "clear_hazards"},
    "tidyup": {"type": "Normal", "category": "status", "bp": 0, "priority": 0, "effect": "setup"},
    "sheercold": {"type": "Ice", "category": "special", "bp": 0, "priority": 0, "is_ohko": True, "accuracy": 30},
    "fissure": {"type": "Ground", "category": "physical", "bp": 0, "priority": 0, "is_ohko": True, "accuracy": 30},
    "horndrill": {"type": "Normal", "category": "physical", "bp": 0, "priority": 0, "is_ohko": True, "accuracy": 30},
    "guillotine": {"type": "Normal", "category": "physical", "bp": 0, "priority": 0, "is_ohko": True, "accuracy": 30},
    "moongeistbeam": {"type": "Ghost", "category": "special", "bp": 100, "priority": 0, "ignore_ability": True},
    "sunsteelstrike": {"type": "Steel", "category": "physical", "bp": 100, "priority": 0, "ignore_ability": True},
    "photongeyser": {"type": "Psychic", "category": "special", "bp": 100, "priority": 0, "ignore_ability": True},
    "spectraltheft": {"type": "Ghost", "category": "physical", "bp": 90, "priority": 0},
    "gigatonhammer": {"type": "Steel", "category": "physical", "bp": 160, "priority": 0},
    "populationbomb": {"type": "Normal", "category": "physical", "bp": 200, "priority": 0},
    "ragefist": {"type": "Ghost", "category": "physical", "bp": 100, "priority": 0},
    "saltcure": {"type": "Rock", "category": "physical", "bp": 40, "priority": 0},
    "transform": {"type": "Normal", "category": "status", "bp": 0, "priority": 0, "effect": "transform"}
}


def guess_move_info(move_id: str, move_name: str = "") -> Dict[str, Any]:
    """Compatibility wrapper for get_move_info."""
    return BattleTacticsEngine.get_move_info(move_id, move_name)


class BattleTacticsEngine:
    """Hyper-intelligent tactical brain that computes type matchups, immunities, and counterplays."""

    @staticmethod
    def get_pokemon_types(species_name: str, tera_type: Optional[str] = None) -> List[str]:
        """Returns the true type list for a Pokémon species from Pokédex, respecting Terastallization."""
        if tera_type and tera_type.strip():
            clean_tera = tera_type.strip().capitalize()
            if clean_tera in TYPE_CHART:
                return [clean_tera]

        if not species_name:
            return ["Normal"]

        clean_spec = re.sub(r"[^a-zA-Z0-9]", "", species_name.lower())

        # 1. Lookup in official Showdown pokedex.json (1,517 species)
        if clean_spec in POKEDEX_DATA:
            types = POKEDEX_DATA[clean_spec].get("types", [])
            if types:
                return types

        # Check prefix/fuzzy matching in pokedex (e.g. "misdreavusl50" -> "misdreavus")
        for k, v in POKEDEX_DATA.items():
            if clean_spec.startswith(k) or k in clean_spec:
                types = v.get("types", [])
                if types:
                    return types

        # 2. Check hardcoded competitive dictionary
        if clean_spec in SPECIES_TYPES:
            return SPECIES_TYPES[clean_spec]

        for k, v in SPECIES_TYPES.items():
            if k in clean_spec or clean_spec in k:
                return v

        return ["Normal"]

    @staticmethod
    def get_known_abilities(species_name: str) -> List[str]:
        """Returns the list of possible abilities for this species from Pokédex."""
        if not species_name:
            return []
        clean_spec = re.sub(r"[^a-zA-Z0-9]", "", species_name.lower())
        entry = POKEDEX_DATA.get(clean_spec)
        if not entry:
            for k, v in POKEDEX_DATA.items():
                if clean_spec.startswith(k) or k in clean_spec:
                    entry = v
                    break
        if entry:
            abilities_dict = entry.get("abilities", {})
            return list(abilities_dict.values())
        return []

    @staticmethod
    def get_move_info(move_id: str, move_name: str = "") -> Dict[str, Any]:
        """Looks up move data in Showdown moves.json (954 moves) or falls back to heuristics."""
        clean_id = re.sub(r"[^a-zA-Z0-9]", "", (move_id or "").lower())
        clean_name = re.sub(r"[^a-zA-Z0-9]", "", (move_name or "").lower())

        entry = MOVES_DATA.get(clean_id) or MOVES_DATA.get(clean_name)
        if entry:
            m_type = entry.get("type", "Normal")
            cat = (entry.get("category") or "physical").lower()
            bp = entry.get("basePower", 0)
            prio = entry.get("priority", 0)
            acc = entry.get("accuracy", 100)
            if acc is True:
                acc = 100
            elif not isinstance(acc, (int, float)):
                acc = 100
            flags = entry.get("flags", {})
            is_sound = bool(flags.get("sound"))
            is_reflectable = bool(flags.get("reflectable"))
            is_powder = bool(flags.get("powder"))
            bypass_sub = bool(flags.get("bypasssub"))
            ignore_ability = bool(entry.get("ignoreAbility"))
            is_ohko = bool(entry.get("ohko"))
            hits_flying = bool(entry.get("ignoreImmunity", {}).get("Ground")) or "thousandarrows" in clean_id
            m_status = entry.get("status") or ""
            m_boosts = entry.get("boosts") or {}

            # Determine tactical effect
            effect = ""
            if cat == "status" or bp == 0:
                if entry.get("heal") or any(k in clean_id for k in ("recover", "roost", "heal", "wish", "rest", "morningsun", "synthesis", "moonlight", "slackoff", "softboiled", "shoreup", "lifedew", "strengthsap")):
                    effect = "heal"
                elif any(k in clean_id for k in ("protect", "detect", "banefulbunker", "spikyshield", "silktrap", "kingsshield", "obstruct")):
                    effect = "protect"
                elif any(k in clean_id for k in ("stealthrock", "spikes", "toxicspikes", "stickyweb", "ceaselessedge", "stoneaxe")):
                    effect = "hazard"
                elif any(k in clean_id for k in ("swordsdance", "dragondance", "nastyplot", "calmmind", "bulkup", "quiverdance", "coil", "shellsmash", "curse", "irondefense", "shiftgear", "autotomize", "bellydrum", "tidyup")):
                    effect = "setup"
                elif m_status == "par" or any(k in clean_id for k in ("thunderwave", "glare", "stunspore", "nuzzle")):
                    effect = "paralyze"
                elif m_status == "slp" or any(k in clean_id for k in ("spore", "sleeppowder", "hypnosis", "yawn", "darkvoid", "sing", "grasswhistle")):
                    effect = "sleep"
                elif m_status == "brn" or any(k in clean_id for k in ("willowisp",)):
                    effect = "burn"
                elif m_status in ("tox", "psn") or any(k in clean_id for k in ("toxic", "poisongas", "poisonpowder")):
                    effect = "toxic"
                elif any(k in clean_id for k in ("taunt", "encore", "disable", "torment")):
                    effect = "taunt"
                elif any(k in clean_id for k in ("whirlwind", "roar")):
                    effect = "phaze"
                elif is_ohko:
                    effect = "ohko"

            # Handle variable power moves that have basePower: 0 in DB
            if bp == 0 and cat != "status" and not is_ohko:
                bp = 80  # Baseline benchmark for Low Kick, Seismic Toss, Night Shade, Foul Play, Heavy Slam, etc.

            return {
                "name": entry.get("name", move_name or move_id),
                "type": m_type,
                "category": cat,
                "bp": bp,
                "priority": prio,
                "accuracy": acc,
                "effect": effect,
                "is_sound": is_sound,
                "is_reflectable": is_reflectable,
                "is_powder": is_powder,
                "bypass_sub": bypass_sub,
                "ignore_ability": ignore_ability,
                "is_ohko": is_ohko,
                "hits_flying": hits_flying,
                "boosts": m_boosts
            }

        # Check hardcoded fallback database
        fb = MOVE_DATABASE.get(clean_id) or MOVE_DATABASE.get(clean_name)
        if fb:
            return {
                "name": move_name or move_id,
                "type": fb.get("type", "Normal"),
                "category": fb.get("category", "physical"),
                "bp": fb.get("bp", 0),
                "priority": fb.get("priority", 0),
                "accuracy": fb.get("accuracy", 100),
                "effect": fb.get("effect", ""),
                "is_sound": fb.get("is_sound", False),
                "is_reflectable": fb.get("is_reflectable", False),
                "is_powder": fb.get("is_powder", False),
                "bypass_sub": fb.get("bypass_sub", False),
                "ignore_ability": fb.get("ignore_ability", False),
                "is_ohko": fb.get("is_ohko", False),
                "hits_flying": fb.get("hits_flying", False),
                "boosts": fb.get("boosts", {})
            }

        # Heuristic for unlisted exotic moves
        cat = "status" if any(k in clean_id for k in ("dance", "plot", "mind", "bulk", "coil", "charge", "recover", "roost", "heal", "wish", "protect", "shield", "spikes", "rock", "toxic", "wave")) else "physical"
        type_guess = "Normal"
        for t in TYPE_CHART.keys():
            if t.lower() in clean_id or t.lower() in clean_name:
                type_guess = t
                break
        return {
            "name": move_name or move_id,
            "type": type_guess,
            "category": cat,
            "bp": 80 if cat != "status" else 0,
            "priority": 0,
            "accuracy": 100,
            "effect": "",
            "is_sound": False,
            "is_reflectable": False,
            "is_powder": False,
            "bypass_sub": False,
            "ignore_ability": False,
            "is_ohko": False,
            "hits_flying": False,
            "boosts": {}
        }

    @staticmethod
    def calculate_effectiveness(
        move_type: str,
        def_types: List[str],
        def_ability: str = "",
        hits_flying: bool = False,
        ignore_ability: bool = False,
        atk_ability: str = "",
        def_item: str = "",
        has_air_balloon: bool = False
    ) -> float:
        """Computes true type effectiveness considering dual-types, item immunities, and ability bypasses."""
        if not def_types:
            return 1.0

        chart = TYPE_CHART.get(move_type, {})
        mult = 1.0
        for dt in def_types:
            mult *= chart.get(dt, 1.0)

        # Air Balloon check
        if (has_air_balloon or "air balloon" in def_item.lower()) and move_type == "Ground" and not hits_flying:
            return 0.0

        # Check ability bypass (Mold Breaker, Teravolt, Turboblaze, Neutralizing Gas, or ignore_ability moves like Sunsteel Strike)
        atk_ab_clean = (atk_ability or "").lower()
        if ignore_ability or any(k in atk_ab_clean for k in ("mold breaker", "teravolt", "turboblaze", "neutralizing gas")):
            # Ability immunities are bypassed!
            return mult

        # ─── DEFENSIVE ABILITY IMMUNITIES ───
        ab_clean = (def_ability or "").lower()

        # 1. Wonder Guard: ONLY super-effective (mult > 1.0) deals damage!
        if "wonder guard" in ab_clean:
            if mult <= 1.0:
                return 0.0

        # 2. Levitate: Ground moves deal 0 (unless Thousand Arrows / hits_flying)
        if "levitate" in ab_clean and move_type == "Ground" and not hits_flying:
            return 0.0

        # 3. Flash Fire / Well-Baked Body
        if ("flash fire" in ab_clean or "well-baked" in ab_clean) and move_type == "Fire":
            return 0.0

        # 4. Volt Absorb / Lightning Rod / Motor Drive
        if any(k in ab_clean for k in ("volt absorb", "lightning rod", "motor drive")) and move_type == "Electric":
            return 0.0

        # 5. Water Absorb / Storm Drain / Dry Skin
        if any(k in ab_clean for k in ("water absorb", "storm drain", "dry skin")) and move_type == "Water":
            return 0.0

        # 6. Earth Eater
        if "earth eater" in ab_clean and move_type == "Ground" and not hits_flying:
            return 0.0

        # 7. Sap Sipper
        if "sap sipper" in ab_clean and move_type == "Grass":
            return 0.0

        return mult

    def score_move(
        self,
        move_obj: Dict[str, Any],
        my_species: str,
        my_types: List[str],
        my_hp_pct: float,
        opp_species: str,
        opp_types: List[str],
        opp_hp_pct: float,
        opp_ability: str,
        immune_moves: Set[str],
        hazards_up: bool,
        stall_count: int,
        can_tera: bool = False,
        immune_types: Optional[Set[str]] = None,
        opp_status: str = "",
        my_status: str = "",
        my_boosts: Optional[Dict[str, int]] = None,
        opp_boosts: Optional[Dict[str, int]] = None,
        failed_moves: Optional[Set[str]] = None,
        opp_substitute: bool = False,
        opp_item: str = "",
        terrain: str = "",
        weather: str = "",
        battle_format: str = "",
        sleep_clause_active: bool = False,
        my_ability: str = "",
        learned_intel: Optional[Dict[str, Any]] = None
    ) -> Tuple[float, str, bool]:
        """
        Hyper-intelligent battle decision evaluator with anti-repetition memory,
        mechanics-accurate status checks, and setup thresholds.
        """
        m_id = move_obj.get("id", "").lower()
        m_name = move_obj.get("move", "")
        minfo = self.get_move_info(m_id, m_name)
        m_type = minfo["type"]
        cat = minfo["category"]
        bp = minfo["bp"]
        priority = minfo.get("priority", 0)
        acc = minfo.get("accuracy", 100)
        effect = minfo.get("effect", "")
        hits_flying = minfo.get("hits_flying", False)
        ignore_ab = minfo.get("ignore_ability", False)
        is_ohko = minfo.get("is_ohko", False)
        opp_ab_clean = (opp_ability or "").lower()

        # Check persistent learned intel for this species (e.g. Wonder Guard, Soundproof, Air Balloon)
        if learned_intel:
            known_abs = [a.lower() for a in learned_intel.get("abilities", [])]
            if "wonder guard" in known_abs and not opp_ab_clean:
                opp_ab_clean = "wonder guard"
            if "soundproof" in known_abs and not opp_ab_clean:
                opp_ab_clean = "soundproof"
            if "magic bounce" in known_abs and not opp_ab_clean:
                opp_ab_clean = "magic bounce"
            if not opp_item and learned_intel.get("items"):
                opp_item = list(learned_intel.get("items"))[0]

        # 1. Strict blacklist if move previously dealt 0 or was immune
        if m_id in immune_moves or m_name.lower() in immune_moves:
            return -99999.0, f"{m_name} previously had 0x effect/immune vs {opp_species} - strictly avoiding!", False

        # 2. Strict blacklist if move previously failed against this opponent
        if failed_moves and (m_id in failed_moves or m_name.lower() in failed_moves):
            return -99999.0, f"{m_name} previously failed vs {opp_species} - avoid repeating mistake!", False

        # 3. Strict blacklist if move's type was learned to be 0x immune vs this target
        if immune_types and m_type in immune_types and not ignore_ab:
            return -99999.0, f"{m_type}-type attacks are 0x immune vs {opp_species}", False

        # ─── 4. STATUS / AFFLICTION REPETITION & IMMUNITY GUARDS ───
        if effect in ("sleep", "burn", "paralyze", "toxic"):
            # Target ALREADY has a status condition: A Pokémon CANNOT have two non-volatile statuses!
            if opp_status:
                return -99999.0, f"{opp_species} is already afflicted with {opp_status.upper()} - {m_name} will fail!", False

            # Sleep mechanics & immunities
            if effect == "sleep":
                if sleep_clause_active:
                    return -99999.0, f"Sleep Clause active - cannot put another Pokémon to sleep with {m_name}!", False
                if any(k in opp_ab_clean for k in ("insomnia", "vital spirit", "sweet veil", "comatose", "purifying salt", "good as gold")):
                    return -99999.0, f"{opp_species} has {opp_ability or 'sleep-immune ability'} - {m_name} will fail!", False
                if terrain.lower() in ("electricterrain", "mistyterrain"):
                    return -99999.0, f"{terrain} is active - grounded Pokémon cannot fall asleep to {m_name}!", False

            # Burn mechanics & immunities
            elif effect == "burn":
                if "Fire" in opp_types or any(k in opp_ab_clean for k in ("water veil", "water bubble", "thermal exchange", "purifying salt", "good as gold")):
                    return -99999.0, f"{opp_species} is immune to burns - {m_name} will fail!", False

            # Paralysis mechanics & immunities
            elif effect == "paralyze":
                if "Electric" in opp_types or ("Ground" in opp_types and m_type == "Electric") or any(k in opp_ab_clean for k in ("limber", "purifying salt", "good as gold")):
                    return -99999.0, f"{opp_species} is immune to paralysis - {m_name} will fail!", False

            # Toxic / Poison mechanics & immunities
            elif effect == "toxic":
                if ("Steel" in opp_types or "Poison" in opp_types) or any(k in opp_ab_clean for k in ("immunity", "poison heal", "purifying salt", "good as gold")):
                    return -99999.0, f"{opp_species} is immune to poison - {m_name} will fail!", False

            # General status immunities
            if any(k in opp_ab_clean for k in ("good as gold", "purifying salt")):
                return -99999.0, f"{opp_species} has {opp_ability} (status immune) - {m_name} will fail!", False

        # ─── 5. MAGIC BOUNCE & SOUNDPROOF GUARDS ───
        if "magic bounce" in opp_ab_clean:
            if minfo.get("is_reflectable") or cat == "status":
                return -99999.0, f"{opp_species} has Magic Bounce! {m_name} will bounce back against us!", False

        if "soundproof" in opp_ab_clean and minfo.get("is_sound"):
            return -99999.0, f"{opp_species} has Soundproof - sound-based move {m_name} is completely blocked!", False

        # Powder move immunity (Grass types, Safety Goggles, Overcoat)
        if minfo.get("is_powder"):
            if "Grass" in opp_types or "safety goggles" in (opp_item or "").lower() or "overcoat" in opp_ab_clean:
                return -99999.0, f"{opp_species} is immune to powder moves ({m_name})!", False

        # Substitute guard (status moves fail into substitute unless bypass_sub / sound)
        if opp_substitute and cat == "status" and not minfo.get("bypass_sub") and not minfo.get("is_sound"):
            return -99999.0, f"{opp_species} is behind a Substitute - status move {m_name} will fail!", False

        # ─── 6. STATUS / TACTICAL MOVES EVALUATION ───
        if cat == "status" or bp == 0:
            # Healing moves
            if effect == "heal":
                if my_hp_pct < 40.0:
                    return 250.0, f"Critical HP ({my_hp_pct:.0f}%) - emergency heal with {m_name}", False
                elif my_hp_pct < 65.0:
                    return 140.0, f"Sustain HP ({my_hp_pct:.0f}%) with {m_name}", False
                else:
                    return -100.0, f"HP full ({my_hp_pct:.0f}%) - do not heal", False

            # Setup moves
            if effect == "setup":
                boosts = my_boosts or {}
                # Attack boost checks
                if any(k in m_id for k in ("swordsdance", "dragondance", "bulkup", "bellydrum", "shiftgear", "coil")):
                    atk_b = boosts.get("atk", 0)
                    if atk_b >= 6:
                        return -99999.0, f"Attack stat already maxed out (+6) - {m_name} will fail!", False
                    elif atk_b >= 2 and opp_hp_pct < 85.0:
                        return 30.0, f"Already at +{atk_b} Attack - attack rather than over-boosting with {m_name}", False
                # Sp. Atk boost checks
                if any(k in m_id for k in ("nastyplot", "calmmind", "quiverdance", "tailglow", "geomancy")):
                    spa_b = boosts.get("spa", 0)
                    if spa_b >= 6:
                        return -99999.0, f"Sp. Atk stat already maxed out (+6) - {m_name} will fail!", False
                    elif spa_b >= 2 and opp_hp_pct < 85.0:
                        return 30.0, f"Already at +{spa_b} Sp. Atk - attack rather than over-boosting with {m_name}", False
                # Belly Drum check
                if "bellydrum" in m_id and my_hp_pct <= 50.0:
                    return -99999.0, f"HP ({my_hp_pct:.0f}%) too low for Belly Drum (requires >50%)!", False
                # Unaware check
                if "unaware" in opp_ab_clean:
                    return -80.0, f"{opp_species} has Unaware (ignores stat boosts) - setup with {m_name} is ineffective", False

                if my_hp_pct > 70.0 and opp_hp_pct > 50.0:
                    return 170.0, f"Healthy HP ({my_hp_pct:.0f}%) - boost stats with {m_name}", False
                elif my_hp_pct > 45.0:
                    return 110.0, f"Boost stats with {m_name}", False
                else:
                    return -50.0, f"HP too low ({my_hp_pct:.0f}%) to spend turn setting up", False

            # Hazards
            if effect == "hazard":
                if not hazards_up:
                    return 130.0, f"Set entry hazards with {m_name}", False
                else:
                    return -500.0, f"Hazards already active - do not recast {m_name}", False

            # Protection
            if effect == "protect":
                if stall_count == 0 and opp_hp_pct > 15.0:
                    return 90.0, f"Tactical shield with {m_name}", False
                else:
                    return -800.0, f"Protect consecutive use penalty - likely to fail", False

            # Status afflictions (scaled by accuracy)
            if effect in ("paralyze", "sleep", "burn", "toxic"):
                base_score = 140.0 if effect == "sleep" else 110.0
                score = base_score * (acc / 100.0)
                if opp_hp_pct <= 30.0:
                    score -= 60.0  # Don't status an opponent we can finish off with an attack
                return score, f"Tactical {effect} affliction with {m_name} ({acc}% acc)", False

            # OHKO moves with No Guard (Hackmons meta)
            if is_ohko:
                if "no guard" in (my_ability.lower() + " " + opp_ab_clean):
                    return 550.0, f"🎯 No Guard OHKO guaranteed kill with {m_name}!", False
                else:
                    return 35.0, f"Risky 30% OHKO move {m_name}", False

            return 50.0, f"Tactical utility {m_name}", False

        # ─── 7. OFFENSIVE MOVES EVALUATION ───
        eff = self.calculate_effectiveness(
            move_type=m_type,
            def_types=opp_types,
            def_ability=opp_ability,
            hits_flying=hits_flying,
            ignore_ability=ignore_ab,
            atk_ability=my_ability,
            def_item=opp_item
        )

        # If move is completely immune (0x), STRICTLY AVOID IT!
        if eff == 0.0:
            return -99999.0, f"{m_name} ({m_type}) is 0x IMMUNE vs {opp_species} ({'/'.join(opp_types)})", False

        # STAB bonus
        stab = 1.5 if m_type in my_types else 1.0

        # Base expected damage benchmark
        expected_dmg = bp * stab * eff

        # Stat boost multipliers
        boosts = my_boosts or {}
        if cat == "physical":
            atk_b = boosts.get("atk", 0)
            if atk_b > 0:
                expected_dmg *= (1.0 + 0.5 * atk_b)
            elif atk_b < 0:
                expected_dmg *= (2.0 / (2.0 - atk_b))
            if any(k in my_ability.lower() for k in ("huge power", "pure power")):
                expected_dmg *= 2.0
        elif cat == "special":
            spa_b = boosts.get("spa", 0)
            if spa_b > 0:
                expected_dmg *= (1.0 + 0.5 * spa_b)
            elif spa_b < 0:
                expected_dmg *= (2.0 / (2.0 - spa_b))

        # Accuracy factor
        expected_dmg *= (acc / 100.0)

        # Tactical multipliers
        tera_rec = False
        reason = f"{m_name} ({m_type}, {bp} BP, {eff}x eff)"

        if eff >= 4.0:
            expected_dmg += 150.0
            reason += " [DOUBLE SUPER EFFECTIVE! 💥]"
        elif eff >= 2.0:
            expected_dmg += 80.0
            reason += " [SUPER EFFECTIVE! ⚡]"
        elif eff <= 0.25:
            expected_dmg -= 80.0
            reason += " [HEAVILY RESISTED ⚠️]"
        elif eff <= 0.5:
            expected_dmg -= 40.0
            reason += " [RESISTED ⚠️]"

        # Priority execute bonus: if opponent is low HP, finish them before they strike
        if priority > 0 and opp_hp_pct <= 35.0:
            expected_dmg += 120.0
            reason += f" [PRIORITY EXECUTE +{priority}]"

        # Terastallize recommendation: if Tera boosts this move's STAB and gives super effective damage
        if can_tera and eff >= 2.0 and stab == 1.0:
            tera_rec = True
            expected_dmg += 40.0
            reason += " [RECOMMEND TERA]"

        return expected_dmg, reason, tera_rec

    def evaluate_switches(
        self,
        side_pokemon: List[Dict[str, Any]],
        my_active_name: str,
        opp_species: str,
        opp_types: List[str],
        opp_ability: str = "",
        immune_moves: Optional[Set[str]] = None,
        immune_types: Optional[Set[str]] = None,
        opp_last_move: str = "",
        opp_item: str = "",
        battle_format: str = "",
        my_ability: str = "",
        learned_intel: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[int, float, str]]:
        """Evaluates bench Pokémon to find effective counters when active Pokémon is walled."""
        ranked_switches = []

        # Determine effective opponent ability including persistent learned intel
        effective_opp_ab = (opp_ability or "").strip().lower()
        if learned_intel:
            known_abs = [a.lower() for a in learned_intel.get("abilities", [])]
            if "wonder guard" in known_abs and not effective_opp_ab:
                effective_opp_ab = "wonder guard"
            if not opp_item and learned_intel.get("items"):
                opp_item = list(learned_intel.get("items"))[0]

        has_wonder_guard = "wonder guard" in effective_opp_ab

        for idx, p in enumerate(side_pokemon, 1):
            if p.get("active") or p.get("condition", "").endswith("fnt") or p.get("condition", "") == "0 fnt":
                continue

            bench_raw = p.get("details", "") or p.get("species", "") or p.get("ident", "")
            bench_species = bench_raw.split(",")[0].split(":", 1)[-1].strip()
            bench_types = self.get_pokemon_types(bench_species)
            bench_ability = (p.get("ability") or p.get("baseAbility") or "").lower()
            bench_moves = p.get("moves", [])

            score = 100.0
            reasons = []

            # ─── 1. OFFENSIVE VERIFICATION (Can bench actually hit/damage opponent?) ───
            bench_can_pierce_wonder = False
            best_move_eff = 0.0
            has_valid_damaging_move = False

            for m_raw in bench_moves:
                m_clean = m_raw.strip().lower()
                if immune_moves and m_clean in immune_moves:
                    continue
                minfo = self.get_move_info(m_clean)
                m_type = minfo["type"]
                cat = minfo["category"]
                bp = minfo["bp"]
                ignore_ab = minfo.get("ignore_ability", False)
                is_ohko = minfo.get("is_ohko", False)

                # OHKO + No Guard check
                if is_ohko and ("no guard" in bench_ability or "no guard" in effective_opp_ab):
                    bench_can_pierce_wonder = True
                    has_valid_damaging_move = True
                    best_move_eff = max(best_move_eff, 4.0)
                    reasons.append(f"OHKO move ({m_clean})")
                    continue

                if cat == "status" or bp <= 0:
                    continue

                if immune_types and m_type in immune_types and not ignore_ab:
                    continue

                eff = self.calculate_effectiveness(
                    move_type=m_type,
                    def_types=opp_types,
                    def_ability=effective_opp_ab,
                    hits_flying=minfo.get("hits_flying", False),
                    ignore_ability=ignore_ab,
                    atk_ability=bench_ability,
                    def_item=opp_item
                )

                if eff > 0.0:
                    has_valid_damaging_move = True
                    best_move_eff = max(best_move_eff, eff)
                    if ignore_ab or eff > 1.0:
                        bench_can_pierce_wonder = True

            # STRICT WONDER GUARD PENALTY: Never switch to a Pokémon that cannot damage Wonder Guard!
            if has_wonder_guard and not bench_can_pierce_wonder:
                score = -99999.0
                ranked_switches.append((idx, score, f"Skip {bench_species}: 0 moves can damage Wonder Guard {opp_species}! [Score: {score:.0f}]"))
                continue

            # Ineffective bench penalty
            if not has_valid_damaging_move and len(bench_moves) > 0:
                score = -99999.0
                ranked_switches.append((idx, score, f"Skip {bench_species}: All moves ineffective vs {opp_species}! [Score: {score:.0f}]"))
                continue

            # Offensive damage bonuses
            if best_move_eff >= 4.0:
                score += 180.0
                reasons.append(f"4x Super Effective ({best_move_eff}x)")
            elif best_move_eff >= 2.0:
                score += 90.0
                reasons.append(f"Super Effective ({best_move_eff}x)")
            elif bench_can_pierce_wonder and has_wonder_guard:
                score += 120.0
                reasons.append("Wonder Guard Piercing Attack")

            # ─── 2. DEFENSIVE MATCHUP AGAINST OPPONENT'S ACTIVE MOVE ───
            if opp_last_move:
                last_minfo = self.get_move_info(opp_last_move)
                last_mtype = last_minfo.get("type", "")
                if last_mtype:
                    move_eff = self.calculate_effectiveness(last_mtype, bench_types, def_ability=bench_ability)
                    if move_eff == 0.0:
                        # IMMUNITY: Free switch into locked or preferred attack (e.g. Fairy into Outrage)!
                        score += 250.0
                        reasons.append(f"Immune to opponent's {opp_last_move} ({last_mtype})!")
                    elif move_eff <= 0.5:
                        score += 80.0
                        reasons.append(f"Resists opponent's {opp_last_move}")
                    elif move_eff >= 2.0:
                        # SUICIDE SWITCH: Bench is weak to move opponent just used!
                        score -= 300.0
                        reasons.append(f"⚠️ Weak to opponent's {opp_last_move} ({move_eff}x)!")

            # ─── 3. DEFENSIVE MATCHUP AGAINST OPPONENT STAB TYPES ───
            for ot in opp_types:
                res = self.calculate_effectiveness(ot, bench_types, def_ability=bench_ability)
                if res <= 0.5:
                    score += 40.0
                elif res == 0.0:
                    score += 90.0
                elif res >= 2.0:
                    score -= 50.0

            reason_str = ", ".join(reasons) if reasons else f"{'/'.join(bench_types)}"
            ranked_switches.append((idx, score, f"Switch to {bench_species} ({reason_str}) [Score: {score:.0f}]"))

        ranked_switches.sort(key=lambda x: x[1], reverse=True)
        return ranked_switches
