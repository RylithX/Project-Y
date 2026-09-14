"""
ShowdownTeamBuilder: Dynamic competitive Pokémon team generator, validator, auto-healer and packer.
Supports all Smogon formats (Gen 9 OU, Ubers, AG, Doubles, Monotype, Gen 8/7), LLM generation,
and automatic real-time correction of team rejections (e.g. 508 EV restrictions, tier bans).
"""

import os
import re
import json
import random
from typing import Optional, Dict, Any, List, Callable, Tuple


def fix_508_evs_in_packed(packed_team: str) -> str:
    """Adjusts EV spreads in packed format so total EVs != 508 to satisfy Showdown unrestricted EV rule."""
    mons = packed_team.split("]")
    fixed_mons = []
    for m in mons:
        parts = m.split("|")
        if len(parts) >= 7:
            ev_str = parts[6]
            ev_list = [int(x) if x.isdigit() else 0 for x in ev_str.split(",")]
            while len(ev_list) < 6:
                ev_list.append(0)
            total_evs = sum(ev_list)
            if total_evs == 508:
                # Add 1 EV to the 4 EV stat or lowest non-zero stat (making total 509)
                for i in range(6):
                    if ev_list[i] == 4:
                        ev_list[i] = 5
                        break
                else:
                    for i in range(6):
                        if 0 < ev_list[i] < 252:
                            ev_list[i] += 1
                            break
                    else:
                        for i in range(6):
                            if ev_list[i] < 252:
                                ev_list[i] += 1
                                break
                parts[6] = ",".join(str(x) if x else "" for x in ev_list)
            fixed_mons.append("|".join(parts))
        else:
            fixed_mons.append(m)
    return "]".join(fixed_mons)


def fix_508_evs_in_export(text: str) -> str:
    """Adjusts EV lines in Pokepaste text from 508 to 509 EVs to pass Showdown unrestricted EV check."""
    lines = []
    for line in text.splitlines():
        if line.strip().startswith("EVs:"):
            ev_str = line.split(":", 1)[1].strip()
            parts = [p.strip() for p in ev_str.split("/") if p.strip()]
            tot = 0
            ev_entries = []
            for p in parts:
                toks = p.split()
                if len(toks) >= 2 and toks[0].isdigit():
                    val = int(toks[0])
                    tot += val
                    ev_entries.append((val, toks[1]))
            if tot == 508:
                new_entries = []
                added = False
                for val, stat in ev_entries:
                    if not added and (val == 4 or val < 252):
                        new_entries.append(f"{val + 1} {stat}")
                        added = True
                    else:
                        new_entries.append(f"{val} {stat}")
                lines.append(f"EVs: {' / '.join(new_entries)}")
                continue
        lines.append(line)
    return "\n".join(lines)


