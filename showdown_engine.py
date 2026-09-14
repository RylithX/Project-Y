# -*- coding: utf-8 -*-
"""
showdown_engine.py - Autonomous Pokémon Showdown Agent & Account Manager (Hyper Intelligence)
Handles account registration, battle challenges, automated tactical play, event-driven commentary
(kills, deaths, crits, stall, wildcards, teampreview, victory), any-format team generation,
chat restriction mute-fallbacks to Discord DMs, and persistent adaptive memory learning.
"""

import asyncio
import json
import logging
import os
import random
import re
import time
import urllib.parse
import urllib.request
from typing import Dict, Any, Optional, Callable, List, Tuple

import aiohttp
import websockets

from showdown_builder import ShowdownTeamBuilder, parse_and_pack_showdown_team
from showdown_memory import ShowdownMemoryManager
from showdown_tactics import BattleTacticsEngine

logger = logging.getLogger("showdown_engine")

# ─── POKÉMON TYPE EFFECTIVENESS TABLE (GEN 6 - 9) ───
TYPE_CHART: Dict[str, Dict[str, float]] = {
    "normal":   {"rock": 0.5, "ghost": 0.0, "steel": 0.5},
    "fire":     {"fire": 0.5, "water": 0.5, "grass": 2.0, "ice": 2.0, "bug": 2.0, "rock": 0.5, "dragon": 0.5, "steel": 2.0},
    "water":    {"fire": 2.0, "water": 0.5, "grass": 0.5, "ground": 2.0, "rock": 2.0, "dragon": 0.5},
    "grass":    {"fire": 0.5, "water": 2.0, "grass": 0.5, "poison": 0.5, "ground": 2.0, "flying": 0.5, "bug": 0.5, "rock": 2.0, "dragon": 0.5, "steel": 0.5},
    "electric": {"water": 2.0, "grass": 0.5, "electric": 0.5, "ground": 0.0, "flying": 2.0, "dragon": 0.5},
    "ice":      {"fire": 0.5, "water": 0.5, "grass": 2.0, "ice": 0.5, "ground": 2.0, "flying": 2.0, "dragon": 2.0, "steel": 0.5},
    "fighting": {"normal": 2.0, "ice": 2.0, "poison": 0.5, "flying": 0.5, "psychic": 0.5, "bug": 0.5, "rock": 2.0, "ghost": 0.0, "dark": 2.0, "steel": 2.0, "fairy": 0.5},
    "poison":   {"grass": 2.0, "poison": 0.5, "ground": 0.5, "rock": 0.5, "ghost": 0.5, "steel": 0.0, "fairy": 2.0},
    "ground":   {"fire": 2.0, "grass": 0.5, "electric": 2.0, "poison": 2.0, "flying": 0.0, "bug": 0.5, "rock": 2.0, "steel": 2.0},
    "flying":   {"grass": 2.0, "electric": 0.5, "fighting": 2.0, "bug": 2.0, "rock": 0.5, "steel": 0.5},
    "psychic":  {"fighting": 2.0, "poison": 2.0, "psychic": 0.5, "dark": 0.0, "steel": 0.5},
    "bug":      {"fire": 0.5, "grass": 2.0, "fighting": 0.5, "poison": 0.5, "flying": 0.5, "psychic": 2.0, "ghost": 0.5, "dark": 2.0, "steel": 0.5, "fairy": 0.5},
    "rock":     {"fire": 2.0, "ice": 2.0, "fighting": 0.5, "ground": 0.5, "flying": 2.0, "bug": 2.0, "steel": 0.5},
    "ghost":    {"normal": 0.0, "psychic": 2.0, "ghost": 2.0, "dark": 0.5},
    "dragon":   {"dragon": 2.0, "steel": 0.5, "fairy": 0.0},
    "steel":    {"fire": 0.5, "water": 0.5, "electric": 0.5, "ice": 2.0, "rock": 2.0, "steel": 0.5, "fairy": 2.0},
    "dark":     {"fighting": 0.5, "psychic": 2.0, "ghost": 2.0, "dark": 0.5, "fairy": 0.5},
    "fairy":    {"fire": 0.5, "fighting": 2.0, "poison": 0.5, "dragon": 2.0, "dark": 2.0, "steel": 0.5}
}

def get_type_effectiveness(attack_type: str, defend_types: List[str]) -> float:
    """Calculates move effectiveness multiplier against target Pokémon types."""
    atk = attack_type.lower().strip()
    mult = 1.0
    for def_t in defend_types:
        d = def_t.lower().strip()
        if atk in TYPE_CHART and d in TYPE_CHART[atk]:
            mult *= TYPE_CHART[atk][d]
    return mult


