"""
minecraft_engine.py — Advanced Autonomous Personality-Driven Minecraft Engine
Coordinates Mineflayer subprocesses with real-time personality planning,
tactical survival hierarchies, resource progression, and in-game character chat.
"""

import os
import sys
import json
import time
import random
import asyncio
import subprocess
import threading
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MEMORIES_DIR = os.path.join(SCRIPT_DIR, "memories", "minecraft")
os.makedirs(MEMORIES_DIR, exist_ok=True)

class MinecraftPersonalityPlanner:
    """
    Evaluates in-game state and generates personality-driven tactical plans,
    hierarchical goal progression, and distinct in-character commentary.
    """
    def __init__(self, bot_name: str = "Player", personality: str = "", role: str = "Companion"):
        self.bot_name = bot_name
        self.personality = personality or ""
        self.role = role or "Companion"
        self.archetype = self._determine_archetype()
        
        self.state = {
            "health": 20,
            "food": 20,
            "pos": {"x": 0, "y": 64, "z": 0},
            "inventory": {},
            "time": 6000,
            "weather": "clear",
            "nearby_mobs": [],
            "nearby_players": [],
            "equipped": "fist",
            "last_action": "idle",
            "dimension": "overworld"
        }
        
        self.current_goal = "EXPEDITION"
        self.current_plan: List[str] = []
        self.last_comment_time = 0.0
        self.last_plan_tick = 0.0
        self.milestones: List[str] = []

    def _determine_archetype(self) -> str:
        text = f"{self.bot_name} {self.role} {self.personality}".lower()
        if any(w in text for w in ["warrior", "knight", "guard", "fight", "soldier", "berserker", "slayer", "protect", "combat"]):
            return "WARRIOR"
        elif any(w in text for w in ["timid", "shy", "cautious", "fear", "scared", "gentle", "coward", "anxious", "nervous"]):
            return "CAUTIOUS"
        elif any(w in text for w in ["builder", "architect", "artist", "create", "creative", "design", "decorate"]):
            return "BUILDER"
        elif any(w in text for w in ["miner", "engineer", "pragmatic", "smart", "efficient", "craft", "tech", "logic"]):
            return "PRAGMATIST"
        else:
            return "COMPANION"

    def update_state(self, new_data: Dict[str, Any]):
        if not new_data or not isinstance(new_data, dict):
            return
        for k, v in new_data.items():
            if k in self.state and isinstance(self.state[k], dict) and isinstance(v, dict):
                self.state[k].update(v)
            else:
                self.state[k] = v

    def evaluate_plan(self) -> Dict[str, Any]:
        """
        Hierarchical Goal Evaluation:
        1. Emergency Survival (Health <= 8 or Food <= 6)
        2. Nighttime Defense / Sleep (Time > 12500)
        3. Tool & Equipment Progression (Wood -> Stone -> Iron)
        4. Personality-Driven Objectives
        """
        self.last_plan_tick = time.time()
        health = float(self.state.get("health", 20))
        food = float(self.state.get("food", 20))
        inv = self.state.get("inventory", {})
        game_time = int(self.state.get("time", 6000))
        is_night = (12500 <= (game_time % 24000) <= 23500)

        # 1. EMERGENCY SURVIVAL
        if health <= 8.0 or food <= 6.0:
            self.current_goal = "EMERGENCY_SURVIVAL"
            self.current_plan = [
                f"Health is critical ({health:.1f}/20) or hunger low ({food:.1f}/20)",
                "Consume available food items from inventory immediately",
                "Retreat from hostile entities into a secure, lit perimeter",
                "Build temporary 1x2 defensive barrier if under active attack"
            ]
            return {
                "goal": self.current_goal,
                "action": "eat",
                "params": {},
                "plan": self.current_plan,
                "priority": "CRITICAL"
            }

        # 2. NIGHTTIME DEFENSE OR REST
        if is_night:
            if self.archetype == "WARRIOR":
                self.current_goal = "NIGHT_PERIMETER_PATROL"
                self.current_plan = [
                    "Nightfall active: Hostile mobs spawning in dark regions",
                    "Equip melee weapon and shield for base defense",
                    "Engage nearby zombies, skeletons, and spiders",
                    "Collect monster drops (arrows, bones, string, gunpowder)"
                ]
                return {
                    "goal": self.current_goal,
                    "action": "patrol",
                    "params": {"radius": 18},
                    "plan": self.current_plan,
                    "priority": "HIGH"
                }
            else:
                self.current_goal = "NIGHT_SHELTER_AND_SLEEP"
                self.current_plan = [
                    "Nightfall active: Dangerous conditions outside",
                    "Locate nearest placed bed and initiate sleep cycle",
                    "If no bed available, stay inside enclosed shelter near torches",
                    "Wait for dawn to safely resume outdoor operations"
                ]
                return {
                    "goal": self.current_goal,
                    "action": "sleep",
                    "params": {},
                    "plan": self.current_plan,
                    "priority": "HIGH"
                }

        # 3. TOOL & EQUIPMENT PROGRESSION
        has_pickaxe = any("pickaxe" in k.lower() for k in inv.keys())
        has_axe = any("axe" in k.lower() for k in inv.keys())
        has_sword = any("sword" in k.lower() for k in inv.keys())
        has_wood = any("log" in k.lower() or "wood" in k.lower() for k in inv.keys())
        wood_count = sum(v for k, v in inv.items() if "log" in k.lower() or "wood" in k.lower())

        if not has_pickaxe and not has_axe and wood_count < 4:
            self.current_goal = "RESOURCE_BOOTSTRAPPING"
            self.current_plan = [
                "Early survival phase: No harvesting tools in inventory",
                "Locate nearest tree (Oak, Birch, Spruce, Dark Oak)",
                "Harvest 4-6 wood logs for planks and crafting bench",
                "Craft Crafting Table and Wooden Pickaxe"
            ]
            return {
                "goal": self.current_goal,
                "action": "mine",
                "params": {"block": "oak_log", "count": 4},
                "plan": self.current_plan,
                "priority": "MEDIUM"
            }

        # 4. PERSONALITY-ALIGNED GAMEPLAY
        if self.archetype == "WARRIOR":
            self.current_goal = "MOB_HUNT_AND_EXPLORATION"
            self.current_plan = [
                "Patrol surrounding wilderness and subterranean caverns",
                "Engage hostile mobs to harvest rare loot and experience",
                "Maintain defensive readiness and protect friendly players"
            ]
            return {
                "goal": self.current_goal,
                "action": "hunt",
                "params": {"target": "hostile"},
                "plan": self.current_plan,
                "priority": "NORMAL"
            }

        elif self.archetype == "BUILDER":
            self.current_goal = "ARCHITECTURAL_CONSTRUCTION"
            self.current_plan = [
                "Quarry decorative building materials (wood, stone, clay, glass)",
                "Construct and enhance perimeter walls and living shelter",
                "Place torches at 6-block intervals to prevent mob spawning"
            ]
            return {
                "goal": self.current_goal,
                "action": "build",
                "params": {"structure": "shelter"},
                "plan": self.current_plan,
                "priority": "NORMAL"
            }

        elif self.archetype == "PRAGMATIST":
            self.current_goal = "SUBTERRANEAN_ORE_EXTRACTION"
            self.current_plan = [
                "Establish structured staircase mine downward",
                "Extract iron ore, coal, redstone, and diamond veins",
                "Smelt raw ores in furnace and craft upgraded iron tools/armor"
            ]
            return {
                "goal": self.current_goal,
                "action": "mine",
                "params": {"block": "iron_ore", "count": 5},
                "plan": self.current_plan,
                "priority": "NORMAL"
            }

        elif self.archetype == "CAUTIOUS":
            self.current_goal = "FOOD_STOCKPILING_AND_FORTIFICATION"
            self.current_plan = [
                "Harvest mature wheat, carrots, and sweet berries",
                "Hunt passive animals (cows, pigs, sheep) for food and wool",
                "Return to base before dusk and secure all entrances"
            ]
            return {
                "goal": self.current_goal,
                "action": "gather_food",
                "params": {},
                "plan": self.current_plan,
                "priority": "NORMAL"
            }

        else: # COMPANION
            self.current_goal = "PLAYER_ESCORT_AND_ASSISTANCE"
            self.current_plan = [
                "Follow active players and maintain a 3-5 block escort distance",
                "Assist companion with mining and monster defense",
                "Share collected materials, torches, and sustenance"
            ]
            return {
                "goal": self.current_goal,
                "action": "follow",
                "params": {},
                "plan": self.current_plan,
                "priority": "NORMAL"
            }

    def generate_in_character_comment(self, trigger_event: str = "") -> Optional[str]:
        """
        Generates vivid in-game Minecraft chat commentary true to character archetype.
        """
        now = time.time()
        # Rate limit spontaneous in-game chat to at least 45 seconds between messages unless event
        if not trigger_event and (now - self.last_comment_time < 45.0):
            return None
            
        self.last_comment_time = now
        arch = self.archetype
        h = self.state.get("health", 20)
        pos = self.state.get("pos", {})
        x, y, z = int(pos.get("x", 0)), int(pos.get("y", 64)), int(pos.get("z", 0))

        if trigger_event == "death":
            if arch == "WARRIOR":
                return random.choice([
                    "Hmph, a warrior never stays down. Respawning and coming right back!",
                    "That was a cowardly strike! Mark my words, I'll slay that beast next time.",
                    "A tactical setback. Sharpening my blade for vengeance!"
                ])
            elif arch == "CAUTIOUS":
                return random.choice([
                    "Eep! That was terrifying! I knew I shouldn't have wandered in the dark...",
                    "I... I died?! Please tell me my items didn't fall into lava!",
                    "Ouch... note to self: never look an Enderman in the eyes again."
                ])
            elif arch == "BUILDER":
                return random.choice([
                    "No! I fell off my scaffolding... gravity is the true enemy of architecture.",
                    "Respawned! Hopefully a creeper didn't blow up my recent build...",
                    "Time to rebuild and try that roof again!"
                ])
            elif arch == "PRAGMATIST":
                return random.choice([
                    f"Death recorded at ({x}, {y}, {z}). Calculating optimal retrieval route.",
                    "Unfortunate durability loss on death. Recalibrating survival parameters.",
                    "Respawn complete. Resuming resource acquisition cycle."
                ])
            else:
                return random.choice([
                    "Aww, respawned at the bed! Anyone nearby want to group up?",
                    "Oof, that hurt! Give me a second to gather my bearings!",
                    "Back in action! Who wants to go adventuring?"
                ])

        if trigger_event == "milestone":
            if arch == "WARRIOR":
                return "Another conquest complete! Victory favors the prepared!"
            elif arch == "BUILDER":
                return "The foundation looks stunning! Step by step, this world becomes art."
            elif arch == "PRAGMATIST":
                return "Milestone achieved. Efficiency increased by 14%."
            else:
                return "Yay! We're making real progress in this world!"

        # Ambient / Goal commentary
        if self.current_goal == "EMERGENCY_SURVIVAL":
            if arch == "CAUTIOUS":
                return f"*panting heavily* Low on health ({h:.0f}HP)! Need to eat and hide right now!"
            return f"Taking cover to regenerate health ({h:.0f}/20). Cover me if you're close!"

        if self.current_goal in ("NIGHT_SHELTER_AND_SLEEP", "NIGHT_PERIMETER_PATROL"):
            if arch == "WARRIOR":
                return "Sundown. Monsters are roaming. Keep your weapons drawn!"
            elif arch == "CAUTIOUS":
                return "It's getting pitch black... let's sleep in our beds before phantoms spawn!"
            return "Night has fallen. Let's sleep through the night to clear the skies."

        if self.current_goal == "SUBTERRANEAN_ORE_EXTRACTION":
            return f"Mining down at level Y={y}. Placing torches to keep the cavern lit."

        if self.current_goal == "ARCHITECTURAL_CONSTRUCTION":
            return "Gathering building blocks for the next shelter expansion!"

        if self.current_goal == "PLAYER_ESCORT_AND_ASSISTANCE":
            return "Following close behind! Let me know if you need supplies or a hand."

        return None