def parse_and_pack_showdown_team(text: str, format_hint: str = "") -> str:
    """Parses standard Showdown export / Pokepaste text into Showdown /utm packed format."""
    mons = []
    current_mon = None

    for raw_line in text.strip().splitlines():
        line = raw_line.strip()
        if not line:
            if current_mon and (current_mon.get("species") or current_mon.get("name")):
                mons.append(current_mon)
                current_mon = None
            continue

        if current_mon is None:
            current_mon = {
                "name": "", "species": "", "item": "", "ability": "",
                "moves": [], "nature": "Hardy", "evs": [""] * 6,
                "gender": "", "ivs": [""] * 6, "shiny": False,
                "level": "", "tera_type": ""
            }
            if "@" in line:
                head, item_part = line.split("@", 1)
                current_mon["item"] = item_part.strip()
            else:
                head = line

            if "(M)" in head:
                current_mon["gender"] = "M"
                head = head.replace("(M)", "")
            elif "(F)" in head:
                current_mon["gender"] = "F"
                head = head.replace("(F)", "")

            head = head.strip()
            if "(" in head and ")" in head:
                nick, sp = head.split("(", 1)
                current_mon["name"] = nick.strip()
                current_mon["species"] = sp.replace(")", "").strip()
            else:
                current_mon["species"] = head.strip()
                current_mon["name"] = head.strip()
        else:
            if line.startswith("Ability:"):
                current_mon["ability"] = line.split(":", 1)[1].strip()
            elif line.startswith("Tera Type:"):
                current_mon["tera_type"] = line.split(":", 1)[1].strip()
            elif line.startswith("Shiny:"):
                val = line.split(":", 1)[1].strip().lower()
                current_mon["shiny"] = (val in ("yes", "true", "s"))
            elif line.startswith("Level:"):
                current_mon["level"] = line.split(":", 1)[1].strip()
            elif line.endswith("Nature"):
                current_mon["nature"] = line.split()[0].strip()
            elif line.startswith("EVs:"):
                ev_str = line.split(":", 1)[1].strip()
                ev_map = {"hp": 0, "atk": 1, "def": 2, "spa": 3, "spd": 4, "spe": 5}
                ev_arr = [""] * 6
                for part in ev_str.split("/"):
                    p = part.strip().split()
                    if len(p) >= 2:
                        val = p[0]
                        stat = p[1].lower()
                        if stat in ev_map:
                            ev_arr[ev_map[stat]] = val
                current_mon["evs"] = ev_arr
            elif line.startswith("IVs:"):
                iv_str = line.split(":", 1)[1].strip()
                iv_map = {"hp": 0, "atk": 1, "def": 2, "spa": 3, "spd": 4, "spe": 5}
                iv_arr = [""] * 6
                for part in iv_str.split("/"):
                    p = part.strip().split()
                    if len(p) >= 2:
                        val = p[0]
                        stat = p[1].lower()
                        if stat in iv_map and val != "31":
                            iv_arr[iv_map[stat]] = val
                current_mon["ivs"] = iv_arr
            elif line.startswith("-"):
                move_name = line.lstrip("- ").strip()
                if move_name:
                    current_mon["moves"].append(move_name)

    if current_mon and (current_mon.get("species") or current_mon.get("name")):
        mons.append(current_mon)

    packed_parts = []
    for m in mons:
        name = m.get("name", "")
        species = m.get("species", "")
        if name.lower() == species.lower():
            name = ""
        item = re.sub(r"[^a-zA-Z0-9_-]", "", m.get("item", ""))
        ability = re.sub(r"[^a-zA-Z0-9_-]", "", m.get("ability", ""))
        moves = ",".join(re.sub(r"[^a-zA-Z0-9_-]", "", mv) for mv in m.get("moves", []))
        nature = m.get("nature", "Hardy")

        # Proactively fix 508 EVs in unrestricted formats
        ev_ints = [int(x) if str(x).isdigit() else 0 for x in m.get("evs", [""] * 6)]
        if sum(ev_ints) == 508 and any(f in format_hint.lower() for f in ("ag", "anythinggoes", "hackmons", "custom")):
            for i in range(6):
                if ev_ints[i] == 4:
                    ev_ints[i] = 5
                    break
            else:
                for i in range(6):
                    if 0 < ev_ints[i] < 252:
                        ev_ints[i] += 1
                        break
            m["evs"] = [str(x) if x else "" for x in ev_ints]

        evs = ",".join(str(x) if x else "" for x in m.get("evs", [""] * 6))
        gender = m.get("gender", "")
        ivs = ",".join(str(x) if x else "" for x in m.get("ivs", [""] * 6))
        shiny = "S" if m.get("shiny") else ""
        level = str(m.get("level", "")) if str(m.get("level", "")) not in ("", "100") else ""
        tera = m.get("tera_type", "")
        misc = f",,,{tera}" if tera else ""
        packed_parts.append(f"{name}|{species}|{item}|{ability}|{moves}|{nature}|{evs}|{gender}|{ivs}|{shiny}|{level}|{misc}")

    return "]".join(packed_parts)


