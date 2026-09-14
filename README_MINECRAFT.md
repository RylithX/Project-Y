# 🎮 Minecraft Real-Player Autonomous Bot — Complete Setup & Usage Guide

Transform your Discord AI bot into an **autonomous, human-like Minecraft player** powered by [Mineflayer](https://github.com/PrismarineJS/mineflayer), 3D A* Parkour Pathfinding, PvP combat, auto-eating, resource gathering, recipe crafting, and a real-time LLM decision engine.

---

## 🌟 Features & Human-Like Behaviors

- 🧠 **Autonomous Self-Driving Progression AI**:
  - When idle without player orders, it naturally progresses the game through tech milestones (Chops Wood ➔ Crafts Tables/Tools ➔ Mines Stone ➔ Hunts Food & Wool ➔ Mines Iron ➔ Smelts Ingots ➔ Crafts Armor & Shield ➔ Mines Diamonds).
  - **Journal & To-Do Memory System (`journal.json`)**: Keeps track of active survival goals, completed milestones, lifetime stats, and lessons learned from mistakes and deaths!
- ⚔️ **Advanced PvP & Combat Engine (`mineflayer-pvp`)**:
  - Automatically equips the best weapon (Netherite > Diamond > Iron > Stone > Wood) and Shield in off-hand.
  - Automatically defends against mobs/players upon taking damage.
  - Blocks incoming skeleton arrows with shields, attacks with proper weapon cooldown timing, and strafes targets.
- 🔨 **Multi-Step Recursive Auto-Crafting**:
  - Solves recipe dependencies (e.g. Logs ➔ Planks ➔ Sticks ➔ Pickaxes/Swords).
  - Automatically places a crafting table from inventory (or crafts one if needed), stands next to it to craft 3x3 grid recipes, and gathers items!
- 🛏️ **Smart Bed Placement & Sleep**:
  - Checks if a bed is placed in the world. If none is placed, **places a bed directly from inventory onto the floor**, sleeps through the night, and retrieves the bed back upon waking!
- 🎁 **Proximity Item Giving**:
  - Walks up to the player, looks directly at them, cleanly tosses requested items/stacks, and crouch-greets.
- 🏃 **3D Parkour & Pathfinding (`mineflayer-pathfinder`)**: Jump-sprints across gaps, pillars up walls, climbs ladders, swims in water, bridges over cliffs, and opens doors.
- 🍖 **Survival Instincts (`mineflayer-auto-eat` & `mineflayer-armor-manager`)**:
  - Automatically eats food from inventory when hunger is low (`food < 16`) or damaged.
  - Automatically equips the best armor pieces (helmet, chestplate, leggings, boots).
- 💥 **Danger Awareness & Self-Preservation**:
  - **Creeper Detection**: Immediately sprints backwards away if an ignited/flashing creeper gets within 4.5 blocks.
- ✨ **Human Body Language & Emotes**:
  - **Sneak-Spam Greeting**: Rapidly crouches and uncrouches (the universal friendly Minecraft player greeting) when meeting players or saying hello.
  - **Ambient Gaze**: Turns head to look around its surroundings and glances at nearby players naturally.
  - **Emotes**: Nodding, head shaking, jumping for joy.
- 💬 **In-Game Chat AI**: In-game player chat mentioning the bot is processed with the LLM to generate in-character replies in Minecraft chat and trigger in-world actions.

---

## 📋 Compatibility & Requirements

| Requirement | Details |
| :--- | :--- |
| **Game Edition** | **Minecraft Java Edition** (Vanilla, Spigot, Paper, Fabric, Purpur, Forge) |
| **Game Versions** | **1.8.x through 1.20.4+** |
| **Server Types** | Localhost / LAN, Dedicated Servers, Aternos, FalixNodes, Shockbyte, etc. |
| **Authentication** | `offline` (Cracked / LAN / Non-Premium) or `microsoft` (Online Auth) |
| **Runtime** | Node.js 18+ / 20+ / 22+ & Python 3.10+ |

---

## 🚀 Quick Setup Guide

### 1. Install Node.js Dependencies

On **Termux (Android)** or **Linux**:
```bash
# Install Node.js if not already installed
pkg install nodejs -y    # On Termux
# or: sudo apt install nodejs npm -y   # On Ubuntu/Debian

# Install the Mineflayer plugins natively
npm --prefix /data/data/com.termux/files/home install --no-audit --no-fund \
  mineflayer \
  mineflayer-pathfinder \
  mineflayer-pvp \
  mineflayer-auto-eat \
  mineflayer-armor-manager \
  mineflayer-collectblock \
  vec3 \
  debug
```

---

### 2. Configure Server Connection

You can configure the server settings via **Web Dashboard** or directly in [`config.json`](file:///storage/emulated/0/discord-bot/config.json) / [`bots.json`](file:///storage/emulated/0/discord-bot/bots.json):

```json
{
  "minecraft_enabled": true,
  "minecraft_server": "localhost",
  "minecraft_port": 25565,
  "minecraft_username": "YunaBot",
  "minecraft_version": "1.20.4",
  "minecraft_edition": "java",
  "minecraft_auth": "offline",
  "minecraft_auto_reconnect": true,
  "minecraft_channel": "123456789012345678"
}
```

#### Configuration Options Explained:
- `minecraft_enabled` (`bool`): Set to `true` to enable Minecraft features.
- `minecraft_server` (`string`): The IP address or domain of the Minecraft server (e.g. `localhost`, `192.168.1.100`, `myserver.aternos.me`).
- `minecraft_port` (`int`): Server port (default Java port is `25565`).
- `minecraft_username` (`string`): The in-game player name for the bot (e.g. `YunaBot`).
- `minecraft_version` (`string`): Specific game version (e.g. `1.20.4`, `1.19.2`, `1.16.5`) or leave empty string `""` for auto-detection.
- `minecraft_auth` (`string`):
  - `"offline"`: For cracked servers, LAN worlds, or servers with `online-mode=false`.
  - `"microsoft"`: For official Microsoft accounts on premium servers (will prompt for Microsoft device login).
- `minecraft_channel` (`string` or `null`): Discord Text Channel ID where in-game chat messages and events are broadcast.

---

## 🎮 How to Control the Bot

### 🌐 Method 1: Web Dashboard (Visual Control)
1. Open your browser and go to `http://<device-ip>:5000`.
2. Open the **⚙️ Settings** paper panel.
3. Scroll to **Minecraft Real-Player Bot**.
4. Enter your server IP, port, and bot username.
5. Click **▶ START BOT** to connect, or **⏹ STOP BOT** to disconnect.

---

### ⚡ Method 2: Discord Slash Commands (`/mc`)

| Command | Target / Arguments | Description | Example |
| :--- | :--- | :--- | :--- |
| `/mc action:start` | — | Starts and connects the Minecraft bot | `/mc start` |
| `/mc action:stop` | — | Disconnects the Minecraft bot | `/mc stop` |
| `/mc action:status` | — | Displays live coords, health ❤️, hunger 🍖, current task & inventory | `/mc status` |
| `/mc action:journal` | — | Displays active To-Do list, milestones, stats & lessons learned | `/mc journal` |
| `/mc action:follow` | `target: <username>` | Dynamically pathfinds and follows a player | `/mc follow target:Steve` |
| `/mc action:mine` | `target: <block_name>` | Mines and gathers blocks | `/mc mine target:oak_log` |
| `/mc action:craft` | `target: <item_name>` | Solves dependencies, places table, and crafts item | `/mc craft target:wooden_pickaxe` |
| `/mc action:give` | `target: <item> [player]` | Approaches player and tosses item stack | `/mc give target:iron_ingot Steve` |
| `/mc action:attack` | `target: <mob/player>` | Engages target in melee PvP with shield defense | `/mc attack target:zombie` |
| `/mc action:sleep` | — | Sleeps in bed (places bed from inventory if needed) | `/mc sleep` |
| `/mc action:emote` | `target: sneak_spam\|nod\|shake\|jump` | Triggers a body language gesture | `/mc emote target:sneak_spam` |
| `/mc action:chat` | `target: <message>` | Sends a message into Minecraft server chat | `/mc chat target:Hello world!` |
| `/mc action:goal` | `target: <natural goal>` | Uses LLM to plan and execute multi-step actions | `/mc goal target:Chop some wood and protect me` |

---

### 💬 Method 3: Discord Prefix Commands (`!mc`)

You can use text prefix commands anywhere in your server. Works for single-bot and multi-bot configurations:

```text
# General / Active Bot:
!mc start
!mc stop
!mc status
!mc journal
!mc follow Steve
!mc mine oak_log 5
!mc craft wooden_pickaxe
!mc give iron_ingot 5 Steve
!mc attack skeleton
!mc sleep
!mc emote sneak_spam
!mc chat Hello everyone!
!mc goal Gather some iron and make a sword

# Multi-Bot Target Specific Bots:
!mc law status
!mc yuna journal
!mc law start
!mc law mine oak_log 10
!mc law goal explore the cave
!law mc status

# Control All Bots Simultaneously:
!mc all status
!mc all journal
!mc all start
!mc all stop
```

---

### 🗣️ Method 4: Talking Directly In-Game (AI Persona Chat)

When you are playing in the Minecraft server with the bot, you can speak directly in Minecraft chat:

- **Greeting**: Type `hi yuna` or `hello Yuna` in chat ➔ The bot will perform a sneak-spam crouch greeting and reply in chat!
- **Follow Me**: Type `Yuna come here and follow me` ➔ The bot will pathfind to you and follow you smoothly.
- **Resource Request**: Type `Yuna mine some wood for us` ➔ The bot will locate nearby trees and start chopping.
- **Combat Assistance**: Type `Yuna help attack this zombie` ➔ The bot will engage the mob with its weapon.
- **Sleeping**: Type `Yuna let's sleep` ➔ The bot will find a bed and sleep through the night.

---

## 🛠️ Troubleshooting & FAQs

### Q1: The bot fails to connect or says "Connection Refused"
- Ensure your Minecraft server is running and accessible from the bot's device.
- If running on a local PC, make sure you use the PC's local IP address (e.g. `192.168.1.50`), not `127.0.0.1` or `localhost` if running from Termux/mobile.
- Verify that Windows Firewall / router isn't blocking port `25565`.

### Q2: "Kicked: Invalid Session" or "Not Authenticated with Minecraft.net"
- If your server has `online-mode=true` in `server.properties`, either:
  1. Set `online-mode=false` in your `server.properties` (for offline/cracked mode), OR
  2. Set `"minecraft_auth": "microsoft"` in [`config.json`](file:///storage/emulated/0/discord-bot/config.json).

### Q3: How do I make the bot bridge messages to Discord?
- Put your Discord channel ID in `"minecraft_channel"` in [`config.json`](file:///storage/emulated/0/discord-bot/config.json).
- In-game player chat messages will automatically be forwarded to that Discord channel.

### Q4: The bot gets stuck on obstacles or cliffs
- The bot uses 3D A* pathfinding. Make sure the bot has blocks in inventory (dirt, cobblestone) so it can pillar up or bridge across gaps if necessary.