class MinecraftBotProcess:
    """
    Manages a single node mc_bridge.js child process with JSON IPC over stdin/stdout.
    """
    def __init__(self, bot_id: str, opts: Dict[str, Any], planner: MinecraftPersonalityPlanner):
        self.bot_id = bot_id
        self.opts = opts
        self.planner = planner
        self.process: Optional[subprocess.Popen] = None
        self._running = False
        self._loop_task: Optional[asyncio.Task] = None
        self.on_chat_callback: Optional[Callable] = None
        self.on_event_callback: Optional[Callable] = None
        self.start_time = 0.0

    def start(self) -> Tuple[bool, str]:
        if self.process and self.process.poll() is None:
            return True, "Minecraft bot is already running."

        bridge_candidates = [
            os.path.join(SCRIPT_DIR, "mc_bridge.js"),
            os.path.join("/storage/emulated/0/discord-bot", "mc_bridge.js")
        ]
        script_path = None
        for p in bridge_candidates:
            if os.path.exists(p):
                script_path = p
                break

        if not script_path:
            return False, "mc_bridge.js script not found on disk."

        # Setup Node environment with Termux & local node_modules
        env = os.environ.copy()
        node_paths = [
            "/data/data/com.termux/files/home/node_modules",
            "/storage/emulated/0/discord-bot/node_modules",
            os.path.join(SCRIPT_DIR, "node_modules")
        ]
        env["NODE_PATH"] = ":".join(p for p in node_paths if os.path.exists(p))

        cmd = ["node", script_path, json.dumps(self.opts)]

        try:
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env
            )
            self._running = True
            self.start_time = time.time()

            # Start stdout reading thread
            t = threading.Thread(target=self._stdout_reader, daemon=True)
            t.start()
            
            return True, f"Minecraft bot '{self.opts.get('username')}' connecting to {self.opts.get('host')}:{self.opts.get('port')}"
        except Exception as e:
            self._running = False
            return False, f"Failed to spawn node mc_bridge.js: {e}"

    def _stdout_reader(self):
        """Reads JSON event streams emitted from mc_bridge.js."""
        if not self.process or not self.process.stdout:
            return
        while self._running and self.process and self.process.poll() is None:
            line = self.process.stdout.readline()
            if not line:
                break
            line_str = line.strip()
            if not line_str or not line_str.startswith("{"):
                continue
            try:
                data = json.loads(line_str)
                event_type = data.get("type", "")

                if event_type == "status":
                    self.planner.update_state(data)
                elif event_type == "spawn":
                    pos = data.get("pos", {})
                    self.planner.update_state({"pos": pos})
                    if self.on_event_callback:
                        self.on_event_callback("spawn", f"Spawned into world at ({pos.get('x',0):.1f}, {pos.get('y',64):.1f}, {pos.get('z',0):.1f})")
                elif event_type == "death":
                    comment = self.planner.generate_in_character_comment(trigger_event="death")
                    if comment:
                        self.send_chat(comment)
                    if self.on_event_callback:
                        self.on_event_callback("death", "Bot died and respawned.")
                elif event_type == "milestone":
                    m_desc = data.get("desc", "Milestone completed")
                    self.planner.milestones.append(m_desc)
                    comment = self.planner.generate_in_character_comment(trigger_event="milestone")
                    if comment:
                        self.send_chat(comment)
                    if self.on_event_callback:
                        self.on_event_callback("milestone", m_desc)
                elif event_type == "chat":
                    user = data.get("username", "")
                    msg = data.get("message", "")
                    if self.on_chat_callback and user.lower() != str(self.opts.get("username", "")).lower():
                        self.on_chat_callback(user, msg)
            except Exception:
                pass

    def send_action(self, action: str, params: Optional[Dict[str, Any]] = None) -> bool:
        """Sends a JSON action command to mc_bridge.js via stdin."""
        if not self.process or self.process.poll() is not None:
            return False
        payload = {"action": action, "params": params or {}}
        try:
            line = json.dumps(payload) + "\n"
            self.process.stdin.write(line)
            self.process.stdin.flush()
            return True
        except Exception:
            return False

    def send_chat(self, msg: str) -> bool:
        """Sends in-game public chat message."""
        return self.send_action("say", {"message": msg[:200]})

    def stop(self) -> Tuple[bool, str]:
        self._running = False
        if self.process:
            try:
                self.send_action("quit")
            except Exception:
                pass
            try:
                self.process.terminate()
                self.process.wait(timeout=2.0)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None
            return True, "Minecraft bot disconnected."
        return False, "Minecraft bot was not running."