# ─── BUILT-IN COMPETITIVE SMOGON ARCHETYPES ──────────────────────
COMPETITIVE_ARCHETYPES = {
    "gen9ou": """
Great Tusk @ Booster Energy  
Ability: Protosynthesis  
Tera Type: Ice  
EVs: 252 Atk / 4 SpD / 252 Spe  
Jolly Nature  
- Headlong Rush  
- Close Combat  
- Ice Spinner  
- Rapid Spin  

Kingambit @ Lum Berry  
Ability: Supreme Overlord  
Tera Type: Flying  
EVs: 212 HP / 252 Atk / 44 Spe  
Adamant Nature  
- Swords Dance  
- Kowtow Cleave  
- Sucker Punch  
- Iron Head  

Gholdengo @ Choice Scarf  
Ability: Good as Gold  
Tera Type: Fighting  
EVs: 252 SpA / 4 SpD / 252 Spe  
Timid Nature  
- Shadow Ball  
- Make It Rain  
- Focus Blast  
- Trick  

Ogerpon-Wellspring (F) @ Wellspring Mask  
Ability: Water Absorb  
Tera Type: Water  
EVs: 252 Atk / 4 SpD / 252 Spe  
Jolly Nature  
- Ivy Cudgel  
- Horn Leech  
- Play Rough  
- Swords Dance  

Dragonite @ Heavy-Duty Boots  
Ability: Multiscale  
Tera Type: Normal  
EVs: 252 Atk / 4 SpD / 252 Spe  
Adamant Nature  
- Dragon Dance  
- Extreme Speed  
- Earthquake  
- Roost  

Iron Valiant @ Booster Energy  
Ability: Quark Drive  
Tera Type: Fairy  
EVs: 4 Atk / 252 SpA / 252 Spe  
Naive Nature  
- Moonblast  
- Close Combat  
- Thunderbolt  
- Encore  
""",

    "gen9anythinggoes": """
Miraidon @ Choice Specs  
Ability: Hadron Engine  
Tera Type: Electric  
EVs: 252 SpA / 5 SpD / 252 Spe  
Timid Nature  
- Electro Drift  
- Draco Meteor  
- Overheat  
- Volt Switch  

Koraidon @ Choice Band  
Ability: Orichalcum Pulse  
Tera Type: Fire  
EVs: 252 Atk / 5 SpD / 252 Spe  
Jolly Nature  
- Collision Course  
- Flare Blitz  
- Low Kick  
- U-turn  

Calyrex-Shadow @ Life Orb  
Ability: As One (Spectrier)  
Tera Type: Ghost  
EVs: 252 SpA / 5 SpD / 252 Spe  
Timid Nature  
- Astral Barrage  
- Psyshock  
- Nasty Plot  
- Draining Kiss  

Arceus @ Silk Scarf  
Ability: Multitype  
Tera Type: Normal  
EVs: 252 HP / 252 Atk / 5 Spe  
Adamant Nature  
- Extreme Speed  
- Swords Dance  
- Earthquake  
- Taunt  

Zacian-Crowned @ Rusted Sword  
Ability: Intrepid Sword  
Tera Type: Ground  
EVs: 252 Atk / 5 SpD / 252 Spe  
Jolly Nature  
- Behemoth Blade  
- Play Rough  
- Close Combat  
- Swords Dance  

Ting-Lu @ Leftovers  
Ability: Vessel of Ruin  
Tera Type: Poison  
EVs: 252 HP / 5 Def / 252 SpD  
Careful Nature  
- Stealth Rock  
- Earthquake  
- Ruination  
- Whirlwind  
""",

    "gen9ubers": """
Koraidon @ Choice Band  
Ability: Orichalcum Pulse  
Tera Type: Fire  
EVs: 252 Atk / 4 SpD / 252 Spe  
Jolly Nature  
- Collision Course  
- Flare Blitz  
- Low Kick  
- U-turn  

Miraidon @ Choice Specs  
Ability: Hadron Engine  
Tera Type: Electric  
EVs: 252 SpA / 4 SpD / 252 Spe  
Timid Nature  
- Electro Drift  
- Draco Meteor  
- Overheat  
- Volt Switch  

Zacian-Crowned @ Rusted Sword  
Ability: Intrepid Sword  
Tera Type: Ground  
EVs: 252 Atk / 4 SpD / 252 Spe  
Jolly Nature  
- Behemoth Blade  
- Play Rough  
- Close Combat  
- Swords Dance  

Ting-Lu @ Leftovers  
Ability: Vessel of Ruin  
Tera Type: Poison  
EVs: 252 HP / 4 Def / 252 SpD  
Careful Nature  
- Stealth Rock  
- Earthquake  
- Ruination  
- Whirlwind  

Flutter Mane @ Booster Energy  
Ability: Protosynthesis  
Tera Type: Fairy  
EVs: 252 SpA / 4 SpD / 252 Spe  
Timid Nature  
- Moonblast  
- Shadow Ball  
- Taunt  
- Pain Split  

Necrozma-Dusk-Mane @ Leftovers  
Ability: Prism Armor  
Tera Type: Water  
EVs: 252 HP / 252 Def / 4 SpD  
Impish Nature  
- Sunsteel Strike  
- Earthquake  
- Morning Sun  
- Thunder Wave  
""",

    "gen9doublesou": """
Flutter Mane @ Booster Energy  
Ability: Protosynthesis  
Tera Type: Fairy  
EVs: 252 SpA / 4 SpD / 252 Spe  
Timid Nature  
- Dazzling Gleam  
- Shadow Ball  
- Protect  
- Icy Wind  

Iron Hands @ Assault Vest  
Ability: Quark Drive  
Tera Type: Grass  
EVs: 252 HP / 252 Atk / 4 SpD  
Adamant Nature  
- Fake Out  
- Drain Punch  
- Wild Charge  
- Heavy Slam  

Tornadus @ Covert Cloak  
Ability: Prankster  
Tera Type: Ghost  
EVs: 252 HP / 140 Def / 116 Spe  
Timid Nature  
- Tailwind  
- Bleakwind Storm  
- Rain Dance  
- Taunt  

Ogerpon-Wellspring (F) @ Wellspring Mask  
Ability: Water Absorb  
Tera Type: Water  
EVs: 252 Atk / 4 SpD / 252 Spe  
Jolly Nature  
- Ivy Cudgel  
- Follow Me  
- Horn Leech  
- Spiky Shield  

Chi-Yu @ Choice Specs  
Ability: Beads of Ruin  
Tera Type: Ghost  
EVs: 252 SpA / 4 SpD / 252 Spe  
Modest Nature  
- Heat Wave  
- Dark Pulse  
- Overheat  
- Snarl  

Landorus-Therian @ Choice Scarf  
Ability: Intimidate  
Tera Type: Flying  
EVs: 252 Atk / 4 SpD / 252 Spe  
Adamant Nature  
- Stomping Tantrum  
- Rock Slide  
- Tera Blast  
- U-turn  
""",

    "gen8ou": """
Dragapult @ Choice Specs  
Ability: Infiltrator  
EVs: 252 SpA / 4 SpD / 252 Spe  
Timid Nature  
- Shadow Ball  
- Draco Meteor  
- Flamethrower  
- U-turn  

Landorus-Therian @ Leftovers  
Ability: Intimidate  
EVs: 252 HP / 164 Def / 92 Spe  
Impish Nature  
- Stealth Rock  
- Earthquake  
- U-turn  
- Toxic  

Ferrothorn @ Leftovers  
Ability: Iron Barbs  
EVs: 252 HP / 80 Def / 176 SpD  
Careful Nature  
- Spikes  
- Knock Off  
- Leech Seed  
- Power Whip  

Heatran @ Leftovers  
Ability: Flash Fire  
EVs: 252 HP / 136 SpD / 120 Spe  
Calm Nature  
- Magma Storm  
- Earth Power  
- Taunt  
- Toxic  

Clefable @ Life Orb  
Ability: Magic Guard  
EVs: 252 HP / 196 Def / 60 SpD  
Bold Nature  
- Moonblast  
- Soft-Boiled  
- Flamethrower  
- Calm Mind  

Weavile @ Choice Band  
Ability: Pressure  
EVs: 252 Atk / 4 SpD / 252 Spe  
Jolly Nature  
- Triple Axel  
- Knock Off  
- Ice Shard  
- Low Kick  
""",

    "gen9balancedhackmons": """
Chansey @ Eviolite  
Ability: Imposter  
Tera Type: Normal  
EVs: 252 HP / 252 Atk / 252 Def / 252 SpA / 252 SpD / 252 Spe  
Bold Nature  
- Transform  
- Soft-Boiled  
- Whirlwind  
- Toxic  

Arceus @ Toxic Orb  
Ability: Poison Heal  
Tera Type: Normal  
EVs: 252 HP / 252 Atk / 252 Def / 252 SpA / 252 SpD / 252 Spe  
Adamant Nature  
- Extreme Speed  
- Swords Dance  
- Thousand Arrows  
- Strength Sap  

Ting-Lu @ Leftovers  
Ability: Ice Scales  
Tera Type: Poison  
EVs: 252 HP / 252 Def / 252 SpD  
Careful Nature  
- Ruination  
- Ceaseless Edge  
- Strength Sap  
- Whirlwind  

Corviknight @ Heavy-Duty Boots  
Ability: Fur Coat  
Tera Type: Dragon  
EVs: 252 HP / 252 Def / 252 SpD  
Impish Nature  
- U-turn  
- Strength Sap  
- Defog  
- Mortal Spin  

Calyrex-Shadow @ Life Orb  
Ability: Magic Bounce  
Tera Type: Fighting  
EVs: 252 HP / 252 Def / 252 SpA / 252 SpD / 252 Spe  
Timid Nature  
- Astral Barrage  
- Secret Sword  
- Quiver Dance  
- Strength Sap  

Dialga-Origin @ Assault Vest  
Ability: Regenerator  
Tera Type: Steel  
EVs: 252 HP / 252 Def / 252 SpA / 252 SpD  
Modest Nature  
- Core Enforcer  
- Doom Desire  
- Volt Switch  
- Mortal Spin  
""",

    "gen9purehackmons": """
Miraidon @ Air Balloon  
Ability: Wonder Guard  
Tera Type: Electric  
EVs: 252 HP / 252 Def / 252 SpA / 252 SpD / 252 Spe  
Timid Nature  
- Electro Drift  
- Moongeist Beam  
- Photon Geyser  
- Spore  

Slaking @ Choice Band  
Ability: Huge Power  
Tera Type: Normal  
EVs: 252 HP / 252 Atk / 252 Def / 252 SpD / 252 Spe  
Jolly Nature  
- Extreme Speed  
- Wicked Blow  
- Precipice Blades  
- V-create  

Zacian-Crowned @ Rusted Sword  
Ability: Wonder Guard  
Tera Type: Ground  
EVs: 252 HP / 252 Atk / 252 Def / 252 SpD / 252 Spe  
Jolly Nature  
- Sunsteel Strike  
- Thousand Arrows  
- V-create  
- Shift Gear  

Deoxys-Speed @ Focus Sash  
Ability: No Guard  
Tera Type: Ghost  
EVs: 252 HP / 252 Def / 252 SpD / 252 Spe  
Timid Nature  
- Sheer Cold  
- Fissure  
- Spore  
- Taunt  

Calyrex-Shadow @ Heavy-Duty Boots  
Ability: Neutralizing Gas  
Tera Type: Dark  
EVs: 252 HP / 252 Def / 252 SpA / 252 SpD / 252 Spe  
Timid Nature  
- Astral Barrage  
- Shell Smash  
- Secret Sword  
- Spore  

Chansey @ Eviolite  
Ability: Imposter  
EVs: 252 HP / 252 Def / 252 SpD / 252 Spe  
Bold Nature  
- Transform  
- Soft-Boiled  
- Whirlwind  
- Spore  
""",

    "gen8balancedhackmons": """
Chansey @ Eviolite  
Ability: Imposter  
EVs: 252 HP / 252 Def / 252 SpD / 252 Spe  
Bold Nature  
- Transform  
- Soft-Boiled  
- Spikes  
- Whirlwind  

Giratina @ Toxic Orb  
Ability: Poison Heal  
EVs: 252 HP / 252 Def / 252 SpD  
Careful Nature  
- Spectral Theft  
- Strength Sap  
- Core Enforcer  
- Defog  

Zacian-Crowned @ Rusted Sword  
Ability: Fur Coat  
EVs: 252 HP / 252 Atk / 252 Spe  
Jolly Nature  
- Behemoth Blade  
- Thousand Arrows  
- V-create  
- Shift Gear  

Registeel @ Leftovers  
Ability: Ice Scales  
EVs: 252 HP / 252 Def / 252 SpD  
Careful Nature  
- Anchor Shot  
- Strength Sap  
- Stealth Rock  
- U-turn  

Yveltal @ Life Orb  
Ability: Triage  
EVs: 252 HP / 252 SpA / 252 SpD  
Modest Nature  
- Oblivion Wing  
- Draining Kiss  
- Nasty Plot  
- Taunt  

Calyrex-Shadow @ Choice Specs  
Ability: Regenerator  
EVs: 252 SpA / 252 SpD / 252 Spe  
Timid Nature  
- Astral Barrage  
- Secret Sword  
- Trick  
- Volt Switch  
""",

    "gen7purehackmons": """
Deoxys-Speed @ Focus Sash  
Ability: No Guard  
EVs: 252 HP / 252 Atk / 252 Def / 252 SpA / 252 SpD / 252 Spe  
Timid Nature  
- Sheer Cold  
- Fissure  
- Sunsteel Strike  
- Spore  

Magearna @ Air Balloon  
Ability: Wonder Guard  
EVs: 252 HP / 252 Atk / 252 Def / 252 SpA / 252 SpD / 252 Spe  
Modest Nature  
- Sunsteel Strike  
- Moongeist Beam  
- Ice Beam  
- Shore Up  

Rayquaza-Mega @ Life Orb  
Ability: Wonder Guard  
EVs: 252 HP / 252 Atk / 252 Def / 252 SpA / 252 SpD / 252 Spe  
Jolly Nature  
- Dragon Ascent  
- Sunsteel Strike  
- Ice Beam  
- Extreme Speed  

Kyogre-Primal @ Blue Orb  
Ability: Primordial Sea  
EVs: 252 HP / 252 Atk / 252 Def / 252 SpA / 252 SpD / 252 Spe  
Modest Nature  
- Water Spout  
- Origin Pulse  
- Ice Beam  
- Sunsteel Strike  

Necrozma-Ultra @ Ultranecrozium Z  
Ability: Neuroforce  
EVs: 252 HP / 252 Atk / 252 Def / 252 SpA / 252 SpD / 252 Spe  
Timid Nature  
- Photon Geyser  
- Moongeist Beam  
- Sunsteel Strike  
- Ice Beam  

Xerneas @ Power Herb  
Ability: Wonder Guard  
EVs: 252 HP / 252 Atk / 252 Def / 252 SpA / 252 SpD / 252 Spe  
Timid Nature  
- Geomancy  
- Moonblast  
- Moongeist Beam  
- Sunsteel Strike  
""",

    "gen7ou": """
Greninja-Ash (M) @ Choice Specs  
Ability: Battle Bond  
EVs: 252 SpA / 5 SpD / 252 Spe  
Timid Nature  
- Hydro Pump  
- Dark Pulse  
- Water Shuriken  
- Spikes  

Landorus-Therian @ Leftovers  
Ability: Intimidate  
EVs: 252 HP / 240 Def / 16 Spe  
Impish Nature  
- Stealth Rock  
- Earthquake  
- U-turn  
- Hidden Power Ice  

Heatran @ Leftovers  
Ability: Flash Fire  
EVs: 252 HP / 136 SpD / 120 Spe  
Calm Nature  
- Magma Storm  
- Earth Power  
- Taunt  
- Toxic  

Magearna @ Assault Vest  
Ability: Soul-Heart  
EVs: 248 HP / 224 SpD / 36 Spe  
Calm Nature  
- Fleur Cannon  
- Flash Cannon  
- Volt Switch  
- Ice Beam  

Kartana @ Choice Scarf  
Ability: Beast Boost  
EVs: 252 Atk / 5 SpD / 252 Spe  
Jolly Nature  
- Leaf Blade  
- Sacred Sword  
- Smart Strike  
- Knock Off  

Toxapex @ Black Sludge  
Ability: Regenerator  
EVs: 252 HP / 252 Def / 5 SpD  
Bold Nature  
- Scald  
- Recover  
- Haze  
- Toxic Spikes  
"""
}


