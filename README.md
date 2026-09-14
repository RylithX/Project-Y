# 🤖 Discord AI Bot // Multi-Provider Intelligence & 3D VTuber Platform

A high-performance Discord AI platform featuring **multi-provider LLM intelligence**, **3D VTuber VRM avatar synchronization**, **real-time voice channel transcription & emotion TTS**, **long-term persistent memory**, and an **architectural Drafting Desk web dashboard**.

---

## 🌟 Key Highlights & Core Capabilities

### 🧠 Multi-Provider AI Brain & Vision
- **Multi-Engine Intelligence**: Seamless support for **Google Gemini** (`gemini-3.6-flash`, `gemini-3.1-flash-lite`), **Groq** (`llama-3.3-70b-versatile`), and **OpenRouter** (`nvidia/nemotron-3-ultra-550b-a55b:free`, custom models) with intelligent auto-fallback.
- **Multimodal Vision & Video Understanding**: Real-time image recognition and frame-by-frame video understanding with audio track extraction.
- **Dynamic Web Search**: DuckDuckGo live search with natural AI synthesis and source citations.
- **Human-Like Message Splitting**: Configurable typing delays and multi-bubble message responses.
- **Document & File Reader**: Text extraction support for **PDF** (PyMuPDF / PyPDF2 / pdfplumber), **DOCX**, **CSV**, and code files up to 70MB.

