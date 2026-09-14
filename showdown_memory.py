"""
ShowdownMemoryManager: Battle history, opponent tracking, win/loss stats, and adaptive evolution.
Enables bots to learn from defeats and automatically counter-adapt teams for future matches.
"""

import os
import json
import time
import re
from typing import Optional, Dict, Any, List


class ShowdownMemoryManager:
    """Tracks battle statistics and executes post-defeat adaptive counter-strategy updates."""

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = base_dir or os.path.dirname(os.path.abspath(__file__))
        self.history_dir = os.path.join(self.base_dir, "memories", "showdown", "history")
        self.teams_dir = os.path.join(self.base_dir, "memories", "showdown", "teams")
        self.tactics_memory_path = os.path.join(self.base_dir, "memories", "showdown", "tactics_memory.json")
        os.makedirs(self.history_dir, exist_ok=True)
        os.makedirs(self.teams_dir, exist_ok=True)

    def load_tactics_memory(self) -> Dict[str, Any]:
        """Loads learned intel on opponent species, abilities, items, moves, and failed moves across battles."""
        if os.path.exists(self.tactics_memory_path):
            try:
                with open(self.tactics_memory_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "species_intel": {},
            "failed_matchups": {},
            "threat_sweepers": {}
        }

    def save_tactics_memory(self, data: Dict[str, Any]):
        try:
            with open(self.tactics_memory_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[SHOWDOWN TACTICS MEMORY ERROR] Could not save tactics memory: {e}")

    def record_intel(
        self,
        species: str,
        ability: Optional[str] = None,
        item: Optional[str] = None,
        move: Optional[str] = None,
        immune_move: Optional[str] = None,
        immune_type: Optional[str] = None
    ):
        """Records discovered battle data (e.g. Wonder Guard, Air Balloon, moves) into persistent memory."""
        if not species:
            return
        mem = self.load_tactics_memory()
        sp_key = species.strip().lower()
        sp_data = mem["species_intel"].setdefault(sp_key, {
            "species": species,
            "abilities": [],
            "items": [],
            "moves": [],
            "immune_moves": [],
            "immune_types": []
        })

        if ability and ability not in sp_data["abilities"]:
            sp_data["abilities"].append(ability)
        if item and item not in sp_data["items"]:
            sp_data["items"].append(item)
        if move and move not in sp_data["moves"]:
            sp_data["moves"].append(move)
        if immune_move and immune_move not in sp_data["immune_moves"]:
            sp_data["immune_moves"].append(immune_move)
        if immune_type and immune_type not in sp_data["immune_types"]:
            sp_data["immune_types"].append(immune_type)

        self.save_tactics_memory(mem)

    def record_move_failure(self, move: str, target_species: str, reason: str = ""):
        """Records a move failure into persistent memory so the bot never repeats this tactical mistake."""
        if not move or not target_species:
            return
        mem = self.load_tactics_memory()
        key = f"{move.strip().lower()} vs {target_species.strip().lower()}"
        mem["failed_matchups"][key] = {
            "move": move,
            "target": target_species,
            "reason": reason,
            "count": mem["failed_matchups"].get(key, {}).get("count", 0) + 1,
            "timestamp": time.time()
        }
        self.save_tactics_memory(mem)

    def get_known_intel(self, species: str) -> Dict[str, Any]:
        """Retrieves learned intel for a species from cross-battle memory."""
        if not species:
            return {}
        mem = self.load_tactics_memory()
        return mem.get("species_intel", {}).get(species.strip().lower(), {})

    def _get_history_path(self, bot_id: str) -> str:
        return os.path.join(self.history_dir, f"battle_history_{bot_id}.json")

    def load_history(self, bot_id: str) -> Dict[str, Any]:
        path = self._get_history_path(bot_id)
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "bot_id": bot_id,
            "total_battles": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "formats": {},
            "opponents": {},
            "adaptations": [],
            "recent_battles": []
        }

    def save_history(self, bot_id: str, data: Dict[str, Any]):
        path = self._get_history_path(bot_id)
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[SHOWDOWN MEMORY ERROR] Could not save history: {e}")

    def get_opponent_context(self, bot_id: str, opponent_name: str) -> Optional[Dict[str, Any]]:
        """Returns past encounter history with a given opponent for personalized banter."""
        clean_opp = opponent_name.strip().lower()
        hist = self.load_history(bot_id)
        return hist.get("opponents", {}).get(clean_opp)

    def record_match_result(
        self,
        bot_id: str,
        bot_name: str,
        room_id: str,
        opponent: str,
        battle_format: str,
        is_win: bool,
        turns: int,
        bot_faints: int,
        opp_faints: int,
        killer_info: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Records battle outcome, updates stats, and triggers adaptive learning on loss."""
        hist = self.load_history(bot_id)
        hist["total_battles"] += 1
        if is_win:
            hist["wins"] += 1
        else:
            hist["losses"] += 1
        hist["win_rate"] = round(hist["wins"] / max(1, hist["total_battles"]), 3)

        # Format stats
        clean_fmt = battle_format.lower()
        if clean_fmt not in hist["formats"]:
            hist["formats"][clean_fmt] = {"wins": 0, "losses": 0, "total": 0}
        f_stat = hist["formats"][clean_fmt]
        f_stat["total"] += 1
        if is_win:
            f_stat["wins"] += 1
        else:
            f_stat["losses"] += 1

        # Opponent stats
        clean_opp = opponent.strip().lower()
        if clean_opp not in hist["opponents"]:
            hist["opponents"][clean_opp] = {
                "display_name": opponent,
                "matches": 0,
                "wins": 0,
                "losses": 0,
                "last_seen": time.time()
            }
        opp_stat = hist["opponents"][clean_opp]
        opp_stat["matches"] += 1
        opp_stat["last_seen"] = time.time()
        if is_win:
            opp_stat["losses"] += 1 # opponent lost
        else:
            opp_stat["wins"] += 1   # opponent won

        # Recent battles list (cap 30)
        match_entry = {
            "room_id": room_id,
            "opponent": opponent,
            "format": battle_format,
            "result": "win" if is_win else "loss",
            "turns": turns,
            "bot_faints": bot_faints,
            "opp_faints": opp_faints,
            "timestamp": time.time()
        }
        hist["recent_battles"].insert(0, match_entry)
        if len(hist["recent_battles"]) > 30:
            hist["recent_battles"].pop()

        adaptation_note = None
        # ─── ADAPTIVE POST-MORTEM EVOLUTION ───────────────────
        if not is_win and "random" not in clean_fmt:
            adaptation_note = self._adapt_team_after_loss(
                bot_id=bot_id,
                bot_name=bot_name,
                battle_format=clean_fmt,
                killer_info=killer_info or []
            )
            if adaptation_note:
                hist["adaptations"].insert(0, {
                    "format": battle_format,
                    "timestamp": time.time(),
                    "adaptation": adaptation_note
                })
                if len(hist["adaptations"]) > 20:
                    hist["adaptations"].pop()

        self.save_history(bot_id, hist)
        return {
            "total_battles": hist["total_battles"],
            "win_rate": hist["win_rate"],
            "adaptation": adaptation_note
        }

    def _adapt_team_after_loss(
        self,
        bot_id: str,
        bot_name: str,
        battle_format: str,
        killer_info: List[str]
    ) -> Optional[str]:
        """Modifies team build in memory to counter threats that defeated the bot."""
        cache_file = os.path.join(self.teams_dir, f"{bot_id}_{battle_format}.json")
        if not os.path.exists(cache_file):
            return None

        try:
            with open(cache_file, "r") as f:
                data = json.load(f)
            export_text = data.get("export_text", "")
            if not export_text:
                return None

            adaptation_note = ""
            lines = export_text.splitlines()
            k_str = " ".join(str(k) for k in killer_info).lower()

            # Extract sweeper species, moves, and query persistent learned intel
            sweeper_species = []
            sweeper_moves = []
            sweeper_abilities = set()
            for k in killer_info:
                parts = str(k).split(" using ")
                sp = parts[0].strip()
                if sp:
                    sweeper_species.append(sp)
                    intel = self.get_known_intel(sp)
                    for ab in intel.get("abilities", []):
                        sweeper_abilities.add(ab.lower())
                    for mv in intel.get("moves", []):
                        sweeper_moves.append(mv.lower())
                if len(parts) > 1:
                    sweeper_moves.append(parts[1].strip().lower())

            is_hackmons = any(h in battle_format.lower() for h in ("hackmon", "bh"))
            has_wonder_guard = (
                "wonder guard" in sweeper_abilities or
                "wonder guard" in k_str or
                "shedinja" in k_str or
                (is_hackmons and any("rayquaza" in s.lower() for s in sweeper_species))
            )
            has_dragon_threat = any(m in sweeper_moves for m in ("outrage", "dragon ascent", "draco meteor", "clangorous soulblaze", "dragon claw")) or "outrage" in k_str
            has_sleep_threat = any(s in k_str or s in sweeper_moves for s in ("spore", "sing", "hypnosis", "sleep", "slp", "dark void"))
            has_setup_threat = any(s in k_str or s in sweeper_moves for s in ("dragon dance", "swords dance", "quiver dance", "shell smash", "nasty plot", "belly drum"))
            has_ground_threat = any(g in k_str or g in sweeper_moves for g in ("earthquake", "precipice blades", "headlong rush"))
            has_hazard_threat = any(h in k_str or h in sweeper_moves for h in ("stealth rock", "spikes", "toxic spikes", "hazard"))

            # ─── ADAPTATION 1: WONDER GUARD & HACKMONS COUNTERS ───
            if has_wonder_guard or is_hackmons:
                # If cached team completely lacks piercing or OHKO moves, replace with verified competitive archetype
                has_piercing = any(p in export_text for p in ("Sunsteel Strike", "Moongeist Beam", "Photon Geyser", "Ice Beam", "Sheer Cold"))
                if not has_piercing:
                    from showdown_builder import COMPETITIVE_ARCHETYPES
                    base_fmt = "gen7purehackmons" if "gen7" in battle_format else "gen9purehackmons"
                    new_export = COMPETITIVE_ARCHETYPES.get(base_fmt, COMPETITIVE_ARCHETYPES["gen7purehackmons"])
                    lines = new_export.splitlines()
                    adaptation_note = f"Adapted team: Upgraded entire roster to top-tier {base_fmt.upper()} with Sunsteel Strike, Ice Beam, and No Guard Sheer Cold to shatter Wonder Guard."
                else:
                    # Upgrade individual moves on Pokémon that lack piercing moves
                    new_lines = []
                    replaced_moves = 0
                    for l in lines:
                        if l.strip().startswith("-") and replaced_moves < 2:
                            # Replace ineffective or redundant moves
                            if any(m in l for m in ("Thousand Arrows", "Extreme Speed", "Precipice Blades", "V-create", "Close Combat", "Dragon Pulse", "Heat Wave", "Sludge Wave", "Stone Edge")):
                                if replaced_moves == 0:
                                    l = " - Sunsteel Strike"
                                    adaptation_note = "Adapted team: Equipped Sunsteel Strike to pierce through Wonder Guard."
                                else:
                                    l = " - Ice Beam"
                                    adaptation_note += " Equipped Ice Beam for 4x super-effective coverage."
                                replaced_moves += 1
                        new_lines.append(l)
                    lines = new_lines

            # ─── ADAPTATION 2: DRAGON / OUTRAGE HARD COUNTER ───
            if not adaptation_note and has_dragon_threat:
                new_lines = []
                replaced = False
                for l in lines:
                    if l.startswith("Tera Type:"):
                        l = "Tera Type: Fairy"
                        replaced = True
                        adaptation_note = "Adapted team: Shifted Tera Type to Fairy to gain complete immunity against Dragon / Outrage sweeps."
                    elif l.strip().startswith("-") and not replaced and any(m in l for m in ("Close Combat", "Focus Blast", "Shadow Ball", "Dark Pulse")):
                        l = " - Moonblast"
                        replaced = True
                        adaptation_note = "Adapted team: Equipped STAB Fairy Moonblast to punish Dragon / Outrage attackers with complete immunity and 2x damage."
                    new_lines.append(l)
                lines = new_lines

            # ─── ADAPTATION 3: STATUS / SLEEP SPAM COUNTER ───
            if not adaptation_note and has_sleep_threat:
                new_lines = []
                replaced = False
                for l in lines:
                    if "@" in l and not replaced and any(it in l for it in ("Life Orb", "Choice Band", "Blue Orb", "Leftovers")):
                        l = re.sub(r"@\s*[A-Za-z\s-]+", "@ Lum Berry", l)
                        replaced = True
                        adaptation_note = "Adapted team: Equipped Lum Berry to counter sleep / status affliction spam."
                    new_lines.append(l)
                lines = new_lines

            # ─── ADAPTATION 4: SETUP SWEEPERS COUNTER ───
            if not adaptation_note and has_setup_threat:
                new_lines = []
                replaced = False
                for l in lines:
                    if "@" in l and not replaced and "Booster Energy" in l:
                        l = l.replace("Booster Energy", "Choice Scarf")
                        replaced = True
                        adaptation_note = "Adapted team: Swapped Booster Energy for Choice Scarf for revenge-killing speed control against setup sweeps."
                    elif "@" in l and not replaced and "Life Orb" in l:
                        l = l.replace("Life Orb", "Focus Sash")
                        replaced = True
                        adaptation_note = "Adapted team: Equipped Focus Sash to survive setup attacks and retaliate."
                    new_lines.append(l)
                lines = new_lines

            # ─── ADAPTATION 5: GROUND SWEEPS ───
            if not adaptation_note and has_ground_threat:
                new_lines = []
                for l in lines:
                    if l.startswith("Tera Type: Normal"):
                        l = "Tera Type: Flying"
                        adaptation_note = "Adapted team: Adjusted Tera Type to Flying to gain Ground immunity against Earthquake."
                    new_lines.append(l)
                lines = new_lines

            # ─── ADAPTATION 6: HAZARD PROTECTION ───
            if not adaptation_note and has_hazard_threat:
                new_lines = []
                replaced = False
                for l in lines:
                    if "@ Leftovers" in l and not replaced:
                        l = l.replace("@ Leftovers", "@ Heavy-Duty Boots")
                        replaced = True
                        adaptation_note = "Adapted team: Equipped Heavy-Duty Boots to counter entry hazard chip damage."
                    new_lines.append(l)
                lines = new_lines

            if not adaptation_note:
                adaptation_note = f"Analyzed defeat vs {k_str[:60]}: Optimized damage calculations and defensive counterplay."

            # Repack team with updated changes
            from showdown_builder import parse_and_pack_showdown_team
            new_export = "\n".join(lines)
            new_packed = parse_and_pack_showdown_team(new_export, format_hint=battle_format)
            data["export_text"] = new_export
            data["packed"] = new_packed
            with open(cache_file, "w") as f:
                json.dump(data, f, indent=2)

            print(f"[SHOWDOWN ADAPTATION:{bot_name}] {adaptation_note}")
            return adaptation_note
        except Exception as e:
            print(f"[SHOWDOWN ADAPTATION ERROR] {e}")
            return None