class MinecraftManager:
    """
    Multi-tenant Minecraft Bot Manager for SaaS Discord Bot.
    Coordinates MinecraftBotProcess instances keyed by bot_id.
    """
    def __init__(self):
        self.bots: Dict[str, MinecraftBotProcess] = {}
        self.planners: Dict[str, MinecraftPersonalityPlanner] = {}
        self._ticker_task: Optional[asyncio.Task] = None
        self._running = False

    def get_or_create_planner(self, bot_id: str, bot_name: str, personality: str, role: str) -> MinecraftPersonalityPlanner:
        if bot_id not in self.planners:
            self.planners[bot_id] = MinecraftPersonalityPlanner(bot_name=bot_name, personality=personality, role=role)
        else:
            self.planners[bot_id].bot_name = bot_name
            self.planners[bot_id].personality = personality
            self.planners[bot_id].role = role
            self.planners[bot_id].archetype = self.planners[bot_id]._determine_archetype()
        return self.planners[bot_id]

    def start_bot(self, bot_id: str, cfg: Dict[str, Any], bot_name: str, 
                  on_chat: Optional[Callable] = None, on_event: Optional[Callable] = None) -> Tuple[bool, str]:
        # Stop existing if running
        if bot_id in self.bots and self.bots[bot_id].process and self.bots[bot_id].process.poll() is None:
            return True, f"Minecraft bot is already running for {bot_name}."

        planner = self.get_or_create_planner(
            bot_id, 
            bot_name=bot_name, 
            personality=cfg.get("minecraft_personality") or cfg.get("personality", ""),
            role=cfg.get("role", "Companion")
        )

        mc_user = cfg.get("minecraft_username") or f"{bot_name}Bot".replace(" ", "_")
        mc_opts = {
            "botId": bot_id,
            "username": mc_user,
            "botName": bot_name,
            "host": cfg.get("minecraft_server", "localhost"),
            "port": int(cfg.get("minecraft_port", 25565)),
            "version": cfg.get("minecraft_version") or False,
            "auth": cfg.get("minecraft_auth", "offline"),
            "skin": cfg.get("minecraft_skin", ""),
            "personality": planner.archetype
        }

        bot_proc = MinecraftBotProcess(bot_id, mc_opts, planner)
        bot_proc.on_chat_callback = on_chat
        bot_proc.on_event_callback = on_event

        ok, msg = bot_proc.start()
        if ok:
            self.bots[bot_id] = bot_proc
            # Ensure background autonomous ticker is active
            if not self._running:
                self._running = True
                self._start_ticker()
        return ok, msg

    def stop_bot(self, bot_id: str) -> Tuple[bool, str]:
        if bot_id in self.bots:
            ok, msg = self.bots[bot_id].stop()
            del self.bots[bot_id]
            return ok, msg
        return False, "No active Minecraft bot found for this bot ID."

    def get_status(self, bot_id: str) -> Dict[str, Any]:
        is_active = (bot_id in self.bots and self.bots[bot_id].process and self.bots[bot_id].process.poll() is None)
        planner = self.planners.get(bot_id)
        return {
            "active": is_active,
            "bot_id": bot_id,
            "archetype": planner.archetype if planner else "COMPANION",
            "current_goal": planner.current_goal if planner else "IDLE",
            "plan": planner.current_plan if planner else [],
            "state": planner.state if planner else {},
            "milestones": planner.milestones[-5:] if planner else []
        }

    def send_action(self, bot_id: str, action: str, params: Optional[Dict[str, Any]] = None) -> bool:
        if bot_id in self.bots:
            return self.bots[bot_id].send_action(action, params)
        return False

    def send_chat(self, bot_id: str, message: str) -> bool:
        if bot_id in self.bots:
            return self.bots[bot_id].send_chat(message)
        return False

    def _start_ticker(self):
        """Background thread executing periodic autonomous goal evaluation."""
        def _ticker_worker():
            while self._running:
                try:
                    for bid, bot_proc in list(self.bots.items()):
                        if not bot_proc.process or bot_proc.process.poll() is not None:
                            continue
                        planner = bot_proc.planner
                        # Evaluate tactical gameplay plan
                        decision = planner.evaluate_plan()
                        act = decision.get("action")
                        params = decision.get("params", {})
                        if act and act not in ("sleep", "idle"):
                            bot_proc.send_action(act, params)

                        # Ambient in-character commentary
                        comment = planner.generate_in_character_comment()
                        if comment:
                            bot_proc.send_chat(comment)
                except Exception:
                    pass
                time.sleep(10.0)

        t = threading.Thread(target=_ticker_worker, daemon=True)
        t.start()

# Global manager instance
mc_manager = MinecraftManager()