### 🎙️ Voice, Emotion TTS & 3D VTuber Engine
- **Voice Channel (VC) Live Listening**: Real-time voice transcription using Groq Whisper, reasoning, and audio response playback.
- **Fish Audio Emotion TTS**: Expressive voice synthesis (`s2.1-pro-free`) with real-time emotion tag delivery (`(excited)`, `(whisper)`, `(sad)`, `(angry)`, `(confident)`, `(nervous)`).
- **3D VRM VTuber Bridge**: Built-in WebSocket server (`ws://localhost:8765`) streaming live audio, viseme lip-sync, and facial expressions to [`vrm_viewer.html`](file:///data/data/com.termux/files/home/antigravity-workspace/discord-bot/vrm_viewer.html) with 3D avatars (e.g. `yuna.vrm`).

### 📚 Memory & Persona Engine
- **Long-Term Memory Persistence**: `/summarize` condenses channel history into persistent knowledge bases stored in `memories/<bot_id>/`.
- **User Memory & Profiling**: Automatically tracks interaction history, user preferences, and custom personas (`/persona`, `/memory`).
- **Rich Discord Presence**: Dynamic activity rotation with customizable music track/artist broadcast.

### 🌐 Architectural Drafting Desk Web Dashboard
- **Web Control Center**: Hosted locally at `http://localhost:5000` with blueprints, sticky notes, and terminal telemetry.
- **Multi-Bot Profile Manager**: Create, switch, and configure multiple isolated bot instances (`bots.json`) on the fly.
- **Live Settings Editor**: Real-time updates for personalities, provider keys, temperature, and tokens.

---

## 🛠️ Slash & Prefix Commands Reference

### ⚡ Slash Commands (`/`)
| Command | Arguments | Description | Permission |
| :--- | :--- | :--- | :--- |
| `/ask` | `prompt`, `[image]` | Chat directly with the active AI bot | Everyone |
| `/search` | `query` | Search the web using DuckDuckGo with AI synthesis | Everyone |
| `/memory` | — | Display your stored user profile and memory facts for this bot | Everyone |
| `/persona` | `notes` | Set personal notes/facts for this bot to remember | Everyone |
| `/forgetme` | `[scope: this_bot\|all_bots]` | Wipe all stored facts, quotes, and memories about you | Everyone |
| `/summarize` | `[limit]` | Summarize recent channel chat into long-term memory | Everyone |
| `/transcribe` | — | Transcribe the most recent voice message in the channel | Everyone |
| `/vtuber` | `action`, `[emotion]` | Control VTuber expressions and WebSocket bridge | Everyone |
| `/presence` | `status`, `[artist]` | Update bot activity status and listening music | Everyone |
| `/mc` | `action`, `[target]` | Real-Player Minecraft bot controls (start, stop, status, follow, mine, craft, attack, sleep, emote, chat, goal) | Everyone |
| `/reset` | — | Clear current channel conversation context | Everyone |
| `/vc` | `join`/`leave`/`start`/`stop` | Voice channel transcription & listening controls | **Owner** |
| `/sync` | — | Force global re-synchronization of slash commands | **Owner** |
| `/purgeall` | — | Purge all conversation context memory globally | **Owner** |

### 💬 Text Prefix Commands
- `!mc <action> [args]` — Minecraft autonomous bot controls (`start`, `stop`, `status`, `follow`, `mine`, `craft`, `attack`, `sleep`, `emote`, `chat`, `goal`)
- `!forgetme` / `!forgetme all` — Wipe individual bot memory or global memory
- `!memory` — View remembered facts and quotes for the current bot
- `!sync` — Global slash command sync
- `!sync here` — Guild-specific slash command sync
- `!testopenai` — Health check for OpenAI API (GPT-4o / GPT-4o-mini)
- `!testdeepseek` — Health check for DeepSeek API (DeepSeek-V3 / DeepSeek-R1)
- `!testgemini` — Health check for Google Gemini API
- `!testgroq` — Health check for Groq API
- `!testmistral` — Health check for Mistral AI API
- `!testopenrouter` — Health check for OpenRouter API
- `!reset` — Clear channel context memory
- `!purgeall` — Global memory purge
- `!search <query>` — Manual DuckDuckGo web search

👉 **For the full Minecraft guide, see [`README_MINECRAFT.md`](./README_MINECRAFT.md)**

---

## 📦 Installation & Setup

### 1. Prerequisites
Ensure you have **Python 3.10+** and **FFmpeg** installed.

#### On Termux (Android):
```bash
pkg update && pkg upgrade -y
pkg install python ffmpeg git -y
```

#### On Linux / Ubuntu / Debian:
```bash
sudo apt update && sudo apt install python3 python3-pip ffmpeg git -y
```

---

### 2. Install Python Dependencies
```bash
# Core Discord & Web Dashboard
pip install discord.py python-dotenv aiohttp flask websockets

# Voice, Audio & TTS
pip install PyNaCl discord-ext-voice-recv

# PDF & Document Processing (Termux compatible)
pip install PyPDF2 pymupdf pdfplumber
```

---

### 3. Environment Variables (`.env`)
Create a `.env` file in the project root:

```env
# Discord Configuration
DISCORD_TOKEN=your_discord_bot_token
OWNER_ID=your_discord_user_id

# AI Providers (Provide at least one, or configure via Web Dashboard)
OPENAI_KEY=your_openai_api_key
DEEPSEEK_KEY=your_deepseek_api_key
GEMINI_KEY=your_gemini_api_key
GROQ_KEY=your_groq_api_key
MISTRAL_KEY=your_mistral_api_key
OPENROUTER_KEY=your_openrouter_api_key

# Fish Audio TTS (Optional)
FISH_AUDIO_KEY=your_fish_audio_api_key

# Optional default bot profile ID
# BOT_ID=bot_ek0ldel3
```

---

### 4. Running the Bot
```bash
python3 bot.py
```

Upon launching:
1. The Discord bot connects and logs in with its active identity.
2. The **Web Dashboard** starts at `http://localhost:5000`.
3. The **VTuber WebSocket Server** starts at `ws://localhost:8765`.

---

## 📂 Project Architecture

```
discord-bot/
├── bot.py                  # Core engine, Discord events, AI handlers & Flask API
├── config.json             # Global runtime settings & active personality
├── bots.json               # Multi-bot profile registry
├── dashboard.html          # Drafting Desk web UI (served on port 5000)
├── vrm_viewer.html         # Three.js 3D VTuber avatar renderer
├── yuna.vrm                # 3D VRM humanoid avatar model
├── user_profiles.json      # User memory profiles & persona notes
├── contexts.json           # Active per-channel conversational context
├── memories/               # Long-term summarized memory databases
│   └── bot_ek0ldel3/       # Per-bot indexed knowledge
└── package.json            # Web assets & dependencies
```

---

## 🌐 Web Dashboard Features

Navigate to `http://localhost:5000` to access:
- 🗂️ **Status Radar**: Live message counters, uptime, and latency.
- 🤖 **Bot Manager**: Switch between custom personalities on the fly.
- ⚙️ **Settings Desk**: Adjust temperature, token limits, and TTS voice IDs.
- 🔀 **Provider Matrix**: Real-time provider health tests (Gemini, Groq, OpenRouter).
- 🐛 **Context Inspector**: View active conversational memory and clear specific channels.
- 🎭 **VRM Studio**: Direct link to the 3D VTuber viewer with live lip-sync.

---

## 🎭 3D VTuber Setup

1. Enable `vtuber_enabled: true` in [`config.json`](file:///data/data/com.termux/files/home/antigravity-workspace/discord-bot/config.json) or through the web dashboard.
2. Open [`http://localhost:5000/vrm_viewer.html`](http://localhost:5000/vrm_viewer.html) in any modern browser.
3. The 3D avatar will automatically connect to `ws://localhost:8765`, speaking and emoting in sync with Discord voice chat and TTS responses.

---

## 📜 License & Credits

Built with ❤️ for Termux, Linux servers, and everywhere in between.
Licensed under the **MIT License**.