class PokemonShowdownClient:
    """
    Autonomous Hyper-Intelligent client for a single bot persona on Pokémon Showdown.
    Connects to Showdown via WebSocket, logs in with registered accounts, auto-accepts challenges,
    builds format-compliant teams on-the-fly, executes event-driven banter, and adapts from losses.
    """

    def __init__(
        self,
        bot_id: str,
        bot_name: str,
        config: Dict[str, Any],
        on_event_cb: Optional[Callable] = None,
        save_config_cb: Optional[Callable] = None,
        llm_generate_cb: Optional[Callable] = None
    ):
        self.bot_id = bot_id
        self.bot_name = bot_name
        self.config = config
        self.on_event_cb = on_event_cb
        self.save_config_cb = save_config_cb
        self.llm_generate_cb = llm_generate_cb

        clean_name = re.sub(r'[^a-zA-Z0-9]', '', bot_name) or "Bot"
        self.username = config.get("showdown_username") or f"{clean_name}AI"
        self.password = config.get("showdown_password") or ""
        self.default_format = config.get("showdown_format") or "gen9randombattle"
        self.personality = config.get("showdown_personality") or f"You are {bot_name}, a clever and spirited Pokémon trainer."
        self.autonomous = config.get("showdown_autonomous", True)
        self.auto_accept = config.get("showdown_auto_accept", True)
        self.channel_id = config.get("showdown_channel")
        self.initiator_user_id = config.get("showdown_initiator_user_id")

        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.is_connected = False
        self.is_registered = False
        self.running = False
        self.chat_muted = False
        self.active_battles: Dict[str, Dict[str, Any]] = {}
        self._task: Optional[asyncio.Task] = None
        self.recent_logs: List[str] = []

        # Rejection recovery tracking
        self._last_format = self.default_format
        self._last_challenger = ""
        self._last_target = ""
        self._last_action = ""
        self._last_packed_team = ""
        self._rejection_retry_count = 0

        # Hyper Intelligence subsystems
        self.team_builder = ShowdownTeamBuilder()
        self.memory_manager = ShowdownMemoryManager()
        self.tactics_engine = BattleTacticsEngine()

    def log(self, msg: str):
        entry = f"[SHOWDOWN:{self.bot_name}] {msg}"
        print(entry)
        self.recent_logs.append(msg)
        if len(self.recent_logs) > 50:
            self.recent_logs.pop(0)

    async def notify_discord(self, message_text: str, embed_data: Optional[Dict[str, Any]] = None, is_battle_chat: bool = False):
        """Sends real-time updates or routed battle chat to Discord."""
        if self.on_event_cb:
            try:
                if asyncio.iscoroutinefunction(self.on_event_cb):
                    await self.on_event_cb(self, message_text, embed_data, is_battle_chat)
                else:
                    self.on_event_cb(self, message_text, embed_data, is_battle_chat)
            except TypeError:
                try:
                    if asyncio.iscoroutinefunction(self.on_event_cb):
                        await self.on_event_cb(self, message_text, embed_data)
                    else:
                        self.on_event_cb(self, message_text, embed_data)
                except Exception as e:
                    self.log(f"Discord notification note: {e}")
            except Exception as e:
                self.log(f"Discord notification note: {e}")

    async def send_room_chat(self, room: str, text: str):
        """Sends chat message inside a battle room or falls back to Discord DM if chat is muted."""
        if not text:
            return
        if self.chat_muted:
            b_info = self.active_battles.get(room, {})
            opp = b_info.get("opponent", "Opponent")
            await self.notify_discord(f"💬 **[{self.bot_name} vs {opp}]**: {text}", is_battle_chat=True)
            return

        if self.ws and self.is_connected:
            await self.send_raw(f"{room}|{text}")

    async def send_raw(self, msg: str):
        """Sends raw command string to Showdown WebSocket."""
        if self.ws and self.is_connected:
            try:
                await self.ws.send(msg)
            except Exception as e:
                self.log(f"Send error: {e}")

    async def start(self):
        """Starts the Showdown client background loop."""
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self):
        """Stops the client and closes WebSocket."""
        self.running = False
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
        if self._task and not self._task.done():
            self._task.cancel()
        self.is_connected = False
        self.log("Client stopped.")

    async def _run_loop(self):
        """Persistent connection loop with automatic reconnect."""
        uri = "wss://sim3.psim.us/showdown/websocket"
        while self.running:
            try:
                self.log(f"Connecting to Pokémon Showdown ({uri})...")
                async with websockets.connect(uri, ping_interval=20, ping_timeout=20) as ws:
                    self.ws = ws
                    self.is_connected = True
                    self.log("WebSocket connected successfully.")
                    while self.running:
                        msg = await ws.recv()
                        await self._process_message(msg)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log(f"WebSocket error: {e}. Reconnecting in 5s...")
                self.is_connected = False
                await asyncio.sleep(5)

    async def _process_message(self, raw_msg: str):
        """Parses multi-line Showdown protocol messages."""
        lines = raw_msg.splitlines()
        room = ""
        for line in lines:
            if line.startswith(">"):
                room = line[1:].strip()
                continue

            if not line.startswith("|"):
                continue

            parts = line.split("|")
            cmd = parts[1] if len(parts) > 1 else ""

            # ─── CORE AUTH & SYSTEM COMMANDS ───
            if cmd == "challstr":
                challstr = "|".join(parts[2:])
                await self._handle_challstr(challstr)

            elif cmd == "updateuser":
                uname = parts[2].strip() if len(parts) > 2 else ""
                named = parts[3] if len(parts) > 3 else "0"
                if named == "1":
                    self.log(f"Authenticated as [{uname}]! Ready for battles.")
                    self.username = uname
                    self.is_connected = True
                    await self.send_raw("|/unblockchallenges")
                    await self.send_raw("|/unblockpms")
                    avatar_id = self.config.get("showdown_avatar") or ("cynthia" if "yuna" in self.bot_name.lower() else "red")
                    await self.send_raw(f"|/avatar {avatar_id}")
                    await self.send_raw("|/utm null")

            elif cmd == "pm":
                sender_raw = parts[2] if len(parts) > 2 else ""
                receiver_raw = parts[3] if len(parts) > 3 else ""
                msg_content = "|".join(parts[4:]).strip() if len(parts) > 4 else ""
                await self._handle_pm(sender_raw, msg_content)

            elif cmd == "updatechallenges":
                try:
                    payload = json.loads("|".join(parts[2:]))
                    await self._handle_updatechallenges(payload)
                except Exception as e:
                    self.log(f"Failed to parse updatechallenges: {e}")

            elif cmd == "nametaken":
                taken_name = parts[2].strip() if len(parts) > 2 else ""
                reason = parts[3].strip() if len(parts) > 3 else "Name already registered or taken"
                self.log(f"⚠️ Showdown handle '{taken_name}' unavailable ({reason}). Claiming unique alternate handle...")
                clean_base = re.sub(r'[^a-zA-Z0-9]', '', self.bot_name) or "Trainer"
                fallback_name = f"{clean_base}AI{random.randint(10, 999)}"
                self.username = fallback_name
                last_ch = getattr(self, "_last_challstr", None)
                if last_ch:
                    assertion = await self._api_getassertion(fallback_name, last_ch)
                    if assertion:
                        await self.send_raw(f"|/trn {fallback_name},0,{assertion}")

            elif cmd in ("popup", "error"):
                pop_msg = "|".join(parts[2:]).strip()
                self.log(f"Showdown notice ({cmd}): {pop_msg}")
                low_pop = pop_msg.lower()

                # 1. Team rejection detection & dynamic self-healing
                if any(k in low_pop for k in ("rejected", "not valid", "exactly 508 evs", "is banned", "can't learn", "illegal", "does not restrict you to 510 evs")):
                    self.log("⚠️ Team rejection detected! Triggering dynamic auto-fix and recovery...")
                    asyncio.create_task(self._handle_team_rejection(pop_msg))
                    return

                # 2. Provider IP spam or mute restriction
                elif any(k in low_pop for k in ("can't speak", "cant speak", "spam from your internet provider", "must be registered to send", "muted")):
                    if not self.chat_muted:
                        self.chat_muted = True
                        self.log("⚠️ Chat muted by Showdown server policy. Diverting dialogue to Discord DM!")
                        await self.notify_discord(
                            f"⚠️ **[Showdown] Chat Muted:** Showdown restricted direct chatting (`{pop_msg}`).\n"
                            f"➡️ **All in-character battle reactions & chat will now be delivered directly to your Discord DM!**",
                            is_battle_chat=True
                        )
                elif any(k in low_pop for k in ("challenge", "battle", "team", "error", "ban")):
                    await self.notify_discord(f"⚠️ **[Showdown] Notice:** {pop_msg}")

            elif cmd in ("c", "c:"):
                if cmd == "c:":
                    c_sender = parts[3].strip().lstrip(" ~+@%*&#!★") if len(parts) > 3 else ""
                    c_msg = "|".join(parts[4:]).strip() if len(parts) > 4 else ""
                else:
                    c_sender = parts[2].strip().lstrip(" ~+@%*&#!★") if len(parts) > 2 else ""
                    c_msg = "|".join(parts[3:]).strip() if len(parts) > 3 else ""
                if room in self.active_battles and c_sender.lower() != self.username.lower():
                    await self._handle_battle_chat(room, c_sender, c_msg)

            # ─── BATTLE ROOM EVENTS & STREAM PARSING ───
            elif room.startswith("battle-"):
                await self._process_battle_event(room, cmd, parts, line)

    async def _process_battle_event(self, room: str, cmd: str, parts: List[str], line: str):
        """Processes granular battle stream events for hyper-intelligent tactical banter & learning."""
        if cmd == "init" and len(parts) > 2 and parts[2] == "battle":
            self.log(f"Joined battle room: {room}")
            fmt_from_room = room.split("-")[1].lower() if "-" in room else self.default_format
            self.active_battles[room] = {
                "room_id": room,
                "opponent": "Opponent",
                "format": fmt_from_room,
                "turn": 0,
                "player_id": None,
                "my_side": None,
                "opp_side": None,
                "my_active": "",
                "opp_active": "",
                "my_hp_pct": 100.0,
                "opp_hp_pct": 100.0,
                "my_status": "",
                "opp_status": "",
                "my_statuses": {},
                "opp_statuses": {},
                "my_boosts": {},
                "opp_boosts": {},
                "my_faints": 0,
                "opp_faints": 0,
                "stall_count": 0,
                "last_speech_time": 0.0,
                "last_speech_turn": -1,
                "killer_moves": [],
                "opp_team": [],
                "opp_ability": "",
                "opp_item": "",
                "opp_substitute": False,
                "terrain": "",
                "weather": "",
                "failed_moves": {},
                "opp_types": [],
                "opp_active_nick": "",
                "my_active_nick": "",
                "my_types": [],
                "hazards_up": False,
                "immune_moves": {},
                "immune_types": {},
                "last_move_used": "",
                "opp_last_move": ""
            }
            # Start battle greeting
            await self._trigger_battle_banter(room, "start")

        b_info = self.active_battles.get(room)
        if not b_info:
            return

        if cmd == "player":
            pid = parts[2] if len(parts) > 2 else ""
            pname = parts[3] if len(parts) > 3 else ""
            if pname.lower() == self.username.lower():
                b_info["player_id"] = pid
                b_info["my_side"] = pid
                b_info["opp_side"] = "p2" if pid == "p1" else "p1"
            elif pname:
                b_info["opponent"] = pname

        elif cmd == "tier":
            if len(parts) > 2:
                clean_tier = re.sub(r"[^a-zA-Z0-9_-]", "", parts[2].lower())
                b_info["format"] = clean_tier
                self.log(f"[{room}] Confirmed battle tier: {clean_tier}")

        elif cmd == "teampreview":
            await self._trigger_battle_banter(room, "teampreview")

        elif cmd == "poke":
            # |poke|p1|Garchomp, M|...
            p_side = parts[2] if len(parts) > 2 else ""
            p_mon = parts[3].split(",")[0].strip() if len(parts) > 3 else ""
            if p_side == b_info.get("opp_side") and p_mon:
                b_info["opp_team"].append(p_mon)

        elif cmd in ("switch", "drag"):
            # |switch|p1a: Dragapult|Dragapult, M|100/100
            # |switch|p2a: Shadow|Misdreavus, L50, F|100/100 slp
            if len(parts) > 3:
                sw_side = parts[2][:2]
                sw_nick = parts[2].split(":", 1)[-1].strip()
                sw_spec = parts[3].split(",")[0].strip()
                hp_str = parts[4] if len(parts) > 4 else "100/100"
                hp_pct = self._parse_hp_percent(hp_str)

                # Parse non-volatile status (e.g. "100/100 slp")
                cond_tokens = hp_str.split()
                st_code = cond_tokens[1].lower() if len(cond_tokens) > 1 and cond_tokens[1].lower() in ("slp", "brn", "par", "tox", "psn", "frz") else ""

                if sw_side == b_info.get("my_side"):
                    b_info["my_active"] = sw_spec
                    b_info["my_active_nick"] = sw_nick
                    b_info["my_hp_pct"] = hp_pct
                    b_info["my_status"] = st_code
                    b_info["my_boosts"] = {}
                    b_info["my_types"] = self.tactics_engine.get_pokemon_types(sw_spec)
                else:
                    b_info["opp_active"] = sw_spec
                    b_info["opp_active_nick"] = sw_nick
                    b_info["opp_hp_pct"] = hp_pct
                    b_info["opp_status"] = st_code
                    b_info.setdefault("opp_statuses", {})[sw_nick] = st_code
                    b_info.setdefault("opp_statuses", {})[sw_spec] = st_code
                    b_info["opp_boosts"] = {}
                    b_info["opp_substitute"] = False
                    b_info["stall_count"] = 0
                    b_info["opp_types"] = self.tactics_engine.get_pokemon_types(sw_spec)

                    # Consult cross-battle learned memory first!
                    learned = self.memory_manager.get_known_intel(sw_spec)
                    if learned.get("abilities"):
                        b_info["opp_ability"] = learned["abilities"][0]
                    else:
                        known_ab = self.tactics_engine.get_known_abilities(sw_spec)
                        if len(known_ab) == 1:
                            b_info["opp_ability"] = known_ab[0]
                        else:
                            b_info["opp_ability"] = "Wonder Guard" if "shedinja" in sw_spec.lower() else ""

                    if learned.get("items") and not b_info.get("opp_item"):
                        b_info["opp_item"] = learned["items"][0]

                    self.log(f"[{room}] Opponent sent out {sw_spec} ({'/'.join(b_info['opp_types'])})" + (f" [{b_info['opp_ability']}]" if b_info['opp_ability'] else "") + (f" Status: {st_code}" if st_code else ""))

        elif cmd in ("-formechange", "detailschange"):
            # |-formechange|p2a: Aegislash|Aegislash-Blade|...
            if len(parts) > 3:
                f_side = parts[2][:2]
                f_spec = parts[3].split(",")[0].strip()
                if f_side == b_info.get("opp_side"):
                    b_info["opp_active"] = f_spec
                    b_info["opp_types"] = self.tactics_engine.get_pokemon_types(f_spec)
                    self.log(f"[{room}] Opponent changed forme to {f_spec} ({'/'.join(b_info['opp_types'])})")
                elif f_side == b_info.get("my_side"):
                    b_info["my_active"] = f_spec
                    b_info["my_types"] = self.tactics_engine.get_pokemon_types(f_spec)

        elif cmd == "faint":
            # |faint|p1a: Pikachu
            if len(parts) > 2:
                f_side = parts[2][:2]
                f_mon = parts[2].split(":", 1)[-1].strip()
                if f_side == b_info.get("opp_side"):
                    b_info["opp_faints"] = b_info.get("opp_faints", 0) + 1
                    await self._trigger_battle_banter(room, "kill", mon=f_mon)
                elif f_side == b_info.get("my_side"):
                    b_info["my_faints"] = b_info.get("my_faints", 0) + 1
                    # Record killer info for post-mortem adaptation!
                    killer_mon = b_info.get("opp_active", "Opponent")
                    killer_move = b_info.get("opp_last_move", "Unknown")
                    killer_entry = f"{killer_mon} using {killer_move}"
                    b_info["killer_moves"].append(killer_entry)
                    self.log(f"[{room}] 💀 {f_mon} fainted to {killer_entry}!")
                    await self._trigger_battle_banter(room, "death", mon=f_mon)

        elif cmd == "-damage":
            # |-damage|p2a: Ting-Lu|30/100
            if len(parts) > 3:
                d_side = parts[2][:2]
                d_mon = parts[2].split(":", 1)[-1].strip()
                new_hp = self._parse_hp_percent(parts[3])
                old_hp = b_info.get("opp_hp_pct", 100.0) if d_side == b_info.get("opp_side") else b_info.get("my_hp_pct", 100.0)
                delta = old_hp - new_hp
                if d_side == b_info.get("opp_side"):
                    b_info["opp_hp_pct"] = new_hp
                    if delta >= 45.0:
                        await self._trigger_battle_banter(room, "crit_dealt", mon=d_mon)
                else:
                    b_info["my_hp_pct"] = new_hp
                    if delta >= 45.0:
                        await self._trigger_battle_banter(room, "crit_taken", mon=d_mon)

        elif cmd == "-crit":
            # |-crit|p2a: Ting-Lu
            if len(parts) > 2:
                c_side = parts[2][:2]
                c_mon = parts[2].split(":", 1)[-1].strip()
                if c_side == b_info.get("opp_side"):
                    await self._trigger_battle_banter(room, "crit_dealt", mon=c_mon)
                else:
                    await self._trigger_battle_banter(room, "crit_taken", mon=c_mon)

        elif cmd == "-status":
            # |-status|p2a: Gengar|slp
            if len(parts) > 3:
                st_side = parts[2][:2]
                st_mon = parts[2].split(":", 1)[-1].strip()
                st_val = parts[3].strip().lower()
                if st_side == b_info.get("opp_side"):
                    b_info["opp_status"] = st_val
                    b_info.setdefault("opp_statuses", {})[st_mon] = st_val
                    b_info.setdefault("opp_statuses", {})[b_info.get("opp_active", "")] = st_val
                    self.log(f"[{room}] 💤 Opponent {st_mon} afflicted with {st_val.upper()}! Anti-repetition active.")
                else:
                    b_info["my_status"] = st_val

        elif cmd == "-curestatus":
            # |-curestatus|p2a: Gengar|slp
            if len(parts) > 2:
                st_side = parts[2][:2]
                st_mon = parts[2].split(":", 1)[-1].strip()
                if st_side == b_info.get("opp_side"):
                    b_info["opp_status"] = ""
                    b_info.setdefault("opp_statuses", {})[st_mon] = ""
                    self.log(f"[{room}] Opponent {st_mon} status cured.")
                else:
                    b_info["my_status"] = ""

        elif cmd == "-fail":
            # |-fail|p1a: Jigglypuff|slp
            # |-fail|p1a: Garchomp
            if len(parts) > 2:
                f_side = parts[2][:2]
                if f_side == b_info.get("my_side"):
                    last_m = b_info.get("last_move_used", "")
                    opp_mon = b_info.get("opp_active", "")
                    opp_nick = b_info.get("opp_active_nick", "")
                    if last_m:
                        for tname in (opp_mon, opp_nick):
                            if tname:
                                b_info.setdefault("failed_moves", {}).setdefault(tname, set()).add(last_m.lower())
                        self.memory_manager.record_move_failure(last_m, opp_mon, "Failed in combat")
                        self.log(f"[{room}] ❌ Tactical Guard: Move '{last_m}' FAILED vs {opp_mon}! Added to fail blacklist so bot won't repeat mistake.")

        elif cmd == "-activate":
            # |-activate|p2a: Protect
            act_text = "|".join(parts[2:])
            if any(m in act_text for m in ("Protect", "Detect", "Spiky Shield", "Baneful Bunker", "Silk Trap")):
                b_info["stall_count"] = b_info.get("stall_count", 0) + 1
                if b_info["stall_count"] >= 2:
                    await self._trigger_battle_banter(room, "stall")
            elif "Substitute" in act_text:
                if parts[2][:2] == b_info.get("opp_side"):
                    b_info["opp_substitute"] = True
                    self.log(f"[{room}] Opponent created a Substitute!")

        elif cmd == "-end":
            # |-end|p2a: Substitute
            if len(parts) > 3 and "Substitute" in parts[3]:
                if parts[2][:2] == b_info.get("opp_side"):
                    b_info["opp_substitute"] = False

        elif cmd == "-terastallize":
            # |-terastallize|p2a: Kingambit|Flying
            if len(parts) > 3:
                t_side = parts[2][:2]
                t_mon = parts[2].split(":", 1)[-1].strip()
                t_type = parts[3].strip().capitalize()
                if t_side == b_info.get("opp_side"):
                    b_info["opp_types"] = [t_type]
                    self.log(f"[{room}] ⚡ Opponent Terastallized into {t_type}! Defense matrix updated.")
                    await self._trigger_battle_banter(room, "wildcard_opp", mon=t_mon, extra=t_type)
                else:
                    b_info["my_types"] = [t_type]
                    await self._trigger_battle_banter(room, "wildcard_my", mon=t_mon, extra=t_type)

        elif cmd in ("-boost", "-unboost"):
            # |-boost|p2a: Roaring Moon|atk|2
            if len(parts) > 4:
                b_side = parts[2][:2]
                stat_name = parts[3].strip().lower()
                try:
                    b_amt = int(parts[4])
                    if cmd == "-unboost":
                        b_amt = -b_amt
                    target_dict = b_info.setdefault("my_boosts" if b_side == b_info.get("my_side") else "opp_boosts", {})
                    target_dict[stat_name] = max(-6, min(6, target_dict.get(stat_name, 0) + b_amt))

                    if b_amt >= 2 and b_side == b_info.get("opp_side"):
                        await self._trigger_battle_banter(room, "wildcard_boost", mon=parts[2].split(":")[-1].strip())
                except ValueError:
                    pass

        elif cmd in ("-clearboost", "-clearallboost"):
            b_info["my_boosts"] = {}
            b_info["opp_boosts"] = {}

        elif cmd == "-fieldstart":
            # |-fieldstart|move: Electric Terrain
            f_text = "|".join(parts[2:]).lower()
            if "terrain" in f_text:
                b_info["terrain"] = f_text.split(":")[-1].replace(" ", "").strip()
                self.log(f"[{room}] 🌐 Active terrain: {b_info['terrain']}")

        elif cmd == "-fieldend":
            b_info["terrain"] = ""

        elif cmd == "-weather":
            w_val = parts[2].strip() if len(parts) > 2 else "none"
            b_info["weather"] = "" if w_val.lower() == "none" else w_val

        elif cmd == "-item":
            # |-item|p2a: Gengar|Air Balloon
            if len(parts) > 3:
                i_side = parts[2][:2]
                it_name = parts[3].strip()
                if i_side == b_info.get("opp_side"):
                    b_info["opp_item"] = it_name
                    opp_mon = b_info.get("opp_active", "")
                    if opp_mon:
                        self.memory_manager.record_intel(opp_mon, item=it_name)
                    self.log(f"[{room}] 🎈 Opponent item revealed: {it_name} on {opp_mon}!")

        elif cmd == "-enditem":
            if len(parts) > 2 and parts[2][:2] == b_info.get("opp_side"):
                b_info["opp_item"] = ""

        elif cmd == "move":
            # |move|p1a: Rayquaza|Earthquake|p2a: Gengar
            if len(parts) > 3:
                m_side = parts[2][:2]
                m_name = parts[3].strip()
                if m_side == b_info.get("my_side"):
                    b_info["last_move_used"] = m_name
                else:
                    b_info["opp_last_move"] = m_name
                    opp_mon = b_info.get("opp_active", "")
                    if opp_mon:
                        self.memory_manager.record_intel(opp_mon, move=m_name)

        elif cmd == "-ability":
            # |-ability|p2a: Gengar|Wonder Guard
            if len(parts) > 3:
                ab_side = parts[2][:2]
                ab_name = parts[3].strip()
                if ab_side == b_info.get("opp_side"):
                    b_info["opp_ability"] = ab_name
                    opp_mon = b_info.get("opp_active", "")
                    if opp_mon:
                        self.memory_manager.record_intel(opp_mon, ability=ab_name)
                    self.log(f"[{room}] 🔍 Identified opponent ability: {ab_name}!")

        elif cmd == "-immune":
            # |-immune|p2a: Gengar|[from] ability: Wonder Guard
            if len(parts) > 2:
                im_side = parts[2][:2]
                if im_side == b_info.get("opp_side"):
                    last_m = b_info.get("last_move_used", "")
                    opp_mon = b_info.get("opp_active", "")
                    opp_nick = b_info.get("opp_active_nick", "")
                    minfo = self.tactics_engine.get_move_info(last_m)
                    m_type = minfo.get("type", "")
                    for target_name in (opp_mon, opp_nick):
                        if target_name:
                            b_info.setdefault("immune_moves", {}).setdefault(target_name, set()).add(last_m.lower())
                            if m_type:
                                b_info.setdefault("immune_types", {}).setdefault(target_name, set()).add(m_type)
                    if opp_mon and last_m:
                        self.memory_manager.record_intel(opp_mon, immune_move=last_m.lower(), immune_type=m_type)
                    self.log(f"[{room}] ⚠️ Blacklisted move '{last_m}' AND {m_type}-type attacks vs {opp_mon} (0x immune)!")
                    if "[from] ability:" in line:
                        ab_name = line.split("[from] ability:")[-1].split("|")[0].strip()
                        if ab_name:
                            b_info["opp_ability"] = ab_name
                            if opp_mon:
                                self.memory_manager.record_intel(opp_mon, ability=ab_name)
                            self.log(f"[{room}] 🛡️ Discovered opponent ability: {ab_name}!")
                    elif "wonder guard" in line.lower():
                        b_info["opp_ability"] = "Wonder Guard"
                        if opp_mon:
                            self.memory_manager.record_intel(opp_mon, ability="Wonder Guard")
                        self.log(f"[{room}] 🛡️ Opponent has Wonder Guard! Filtering non-super-effective moves!")

        elif cmd == "-sidestart":
            # |-sidestart|p2: Opponent|move: Stealth Rock
            if len(parts) > 3:
                s_side = parts[2][:2]
                if s_side == b_info.get("opp_side"):
                    b_info["hazards_up"] = True

        elif cmd == "request":
            raw_json = "|".join(parts[2:]).strip()
            if raw_json:
                try:
                    req_data = json.loads(raw_json)
                    await self._handle_battle_request(room, req_data)
                except Exception as e:
                    self.log(f"Error handling battle request in {room}: {e}")

        elif cmd == "win":
            winner = parts[2].strip() if len(parts) > 2 else ""
            b_info = self.active_battles.pop(room, {})
            is_win = (winner.lower() == self.username.lower())
            opp = b_info.get("opponent", "Opponent")
            result_msg = "VICTORY 🏆" if is_win else "DEFEAT 💔"

            # Post-match speech
            await self._trigger_battle_banter(room, "victory" if is_win else "defeat")
            self.log(f"Battle against {opp} finished! Result: {result_msg}")

            # Record match in persistent memory & run adaptive evolution
            rec_result = self.memory_manager.record_match_result(
                bot_id=self.bot_id,
                bot_name=self.bot_name,
                room_id=room,
                opponent=opp,
                battle_format=b_info.get("format", self.default_format),
                is_win=is_win,
                turns=b_info.get("turn", 0),
                bot_faints=b_info.get("my_faints", 0),
                opp_faints=b_info.get("opp_faints", 0),
                killer_info=b_info.get("killer_moves", [])
            )

            await self.send_raw(f"|/leave {room}")
            battle_url = f"https://play.pokemonshowdown.com/{room}"
            disc_msg = (
                f"⚔️ **[Showdown]** Battle against **{opp}** concluded!\n"
                f"• Result: **{result_msg}** ({self.bot_name})\n"
                f"• Record: `{rec_result['win_rate']*100:.1f}% win-rate` ({rec_result['total_battles']} matches)\n"
                f"• Replay / Watch: {battle_url}"
            )
            if rec_result.get("adaptation"):
                disc_msg += f"\n🧠 **Adaptive Improvement:** {rec_result['adaptation']}"
            await self.notify_discord(disc_msg)

    def _parse_hp_percent(self, hp_str: str) -> float:
        """Parses '50/100' or '120/240' into percentage float."""
        if not hp_str or "fnt" in hp_str:
            return 0.0
        cleaned = hp_str.split()[0]
        if "/" in cleaned:
            parts = cleaned.split("/")
            try:
                cur = float(parts[0])
                total = float(parts[1])
                return (cur / max(1.0, total)) * 100.0
            except ValueError:
                pass
        return 100.0

    async def _trigger_battle_banter(self, room: str, event_type: str, **kwargs):
        """Generates contextual in-character commentary and dispatches it with spam protection."""
        b_info = self.active_battles.get(room)
        now = time.time()
        cur_turn = b_info.get("turn", 0) if b_info else 0

        # Anti-spam cooldown (except game-ending victory/defeat)
        if event_type not in ("victory", "defeat", "start"):
            if b_info:
                last_t = b_info.get("last_speech_time", 0.0)
                last_turn = b_info.get("last_speech_turn", -1)
                if (now - last_t < 4.0) or (cur_turn == last_turn):
                    return
                b_info["last_speech_time"] = now
                b_info["last_speech_turn"] = cur_turn

        comment = self._get_in_character_comment(event_type, kwargs)
        if comment:
            await self.send_room_chat(room, comment)

    def _get_in_character_comment(self, trigger: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Returns rich personality-driven dialogue tailored to specific in-battle events."""
        ctx = context or {}
        mon = ctx.get("mon", "Pokémon")
        extra = ctx.get("extra", "")
        name_l = self.bot_name.lower()

        # ─── TRAFALGAR LAW / ANALYTICAL TACTICIAN ───
        if "law" in name_l:
            quotes = {
                "start": "The operation begins. Let's see if your deductions hold up under pressure.",
                "teampreview": "Analyzing opponent lineup. Weaknesses cataloged; initiating surgical dissection.",
                "kill": f"Target eliminated. {mon} has been removed from the board.",
                "death": f"Tch... a calculated sacrifice. The trajectory of this battle remains within parameters.",
                "crit_dealt": "Critical incision confirmed. Right through your defensive line.",
                "crit_taken": "Anomalous damage spike detected. Structural defenses re-orienting immediately.",
                "stall": "Stalling behind Protect? Delaying the inevitable will not alter your probability of defeat.",
                "wildcard_opp": f"Terastallization observed: {mon} shifts to {extra}. A dynamic variable, yet manageable.",
                "wildcard_my": f"Room. Shambles! Unleashing {extra} Terastallization to conclude this round.",
                "wildcard_boost": f"Setup boost recorded on {mon}. Priority target flagged for immediate neutralisation.",
                "victory": "Checkmate. The outcome was mathematically determined from turn three.",
                "defeat": "Fascinating tactical execution. I have cataloged your patterns for our next encounter."
            }
        # ─── BRILIANCE / COSMIC CELESTIAL MYSTIC ───
        elif "briliance" in name_l:
            quotes = {
                "start": "The constellations align above our arena. Let the dance of stars commence. ࣪ ִֶָ☾",
                "teampreview": "Your celestial lineup radiates power... let us see which stars burn brightest tonight. ✨",
                "kill": f"Returned to stardust. {mon} fought with noble grace, yet the eclipse advances.",
                "death": f"Fallen into the lunar shadow... your light guided us well. The next star ascends! ☾",
                "crit_dealt": "A supernova strike! The fabric of their defense has shattered! 💥",
                "crit_taken": "A heavy cosmic tremor... the void shakes, but our resolve remains luminous.",
                "stall": "Barriers of light and shadow... you seek sanctuary, yet the tides of fate flow ever onward.",
                "wildcard_opp": f"A stellar metamorphosis! {mon} embraces the {extra} radiance.",
                "wildcard_my": f"By the ancient cosmos! Shining with {extra} brilliance! ࣪ ִֶָ☾",
                "wildcard_boost": f"The aura of {mon} surges like a rising comet! A formidable challenge.",
                "victory": "The heavens rejoice. A magnificent duel written among the constellations. ࣪ ִֶָ☾ 🏆",
                "defeat": "The stars dim, and your dawn arrives. A truly breathtaking spectacle... until our orbits cross again. ✨"
            }
        # ─── YUNA / ENERGETIC SPIRITED CHAMPION ───
        else:
            quotes = {
                "start": "*smiles brightly* Eyes on the arena! Let's show them what real bond and strategy look like! ⭐",
                "teampreview": "Ooh, that's an awesome roster! I see some serious threats, but my team is ready for anything! ✨",
                "kill": f"BOOM! Down goes {mon}! Beautiful hit, team—keep the momentum going! ⚡",
                "death": f"Ugh, no! You were incredible out there, take a good rest... I've got your back! Rematch starts now!",
                "crit_dealt": "Direct hit right in the weak spot! That had to sting! 💥",
                "crit_taken": "Whoa, heavy impact! Ouch... you definitely weren't playing around with that one!",
                "stall": "Protecting again? You can hide behind shields all you want, but you'll have to face me eventually! 🛡️",
                "wildcard_opp": f"Whoa, Terastallization! {mon} turning into {extra}?! Let's see your true colors! 🌟",
                "wildcard_my": f"Time to crank up the heat! Terastallizing into {extra}! Let's go all out! 🔥",
                "wildcard_boost": f"Whoa, {mon} is powering up fast! I need to take that down before it snowballs!",
                "victory": "WUWAHAHA! What an incredible match! That was so much fun, thank you for the battle! 🏆💖",
                "defeat": "Aww, checkmate! You completely outplayed me there—respect! We're definitely doing a rematch soon! ⚔️✨"
            }

        return quotes.get(trigger, quotes.get("start", "Good luck in battle!"))

    async def _handle_challstr(self, challstr: str):
        """Authenticates with Showdown by logging in with saved credentials or registered assertions."""
        self._last_challstr = challstr
        self.log(f"Received challstr. Authenticating {self.username}...")

        # 1. Login with saved password
        if self.password:
            assertion = await self._api_login(self.username, self.password, challstr)
            if assertion:
                self.log(f"Logged into registered account {self.username}!")
                self.is_registered = True
                await self.send_raw(f"|/trn {self.username},1,{assertion}")
                return

        # 2. Registration fallback
        if not self.password:
            self.password = f"Pkm!{random.randint(100000, 999999)}"

        reg_assertion, reg_err = await self._api_register(self.username, self.password, challstr)
        if reg_assertion:
            self.log(f"✅ Successfully created & registered new account: {self.username}")
            self.is_registered = True
            self.config["showdown_username"] = self.username
            self.config["showdown_password"] = self.password
            if self.save_config_cb:
                self.save_config_cb(self.bot_id, self.config)
            await self.send_raw(f"|/trn {self.username},1,{reg_assertion}")
            return

        # 3. Fallback to unregistered assertion if server blocks registration
        self.log(f"Registration note: {reg_err}. Using unregistered assertion for full battle access.")
        guest_assertion = await self._api_getassertion(self.username, challstr)
        if guest_assertion:
            await self.send_raw(f"|/trn {self.username},0,{guest_assertion}")
            self.log(f"Logged in as active trainer: {self.username}")

    async def _api_login(self, username: str, password: str, challstr: str) -> Optional[str]:
        """Performs password login to Showdown API."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://play.pokemonshowdown.com/api/login",
                    data={"act": "login", "name": username, "pass": password, "challstr": challstr}
                ) as resp:
                    raw = await resp.text()
                    s = raw.strip()
                    if s.startswith("]"):
                        s = s[1:]
                    parsed = json.loads(s)
                    if parsed.get("actionsuccess"):
                        return parsed.get("assertion")
                    else:
                        self.log(f"Login note for {username}: {parsed.get('actionerror', 'Unknown error')}")
        except Exception as e:
            self.log(f"API login error: {e}")
        return None

    async def _api_register(self, username: str, password: str, challstr: str) -> Tuple[Optional[str], str]:
        """Registers an account on Showdown solving anti-spam verification."""
        try:
            post_data = {
                "act": "register",
                "username": username,
                "password": password,
                "cpassword": password,
                "captcha": "pikachu",
                "challstr": challstr
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://play.pokemonshowdown.com/api/register",
                    data=post_data,
                    headers={"User-Agent": "Mozilla/5.0"}
                ) as resp:
                    raw = await resp.text()
                    s = raw.strip()
                    if s.startswith("]"):
                        s = s[1:]
                    parsed = json.loads(s)
                    if parsed.get("actionsuccess"):
                        return parsed.get("assertion"), ""
                    return None, parsed.get("actionerror", "Unknown error")
        except Exception as e:
            return None, str(e)

    async def _api_getassertion(self, username: str, challstr: str) -> Optional[str]:
        """Retrieves assertion for unregistered username."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://play.pokemonshowdown.com/api/login",
                    data={"act": "getassertion", "userid": username.lower(), "challstr": challstr}
                ) as resp:
                    raw = await resp.text()
                    if raw and not raw.startswith(";") and not raw.startswith("]"):
                        return raw.strip()
        except Exception as e:
            self.log(f"getassertion error: {e}")
        return None

    async def _handle_pm(self, sender_raw: str, msg_content: str):
        """Handles incoming private messages, challenge commands, and battle requests."""
        sender = sender_raw.strip()
        sender_clean = sender.lstrip(" ~+@%*&#!★") or sender
        if not sender_clean or sender_clean.lower() == self.username.lower():
            return

        if msg_content.startswith("/nonotify"):
            return

        self.log(f"Received PM from [{sender_clean}]: {msg_content}")

        # 1. Challenge sent via PM
        if msg_content.startswith("/challenge"):
            c_parts = msg_content.split()
            raw_fmt = c_parts[1] if len(c_parts) > 1 else self.default_format
            fmt = raw_fmt.split("|")[0].strip()
            self.log(f"Detected battle challenge in PM from [{sender_clean}] for [{fmt}]!")
            if self.auto_accept:
                await self._accept_challenge_with_team(sender_clean, fmt)
            return

        # 2. System error or warning note or log
        if msg_content.startswith(("/error", "/raw", "/log", "/text", "/uhtml", "/html")):
            if msg_content.startswith(("/error", "/raw")):
                self.log(f"Showdown notice from [{sender}]: {msg_content}")
                low_err = msg_content.lower()
                if any(k in low_err for k in ("can't speak", "cant speak", "spam from your internet provider", "must be registered to send", "cannot be pmed", "muted")):
                    if not self.chat_muted:
                        self.chat_muted = True
                        self.log("⚠️ Chat restricted on Showdown. Diverting dialogue to Discord DM!")
                        await self.notify_discord(
                            f"⚠️ **[Showdown] Chat Muted:** Showdown restricted direct chatting (`{msg_content}`).\n"
                            f"➡️ **All in-character battle reactions & chat will now be delivered directly to your Discord DM!**",
                            is_battle_chat=True
                        )
            return

        # 3. User asks to battle in PM
        low_msg = msg_content.lower().strip()
        if any(w in low_msg for w in ("battle", "fight", "play", "!battle", "challenge", "duel", "match")):
            self.log(f"User [{sender_clean}] asked for a battle. Sending challenge in [{self.default_format}]...")
            await self.challenge_user(sender_clean, self.default_format)
            reply = f"I challenged you in {self.default_format}! Click Accept on your screen to start! ⚔️"
            if self.chat_muted:
                await self.notify_discord(f"💬 **[{self.bot_name} PM to {sender_clean}]**: {reply}", is_battle_chat=True)
            else:
                await self.send_raw(f"|/pm {sender_clean}, {reply}")
            return

        # 4. In-character persona response to PM
        reply = self._get_in_character_comment("start")
        pm_text = f"{reply} (Challenge me in any format, or type 'battle' and I will challenge you!)"
        if self.chat_muted:
            await self.notify_discord(
                f"💬 **[Showdown PM from {sender_clean}]**: {msg_content}\n"
                f"💬 **[{self.bot_name} Reply]**: {pm_text}",
                is_battle_chat=True
            )
        else:
            await self.send_raw(f"|/pm {sender_clean}, {pm_text}")

    async def _handle_updatechallenges(self, data: Dict[str, Any]):
        """Detects incoming challenges and auto-accepts them with appropriate team setup."""
        challenges_from = data.get("challengesFrom", {})
        if not challenges_from:
            return

        for challenger, fmt_info in challenges_from.items():
            raw_fmt = fmt_info if isinstance(fmt_info, str) else (fmt_info.get("format", self.default_format) if isinstance(fmt_info, dict) else self.default_format)
            fmt = raw_fmt.split("|")[0].strip()
            self.log(f"Received battle challenge from [{challenger}] in format [{fmt}]!")
            if self.auto_accept:
                await self._accept_challenge_with_team(challenger, fmt)

    async def _accept_challenge_with_team(self, challenger: str, battle_format: str):
        """Builds on-demand competitive team if needed, loads /utm, and accepts challenge."""
        fmt = (battle_format or self.default_format).split("|")[0].strip()
        self._last_format = fmt
        self._last_challenger = challenger
        self._last_action = "accept"
        self.log(f"Preparing to accept battle against [{challenger}] in format [{fmt}]...")

        if "random" in fmt.lower():
            self._last_packed_team = "null"
            await self.send_raw("|/utm null")
            await self.send_raw(f"|/accept {challenger}")
            accept_msg = "Challenge accepted! Best of luck in our battle! ⚔️✨"
            if self.chat_muted:
                await self.notify_discord(f"💬 **[{self.bot_name} to {challenger}]**: {accept_msg}", is_battle_chat=True)
            else:
                await self.send_raw(f"|/pm {challenger}, {accept_msg}")
        else:
            # Constructed tier requires building a team!
            prep_msg = "Hold on! I am making a team real quick... 🛠️⚡"
            if self.chat_muted:
                await self.notify_discord(f"💬 **[{self.bot_name} to {challenger}]**: {prep_msg}", is_battle_chat=True)
            else:
                await self.send_raw(f"|/pm {challenger}, {prep_msg}")

            await self.notify_discord(
                f"🛠️ **[Showdown] {self.bot_name}** is dynamically building a custom team for `{fmt}` vs **{challenger}**!",
                is_battle_chat=True
            )

            # Build / load custom team for this format
            packed_team = await self.team_builder.build_or_load_team(
                bot_id=self.bot_id,
                bot_name=self.bot_name,
                personality=self.personality,
                battle_format=fmt,
                llm_generate_cb=self.llm_generate_cb
            )

            self._last_packed_team = packed_team
            await self.send_raw(f"|/utm {packed_team}")
            await asyncio.sleep(0.5)
            await self.send_raw(f"|/accept {challenger}")
            ready_msg = "Team assembled and ready! Let's have a magnificent battle! ⚔️"
            if self.chat_muted:
                await self.notify_discord(f"💬 **[{self.bot_name} to {challenger}]**: {ready_msg}", is_battle_chat=True)
            else:
                await self.send_raw(f"|/pm {challenger}, {ready_msg}")

        disc_msg = (
            f"⚔️ **[Showdown] {self.bot_name}** accepted battle challenge from **{challenger}** in `{fmt}`!\n"
            f"• Playing as: `{self.username}`\n"
            f"• Watch live on: https://play.pokemonshowdown.com"
        )
        await self.notify_discord(disc_msg)

    async def _handle_battle_chat(self, room: str, sender: str, msg: str):
        """Replies to opponent banter in the battle room chat."""
        if not msg or msg.startswith("/"):
            return
        comment = self._get_in_character_comment("start")
        await self.send_room_chat(room, f"{comment}")

    async def _handle_battle_request(self, room: str, req: Dict[str, Any]):
        """Makes intelligent tactical moves or switches in battle."""
        if req.get("wait"):
            return

        # 0. Team Preview: Picking battle Pokémon order / lead
        if req.get("teamPreview"):
            side = req.get("side", {})
            p_list = side.get("pokemon", [])
            max_size = req.get("maxTeamSize", len(p_list))
            order = "".join(str(i) for i in range(1, min(len(p_list), max_size) + 1))
            self.log(f"[{room}] Team Preview: Selecting battle team order ({order})...")
            await asyncio.sleep(0.6)
            await self.send_raw(f"{room}|/team {order}")
            return

        # 1. Forced switch (e.g. after a faint)
        if req.get("forceSwitch"):
            switches = []
            side = req.get("side", {})
            for i, p in enumerate(side.get("pokemon", []), 1):
                cond = p.get("condition", "")
                if not p.get("active") and not cond.endswith("fnt") and cond != "0 fnt":
                    switches.append(i)
            if switches:
                chosen_switch = switches[0]
                self.log(f"[{room}] Switching to slot {chosen_switch}")
                await self.send_raw(f"{room}|/choose switch {chosen_switch}")
            else:
                await self.send_raw(f"{room}|/choose default")
            return

        # 2. Regular move selection
        active_list = req.get("active", [])
        if not active_list:
            if not req.get("wait"):
                await self.send_raw(f"{room}|/choose default")
            return

        active_mon = active_list[0]
        moves = active_mon.get("moves", [])
        valid_moves = []
        for i, m in enumerate(moves, 1):
            if not m.get("disabled") and m.get("pp", 1) > 0:
                valid_moves.append((i, m))

        if not valid_moves:
            await self.send_raw(f"{room}|/choose default")
        b_info = self.active_battles.get(room, {})
        my_side = req.get("side", {}).get("id")
        if my_side:
            b_info["my_side"] = my_side
            b_info["opp_side"] = "p2" if my_side == "p1" else "p1"

        my_species = b_info.get("my_active") or active_mon.get("species", "")
        my_types = b_info.get("my_types") or self.tactics_engine.get_pokemon_types(my_species, tera_type=active_mon.get("teraType"))
        opp_species = b_info.get("opp_active", "")
        opp_types = b_info.get("opp_types") or self.tactics_engine.get_pokemon_types(opp_species)
        opp_ability = b_info.get("opp_ability", "")
        opp_hp = b_info.get("opp_hp_pct", 100.0)
        my_hp = b_info.get("my_hp_pct", 100.0)

        # Merge blacklists and failure memory from species, nickname, and cross-battle learning
        immune_set = set(b_info.get("immune_moves", {}).get(opp_species, set()))
        immune_types = set(b_info.get("immune_types", {}).get(opp_species, set()))
        failed_set = set(b_info.get("failed_moves", {}).get(opp_species, set()))
        opp_nick = b_info.get("opp_active_nick", "")
        if opp_nick:
            immune_set.update(b_info.get("immune_moves", {}).get(opp_nick, set()))
            immune_types.update(b_info.get("immune_types", {}).get(opp_nick, set()))
            failed_set.update(b_info.get("failed_moves", {}).get(opp_nick, set()))

        # Cross-battle persistent memory
        learned_intel = self.memory_manager.get_known_intel(opp_species)
        if learned_intel:
            immune_set.update(learned_intel.get("immune_moves", []))
            immune_types.update(learned_intel.get("immune_types", []))
            if not opp_ability and learned_intel.get("abilities"):
                opp_ability = learned_intel["abilities"][0]
            if not b_info.get("opp_item") and learned_intel.get("items"):
                b_info["opp_item"] = learned_intel["items"][0]

        hazards_up = b_info.get("hazards_up", False)
        stall_count = b_info.get("stall_count", 0)
        can_tera = bool(active_mon.get("canTerastallize"))
        opp_status = b_info.get("opp_status", "")
        my_status = b_info.get("my_status", "")
        my_boosts = b_info.get("my_boosts", {})
        opp_boosts = b_info.get("opp_boosts", {})
        opp_sub = b_info.get("opp_substitute", False)
        opp_item = b_info.get("opp_item", "")
        terrain = b_info.get("terrain", "")
        weather = b_info.get("weather", "")
        battle_format = b_info.get("format", self.default_format)
        sleep_clause_active = any(st == "slp" for st in b_info.get("opp_statuses", {}).values())
        my_ability = active_mon.get("ability", "")

        scored_moves = []
        for slot, m in valid_moves:
            score, reason, rec_tera = self.tactics_engine.score_move(
                move_obj=m,
                my_species=my_species,
                my_types=my_types,
                my_hp_pct=my_hp,
                opp_species=opp_species,
                opp_types=opp_types,
                opp_hp_pct=opp_hp,
                opp_ability=opp_ability,
                immune_moves=immune_set,
                hazards_up=hazards_up,
                stall_count=stall_count,
                can_tera=can_tera,
                immune_types=immune_types,
                opp_status=opp_status,
                my_status=my_status,
                my_boosts=my_boosts,
                opp_boosts=opp_boosts,
                failed_moves=failed_set,
                opp_substitute=opp_sub,
                opp_item=opp_item,
                terrain=terrain,
                weather=weather,
                battle_format=battle_format,
                sleep_clause_active=sleep_clause_active,
                my_ability=my_ability,
                learned_intel=learned_intel
            )
            scored_moves.append((slot, score, reason, rec_tera, m))

        # Sort moves highest score first
        scored_moves.sort(key=lambda x: x[1], reverse=True)
        best_slot, best_score, best_reason, rec_tera, chosen_m = scored_moves[0]

        # 3. Check if all available moves are useless/immune (score <= 0) -> Tactical Switch!
        side_mons = req.get("side", {}).get("pokemon", [])
        is_trapped = bool(active_mon.get("trapped"))
        if best_score <= 0.0 and len(side_mons) > 1 and not is_trapped:
            ranked_switches = self.tactics_engine.evaluate_switches(
                side_pokemon=side_mons,
                my_active_name=my_species,
                opp_species=opp_species,
                opp_types=opp_types,
                opp_ability=opp_ability,
                immune_moves=immune_set,
                immune_types=immune_types,
                opp_last_move=b_info.get("opp_last_move", ""),
                opp_item=opp_item,
                battle_format=battle_format,
                my_ability=my_ability,
                learned_intel=learned_intel
            )
            # ONLY switch if a genuinely viable counter exists on bench (score > 0.0)
            if ranked_switches and ranked_switches[0][1] > 0.0:
                sw_slot, sw_score, sw_reason = ranked_switches[0]
                self.log(f"[{room}] 🧠 Tactical Switch: All active moves ineffective vs {opp_species} ({best_reason}). {sw_reason}")
                await asyncio.sleep(0.8)
                await self.send_raw(f"{room}|/choose switch {sw_slot}")
                return
            else:
                self.log(f"[{room}] ⚠️ Tactical Hold: Active moves are ineffective vs {opp_species}, but no bench Pokémon has an advantageous counter (best switch score <= 0). Holding field!")

        tera_flag = " terastallize" if (can_tera and rec_tera) else ""
        self.log(f"[{room}] 🧠 Tactical Move: Slot {best_slot} -> {best_reason} [Score: {best_score:.1f}]{tera_flag}")

        b_info["last_move_used"] = chosen_m.get("move", "")
        await asyncio.sleep(0.8)
        await self.send_raw(f"{room}|/choose move {best_slot}{tera_flag}")

        b_info["turn"] = b_info.get("turn", 0) + 1

    async def challenge_user(self, target_user: str, battle_format: Optional[str] = None):
        """Challenges another player on Showdown with format-aware team packing."""
        fmt = battle_format or self.default_format
        clean_target = re.sub(r'[^a-zA-Z0-9_-]', '', target_user)
        self._last_format = fmt
        self._last_target = clean_target
        self._last_action = "challenge"

        for _ in range(20):
            if self.ws and self.is_connected:
                break
            await asyncio.sleep(0.5)

        if "random" in fmt.lower():
            self._last_packed_team = "null"
            await self.send_raw("|/utm null")
        else:
            packed_team = await self.team_builder.build_or_load_team(
                bot_id=self.bot_id,
                bot_name=self.bot_name,
                personality=self.personality,
                battle_format=fmt,
                llm_generate_cb=self.llm_generate_cb
            )
            self._last_packed_team = packed_team
            await self.send_raw(f"|/utm {packed_team}")

        await self.send_raw(f"|/challenge {clean_target}, {fmt}")
        self.log(f"Sent challenge to [{clean_target}] in format [{fmt}]")
        disc_msg = (
            f"⚔️ **[Showdown] {self.bot_name}** challenged **{clean_target}** to a `{fmt}` battle!\n"
            f"• Playing as: `{self.username}`\n"
            f"• Accept the challenge on: https://play.pokemonshowdown.com"
        )
        await self.notify_discord(disc_msg)

    async def search_ladder(self, battle_format: Optional[str] = None):
        """Starts matchmaking on the Showdown public ladder."""
        fmt = battle_format or self.default_format
        self._last_format = fmt
        self._last_action = "ladder"

        if "random" in fmt.lower():
            self._last_packed_team = "null"
            await self.send_raw("|/utm null")
        else:
            packed_team = await self.team_builder.build_or_load_team(
                bot_id=self.bot_id,
                bot_name=self.bot_name,
                personality=self.personality,
                battle_format=fmt,
                llm_generate_cb=self.llm_generate_cb
            )
            self._last_packed_team = packed_team
            await self.send_raw(f"|/utm {packed_team}")
        await self.send_raw(f"|/search {fmt}")
        self.log(f"Searching ladder for format: {fmt}...")

    async def cancel_ladder_search(self):
        """Cancels active ladder search."""
        await self.send_raw("|/cancelsearch")
        self.log("Ladder search cancelled.")

    async def _handle_team_rejection(self, rejection_msg: str):
        """Dynamically fixes team rejection errors and re-submits/re-accepts battle."""
        self._rejection_retry_count = getattr(self, "_rejection_retry_count", 0) + 1
        if self._rejection_retry_count > 3:
            self.log("Maximum team fix retries (3) reached. Stopping to prevent loop.")
            self._rejection_retry_count = 0
            await self.notify_discord(
                f"❌ **[Showdown] {self.bot_name}** could not auto-resolve team rejection after 3 attempts:\n`{rejection_msg}`",
                is_battle_chat=True
            )
            return

        fmt = getattr(self, "_last_format", self.default_format)
        action = getattr(self, "_last_action", "accept")
        challenger = getattr(self, "_last_challenger", "")
        target = getattr(self, "_last_target", "")
        current_packed = getattr(self, "_last_packed_team", "")

        clean_reasons = rejection_msg.replace("||||", "\n").replace("||", "\n").replace("Your team was rejected for the following reasons:", "").strip()
        self.log(f"Auto-fixing team mistakes for format [{fmt}]. Reasons:\n{clean_reasons}")

        await self.notify_discord(
            f"🛠️ **[Showdown] {self.bot_name}** detected team rejection! Auto-fixing mistakes...\n"
            f"• **Format**: `{fmt}`\n"
            f"• **Issue**: `{clean_reasons[:180]}...`",
            is_battle_chat=True
        )

        fixed_export, fixed_packed, explanation = await self.team_builder.fix_team_rejection(
            bot_id=self.bot_id,
            bot_name=self.bot_name,
            personality=self.personality,
            battle_format=fmt,
            rejection_reasons=rejection_msg,
            current_packed=current_packed,
            llm_generate_cb=self.llm_generate_cb
        )

        self._last_packed_team = fixed_packed
        await self.send_raw(f"|/utm {fixed_packed}")
        await asyncio.sleep(0.8)

        # Dynamically re-execute the failed action!
        if action == "accept" and challenger:
            self.log(f"Re-accepting battle challenge from [{challenger}] with fixed team...")
            await self.send_raw(f"|/accept {challenger}")
            reply_msg = "Fixed my team setup! Re-accepting our battle now! ⚔️✨"
            if self.chat_muted:
                await self.notify_discord(f"💬 **[{self.bot_name} to {challenger}]**: {reply_msg}", is_battle_chat=True)
            else:
                await self.send_raw(f"|/pm {challenger}, {reply_msg}")

        elif action == "challenge" and target:
            self.log(f"Re-sending challenge to [{target}] with fixed team...")
            await self.send_raw(f"|/challenge {target}, {fmt}")

        elif action == "ladder":
            self.log(f"Re-searching ladder for format [{fmt}] with fixed team...")
            await self.send_raw(f"|/search {fmt}")

        self._rejection_retry_count = 0
        await self.notify_discord(
            f"✅ **[Showdown] {self.bot_name}** dynamically fixed team mistakes!\n"
            f"• **Resolution**: {explanation}\n"
            f"• **Action**: Re-submitted team and resumed match against **{challenger or target or 'ladder'}**! ⚔️",
            is_battle_chat=True
        )


class ShowdownManager:
    """Orchestrates Showdown clients across multiple bot personas."""

    def __init__(self, bots_state: Dict[str, Any], save_cb: Optional[Callable] = None):
        self.bots_state = bots_state
        self.save_cb = save_cb
        self.clients: Dict[str, PokemonShowdownClient] = {}
        self.discord_notify_callback: Optional[Callable] = None
        self.llm_team_generator_cb: Optional[Callable] = None

    def set_discord_callback(self, cb: Callable):
        self.discord_notify_callback = cb

    def set_llm_team_generator(self, cb: Callable):
        self.llm_team_generator_cb = cb
        for c in self.clients.values():
            c.llm_generate_cb = cb

    def get_client(self, bot_id: str) -> Optional[PokemonShowdownClient]:
        return self.clients.get(bot_id)

    def init_bot(self, bot_id: str, bot_name: str, config: Dict[str, Any]) -> PokemonShowdownClient:
        """Instantiates or retrieves client for a bot persona."""
        if bot_id in self.clients:
            c = self.clients[bot_id]
            if not c.llm_generate_cb and self.llm_team_generator_cb:
                c.llm_generate_cb = self.llm_team_generator_cb
            return c

        client = PokemonShowdownClient(
            bot_id=bot_id,
            bot_name=bot_name,
            config=config,
            on_event_cb=self._on_client_event,
            save_config_cb=self.save_cb,
            llm_generate_cb=self.llm_team_generator_cb
        )
        self.clients[bot_id] = client
        return client

    async def _on_client_event(self, client: PokemonShowdownClient, msg: str, embed_data: Optional[Dict[str, Any]] = None, is_battle_chat: bool = False):
        if self.discord_notify_callback:
            try:
                if asyncio.iscoroutinefunction(self.discord_notify_callback):
                    await self.discord_notify_callback(client, msg, embed_data, is_battle_chat)
                else:
                    self.discord_notify_callback(client, msg, embed_data, is_battle_chat)
            except TypeError:
                try:
                    if asyncio.iscoroutinefunction(self.discord_notify_callback):
                        await self.discord_notify_callback(client, msg, embed_data)
                    else:
                        self.discord_notify_callback(client, msg, embed_data)
                except Exception as e:
                    print(f"[SHOWDOWN MANAGER] Callback error: {e}")
            except Exception as e:
                print(f"[SHOWDOWN MANAGER] Callback error: {e}")

    async def start_bot(self, bot_id: str):
        client = self.clients.get(bot_id)
        if client:
            await client.start()

    async def stop_bot(self, bot_id: str):
        client = self.clients.get(bot_id)
        if client:
            await client.stop()

    def get_statuses(self) -> List[Dict[str, Any]]:
        results = []
        for b_id, c in self.clients.items():
            results.append({
                "bot_id": b_id,
                "bot_name": c.bot_name,
                "username": c.username,
                "is_connected": c.is_connected,
                "is_registered": c.is_registered,
                "active_battles": len(c.active_battles),
                "auto_accept": c.auto_accept,
                "format": c.default_format
            })
        return results