class ShowdownTeamBuilder:
    """Manages format-aware team creation, caching, persona flavoring, packing, and dynamic auto-healing."""

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = base_dir or os.path.dirname(os.path.abspath(__file__))
        self.teams_dir = os.path.join(self.base_dir, "memories", "showdown", "teams")
        os.makedirs(self.teams_dir, exist_ok=True)

    def _get_persona_nicknames(self, bot_name: str) -> List[str]:
        name_l = bot_name.lower()
        if "law" in name_l:
            return ["Scalpel", "Kikoku", "Shambles", "Heart", "Surgeon", "Room"]
        elif "briliance" in name_l:
            return ["Cosmos", "Supernova", "Eclipse", "Starlight", "Nebula", "Solaria"]
        else:
            # Yuna / Energetic champion style
            return ["Apex", "Blitz", "Juggernaut", "Titan", "Phantom", "Crown"]

    def apply_persona_styling(self, raw_export: str, bot_name: str, personality: str) -> str:
        """Injects custom persona nicknames and aesthetic flair into team export text."""
        nicks = self._get_persona_nicknames(bot_name)
        random.shuffle(nicks)

        lines = []
        nick_idx = 0
        for line in raw_export.splitlines():
            sline = line.strip()
            if "@" in sline and not sline.startswith(("-", "Ability:", "EVs:", "Tera", "Shiny:")):
                parts = sline.split("@", 1)
                species_part = parts[0].strip()
                item_part = parts[1].strip()
                if "(" not in species_part and nick_idx < len(nicks):
                    chosen_nick = nicks[nick_idx]
                    nick_idx += 1
                    lines.append(f"{chosen_nick} ({species_part}) @ {item_part}")
                    continue
            lines.append(line)
        return "\n".join(lines)

    async def build_or_load_team(
        self,
        bot_id: str,
        bot_name: str,
        personality: str,
        battle_format: str,
        llm_generate_cb: Optional[Callable] = None,
        force_regenerate: bool = False
    ) -> str:
        """Returns packed team string (/utm ready) for the given format."""
        clean_fmt = re.sub(r"[^a-zA-Z0-9_-]", "", battle_format.lower())
        cache_file = os.path.join(self.teams_dir, f"{bot_id}_{clean_fmt}.json")

        # 1. Check disk cache if available
        if not force_regenerate and os.path.exists(cache_file):
            try:
                with open(cache_file, "r") as f:
                    cached_data = json.load(f)
                    packed = cached_data.get("packed")
                    export_text = cached_data.get("export_text", "")
                    # Auto-heal: If format is hackmons, verify authentic Hackmons meta with Wonder Guard counters
                    if any(h in clean_fmt for h in ("hackmon", "bh")):
                        has_piercing = any(p in export_text for p in ("Sunsteel Strike", "Moongeist Beam", "Photon Geyser", "Ice Beam", "Sheer Cold"))
                        if not has_piercing or ("Great Tusk" in export_text and "Kingambit" in export_text):
                            print(f"[SHOWDOWN BUILDER] Cached team lacks Hackmons meta counters in {clean_fmt} - regenerating with top-tier archetype!")
                            packed = None  # Force fresh generation with authentic Hackmons meta
                    if packed and len(packed) > 20:
                        # Safety check: if AG/unrestricted, make sure not 508
                        if any(f in clean_fmt for f in ("ag", "anythinggoes", "hackmons")):
                            packed = fix_508_evs_in_packed(packed)
                        return packed
            except Exception:
                pass

        # 2. Try LLM generation if callback provided
        export_text = ""
        if llm_generate_cb:
            try:
                llm_res = await llm_generate_cb(bot_name, personality, battle_format)
                if llm_res and ("Ability:" in llm_res or "EVs:" in llm_res):
                    export_text = llm_res
            except Exception as e:
                print(f"[TEAM BUILDER] LLM generation failed: {e}")

        # 3. Fallback to Smogon competitive archetype
        if not export_text or len(export_text.splitlines()) < 8:
            base_fmt = "gen9ou"
            if "gen7" in clean_fmt:
                base_fmt = "gen7purehackmons" if "hackmon" in clean_fmt else "gen7ou"
            elif "gen8" in clean_fmt:
                base_fmt = "gen8balancedhackmons" if "hackmon" in clean_fmt else "gen8ou"
            elif "purehackmon" in clean_fmt or ("pure" in clean_fmt and "hackmon" in clean_fmt):
                base_fmt = "gen9purehackmons"
            elif "hackmon" in clean_fmt or "bh" in clean_fmt:
                base_fmt = "gen9balancedhackmons"
            elif "ag" in clean_fmt or "anythinggoes" in clean_fmt:
                base_fmt = "gen9anythinggoes"
            elif "uber" in clean_fmt:
                base_fmt = "gen9ubers"
            elif "double" in clean_fmt or "vgc" in clean_fmt:
                base_fmt = "gen9doublesou"
            elif "gen9" in clean_fmt or "ou" in clean_fmt:
                base_fmt = "gen9ou"
            export_text = COMPETITIVE_ARCHETYPES.get(base_fmt, COMPETITIVE_ARCHETYPES["gen9ou"])

        # 4. Apply persona styling (custom nicknames)
        styled_text = self.apply_persona_styling(export_text, bot_name, personality)

        # 5. Pack team
        packed_team = parse_and_pack_showdown_team(styled_text, format_hint=clean_fmt)

        # 6. Save to cache
        try:
            with open(cache_file, "w") as f:
                json.dump({
                    "bot_id": bot_id,
                    "format": battle_format,
                    "export_text": styled_text,
                    "packed": packed_team
                }, f, indent=2)
        except Exception:
            pass

        return packed_team

    async def fix_team_rejection(
        self,
        bot_id: str,
        bot_name: str,
        personality: str,
        battle_format: str,
        rejection_reasons: str,
        current_packed: Optional[str] = None,
        llm_generate_cb: Optional[Callable] = None
    ) -> Tuple[str, str, str]:
        """
        Dynamically diagnoses and fixes team rejection errors returned by Showdown.
        Returns (fixed_export_text, fixed_packed_team, explanation_summary).
        """
        clean_fmt = re.sub(r"[^a-zA-Z0-9_-]", "", battle_format.lower())
        cache_file = os.path.join(self.teams_dir, f"{bot_id}_{clean_fmt}.json")
        low_reasons = rejection_reasons.lower()

        current_export = ""
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r") as f:
                    cdata = json.load(f)
                    current_export = cdata.get("export_text", "")
                    if not current_packed:
                        current_packed = cdata.get("packed", "")
            except Exception:
                pass

        # ─── CASE 1: 508 EVs in unrestricted EV format ───
        if "508 evs" in low_reasons:
            explanation = "Adjusted EV allocations from 508 to 509 EVs to comply with Showdown unrestricted EV tier rules."
            fixed_packed = fix_508_evs_in_packed(current_packed) if current_packed else ""
            fixed_export = fix_508_evs_in_export(current_export) if current_export else ""

            if not fixed_packed or len(fixed_packed) < 20:
                fixed_packed = await self.build_or_load_team(
                    bot_id, bot_name, personality, battle_format, llm_generate_cb, force_regenerate=True
                )
                fixed_packed = fix_508_evs_in_packed(fixed_packed)

            try:
                with open(cache_file, "w") as f:
                    json.dump({
                        "bot_id": bot_id,
                        "format": battle_format,
                        "export_text": fixed_export,
                        "packed": fixed_packed
                    }, f, indent=2)
            except Exception:
                pass

            return fixed_export, fixed_packed, explanation

        # ─── CASE 2: Banned Pokémon, illegal abilities/moves ───
        if llm_generate_cb:
            prompt = (
                f"You are a competitive Pokémon master fixing a team rejected by Pokémon Showdown.\n"
                f"Format: {battle_format}\n"
                f"Trainer Persona: {bot_name} ({personality})\n\n"
                f"Showdown Rejection Errors:\n{rejection_reasons}\n\n"
                f"Current Rejected Team Export:\n{current_export}\n\n"
                f"Task:\n"
                f"Fix the exact errors listed above (replace banned Pokémon with legal tier staples, adjust illegal moves/abilities, ensure correct EV limits).\n"
                f"Output the complete fixed team in standard Pokémon Showdown export text (Pokepaste format) only! No markdown or extra commentary."
            )
            try:
                llm_fixed = await llm_generate_cb(bot_name, personality, prompt)
                if llm_fixed and ("Ability:" in llm_fixed or "EVs:" in llm_fixed):
                    fixed_export = self.apply_persona_styling(llm_fixed, bot_name, personality)
                    fixed_packed = parse_and_pack_showdown_team(fixed_export, format_hint=clean_fmt)
                    explanation = "AI strategist resolved tier legality and moveset violations."
                    try:
                        with open(cache_file, "w") as f:
                            json.dump({
                                "bot_id": bot_id,
                                "format": battle_format,
                                "export_text": fixed_export,
                                "packed": fixed_packed
                            }, f, indent=2)
                    except Exception:
                        pass
                    return fixed_export, fixed_packed, explanation
            except Exception as e:
                print(f"[TEAM FIXER LLM ERROR] {e}")

        # Fallback to verified legal archetype
        base_fmt = "gen9ou"
        if "gen7" in clean_fmt:
            base_fmt = "gen7purehackmons" if "hackmon" in clean_fmt else "gen7ou"
        elif "gen8" in clean_fmt:
            base_fmt = "gen8ou"
        elif "ag" in clean_fmt or "anythinggoes" in clean_fmt:
            base_fmt = "gen9anythinggoes"
        elif "uber" in clean_fmt:
            base_fmt = "gen9ubers"
        elif "double" in clean_fmt or "vgc" in clean_fmt:
            base_fmt = "gen9doublesou"

        fallback_export = COMPETITIVE_ARCHETYPES.get(base_fmt, COMPETITIVE_ARCHETYPES["gen9ou"])
        fixed_export = self.apply_persona_styling(fallback_export, bot_name, personality)
        if "508 evs" in low_reasons or "ag" in clean_fmt or "anythinggoes" in clean_fmt:
            fixed_export = fix_508_evs_in_export(fixed_export)
        fixed_packed = parse_and_pack_showdown_team(fixed_export, format_hint=clean_fmt)
        if "508 evs" in low_reasons or "ag" in clean_fmt or "anythinggoes" in clean_fmt:
            fixed_packed = fix_508_evs_in_packed(fixed_packed)

        explanation = f"Swapped invalid sets with verified legal {base_fmt.upper()} competitive roster."
        try:
            with open(cache_file, "w") as f:
                json.dump({
                    "bot_id": bot_id,
                    "format": battle_format,
                    "export_text": fixed_export,
                    "packed": fixed_packed
                }, f, indent=2)
        except Exception:
            pass

        return fixed_export, fixed_packed, explanation
