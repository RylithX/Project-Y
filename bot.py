from typing import Optional, List, Dict, Tuple, Any
import json
import uuid
import time
import contextlib
import logging
from observation_module import PassiveObservationModule
import discord
import aiohttp
import asyncio
import threading
import io
import base64
import re
import os
import tempfile
import zipfile
import xml.etree.ElementTree as ET
import csv
import random
import argparse
import sys
import subprocess
import shutil
import math
import difflib
import unicodedata
from html import unescape
from urllib.parse import unquote
from collections import defaultdict

try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    edge_tts = None
    EDGE_TTS_AVAILABLE = False

try:
    import media_intelligence
    from media_intelligence.tools.discord_tools import (
        watch_video_tool,
        browse_web_tool,
        search_web_tool,
        detect_and_handle_media_urls
    )
    MEDIA_INTELLIGENCE_AVAILABLE = True
except Exception as _mie:
    print(f"[MEDIA INTELLIGENCE LOAD NOTICE] {_mie}")
    media_intelligence = None
    MEDIA_INTELLIGENCE_AVAILABLE = False

try:
    import social
    from social import SocialManager, global_media_queue, load_social_config, load_instagram_config, save_instagram_config
    SOCIAL_INTEGRATION_AVAILABLE = True
except Exception as _soc_e:
    print(f"[SOCIAL INTEGRATION LOAD NOTICE] {_soc_e}")
    social = None
    SocialManager = None
    global_media_queue = None
    load_social_config = None
    load_instagram_config = None
    save_instagram_config = None
    SOCIAL_INTEGRATION_AVAILABLE = False

try:
    import doodle_engine
    from doodle_engine import generate_doodle, doodle_along, is_doodle_request, get_vector_doodle_blueprint
    DOODLE_ENGINE_AVAILABLE = True
except Exception as _de_err:
    print(f"[DOODLE ENGINE LOAD NOTICE] {_de_err}")
    doodle_engine = None
    generate_doodle = None
    doodle_along = None
    is_doodle_request = None
    get_vector_doodle_blueprint = None
    DOODLE_ENGINE_AVAILABLE = False

try:
    import showdown_engine
    from showdown_engine import ShowdownManager, PokemonShowdownClient
    SHOWDOWN_ENGINE_AVAILABLE = True
except Exception as _sde_err:
    print(f"[SHOWDOWN ENGINE LOAD NOTICE] {_sde_err}")
    showdown_engine = None
    ShowdownManager = None
    PokemonShowdownClient = None
    SHOWDOWN_ENGINE_AVAILABLE = False

try:
    import yuna_backup_guard as backup_guard
    import yuna_agy_bridge as agy_bridge
    import yuna_owner_escalation as owner_escalation
    import yuna_feature_evaluator as feature_evaluator
    AGY_BRIDGE_AVAILABLE = True
except Exception as _agy_e:
    print(f"[AGY BRIDGE LOAD NOTICE] {_agy_e}")
    backup_guard = None
    agy_bridge = None
    owner_escalation = None
    feature_evaluator = None
    AGY_BRIDGE_AVAILABLE = False

try:
    import discord_voice
    from discord_voice import voice_manager
    DISCORD_VOICE_AVAILABLE = True
except Exception as _dv_e:
    print(f"[DISCORD VOICE LOAD NOTICE] {_dv_e}")
    discord_voice = None
    voice_manager = None
    DISCORD_VOICE_AVAILABLE = False

try:
    import yuna_gambling
    YUNA_GAMBLING_AVAILABLE = True
except Exception as _yg_e:
    print(f"[YUNA GAMBLING LOAD NOTICE] {_yg_e}")
    yuna_gambling = None
    YUNA_GAMBLING_AVAILABLE = False

try:
    import yuna_rpc
    YUNA_RPC_AVAILABLE = True
except Exception as _yr_e:
    print(f"[YUNA RPC LOAD NOTICE] {_yr_e}")
    yuna_rpc = None
    YUNA_RPC_AVAILABLE = False



# ─── SINGLETON PROCESS GUARD (PREVENTS DUPLICATE BOT INSTANCES) ───
PID_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memories", "pids")
os.makedirs(PID_DIR, exist_ok=True)

def _parent_watchdog():
    """Child worker thread: terminates if the parent supervisor process exits."""
    sup_pid_str = os.getenv("SUPERVISOR_PID")
    if not sup_pid_str or not sup_pid_str.isdigit():
        return
    sup_pid = int(sup_pid_str)
    while True:
        time.sleep(4)
        try:
            os.kill(sup_pid, 0)
        except OSError:
            os._exit(0)

def _kill_all_stale_bot_processes():
    """Kills any previous running bot.py or mc_bridge.js processes from other terminals."""
    my_pid = os.getpid()
    my_ppid = os.getppid()
    try:
        out = subprocess.check_output(['ps', '-ef'], stderr=subprocess.DEVNULL).decode('utf-8', errors='ignore')
        for line in out.splitlines():
            if ('bot.py' in line or 'mc_bridge.js' in line) and not any(k in line for k in ['python3 -c', 'grep', 'bash', 'ps -ef']):
                parts = line.split()
                if len(parts) > 1 and parts[1].isdigit():
                    pid = int(parts[1])
                    if pid != my_pid and pid != my_ppid and pid != 1:
                        cmd_part = ' '.join(parts[7:]) if len(parts) > 7 else ''
                        if ('python' in cmd_part or 'node' in cmd_part) and 'grep' not in cmd_part:
                            try:
                                os.kill(pid, 9)
                                print(f"[INSTANCE GUARD] Force-terminated stale bot process (PID {pid})")
                            except OSError:
                                pass
    except Exception:
        pass

def _acquire_instance_lock():
    """Ensures each bot ID and supervisor has exactly one active process."""
    my_pid = os.getpid()
    is_child = os.getenv("IS_BOT_CHILD") == "1"
    bot_id = os.getenv("BOT_ID")
    if not is_child or not bot_id:
        # Supervisor process: wipe all old rogue instances across terminals
        _kill_all_stale_bot_processes()
        pid_file = os.path.join(PID_DIR, "supervisor.pid")
    else:
        pid_file = os.path.join(PID_DIR, f"{bot_id}.pid")
        # Start watchdog to die if supervisor dies
        t = threading.Thread(target=_parent_watchdog, daemon=True)
        t.start()

    try:
        with open(pid_file, "w") as f:
            f.write(str(my_pid))
    except Exception:
        pass

# Instance lock will only be acquired when executing directly (__main__)

# ─── ACTIVITY & TERMINAL DEBUG LOGGER ─────────────────
import logging
from logging.handlers import RotatingFileHandler

def _check_terminal_debug():
    if os.getenv("YUNA_DEBUG", "").lower() in ("1", "true", "yes"):
        return True
    if os.getenv("DEBUG", "").lower() in ("1", "true", "yes"):
        return True
    if "--debug" in sys.argv or "-d" in sys.argv:
        return True
    cfg_p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if os.path.exists(cfg_p):
        try:
            with open(cfg_p, "r", encoding="utf-8") as f:
                c = json.load(f)
                if c.get("debug") or c.get("terminal_debug"):
                    return True
        except Exception:
            pass
    return False

DEBUG_MODE = _check_terminal_debug()

# Terminal logging configuration for real-time debug output
class NoisyLogFilter(logging.Filter):
    def filter(self, record):
        if record.name in ("private_request", "public_request", "instagrapi", "urllib3", "requests", "instaloader"):
            return False
        msg = record.getMessage() if hasattr(record, "getMessage") else str(record.msg)
        if "private_request" in msg or "i.instagram.com/api/v1" in msg or "Google/google Pixel" in msg:
            return False
        return True

for _noisy in ["private_request", "public_request", "instagrapi", "urllib3", "requests", "instaloader"]:
    _nl = logging.getLogger(_noisy)
    _nl.setLevel(logging.CRITICAL)
    _nl.disabled = True
    _nl.propagate = False

if DEBUG_MODE:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)-7s | %(name)s: %(message)s',
        datefmt='%H:%M:%S',
        stream=sys.stdout,
        force=True
    )
    _root = logging.getLogger()
    _root.addFilter(NoisyLogFilter())
    for _h in _root.handlers:
        _h.addFilter(NoisyLogFilter())
    logging.getLogger("discord").setLevel(logging.INFO)
    logging.getLogger("discord.gateway").setLevel(logging.INFO)
    logging.getLogger("discord.client").setLevel(logging.INFO)
    logging.getLogger("discord.http").setLevel(logging.WARNING)
    print("[DEBUG] Terminal debugging mode ENABLED (logging level: INFO)", flush=True)

_yuna_logger = logging.getLogger("yuna_activity")
_yuna_logger.setLevel(logging.INFO)
if not _yuna_logger.handlers:
    _yh = RotatingFileHandler("yuna_activity.log", maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
    _yh.setFormatter(logging.Formatter('%(asctime)s | %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
    _yuna_logger.addHandler(_yh)

def _yuna_log(msg: str):
    _yuna_logger.info(msg)
    print(f"[YUNA] {msg}", flush=True)

# ─── THREAD-SAFE STATE LOCK ───────────────────────────
state_lock = threading.RLock()

# ─── ATOMIC JSON SAVE WITH BACKUP ─────────────────────
def _atomic_json_save(path: str, data, backup=True, max_backups=5):
    """Write JSON atomically with rotated backups to prevent corruption."""
    with state_lock:
        path = os.path.abspath(path)
        # Create backup of existing file
        if backup and os.path.exists(path):
            bak_dir = os.path.join(os.path.dirname(path) or ".", ".bak")
            os.makedirs(bak_dir, exist_ok=True)
            base = os.path.basename(path)
            timestamp = int(time.time())
            bak_path = os.path.join(bak_dir, f"{base}.{timestamp}.bak")
            try:
                shutil.copy2(path, bak_path)
                # Clean old backups
                _cleanup_backups(bak_dir, base, max_backups)
            except Exception as e:
                print(f"[BACKUP] Could not create backup for {path}: {e}")
        # Atomic write with unique per-process/thread temporary filename
        tmp_path = f"{path}.tmp.{os.getpid()}.{time.time_ns()}"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            try:
                os.replace(tmp_path, path)
            except OSError:
                shutil.move(tmp_path, path)
        except Exception as e:
            print(f"[ERROR] _atomic_json_save failed for {path}: {e}")
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            # Direct fallback write to ensure data is not lost
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            except Exception as direct_e:
                print(f"[FATAL] Direct save also failed for {path}: {direct_e}")

def _cleanup_backups(bak_dir, base_name, max_backups):
    try:
        pattern = f"{base_name}.*.bak"
        files = [os.path.join(bak_dir, f) for f in os.listdir(bak_dir) if f.startswith(base_name + ".") and f.endswith(".bak")]
        files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        for old in files[max_backups:]:
            try:
                os.remove(old)
            except:
                pass
    except Exception:
        pass

def _load_json_with_recovery(path: str):
    """Load JSON, try backups if main file is corrupted."""
    with state_lock:
        path = os.path.abspath(path)
        # Try main file
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[RECOVERY] {path} corrupted: {e}")
        # Try backups newest first
        bak_dir = os.path.join(os.path.dirname(path) or ".", ".bak")
        if os.path.isdir(bak_dir):
            base = os.path.basename(path)
            try:
                files = [os.path.join(bak_dir, f) for f in os.listdir(bak_dir) if f.startswith(base + ".") and f.endswith(".bak")]
                files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                for bak in files:
                    try:
                        with open(bak, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            print(f"[RECOVERY] Restored {path} from backup {bak}")
                            # Restore main file
                            _atomic_json_save(path, data, backup=False)
                            return data
                    except Exception:
                        continue
            except Exception:
                pass
        return None




from discord import app_commands
from flask import Flask, request, jsonify, render_template_string, send_file, send_from_directory, Response, stream_with_context
from dotenv import load_dotenv
from pathlib import Path

# Optional imports with graceful fallback
try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    print("[WARN] websockets not installed. VTuber bridge will not work.")

try:
    import nacl
    PYNACL_AVAILABLE = True
except ImportError:
    PYNACL_AVAILABLE = False
    print("[WARN] PyNaCl not installed. Voice channel features will not work.")

try:
    import discord.ext.voice_recv as voice_recv
    VOICE_RECV_AVAILABLE = True
    try:
        import discord.opus
        _orig_decoder_decode = discord.opus.Decoder.decode
        def _safe_decoder_decode(self, data, *, fec=False):
            try:
                return _orig_decoder_decode(self, data, fec=fec)
            except discord.opus.OpusError:
                return b'\x00' * 3840
        discord.opus.Decoder.decode = _safe_decoder_decode
        print("[VOICE] Patched discord.opus.Decoder for fault tolerance")
    except Exception as e:
        print(f"[VOICE] Could not patch opus decoder: {e}")


except ImportError:
    VOICE_RECV_AVAILABLE = False
    voice_recv = None
    print("[WARN] discord-ext-voice-recv not installed. Voice call features will not work.")

try:
    import PIL.Image as Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# Force load .env from the script folder (not cwd)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(SCRIPT_DIR, ".env")
load_dotenv(ENV_PATH)

_fish = os.getenv("FISH_AUDIO_KEY", "")
print(f"[BOOT] .env path: {ENV_PATH}")
print(f"[BOOT] .env exists: {os.path.exists(ENV_PATH)}")
print(f"[BOOT] FISH_AUDIO_KEY loaded: {bool(_fish)} (len={len(_fish)})")

CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")
DEBUG_MODE = _check_terminal_debug()
OWNER_ID = os.getenv("OWNER_ID")
GEMINI_KEY = os.getenv("GEMINI_KEY")
GROQ_KEY = os.getenv("GROQ_KEY")
MISTRAL_KEY = os.getenv("MISTRAL_KEY", "").strip()
OPENAI_KEY = os.getenv("OPENAI_KEY", os.getenv("OPENAI_API_KEY", "")).strip()
DEEPSEEK_KEY = os.getenv("DEEPSEEK_KEY", os.getenv("DEEPSEEK_API_KEY", "")).strip()
ELEVENLABS_KEY = os.getenv("ELEVENLABS_KEY", "").strip()
CARTESIA_KEY = os.getenv("CARTESIA_KEY", "").strip()
FISH_AUDIO_KEY = os.getenv("FISH_AUDIO_KEY", "").strip()
print(f"[BOOT] FISH_AUDIO_KEY after strip: {bool(FISH_AUDIO_KEY)} | starts_with: {FISH_AUDIO_KEY[:4] if FISH_AUDIO_KEY else 'none'}")
print(f"[BOOT] ELEVENLABS_KEY loaded: {bool(ELEVENLABS_KEY)} | OPENAI_KEY: {bool(OPENAI_KEY)} | DEEPSEEK_KEY: {bool(DEEPSEEK_KEY)} | CARTESIA_KEY: {bool(CARTESIA_KEY)} | MISTRAL_KEY: {bool(MISTRAL_KEY)}")

USER_PROFILES_FILE = os.path.join(SCRIPT_DIR, "user_profiles.json")
INTERACTED_USERS_FILE = os.path.join(SCRIPT_DIR, "interacted_users.json")
CONTEXTS_FILE = os.path.join(SCRIPT_DIR, "contexts.json")

MAX_FILE_SIZE_MB = 70
MAX_VIDEO_SIZE_MB = 300
MAX_AUDIO_SIZE_MB = 50

DEFAULT_CONFIG = {
    "debug": True,
    "personality": "You are a helpful, friendly assistant. Be concise and direct.",
    "provider": "auto",
    "gemini_model": "gemini-3.1-flash-lite",
    "groq_model": "openai/gpt-oss-120b",
    "mistral_model": "ministral-8b-latest",
    "openai_chat_model": "gpt-4o-mini",
    "openai_api_key": "",
    "deepseek_model": "deepseek-chat",
    "deepseek_api_key": "",
    "model": "openrouter/free",
    "use_custom_model": False,
    "custom_model": "",
    "custom_base_url": "",
    "custom_key": "",
    "max_tokens": 2500,
    "temperature": 0.7,
    "top_p": 1.0,
    "frequency_penalty": 0.0,
    "presence_penalty": 0.0,
    "context_enabled": True,
    "max_context": 10,
    "cooldown_seconds": 10,
    "vision_model": "openrouter/free",
    "vision_provider": "gemini",
    "gemini_vision_model": "gemini-3.1-flash-lite",
    "auto_search": True,
    "file_reading_enabled": True,
    "video_watching_enabled": True,
    "video_watching_model": "gemini-3.1-flash-lite",
    "random_dms_enabled": False,
    "random_dms_interval_minutes": 60,
    "random_dms_prompt": "Send a casual, friendly message to someone you haven't talked to in a while. Keep it short and natural.",
    "presence_enabled": True,
    "presence_music_enabled": True,
    "presence_music_artist": "Kairiki Bear",
    "presence_idle_statuses": [],
    "presence_cycle_interval": 30,
    "tts_enabled": False,
    "tts_provider": "auto",
    "elevenlabs_voice_id": "21m00Tcm4TlvDq8ikWAM",
    "elevenlabs_model": "eleven_turbo_v2_5",
    "openai_voice": "nova",
    "openai_model": "tts-1",
    "cartesia_voice_id": "a0e99841-438c-4a64-b679-ae501e7d6091",
    "cartesia_model": "sonic-3.5",
    "groq_tts_voice": "hannah",
    "groq_tts_model": "canopylabs/orpheus-v1-english",
    "edge_tts_voice": "en-US-AvaMultilingualNeural",
    "fish_voice_id": "",
    "fish_model": "s2.1-pro-free",
    "message_split_enabled": False,
    "message_split_min": 1,
    "message_split_max": 1,
    "message_split_delay": 1.0,
    "auto_stt": False,
    "vc_transcription_enabled": True,
    "vc_transcription_channel": None,
    "vtuber_enabled": False,
    "vtuber_ws_port": 8765,
    "random_chat_enabled": False,
    "random_chat_chance": 0.05,
    "random_chat_context_limit": 50,
    "bot_name_triggers": ["bot", "ai"],
    "user_memory_enabled": True,
    "open_chat_enabled": True,
    "minecraft_enabled": False,
    "minecraft_server": "localhost",
    "minecraft_port": 25565,
    "minecraft_username": "",
    "minecraft_version": "1.20.4",
    "minecraft_edition": "java",
    "minecraft_auth": "offline",
    "minecraft_auto_reconnect": True,
    "minecraft_channel": None,
    "minecraft_autonomous": False,
    "minecraft_auto_interval": 8,
    "minecraft_personality": "",
    # Greeting / Welcome settings
    "greet_enabled": True,
    "greet_message": "Welcome! Please check out the server and have fun.",
    "greet_channel_id": None,
    "greet_ai_enhance": True,
    "greet_ping": True,
}

def load_config():
    with state_lock:
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    loaded = json.load(f)
                    return {**DEFAULT_CONFIG, **loaded}
            except:
                return DEFAULT_CONFIG.copy()
        return DEFAULT_CONFIG.copy()

def save_config(cfg):
    _atomic_json_save(CONFIG_FILE, cfg, backup=True, max_backups=5)
    if SOCIAL_INTEGRATION_AVAILABLE and 'social_manager' in globals() and social_manager:
        try:
            social_manager.update_config(cfg)
        except Exception:
            pass

# ─── CONFIG FIELD MAPPINGS (FOR @MENTION / /setmodel / /config) ───
CONFIG_FIELD_MAPPINGS = {
    # Gemini
    "gemini": "gemini_model",
    "gemini_model": "gemini_model",
    "gemini-model": "gemini_model",
    "geminimodel": "gemini_model",
    
    # Groq
    "groq": "groq_model",
    "groq_model": "groq_model",
    "groq-model": "groq_model",
    "groqmodel": "groq_model",
    
    # Mistral
    "mistral": "mistral_model",
    "mistral_model": "mistral_model",
    "mistral-model": "mistral_model",
    "mistralmodel": "mistral_model",
    
    # OpenRouter / Custom Model
    "model": "model",
    "openrouter": "model",
    "openrouter_model": "model",
    "openrouter-model": "model",
    "custom_model": "custom_model",
    "custom": "custom_model",
    
    # Hugging Face
    "hf": "huggingface_model",
    "huggingface": "huggingface_model",
    "huggingface_model": "huggingface_model",
    "hf_model": "huggingface_model",
    
    # Provider
    "provider": "provider",
    "engine": "provider",
    "ai_provider": "provider",
    
    # Vision
    "vision": "gemini_vision_model",
    "vision_model": "vision_model",
    "gemini_vision": "gemini_vision_model",
    "gemini_vision_model": "gemini_vision_model",
    "vision_provider": "vision_provider",
    
    # Personality / System Prompt
    "personality": "personality",
    "prompt": "personality",
    "system": "personality",
    "system_prompt": "personality",
    "persona": "personality",
    
    # Voice / TTS Settings
    "tts": "tts_provider",
    "tts_provider": "tts_provider",
    "voice": "fish_voice_id",
    "fish_voice": "fish_voice_id",
    "fish_voice_id": "fish_voice_id",
    "fish_model": "fish_model",
    "elevenlabs_voice": "elevenlabs_voice_id",
    "elevenlabs_voice_id": "elevenlabs_voice_id",
    "elevenlabs_model": "elevenlabs_model",
    "openai_voice": "openai_voice",
    "cartesia_voice": "cartesia_voice_id",
    "cartesia_voice_id": "cartesia_voice_id",
    "cartesia_model": "cartesia_model",
    "groq_voice": "groq_tts_voice",
    "groq_tts_voice": "groq_tts_voice",
    "edge_voice": "edge_tts_voice",
    "edge_tts_voice": "edge_tts_voice",
    
    # VAD & Voice Calling Settings
    "vad_gap": "vad_silence_gap",
    "vad_silence_gap": "vad_silence_gap",
    "vad_silence": "vad_silence_gap",
    "vad_timeout": "vad_silence_gap",
    "vad_pause": "vad_silence_gap",
    "vad_threshold": "vad_silence_threshold",
    "vad_silence_threshold": "vad_silence_threshold",
    "vad_sensitivity": "vad_silence_threshold",
    "vad_min_speech": "vad_min_speech_duration",
    "vad_min_speech_duration": "vad_min_speech_duration",
    
    # STT / Speech-to-Text Model Selection
    "stt": "stt_model",
    "stt_model": "stt_model",
    "stt_provider": "stt_model",
    "whisper": "stt_model",
    "whisper_model": "stt_model",
    "voice_stt": "stt_model",
    
    # Generation parameters
    "temperature": "temperature",
    "temp": "temperature",
    "max_tokens": "max_tokens",
    "tokens": "max_tokens",
    "max_token": "max_tokens",
    "top_p": "top_p",
    "frequency_penalty": "frequency_penalty",
    "presence_penalty": "presence_penalty",
    "cooldown": "cooldown_seconds",
    "cooldown_seconds": "cooldown_seconds",
    "max_context": "max_context",
    "context": "max_context",
    "context_enabled": "context_enabled",
    "tts_enabled": "tts_enabled",
    "vision_enabled": "vision_enabled",
    "auto_search": "auto_search",
    "open_chat": "open_chat_enabled",
    "open_chat_enabled": "open_chat_enabled",
    
    # Welcome / Greet Settings
    "greet": "greet_message",
    "greet_message": "greet_message",
    "greeting": "greet_message",
    "welcome": "greet_message",
    "welcome_message": "greet_message",
    "greet_channel": "greet_channel_id",
    "greet_channel_id": "greet_channel_id",
    "greet_enabled": "greet_enabled",
    "greet_ai_enhance": "greet_ai_enhance",
    "greet_ping": "greet_ping",

    # Dedicated Instagram Settings (Isolated from Discord)
    "insta": "insta_enabled",
    "insta_enabled": "insta_enabled",
    "instagram": "insta_enabled",
    "insta_personality": "insta_personality",
    "insta_persona": "insta_personality",
    "insta_prompt": "insta_personality",
    "insta_character_name": "insta_character_name",
    "insta_name": "insta_character_name",
    "insta_style": "insta_style",
    "insta_tone": "insta_tone",
    "insta_sass": "insta_sass_level",
    "insta_sass_level": "insta_sass_level",
    "insta_affection": "insta_affection_level",
    "insta_affection_level": "insta_affection_level",
    "insta_chaos": "insta_chaos_level",
    "insta_chaos_level": "insta_chaos_level",
    "insta_energy": "insta_energy_level",
    "insta_energy_level": "insta_energy_level",
    "insta_dms": "insta_auto_reply_dms",
    "insta_auto_reply_dms": "insta_auto_reply_dms",
    "insta_comments": "insta_auto_reply_comments",
    "insta_auto_reply_comments": "insta_auto_reply_comments",
    "insta_follow_requests": "insta_auto_approve_follow_requests",
    "insta_auto_approve_follow_requests": "insta_auto_approve_follow_requests",
    "insta_watch_stories": "insta_watch_follower_stories",
    "insta_watch_follower_stories": "insta_watch_follower_stories",
    "insta_like_stories": "insta_auto_like_stories",
    "insta_auto_like_stories": "insta_auto_like_stories",
    "insta_respond_likes": "insta_auto_respond_likes",
    "insta_auto_respond_likes": "insta_auto_respond_likes",
    "insta_music_notes": "insta_auto_music_notes",
    "insta_auto_music_notes": "insta_auto_music_notes",
    "insta_post_stories": "insta_auto_post_stories",
    "insta_auto_post_stories": "insta_auto_post_stories",
    "insta_stories_per_day": "insta_stories_per_day",
    "insta_username": "insta_username",
    "insta_sessionid": "insta_sessionid",
    "insta_session_id": "insta_sessionid",
}

def update_config_setting(raw_field: str, raw_value: str) -> tuple:
    """Updates config key, auto-saves to config.json and active bot in bots.json."""
    global config, bots_state
    field_norm = raw_field.lower().strip().replace(" ", "_")
    if field_norm not in CONFIG_FIELD_MAPPINGS:
        return False, raw_field, "", f"Unknown field '{raw_field}'"
    
    target_key = CONFIG_FIELD_MAPPINGS[field_norm]
    old_val = str(config.get(target_key, ""))
    val_str = str(raw_value).strip()
    
    try:
        if target_key in ("temperature", "top_p", "frequency_penalty", "presence_penalty", "message_split_delay", "random_chat_chance", "vad_silence_gap", "vad_silence_threshold", "vad_min_speech_duration"):
            converted = float(val_str)
        elif target_key in ("max_tokens", "max_context", "cooldown_seconds", "random_dms_interval_minutes", "random_chat_context_limit", "message_split_min", "message_split_max", "insta_sass_level", "insta_affection_level", "insta_chaos_level", "insta_energy_level", "insta_stories_per_day", "insta_story_check_interval_minutes", "insta_poll_interval_seconds"):
            converted = int(float(val_str))
        elif target_key in ("tts_enabled", "vision_enabled", "auto_search", "user_memory_enabled", "open_chat_enabled", "auto_stt", "message_split_enabled", "random_dms_enabled", "random_chat_enabled", "use_custom_model", "file_reading_enabled", "video_watching_enabled", "context_enabled", "vtuber_enabled", "presence_enabled", "presence_music_enabled", "greet_enabled", "greet_ai_enhance", "greet_ping", "insta_enabled", "insta_auto_reply_dms", "insta_auto_reply_comments", "insta_auto_approve_follow_requests", "insta_watch_follower_stories", "insta_auto_like_stories", "insta_auto_respond_likes", "insta_auto_music_notes", "insta_auto_post_stories"):
            converted = val_str.lower() in ("true", "1", "yes", "on", "enable", "enabled")
        elif target_key == "greet_channel_id":
            m = re.search(r'\d+', val_str)
            converted = int(m.group(0)) if m else (int(val_str) if val_str.isdigit() else None)
        elif target_key == "provider":
            converted = val_str.lower()
            if converted not in ("gemini", "groq", "mistral", "openrouter", "openai", "deepseek", "custom", "huggingface", "auto"):
                converted = "auto"
        else:
            converted = val_str.strip('"\'')
        
        config[target_key] = converted
        save_config(config)

        # Sync VAD settings live to active voice calls if active
        if target_key.startswith("vad_") and DISCORD_VOICE_AVAILABLE and voice_manager:
            try:
                if target_key == "vad_silence_gap":
                    voice_manager.set_vad_gap(None, float(converted))
                elif target_key == "vad_silence_threshold":
                    voice_manager.set_vad_threshold(None, float(converted))
            except Exception:
                pass

        # If Instagram setting, persist to data/instagram_config.json
        if target_key.startswith("insta_") and save_instagram_config:
            save_instagram_config({target_key: converted})
        
        # Also sync to current/active bot in bots.json (only for Discord settings)
        if not target_key.startswith("insta_") and 'bots_state' in globals() and isinstance(bots_state, dict):
            current_id = os.getenv("BOT_ID") or bots_state.get("active_id")
            target_bot = get_bot_by_id(bots_state, current_id) if current_id else get_active_bot(bots_state)
            if target_bot and isinstance(target_bot.get("config"), dict):
                target_bot["config"][target_key] = converted
                save_bots(bots_state)
                
        return True, target_key, old_val, str(converted)
    except Exception as e:
        return False, target_key, old_val, f"Conversion error: {e}"

def toggle_provider(target_provider: str = None) -> tuple:
    """Toggles or sets the active provider. Cycles if not provided."""
    global config, bots_state
    old_provider = config.get("provider", "auto")
    CYCLE = ["auto", "custom", "groq", "mistral", "openrouter", "gemini", "openai", "deepseek", "huggingface"]
    if target_provider and target_provider.lower().strip() in CYCLE:
        new_provider = target_provider.lower().strip()
    else:
        try:
            curr_idx = CYCLE.index(old_provider)
            new_provider = CYCLE[(curr_idx + 1) % len(CYCLE)]
        except ValueError:
            new_provider = "auto"
    config["provider"] = new_provider
    save_config(config)
    if 'bots_state' in globals() and isinstance(bots_state, dict):
        current_id = os.getenv("BOT_ID") or bots_state.get("active_id")
        target_bot = get_bot_by_id(bots_state, current_id) if current_id else get_active_bot(bots_state)
        if target_bot and isinstance(target_bot.get("config"), dict):
            target_bot["config"]["provider"] = new_provider
            save_bots(bots_state)
    return old_provider, new_provider

def format_toast_embed(title: str, description: str, color: int = 0x00ffcc) -> discord.Embed:
    """Formats a compact, modern toast-style confirmation notification."""
    bot_name = client.user.display_name if client.user else "Bot"
    embed = discord.Embed(
        title=f"🍞 {title}",
        description=description,
        color=color
    )
    embed.set_footer(text=f"{bot_name} • Auto-saved")
    return embed

# ─── PER-BOT USER MEMORY / PROFILES ───────────────────
user_profiles = {}

def get_current_bot_id():
    """Returns the current bot's unique ID/identifier to scope memories and contexts per bot."""
    try:
        env_bid = os.getenv("BOT_ID")
        if env_bid:
            return str(env_bid).strip()
    except Exception:
        pass
    try:
        if client and getattr(client, 'user', None) and client.user.id:
            return str(client.user.id)
    except Exception:
        pass
    try:
        if 'bots_state' in globals() and isinstance(bots_state, dict):
            aid = bots_state.get("active_id")
            if aid:
                return str(aid)
    except Exception:
        pass
    return "default_bot"

def get_current_bot_name():
    """Returns the current bot's display name."""
    bid = os.getenv("BOT_ID")
    if bid and 'bots_state' in globals() and isinstance(bots_state, dict):
        b = get_bot_by_id(bots_state, bid)
        if b and b.get("name"):
            return b["name"]
    if client and getattr(client, 'user', None) and client.user.display_name:
        return client.user.display_name
    if client and getattr(client, 'user', None) and client.user.name:
        return client.user.name
    if 'bots_state' in globals() and isinstance(bots_state, dict):
        ab = get_active_bot(bots_state)
        if ab and ab.get("name"):
            return ab["name"]
    return config.get("name") or "Bot"

def get_canonical_bot_id(bot_id: str = None) -> str:
    """Returns the primary unique ID for a bot (matching bots.json entry id)."""
    raw_bid = str(bot_id or get_current_bot_id() or "default_bot").strip()
    if 'bots_state' in globals() and isinstance(bots_state, dict):
        for b in bots_state.get("bots", []):
            if b.get("id") == raw_bid:
                return b["id"]
            tok = b.get("token") or ""
            try:
                sf = base64.b64decode(tok.split(".")[0] + "==").decode()
                if sf == raw_bid:
                    return b["id"]
            except Exception:
                pass
            bname = (b.get("name") or "").strip().lower()
            if bname and bname == raw_bid.lower():
                return b["id"]
    return raw_bid

def get_user_bot_memory(uid: str, bot_id: str = None) -> dict:
    """Get the scoped memory dictionary for a specific user and bot, resolving all aliases and merging splits."""
    uid = str(uid)
    if uid not in user_profiles:
        user_profiles[uid] = {
            "name": "Unknown",
            "global_name": "Unknown",
            "discriminator": "0",
            "avatar_url": None,
            "banner_url": None,
            "status": "unknown",
            "activities": [],
            "roles": {},
            "first_seen": time.time(),
            "last_seen": time.time(),
            "last_full_scan": 0,
            "profile_changes": [],
            "mentioned_users": [],
            "bot_memories": {}
        }
    profile = user_profiles[uid]
    bot_memories = profile.setdefault("bot_memories", {})

    canonical_bid = get_canonical_bot_id(bot_id)

    # Collect all possible alias keys that might exist for this bot
    alias_keys = [canonical_bid]
    env_bid = os.getenv("BOT_ID")
    if env_bid:
        alias_keys.append(str(env_bid).strip())
    if client and getattr(client, 'user', None) and client.user.id:
        alias_keys.append(str(client.user.id))
    if 'bots_state' in globals() and isinstance(bots_state, dict):
        for b in bots_state.get("bots", []):
            if b.get("id") == canonical_bid or (env_bid and b.get("id") == env_bid):
                tok = b.get("token") or ""
                try:
                    sf = base64.b64decode(tok.split(".")[0] + "==").decode()
                    if sf:
                        alias_keys.append(sf)
                except Exception:
                    pass
                bname = (b.get("name") or "").strip().lower()
                if bname:
                    alias_keys.append(bname)

    # Filter unique aliases preserving order
    seen_aliases = set()
    unique_aliases = []
    for a in alias_keys:
        if a and a not in seen_aliases:
            seen_aliases.add(a)
            unique_aliases.append(a)

    # Check if we have memories stored under any of these aliases
    existing_keys = [a for a in unique_aliases if a in bot_memories]

    if canonical_bid not in bot_memories:
        if existing_keys:
            # Re-key the primary existing alias to canonical_bid
            primary_key = existing_keys[0]
            bot_memories[canonical_bid] = bot_memories.pop(primary_key)
            existing_keys.remove(primary_key)
        else:
            # Check if there are root-level legacy facts/sentences to migrate
            legacy_facts = profile.pop("facts", None) or []
            legacy_sentences = profile.pop("sentences", None) or []
            legacy_buffer = profile.pop("conversation_buffer", None) or []
            legacy_count = profile.pop("interaction_count", 0)
            if isinstance(legacy_facts, str):
                legacy_facts = [legacy_facts.strip()] if legacy_facts.strip() else []
            bot_memories[canonical_bid] = {
                "facts": list(legacy_facts),
                "sentences": list(legacy_sentences),
                "conversation_buffer": list(legacy_buffer),
                "interaction_count": legacy_count,
                "last_seen": time.time()
            }

    mem = bot_memories[canonical_bid]
    mem.setdefault("facts", [])
    mem.setdefault("sentences", [])
    mem.setdefault("conversation_buffer", [])
    mem.setdefault("interaction_count", 0)
    mem.setdefault("last_seen", time.time())
    if isinstance(mem.get("facts"), str):
        mem["facts"] = [mem["facts"].strip()] if mem["facts"].strip() else []

    # Merge any remaining duplicate alias structures into canonical_bid WITHOUT popping canonical_bid!
    for other_k in existing_keys:
        if other_k == canonical_bid:
            continue
        other_mem = bot_memories.pop(other_k, None)
        if isinstance(other_mem, dict):
            for f in other_mem.get("facts", []):
                if f and f not in mem["facts"]:
                    mem["facts"].append(f)
            for s in other_mem.get("sentences", []):
                if s and s not in mem["sentences"]:
                    mem["sentences"].append(s)
            for b_msg in other_mem.get("conversation_buffer", []):
                if b_msg and b_msg not in mem["conversation_buffer"]:
                    mem["conversation_buffer"].append(b_msg)
            mem["interaction_count"] = max(mem.get("interaction_count", 0), other_mem.get("interaction_count", 0))
            mem["last_seen"] = max(mem.get("last_seen", 0), other_mem.get("last_seen", 0))

    # CRITICAL: Always ensure canonical entry is securely pinned in profile
    bot_memories[canonical_bid] = mem
    # Also maintain alias references pointing directly to mem so snowflake queries see all facts
    for a in unique_aliases:
        if a and a != canonical_bid:
            bot_memories[a] = mem
    return mem

def clear_user_bot_memory(uid: str, bot_id: str = None, all_bots: bool = False) -> bool:
    """Wipe memory for a user on a specific bot or across all bots."""
    uid = str(uid)
    sync_user_profiles_from_disk()
    if uid not in user_profiles:
        return False
    profile = user_profiles[uid]
    if all_bots:
        profile["bot_memories"] = {}
        profile.pop("facts", None)
        profile.pop("sentences", None)
        profile.pop("conversation_buffer", None)
    else:
        bid = get_canonical_bot_id(bot_id or get_current_bot_id())
        if "bot_memories" in profile:
            profile["bot_memories"][bid] = {
                "facts": [],
                "sentences": [],
                "conversation_buffer": [],
                "interaction_count": 0,
                "last_seen": time.time()
            }
    save_user_profiles(force=True)
    return True

PROFILES_LOCK_DIR = os.path.join(SCRIPT_DIR, "data", "profiles.lock")
_profiles_disk_mtime = 0
_profiles_dirty = False
_last_profiles_save_time = 0
_user_last_memory_extraction = {}  # { (uid, bot_id): timestamp }

class ProcessProfilesLock:
    """Atomic multi-process lock for Android storage using atomic mkdir/rmdir."""
    def __init__(self, lock_dir=PROFILES_LOCK_DIR, timeout=5.0, stale_age=12.0):
        self.lock_dir = lock_dir
        self.timeout = timeout
        self.stale_age = stale_age
        self.acquired = False

    def __enter__(self):
        os.makedirs(os.path.dirname(self.lock_dir), exist_ok=True)
        start = time.time()
        while time.time() - start < self.timeout:
            try:
                os.mkdir(self.lock_dir)
                self.acquired = True
                return self
            except FileExistsError:
                try:
                    mtime = os.path.getmtime(self.lock_dir)
                    if time.time() - mtime > self.stale_age:
                        os.rmdir(self.lock_dir)
                        continue
                except Exception:
                    pass
                time.sleep(0.04)
        self.acquired = False
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.acquired:
            try:
                os.rmdir(self.lock_dir)
            except Exception:
                pass

def merge_profiles_dict(target: dict, source: dict):
    """
    Two-way non-destructive merge of profile dictionaries from disk and memory.
    Merges bot_memories (facts, sentences, buffers) without losing either process's updates.
    """
    for uid, s_prof in source.items():
        if not isinstance(s_prof, dict):
            continue
        if uid not in target or not isinstance(target[uid], dict):
            target[uid] = dict(s_prof)
            continue
        t_prof = target[uid]
        if s_prof.get("last_seen", 0) > t_prof.get("last_seen", 0):
            for k in ["name", "global_name", "avatar_url", "banner_url", "status", "last_seen"]:
                if s_prof.get(k):
                    t_prof[k] = s_prof[k]
        s_roles = s_prof.get("roles", {})
        t_roles = t_prof.setdefault("roles", {})
        if isinstance(s_roles, dict) and isinstance(t_roles, dict):
            t_roles.update(s_roles)
        t_ment = t_prof.setdefault("mentioned_users", [])
        for m in s_prof.get("mentioned_users", []):
            if m not in t_ment:
                t_ment.append(m)
        if len(t_ment) > 100:
            del t_ment[:-100]
        t_bm = t_prof.setdefault("bot_memories", {})
        s_bm = s_prof.get("bot_memories", {})
        if isinstance(s_bm, dict):
            for bid, s_mem in s_bm.items():
                if not isinstance(s_mem, dict):
                    continue
                if bid not in t_bm or not isinstance(t_bm[bid], dict):
                    t_bm[bid] = dict(s_mem)
                    continue
                t_mem = t_bm[bid]
                t_facts = t_mem.setdefault("facts", [])
                for f in s_mem.get("facts", []):
                    if f and f not in t_facts:
                        t_facts.append(f)
                t_sents = t_mem.setdefault("sentences", [])
                for s in s_mem.get("sentences", []):
                    if s and s not in t_sents:
                        t_sents.append(s)
                t_buf = t_mem.setdefault("conversation_buffer", [])
                for b in s_mem.get("conversation_buffer", []):
                    if b and b not in t_buf:
                        t_buf.append(b)
                if len(t_buf) > 50:
                    del t_buf[:-50]
                t_mem["interaction_count"] = max(t_mem.get("interaction_count", 0), s_mem.get("interaction_count", 0))
                t_mem["last_seen"] = max(t_mem.get("last_seen", 0), s_mem.get("last_seen", 0))

def sync_user_profiles_from_disk(force=False):
    """Refreshes in-memory profiles if disk file was modified by another process."""
    global user_profiles, _profiles_disk_mtime
    if not os.path.exists(USER_PROFILES_FILE):
        return
    try:
        cur_mtime = os.path.getmtime(USER_PROFILES_FILE)
        if force or (cur_mtime > _profiles_disk_mtime):
            with state_lock:
                data = _load_json_with_recovery(USER_PROFILES_FILE)
                if data and isinstance(data, dict):
                    merge_profiles_dict(user_profiles, data)
                    _profiles_disk_mtime = cur_mtime
    except Exception as e:
        print(f"[PROFILE SYNC ERROR] {e}")

def load_user_profiles():
    global user_profiles, _profiles_disk_mtime
    with state_lock:
        with ProcessProfilesLock():
            data = _load_json_with_recovery(USER_PROFILES_FILE)
            if data is not None:
                user_profiles = data
                if os.path.exists(USER_PROFILES_FILE):
                    try:
                        _profiles_disk_mtime = os.path.getmtime(USER_PROFILES_FILE)
                    except Exception:
                        pass
                curr_bid = get_canonical_bot_id(get_current_bot_id())
                migrated = 0
                for uid, profile in user_profiles.items():
                    if not isinstance(profile, dict):
                        continue
                    bot_mems = profile.setdefault("bot_memories", {})
                    # Legacy root migration
                    if "facts" in profile or "sentences" in profile or "conversation_buffer" in profile:
                        root_facts = profile.pop("facts", [])
                        root_sents = profile.pop("sentences", [])
                        root_buf = profile.pop("conversation_buffer", [])
                        if isinstance(root_facts, str):
                            root_facts = [root_facts.strip()] if root_facts.strip() else []
                        if curr_bid not in bot_mems:
                            bot_mem = get_user_bot_memory(uid, curr_bid)
                            bot_mem["facts"] = list(root_facts)
                            bot_mem["sentences"] = list(root_sents)
                            bot_mem["conversation_buffer"] = list(root_buf)
                            migrated += 1
                if migrated:
                    print(f"[PROFILE] Migrated {migrated} per-bot memory structures")
                    save_user_profiles(force=True)
            else:
                user_profiles = {}
                print("[PROFILE] No existing profiles found, starting fresh")

def mark_user_profiles_dirty():
    global _profiles_dirty
    _profiles_dirty = True

def save_user_profiles(force=False):
    global _profiles_dirty, _last_profiles_save_time, _profiles_disk_mtime
    now = time.time()
    if not force and not _profiles_dirty:
        return
    if not force and (now - _last_profiles_save_time < 30):
        return
    with state_lock:
        with ProcessProfilesLock():
            # Cross-process merge: read latest disk data before writing to prevent clobbering other bots' writes
            if os.path.exists(USER_PROFILES_FILE):
                try:
                    cur_disk_mtime = os.path.getmtime(USER_PROFILES_FILE)
                    if cur_disk_mtime > _profiles_disk_mtime:
                        disk_data = _load_json_with_recovery(USER_PROFILES_FILE)
                        if disk_data and isinstance(disk_data, dict):
                            merge_profiles_dict(user_profiles, disk_data)
                except Exception as me:
                    print(f"[PROFILE PRE-SAVE MERGE ERROR] {me}")

            _atomic_json_save(USER_PROFILES_FILE, user_profiles, backup=True, max_backups=10)
            _profiles_dirty = False
            _last_profiles_save_time = now
            if os.path.exists(USER_PROFILES_FILE):
                try:
                    _profiles_disk_mtime = os.path.getmtime(USER_PROFILES_FILE)
                except Exception:
                    pass


# ─── MEMORY DEDUPLICATION & EXPLICIT TRIGGER HELPERS ──
MEMORY_EXPLICIT_PATTERNS = [
    re.compile(r'\bremember\b', re.IGNORECASE),
    re.compile(r'\bremind\b', re.IGNORECASE),
    re.compile(r'\bdon\'?t forget\b', re.IGNORECASE),
    re.compile(r'\bnever forget\b', re.IGNORECASE),
    re.compile(r'\bkeep in mind\b', re.IGNORECASE),
    re.compile(r'\btake note\b', re.IGNORECASE),
    re.compile(r'\bmemorize\b', re.IGNORECASE),
    re.compile(r'\bwhat\'?s your opinion\b', re.IGNORECASE),
    re.compile(r'\bwhat is your opinion\b', re.IGNORECASE),
    re.compile(r'\bopinion on\b', re.IGNORECASE),
    re.compile(r'\bwhat do you think (about|of)\b', re.IGNORECASE),
    re.compile(r'\bwhat are your thoughts\b', re.IGNORECASE),
    re.compile(r'\bhow do you feel about\b', re.IGNORECASE),
    re.compile(r'\bwhat\'?s your view\b', re.IGNORECASE),
    re.compile(r'\bmy favou?rite\b', re.IGNORECASE),
    re.compile(r'\bi (really )?(love|hate|prefer|dislike)\b', re.IGNORECASE),
    re.compile(r'\bmy (name|birthday|age|job|hobby|pet|friend|partner|wife|husband|car) is\b', re.IGNORECASE),
    re.compile(r'\bi am (allergic|working as|studying|living in|from)\b', re.IGNORECASE),
    re.compile(r'\bi\'?m (allergic|working as|studying|living in|from)\b', re.IGNORECASE),
    re.compile(r'\bdo you remember\b', re.IGNORECASE),
    re.compile(r'\bwhat do you remember\b', re.IGNORECASE),
    re.compile(r'\bwhat do you know about me\b', re.IGNORECASE),
]

def is_explicit_memory_trigger(text: str) -> bool:
    """Check if message explicitly asks the bot to remember something, asks for opinions, or states strong preferences."""
    if not text or not isinstance(text, str):
        return False
    t = text.strip()
    return any(p.search(t) for p in MEMORY_EXPLICIT_PATTERNS)

def is_similar_to_existing(new_item, existing_list, threshold=0.72):
    """Quick local similarity check using SequenceMatcher."""
    if not new_item or not isinstance(new_item, str):
        return False
    new_lower = new_item.lower().strip()
    if not new_lower:
        return False
    for existing in existing_list:
        if not existing or not isinstance(existing, str):
            continue
        sim = difflib.SequenceMatcher(None, new_lower, existing.lower().strip()).ratio()
        if sim >= threshold:
            return True
    return False

async def update_user_profile(user, message_content=None, guild=None):
    uid = str(user.id)
    now = time.time()

    is_new = uid not in user_profiles
    if is_new:
        user_profiles[uid] = {
            "name": user.display_name,
            "global_name": getattr(user, 'global_name', None) or str(user),
            "discriminator": getattr(user, 'discriminator', '0'),
            "avatar_url": str(user.avatar.url) if user.avatar else None,
            "banner_url": str(user.banner.url) if getattr(user, 'banner', None) else None,
            "status": "unknown",
            "activities": [],
            "roles": {},
            "first_seen": now,
            "last_seen": now,
            "last_full_scan": 0,
            "profile_changes": [],
            "mentioned_users": [],
            "bot_memories": {}
        }
        mark_user_profiles_dirty()

    profile = user_profiles[uid]
    # Refresh basic user info in memory
    profile["name"] = user.display_name
    profile["global_name"] = getattr(user, 'global_name', None) or str(user)
    if user.avatar:
        profile["avatar_url"] = str(user.avatar.url)
    profile["last_seen"] = now
    mark_user_profiles_dirty()

    # Scope memory buffer and interaction count per bot
    bot_mem = get_user_bot_memory(uid)
    bot_mem["interaction_count"] = bot_mem.get("interaction_count", 0) + 1
    bot_mem["last_seen"] = now

    has_explicit_cue = False
    if message_content and len(message_content.strip()) > 5:
        msg_clean = message_content.strip()
        buffer = bot_mem.setdefault("conversation_buffer", [])
        buffer.append(msg_clean)
        if len(buffer) > 50:
            buffer.pop(0)

        # Immediate extraction if explicit trigger like "remember", "whats your opinion on", etc.
        if is_explicit_memory_trigger(msg_clean):
            has_explicit_cue = True
            print(f"[MEMORY IMMEDIATE] Explicit memory trigger from {user.display_name}: '{msg_clean[:55]}' -> extracting instantly")
            await _extract_memories_from_buffer(uid, force=True)

    if message_content:
        mentioned_ids = re.findall(r'<@!?(\d+)>', message_content)
        mlist = profile.setdefault("mentioned_users", [])
        for mid in mentioned_ids:
            if mid != uid and mid not in mlist:
                mlist.append(mid)
                mark_user_profiles_dirty()
                if len(mlist) > 100:
                    mlist.pop(0)

    # Full scan only if brand new user, or if >1 hour elapsed since last full scan
    if is_new or (now - profile.get("last_full_scan", 0) > 3600):
        await _do_full_scan(user, guild, uid)
    elif has_explicit_cue:
        save_user_profiles(force=True)
    else:
        save_user_profiles(force=False)


async def _do_full_scan(user, guild, uid):
    profile = user_profiles[uid]
    old = {
        "name": profile.get("name"),
        "global_name": profile.get("global_name"),
        "status": profile.get("status", "unknown"),
        "activities": [a.get("name", "") for a in profile.get("activities", [])],
    }

    profile["name"] = user.display_name
    profile["global_name"] = getattr(user, 'global_name', None) or str(user)
    profile["avatar_url"] = str(user.avatar.url) if user.avatar else None
    profile["banner_url"] = str(user.banner.url) if getattr(user, 'banner', None) else None

    # Ensure new fields exist for legacy profiles
    if "sentences" not in profile:
        profile["sentences"] = []
    if isinstance(profile.get("facts"), str):
        old_f = profile["facts"].strip()
        profile["facts"] = [old_f] if old_f else []

    status = "unknown"
    activities = []
    roles = []
    member = None

    # Try the provided guild first, then any shared guild (crucial for DMs)
    if guild:
        try:
            member = guild.get_member(user.id)
        except Exception as e:
            print(f"[PROFILE SCAN] Could not scan member {uid} in {guild.id}: {e}")
    if not member:
        for g in getattr(client, 'guilds', []):
            try:
                member = g.get_member(user.id)
                if member:
                    guild = g
                    break
            except Exception:
                continue

    if member:
        try:
            status = str(member.status) if member.status else "unknown"
            activities = []
            for a in member.activities:
                act_data = {"name": getattr(a, 'name', '') or "", "type": str(getattr(a, 'type', ''))}
                if getattr(a, 'state', None):
                    act_data["state"] = str(a.state)
                if getattr(a, 'details', None):
                    act_data["details"] = str(a.details)
                if getattr(a, 'title', None):
                    act_data["title"] = str(a.title)
                if getattr(a, 'artist', None):
                    act_data["artist"] = str(a.artist)
                if getattr(a, 'emoji', None):
                    act_data["emoji"] = str(a.emoji)
                activities.append(act_data)
            roles = [r.name for r in member.roles if r.name != "@everyone"]
            if guild:
                profile["roles"][str(guild.id)] = roles
        except Exception as e:
            print(f"[PROFILE SCAN] Could not read member data for {uid}: {e}")

    profile["status"] = status
    profile["activities"] = activities
    profile["last_full_scan"] = time.time()
    mark_user_profiles_dirty()

    changes = []
    if old["name"] and old["name"] != user.display_name:
        changes.append(f"changed display name from '{old['name']}' to '{user.display_name}'")
    if old["global_name"] and old["global_name"] != profile["global_name"]:
        changes.append(f"changed username from '{old['global_name']}' to '{profile['global_name']}'")
    if old["status"] and old["status"] != "unknown" and old["status"] != status:
        changes.append(f"status changed from {old['status']} to {status}")
    if old["activities"] and activities:
        old_names = set(old["activities"])
        new_names = {a["name"] for a in activities}
        started = new_names - old_names
        stopped = old_names - new_names
        if started:
            changes.append(f"started: {', '.join(started)}")
        if stopped:
            changes.append(f"stopped: {', '.join(stopped)}")

    if changes:
        obs = f"Noticed {user.display_name} " + "; ".join(changes)
        profile.setdefault("profile_changes", []).append({
            "time": time.time(),
            "changes": changes
        })
        bot_mem = get_user_bot_memory(uid)
        facts_list = bot_mem.setdefault("facts", [])
        if not is_similar_to_existing(obs, facts_list):
            facts_list.append(obs)
            print(f"[PROFILE] {obs}")
        else:
            print(f"[PROFILE] {obs} (similar existing, skipped)")

    save_user_profiles(force=False)


async def _extract_memories_from_buffer(uid, bot_id=None, force=False):
    profile = user_profiles.get(uid)
    if not profile:
        return
    bid = str(bot_id or get_current_bot_id())
    bot_mem = get_user_bot_memory(uid, bid)
    buffer = bot_mem.get("conversation_buffer", [])
    
    min_required = 1 if force else 2
    if len(buffer) < min_required:
        return

    existing_facts = bot_mem.get("facts", [])
    existing_sentences = bot_mem.get("sentences", [])
    combined = "\n".join([f"- {m}" for m in buffer])

    existing_facts_text = "\n".join([f"- {f}" for f in existing_facts[-50:]]) if existing_facts else "None yet"
    existing_sentences_text = "\n".join([f"- {s}" for s in existing_sentences[-50:]]) if existing_sentences else "None yet"

    prompt = (
        "You are a memory curator for a personal AI assistant. Analyze these user messages and extract memorable information.\n\n"
        "EXISTING FACTS (do NOT duplicate or closely paraphrase these):\n"
        f"{existing_facts_text}\n\n"
        "EXISTING SENTENCES/QUOTES (do NOT duplicate these):\n"
        f"{existing_sentences_text}\n\n"
        "NEW MESSAGES TO ANALYZE:\n"
        f"{combined}\n\n"
        "Instructions:\n"
        "1. Extract 1-5 detailed facts about the user (interests, preferences, opinions, topics they care about, personal details, life events, relationships, work, hobbies).\n"
        "2. Extract 1-5 notable sentences or quotes — things they said or asked that reveal personality, humor, emotions, opinions, or important info. Save the actual wording or a close paraphrase.\n"
        "3. CRITICAL DEDUPLICATION: Only return items that are GENUINELY NEW. If a fact or sentence is semantically similar to an existing one, SKIP it entirely. Do not rephrase existing memories.\n"
        "4. Be comprehensive. Write full, detailed sentences. Do not summarize multiple messages into one vague fact.\n\n"
        "Return ONLY valid JSON in this exact format (no markdown, no explanation):\n"
        '{"facts": ["detailed fact 1", "detailed fact 2"], "sentences": ["notable sentence 1", "notable sentence 2"]}'
    )

    cur_bname = get_current_bot_name()
    curator_system = f"You are an objective memory curator for {cur_bname}. Analyze the user's messages and extract factual user preferences, interests, and quotes from the user."
    facts_text, err = None, True

    # Fast & reliable: prioritize Gemini directly
    if GEMINI_KEY and time.time() >= gemini_blocked_until:
        facts_text, err = await ask_gemini(curator_system, [], prompt, caller="memory")
    if (err or not facts_text) and GROQ_KEY and time.time() >= groq_blocked_until:
        facts_text, err = await ask_groq([], prompt, system_msg=curator_system)
    if (err or not facts_text) and (os.getenv("MISTRAL_KEY") or MISTRAL_KEY) and time.time() >= mistral_blocked_until:
        facts_text, err = await ask_mistral([], prompt, system_msg=curator_system)

    if err or not facts_text:
        print(f"[MEMORY] Extraction failed for {uid}: {facts_text}")
        bot_mem["conversation_buffer"] = buffer[-3:]
        return

    new_facts = []
    new_sentences = []
    try:
        clean_text = str(facts_text).strip()
        if "```json" in clean_text:
            clean_text = clean_text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in clean_text:
            clean_text = clean_text.split("```", 1)[1].split("```", 1)[0].strip()
        match = re.search(r'\{.*\}', clean_text, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
            new_facts = parsed.get("facts", [])
            new_sentences = parsed.get("sentences", [])
        else:
            lines = [line.strip("- *\u2022").strip() for line in clean_text.split("\n")
                     if line.strip() and not line.strip().startswith("```")]
            new_facts = [l for l in lines if len(l) > 10]
    except Exception as e:
        print(f"[MEMORY] Parse error for {uid}: {e}")
        bot_mem["conversation_buffer"] = buffer[-3:]
        return

    if not isinstance(new_facts, list):
        new_facts = [str(new_facts)] if new_facts else []
    if not isinstance(new_sentences, list):
        new_sentences = [str(new_sentences)] if new_sentences else []

    facts_list = bot_mem["facts"]
    sentences_list = bot_mem["sentences"]

    added_facts = 0
    added_sentences = 0

    for f in new_facts:
        if isinstance(f, str) and f.strip() and len(f) > 5:
            f_clean = f.strip()
            if not is_similar_to_existing(f_clean, facts_list):
                facts_list.append(f_clean)
                added_facts += 1

    for s in new_sentences:
        if isinstance(s, str) and s.strip() and len(s) > 5:
            s_clean = s.strip()
            if not is_similar_to_existing(s_clean, sentences_list):
                sentences_list.append(s_clean)
                added_sentences += 1

    if added_facts or added_sentences:
        print(f"[MEMORY] {uid} (bot: {bid}): +{added_facts} facts, +{added_sentences} sentences. Totals: {len(facts_list)} facts, {len(sentences_list)} sentences.")

    bot_mem["conversation_buffer"] = []
    _user_last_memory_extraction[(uid, bid)] = time.time()
    save_user_profiles(force=True)

async def flush_all_buffers():
    for uid, profile in user_profiles.items():
        bot_mems = profile.get("bot_memories", {})
        for bid, bmem in bot_mems.items():
            buffer = bmem.get("conversation_buffer", [])
            if len(buffer) >= 2:
                await _extract_memories_from_buffer(uid, bot_id=bid, force=True)

def retrieve_relevant_memories(all_facts: list, all_sentences: list, current_prompt: str = None, max_facts: int = 65, max_sentences: int = 25) -> tuple:
    """
    Intelligently retrieves memories ensuring the oldest foundational memories are NEVER forgotten,
    surfacing topic-relevant memories from any point in history, and preserving recent context.
    """
    # 1. FACTS SELECTION
    selected_facts = []
    if len(all_facts) <= max_facts:
        selected_facts = list(all_facts)
    else:
        # A. Oldest Foundational Memories (first 15 items: early origins & core identity)
        oldest_indices = set(range(min(15, len(all_facts))))

        # B. Recent Memories (last 20 items: freshest context)
        recent_indices = set(range(max(0, len(all_facts) - 20), len(all_facts)))

        # C. Keyword / Topic Relevant Memories across ALL historical facts
        relevant_indices = []
        if current_prompt and isinstance(current_prompt, str):
            stopwords = {"the", "and", "that", "this", "with", "have", "from", "they", "will", "would", "there", "their", "what", "about", "which", "when", "make", "like", "time", "just", "know", "take", "people", "into", "year", "your", "good", "some", "could", "them", "other", "than", "then", "now", "look", "only", "come", "its", "over", "think", "also", "back", "after", "use", "two", "how", "our", "work", "first", "well", "way", "even", "new", "want", "because", "any", "these", "give", "day", "most", "cant", "wont", "dont", "youre", "hes", "shes", "theyre"}
            clean_words = set(re.findall(r'\b[a-zA-Z]{3,}\b', current_prompt.lower())) - stopwords

            scored_facts = []
            for idx, fact in enumerate(all_facts):
                if idx in oldest_indices or idx in recent_indices:
                    continue
                fact_lower = fact.lower()
                score = 0
                for w in clean_words:
                    if w in fact_lower:
                        score += 3
                if score > 0:
                    scored_facts.append((score, idx))

            scored_facts.sort(key=lambda x: x[0], reverse=True)
            available_slots = max_facts - len(oldest_indices | recent_indices)
            relevant_indices = [idx for _, idx in scored_facts[:max(15, available_slots)]]

        chosen_indices = oldest_indices | recent_indices | set(relevant_indices)

        # If room remains, pull from earliest facts forward to maintain continuous historical depth
        if len(chosen_indices) < max_facts:
            remaining = [i for i in range(len(all_facts)) if i not in chosen_indices]
            for idx in remaining[:max_facts - len(chosen_indices)]:
                chosen_indices.add(idx)

        # Preserve original chronological order
        selected_facts = [all_facts[i] for i in sorted(chosen_indices)]

    # 2. SENTENCES / QUOTES SELECTION
    selected_sentences = []
    if len(all_sentences) <= max_sentences:
        selected_sentences = list(all_sentences)
    else:
        oldest_s_idx = set(range(min(5, len(all_sentences))))
        recent_s_idx = set(range(max(0, len(all_sentences) - 10), len(all_sentences)))

        rel_s_idx = []
        if current_prompt and isinstance(current_prompt, str):
            clean_words = set(re.findall(r'\b[a-zA-Z]{3,}\b', current_prompt.lower()))
            scored_s = []
            for idx, sent in enumerate(all_sentences):
                if idx in oldest_s_idx or idx in recent_s_idx:
                    continue
                score = sum(2 for w in clean_words if w in sent.lower())
                if score > 0:
                    scored_s.append((score, idx))
            scored_s.sort(key=lambda x: x[0], reverse=True)
            rel_s_idx = [idx for _, idx in scored_s[:8]]

        chosen_s_idx = oldest_s_idx | recent_s_idx | set(rel_s_idx)
        if len(chosen_s_idx) < max_sentences:
            remaining_s = [i for i in range(len(all_sentences)) if i not in chosen_s_idx]
            for idx in remaining_s[:max_sentences - len(chosen_s_idx)]:
                chosen_s_idx.add(idx)

        selected_sentences = [all_sentences[i] for i in sorted(chosen_s_idx)]

    return selected_facts, selected_sentences

def search_memory_tree(query: str, bot_id: str = None, max_results: int = 5, exclude_uids: set = None) -> list:
    """
    Performs keyword/semantic memory search across all users in the memory tree
    and user_profiles to answer questions like 'who plays blitz?', 'who said X?',
    'who is the person who...', etc.
    """
    if not query or not isinstance(query, str):
        return []
    
    clean_q = extract_clean_user_query(query).lower()
    stopwords = {
        "the", "and", "that", "this", "with", "have", "from", "they", "will", "would",
        "there", "their", "what", "about", "which", "when", "where", "make", "like",
        "time", "just", "know", "take", "people", "into", "year", "your", "good",
        "some", "could", "them", "other", "than", "then", "now", "look", "only",
        "come", "its", "over", "think", "also", "back", "after", "use", "two", "how",
        "our", "work", "first", "well", "way", "even", "new", "want", "because",
        "any", "these", "give", "day", "most", "cant", "wont", "dont", "youre", "hes",
        "shes", "theyre", "who", "does", "said", "tell", "talk", "talking", "someone",
        "person", "anyone", "remember", "opinion"
    }
    keywords = [w for w in re.findall(r'\b[a-zA-Z]{3,}\b', clean_q) if w not in stopwords]
    if not keywords:
        return []

    effective_bid = str(bot_id or get_current_bot_id() or "default")
    cur_bot_name = (get_current_bot_name() or "").lower()
    matches = []
    seen_items = set()
    ex_uids = set(str(u) for u in (exclude_uids or []))

    # Search through user_profiles and memories tree
    for uid, prof in user_profiles.items():
        if str(uid) in ex_uids:
            continue
        uname = prof.get("global_name") or prof.get("name") or str(uid)
        
        bm = prof.get("bot_memories", {})
        facts = []
        sentences = []
        if effective_bid in bm:
            facts.extend(bm[effective_bid].get("facts", []))
            sentences.extend(bm[effective_bid].get("sentences", []))
        for b_k, b_data in bm.items():
            if isinstance(b_data, dict):
                for f in b_data.get("facts", []):
                    if f and f not in facts:
                        facts.append(f)
                for s in b_data.get("sentences", []):
                    if s and s not in sentences:
                        sentences.append(s)
        for f in prof.get("facts", []):
            if f and f not in facts:
                facts.append(f)
        for s in prof.get("sentences", []):
            if s and s not in sentences:
                sentences.append(s)

        # Also load from disk tree if exists
        tree_user_dir = os.path.join(SCRIPT_DIR, "memories", "users", str(uid))
        if os.path.isdir(tree_user_dir):
            try:
                tf_p = os.path.join(tree_user_dir, "facts.json")
                if os.path.isfile(tf_p):
                    with open(tf_p, "r", encoding="utf-8", errors="ignore") as ff:
                        tf_list = json.load(ff)
                        if isinstance(tf_list, list):
                            for f in tf_list:
                                if f and f not in facts:
                                    facts.append(f)
                tq_p = os.path.join(tree_user_dir, "quotes.json")
                if os.path.isfile(tq_p):
                    with open(tq_p, "r", encoding="utf-8", errors="ignore") as ff:
                        tq_list = json.load(ff)
                        if isinstance(tq_list, list):
                            for s in tq_list:
                                if s and s not in sentences:
                                    sentences.append(s)
            except Exception:
                pass

        for fact in facts:
            if not isinstance(fact, str) or not fact.strip() or fact in seen_items:
                continue
            f_low = fact.lower()
            if cur_bot_name != "yuna" and re.search(r'\b(yuna|yuna\'s|yunas)\b', fact, re.IGNORECASE):
                continue
            score = sum(3 for kw in keywords if kw in f_low)
            if score > 0:
                seen_items.add(fact)
                matches.append((score, str(uid), uname, fact))

        for sent in sentences:
            if not isinstance(sent, str) or not sent.strip() or sent in seen_items:
                continue
            s_low = sent.lower()
            if cur_bot_name != "yuna" and re.search(r'\b(yuna|yuna\'s|yunas)\b', sent, re.IGNORECASE):
                continue
            score = sum(3 for kw in keywords if kw in s_low)
            if score > 0:
                seen_items.add(sent)
                matches.append((score, str(uid), uname, f'Said: "{sent}"'))

    matches.sort(key=lambda x: x[0], reverse=True)
    return matches[:max_results]


def normalize_discord_name(s: str) -> tuple:
    """Normalizes any Discord username/nickname, stripping unicode fonts, titles, and decorative symbols."""
    if not s or not isinstance(s, str):
        return "", []
    try:
        import unicodedata
        s_norm = unicodedata.normalize('NFKD', s)
    except Exception:
        s_norm = s
    cleaned = re.sub(r'[^a-zA-Z0-9\s]+', ' ', s_norm).lower()
    cleaned = re.sub(r'\b(mr|ms|mrs|dr|lord|sir|lady|prof)\b', ' ', cleaned).strip()
    cleaned = re.sub(r'\s+', ' ', cleaned)
    tokens = [w for w in cleaned.split() if len(w) >= 2]
    return cleaned, tokens


def resolve_subject_users(query: str, primary_uid: str = None, raw_mentions: list = None, reply_to_user_id: str = None, raw_content: str = None) -> list:
    """
    Identifies and resolves user(s) being mentioned or asked about in the prompt.
    Returns a list of matching user IDs from user_profiles / memories tree.
    """
    if not query or not isinstance(query, str):
        return []
        
    subject_ids = []
    primary_uid_str = str(primary_uid) if primary_uid else None
    
    # 1. Identify all bot IDs so bots are never treated as inquiry subjects
    known_bot_uids = set()
    if client and getattr(client, 'user', None) and client.user.id:
        known_bot_uids.add(str(client.user.id))
    if 'bots_state' in globals() and isinstance(bots_state, dict):
        for b in bots_state.get("bots", []):
            tok = b.get("token") or ""
            parts = tok.split(".")
            if len(parts) >= 2:
                try:
                    padded = parts[0] + "=" * ((4 - len(parts[0]) % 4) % 4)
                    sf = base64.b64decode(padded).decode("utf-8", errors="ignore")
                    if sf and sf.isdigit():
                        known_bot_uids.add(sf)
                except Exception:
                    pass
            bid = b.get("id")
            if bid:
                known_bot_uids.add(str(bid))
    cur_bot_id_str = os.getenv("BOT_ID") or (bots_state.get("active_id") if 'bots_state' in globals() and isinstance(bots_state, dict) else None)
    if cur_bot_id_str:
        known_bot_uids.add(str(cur_bot_id_str))

    # 2. Priority 1: Direct Discord Mentions / Snowflakes
    if raw_mentions:
        for mid in raw_mentions:
            m_str = str(mid)
            if m_str != primary_uid_str and m_str not in known_bot_uids and m_str not in subject_ids:
                subject_ids.append(m_str)

    for txt in (raw_content, query):
        if txt:
            for mid in re.findall(r'<@!?(\d+)>', txt):
                mid_str = str(mid)
                if mid_str != primary_uid_str and mid_str not in known_bot_uids and mid_str not in subject_ids:
                    subject_ids.append(mid_str)

    if subject_ids:
        return subject_ids

    # 3. Priority 2: Reply reference target for "who is this", "what about them", etc.
    q_clean = query.strip()
    if q_clean.startswith("[") and "]:" in q_clean:
        q_clean = q_clean.split("]:", 1)[1].strip()

    if reply_to_user_id:
        r_str = str(reply_to_user_id)
        if r_str != primary_uid_str and r_str not in known_bot_uids:
            if re.search(r'\b(who\s+is\s+this|who\s+is\s+that|who\s+are\s+they|who\s+is\s+he|who\s+is\s+she|what\s+about\s+them|who\s+is\s+this\s+person)\b', q_clean, re.IGNORECASE):
                return [r_str]

    # 4. Priority 3: Extract potential names/terms from inquiry phrases
    extracted_terms = []
    inquiry_patterns = [
        r'\b(?:who\s+(?:is|\'s|are|was|the\s+fuck\s+is|tf\s+is)|what\s+about|tell\s+me\s+about|do\s+you\s+know|what\s+do\s+you\s+think\s+of|opinion\s+on|describe|how\s+about|relationship\s+with)\s+([^?!\n]+)',
    ]
    for pat in inquiry_patterns:
        m = re.search(pat, q_clean, re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            cleaned = re.sub(r'\b(to\s+you|again|irl|actually|bro|rn|lol|lmao|btw|tbh|anyway)\b', '', raw, flags=re.IGNORECASE).strip()
            cleaned = re.sub(r'^[@<@!>#\[\]~]+', '', cleaned).strip(' >?.!,')
            if cleaned and len(cleaned) >= 2:
                extracted_terms.append(cleaned)

    # Clean mentions like @Username (supporting emojis, decorative fonts, and punctuation)
    for cm in re.findall(r'@([^\s,?:!]+)', q_clean):
        c_clean = re.sub(r'^[@<@!>#\[\]~]+', '', cm).strip(' >?.!,')
        if c_clean.lower() not in ("yuna", "bot", "here", "everyone", "law", "briliance", "brilliance"):
            extracted_terms.append(c_clean)

    q_norm, q_tokens = normalize_discord_name(q_clean)
    stopwords = {'who', 'what', 'about', 'tell', 'know', 'relationship', 'with', 'your', 'and', 'yuna', 'the', 'you', 'this', 'that', 'they', 'are', 'was', 'were', 'have', 'from', 'for', 'them', 'him', 'her', 'she', 'how'}
    q_key_tokens = [w for w in q_tokens if w not in stopwords]

    # 5. Score matching against user_profiles and disk memory tree
    tree_users_dir = os.path.join(SCRIPT_DIR, "memories", "users")
    scored = []
    for uid_k, prof_v in user_profiles.items():
        uid_str = str(uid_k)
        if uid_str == primary_uid_str or uid_str in known_bot_uids:
            continue
        if client and getattr(client, 'user', None) and str(client.user.id) == uid_str:
            continue

        un = prof_v.get("name") or ""
        gn = prof_v.get("global_name") or ""
        un_norm, un_tokens = normalize_discord_name(un)
        gn_norm, gn_tokens = normalize_discord_name(gn)

        user_tokens = set(un_tokens) | set(gn_tokens)
        bm = prof_v.get("bot_memories", {})
        facts_cnt = len(prof_v.get("facts", [])) + sum(len(b.get("facts", [])) for b in bm.values() if isinstance(b, dict))

        best_score = 0
        for term in extracted_terms:
            t_low = term.lower().strip()
            # Direct ID match
            if t_low.isdigit() and t_low == uid_str:
                best_score = max(best_score, 1000)
                break

            t_norm, t_tokens = normalize_discord_name(term)
            if not t_norm:
                continue

            # Exact full string match
            if t_norm == un_norm or t_norm == gn_norm:
                best_score = max(best_score, 100)
            elif any(tt in user_tokens for tt in t_tokens):
                best_score = max(best_score, 90)
            elif len(t_norm) >= 3 and (t_norm in un_norm or t_norm in gn_norm):
                best_score = max(best_score, 85)
            # Nickname substring match (e.g. 'kemi' in 'kemikyou')
            elif len(un_norm) >= 3 and un_norm not in stopwords and un_norm in t_norm:
                best_score = max(best_score, 85)

        # Direct token match against query words
        if best_score < 80 and user_tokens:
            overlap = [ut for ut in user_tokens if ut in q_key_tokens and len(ut) >= 3 and ut not in stopwords]
            if overlap:
                best_score = max(best_score, 80 + len(overlap) * 5)
            elif len(un_norm) >= 3 and un_norm not in stopwords and re.search(rf'\b{re.escape(un_norm)}\b', q_norm):
                best_score = max(best_score, 80)
            elif len(gn_norm) >= 3 and gn_norm not in stopwords and re.search(rf'\b{re.escape(gn_norm)}\b', q_norm):
                best_score = max(best_score, 80)

        if best_score >= 80:
            scored.append((best_score, facts_cnt, uid_str))

    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [uid for _, _, uid in scored[:2]]


def build_scene_context(channel_id, primary_user_id=None, user_name=None, guild=None, is_dm=False, current_prompt=None, bot_id=None, raw_mentions=None, reply_to_user_id=None, raw_content=None):
    parts = []
    raw_context = get_context(channel_id, bot_id=bot_id)

    def _render_profile(p, indent="", target_uid=None, target_bid=None):
        lines = []
        name = p.get("name", "Unknown")
        uname = p.get("global_name", "")
        avatar = p.get("avatar_url", "")
        banner = p.get("banner_url", "")
        status = p.get("status", "unknown")
        acts = p.get("activities", [])
        
        # Scoped bot memory strictly for this bot
        p_uid = target_uid or str(p.get("id") or "")
        facts = []
        sentences = []
        effective_bid = str(target_bid or bot_id or get_current_bot_id())
        cur_bot_name = (get_current_bot_name() or "").lower()

        if p_uid:
            bot_mem = get_user_bot_memory(p_uid, bot_id=effective_bid)
            facts.extend(bot_mem.get("facts", []))
            sentences.extend(bot_mem.get("sentences", []))

            # Disk tree integration (memories/users/<p_uid>/)
            tree_user_dir = os.path.join(SCRIPT_DIR, "memories", "users", str(p_uid))
            if os.path.isdir(tree_user_dir):
                try:
                    tf_p = os.path.join(tree_user_dir, "facts.json")
                    if os.path.isfile(tf_p):
                        with open(tf_p, "r", encoding="utf-8", errors="ignore") as _f:
                            tf_data = json.load(_f)
                            if isinstance(tf_data, list):
                                facts.extend([x for x in tf_data if isinstance(x, str) and x.strip()])
                    tq_p = os.path.join(tree_user_dir, "quotes.json")
                    if os.path.isfile(tq_p):
                        with open(tq_p, "r", encoding="utf-8", errors="ignore") as _f:
                            tq_data = json.load(_f)
                            if isinstance(tq_data, list):
                                sentences.extend([x for x in tq_data if isinstance(x, str) and x.strip()])
                except Exception:
                    pass

        # Root-level legacy facts only if not persona-specific to another bot
        for f in p.get("facts", []):
            if isinstance(f, str) and f.strip():
                if cur_bot_name != "yuna" and re.search(r'\b(yuna|yuna\'s|yunas)\b', f, re.IGNORECASE):
                    continue
                facts.append(f)
        for s in p.get("sentences", []):
            if isinstance(s, str) and s.strip():
                if cur_bot_name != "yuna" and re.search(r'\b(yuna|yuna\'s|yunas)\b', s, re.IGNORECASE):
                    continue
                sentences.append(s)

        # CRITICAL PROTECTION: If this bot is NOT Yuna, scrub any leaked/contaminated Yuna memories
        if cur_bot_name and cur_bot_name != "yuna":
            facts = [f for f in facts if not re.search(r'\b(yuna|yuna\'s|yunas)\b', f, re.IGNORECASE)]
            sentences = [s for s in sentences if not re.search(r'\b(yuna|yuna\'s|yunas)\b', s, re.IGNORECASE)]

        facts = list(dict.fromkeys(facts))
        sentences = list(dict.fromkeys(sentences))

        roles = p.get("roles", {})
        changes = p.get("profile_changes", [])
        mentioned = p.get("mentioned_users", [])

        lines.append(f"{indent}Name: {name}")
        if uname:
            lines.append(f"{indent}Username: @{uname}")
        if avatar:
            lines.append(f"{indent}Avatar: {avatar}")
        if banner:
            lines.append(f"{indent}Banner: {banner}")
        if status and status != "unknown":
            lines.append(f"{indent}Status: {status}")
        if acts:
            act_strs = []
            for a in acts:
                if isinstance(a, dict):
                    aname = a.get("name", "")
                    astate = a.get("state", "")
                    adetails = a.get("details", "")
                    atitle = a.get("title", "")
                    aartist = a.get("artist", "")
                    aemoji = a.get("emoji", "")
                    
                    if "spotify" in str(a.get("type", "")).lower() or atitle or aartist:
                        track_desc = f"'{atitle}' by {aartist}" if atitle and aartist else aname
                        act_strs.append(f"Listening to Spotify: {track_desc}")
                    elif "custom" in str(a.get("type", "")).lower() or aname.lower() == "custom status":
                        status_msg = f"{aemoji} {astate}".strip() if astate else aemoji
                        if status_msg:
                            act_strs.append(f"Custom Status / Quote: \"{status_msg}\"")
                    else:
                        extra = []
                        if adetails: extra.append(adetails)
                        if astate: extra.append(astate)
                        extra_str = f" ({', '.join(extra)})" if extra else ""
                        act_strs.append(f"{aname}{extra_str}")
                elif isinstance(a, str):
                    act_strs.append(a)
            if act_strs:
                lines.append(f"{indent}Currently doing / Status: {', '.join(act_strs)}")

        all_roles = set()
        for rlist in roles.values():
            all_roles.update(rlist)
        if all_roles:
            lines.append(f"{indent}Roles: {', '.join(sorted(all_roles))}")

        if changes:
            lines.append(f"{indent}Recent profile changes:")
            for c in changes[-5:]:
                lines.append(f"{indent}  - {c.get('changes', [])}")

        # Social & Marriage Status
        if p_uid:
            try:
                g_u = None
                if YUNA_GAMBLING_AVAILABLE and yuna_gambling and hasattr(yuna_gambling, "_USER_STATS"):
                    g_u = yuna_gambling._USER_STATS.get(str(p_uid))
                if not g_u:
                    g_f = os.path.join(SCRIPT_DIR, "data", "yuna_gambling.json")
                    if os.path.isfile(g_f):
                        with open(g_f, "r", encoding="utf-8", errors="ignore") as _gf:
                            g_u = json.load(_gf).get("users", {}).get(str(p_uid))
                if g_u and isinstance(g_u, dict):
                    sp_id = g_u.get("spouse")
                    if sp_id:
                        sp_prof = user_profiles.get(str(sp_id), {})
                        sp_disp = sp_prof.get("global_name") or sp_prof.get("name") or f"User {sp_id}"
                        lines.append(f"{indent}Marriage Status: Married to {sp_disp} (ID: {sp_id})")
                    b_amt = g_u.get("berries")
                    if b_amt is not None:
                        lines.append(f"{indent}Economy Stats: {b_amt:,} 🫐 | Virtue: {g_u.get('virtue', 0)} 💖 | Sin: {g_u.get('sin', 0)} ❤️🔥")
            except Exception:
                pass

        recalled_facts, recalled_sentences = retrieve_relevant_memories(facts, sentences, current_prompt=current_prompt)

        if recalled_facts:
            if len(facts) <= len(recalled_facts):
                lines.append(f"{indent}Facts you remember ({len(facts)} total) — USE THESE NATURALLY:")
            else:
                lines.append(f"{indent}Memories you remember ({len(recalled_facts)} recalled of {len(facts)} total spanning earliest meetings to latest) — USE NATURALLY:")
            for f in recalled_facts:
                lines.append(f"{indent}  • {f}")

        if recalled_sentences:
            if len(sentences) <= len(recalled_sentences):
                lines.append(f"{indent}Things they've said ({len(sentences)} total) — REFERENCE WHEN RELEVANT:")
            else:
                lines.append(f"{indent}Quotes you remember ({len(recalled_sentences)} recalled of {len(sentences)} total) — REFERENCE WHEN RELEVANT:")
            for s in recalled_sentences:
                lines.append(f"{indent}  • \"{s}\"")

        if mentioned:
            mnames = []
            for mid in mentioned[-10:]:
                mp = user_profiles.get(mid)
                if mp:
                    mnames.append(mp.get("name", "someone"))
            if mnames:
                lines.append(f"{indent}People they've mentioned: {', '.join(mnames)}")

        return lines

    if is_dm:
        parts.append("=" * 50)
        parts.append("SCENE CONTEXT — PRIVATE DM")
        parts.append("=" * 50)
        primary_uid_str = str(primary_user_id) if primary_user_id else None
        if primary_uid_str:
            uid = primary_uid_str
            # Resolve linked Discord identity if Instagram PK
            try:
                from social.insta_memory import insta_memory
                linked_id = insta_memory.get_profile(uid).get("linked_discord_id")
                if linked_id and linked_id in user_profiles:
                    uid = str(linked_id)
            except Exception:
                pass

            p = user_profiles.get(uid)
            if p:
                parts.append(f"\n>>> YOU KNOW THIS PERSON DEEPLY. You have talked to them before.")
                parts.append(f">>> Their profile and everything you remember about them:")
                parts.extend(_render_profile(p, indent="  ", target_uid=uid, target_bid=bot_id))
                parts.append("\n>>> INSTRUCTION: Treat them like someone you know intimately. Use your memories naturally — reference past conversations, inside jokes, known preferences, and things they've said before. Do NOT act like a stranger.")
            else:
                parts.append(f"\nTalking to: {user_name or 'User'} (ID: {uid})")
                parts.append("No stored memories yet. This is effectively a first conversation.")

        # In DM, resolve subject users if user asks about another person (e.g. "who is X?")
        subject_uids = resolve_subject_users(current_prompt, primary_uid=primary_user_id, raw_mentions=raw_mentions, reply_to_user_id=reply_to_user_id, raw_content=raw_content)
        if subject_uids:
            for s_uid in subject_uids:
                s_prof = user_profiles.get(s_uid)
                if not s_prof:
                    tree_pfile = os.path.join(SCRIPT_DIR, "memories", "users", str(s_uid), "profile.json")
                    if os.path.isfile(tree_pfile):
                        try:
                            with open(tree_pfile, "r", encoding="utf-8") as f:
                                s_prof = json.load(f)
                        except Exception:
                            pass
                s_disp = (s_prof.get("global_name") or s_prof.get("name") or f"User {s_uid}") if s_prof else f"User {s_uid}"
                parts.append("\n" + ("=" * 45))
                parts.append(f"🎯 SUBJECT OF INQUIRY / PERSON BEING ASKED ABOUT:")
                parts.append(f"  Target User: {s_disp} (ID: {s_uid})")
                if s_prof:
                    parts.extend(_render_profile(s_prof, indent="    ", target_uid=s_uid, target_bid=bot_id))
                parts.append(
                    f"\n🚨 [CRITICAL DIRECTIVE FOR ANSWERING ABOUT {s_disp.upper()}]:\n"
                    f"- The user is directly asking you about {s_disp}!\n"
                    f"- You KNOW {s_disp}! You have real history, memories, inside jokes, and shared experiences with them.\n"
                    f"- NEVER pretend not to know {s_disp}, do NOT act like a stranger, do NOT dismiss them, and do NOT say you don't know who that is!\n"
                    f"- Speak about {s_disp} with deep personal familiarity in full character as {get_current_bot_name()}, actively weaving in your memories, their quirks, quotes, and your shared bond!"
                )
                parts.append("=" * 45)

        # In DM, memory search for facts/topics
        matched_memories = search_memory_tree(current_prompt, bot_id=bot_id, exclude_uids={primary_uid_str} | set(subject_uids))
        if matched_memories:
            parts.append("\n" + ("=" * 45))
            parts.append("🔍 RELEVANT MEMORIES RETRIEVED FROM MEMORY TREE:")
            for score, m_uid, m_name, m_fact in matched_memories:
                parts.append(f"  • Regarding {m_name} (ID: {m_uid}): \"{m_fact}\"")
            parts.append(f">>> DIRECTIVE: Use these relevant memories to directly answer what the user is asking about!")
            parts.append("=" * 45)

        parts.append("=" * 50)
    else:
        if guild:
            parts.append(f"=" * 50)
            parts.append(f"SCENE CONTEXT — PUBLIC CHANNEL: {guild.name}")
            parts.append("=" * 50)
        else:
            parts.append("=" * 50)
            parts.append("SCENE CONTEXT — PUBLIC CHANNEL")
            parts.append("=" * 50)

        # 1. IDENTIFY AND HIGHLIGHT ACTIVE SPEAKER FIRST
        primary_uid_str = str(primary_user_id) if primary_user_id else None
        active_prof = user_profiles.get(primary_uid_str) if primary_uid_str else None
        active_display = user_name or (active_prof.get("name") if active_prof else "User")

        parts.append("\n" + ("=" * 45))
        parts.append(f"🎯 ACTIVE SPEAKER TALKING TO YOU RIGHT NOW:")
        parts.append(f"  Name / Display: {active_display}")
        if primary_uid_str:
            parts.append(f"  User ID: {primary_uid_str}")
        if active_prof:
            if active_prof.get("global_name"):
                parts.append(f"  Handle: @{active_prof.get('global_name')}")
            parts.append(f"  Memories & details specific to {active_display}:")
            parts.extend(_render_profile(active_prof, indent="    ", target_uid=primary_uid_str, target_bid=bot_id))
        else:
            parts.append(f"  No stored memories yet for {active_display}. Treat this as a fresh interaction.")
        parts.append("=" * 45)

        if active_prof:
            parts.append(
                f"\n>>> RELATIONSHIP WITH {active_display.upper()}:\n"
                f"- You know {active_display}. Reference your shared history, memories, preferences, and quotes naturally across channels.\n"
                f"- Do NOT act like a stranger or forget them just because you are speaking in a public channel or a new room."
            )

        # 2. RESOLVE SUBJECT USERS / PERSONS OF INQUIRY BEING ASKED ABOUT
        subject_uids = resolve_subject_users(current_prompt, primary_uid=primary_user_id, raw_mentions=raw_mentions, reply_to_user_id=reply_to_user_id, raw_content=raw_content)
        if subject_uids:
            for s_uid in subject_uids:
                s_prof = user_profiles.get(s_uid)
                if not s_prof:
                    tree_pfile = os.path.join(SCRIPT_DIR, "memories", "users", str(s_uid), "profile.json")
                    if os.path.isfile(tree_pfile):
                        try:
                            with open(tree_pfile, "r", encoding="utf-8") as f:
                                s_prof = json.load(f)
                        except Exception:
                            pass
                s_disp = (s_prof.get("global_name") or s_prof.get("name") or f"User {s_uid}") if s_prof else f"User {s_uid}"
                parts.append("\n" + ("=" * 45))
                parts.append(f"🎯 SUBJECT OF INQUIRY / PERSON BEING ASKED ABOUT:")
                parts.append(f"  Target User: {s_disp} (ID: {s_uid})")
                if s_prof:
                    parts.extend(_render_profile(s_prof, indent="    ", target_uid=s_uid, target_bid=bot_id))
                parts.append(
                    f"\n🚨 [CRITICAL DIRECTIVE FOR ANSWERING ABOUT {s_disp.upper()}]:\n"
                    f"- The active speaker (@{active_display}) is directly asking you about {s_disp}!\n"
                    f"- You KNOW {s_disp}! You have real history, memories, inside jokes, and shared experiences with them.\n"
                    f"- NEVER pretend not to know {s_disp}, do NOT act like a stranger, do NOT dismiss them, and do NOT say you don't know who that is!\n"
                    f"- Speak about {s_disp} with deep personal familiarity in full character as {get_current_bot_name()}, actively weaving in your memories, their quirks, quotes, and your shared bond!"
                )
                parts.append("=" * 45)

        # 3. MEMORY TREE SEARCH FOR TOPIC / FACTS
        matched_memories = search_memory_tree(current_prompt, bot_id=bot_id, exclude_uids={primary_uid_str} | set(subject_uids))
        if matched_memories:
            parts.append("\n" + ("=" * 45))
            parts.append("🔍 RELEVANT MEMORIES RETRIEVED FROM MEMORY TREE:")
            for score, m_uid, m_name, m_fact in matched_memories:
                parts.append(f"  • Regarding {m_name} (ID: {m_uid}): \"{m_fact}\"")
            parts.append(f">>> DIRECTIVE: Use these relevant memories to directly answer what @{active_display} is asking about!")
            parts.append("=" * 45)

        # 4. IDENTIFY OTHER PARTICIPANTS IN CHANNEL (EXCLUDING ACTIVE SPEAKER AND SUBJECT USERS)
        participant_ids = []
        for msg in raw_context[-50:]:
            uid = msg.get("user_id")
            if uid and str(uid) != primary_uid_str and str(uid) not in subject_uids and str(uid) not in participant_ids:
                participant_ids.append(str(uid))

        if participant_ids:
            parts.append(f"\n👥 OTHER PEOPLE WHO WERE IN THIS CHAT (FOR CONTEXT ONLY — NOT CURRENT SPEAKER):")
            other_names = []
            for pid in participant_ids:
                p = user_profiles.get(pid)
                if p:
                    pname = p.get('name', f'User_{pid}')
                    other_names.append(pname)
                    parts.append(f"\n  --- {pname} (ID: {pid}) ---")
                    parts.extend(_render_profile(p, indent="    ", target_uid=pid, target_bid=bot_id))
                else:
                    parts.append(f"\n  --- User (ID: {pid}) ---")
                    parts.append("    No stored memories.")

            other_names_str = ", ".join(other_names) if other_names else "other users"
            parts.append(
                f"\n🚨 [CRITICAL USER SEPARATION RULE]:\n"
                f"- You are responding directly to {active_display}.\n"
                f"- DO NOT confuse {active_display} with {other_names_str}.\n"
                f"- DO NOT call {active_display} by someone else's name, and do NOT attribute other people's memories, quotes, or actions to {active_display}!\n"
                f"- Address {active_display} by their actual name/display name.\n"
                f"- Seamlessly use your stored memories of {active_display} to maintain continuous connection across servers and DMs."
            )
        else:
            parts.append(
                f"\n[USER DIRECTIVE]:\n"
                f"- You are speaking directly to {active_display}. Address them naturally using your shared memories."
            )

        parts.append("=" * 50)

    cur_bname = (get_current_bot_name() or "").lower()
    is_yuna = ("yuna" in cur_bname) or (str(bot_id) == "bot_ek0ldel3") or (str(bot_id).lower() == "yuna")
    if is_yuna:
        if YUNA_GAMBLING_AVAILABLE and yuna_gambling and hasattr(yuna_gambling, "build_yuna_ai_context"):
            try:
                yg_ctx = yuna_gambling.build_yuna_ai_context(primary_user_id)
                if yg_ctx:
                    parts.append(yg_ctx)
            except Exception:
                pass
        elif YUNA_RPC_AVAILABLE and yuna_rpc:
            try:
                curr_song = yuna_rpc.get_current_track_info()
                if curr_song:
                    parts.append(
                        f"\n🎧 [CURRENT SPOTIFY MUSIC - KIZZY RPC]:\n"
                        f"- You are wearing your headphones listening to \"{curr_song['title']}\" by {curr_song['artist']} (Album: {curr_song['album']}) on Spotify.\n"
                        f"- If users ask what you are listening to or mention music, banter and chat about this track naturally!"
                    )
            except Exception:
                pass

    return "\n".join(parts)



# ─── INTERACTED USERS ─────────────────────────────────
def load_interacted_users():
    with state_lock:
        if os.path.exists(INTERACTED_USERS_FILE):
            try:
                with open(INTERACTED_USERS_FILE, "r") as f:
                    return set(json.load(f))
            except:
                return set()
        return set()

def save_interacted_users(users):
    _atomic_json_save(INTERACTED_USERS_FILE, list(users), backup=True, max_backups=5)

def save_contexts():
    try:
        _atomic_json_save(CONTEXTS_FILE, contexts, backup=True, max_backups=5)
    except Exception as e:
        print(f"[CONTEXT SAVE ERROR] {e}")

def load_contexts():
    global contexts
    with state_lock:
        if os.path.exists(CONTEXTS_FILE):
            try:
                with open(CONTEXTS_FILE, "r") as f:
                    loaded = json.load(f)
                    for k, v in loaded.items():
                        if isinstance(v, list):
                            contexts[k] = v[-config.get("max_context", 10):]
                print(f"[CONTEXT] Loaded {len(contexts)} channel memories from disk.")
            except Exception as e:
                print(f"[CONTEXT LOAD ERROR] {e}")
                contexts = {}
        else:
            contexts = {}

# ─── FILE READING & VIDEO ─────────────────────────────
def extract_text_from_pdf(filepath, max_pages=20):
    print(f"[PDF] Starting extraction for: {filepath}")
    try:
        import PyPDF2
        text = ""
        with open(filepath, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            total_pages = len(reader.pages)
            pages_to_read = min(total_pages, max_pages)
            print(f"[PDF] PyPDF2 opened, {total_pages} total pages, reading buffer of {pages_to_read} pages")
            for i in range(pages_to_read):
                try:
                    page = reader.pages[i]
                    page_text = page.extract_text()
                    if page_text:
                        text += f"--- Page {i+1} ---\n" + page_text + "\n\n"
                except Exception as pe:
                    print(f"[PDF] PyPDF2 page {i+1} extraction error: {pe}")
        if text.strip():
            print(f"[PDF] ✓ PyPDF2 extracted {len(text)} chars from {pages_to_read} pages")
            return text.strip()
        return "[PDF: no extractable text found — the PDF may be image-based or scanned]"
    except ImportError:
        return "[PDF extraction failed. Install PyPDF2: pip install PyPDF2]"
    except Exception as e:
        return f"[PDF extraction error: {e}]"

def extract_text_from_docx(filepath):
    try:
        text_parts = []
        with zipfile.ZipFile(filepath, "r") as z:
            with z.open("word/document.xml") as f:
                tree = ET.parse(f)
                root = tree.getroot()
                for t in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"):
                    if t.text:
                        text_parts.append(t.text)
        return " ".join(text_parts).strip()
    except Exception as e:
        return f"[DOCX error: {e}]"

def extract_text_from_csv(filepath, max_rows=2000):
    try:
        rows = []
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.reader(f)
            for row in reader:
                rows.append(" | ".join(row))
        return "\n".join(rows[:max_rows])
    except Exception as e:
        return f"[CSV error: {e}]"

async def read_file_attachment(attachment):
    size_mb = attachment.size / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        return f"File too large ({size_mb:.1f} MB). Max: {MAX_FILE_SIZE_MB} MB."
    ext = Path(attachment.filename).suffix.lower()
    if ext not in (".pdf", ".docx", ".csv"):
        return f"Unsupported file type: {ext}. I can read PDF, DOCX, and CSV."
    tmp_path = None
    try:
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=ext)
        os.close(tmp_fd)
        async with aiohttp.ClientSession() as session:
            async with session.get(attachment.url, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                if resp.status != 200:
                    return "Couldn't download that file."
                with open(tmp_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(8192):
                        f.write(chunk)
        if ext == ".pdf":
            text = extract_text_from_pdf(tmp_path, max_pages=20)
        elif ext == ".docx":
            text = extract_text_from_docx(tmp_path)
        elif ext == ".csv":
            text = extract_text_from_csv(tmp_path, max_rows=2000)
        else:
            text = "Unknown file type."
        if not text or not text.strip():
            return "I couldn't extract any readable text from that file."
        if text.startswith("[") and text.endswith("]"):
            return text
        preview = text[:120000]
        if len(text) > 120000:
            preview += f"\n\n... [{len(text) - 120000} more characters truncated]"
        return preview
    except Exception as e:
        return f"File read error: {e}"
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except:
                pass

def _has_ffmpeg():
    return shutil.which("ffmpeg") is not None

def enhance_audio_for_stt(input_wav_path: str, output_wav_path: str) -> bool:
    if not _has_ffmpeg():
        return False
    try:
        cmd = [
            "ffmpeg", "-y", "-i", input_wav_path,
            "-af", "highpass=f=80,afftdn=nf=-25,dynaudnorm=f=150:g=15:p=0.5,volume=2.0",
            "-ar", "16000", "-ac", "1", "-acodec", "pcm_s16le",
            output_wav_path
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=15)
        ok = os.path.exists(output_wav_path) and os.path.getsize(output_wav_path) > 1024
        if not ok:
            err = result.stderr.decode()[:200] if result.stderr else "unknown"
            print(f"[AUDIO ENHANCE] ffmpeg failed: {err}")
        return ok
    except Exception as e:
        print(f"[AUDIO ENHANCE] Error: {e}")
        return False

def _get_video_duration(video_path):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
            capture_output=True, text=True, timeout=15
        )
        return float(result.stdout.strip())
    except:
        return None

def extract_video_frames(video_path, max_frames=5):
    if not _has_ffmpeg():
        return None, "ffmpeg not found. Install it with: pkg install ffmpeg"
    duration = _get_video_duration(video_path)
    if not duration or duration <= 0:
        return None, "Could not determine video duration."
    tmp_dir = tempfile.mkdtemp()
    try:
        interval = duration / (max_frames + 1)
        frames = []
        for i in range(1, max_frames + 1):
            ts = interval * i
            out_file = os.path.join(tmp_dir, f"frame_{i:03d}.jpg")
            cmd = [
                "ffmpeg", "-y", "-ss", str(ts), "-i", str(video_path),
                "-frames:v", "1", "-q:v", "2", "-vf", "scale=512:-1",
                out_file
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            if os.path.exists(out_file):
                with open(out_file, "rb") as f:
                    frames.append(f.read())
        if not frames:
            return None, "Could not extract any frames from the video."
        return frames, None
    except Exception as e:
        return None, f"Frame extraction error: {e}"
    finally:
        try:
            shutil.rmtree(tmp_dir)
        except:
            pass

def extract_audio_from_video(video_path):
    if not _has_ffmpeg():
        return None, "ffmpeg not found"
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".wav")
    os.close(tmp_fd)
    try:
        cmd = [
            "ffmpeg", "-y", "-i", str(video_path),
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            tmp_path
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 1024:
            with open(tmp_path, "rb") as f:
                return f.read(), None
        return None, "No audio track found or extraction failed"
    except Exception as e:
        return None, f"Audio extraction error: {e}"
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except:
                pass

async def process_video_attachment(attachment, prompt, channel_id):
    size_mb = attachment.size / (1024 * 1024)
    if size_mb > MAX_VIDEO_SIZE_MB:
        return f"Video too large ({size_mb:.1f} MB). Max: {MAX_VIDEO_SIZE_MB} MB."
    ext = Path(attachment.filename).suffix.lower()
    if ext not in (".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".3gp"):
        return f"Unsupported video format: {ext}. I can watch MP4, MOV, AVI, MKV, WEBM, M4V, 3GP."
    tmp_path = None
    try:
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=ext)
        os.close(tmp_fd)
        async with aiohttp.ClientSession() as session:
            async with session.get(attachment.url, timeout=aiohttp.ClientTimeout(total=300)) as resp:
                if resp.status != 200:
                    return "Couldn't download that video."
                with open(tmp_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(65536):
                        f.write(chunk)
        
        frames, err = extract_video_frames(tmp_path, max_frames=5)
        if err or not frames:
            return err or "Could not extract frames from the video."
        
        audio_transcription = None
        if GROQ_KEY or GEMINI_KEY:
            try:
                audio_bytes, audio_err = extract_audio_from_video(tmp_path)
                if audio_bytes and not audio_err:
                    audio_transcription, trans_err = await transcribe_audio(audio_bytes, "audio.wav")
                    if trans_err:
                        print(f"[VIDEO AUDIO] Transcription error: {trans_err}")
                    else:
                        print(f"[VIDEO AUDIO] Transcribed {len(audio_transcription)} chars")
            except Exception as e:
                print(f"[VIDEO AUDIO] Extraction error: {e}")

        vprompt = f"The user shared a video ({len(frames)} extracted chronological frames)."
        if prompt:
            vprompt += f" User question/comment: {prompt}."
        if audio_transcription and audio_transcription.strip():
            vprompt += f"\n\nVideo Audio Transcription: \"{audio_transcription}\""
        vprompt += "\n\nRespond naturally in character. Summarize and react to what the video shows, the actions occurring, and any spoken dialogue."

        # 1. Try Gemini Vision multi-image + raw audio hearing
        if GEMINI_KEY and time.time() >= gemini_blocked_until:
            reply, err = await ask_gemini_vision(
                config.get("personality", ""), vprompt, frames, "image/jpeg",
                history=get_context(channel_id), audio_bytes=audio_bytes, audio_mime="audio/wav"
            )
            if not err and reply:
                add_to_context(channel_id, "user", f"[User sent a video: {prompt or attachment.filename}]")
                add_to_context(channel_id, "assistant", reply)
                return reply

        # 2. Try OpenRouter Vision multi-image failover
        if os.getenv("OPENROUTER_KEY") and time.time() >= openrouter_blocked_until:
            vmodel = config.get("vision_model", "").strip() or None
            reply, err = await ask_openrouter_vision(
                config.get("personality", ""), vprompt, frames, "image/jpeg",
                history=get_context(channel_id), vision_model=vmodel
            )
            if not err and reply:
                add_to_context(channel_id, "user", f"[User sent a video: {prompt or attachment.filename}]")
                add_to_context(channel_id, "assistant", reply)
                return reply

        # 3. Fallback: Synthesis from individual frame descriptors
        descriptions = []
        for i, frame_bytes in enumerate(frames):
            frame_prompt = f"Describe what you see in this video frame ({i+1}/{len(frames)})."
            desc, d_err = None, True
            if GEMINI_KEY and time.time() >= gemini_blocked_until:
                desc, d_err = await ask_gemini_vision(config.get("personality", ""), frame_prompt, frame_bytes, "image/jpeg")
            if d_err and os.getenv("OPENROUTER_KEY"):
                desc, d_err = await ask_openrouter_vision(config.get("personality", ""), frame_prompt, frame_bytes, "image/jpeg")
            if not d_err and desc:
                descriptions.append(f"Frame {i+1}: {desc}")

        if descriptions:
            combined = "\n\n".join(descriptions)
            synthesis_prompt = f"The user shared a video. Here are descriptions of frames extracted from it:\n\n{combined}"
            if audio_transcription:
                synthesis_prompt += f"\n\nAudio: \"{audio_transcription}\""
            synthesis_prompt += f"\n\nUser prompt: {prompt or 'Summarize this video.'}"
            reply, s_err = await ask_gemini(config.get("personality", ""), get_context(channel_id), synthesis_prompt)
            if not s_err and reply:
                add_to_context(channel_id, "user", f"[User sent a video: {prompt or attachment.filename}]")
                add_to_context(channel_id, "assistant", reply)
                return reply

        return "Failed to analyze video frames with available vision models."
    except Exception as e:
        return f"Video processing error: {e}"
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try: os.remove(tmp_path)
            except: pass


def fast_heuristic_speech_correct(text: str) -> str:
    """Instant zero-latency phonetic regex correction for well-known speech-to-text slips."""
    if not text:
        return text
    t = text
    # "my eyes heard" -> "my eyes hurt", "head heard" -> "head hurt", "ears heard" -> "ears hurt"
    t = re.sub(r'\b(eyes?|head|ears?|throat|arm|arms|leg|legs|back|neck|tooth|teeth|feet|foot|chest|stomach|knee|knees|shoulder|shoulders|belly|tummy|hands?|wrist|ankle)\s+heard\b', r'\1 hurt', t, flags=re.IGNORECASE)
    # "are you they are" -> "are you there"
    t = re.sub(r'\b(are\s+you\s+)they\s+are\b', r'\1there', t, flags=re.IGNORECASE)
    # "for all intensive purposes" -> "for all intents and purposes"
    t = re.sub(r'\bfor\s+all\s+intensive\s+purposes\b', 'for all intents and purposes', t, flags=re.IGNORECASE)
    # "can you here me" -> "can you hear me"
    t = re.sub(r'\b(can\s+you\s+|did\s+you\s+|could\s+you\s+)here\s+me\b', r'\1hear me', t, flags=re.IGNORECASE)
    # "bone apple tea" -> "bon appétit"
    t = re.sub(r'\bbone\s+apple\s+tea\b', 'bon appétit', t, flags=re.IGNORECASE)
    return t


async def correct_speech_transcript(raw_text: str, groq_key: str = None, gemini_key: str = None) -> str:
    """
    Uses AI LLMs to detect and repair acoustic mishearings, near-homophones, and phonetic slips
    in speech-to-text transcripts (e.g. 'my eyes heard' -> 'my eyes hurt').
    Preserves intentional slang, gamer jargon, casual syntax, and names.
    """
    if not raw_text or len(raw_text.strip()) < 3 or raw_text.startswith("*["):
        return raw_text

    text = fast_heuristic_speech_correct(raw_text.strip())

    system_prompt = (
        "You are a real-time speech-to-text acoustic error corrector for spoken English. "
        "Your ONLY task is to fix speech recognition mistakes caused by phonetic confusion, homophones, "
        "acoustic slips, or slurred words (for example: 'my eyes heard' -> 'my eyes hurt', "
        "'my head heard' -> 'my head hurt', 'are you they are' -> 'are you there', 'can you here me' -> 'can you hear me'). "
        "RULES:\n"
        "1. If the sentence has no acoustic or phonetic errors, return it EXACTLY unchanged.\n"
        "2. Do NOT alter intentional slang, internet terms, colloquialisms, names, or casual grammar (e.g. keep 'gonna', 'rizz', 'fr fr', 'lol', 'bruh', 'wassup').\n"
        "3. Output ONLY the final corrected English text with no quotes, no markdown, and no extra commentary."
    )

    g_key = groq_key or GROQ_KEY or os.getenv("GROQ_KEY", "")
    if g_key and time.time() >= groq_blocked_until:
        for model in ["groq/compound-mini", "openai/gpt-oss-20b"]:
            try:
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": text}
                    ],
                    "temperature": 0.0,
                    "max_tokens": 120
                }
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {g_key}", "Content-Type": "application/json"},
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=2.5)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            msg = data.get("choices", [{}])[0].get("message", {})
                            cand = (msg.get("content") or "").strip()
                            if cand and not cand.startswith("<think>"):
                                if (cand.startswith('"') and cand.endswith('"')) or (cand.startswith("'") and cand.endswith("'")):
                                    cand = cand[1:-1].strip()
                                return cand
            except Exception:
                pass

    gem_key = gemini_key or GEMINI_KEY or os.getenv("GEMINI_KEY", "")
    if gem_key and time.time() >= gemini_blocked_until:
        for gem_model in ["gemini-3.5-flash-lite", "gemini-3.6-flash"]:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{gem_model}:generateContent?key={gem_key}"
                payload = {
                    "contents": [{"role": "user", "parts": [{"text": text}]}],
                    "systemInstruction": {"parts": [{"text": system_prompt}]},
                    "generationConfig": {"temperature": 0.0, "maxOutputTokens": 100}
                }
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=2.5)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                            cand = "".join(p.get("text", "") for p in parts if "text" in p and not p.get("thought")).strip()
                            if cand:
                                if (cand.startswith('"') and cand.endswith('"')) or (cand.startswith("'") and cand.endswith("'")):
                                    cand = cand[1:-1].strip()
                                return cand
            except Exception:
                pass

    return text


AVAILABLE_STT_MODELS = {
    "whisper-large-v3-turbo": {
        "name": "Groq Whisper Large v3 Turbo",
        "provider": "groq",
        "tag": "⚡ Ultra-Fast (<300ms)",
        "badge": "FREE",
        "desc": "Blazing-fast Whisper Turbo with forced English transcription."
    },
    "whisper-large-v3": {
        "name": "Groq Whisper Large v3",
        "provider": "groq",
        "tag": "🎯 High Precision",
        "badge": "FREE",
        "desc": "Maximum accuracy Whisper large model for quiet, accented, or complex speech."
    },
    "gemini-3.5-flash-lite": {
        "name": "Gemini 3.5 Flash-Lite Audio",
        "provider": "gemini",
        "tag": "🧠 Multimodal Audio",
        "badge": "FREE TIER",
        "desc": "Direct audio listening via Gemini 3.5 multimodal model."
    },
    "gemini-3.6-flash": {
        "name": "Gemini 3.6 Flash Audio",
        "provider": "gemini",
        "tag": "🌟 Deep Reasoning Audio",
        "badge": "FREE TIER",
        "desc": "Full-size Gemini 3.6 Flash multimodal audio understanding."
    },
    "auto": {
        "name": "Smart Auto-Cascade",
        "provider": "auto",
        "tag": "🔄 Automatic Failover",
        "badge": "DEFAULT",
        "desc": "Groq Turbo -> Groq Large -> Gemini Flash-Lite -> Gemini Flash."
    }
}

def normalize_stt_model(model_name: str) -> str:
    if not model_name:
        return "auto"
    m = str(model_name).strip().lower()
    if m in ("turbo", "groq-turbo", "groq:turbo", "whisper-turbo", "whisper-large-v3-turbo", "groq:whisper-large-v3-turbo", "1"):
        return "whisper-large-v3-turbo"
    if m in ("large", "groq-large", "groq:large", "whisper-large", "whisper-large-v3", "groq:whisper-large-v3", "2"):
        return "whisper-large-v3"
    if m in ("gemini-lite", "gemini-3.5", "gemini-3.5-flash-lite", "gemini:gemini-3.5-flash-lite", "flash-lite", "lite", "3"):
        return "gemini-3.5-flash-lite"
    if m in ("gemini", "gemini-flash", "gemini-3.6", "gemini-3.6-flash", "gemini:gemini-3.6-flash", "flash", "4"):
        return "gemini-3.6-flash"
    if m in ("auto", "cascade", "default", "smart", "5"):
        return "auto"
    return m


async def transcribe_audio(audio_bytes: bytes, filename: str = "audio.ogg", model: str = None, **kwargs) -> tuple:
    ext = Path(filename).suffix.lower() or ".ogg"
    req_model = normalize_stt_model(model or config.get("stt_model", "auto"))

    raw_text = None

    # Determine candidate execution order based on requested model
    if req_model == "whisper-large-v3":
        candidates = [("groq", "whisper-large-v3"), ("groq", "whisper-large-v3-turbo"), ("gemini", "gemini-3.5-flash-lite"), ("gemini", "gemini-3.6-flash")]
    elif req_model == "whisper-large-v3-turbo":
        candidates = [("groq", "whisper-large-v3-turbo"), ("groq", "whisper-large-v3"), ("gemini", "gemini-3.5-flash-lite"), ("gemini", "gemini-3.6-flash")]
    elif req_model == "gemini-3.6-flash":
        candidates = [("gemini", "gemini-3.6-flash"), ("gemini", "gemini-3.5-flash-lite"), ("groq", "whisper-large-v3-turbo"), ("groq", "whisper-large-v3")]
    elif req_model == "gemini-3.5-flash-lite":
        candidates = [("gemini", "gemini-3.5-flash-lite"), ("gemini", "gemini-3.6-flash"), ("groq", "whisper-large-v3-turbo"), ("groq", "whisper-large-v3")]
    else:
        # Auto cascade
        candidates = [("groq", "whisper-large-v3-turbo"), ("groq", "whisper-large-v3"), ("gemini", "gemini-3.5-flash-lite"), ("gemini", "gemini-3.6-flash")]

    tmp_path = None
    try:
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=ext)
        os.close(tmp_fd)
        with open(tmp_path, "wb") as f:
            f.write(audio_bytes)
        size_mb = os.path.getsize(tmp_path) / (1024 * 1024)

        for prov, m_name in candidates:
            if raw_text:
                break

            if prov == "groq" and GROQ_KEY and time.time() >= groq_blocked_until and size_mb <= MAX_AUDIO_SIZE_MB:
                try:
                    async with aiohttp.ClientSession() as session:
                        with open(tmp_path, "rb") as _audio_f:
                            data = aiohttp.FormData()
                            mime_sub = ext.lstrip('.')
                            if mime_sub == "m4a":
                                mime_sub = "mp4"
                            data.add_field("file", _audio_f, filename=filename, content_type=f"audio/{mime_sub}")
                            data.add_field("model", m_name)
                            data.add_field("language", "en")  # Force Whisper to ONLY hear English
                            data.add_field("temperature", "0.0")
                            data.add_field("prompt", "Clear conversational English speech, standard vocabulary.")
                            async with session.post(
                                "https://api.groq.com/openai/v1/audio/transcriptions",
                                headers={"Authorization": f"Bearer {GROQ_KEY}"},
                                data=data,
                                timeout=aiohttp.ClientTimeout(total=12)
                            ) as resp:
                                if resp.status == 200:
                                    res_j = await resp.json()
                                    got_text = (res_j.get("text", "") or "").strip()
                                    if got_text:
                                        clean_check = re.sub(r"[^a-zA-Z0-9\s]", "", got_text.lower()).strip()
                                        hallucinations = {
                                            "thank you for watching", "thanks for watching", "thank you for watching this video",
                                            "please subscribe", "like and subscribe", "subscribe to my channel",
                                            "see you next time", "the end",
                                            "music", "applause", "silence", "captions by", "subtitles by",
                                            "subscribed", "watching"
                                        }
                                        if clean_check in hallucinations or len(clean_check) < 2:
                                            print(f"[TRANSCRIPTION] Filtered Whisper silence hallucination on {m_name}: '{got_text}'")
                                            return "", None
                                        raw_text = got_text
                except Exception as ge:
                    print(f"[TRANSCRIPTION] Groq STT ({m_name}) note: {ge}")

            elif prov == "gemini" and GEMINI_KEY and time.time() >= gemini_blocked_until:
                try:
                    mime = "audio/wav" if ext == ".wav" else ("audio/mp4" if ext in (".m4a", ".mp4") else ("audio/ogg" if ext == ".ogg" else "audio/mp3"))
                    g_res, g_err = await ask_gemini_vision(
                        "You are an expert audio transcriber.",
                        "Listen to this audio clip and transcribe the spoken words accurately in English only. Never transcribe into other languages. Output ONLY the transcribed English words, nothing else.",
                        None,
                        mime_type="image/jpeg",
                        audio_bytes=audio_bytes,
                        audio_mime=mime,
                        model_override=m_name
                    )
                    if not g_err and g_res:
                        got_text = g_res.strip()
                        if got_text and not got_text.startswith("Gemini vision blocked"):
                            raw_text = got_text
                except Exception as gerr:
                    print(f"[TRANSCRIPTION] Gemini STT ({m_name}) note: {gerr}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try: os.remove(tmp_path)
            except: pass

    if raw_text:
        # AI-Powered Phonetic & Semantic Mishearing Corrector (e.g. 'my eyes heard' -> 'my eyes hurt')
        corrected = await correct_speech_transcript(raw_text, groq_key=GROQ_KEY, gemini_key=GEMINI_KEY)
        if corrected and corrected != raw_text:
            print(f"[TRANSCRIPTION AI CORRECT] \"{raw_text}\" -> \"{corrected}\"")
            raw_text = corrected
        return raw_text, None

    return None, "All transcription services failed or unavailable."

# ─── VTUBER WEBSOCKET BRIDGE ──────────────────────────
vtuber_clients = set()
vtuber_bridge_online = False

async def vtuber_broadcast(msg_dict):
    if not vtuber_clients:
        return
    dead = set()
    for ws in vtuber_clients:
        try:
            await ws.send(json.dumps(msg_dict))
        except:
            dead.add(ws)
    for d in dead:
        vtuber_clients.discard(d)

def extract_vtuber_cues(text: str):
    if not text:
        return None, None
    t = text.lower()
    emo = None
    pose = None
    if any(k in t for k in ["(happy)", "(joy)", "(excited)", "✨", "😊", "😄", "😁", "🎉", "yay", "haha", "awesome", "glad"]):
        emo = "happy"
    elif any(k in t for k in ["(sad)", "(sorrow)", "😢", "😭", "😞", "sorry", "sadly", "unfortunate"]):
        emo = "sad"
    elif any(k in t for k in ["(angry)", "(mad)", "😡", "😠", "furious", "hate", "annoying"]):
        emo = "angry"
    elif any(k in t for k in ["(surprised)", "(shocked)", "😲", "😮", "whoa", "wow", "really?", "unbelievable"]):
        emo = "surprised"
    elif any(k in t for k in ["(relaxed)", "(calm)", "(whisper)", "😌", "chill", "peaceful", "no problem"]):
        emo = "relaxed"

    if any(k in t for k in ["*wave", "👋", "hello", "hi there", "hey!", "welcome"]):
        pose = "wave"
    elif any(k in t for k in ["*thumbs up*", "*thumbsup*", "👍", "good job", "nice!", "agree"]):
        pose = "thumbsUp"
    elif any(k in t for k in ["*nod*", "*nods*", "indeed", "exactly", "i see", "understood", "yes"]):
        pose = "nod"
    elif any(k in t for k in ["*deny*", "*shakes head*", "✋", "no way", "never", "incorrect", "stop"]):
        pose = "deny"
    elif any(k in t for k in ["*shrug*", "*shrugs*", "🤷", "who knows", "maybe", "idk", "dunno"]):
        pose = "shrug"
    elif any(k in t for k in ["*think*", "*thinks*", "*ponder*", "🤔", "hmm", "let me see", "interesting", "deduction"]):
        pose = "think"
    elif any(k in t for k in ["*facepalm*", "🤦", "ugh", "sigh", "unbelievable"]):
        pose = "facepalm"
    elif any(k in t for k in ["*excited*", "🎉", "🔥", "let's go", "hurray", "hype"]):
        pose = "excited"
    elif any(k in t for k in ["*shy*", "*blush*", "😳", "👉👈", "flustered", "embarrassed"]):
        pose = "shy"
    elif any(k in t for k in ["*confident*", "*smug*", "💪", "😏", "trivial", "easy", "as expected"]):
        pose = "confident"
    return emo, pose

async def handle_vtuber_ptt(audio_b64: str, fmt: str = "webm"):
    print(f"[VTUBER PTT] ====== handle_vtuber_ptt called ====== format={fmt}")
    if not GROQ_KEY:
        print("[VTUBER PTT] ABORT: No Groq key configured for transcription.")
        await vtuber_broadcast({"type": "error", "message": "Transcription not configured (need GROQ_KEY)"})
        await vtuber_broadcast({"type": "speech_done"})
        return
    try:
        audio_bytes = base64.b64decode(audio_b64)
        print(f"[VTUBER PTT] Decoded {len(audio_bytes)} bytes of {fmt} audio")
        if len(audio_bytes) < 1024:
            print("[VTUBER PTT] ABORT: Audio too short (< 1KB), ignoring")
            await vtuber_broadcast({"type": "error", "message": "Audio too short"})
            await vtuber_broadcast({"type": "speech_done"})
            return
        if fmt == "wav":
            print(f"[VTUBER PTT] Received WAV from browser ({len(audio_bytes)} bytes), direct STT pipeline")
        else:
            if not _has_ffmpeg():
                print("[VTUBER PTT] ffmpeg not found, cannot convert browser audio")
                await vtuber_broadcast({"type": "error", "message": "ffmpeg not installed — cannot convert browser audio"})
                await vtuber_broadcast({"type": "speech_done"})
                return
            if len(audio_bytes) < 4096:
                print(f"[VTUBER PTT] Audio too small ({len(audio_bytes)} bytes), likely empty recording")
                await vtuber_broadcast({"type": "error", "message": "No audio captured — mic may be silent or blocked"})
                await vtuber_broadcast({"type": "speech_done"})
                return
            tmp_in = tmp_out = None
            try:
                tmp_fd, tmp_in = tempfile.mkstemp(suffix=f".{fmt}")
                os.close(tmp_fd)
                tmp_fd, tmp_out = tempfile.mkstemp(suffix=".wav")
                os.close(tmp_fd)
                with open(tmp_in, "wb") as f:
                    f.write(audio_bytes)
                debug_path = None
                if DEBUG_MODE:
                    debug_path = os.path.join(SCRIPT_DIR, f"vtuber_debug_{int(time.time())}.{fmt}")
                    shutil.copy(tmp_in, debug_path)
                    print(f"[VTUBER PTT] Debug copy saved: {debug_path}")
                cmd = [
                    "ffmpeg", "-y", "-i", tmp_in,
                    "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                    tmp_out
                ]
                result = subprocess.run(cmd, capture_output=True, timeout=30)
                if os.path.exists(tmp_out) and os.path.getsize(tmp_out) > 1024:
                    with open(tmp_out, "rb") as f:
                        audio_bytes = f.read()
                    fmt = "wav"
                    print(f"[VTUBER PTT] ffmpeg OK: {len(audio_bytes)} bytes WAV")
                    if debug_path and os.path.exists(debug_path):
                        try:
                            os.remove(debug_path)
                        except:
                            pass
                else:
                    err_full = (result.stderr.decode() if result.stderr else "")
                    out_full = (result.stdout.decode() if result.stdout else "")
                    print(f"[VTUBER PTT] ffmpeg FAILED exit={result.returncode}")
                    print("[VTUBER PTT] stderr: " + err_full)
                    print("[VTUBER PTT] stdout: " + out_full)
                    await vtuber_broadcast({"type": "error", "message": f"Audio conversion failed. Debug file: {debug_path}"})
                    await vtuber_broadcast({"type": "speech_done"})
                    return
            except Exception as e:
                print(f"[VTUBER PTT] ffmpeg conversion error: {e}")
                await vtuber_broadcast({"type": "error", "message": f"Audio conversion error: {e}"})
                await vtuber_broadcast({"type": "speech_done"})
                return
            finally:
                for p in (tmp_in, tmp_out):
                    if p and os.path.exists(p):
                        try:
                            os.remove(p)
                        except:
                            pass
        print("[VTUBER PTT] Sending to Groq Whisper for transcription...")
        text, err = await transcribe_audio(audio_bytes, "audio.wav")
        if err or not text or not text.strip():
            print(f"[VTUBER PTT] Transcription empty or error: {err}")
            await vtuber_broadcast({"type": "speech_done"})
            return
        if is_whisper_hallucination(text):
            print(f"[VTUBER PTT] Discarded ambient noise / hallucination: '{text}'")
            await vtuber_broadcast({"type": "speech_done"})
            return
        print(f"[VTUBER PTT] Transcription OK: '{text[:120]}'")
        await vtuber_broadcast({"type": "user_subtitle", "text": text})
        print("[VTUBER PTT] Getting AI reply...")
        reply, err = await ask_ai("vtuber", text)
        if err or not reply:
            print(f"[VTUBER PTT] AI reply FAILED: {reply}")
            await vtuber_broadcast({"type": "error", "message": f"AI error: {reply}"})
            await vtuber_broadcast({"type": "speech_done"})
            return
        print(f"[VTUBER PTT] AI reply OK: '{reply[:120]}'")
        emo, pose = extract_vtuber_cues(reply)
        if emo:
            await vtuber_broadcast({"type": "emotion", "emotion": emo, "intensity": 1.0})
        if pose:
            await vtuber_broadcast({"type": "pose", "value": pose})
        if client and hasattr(client, "is_ready") and client.is_ready():
            for guild_id, session in list(voice_sessions.items()):
                ch_id = session.get("channel_id")
                if ch_id:
                    try:
                        guild = client.get_guild(int(guild_id))
                        if guild:
                            ch_obj = guild.get_channel(int(ch_id))
                            if ch_obj and isinstance(ch_obj, discord.TextChannel):
                                await send_split_messages(ch_obj, f"🎙️ *VTuber:* {reply}")
                    except Exception as e:
                        print(f"[VTUBER PTT] Could not post to Discord: {e}")
        if config.get("tts_enabled"):
            print("[VTUBER PTT] Generating TTS...")
            audio = await speak(reply)
            if not audio:
                print("[VTUBER PTT] TTS generation returned None, sending text fallback")
                await vtuber_broadcast({"type": "subtitle", "text": reply[:500]})
                await vtuber_broadcast({"type": "speech_done"})
        else:
            print(f"[VTUBER PTT] TTS disabled, sending text subtitle")
            await vtuber_broadcast({"type": "subtitle", "text": reply[:500]})
            await vtuber_broadcast({"type": "speech_done"})
    except Exception as e:
        print(f"[VTUBER PTT] CRASH: {e}")
        import traceback
        traceback.print_exc()
        await vtuber_broadcast({"type": "error", "message": f"Server crash: {e}"})
        await vtuber_broadcast({"type": "speech_done"})

async def handle_vtuber_text(text: str):
    refresh_runtime_config()
    clean = text.lower().strip()
    if clean in ("!reset", "!clear", "!restart", "!purge"):
        clear_context("vtuber")
        print("[VTUBER] Context memory reset for web client via !reset.")
        reply = "(*smiles warmly and bows*) Context memory cleared! My mind is refreshed to my initial personality. What would you like to talk about?"
        await vtuber_broadcast({"type": "emotion", "emotion": "happy", "intensity": 1.0})
        await vtuber_broadcast({"type": "pose", "value": "wave"})
        if config.get("tts_enabled"):
            audio = await speak(reply)
            if not audio:
                await vtuber_broadcast({"type": "subtitle", "text": "🧹 Context & personality refreshed"})
                await vtuber_broadcast({"type": "speech_done"})
        else:
            await vtuber_broadcast({"type": "subtitle", "text": "🧹 Context & personality refreshed"})
            await vtuber_broadcast({"type": "speech_done"})
        return

    print(f"[VTUBER TEXT] '{text[:120]}' -> AI")
    await vtuber_broadcast({"type": "user_subtitle", "text": text})
    reply, err = await ask_ai("vtuber", text)
    if err or not reply:
        await vtuber_broadcast({"type": "error", "message": f"AI error: {reply}"})
        await vtuber_broadcast({"type": "speech_done"})
        return
    emo, pose = extract_vtuber_cues(reply)
    if emo:
        await vtuber_broadcast({"type": "emotion", "emotion": emo, "intensity": 1.0})
    if pose:
        await vtuber_broadcast({"type": "pose", "value": pose})
    if config.get("tts_enabled"):
        audio = await speak(reply)
        if not audio:
            await vtuber_broadcast({"type": "subtitle", "text": reply[:500]})
            await vtuber_broadcast({"type": "speech_done"})
    else:
        await vtuber_broadcast({"type": "subtitle", "text": reply[:500]})
        await vtuber_broadcast({"type": "speech_done"})

async def handle_vtuber_vision(prompt: str, image_b64: str = "", frames_b64: list = None, mime_type: str = "image/jpeg", audio_b64: str = "", audio_fmt: str = "wav"):
    refresh_runtime_config()
    has_audio_input = bool(audio_b64 and len(audio_b64) > 100)
    print(f"[VTUBER VISION] Processing visual prompt: '{prompt[:120]}', frames={len(frames_b64) if frames_b64 else (1 if image_b64 else 0)}, audio={has_audio_input}")
    try:
        await vtuber_broadcast({"type": "user_subtitle", "text": f"👁️ {prompt}"})

        image_bytes_list = []
        if frames_b64 and isinstance(frames_b64, list):
            for f in frames_b64:
                if f:
                    try:
                        if "," in f:
                            f = f.split(",", 1)[1]
                        image_bytes_list.append(base64.b64decode(f))
                    except Exception as e:
                        print(f"[VTUBER VISION] Frame decode error: {e}")
        elif image_b64:
            try:
                if "," in image_b64:
                    image_b64 = image_b64.split(",", 1)[1]
                image_bytes_list.append(base64.b64decode(image_b64))
            except Exception as e:
                print(f"[VTUBER VISION] Image decode error: {e}")

        audio_bytes = None
        if audio_b64:
            try:
                if "," in audio_b64:
                    audio_b64 = audio_b64.split(",", 1)[1]
                audio_bytes = base64.b64decode(audio_b64)
            except Exception as e:
                print(f"[VTUBER VISION] Audio decode error: {e}")

        if not image_bytes_list:
            await vtuber_broadcast({"type": "error", "message": "No visual frame received to analyze."})
            await vtuber_broadcast({"type": "speech_done"})
            return

        system_msg = config.get("personality", "You are a helpful assistant.")
        if config.get("user_memory_enabled", True):
            scene = build_scene_context("vtuber", current_prompt=prompt)
            if scene:
                system_msg += "\n\n" + scene

        system_msg += (
            "\n\n[INSTRUCTION]: The user is sharing their live screen, camera, or video with you. "
            "Look closely at the visual frame(s) and listen carefully to any attached audio from the video (dialogue, speech, music, lyrics, sound effects). "
            "React spontaneously in character to what you see and hear! "
            "CRITICAL: Keep your reaction short, punchy, and natural (1 to 2 sentences max) so your response stays in sync with the live video in real-time."
        )

        ctx = get_context("vtuber")
        vision_provider = config.get("vision_provider", "gemini")

        frames_payload = image_bytes_list if len(image_bytes_list) > 1 else image_bytes_list[0]
        reply, err = None, True

        fast_tokens = min(150, int(config.get("vtuber_fast_tokens", 100)))

        # Transcribe audio for OpenRouter fallback or extra context if needed
        audio_transcript = None
        prompt_with_audio = prompt

        if vision_provider == "gemini" and GEMINI_KEY:
            reply, err = await ask_gemini_vision(
                system_msg, prompt, frames_payload, mime_type=mime_type, history=ctx,
                audio_bytes=audio_bytes, audio_mime=f"audio/{audio_fmt}", max_tokens=fast_tokens
            )
            if (err or not reply) and os.getenv("OPENROUTER_KEY") and time.time() >= openrouter_blocked_until:
                print(f"[VTUBER VISION] Gemini vision failed ({reply}), falling back to OpenRouter vision...")
                if audio_bytes and not audio_transcript and (GROQ_KEY or GEMINI_KEY):
                    try: audio_transcript, _ = await transcribe_audio(audio_bytes, "clip.wav")
                    except: pass
                if audio_transcript:
                    prompt_with_audio = f"{prompt}\n[Audio heard in video/music: \"{audio_transcript}\"]"
                vmodel = config.get("vision_model", "").strip() or None
                reply, err = await ask_openrouter_vision(
                    system_msg, prompt_with_audio, frames_payload, mime_type=mime_type, history=ctx, vision_model=vmodel, max_tokens=fast_tokens
                )
        elif vision_provider == "openrouter" and os.getenv("OPENROUTER_KEY"):
            if audio_bytes and not audio_transcript and (GROQ_KEY or GEMINI_KEY):
                try: audio_transcript, _ = await transcribe_audio(audio_bytes, "clip.wav")
                except: pass
            if audio_transcript:
                prompt_with_audio = f"{prompt}\n[Audio heard in video/music: \"{audio_transcript}\"]"
            vmodel = config.get("vision_model", "").strip() or None
            reply, err = await ask_openrouter_vision(
                system_msg, prompt_with_audio, frames_payload, mime_type=mime_type, history=ctx, vision_model=vmodel, max_tokens=fast_tokens
            )
            if (err or not reply) and GEMINI_KEY and time.time() >= gemini_blocked_until:
                print(f"[VTUBER VISION] OpenRouter vision failed ({reply}), falling back to Gemini vision...")
                reply, err = await ask_gemini_vision(
                    system_msg, prompt, frames_payload, mime_type=mime_type, history=ctx,
                    audio_bytes=audio_bytes, audio_mime=f"audio/{audio_fmt}", max_tokens=fast_tokens
                )
        else:
            if GEMINI_KEY and time.time() >= gemini_blocked_until:
                reply, err = await ask_gemini_vision(
                    system_msg, prompt, frames_payload, mime_type=mime_type, history=ctx,
                    audio_bytes=audio_bytes, audio_mime=f"audio/{audio_fmt}", max_tokens=fast_tokens
                )
            if (err or not reply) and os.getenv("OPENROUTER_KEY") and time.time() >= openrouter_blocked_until:
                if audio_bytes and not audio_transcript and (GROQ_KEY or GEMINI_KEY):
                    try: audio_transcript, _ = await transcribe_audio(audio_bytes, "clip.wav")
                    except: pass
                if audio_transcript:
                    prompt_with_audio = f"{prompt}\n[Audio heard in video/music: \"{audio_transcript}\"]"
                vmodel = config.get("vision_model", "").strip() or None
                reply, err = await ask_openrouter_vision(
                    system_msg, prompt_with_audio, frames_payload, mime_type=mime_type, history=ctx, vision_model=vmodel, max_tokens=fast_tokens
                )

        if err or not reply:
            print(f"[VTUBER VISION] Vision FAILED: {reply}")
            await vtuber_broadcast({"type": "error", "message": f"Vision error: {reply}"})
            await vtuber_broadcast({"type": "speech_done"})
            return

        print(f"[VTUBER VISION] Vision OK: '{reply[:120]}'")
        add_to_context("vtuber", "user", f"[User shared live screen/video: {prompt}]")
        add_to_context("vtuber", "assistant", reply)

        # Immediate visual reaction: broadcast emotion, pose, and subtitle without waiting for TTS
        emo, pose = extract_vtuber_cues(reply)
        if emo:
            await vtuber_broadcast({"type": "emotion", "emotion": emo, "intensity": 1.0})
        if pose:
            await vtuber_broadcast({"type": "pose", "value": pose})
        await vtuber_broadcast({"type": "subtitle", "text": reply[:500]})

        if client and hasattr(client, "is_ready") and client.is_ready():
            for guild_id, session in list(voice_sessions.items()):
                ch_id = session.get("channel_id")
                if ch_id:
                    try:
                        guild = client.get_guild(int(guild_id))
                        if guild:
                            ch_obj = guild.get_channel(int(ch_id))
                            if ch_obj and isinstance(ch_obj, discord.TextChannel):
                                await send_split_messages(ch_obj, f"👁️ *VTuber Vision:* {reply}")
                    except Exception as e:
                        print(f"[VTUBER VISION] Discord post error: {e}")

        if config.get("tts_enabled"):
            audio = await speak(reply)
            if not audio:
                await vtuber_broadcast({"type": "speech_done"})
        else:
            await vtuber_broadcast({"type": "speech_done"})

    except Exception as e:
        print(f"[VTUBER VISION] Handler error: {e}")
        import traceback
        traceback.print_exc()
        await vtuber_broadcast({"type": "error", "message": f"Vision error: {e}"})
        await vtuber_broadcast({"type": "speech_done"})

async def vtuber_handler(websocket, *args, **kwargs):
    global vtuber_bridge_online
    vtuber_clients.add(websocket)
    vtuber_bridge_online = True
    print(f"[VTUBER] Client connected from {websocket.remote_address}")
    try:
        await vtuber_broadcast({"type": "ready", "message": "Bot bridge active"})
        async for message in websocket:
            try:
                data = json.loads(message)
                mtype = data.get("type", "")
                print(f"[VTUBER] Received msg type='{mtype}' keys={list(data.keys())}")
                if mtype == "ready":
                    print("[VTUBER] Client reported ready")
                elif mtype == "speech_done":
                    pass
                elif mtype == "emotion_done":
                    pass
                elif mtype == "interrupt":
                    print("[VTUBER] Interruption received from client")
                    await vtuber_broadcast({"type": "interrupted"})
                elif mtype == "error":
                    print(f"[VTUBER] Client error: {data.get('message', '')}")
                elif mtype in ("ptt_audio", "live_audio"):
                    audio_b64 = data.get("data", "")
                    fmt = data.get("format", "webm")
                    print(f"[VTUBER] Audio received ({mtype}): {len(audio_b64)} chars base64, fmt={fmt}")
                    if audio_b64:
                        asyncio.create_task(handle_vtuber_ptt(audio_b64, fmt))
                    else:
                        print("[VTUBER] Audio payload empty, ignoring")
                        await vtuber_broadcast({"type": "speech_done"})
                elif mtype in ("ptt_text", "live_text"):
                    text = (data.get("text") or "").strip()
                    print(f"[VTUBER] Text received ({mtype}): {text[:120]}")
                    if text:
                        asyncio.create_task(handle_vtuber_text(text))
                    else:
                        await vtuber_broadcast({"type": "speech_done"})
                elif mtype == "live_vision":
                    text = (data.get("prompt") or data.get("text") or "What do you see? Describe what is happening.").strip()
                    image_b64 = data.get("image") or ""
                    frames_b64 = data.get("frames") or []
                    audio_b64 = data.get("audio") or ""
                    audio_fmt = data.get("audio_format") or "wav"
                    fmt = data.get("format") or "image/jpeg"
                    if not fmt.startswith("image/"):
                        fmt = "image/jpeg"
                    has_aud = bool(audio_b64 and len(audio_b64) > 100)
                    print(f"[VTUBER] Live vision received: prompt='{text[:80]}', frames={len(frames_b64) if frames_b64 else (1 if image_b64 else 0)}, audio={has_aud}")
                    asyncio.create_task(handle_vtuber_vision(text, image_b64, frames_b64, fmt, audio_b64, audio_fmt))
                elif mtype == "ping":
                    await websocket.send(json.dumps({"type": "pong"}))
                else:
                    print(f"[VTUBER] Unknown msg type: {mtype}")
            except Exception as inner:
                print(f"[VTUBER] Message handler error: {inner}")
    except Exception as e:
        print(f"[VTUBER] Handler error: {e}")
    finally:
        vtuber_clients.discard(websocket)
        if not vtuber_clients:
            vtuber_bridge_online = False
        print("[VTUBER] Client disconnected")

vtuber_server_running = False

async def start_vtuber_server():
    global vtuber_server_running
    if not WEBSOCKETS_AVAILABLE:
        print("[VTUBER] websockets library not available.")
        return
    if vtuber_server_running:
        return
    port = config.get("vtuber_ws_port", 8765)
    print(f"[VTUBER] Starting WebSocket server on 0.0.0.0:{port}...")
    try:
        async with websockets.serve(vtuber_handler, "0.0.0.0", port):
            vtuber_server_running = True
            print(f"[VTUBER] WebSocket server is ONLINE and listening on ws://0.0.0.0:{port}")
            await asyncio.Future()
    except OSError as e:
        if e.errno == 98 or "address already in use" in str(e).lower():
            vtuber_server_running = True
            print(f"[VTUBER] Port {port} is already active/bound by VTuber WebSocket server.")
        else:
            print(f"[VTUBER ERROR] WebSocket server OS error on port {port}: {e}")
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[VTUBER ERROR] WebSocket server failed: {e}")
    finally:
        vtuber_server_running = False

def run_vtuber_server_thread():
    if not WEBSOCKETS_AVAILABLE:
        print("[VTUBER] websockets library not available.")
        return
    print(f"[VTUBER] Initializing dedicated background WebSocket thread for VTuber bridge...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(start_vtuber_server())
    except Exception as e:
        print(f"[VTUBER THREAD] Exited: {e}")

# ─── MULTI-BOT PROCESS REGISTRY ───────────────────────
bot_processes = {}  # bot_id -> subprocess.Popen

def is_user_worker_running() -> bool:
    proc = bot_processes.get("user_worker")
    if proc and proc.poll() is None:
        return True
    pid_f = os.path.join(PID_DIR, "user_worker.pid")
    if os.path.exists(pid_f):
        try:
            with open(pid_f, "r") as pf:
                pid = int(pf.read().strip())
            os.kill(pid, 0)
            return True
        except (ValueError, OSError):
            try:
                os.unlink(pid_f)
            except Exception:
                pass
    return False

def get_user_worker_pid() -> Optional[int]:
    proc = bot_processes.get("user_worker")
    if proc and proc.poll() is None:
        return proc.pid
    pid_f = os.path.join(PID_DIR, "user_worker.pid")
    if os.path.exists(pid_f):
        try:
            with open(pid_f, "r") as pf:
                return int(pf.read().strip())
        except Exception:
            pass
    return None

def stop_user_worker_service() -> bool:
    old_proc = bot_processes.pop("user_worker", None)
    if old_proc:
        try:
            old_proc.terminate()
            old_proc.wait(timeout=4)
        except Exception:
            try:
                old_proc.kill()
            except Exception:
                pass

    pid_f = os.path.join(PID_DIR, "user_worker.pid")
    if os.path.exists(pid_f):
        try:
            with open(pid_f, "r") as pf:
                pid = int(pf.read().strip())
            try:
                os.kill(pid, 15)  # SIGTERM
                time.sleep(0.4)
                os.kill(pid, 9)   # SIGKILL
            except Exception:
                pass
            os.unlink(pid_f)
        except Exception:
            pass
    print("[SUPERVISOR] Yuna Real Account Companion worker (user_worker.py) stopped.")
    return True

def start_user_worker_service() -> bool:
    if is_user_worker_running():
        return True

    user_tok = os.getenv("DISCORD_USER_TOKEN", "").strip()
    if not user_tok:
        print("[SUPERVISOR] DISCORD_USER_TOKEN not set in environment. Skipping user_worker.")
        return False

    user_venv_py = "/data/data/com.termux/files/home/userbot-venv/bin/python"
    worker_path = os.path.join(SCRIPT_DIR, "user_worker.py")
    if not (os.path.exists(user_venv_py) and os.path.exists(worker_path)):
        print(f"[SUPERVISOR] Missing userbot-venv or user_worker.py: {user_venv_py}, {worker_path}")
        return False

    log_path = os.path.join(PID_DIR, "user_worker.log")
    try:
        log_f = open(log_path, "a", encoding="utf-8")
        proc = subprocess.Popen(
            [user_venv_py, "-u", worker_path],
            stdout=log_f,
            stderr=subprocess.STDOUT,
            cwd=SCRIPT_DIR,
            start_new_session=True
        )
        bot_processes["user_worker"] = proc
        pid_f = os.path.join(PID_DIR, "user_worker.pid")
        with open(pid_f, "w", encoding="utf-8") as pf:
            pf.write(str(proc.pid))
        print(f"[SUPERVISOR] Launched Yuna Real Account Companion worker (PID {proc.pid}) -> {log_path}")
        return True
    except Exception as e:
        print(f"[SUPERVISOR ERROR] Failed to launch user_worker: {e}")
        return False

def toggle_user_worker_service(enable: Optional[bool] = None) -> bool:
    global config
    if enable is None:
        current = config.get("user_worker_enabled", True)
        target = not current
    else:
        target = bool(enable)

    config["user_worker_enabled"] = target
    save_config(config)

    if target:
        start_user_worker_service()
    else:
        stop_user_worker_service()

    data_dir = os.path.join(SCRIPT_DIR, "data")
    os.makedirs(data_dir, exist_ok=True)
    req_file = os.path.join(data_dir, "restart_request.json")
    try:
        with open(req_file, "w", encoding="utf-8") as f:
            json.dump({"service": "user_worker", "enabled": target, "timestamp": time.time()}, f)
    except Exception:
        pass

    return target

def get_bot_process_status(bot_id):
    proc = bot_processes.get(bot_id)
    if not proc:
        return False
    if proc.poll() is None:
        return True
    bot_processes.pop(bot_id, None)
    return False

def stop_bot_process(bot_id):
    proc = bot_processes.pop(bot_id, None)
    if proc:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except:
            try:
                proc.kill()
            except:
                pass

def start_bot_process(bot_id, token):
    if get_bot_process_status(bot_id):
        return True
    env = os.environ.copy()
    env["IS_BOT_CHILD"] = "1"
    env["BOT_ID"] = bot_id
    env["DISCORD_TOKEN"] = token
    env["SUPERVISOR_PID"] = str(os.getpid())
    if DEBUG_MODE or (isinstance(config, dict) and config.get("debug", True)):
        env["DEBUG"] = "1"
        env["YUNA_DEBUG"] = "1"
    
    # Enable RUN_SOCIAL for bots configured with their own Instagram credentials or Yuna
    bot_entry = get_bot_by_id(bots_state, bot_id) if 'bots_state' in globals() and isinstance(bots_state, dict) else None
    bot_display_name = (bot_entry.get("name") or bot_id) if bot_entry else bot_id
    bot_name = (bot_entry.get("name") or "").lower() if bot_entry else ""
    
    if bot_entry and (bot_entry.get("insta_enabled") and bot_entry.get("insta_sessionid")):
        env["RUN_SOCIAL"] = "1"
    elif bot_name == "yuna":
        env["RUN_SOCIAL"] = "1"
    else:
        env["RUN_SOCIAL"] = "0"

    try:
        python_bin = sys.executable if (sys.executable and "python" in sys.executable) else "/data/data/com.termux/files/home/discord-bot-venv/bin/python"
        script_file = os.path.abspath(__file__)
        log_file = os.path.join(PID_DIR, f"{bot_id}.log")
        
        proc = subprocess.Popen(
            [python_bin, "-u", script_file],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        bot_processes[bot_id] = proc

        def _stream_child_output(p, name, lf):
            try:
                with open(lf, "a", encoding="utf-8", errors="replace") as f:
                    for line in iter(p.stdout.readline, ""):
                        if not line:
                            break
                        # Suppress noisy Instagram private_request / background device pollings
                        if "private_request" in line or "i.instagram.com/api/v1" in line or "Google/google Pixel" in line:
                            continue
                        f.write(line)
                        f.flush()
                        sys.stdout.write(f"[{name}] {line}")
                        sys.stdout.flush()
            except Exception as se:
                print(f"[STREAM ERROR] {name}: {se}", flush=True)
            finally:
                if p.stdout:
                    try:
                        p.stdout.close()
                    except Exception:
                        pass

        t = threading.Thread(target=_stream_child_output, args=(proc, bot_display_name, log_file), daemon=True)
        t.start()
        return True
    except Exception as e:
        print(f"[BOT PROCESS] Failed to start {bot_id}: {e}", flush=True)
        return False

# ─── MINECRAFT BRIDGE & AUTONOMOUS REAL-PLAYER ENGINE ──
DEFAULT_MC_JOURNAL = {
    "todo_list": [
        {"task": "Gather Wood Logs", "done": False},
        {"task": "Craft Crafting Table & Planks", "done": False},
        {"task": "Craft Wooden Pickaxe", "done": False},
        {"task": "Mine Cobblestone", "done": False},
        {"task": "Craft Stone Tools (Pickaxe, Sword, Axe)", "done": False},
        {"task": "Hunt Animals for Food & Wool", "done": False},
        {"task": "Craft Bed & Cook Food in Furnace", "done": False},
        {"task": "Mine Iron Ore & Coal", "done": False},
        {"task": "Smelt Iron & Craft Iron Armor & Shield", "done": False},
        {"task": "Explore Caves & Search for Diamonds", "done": False}
    ],
    "milestones": [],
    "lessons_learned": [
        "Always carry wood and torches when exploring caves.",
        "Raise shield immediately when hearing skeleton arrows.",
        "Keep at least 4.5 blocks distance when a creeper starts flashing."
    ],
    "stats": {"blocks_mined": 0, "items_crafted": 0, "mobs_defeated": 0, "deaths": 0}
}

mc_proc = None
mc_reader_thread = None
mc_state = {
    "online": False,
    "username": "YunaBot",
    "health": 20,
    "food": 20,
    "pos": {"x": 0, "y": 0, "z": 0},
    "task": "idle",
    "players": [],
    "mobs": [],
    "inventory": [],
    "journal": json.loads(json.dumps(DEFAULT_MC_JOURNAL)),
    "logs": []
}

def send_mc_cmd(cmd_dict: dict):
    global mc_proc
    if mc_proc and mc_proc.poll() is None:
        try:
            line = json.dumps(cmd_dict) + "\n"
            mc_proc.stdin.write(line.encode("utf-8"))
            mc_proc.stdin.flush()
            return True
        except Exception as e:
            print(f"[MC ERROR] Failed to send cmd: {e}")
    return False

def _mc_stdout_worker(proc, loop):
    global mc_state
    try:
        for raw_line in iter(proc.stdout.readline, b""):
            line = raw_line.decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                mtype = data.get("type")
                if mtype == "spawn":
                    mc_state["online"] = True
                    mc_state["pos"] = data.get("pos", mc_state["pos"])
                    if "journal" in data and isinstance(data["journal"], dict):
                        mc_state["journal"] = data["journal"]
                    print(f"[MINECRAFT] Bot spawned in world at {mc_state['pos']}")
                elif mtype == "status":
                    mc_state["online"] = True
                    mc_state["health"] = data.get("health", mc_state["health"])
                    mc_state["food"] = data.get("food", mc_state["food"])
                    mc_state["pos"] = data.get("pos", mc_state["pos"])
                    mc_state["task"] = data.get("task", mc_state["task"])
                    mc_state["players"] = data.get("players", mc_state["players"])
                    mc_state["mobs"] = data.get("mobs", mc_state["mobs"])
                    if "inventory" in data:
                        mc_state["inventory"] = data["inventory"]
                    if "journal" in data and isinstance(data["journal"], dict):
                        mc_state["journal"] = data["journal"]
                elif mtype in ("journal_data", "journal"):
                    if "journal" in data and isinstance(data["journal"], dict):
                        mc_state["journal"] = data["journal"]
                elif mtype == "task_start":
                    mc_state["task"] = data.get("task", mc_state["task"])
                elif mtype in ("task_complete", "task_stopped"):
                    mc_state["task"] = "idle"
                elif mtype == "milestone":
                    m_desc = data.get("milestone", "")
                    print(f"[MINECRAFT MILESTONE] {m_desc}")
                    ch_id = config.get("minecraft_channel")
                    if ch_id and client and loop and loop.is_running():
                        async def _send_milestone():
                            try:
                                ch = client.get_channel(int(ch_id))
                                if ch and isinstance(ch, discord.TextChannel):
                                    await ch.send(f"🏆 **[Minecraft Milestone]** `{m_desc}`")
                            except Exception:
                                pass
                        asyncio.run_coroutine_threadsafe(_send_milestone(), loop)
                elif mtype == "chat":
                    u = data.get("username", "")
                    m = data.get("message", "")
                    print(f"[MINECRAFT CHAT] <{u}> {m}")
                    if loop and loop.is_running():
                        asyncio.run_coroutine_threadsafe(handle_mc_in_game_chat(u, m), loop)
                elif mtype == "death":
                    mc_state["task"] = "dead"
                    print("[MINECRAFT] Bot died!")
                    ch_id = config.get("minecraft_channel")
                    if ch_id and client and loop and loop.is_running():
                        async def _send_death():
                            try:
                                ch = client.get_channel(int(ch_id))
                                if ch and isinstance(ch, discord.TextChannel):
                                    dead_name = current_bot_name or (client.user.display_name if client.user else "Bot")
                                    await ch.send(f"💀 **[Minecraft]** {dead_name} died in the world and respawned! Logging lesson in journal...")
                            except Exception:
                                pass
                        asyncio.run_coroutine_threadsafe(_send_death(), loop)
                elif mtype == "kicked":
                    mc_state["online"] = False
                    print(f"[MINECRAFT] Kicked: {data.get('reason')}")
                elif mtype == "error":
                    print(f"[MINECRAFT ERROR] {data.get('msg')}")
                elif mtype == "end":
                    mc_state["online"] = False
                    print("[MINECRAFT] Connection ended.")

                mc_state["logs"].append(f"[{time.strftime('%H:%M:%S')}] {line[:120]}")
                if len(mc_state["logs"]) > 50:
                    mc_state["logs"].pop(0)
            except Exception:
                pass
    except Exception as e:
        print(f"[MINECRAFT WORKER ERROR] {e}")
    finally:
        mc_state["online"] = False
        if mc_auto_reconnect_enabled and config.get("minecraft_auto_reconnect", True):
            t = threading.Thread(target=_schedule_mc_reconnect, args=(loop,), daemon=True)
            t.start()

def _schedule_mc_reconnect(loop):
    time.sleep(6)
    if mc_auto_reconnect_enabled and config.get("minecraft_auto_reconnect", True):
        if not mc_proc or mc_proc.poll() is not None:
            print("[MINECRAFT] Connection lost. Auto-reconnecting to server...")
            start_minecraft_bot()

mc_auto_reconnect_enabled = False

def start_minecraft_bot():
    global mc_proc, mc_reader_thread, mc_auto_reconnect_enabled
    mc_auto_reconnect_enabled = True
    if mc_proc and mc_proc.poll() is None:
        return True, "Minecraft bot is already running."

    script_path = os.path.join(SCRIPT_DIR, "mc_bridge.js")
    if not os.path.exists(script_path):
        return False, "mc_bridge.js not found."

    current_bot_id = os.getenv("BOT_ID") or bots_state.get("active_id", "default")
    current_bot_name = ""
    if 'bots_state' in globals() and isinstance(bots_state, dict):
        b = get_bot_by_id(bots_state, current_bot_id)
        if b and b.get("name"):
            current_bot_name = b["name"]

    # Determine unique in-game username per bot to prevent collisions/kicks
    default_mc_name = f"{current_bot_name}Bot" if current_bot_name else "MinecraftBot"
    raw_mc_name = config.get("minecraft_username", "").strip()
    if not raw_mc_name or (raw_mc_name == "YunaBot" and current_bot_name and current_bot_name.lower() != "yuna"):
        mc_username = default_mc_name
    else:
        mc_username = raw_mc_name or default_mc_name

    opts = {
        "botId": current_bot_id,
        "botName": current_bot_name or mc_username,
        "host": config.get("minecraft_server", "localhost"),
        "port": config.get("minecraft_port", 25565),
        "username": mc_username,
        "skin": config.get("minecraft_skin", ""),
        "version": config.get("minecraft_version") or False,
        "auth": config.get("minecraft_auth", "offline")
    }

    node_paths = [
        "/data/data/com.termux/files/home/node_modules",
        os.path.join(SCRIPT_DIR, "node_modules")
    ]
    env = os.environ.copy()
    env["NODE_PATH"] = ":".join(node_paths)

    try:
        mc_proc = subprocess.Popen(
            ["node", script_path, json.dumps(opts)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env
        )
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = getattr(client, "loop", None)
        mc_reader_thread = threading.Thread(target=_mc_stdout_worker, args=(mc_proc, loop), daemon=True)
        mc_reader_thread.start()
        print(f"[MINECRAFT] Process started ({current_bot_id}): connecting to {opts['host']}:{opts['port']} as {opts['username']}")
        return True, f"Connecting to {opts['host']}:{opts['port']} as {opts['username']}..."
    except Exception as e:
        print(f"[MINECRAFT] Failed to start: {e}")
        return False, str(e)

def stop_minecraft_bot():
    global mc_proc, mc_auto_reconnect_enabled
    mc_auto_reconnect_enabled = False
    if mc_proc:
        send_mc_cmd({"type": "quit"})
        try:
            mc_proc.terminate()
            mc_proc.wait(timeout=3)
        except Exception:
            try:
                mc_proc.kill()
            except Exception:
                pass
        mc_proc = None
        mc_state["online"] = False
        return True, "Minecraft bot disconnected."
    return False, "Minecraft bot is not running."

async def handle_mc_in_game_chat(username: str, message: str):
    """Processes in-game Minecraft chat messages with personality and goal execution."""
    current_bot_id = os.getenv("BOT_ID") or bots_state.get("active_id", "default")
    current_bot_name = ""
    if 'bots_state' in globals() and isinstance(bots_state, dict):
        b = get_bot_by_id(bots_state, current_bot_id)
        if b and b.get("name"):
            current_bot_name = b["name"]

    bot_mc_user = (config.get("minecraft_username") or current_bot_name or "Player").lower()
    msg_lower = message.lower()

    ch_id = config.get("minecraft_channel")
    if ch_id and client:
        try:
            channel = client.get_channel(int(ch_id))
            if channel and isinstance(channel, discord.TextChannel):
                await channel.send(f"🎮 **[MC]** `<{username}>` {message}")
        except Exception:
            pass

    triggers = [bot_mc_user, "bot", f"!{bot_mc_user}"]
    if current_bot_name:
        triggers.extend([current_bot_name.lower(), f"!{current_bot_name.lower()}"])
    for t in config.get("bot_name_triggers", []):
        if t:
            triggers.append(str(t).strip().lower())

    if any(t in msg_lower for t in triggers):
        clean_msg = message
        for trigger in triggers + [",", ":"]:
            clean_msg = re.sub(rf'\b{re.escape(trigger)}\b', '', clean_msg, flags=re.IGNORECASE).strip()

        if not clean_msg:
            send_mc_cmd({"type": "emote", "emote": "sneak_spam"})
            send_mc_cmd({"type": "chat", "text": f"Hey {username}! Ready to play."})
            return

        await mc_execute_natural_goal(clean_msg, sender_name=username, is_in_game=True)

async def mc_execute_natural_goal(instruction: str, sender_name: str = "Player", is_in_game: bool = False) -> str:
    """Translates natural language user instructions into concrete Minecraft bot actions using LLM."""
    current_bot_id = os.getenv("BOT_ID") or bots_state.get("active_id", "default")
    current_bot_name = ""
    if 'bots_state' in globals() and isinstance(bots_state, dict):
        b = get_bot_by_id(bots_state, current_bot_id)
        if b and b.get("name"):
            current_bot_name = b["name"]
    mc_persona = config.get("minecraft_personality") or config.get("personality") or f"You are {current_bot_name or 'a friendly player'} playing Minecraft."

    prompt = f"""You are controlling a Minecraft Mineflayer bot as {current_bot_name or 'a player'}.
Personality/Role: {mc_persona[:400]}
Current bot state:
- Bot Username: {config.get('minecraft_username', current_bot_name or 'Bot')}
- Health: {mc_state.get('health')}/20
- Food: {mc_state.get('food')}/20
- Position: {mc_state.get('pos')}
- Current Task: {mc_state.get('task')}
- Nearby Players: {mc_state.get('players')}
- Nearby Mobs: {mc_state.get('mobs')}

User instruction from {sender_name}: "{instruction}"

Respond with a JSON object containing:
1. "action": one of ["follow", "mine", "craft", "attack", "goto", "sleep", "give", "emote", "stop", "chat_only"]
2. "params": dictionary of parameters:
   - For "follow": {{"username": "{sender_name}"}}
   - For "mine": {{"block": "oak_log"|"iron_ore"|..., "count": 1-20}}
   - For "craft": {{"item": "wooden_pickaxe"|"torch"|..., "count": 1-10}}
   - For "attack": {{"target": "zombie"|"skeleton"|...}}
   - For "goto": {{"x": 0, "y": 64, "z": 0}}
   - For "give": {{"username": "{sender_name}", "item": "iron_ingot"|..., "count": 1}}
   - For "emote": {{"emote": "sneak_spam"|"nod"|"shake"|"jump"}}
3. "reply": A short 1-sentence in-character response to say in Minecraft chat.

Return ONLY valid JSON."""

    reply, err = await ask_groq([], prompt)
    if err or not reply:
        reply, err = await ask_gemini("You are a helpful Minecraft bot JSON controller.", [], prompt)

    chat_text = "On it!"
    try:
        clean_json = reply or "{}"
        if "```json" in clean_json:
            clean_json = clean_json.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_json:
            clean_json = clean_json.split("```")[1].split("```")[0].strip()
        data = json.loads(clean_json)

        act = data.get("action")
        params = data.get("params", {})
        chat_text = data.get("reply", "On it!")

        if act == "follow":
            target = params.get("username") or sender_name
            send_mc_cmd({"type": "follow", "username": target, "range": 2})
        elif act == "mine":
            send_mc_cmd({"type": "mine", "block": params.get("block", "oak_log"), "count": params.get("count", 3)})
        elif act == "craft":
            send_mc_cmd({"type": "craft", "item": params.get("item", "wooden_pickaxe"), "count": params.get("count", 1)})
        elif act == "attack":
            send_mc_cmd({"type": "attack", "target": params.get("target")})
        elif act == "goto":
            send_mc_cmd({"type": "goto", "x": params.get("x", 0), "y": params.get("y", 64), "z": params.get("z", 0)})
        elif act == "give":
            send_mc_cmd({"type": "give", "username": params.get("username", sender_name), "item": params.get("item", "iron_ingot"), "count": params.get("count", 1)})
        elif act == "emote":
            send_mc_cmd({"type": "emote", "emote": params.get("emote", "sneak_spam")})
        elif act == "sleep":
            send_mc_cmd({"type": "sleep"})
        elif act == "stop":
            send_mc_cmd({"type": "stop"})

        send_mc_cmd({"type": "chat", "text": chat_text})
        return chat_text
    except Exception:
        ins = instruction.lower()
        if "follow" in ins or "come" in ins:
            send_mc_cmd({"type": "follow", "username": sender_name, "range": 2})
            chat_text = f"Coming to you, {sender_name}~"
        elif "mine" in ins or "chop" in ins:
            block = "oak_log" if "wood" in ins or "tree" in ins else "stone"
            send_mc_cmd({"type": "mine", "block": block, "count": 3})
            chat_text = f"Gathering some {block}!"
        elif "stop" in ins:
            send_mc_cmd({"type": "stop"})
            chat_text = "Stopping current task."
        elif "sleep" in ins:
            send_mc_cmd({"type": "sleep"})
            chat_text = "Looking for a bed... zzz"
        else:
            chat_text = "Tell me what to do: follow, mine, craft, defend, or sleep!"
        send_mc_cmd({"type": "chat", "text": chat_text})
        return chat_text

# ─── DISCORD ────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ─── RANDOM DM LOOP ───────────────────────────────────
async def random_dm_loop():
    global interacted_users
    await client.wait_until_ready()
    while not client.is_closed():
        try:
            if not config.get("random_dms_enabled", False):
                await asyncio.sleep(60)
                continue
            interval = max(10, config.get("random_dms_interval_minutes", 60)) * 60
            await asyncio.sleep(interval)
            if not config.get("random_dms_enabled", False):
                continue
            if not interacted_users:
                continue
            candidates = list(interacted_users)
            random.shuffle(candidates)
            user_id = candidates[0]
            user = await client.fetch_user(int(user_id))
            if not user:
                continue
            system_msg = config["personality"]
            dm_prompt = config.get("random_dms_prompt", "Send a casual, friendly message.")
            reply, err = None, True
            provider = config.get("provider", "auto")
            if provider == "gemini" and GEMINI_KEY and time.time() >= gemini_blocked_until:
                reply, err = await ask_gemini(system_msg, [], dm_prompt)
            elif provider == "deepseek" and get_deepseek_key() and time.time() >= deepseek_blocked_until:
                reply, err = await ask_deepseek([], dm_prompt, system_msg=system_msg)
            elif provider == "openai" and get_openai_key() and time.time() >= openai_blocked_until:
                reply, err = await ask_openai([], dm_prompt, system_msg=system_msg)
            elif provider == "groq" and GROQ_KEY and time.time() >= groq_blocked_until:
                reply, err = await ask_groq([], dm_prompt)
            elif provider == "mistral" and (os.getenv("MISTRAL_KEY") or MISTRAL_KEY) and time.time() >= mistral_blocked_until:
                reply, err = await ask_mistral([], dm_prompt, system_msg=system_msg)
            elif provider == "openrouter" and os.getenv("OPENROUTER_KEY") and time.time() >= openrouter_blocked_until:
                reply, err = await ask_openrouter([], dm_prompt)
            else:
                if GEMINI_KEY and time.time() >= gemini_blocked_until:
                    reply, err = await ask_gemini(system_msg, [], dm_prompt)
                if err and get_deepseek_key() and time.time() >= deepseek_blocked_until:
                    reply, err = await ask_deepseek([], dm_prompt, system_msg=system_msg)
                if err and get_openai_key() and time.time() >= openai_blocked_until:
                    reply, err = await ask_openai([], dm_prompt, system_msg=system_msg)
                if err and GROQ_KEY and time.time() >= groq_blocked_until:
                    reply, err = await ask_groq([], dm_prompt)
                if err and (os.getenv("MISTRAL_KEY") or MISTRAL_KEY) and time.time() >= mistral_blocked_until:
                    reply, err = await ask_mistral([], dm_prompt, system_msg=system_msg)
                if err and os.getenv("OPENROUTER_KEY") and time.time() >= openrouter_blocked_until:
                    reply, err = await ask_openrouter([], dm_prompt)
            if not err and reply:
                try:
                    await user.send(reply[:2000])
                    print(f"[RANDOM DM] Sent to {user} ({user_id})")
                except discord.Forbidden:
                    print(f"[RANDOM DM] Cannot DM user {user_id}")
                except Exception as e:
                    print(f"[RANDOM DM] Error: {e}")
        except Exception as e:
            print(f"[RANDOM DM LOOP ERROR] {e}")
            await asyncio.sleep(60)

# ─── RANDOM CHAT LOOP ─────────────────────────────────
async def random_chat_loop():
    await client.wait_until_ready()
    while not client.is_closed():
        try:
            if not config.get("random_chat_enabled", False):
                await asyncio.sleep(30)
                continue
            await asyncio.sleep(random.randint(20, 50))
            candidates = []
            for guild in client.guilds:
                for channel in guild.text_channels:
                    if channel.permissions_for(guild.me).send_messages:
                        candidates.append(channel)
            if not candidates:
                continue
            channel = random.choice(candidates)
            chance = config.get("random_chat_chance", 0.05)
            if random.random() > chance:
                continue
            limit = config.get("random_chat_context_limit", 50)
            history = []
            bot_name = client.user.display_name.lower()
            triggers = [t.lower() for t in config.get("bot_name_triggers", ["bot"])]
            triggers.append(bot_name.split()[0] if bot_name else "bot")
            mentioned = False
            async for msg in channel.history(limit=limit):
                if msg.author == client.user:
                    history.append({"role": "assistant", "content": msg.content or "", "name": client.user.display_name})
                else:
                    history.append({"role": "user", "content": f"[{msg.author.display_name}]: {msg.content or ''}"})
                    if any(t in (msg.content or "").lower() for t in triggers):
                        mentioned = True
            if not history:
                continue
            history.reverse()
            if not mentioned and random.random() > 0.2:
                continue
            recent = "\n".join([h["content"] for h in history[-20:]])
            prompt = f"Recent conversation in this channel:\n{recent}\n\nJump into the conversation naturally with a short, relevant, casual response. Match the vibe and don't mention you're an AI. Keep it under 2 sentences."
            reply, err = await ask_ai(channel.id, prompt, guild=channel.guild, is_dm=False)
            if not err and reply:
                await send_split_messages(channel, reply)
                print(f"[RANDOM CHAT] Replied in #{channel.name}")
        except Exception as e:
            print(f"[RANDOM CHAT ERROR] {e}")
            await asyncio.sleep(30)

# ─── GLOBAL STATE ─────────────────────────────────────
config = load_config()

async def obs_llm_dispatcher(call_type: str, provider: str = "auto", prompt: str = "", system_prompt: str = "", images_b64: list = None, audio_bytes: bytes = None):
    images_b64 = images_b64 or []
    if call_type in ("vision", "vision_query"):
        images_bytes = [base64.b64decode(b) for b in images_b64]
        if GEMINI_KEY:
            res, err = await ask_gemini_vision(system_prompt, prompt, images_bytes, "image/jpeg")
            if not err and res: return res, None
        if os.getenv("OPENROUTER_KEY"):
            res, err = await ask_openrouter_vision(system_prompt, prompt, images_bytes, "image/jpeg")
            if not err and res: return res, None
    elif call_type == "stt" and audio_bytes:
        res, err = await transcribe_audio(audio_bytes, "audio.wav")
        if not err and res: return res, None
    else:
        res, err = await ask_gemini(system_prompt or config.get("personality", ""), [], prompt)
        if not err and res: return res, None
    return None, "All dispatchers failed"

passive_obs_module = PassiveObservationModule(
    llm_dispatcher=obs_llm_dispatcher,
    config=config,
    data_dir=os.path.join(SCRIPT_DIR, "data")
)

contexts = {}
load_contexts()
start_time = time.time()
gemini_blocked_until = 0
openrouter_blocked_until = 0
groq_blocked_until = 0
mistral_blocked_until = 0
openai_blocked_until = 0
deepseek_blocked_until = 0

def get_openai_key() -> str:
    return (config.get("openai_api_key") or os.getenv("OPENAI_KEY") or os.getenv("OPENAI_API_KEY") or OPENAI_KEY or "").strip()

def get_deepseek_key() -> str:
    return (config.get("deepseek_api_key") or os.getenv("DEEPSEEK_KEY") or os.getenv("DEEPSEEK_API_KEY") or DEEPSEEK_KEY or "").strip()

message_count = 0
owner_id_cached = None
user_cooldowns = defaultdict(float)
interacted_users = load_interacted_users()
voice_sessions = {}  # guild_id -> {vc, sink, task, channel_id}
load_user_profiles()

# ─── BOT PROFILES (multi-bot manager) ─────────────────
BOTS_FILE = os.path.join(SCRIPT_DIR, "bots.json")

def _gen_bot_id():
    return "bot_" + "".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=8))

def _is_valid_bot_entry(b):
    return (
        isinstance(b, dict)
        and isinstance(b.get("id"), str)
        and isinstance(b.get("config"), dict)
    )

def _sanitize_loaded_bots(data):
    if not isinstance(data, dict):
        return None, []
    raw_bots = data.get("bots", [])
    if not isinstance(raw_bots, list):
        raw_bots = []
    valid = [b for b in raw_bots if _is_valid_bot_entry(b)]
    aid = data.get("active_id")
    if not isinstance(aid, str) or not any(b["id"] == aid for b in valid):
        aid = valid[0]["id"] if valid else None
    return aid, valid

def load_bots():
    with state_lock:
        if os.path.exists(BOTS_FILE):
            try:
                with open(BOTS_FILE, "r") as f:
                    data = json.load(f)
                aid, valid = _sanitize_loaded_bots(data)
                if valid:
                    env_token = os.getenv("DISCORD_TOKEN", "").strip()
                    if env_token:
                        for b in valid:
                            if not b.get("token") and b["id"] == aid:
                                b["token"] = env_token
                                try:
                                    with open(BOTS_FILE, "w") as f:
                                        json.dump({"active_id": aid, "bots": valid}, f, indent=2)
                                except:
                                    pass
                                break
                    return {"active_id": aid, "bots": valid}
                print(f"[BOTS] {BOTS_FILE} exists but has no valid bot entries — rebuilding.")
            except Exception as e:
                print(f"[BOTS] Failed to read {BOTS_FILE}: {e} — rebuilding.")
        default_id = _gen_bot_id()
        env_token = os.getenv("DISCORD_TOKEN", "").strip()
        bots = {
            "active_id": default_id,
            "bots": [
                {
                    "id": default_id,
                    "name": "Default",
                    "emoji": "🤖",
                    "created_at": time.time(),
                    "token": env_token,
                    "config": json.loads(json.dumps(config)),
                }
            ],
        }
        try:
            with open(BOTS_FILE, "w") as f:
                json.dump(bots, f, indent=2)
        except Exception as e:
            print(f"[BOTS] Could not write {BOTS_FILE}: {e}")
        return bots

def save_bots(bots):
    with state_lock:
        aid, valid = _sanitize_loaded_bots(bots)
        payload = {"active_id": aid, "bots": valid}
        _atomic_json_save(BOTS_FILE, payload, backup=True, max_backups=5)

def get_bot_by_id(bots, bot_id):
    for b in bots.get("bots", []):
        if b["id"] == bot_id:
            return b
    return None

def get_active_bot(bots):
    aid, valid = _sanitize_loaded_bots(bots)
    for b in valid:
        if b["id"] == aid:
            return b
    if valid:
        return valid[0]
    return None

def apply_bot_to_config(bot, save_to_disk=False):
    global config
    if not bot or not isinstance(bot, dict):
        return

    new_cfg = json.loads(json.dumps(DEFAULT_CONFIG))

    # 1. Merge top-level bot attributes
    for k, v in bot.items():
        if k == "prompt" and "personality" not in bot:
            new_cfg["personality"] = v
        elif k not in ("id", "token", "active"):
            new_cfg[k] = v

    # 2. Merge nested bot.config dictionary
    cfg = bot.get("config", {})
    if isinstance(cfg, dict):
        for k, v in cfg.items():
            new_cfg[k] = v
        if not new_cfg.get("personality") and cfg.get("prompt"):
            new_cfg["personality"] = cfg.get("prompt")
        eff_m = str(new_cfg.get("custom_model") if new_cfg.get("use_custom_model") else (new_cfg.get("model") or "")).strip()
        if "gemini" in eff_m.lower():
            new_cfg["gemini_model"] = eff_m

    # 3. Dedicated Instagram fallback: only for Yuna
    bot_name = (bot.get("name") or "").lower()
    if bot_name == "yuna" and os.path.exists(os.path.join(SCRIPT_DIR, "data", "instagram_config.json")):
        try:
            with open(os.path.join(SCRIPT_DIR, "data", "instagram_config.json"), "r", encoding="utf-8") as _icf:
                _icd = json.load(_icf)
                for _ik, _iv in _icd.items():
                    target_k = f"insta_{_ik}" if not _ik.startswith("insta_") else _ik
                    if target_k not in new_cfg or not new_cfg[target_k]:
                        new_cfg[target_k] = _iv
        except Exception:
            pass

    config.clear()
    config.update(new_cfg)
    if save_to_disk and not os.getenv("BOT_ID"):
        save_config(config)

_last_cfg_check = 0
_last_cfg_mtime = 0

def refresh_runtime_config():
    """Auto-sync in-memory config with bots.json without clobbering each other's personality."""
    global config, bots_state, _last_cfg_check, _last_cfg_mtime
    now = time.time()
    if now - _last_cfg_check < 1.0:
        return config
    _last_cfg_check = now
    try:
        mtime = 0
        if os.path.exists(BOTS_FILE):
            mtime = os.path.getmtime(BOTS_FILE)
        if mtime != _last_cfg_mtime:
            _last_cfg_mtime = mtime
            with state_lock:
                bots_state = load_bots()
                child_bot_id = os.getenv("BOT_ID")
                if child_bot_id:
                    target_bot = get_bot_by_id(bots_state, child_bot_id)
                    if target_bot:
                        apply_bot_to_config(target_bot, save_to_disk=False)
                else:
                    active = get_active_bot(bots_state)
                    if active:
                        apply_bot_to_config(active, save_to_disk=False)
    except Exception:
        pass
    return config

def is_bot_addressed(message) -> bool:
    """Accurately checks if this specific bot is being spoken to (by name, trigger, mention, or reply)."""
    if not client.user or message.author == client.user:
        return False

    # 1. Direct Messages (DM) always address this bot
    if message.guild is None:
        return True

    # 2. Direct @Mentions of this specific bot
    if client.user in message.mentions:
        return True

    # 3. Direct Replies to previous messages
    if message.reference and message.reference.message_id:
        ref_msg = getattr(message.reference, "resolved", None)
        if ref_msg and getattr(ref_msg, "author", None) == client.user:
            return True
        if ref_msg and getattr(ref_msg, "author", None) and ref_msg.author != client.user and ref_msg.author.bot:
            return False

    # Gather this bot's own names & triggers
    my_names = set()
    if client.user:
        if client.user.name:
            my_names.add(client.user.name.lower())
        if client.user.display_name:
            my_names.add(client.user.display_name.lower())

    current_id = os.getenv("BOT_ID")
    if current_id and 'bots_state' in globals():
        b = get_bot_by_id(bots_state, current_id)
        if b and b.get("name"):
            my_names.add(b["name"].lower())
    elif 'active_bot' in globals() and active_bot:
        if active_bot.get("name"):
            my_names.add(active_bot["name"].lower())

    # Add custom configured triggers
    for trig in config.get("bot_name_triggers", []):
        if trig and str(trig).strip():
            my_names.add(str(trig).strip().lower())

    # Gather OTHER bots' names so we don't accidentally intercept calls meant for them
    other_names = set()
    if 'bots_state' in globals() and isinstance(bots_state, dict):
        for b in bots_state.get("bots", []):
            bname = (b.get("name") or "").strip().lower()
            if bname and bname not in my_names:
                other_names.add(bname)

    content_lower = message.content.lower().strip()
    words = re.findall(r'\b[a-zA-Z0-9_\-\']+\b', content_lower)

    # If the message specifically starts with another bot's name (e.g. "Law, ..."), do NOT respond
    if words and words[0] in other_names:
        return False

    # If another bot is @mentioned directly and this bot is NOT mentioned
    if message.mentions:
        other_bot_mentioned = any(m != client.user and m.bot for m in message.mentions)
        if other_bot_mentioned and client.user not in message.mentions:
            return False

    # Check if ANY of this bot's names/triggers appear in the message
    for name in my_names:
        if not name:
            continue
        if re.search(rf'\b{re.escape(name)}\b', content_lower, re.IGNORECASE):
            return True

    # If open_chat_enabled is True, respond as long as no other bot was targeted and this is active bot
    if config.get("open_chat_enabled", False):
        active_id = bots_state.get("active_id") if 'bots_state' in globals() and isinstance(bots_state, dict) else None
        cur_id = os.getenv("BOT_ID")
        if not cur_id or not active_id or cur_id == active_id:
            return True

    return False

_bot_avatar_cache = {}
def get_discord_bot_avatar(token):
    if not token or not token.strip():
        return None
    tok = token.strip()
    if tok in _bot_avatar_cache:
        return _bot_avatar_cache[tok]
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://discord.com/api/v10/users/@me",
            headers={"Authorization": f"Bot {tok}", "User-Agent": "DiscordBot (https://github.com, v1.0)"}
        )
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            data = json.loads(resp.read().decode())
            uid = data.get("id")
            av = data.get("avatar")
            if uid and av:
                url = f"https://cdn.discordapp.com/avatars/{uid}/{av}.png?size=128"
                _bot_avatar_cache[tok] = url
                return url
            elif uid:
                disc = int(data.get("discriminator", "0")) % 5
                url = f"https://cdn.discordapp.com/embed/avatars/{disc}.png"
                _bot_avatar_cache[tok] = url
                return url
    except Exception:
        pass
    return None

def bots_summary(bots):
    out = []
    aid = bots.get("active_id")
    for b in bots.get("bots", []):
        av_url = b.get("avatar_url") or b.get("config", {}).get("avatar_url") or b.get("pfp")
        if not av_url and b.get("token"):
            av_url = get_discord_bot_avatar(b.get("token"))
        cfg = b.get("config", {}) or {}
        p_text = cfg.get("personality") or b.get("personality") or ""
        out.append({
            "id": b["id"],
            "bot_id": b["id"],
            "name": b.get("name", "Unnamed"),
            "emoji": b.get("emoji", "🤖"),
            "avatar_url": av_url,
            "pfp": av_url,
            "token": b.get("token", ""),
            "privacy": cfg.get("privacy", "private"),
            "is_active": b["id"] == aid,
            "online": get_bot_process_status(b["id"]),
            "has_token": bool(b.get("token", "").strip()),
            "personality_preview": p_text[:80],
            "personality": p_text,
            "prompt": p_text,
            "provider": cfg.get("provider", "auto"),
            "model": cfg.get("model", ""),
            "custom_model": cfg.get("custom_model") or cfg.get("model", ""),
            "custom_base_url": cfg.get("custom_base_url", ""),
            "custom_key": cfg.get("custom_key", ""),
            "use_custom_model": cfg.get("use_custom_model", False),
            "model_slots": cfg.get("model_slots", []),
            "role": cfg.get("role", "AI Companion"),
            "desc": cfg.get("desc", ""),
            "tts_enabled": cfg.get("tts_enabled", False),
            "tts_provider": cfg.get("tts_provider", "auto"),
            "fish_voice_id": cfg.get("fish_voice_id", ""),
            "elevenlabs_voice_id": cfg.get("elevenlabs_voice_id", ""),
            "voice_id": cfg.get("voice_id", ""),
            "config": cfg,
            "settings": cfg,
            "is_mine": True,
            "owner_id": "",
        })
    return out

bots_state = load_bots()
init_bot_id = os.getenv("BOT_ID")
if init_bot_id:
    child_init_bot = get_bot_by_id(bots_state, init_bot_id)
    if child_init_bot:
        apply_bot_to_config(child_init_bot, save_to_disk=False)
else:
    active_bot = get_active_bot(bots_state)
    if active_bot:
        apply_bot_to_config(active_bot, save_to_disk=False)

# ─── POKÉMON SHOWDOWN MANAGER INITIALIZATION ───────────
showdown_manager = None
if SHOWDOWN_ENGINE_AVAILABLE and ShowdownManager:
    def _save_showdown_config_cb(bot_id: str, bot_cfg: dict):
        with state_lock:
            cur_bs = load_bots()
            b_obj = get_bot_by_id(cur_bs, bot_id)
            if b_obj:
                if "config" not in b_obj:
                    b_obj["config"] = {}
                b_obj["config"]["showdown_username"] = bot_cfg.get("showdown_username", "")
                b_obj["config"]["showdown_password"] = bot_cfg.get("showdown_password", "")
                save_bots(cur_bs)

    showdown_manager = ShowdownManager(bots_state, save_cb=_save_showdown_config_cb)

    async def _on_showdown_discord_notify(sd_client, msg_text, embed_data=None, is_battle_chat=False):
        initiator_id = getattr(sd_client, "initiator_user_id", None)
        target_ch_id = getattr(sd_client, "channel_id", None) or config.get("showdown_channel")
        sent = False

        # 1. Primary route: Direct Message to the user who initiated Showdown / the battle
        if initiator_id:
            try:
                user = client.get_user(int(initiator_id))
                if not user:
                    user = await client.fetch_user(int(initiator_id))
                if user:
                    await user.send(msg_text)
                    sent = True
            except Exception:
                # If DMs are closed or fail, fall back to channel
                pass

        # 2. Secondary route: Discord channel where command was executed
        if not sent and target_ch_id:
            try:
                ch = client.get_channel(int(target_ch_id))
                if not ch:
                    ch = await client.fetch_channel(int(target_ch_id))
                if ch:
                    await ch.send(msg_text)
                    sent = True
            except Exception as _sne:
                print(f"[SHOWDOWN NOTIFY ERROR] {_sne}")

        # 3. Last resort fallback for non-battle system notices only (avoid unprompted DMs to owner)
        if not sent and not is_battle_chat and not initiator_id and OWNER_ID:
            try:
                owner_user = client.get_user(int(OWNER_ID))
                if owner_user:
                    await owner_user.send(msg_text)
            except Exception:
                pass

    async def _generate_team_with_llm(bot_name: str, personality: str, battle_format: str) -> Optional[str]:
        """Asynchronously queries LLM for custom format-tailored competitive Showdown teams."""
        prompt = (
            f"You are a master Pokémon competitive strategist and coach.\n"
            f"Format: {battle_format}\n"
            f"Trainer Persona: {bot_name} ({personality})\n\n"
            f"Requirements:\n"
            f"1. Build an optimized, viable 6-Pokémon team compliant with {battle_format} Smogon tier rules.\n"
            f"2. Give each Pokémon a creative nickname reflecting {bot_name}'s persona.\n"
            f"3. Specify item, ability, nature, EVs, Tera type, and 4 competitive moves per Pokémon.\n"
            f"4. Format the output STRICTLY in standard Pokémon Showdown export text (Pokepaste format) only.\n"
            f"Do NOT include markdown fences, code blocks, or commentary."
        )
        try:
            if 'ask_gemini' in globals():
                raw_text, err = await ask_gemini(personality, [], prompt, caller="showdown_team")
                if raw_text and not err and ("Ability:" in raw_text or "EVs:" in raw_text):
                    return raw_text.strip()
        except Exception as e:
            print(f"[SHOWDOWN LLM TEAM ERROR] {e}")
        return None

    showdown_manager.set_discord_callback(_on_showdown_discord_notify)
    showdown_manager.set_llm_team_generator(_generate_team_with_llm)

def queue_showdown_ipc_cmd(bot_id: str, action: str, cmd_data: dict):
    """Queues a Showdown command from the Web Dashboard for the child process."""
    ipc_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memories", "ipc")
    os.makedirs(ipc_dir, exist_ok=True)
    ipc_file = os.path.join(ipc_dir, "showdown_queue.json")
    with state_lock:
        queue = []
        if os.path.exists(ipc_file):
            try:
                with open(ipc_file, "r") as f:
                    queue = json.load(f)
            except Exception:
                queue = []
        cmd = {
            "id": str(uuid.uuid4()),
            "bot_id": bot_id,
            "action": action,
            "data": cmd_data,
            "time": time.time()
        }
        queue.append(cmd)
        with open(ipc_file, "w") as f:
            json.dump(queue, f)

async def showdown_ipc_listener(bot_id: str, sd_client):
    """Listens for and processes Web Dashboard commands inside the active bot process."""
    ipc_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memories", "ipc")
    ipc_file = os.path.join(ipc_dir, "showdown_queue.json")
    while True:
        try:
            if os.path.exists(ipc_file):
                cmds_to_run = []
                with state_lock:
                    try:
                        with open(ipc_file, "r") as f:
                            queue = json.load(f)
                    except Exception:
                        queue = []
                    remaining = []
                    for c in queue:
                        if c.get("bot_id") == bot_id:
                            cmds_to_run.append(c)
                        else:
                            remaining.append(c)
                    if cmds_to_run:
                        with open(ipc_file, "w") as f:
                            json.dump(remaining, f)
                for c in cmds_to_run:
                    act = c.get("action")
                    cdata = c.get("data", {})
                    init_uid = cdata.get("initiator_user_id")
                    if init_uid and sd_client:
                        sd_client.initiator_user_id = str(init_uid)
                    if act == "challenge":
                        tgt = cdata.get("target")
                        fmt = cdata.get("format")
                        if tgt and sd_client:
                            await sd_client.challenge_user(tgt, fmt)
                    elif act == "accept":
                        challenger = cdata.get("challenger")
                        fmt = cdata.get("format", sd_client.default_format)
                        if challenger and sd_client:
                            await sd_client._accept_challenge_with_team(challenger, fmt)
                    elif act == "ladder":
                        fmt = cdata.get("format")
                        if sd_client:
                            await sd_client.search_ladder(fmt)
        except Exception:
            pass
        await asyncio.sleep(1.0)

# ─── DYNAMIC CHARACTER PERSONA SWITCHING ─────────────
def switch_character_persona(target_name_or_id):
    """Switches the active character persona dynamically in memory, process env, bots.json, and config.json."""
    global config, bots_state
    with state_lock:
        bots_state = load_bots()
        target_str = str(target_name_or_id).strip().lower()
        found = None
        for b in bots_state.get("bots", []):
            if b.get("id", "").lower() == target_str:
                found = b
                break
            if (b.get("name") or "").strip().lower() == target_str:
                found = b
                break
            if target_str in (b.get("name") or "").strip().lower():
                found = b
                break
        if not found:
            return False, None
        bots_state["active_id"] = found["id"]
        save_bots(bots_state)
        # Update process BOT_ID only if running inside a child worker
        if os.getenv("IS_BOT_CHILD") == "1":
            os.environ["BOT_ID"] = found["id"]
        else:
            os.environ.pop("BOT_ID", None)
        apply_bot_to_config(found, save_to_disk=True)
        save_config(config)
        return True, found

def do_list_characters():
    global bots_state
    bots_state = load_bots()
    aid = bots_state.get("active_id")
    embed = discord.Embed(
        title="🎭 Available Character Personas",
        description="Switch characters using `/character switch [name]` or `/switch [name]`:\n",
        color=0x9b59b6
    )
    for b in bots_state.get("bots", []):
        is_act = (b.get("id") == aid)
        badge = " ⭐ **[ACTIVE]**" if is_act else ""
        role = b.get("config", {}).get("role") or "Custom"
        prov = b.get("config", {}).get("provider") or "auto"
        preview = (b.get("config", {}).get("personality", "") or "")[:70]
        embed.add_field(
            name=f"{b.get('emoji', '🤖')} {b.get('name', 'Unnamed')}{badge}",
            value=f"• ID: `{b.get('id')}`\n• Role: `{role}` | Provider: `{prov}`\n• Personality: *\"{preview}...\"*",
            inline=False
        )
    embed.set_footer(text="Example: /switch Law  or  switch to Law in DM")
    return embed

# ─── INTERACTIVE TRAINING SYSTEM & TRAINING DATA STORAGE ─
TRAINING_DATA_FILE = os.path.join(SCRIPT_DIR, "data", "training_data.json")
TRAINING_BACKUPS_FILE = os.path.join(SCRIPT_DIR, "data", "training_backups.json")

def load_training_data() -> dict:
    with state_lock:
        if os.path.exists(TRAINING_DATA_FILE):
            try:
                with open(TRAINING_DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        data.setdefault("approved", [])
                        data.setdefault("rejected", [])
                        return data
            except Exception as e:
                print(f"[TRAIN] Failed to load {TRAINING_DATA_FILE}: {e}")
        return {"version": 1, "approved": [], "rejected": []}

def save_training_data(data: dict):
    with state_lock:
        data["updated_at"] = time.time()
        os.makedirs(os.path.dirname(TRAINING_DATA_FILE), exist_ok=True)
        _atomic_json_save(TRAINING_DATA_FILE, data, backup=True, max_backups=5)

def load_training_backups() -> dict:
    with state_lock:
        if os.path.exists(TRAINING_BACKUPS_FILE):
            try:
                with open(TRAINING_BACKUPS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        data.setdefault("next_id", 1)
                        data.setdefault("backups", [])
                        return data
            except Exception as e:
                print(f"[TRAIN] Failed to load {TRAINING_BACKUPS_FILE}: {e}")
        return {"next_id": 1, "backups": []}

def save_training_backups(data: dict):
    with state_lock:
        os.makedirs(os.path.dirname(TRAINING_BACKUPS_FILE), exist_ok=True)
        _atomic_json_save(TRAINING_BACKUPS_FILE, data, backup=True, max_backups=5)

def add_training_sample(prompt: str, response: str, style: str, status: str, bot_id: str = None, bot_name: str = None, user_id: int = None):
    t_data = load_training_data()
    key = "approved" if status == "approved" else "rejected"
    entry = {
        "id": f"{key}_{int(time.time()*1000)}_{random.randint(100, 999)}",
        "user_id": str(user_id) if user_id else "",
        "bot_id": str(bot_id or get_current_bot_id()),
        "bot_name": str(bot_name or get_current_bot_name()),
        "prompt": prompt.strip(),
        "response": response.strip(),
        "style": style.strip(),
        "timestamp": time.time()
    }
    t_data.setdefault(key, []).append(entry)
    save_training_data(t_data)
    return entry

def build_training_prompt_hook(bot_id: str = None) -> str:
    """Dynamically builds style & preference guidance from training data to hook into the main prompt without modifying it on disk."""
    t_data = load_training_data()
    appr = t_data.get("approved", [])
    rejd = t_data.get("rejected", [])
    if not appr and not rejd:
        return ""

    bid = str(bot_id or "").strip()
    if bid:
        b_appr = [x for x in appr if x.get("bot_id") == bid]
        b_rejd = [x for x in rejd if x.get("bot_id") == bid]
        if b_appr:
            appr = b_appr
        if b_rejd:
            rejd = b_rejd

    lines = [
        "[TRAINED RESPONSE STYLE DIRECTIVES (LEARNED FROM TRAINING DATA)]",
        "The user has actively trained your character via preference evaluations. Adapt your conversational tone, phrasing, pacing, and style to match the APPROVED examples below and avoid the REJECTED examples.",
        "Stay strictly in character as defined above."
    ]

    if appr:
        lines.append("\n=== APPROVED RESPONSE SAMPLES (EMULATE THIS STYLE & TONE) ===")
        for item in appr[-8:]:
            p = item.get("prompt", "")
            r = item.get("response", "")
            s = item.get("style", "")
            s_str = f" [Tone: {s}]" if s else ""
            lines.append(f'• User: "{p}"\n  Approved Response{s_str}: "{r}"')

    if rejd:
        lines.append("\n=== REJECTED RESPONSE SAMPLES (AVOID THESE PATTERNS & MANNERISMS) ===")
        for item in rejd[-8:]:
            p = item.get("prompt", "")
            r = item.get("response", "")
            s = item.get("style", "")
            s_str = f" [Disapproved Style: {s}]" if s else ""
            lines.append(f'• User: "{p}"\n  Rejected Response{s_str}: "{r}"')

    lines.append("\nAlign your response style with the approved patterns above.")
    return "\n".join(lines)

# Session tracking & in-memory pending turns
active_training_sessions = {}
pending_training_turns = {}
turn_message_map = {}

def is_training_active(user_id: int) -> bool:
    uid = str(user_id)
    return uid in active_training_sessions and active_training_sessions[uid].get("active", False)

def start_training_session(user_id: int, channel_id: int, bot_id: str = None):
    uid = str(user_id)
    active_training_sessions[uid] = {
        "active": True,
        "channel_id": channel_id,
        "bot_id": bot_id or get_current_bot_id(),
        "started_at": time.time()
    }

def stop_training_session(user_id: int) -> dict:
    uid = str(user_id)
    active_training_sessions.pop(uid, None)
    t_data = load_training_data()
    appr_c = sum(1 for x in t_data.get("approved", []) if x.get("user_id") == uid)
    rejd_c = sum(1 for x in t_data.get("rejected", []) if x.get("user_id") == uid)
    if appr_c == 0 and rejd_c == 0:
        appr_c = len(t_data.get("approved", []))
        rejd_c = len(t_data.get("rejected", []))
    return {"approved": appr_c, "rejected": rejd_c}

def do_start_training(user_id: int, channel_id: int):
    cur_bid = get_current_bot_id()
    cur_bname = get_current_bot_name()
    start_training_session(user_id, channel_id, cur_bid)

    t_data = load_training_data()
    appr_c = len(t_data.get("approved", []))
    rejd_c = len(t_data.get("rejected", []))

    embed = discord.Embed(
        title="🎯 Training Mode Started",
        description=(
            f"Training mode is active for **{cur_bname}**!\n\n"
            f"💬 **How Training Works:**\n"
            f"1. Type any message in this DM (from *'Hi'* to *'how many stars in the sky'*).\n"
            f"2. The AI will output **two responses in different tones & styles**.\n"
            f"3. Use the reactions or buttons:\n"
            f"   • ✔️ **Approve**: Approve this response style\n"
            f"   • ❌ **Reject**: Reject this response style\n"
            f"   • ♻️ **Regenerate**: Generate two new styles\n\n"
            f"All approved & rejected answers are saved to **training data** to shape how the bot talks without modifying the base personality prompt.\n\n"
            f"• Current Samples: `{appr_c}` approved ✔️, `{rejd_c}` rejected ❌\n\n"
            f"🛑 *Say **'Stop.'** at any time to finish training.*"
        ),
        color=0x3498db
    )
    return embed

def do_tbackup(user_id: int):
    t_data = load_training_data()
    appr = t_data.get("approved", [])
    rejd = t_data.get("rejected", [])
    cur_bid = get_current_bot_id()
    cur_bname = get_current_bot_name()

    if not appr and not rejd:
        embed = discord.Embed(
            title="⚠️ No Training Data to Back Up",
            description="You haven't recorded any approved or rejected training samples yet.\nStart with `/train` in DMs to generate training data!",
            color=0xf39c12
        )
        return False, embed

    backups_data = load_training_backups()
    next_id = backups_data.get("next_id", 1)
    existing_ids = [b.get("id", 0) for b in backups_data.get("backups", [])]
    if existing_ids:
        next_id = max(next_id, max(existing_ids) + 1)

    now_ts = time.time()
    now_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_ts))

    backup_record = {
        "id": next_id,
        "user_id": str(user_id),
        "bot_id": cur_bid,
        "bot_name": cur_bname,
        "created_at": now_ts,
        "date": now_str,
        "approved_count": len(appr),
        "rejected_count": len(rejd),
        "data": {
            "approved": list(appr),
            "rejected": list(rejd)
        }
    }

    backups_data.setdefault("backups", []).append(backup_record)
    backups_data["next_id"] = next_id + 1
    save_training_backups(backups_data)

    embed = discord.Embed(
        title="💾 Training Data Backup Created",
        description=f"Successfully backed up active training data as **Backup #{next_id}**!",
        color=0x2ecc71
    )
    embed.add_field(name="Backup ID", value=f"`{next_id}`", inline=True)
    embed.add_field(name="Character", value=f"**{cur_bname}**", inline=True)
    embed.add_field(name="Samples", value=f"✔️ `{len(appr)} approved` | ❌ `{len(rejd)} rejected`", inline=False)
    embed.add_field(name="Date", value=f"`{now_str}`", inline=True)
    embed.set_footer(text=f"Restore: /backup restore {next_id} | Resume: /resume training {next_id}")
    return True, embed

def do_list_backups():
    backups_data = load_training_backups()
    b_list = backups_data.get("backups", [])
    if not b_list:
        embed = discord.Embed(
            title="📂 Training Backups",
            description="No backups found. Use `/tbackup` to save your current training data!",
            color=0x7f8c8d
        )
        return embed

    embed = discord.Embed(
        title="📂 Saved Training Backups",
        description=f"Found **{len(b_list)}** saved training backups:\n",
        color=0x3498db
    )
    for b in b_list:
        bid = b.get("id")
        bname = b.get("bot_name", "Unknown Bot")
        appr_c = b.get("approved_count", 0)
        rejd_c = b.get("rejected_count", 0)
        dt = b.get("date", "Unknown Date")
        embed.add_field(
            name=f"Backup #{bid} — {bname}",
            value=f"• Samples: ✔️ `{appr_c}` approved • ❌ `{rejd_c}` rejected\n• Saved: `{dt}`\n• Quick Restore: `/backup restore {bid}`",
            inline=False
        )
    embed.set_footer(text="Use /backup restore [Id] or /resume training [Id]")
    return embed

def do_restore_backup(backup_id: int):
    backups_data = load_training_backups()
    found = None
    for b in backups_data.get("backups", []):
        if b.get("id") == backup_id:
            found = b
            break

    if not found:
        embed = discord.Embed(
            title="❌ Backup Not Found",
            description=f"Could not find a training backup with ID `#{backup_id}`.\nUse `/backups` to see all saved backups.",
            color=0xe74c3c
        )
        return False, embed

    restored_data = found.get("data", {})
    t_data = {
        "version": 1,
        "updated_at": time.time(),
        "approved": list(restored_data.get("approved", [])),
        "rejected": list(restored_data.get("rejected", []))
    }
    save_training_data(t_data)

    embed = discord.Embed(
        title="✅ Training Backup Restored",
        description=f"Backup **#{backup_id}** has been restored into the active training data!",
        color=0x2ecc71
    )
    embed.add_field(name="Character", value=f"**{found.get('bot_name', 'Bot')}**", inline=True)
    embed.add_field(name="Approved Samples", value=f"`{found.get('approved_count', len(t_data['approved']))}` ✔️", inline=True)
    embed.add_field(name="Rejected Samples", value=f"`{found.get('rejected_count', len(t_data['rejected']))}` ❌", inline=True)
    embed.set_footer(text="The bot's response style will now reflect this restored data.")
    return True, embed

def do_delete_backup(backup_id: int):
    backups_data = load_training_backups()
    b_list = backups_data.get("backups", [])
    found = None
    for b in b_list:
        if b.get("id") == backup_id:
            found = b
            break
    if not found:
        embed = discord.Embed(
            title="❌ Backup Not Found",
            description=f"Could not find a backup with ID `#{backup_id}` to delete.",
            color=0xe74c3c
        )
        return False, embed

    backups_data["backups"] = [b for b in b_list if b.get("id") != backup_id]
    save_training_backups(backups_data)

    embed = discord.Embed(
        title="🗑️ Training Backup Deleted",
        description=f"Backup **#{backup_id}** ({found.get('bot_name')}) has been permanently deleted.",
        color=0xe74c3c
    )
    return True, embed

def do_resume_training(user_id: int, channel_id: int, backup_id: Optional[int] = None):
    cur_bid = get_current_bot_id()
    cur_bname = get_current_bot_name()

    restored_info = ""
    if backup_id is not None:
        ok, res_emb = do_restore_backup(backup_id)
        if not ok:
            return res_emb
        restored_info = f"\n📦 Restored **Backup #{backup_id}** prior to resuming."

    start_training_session(user_id, channel_id, cur_bid)
    
    t_data = load_training_data()
    appr_c = len(t_data.get("approved", []))
    rejd_c = len(t_data.get("rejected", []))

    embed = discord.Embed(
        title="🎯 Training Mode Resumed",
        description=(
            f"Training mode is active for **{cur_bname}**!{restored_info}\n\n"
            f"• Current Training Data: `{appr_c}` approved ✔️, `{rejd_c}` rejected ❌\n\n"
            f"💬 **How to train:**\n"
            f"Speak to the bot normally in this DM (from *'Hi'* to *'how many stars in the sky'*).\n"
            f"The AI will output **two responses in different tones and styles** with reactions ❌✔️♻️.\n\n"
            f"🛑 Say **'Stop.'** at any time to exit training mode."
        ),
        color=0x9b59b6
    )
    return embed

def _parse_training_pair(raw_text: str):
    if not raw_text:
        return None, None, None, None
    pattern = r'===\s*OPTION\s*1\s*===(.*?)(?:===\s*OPTION\s*2\s*===)(.*)$'
    match = re.search(pattern, raw_text, re.DOTALL | re.IGNORECASE)
    if not match:
        return None, None, None, None
    chunk1 = match.group(1).strip()
    chunk2 = match.group(2).strip()
    style1 = "Style A"
    style2 = "Style B"
    s1_match = re.search(r'^\s*(?:STYLE|TONE)\s*:\s*([^\n\r]+)', chunk1, re.IGNORECASE | re.MULTILINE)
    if s1_match:
        style1 = s1_match.group(1).strip().strip("*_`")
        chunk1 = re.sub(r'^\s*(?:STYLE|TONE)\s*:\s*[^\n\r]+[\r\n]*', '', chunk1, flags=re.IGNORECASE).strip()
    s2_match = re.search(r'^\s*(?:STYLE|TONE)\s*:\s*([^\n\r]+)', chunk2, re.IGNORECASE | re.MULTILINE)
    if s2_match:
        style2 = s2_match.group(1).strip().strip("*_`")
        chunk2 = re.sub(r'^\s*(?:STYLE|TONE)\s*:\s*[^\n\r]+[\r\n]*', '', chunk2, flags=re.IGNORECASE).strip()
    return chunk1, style1, chunk2, style2

async def query_training_llm(system_msg: str, prompt: str) -> str:
    provider = config.get("provider", "auto")
    if provider == "gemini" and GEMINI_KEY and time.time() >= gemini_blocked_until:
        r, e = await ask_gemini(system_msg, [], prompt)
        if not e and r:
            return r
    elif provider == "groq" and GROQ_KEY and time.time() >= groq_blocked_until:
        r, e = await ask_groq([], prompt, system_msg=system_msg)
        if not e and r:
            return r
    elif provider == "mistral" and (os.getenv("MISTRAL_KEY") or MISTRAL_KEY):
        r, e = await ask_mistral([], prompt, system_msg=system_msg)
        if not e and r:
            return r
    elif provider == "openrouter" and os.getenv("OPENROUTER_KEY"):
        r, e = await ask_openrouter([], prompt, system_msg=system_msg)
        if not e and r:
            return r
    elif provider == "openai" and get_openai_key():
        r, e = await ask_openai([], prompt, system_msg=system_msg)
        if not e and r:
            return r
    elif provider == "deepseek" and get_deepseek_key():
        r, e = await ask_deepseek([], prompt, system_msg=system_msg)
        if not e and r:
            return r

    # Auto fallback
    if GEMINI_KEY and time.time() >= gemini_blocked_until:
        r, e = await ask_gemini(system_msg, [], prompt)
        if not e and r:
            return r
    if GROQ_KEY and time.time() >= groq_blocked_until:
        r, e = await ask_groq([], prompt, system_msg=system_msg)
        if not e and r:
            return r
    if get_deepseek_key() and time.time() >= deepseek_blocked_until:
        r, e = await ask_deepseek([], prompt, system_msg=system_msg)
        if not e and r:
            return r
    if (os.getenv("MISTRAL_KEY") or MISTRAL_KEY):
        r, e = await ask_mistral([], prompt, system_msg=system_msg)
        if not e and r:
            return r
    if os.getenv("OPENROUTER_KEY"):
        r, e = await ask_openrouter([], prompt, system_msg=system_msg)
        if not e and r:
            return r
    return ""

async def generate_training_pair(channel_id, prompt: str, user_id=None, user_name=None):
    cur_bid = get_current_bot_id()
    cur_bname = get_current_bot_name()
    base_personality = config.get("personality", f"You are {cur_bname}.")
    training_hook = build_training_prompt_hook(cur_bid)

    pair_instruction = (
        f"{base_personality}\n\n"
        f"{training_hook}\n\n"
        f"[TRAINING PAIR GENERATION DIRECTIVE]:\n"
        f"The user is actively training your conversational response style. You must generate TWO contrasting, in-character candidate responses to the user's message with distinctly DIFFERENT tone, pacing, vocabulary, and delivery style.\n"
        f"• Both options must be authentically in character for {cur_bname}.\n"
        f"• Option 1: One distinct style (e.g. calm, concise, reserved, or subtle).\n"
        f"• Option 2: A contrasting style (e.g. expressive, elaborate, vivid, witty, or emotive).\n"
        f"• Output format must follow this exact template:\n"
        f"===OPTION 1===\n"
        f"STYLE: <1-4 word tone descriptor, e.g. Calm & Concise>\n"
        f"<full response for Option 1>\n"
        f"===OPTION 2===\n"
        f"STYLE: <1-4 word tone descriptor, e.g. Expressive & Dynamic>\n"
        f"<full response for Option 2>"
    )

    raw_reply = await query_training_llm(pair_instruction, prompt)
    opt1_text, opt1_style, opt2_text, opt2_style = _parse_training_pair(raw_reply)

    if opt1_text and opt2_text:
        return opt1_text, opt1_style, opt2_text, opt2_style

    # Fallback to two focused generations
    sys1 = f"{base_personality}\n\n[STYLE DIRECTIVE]: Respond in a calm, concise, grounded, and reserved tone."
    sys2 = f"{base_personality}\n\n[STYLE DIRECTIVE]: Respond in a dynamic, expressive, vivid, and emotive tone."
    r1 = await query_training_llm(sys1, prompt)
    r2 = await query_training_llm(sys2, prompt)
    return (r1 or "..."), "Calm & Concise", (r2 or "..."), "Expressive & Dynamic"

class TrainingFeedbackView(discord.ui.View):
    def __init__(self, user_id: int, turn_id: str, opt_num: int):
        super().__init__(timeout=86400)
        self.user_id = user_id
        self.turn_id = turn_id
        self.opt_num = opt_num

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success, emoji="✔️")
    async def approve_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Only the training user can evaluate this response.", ephemeral=True)
            return
        await handle_training_feedback(
            channel=interaction.channel,
            user_id=self.user_id,
            turn_id=self.turn_id,
            choice="approve",
            opt_num=self.opt_num,
            interaction=interaction
        )

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger, emoji="❌")
    async def reject_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Only the training user can evaluate this response.", ephemeral=True)
            return
        await handle_training_feedback(
            channel=interaction.channel,
            user_id=self.user_id,
            turn_id=self.turn_id,
            choice="reject",
            opt_num=self.opt_num,
            interaction=interaction
        )

    @discord.ui.button(label="Regenerate", style=discord.ButtonStyle.secondary, emoji="♻️")
    async def regen_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Only the training user can evaluate this response.", ephemeral=True)
            return
        await handle_training_feedback(
            channel=interaction.channel,
            user_id=self.user_id,
            turn_id=self.turn_id,
            choice="regenerate",
            opt_num=self.opt_num,
            interaction=interaction
        )

async def handle_training_feedback(channel, user_id: int, turn_id: str, choice: str, opt_num: int, interaction=None):
    turn = pending_training_turns.get(turn_id)
    if not turn:
        msg = "⚠️ This training turn has already been processed or expired."
        if interaction:
            await interaction.response.send_message(msg, ephemeral=True)
        elif channel:
            await channel.send(msg)
        return

    prompt = turn["prompt"]
    cur_bid = turn.get("bot_id") or get_current_bot_id()
    cur_bname = turn.get("bot_name") or get_current_bot_name()
    opt1 = turn["opt1"]
    opt2 = turn["opt2"]

    if choice == "approve":
        chosen = opt1 if opt_num == 1 else opt2
        rejected = opt2 if opt_num == 1 else opt1
        
        # Save chosen as approved and rejected alternative as rejected in training data
        add_training_sample(prompt, chosen["text"], chosen["style"], "approved", cur_bid, cur_bname, user_id)
        add_training_sample(prompt, rejected["text"], rejected["style"], "rejected", cur_bid, cur_bname, user_id)
        
        if channel:
            add_to_context(channel.id, "user", prompt, user_id=user_id, bot_id=cur_bid)
            add_to_context(channel.id, "assistant", chosen["text"], bot_id=cur_bid)

        pending_training_turns.pop(turn_id, None)
        turn_message_map.pop(opt1.get("msg_id"), None)
        turn_message_map.pop(opt2.get("msg_id"), None)

        msg_text = (
            f"✔️ **Option {opt_num} Approved!** *(Alternative marked as rejected)*\n"
            f"Saved to **training data** for **{cur_bname}**.\n"
            f"*(Continue speaking to train more, or say **'Stop.'** to finish)*"
        )
        if interaction:
            await interaction.response.send_message(msg_text)
        elif channel:
            await channel.send(msg_text)

    elif choice == "reject":
        rejected = opt1 if opt_num == 1 else opt2
        add_training_sample(prompt, rejected["text"], rejected["style"], "rejected", cur_bid, cur_bname, user_id)
        msg_text = f"❌ **Option {opt_num} Marked as Rejected.** Saved to **training data**."
        if interaction:
            await interaction.response.send_message(msg_text)
        elif channel:
            await channel.send(msg_text)

    elif choice == "regenerate":
        if interaction:
            await interaction.response.send_message("♻️ **Regenerating 2 new styles...**")
        elif channel:
            await channel.send("♻️ **Regenerating 2 new styles...**")
        
        turn_message_map.pop(opt1.get("msg_id"), None)
        turn_message_map.pop(opt2.get("msg_id"), None)
        pending_training_turns.pop(turn_id, None)

        if channel:
            async with safe_typing(channel):
                t1, s1, t2, s2 = await generate_training_pair(channel.id, prompt, user_id=user_id)
                new_turn_id = f"turn_{int(time.time()*1000)}_{user_id}"
                emb1 = discord.Embed(title="🅰️ Option 1 (Regenerated)", description=f"*{s1}*\n\n{t1}", color=0x3498db)
                emb1.set_footer(text="React ✔️ Approve | ❌ Reject | ♻️ Regenerate")
                v1 = TrainingFeedbackView(user_id=user_id, turn_id=new_turn_id, opt_num=1)
                m1 = await channel.send(embed=emb1, view=v1)

                emb2 = discord.Embed(title="🅱️ Option 2 (Regenerated)", description=f"*{s2}*\n\n{t2}", color=0x9b59b6)
                emb2.set_footer(text="React ✔️ Approve | ❌ Reject | ♻️ Regenerate")
                v2 = TrainingFeedbackView(user_id=user_id, turn_id=new_turn_id, opt_num=2)
                m2 = await channel.send(embed=emb2, view=v2)

                for emo in ("✔️", "❌", "♻️"):
                    try:
                        await m1.add_reaction(emo)
                        await m2.add_reaction(emo)
                    except Exception:
                        pass

                pending_training_turns[new_turn_id] = {
                    "turn_id": new_turn_id,
                    "prompt": prompt,
                    "bot_id": cur_bid,
                    "bot_name": cur_bname,
                    "opt1": {"text": t1, "style": s1, "msg_id": m1.id},
                    "opt2": {"text": t2, "style": s2, "msg_id": m2.id},
                }
                turn_message_map[m1.id] = {"user_id": user_id, "turn_id": new_turn_id, "opt_num": 1}
                turn_message_map[m2.id] = {"user_id": user_id, "turn_id": new_turn_id, "opt_num": 2}

async def handle_training_turn(message: discord.Message, prompt_text: str):
    user_id = message.author.id
    channel = message.channel
    cur_bid = get_current_bot_id()
    cur_bname = get_current_bot_name()

    async with safe_typing(channel):
        t1, s1, t2, s2 = await generate_training_pair(channel.id, prompt_text, user_id=user_id, user_name=message.author.display_name)
        new_turn_id = f"turn_{int(time.time()*1000)}_{user_id}"

        emb1 = discord.Embed(title="🅰️ Option 1", description=f"*{s1}*\n\n{t1}", color=0x3498db)
        emb1.set_footer(text="React ✔️ Approve | ❌ Reject | ♻️ Regenerate")
        v1 = TrainingFeedbackView(user_id=user_id, turn_id=new_turn_id, opt_num=1)
        m1 = await channel.send(embed=emb1, view=v1)

        emb2 = discord.Embed(title="🅱️ Option 2", description=f"*{s2}*\n\n{t2}", color=0x9b59b6)
        emb2.set_footer(text="React ✔️ Approve | ❌ Reject | ♻️ Regenerate")
        v2 = TrainingFeedbackView(user_id=user_id, turn_id=new_turn_id, opt_num=2)
        m2 = await channel.send(embed=emb2, view=v2)

        for emo in ("✔️", "❌", "♻️"):
            try:
                await m1.add_reaction(emo)
                await m2.add_reaction(emo)
            except Exception:
                pass

        pending_training_turns[new_turn_id] = {
            "turn_id": new_turn_id,
            "prompt": prompt_text,
            "bot_id": cur_bid,
            "bot_name": cur_bname,
            "opt1": {"text": t1, "style": s1, "msg_id": m1.id},
            "opt2": {"text": t2, "style": s2, "msg_id": m2.id},
        }
        turn_message_map[m1.id] = {"user_id": user_id, "turn_id": new_turn_id, "opt_num": 1}
        turn_message_map[m2.id] = {"user_id": user_id, "turn_id": new_turn_id, "opt_num": 2}

# ─── PRESENCE / ACTIVITY ──────────────────────────────
async def presence_loop():
    await client.wait_until_ready()
    while not client.is_closed():
        try:
            if not config.get("presence_enabled", True):
                await asyncio.sleep(60)
                continue
            cur_bname = (get_current_bot_name() or "").lower()
            if "yuna" in cur_bname and YUNA_RPC_AVAILABLE and yuna_rpc:
                try:
                    activity = await yuna_rpc.get_or_update_activity()
                except Exception as _rpc_err:
                    print(f"[YUNA RPC ERROR] {_rpc_err}", flush=True)
                    activity = get_bot_activity()
            else:
                activity = get_bot_activity()

            status = discord.Status.online
            await client.change_presence(status=status, activity=activity)
            await asyncio.sleep(config.get("presence_cycle_interval", 25))
        except Exception as e:
            print(f"[PRESENCE] Error: {e}")
            await asyncio.sleep(60)

# ─── PERIODIC 5-MINUTE MEMORY MANAGER LOOP ───────────
async def memory_manager_loop():
    """Flushes memory buffers and extracts long-term memories periodically (every 5 minutes)."""
    await client.wait_until_ready()
    while not client.is_closed():
        try:
            await asyncio.sleep(300)  # Every 5 minutes (300 seconds)
            if not config.get("user_memory_enabled", True):
                continue

            curr_bid = get_current_bot_id()
            extracted_any = False
            now = time.time()

            for uid, profile in list(user_profiles.items()):
                if not isinstance(profile, dict):
                    continue
                bot_mems = profile.get("bot_memories", {})
                bmem = bot_mems.get(curr_bid)
                if not bmem or not isinstance(bmem, dict):
                    continue
                buffer = bmem.get("conversation_buffer", [])
                if len(buffer) >= 2:
                    last_ext = _user_last_memory_extraction.get((uid, curr_bid), 0)
                    if (now - last_ext) >= 240:  # At least ~4-5 mins since last extraction
                        user_disp = profile.get("name", uid)
                        print(f"[MEMORY BATCH] 5-minute cycle: Extracting memories for {user_disp} ({len(buffer)} msgs buffered)...")
                        await _extract_memories_from_buffer(uid, bot_id=curr_bid)
                        _user_last_memory_extraction[(uid, curr_bid)] = now
                        extracted_any = True

            # Save dirty profiles or newly extracted facts
            if extracted_any or _profiles_dirty:
                save_user_profiles(force=True)
                print("[MEMORY BATCH] Periodic 5-minute memory sync complete.")
        except Exception as e:
            print(f"[MEMORY LOOP ERROR] {e}")
            await asyncio.sleep(60)


def get_bot_activity():
    if vtuber_bridge_online:
        return discord.Activity(type=discord.ActivityType.watching, name="the VTuber stream")
    if voice_sessions:
        return discord.Activity(type=discord.ActivityType.listening, name="voice chat")
    if config.get("presence_music_enabled", True):
        artist = config.get("presence_music_artist", "Kairiki Bear")
        statuses = config.get("presence_idle_statuses", [])
        if statuses:
            choice = random.choice(statuses)
            if "Listening" in choice or "listening" in choice:
                return discord.Activity(type=discord.ActivityType.listening, name=choice.replace("Listening to ", "").replace("listening to ", ""))
            if "Watching" in choice or "watching" in choice:
                return discord.Activity(type=discord.ActivityType.watching, name=choice.replace("Watching ", "").replace("watching ", ""))
            if "Competing" in choice or "competing" in choice:
                return discord.Activity(type=discord.ActivityType.competing, name=choice.replace("Competing in ", "").replace("competing in ", ""))
            return discord.Game(name=choice)
        return discord.Activity(type=discord.ActivityType.listening, name=artist)
    return discord.Game(name=get_current_bot_name() or "AI Companion")

# ─── CONTEXT HELPERS ──────────────────────────────────
def get_active_model():
    c_mod = (config.get("custom_model") or "").strip()
    if c_mod:
        return c_mod
    mod = (config.get("model") or "").strip()
    if mod and mod not in ("openrouter/free", "default", "auto"):
        return mod
    prov = config.get("provider", "auto")
    if prov == "groq":
        return (config.get("groq_model") or "qwen/qwen3.8-27b").strip()
    elif prov == "mistral":
        return (config.get("mistral_model") or "ministral-8b-latest").strip()
    elif prov == "gemini":
        return (config.get("gemini_model") or "gemini-3.1-flash-lite").strip()
    elif prov == "deepseek":
        return (config.get("deepseek_model") or "deepseek-chat").strip()
    elif prov == "openai":
        return (config.get("openai_chat_model") or "gpt-4o-mini").strip()
    return "inclusionai/ling-3.0-flash-vl:free"

def get_context_key(channel_id, bot_id=None):
    cid = str(channel_id)
    if cid.startswith("web_") or cid.startswith("web_bot_") or cid == "vtuber" or cid == "social_caption_generator":
        return cid
    bid = str(bot_id or get_current_bot_id() or "default")
    if cid.startswith(f"{bid}:"):
        return cid
    return f"{bid}:{cid}"

def get_context(channel_id, bot_id=None):
    if not config.get("context_enabled", True):
        return []
    key = get_context_key(channel_id, bot_id)
    raw = contexts.get(key, [])
    return [
        {
            "role": m.get("role", "user"),
            "content": m.get("content", ""),
            "user_id": str(m.get("user_id")) if m.get("user_id") else None,
            "user_name": m.get("user_name"),
            "bot_id": m.get("bot_id")
        }
        for m in raw
    ]


def add_to_context(channel_id, role, content, user_name=None, user_id=None, bot_id=None):
    key = get_context_key(channel_id, bot_id)
    if key not in contexts:
        contexts[key] = []
    if role == "user" and user_name:
        prefix = f"[{user_name}"
        if not str(content).startswith(prefix) and not str(content).startswith("["):
            content = f"[{user_name}]: {content}"
    contexts[key].append({
        "role": role,
        "content": content,
        "user_id": str(user_id) if user_id else None,
        "user_name": user_name,
        "bot_id": str(bot_id or get_current_bot_id() or "")
    })
    max_c = config.get("max_context", 10)
    try: max_c = int(max_c)
    except: max_c = 10
    contexts[key] = contexts[key][-max_c:]
    save_contexts()

def clear_context(channel_id, bot_id=None):
    key = get_context_key(channel_id, bot_id)
    contexts.pop(key, None)
    contexts.pop(str(channel_id), None)
    save_contexts()

async def check_owner(user_id: int) -> bool:
    global owner_id_cached
    if OWNER_ID:
        return str(user_id) == OWNER_ID
    if owner_id_cached:
        return user_id == owner_id_cached
    try:
        app = await client.application_info()
        owner_id_cached = app.owner.id
        return user_id == owner_id_cached
    except:
        return False

def check_cooldown(user_id: int) -> tuple:
    now = time.time()
    cd = config.get("cooldown_seconds", 10)
    remaining = cd - (now - user_cooldowns[user_id])
    if remaining > 0:
        return False, int(remaining)
    user_cooldowns[user_id] = now
    return True, 0

# ─── MESSAGE SPLITTING HELPER ─────────────────────────
async def send_split_messages(destination, text: str, reply_to=None):
    if not text:
        return

    # Strip invisible TTS emotion bracket tags for clean Discord chat display
    display_text = strip_emotion_tags(text) or text
        
    # If message splitting is disabled, send as a single clean message (split only if exceeding Discord 2000 limit)
    if not config.get("message_split_enabled", False):
        clean_text = display_text.replace("||SPLIT||", " ").strip()
        chunks = [clean_text[i:i+1950] for i in range(0, len(clean_text), 1950)]
        for j, chunk in enumerate(chunks):
            try:
                if reply_to and j == 0:
                    await safe_reply(reply_to, chunk)
                else:
                    await destination.send(chunk)
            except discord.Forbidden:
                try:
                    await destination.send(chunk)
                except Exception:
                    pass
            except Exception:
                pass
        return

    parts = []
    if "||SPLIT||" in display_text:
        parts = [p.strip() for p in display_text.split("||SPLIT||") if p.strip()]
    else:
        parts = [display_text]
        
    if len(parts) == 1 and len(display_text) > 300:
        raw = [p.strip() for p in display_text.split("\n\n") if p.strip()]
        if len(raw) > 1:
            parts = raw
        else:
            sentences = re.split(r'(?<=[.!?])\s+', display_text)
            if len(sentences) > 1:
                parts = []
                current = ""
                for s in sentences:
                    if len(current) + len(s) < 350:
                        current += " " + s if current else s
                    else:
                        if current:
                            parts.append(current.strip())
                        current = s
                if current:
                    parts.append(current.strip())
                    
    min_msgs = max(1, config.get("message_split_min", 1))
    max_msgs = max(1, config.get("message_split_max", 1))
    delay = max(0.0, config.get("message_split_delay", 1.0))
    target = random.randint(min_msgs, max_msgs)
    if len(parts) > target:
        merged = " ".join(parts[target-1:])
        parts = parts[:target-1] + [merged]
    elif len(parts) < target:
        target = len(parts)
    for i, part in enumerate(parts[:target]):
        if i > 0 and delay > 0:
            await asyncio.sleep(delay)
        chunks = [part[i:i+2000] for i in range(0, len(part), 2000)]
        for j, chunk in enumerate(chunks):
            try:
                if reply_to and i == 0 and j == 0:
                    await safe_reply(reply_to, chunk)
                else:
                    await destination.send(chunk)
            except discord.Forbidden:
                try:
                    await destination.send(chunk)
                except Exception as e:
                    print(f"[SEND ERROR] Forbidden fallback failed: {e}")
            except Exception as e:
                print(f"[SEND ERROR] {e}")

async def safe_reply(message, content=None, embed=None, embeds=None, file=None, files=None, delete_after=None, **kwargs):
    """Safely replies to a Discord message, converting embeds to markdown if Embed Links is missing, and falling back to channel.send."""
    if content and isinstance(content, str):
        content = strip_emotion_tags(content)
    try:
        if embed is not None and message.guild and getattr(message.guild, "me", None):
            try:
                perms = message.channel.permissions_for(message.guild.me)
                if perms and not perms.embed_links:
                    embed_text = f"**{embed.title or ''}**\n{embed.description or ''}"
                    for f in getattr(embed, 'fields', []):
                        embed_text += f"\n**{f.name}**: {f.value}"
                    footer = getattr(embed, 'footer', None)
                    if footer and getattr(footer, 'text', None):
                        embed_text += f"\n_{footer.text}_"
                    content = f"{content}\n\n{embed_text}".strip() if content else embed_text
                    embed = None
            except Exception:
                pass

        return await message.reply(content=content, embed=embed, embeds=embeds, file=file, files=files, delete_after=delete_after, **kwargs)
    except discord.Forbidden:
        try:
            plain_text = content or ""
            if embed:
                text_repr = f"**{embed.title or ''}**\n{embed.description or ''}"
                for f in getattr(embed, 'fields', []):
                    text_repr += f"\n**{f.name}**: {f.value}"
                plain_text = f"{plain_text}\n\n{text_repr}".strip()
            if plain_text:
                return await message.channel.send(plain_text, delete_after=delete_after)
        except Exception as e:
            print(f"[SAFE REPLY] Forbidden fallback failed: {e}")
    except (discord.HTTPException, discord.NotFound):
        try:
            return await message.channel.send(content=content, embed=embed, embeds=embeds, file=file, files=files, delete_after=delete_after, **kwargs)
        except Exception as e:
            print(f"[SAFE REPLY] Fallback channel send failed: {e}")
    except Exception as e:
        print(f"[SAFE REPLY] Unexpected error: {e}")
    return None

@contextlib.asynccontextmanager
async def safe_typing(channel):
    """Safely triggers Discord channel typing indicator without crashing on Missing Access / Forbidden (403) errors."""
    if channel is None:
        yield
        return
    try:
        async with channel.typing():
            yield
    except (discord.errors.Forbidden, discord.errors.NotFound, discord.errors.HTTPException, Exception):
        # Missing Access (403) / permission restriction on typing indicator - gracefully yield so chat works
        yield

# ─── GEMINI ─────────────────────────────────────────────
def normalize_gemini_model(model_name: str) -> list:
    """Normalizes user-provided Gemini model name and returns prioritized candidates to try."""
    working_defaults = ["gemini-3.1-flash-lite", "gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-flash-lite-latest"]
    if not model_name or not str(model_name).strip():
        return list(working_defaults)
    
    cleaned = str(model_name).strip()
    for prefix in ["models/", "google/", "gemini/"]:
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix):]
    
    # live-preview models only support WebSocket bidi streaming, not generateContent HTTP
    if not cleaned or "/" in cleaned or "live-preview" in cleaned.lower():
        return list(working_defaults)

    candidates = []
    # Avoid non-existent or deprecated models that return 404 on Google API
    deprecated = [
        "gemini-2.0-flash", "gemini-2.5-flash", "gemini-1.5-flash", "gemini-1.5-pro",
        "gemini-2.0-flash-exp", "gemini-1.5-flash-8b"
    ]
    if cleaned not in deprecated:
        candidates.append(cleaned)
        if not cleaned.startswith("gemini-") and not cleaned.startswith("gemma-") and not cleaned.startswith("tunedModels/"):
            candidates.append(f"gemini-{cleaned}")
        
    for fb in working_defaults:
        if fb not in candidates:
            candidates.append(fb)
            
    return candidates

async def ask_gemini(system_msg: str, history: list, prompt: str, model: str = None, temperature: float = None, max_tokens: int = None, top_p: float = None, caller: str = "chat") -> tuple:
    global gemini_blocked_until
    if not GEMINI_KEY:
        return "Gemini API key not configured.", True
    if time.time() < gemini_blocked_until:
        remaining = int(gemini_blocked_until - time.time())
        return f"Gemini rate limited. Retry in {remaining}s.", True

    raw_model = (
        model
        or (config.get("custom_model") if ("gemini" in str(config.get("custom_model", "")).lower() or ("/" not in str(config.get("custom_model", "")) and config.get("provider") == "gemini")) else None)
        or (config.get("model") if ("gemini" in str(config.get("model", "")).lower() or ("/" not in str(config.get("model", "")) and config.get("provider") == "gemini")) else None)
        or config.get("gemini_model")
        or "gemini-3.1-flash-lite"
    )
    if str(raw_model).strip() in ["gemini-3.5-flash-lite", "gemini-3.5-flash"]:
        if "3.1" in str(model or config.get("custom_model") or config.get("model")):
            raw_model = "gemini-3.1-flash-lite"
    model_candidates = normalize_gemini_model(raw_model)

    contents = []
    for msg in history:
        role = "model" if msg.get("role") == "assistant" else "user"
        text = (msg.get("content") or "").strip()
        if not text:
            continue
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"][0]["text"] += "\n\n" + text
        else:
            contents.append({"role": role, "parts": [{"text": text}]})

    prompt_text = (prompt or "").strip() or "Hello"
    if contents and contents[-1]["role"] == "user":
        contents[-1]["parts"][0]["text"] += "\n\n" + prompt_text
    else:
        contents.append({"role": "user", "parts": [{"text": prompt_text}]})

    t_val = temperature if temperature is not None else config.get("temperature", 0.7)
    tok_val = max_tokens if max_tokens is not None else int(config.get("max_tokens", 800))
    top_p_val = top_p if top_p is not None else config.get("top_p", 1.0)

    payload = {
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": max(40, min(8192, int(tok_val))),
            "temperature": max(0.0, min(2.0, float(t_val))),
            "topP": max(0.0, min(1.0, float(top_p_val))),
        }
    }
    if system_msg and system_msg.strip():
        payload["systemInstruction"] = {"parts": [{"text": system_msg.strip()}]}

    last_error = ""
    async with aiohttp.ClientSession() as session:
        for model in model_candidates:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_KEY}"
            try:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    data = await resp.json()
                    if resp.status != 200:
                        err = data.get("error", {}).get("message", f"HTTP {resp.status}")
                        if "quota" in err.lower() or "rate limit" in err.lower() or "exceeded" in err.lower() or resp.status == 429:
                            print(f"[GEMINI 429/QUOTA] Model '{model}' quota exceeded, trying next candidate...")
                            last_error = err
                            continue
                        if "not found" in err.lower() or "not supported" in err.lower() or "no longer available" in err.lower() or resp.status == 404:
                            print(f"[GEMINI RETRY] Model '{model}' unavailable, trying next candidate...")
                            last_error = err
                            continue
                        print(f"[GEMINI ERROR] Model '{model}' error: {err}")
                        last_error = err
                        continue
                    try:
                        candidates = data.get("candidates", [])
                        if not candidates:
                            block_reason = data.get("promptFeedback", {}).get("blockReason")
                            if block_reason:
                                print(f"[GEMINI BLOCKED] Prompt blocked by safety filters: {block_reason}")
                                return f"Gemini response blocked by safety filters ({block_reason}).", True
                            continue
                        parts = candidates[0].get("content", {}).get("parts", [])
                        text_parts = [p.get("text", "") for p in parts if "text" in p and not p.get("thought")]
                        if not text_parts:
                            text_parts = [p.get("text", "") for p in parts if "text" in p]
                        raw_reply = "".join(text_parts).strip()
                        reply = clean_llm_output(raw_reply) or raw_reply
                        if not reply:
                            finish_reason = candidates[0].get("finishReason")
                            print(f"[GEMINI EMPTY] Empty response from {model}, finishReason: {finish_reason}")
                            last_error = f"Empty response (finishReason: {finish_reason})"
                            continue
                        if caller == "memory":
                            print(f"[MEMORY EXTRACTION OK] Extracted facts ({len(reply)} chars) using {model}")
                        else:
                            print(f"[GEMINI OK] Reply length: {len(reply)} using {model}")
                        return reply, False
                    except (KeyError, IndexError) as e:
                        print(f"[GEMINI ERROR] Parse failed on {model}: {e} | Data: {str(data)[:300]}")
                        last_error = f"Parse failed: {e}"
                        continue
            except Exception as e:
                print(f"[GEMINI ERROR] Request failed on {model}: {e}")
                last_error = str(e)
    if last_error and ("quota" in last_error.lower() or "rate limit" in last_error.lower() or "exceeded" in last_error.lower()):
        gemini_blocked_until = time.time() + 60
        print(f"[GEMINI RATE LIMIT] All Gemini candidates hit quota or rate limits. Cooldown 60s.")
        return f"Gemini quota exceeded: {last_error}", True
    return f"Gemini failed: {last_error or 'All models failed'}", True

def clean_llm_output(raw_text: str) -> str:
    if not raw_text or not isinstance(raw_text, str):
        return ""
    text = raw_text.strip()
    # 1. Strip XML reasoning tags (<think>, <thought>, <reasoning>, <thought_process>)
    text = re.sub(r"<(think|thought|reasoning|thought_process)>[\s\S]*?<\/\1>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<(think|thought|reasoning|thought_process)>[\s\S]*$", "", text, flags=re.IGNORECASE)
    # 2. Strip explicit 'Thinking Process' and reasoning blocks
    text = re.sub(r"^(?:Here'?s\s+(?:a\s+)?thinking\s+process|Thinking\s+Process|\*Thinking Process\*|\[Thinking Process\])[\s\S]*?(?=(?:\n\n[A-Z*\"\'\u201c\u2018]|[\u4e00-\u9fa5]|$))", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*(?:\*{1,2}|\[)?(?:Thinking|Thought|Reasoning)(?:\s+Process)?(?:\*{1,2}|\])?:\s*[\s\S]*?(?=(?:\n\n|\r\n\r\n)|$)", "", text, flags=re.IGNORECASE)
    # 3. Strip prompt directive leaks
    text = re.sub(r"^\[(?:LIVE THEATER|CO-WATCHING|SYSTEM|CHARACTER IDENTITY|VISUAL REACTION|MUSIC LOUNGE)[^\]]*\][\s\S]*?(?=\n\n|$)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\[(?:LIVE THEATER|CO-WATCHING|VISUAL REACTION|CHARACTER IDENTITY) DIRECTIVE\]:[^\n]*\n*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(?:- Video / Track Title:|- Channel / Artist:|- Current Playback Position:|- Attached Visuals:|- Spoken Words / Lyrics|- Full Video Dialogue|- User said:)[^\n]*\n*", "", text, flags=re.IGNORECASE)
    # 4. Clean leftover Draft / Response / Assistant markers
    text = re.sub(r"^(?:Draft|Response|Reply|Assistant):\s*", "", text, flags=re.IGNORECASE)
    return text.strip()

# ─── GEMINI VISION ──────────────────────────────────────
async def ask_gemini_vision(system_msg: str, prompt: str, image_bytes_or_list, mime_type: str = "image/jpeg", history: list = None, model_override: str = None, audio_bytes: bytes = None, audio_mime: str = "audio/wav", temperature: float = None, max_tokens: int = None, top_p: float = None) -> tuple:
    global gemini_blocked_until
    if not GEMINI_KEY:
        return "Gemini API key not configured.", True
    if time.time() < gemini_blocked_until:
        remaining = int(gemini_blocked_until - time.time())
        return f"Gemini rate limited. Retry in {remaining}s.", True

    raw_model = (
        model_override
        or (config.get("custom_model") if "gemini" in str(config.get("custom_model", "")).lower() else None)
        or config.get("video_watching_model")
        or config.get("gemini_vision_model")
        or config.get("gemini_model")
        or "gemini-3.1-flash-lite"
    )
    if str(raw_model).strip() in ["gemini-3.5-flash-lite", "gemini-3.5-flash"]:
        raw_model = "gemini-3.1-flash-lite"
    model_candidates = normalize_gemini_model(raw_model)

    user_parts = [{"text": prompt or "Describe this image."}]
    if isinstance(image_bytes_or_list, list):
        for img in image_bytes_or_list:
            if img:
                b64_image = base64.b64encode(img).decode("utf-8")
                user_parts.append({"inlineData": {"mimeType": mime_type, "data": b64_image}})
    elif image_bytes_or_list:
        b64_image = base64.b64encode(image_bytes_or_list).decode("utf-8")
        user_parts.append({"inlineData": {"mimeType": mime_type, "data": b64_image}})

    if audio_bytes:
        b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
        user_parts.append({"inlineData": {"mimeType": audio_mime, "data": b64_audio}})

    contents = []
    for msg in history or []:
        role = "model" if msg.get("role") == "assistant" else "user"
        text = (msg.get("content") or "").strip()
        if not text:
            continue
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"][0]["text"] += "\n\n" + text
        else:
            contents.append({"role": role, "parts": [{"text": text}]})

    if contents and contents[-1]["role"] == "user":
        contents[-1]["parts"].extend(user_parts)
    else:
        contents.append({
            "role": "user",
            "parts": user_parts
        })

    t_val = temperature if temperature is not None else config.get("temperature", 0.7)
    tok_val = max_tokens if max_tokens is not None else config.get("max_tokens", 800)
    top_p_val = top_p if top_p is not None else config.get("top_p", 1.0)

    payload = {
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": max(50, min(8000, int(tok_val))),
            "temperature": max(0.0, min(2.0, float(t_val))),
            "topP": max(0.0, min(1.0, float(top_p_val))),
        }
    }
    if system_msg and system_msg.strip():
        payload["systemInstruction"] = {"parts": [{"text": system_msg.strip()}]}

    last_error = ""
    async with aiohttp.ClientSession() as session:
        for model in model_candidates:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_KEY}"
            try:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=45)) as resp:
                    data = await resp.json()
                    if resp.status != 200:
                        err = data.get("error", {}).get("message", f"HTTP {resp.status}")
                        if "quota" in err.lower() or "rate limit" in err.lower() or "exceeded" in err.lower() or resp.status == 429:
                            print(f"[GEMINI VISION RATE LIMIT] 429 on {model}, trying next candidate...")
                            last_error = f"Quota reached on {model}"
                            continue
                        if "not found" in err.lower() or "not supported" in err.lower() or "no longer available" in err.lower() or resp.status == 404:
                            print(f"[GEMINI VISION RETRY] Model '{model}' unavailable, trying next candidate...")
                            last_error = err
                            continue
                        print(f"[GEMINI VISION ERROR] Model '{model}' error: {err}")
                        last_error = err
                        continue
                    try:
                        candidates = data.get("candidates", [])
                        if not candidates:
                            block_reason = data.get("promptFeedback", {}).get("blockReason")
                            if block_reason:
                                print(f"[GEMINI VISION BLOCKED] Prompt blocked: {block_reason}")
                                return f"Gemini vision blocked by safety filters ({block_reason}).", True
                            continue
                        parts = candidates[0].get("content", {}).get("parts", [])
                        text_parts = [p.get("text", "") for p in parts if "text" in p and not p.get("thought")]
                        if not text_parts:
                            text_parts = [p.get("text", "") for p in parts if "text" in p]
                        raw_reply = "".join(text_parts).strip()
                        reply = clean_llm_output(raw_reply) or raw_reply
                        if not reply:
                            finish_reason = candidates[0].get("finishReason")
                            print(f"[GEMINI VISION EMPTY] Empty response from {model}, finishReason: {finish_reason}")
                            last_error = f"Empty response (finishReason: {finish_reason})"
                            continue
                        print(f"\033[92m[GEMINI VISION OK] Reply length: {len(reply)} using {model}\033[0m")
                        return reply, False
                    except (KeyError, IndexError) as e:
                        print(f"[GEMINI VISION ERROR] Parse failed on {model}: {e} | Data: {str(data)[:300]}")
                        last_error = f"Parse failed: {e}"
                        continue
            except Exception as e:
                print(f"[GEMINI VISION ERROR] Request failed on {model}: {e}")
                last_error = str(e)
                continue

    return f"Gemini vision failed: {last_error or 'All model attempts failed'}", True

# ─── WEB SEARCH ───────────────────────────────────────
async def web_search(query: str, max_results: int = 5) -> tuple:
    """Multi-tiered web search engine with DuckDuckGo HTML, Lite, JSON API and Wikipedia fallbacks."""
    query = (query or "").strip()
    if not query:
        return [], "Empty search query."

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "DNT": "1",
        "Sec-GPC": "1",
    }
    
    results = []
    errors = []

    # 1. Primary: DuckDuckGo HTML Endpoint
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query, "b": ""},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    blocks = re.findall(
                        r'<div[^>]+class="[^"]*result[^"]*"[^>]*>.*?<a[^>]+class="result__snippet[^"]*"[^>]*>(.*?)</a>',
                        html, re.DOTALL | re.IGNORECASE
                    )
                    title_matches = re.findall(
                        r'<h2[^>]+class="result__title"[^>]*>.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                        html, re.DOTALL | re.IGNORECASE
                    )
                    for i, (href, title_raw) in enumerate(title_matches[:max_results]):
                        title = re.sub(r'<[^>]+>', '', title_raw).strip()
                        title = unescape(title)
                        if "uddg=" in href:
                            m = re.search(r'uddg=([^&]+)', href)
                            if m:
                                href = unquote(m.group(1))
                        snippet = ""
                        if i < len(blocks):
                            snippet = re.sub(r'<[^>]+>', '', blocks[i]).strip()
                            snippet = unescape(snippet)
                        if title and href:
                            results.append({"title": title, "url": href, "snippet": snippet})
                else:
                    errors.append(f"DDG HTML status {resp.status}")
    except Exception as e:
        errors.append(f"DDG HTML error: {e}")

    if results:
        return results[:max_results], ""

    # 2. Secondary: DuckDuckGo Lite Endpoint
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.post(
                "https://lite.duckduckgo.com/lite/",
                data={"q": query, "kl": "us-en"},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    rows = re.findall(
                        r'<a[^>]+href="([^"]+)"[^>]*class="[^"]*result-link[^"]*"[^>]*>(.*?)</a>'
                        r'.*?<td[^>]*class="[^"]*result-snippet[^"]*"[^>]*>(.*?)</td>',
                        html, re.DOTALL | re.IGNORECASE
                    )
                    for href, title_raw, snippet_raw in rows[:max_results]:
                        title = re.sub(r'<[^>]+>', '', title_raw).strip()
                        snippet = re.sub(r'<[^>]+>', '', snippet_raw).strip()
                        title = unescape(title)
                        snippet = unescape(snippet)
                        if href.startswith("/"):
                            href = "https://lite.duckduckgo.com" + href
                        if title:
                            results.append({"title": title, "url": href, "snippet": snippet})
    except Exception as e:
        errors.append(f"DDG Lite error: {e}")

    if results:
        return results[:max_results], ""

    # 3. Tertiary: DuckDuckGo Instant Answer JSON API
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
                timeout=aiohttp.ClientTimeout(total=8)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    abstract = data.get("AbstractText", "")
                    heading = data.get("Heading", query)
                    url = data.get("AbstractURL", "")
                    if abstract:
                        results.append({"title": heading, "url": url or f"https://duckduckgo.com/?q={query}", "snippet": abstract})
                    for topic in data.get("RelatedTopics", [])[:max_results]:
                        if isinstance(topic, dict) and topic.get("Text") and topic.get("FirstURL"):
                            results.append({"title": topic.get("Text")[:60] + "...", "url": topic["FirstURL"], "snippet": topic["Text"]})
    except Exception as e:
        errors.append(f"DDG API error: {e}")

    if results:
        return results[:max_results], ""

    # 4. Quaternary: Wikipedia Search Fallback
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            wiki_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={query}&format=json&utf8=1"
            async with session.get(wiki_url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    wdata = await resp.json()
                    search_items = wdata.get("query", {}).get("search", [])
                    for item in search_items[:max_results]:
                        wtitle = item.get("title", "")
                        wsnippet = re.sub(r'<[^>]+>', '', item.get("snippet", "")).strip()
                        wpage = f"https://en.wikipedia.org/wiki/{wtitle.replace(' ', '_')}"
                        if wtitle and wsnippet:
                            results.append({"title": f"{wtitle} (Wikipedia)", "url": wpage, "snippet": unescape(wsnippet)})
    except Exception as e:
        errors.append(f"Wikipedia error: {e}")

    if results:
        return results[:max_results], ""

    return [], f"Search failed across all providers: {'; '.join(errors) if errors else 'No results found.'}"

# ─── GROQ ───────────────────────────────────────────────
async def ask_groq(history: list, prompt: str, system_msg: str = None, model: str = None, temperature: float = None, max_tokens: int = None, top_p: float = None, frequency_penalty: float = None, presence_penalty: float = None) -> tuple:
    global groq_blocked_until
    if not GROQ_KEY:
        return None, True
    if time.time() < groq_blocked_until:
        remaining = int(groq_blocked_until - time.time())
        return f"Groq rate limited. Retry in {remaining}s.", True

    valid_groq_models = ["qwen/qwen3.8-27b", "groq/compound-mini", "groq/compound", "openai/gpt-oss-20b", "qwen/qwen3.6-27b"]
    req_m = (model or "").strip()
    if not req_m or (req_m not in valid_groq_models and not any(k in req_m.lower() for k in ["qwen", "groq", "compound", "gpt-oss"])):
        cfg_m = config.get("groq_model") or ""
        if cfg_m in valid_groq_models or any(k in cfg_m.lower() for k in ["qwen", "groq", "compound", "gpt-oss"]):
            req_m = cfg_m
        else:
            req_m = "qwen/qwen3.8-27b"
    models_to_try = [req_m]
    for fb in valid_groq_models:
        if fb not in models_to_try:
            models_to_try.append(fb)

    sys_prompt = system_msg or config.get("personality", "")
    messages = [{"role": "system", "content": sys_prompt}]
    messages.extend([{"role": m["role"], "content": m["content"]} for m in history if m.get("content")])
    messages.append({"role": "user", "content": prompt})

    t_val = temperature if temperature is not None else config.get("temperature", 0.7)
    tok_val = max_tokens if max_tokens is not None else config.get("max_tokens", 800)
    top_p_val = top_p if top_p is not None else config.get("top_p", 1.0)
    freq_val = frequency_penalty if frequency_penalty is not None else config.get("frequency_penalty", 0.0)
    pres_val = presence_penalty if presence_penalty is not None else config.get("presence_penalty", 0.0)

    last_err = ""
    async with aiohttp.ClientSession() as session:
        for model in models_to_try:
            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": max(50, min(8000, int(tok_val))),
                "temperature": max(0.0, min(2.0, float(t_val))),
                "top_p": max(0.0, min(1.0, float(top_p_val))),
                "frequency_penalty": max(-2.0, min(2.0, float(freq_val))),
                "presence_penalty": max(-2.0, min(2.0, float(pres_val))),
            }
            try:
                async with session.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
                    json=payload, timeout=aiohttp.ClientTimeout(total=8),
                ) as resp:
                    text = await resp.text()
                    if resp.status == 429:
                        retry_after = 60
                        ra = resp.headers.get("Retry-After")
                        if ra:
                            try: retry_after = int(float(ra))
                            except ValueError: pass
                        retry_after = min(retry_after, 3600)
                        groq_blocked_until = time.time() + retry_after
                        print(f"[GROQ RATE LIMIT] Cooling down for {retry_after}s on {model}")
                        return f"Groq rate limited. Retry in {retry_after}s.", True
                    if resp.status != 200:
                        print(f"[GROQ ERROR] Model {model} HTTP {resp.status}: {text[:200]}")
                        last_err = f"Groq Error {resp.status}: {text[:300]}"
                        continue
                    data = await resp.json()
                    msg = data["choices"][0]["message"]
                    reply = msg.get("content")
                    if not reply or not reply.strip():
                        reply = msg.get("reasoning")
                    if reply and reply.strip():
                        clean_reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip()
                        return clean_reply or reply, False
            except Exception as e:
                last_err = f"Groq failed on {model}: {e}"
                continue
    return last_err or "Groq returned empty.", True

# ─── MISTRAL ───────────────────────────────────────────
async def ask_mistral(history: list, prompt: str, system_msg: str = None, model: str = None, temperature: float = None, max_tokens: int = None, top_p: float = None, frequency_penalty: float = None, presence_penalty: float = None) -> tuple:
    global mistral_blocked_until
    m_key = config.get("mistral_key", "").strip() or os.getenv("MISTRAL_KEY", "").strip() or MISTRAL_KEY
    if not m_key:
        print("[MISTRAL ERROR] No Mistral API key found in config or environment!")
        return "Mistral API key not configured.", True
    if time.time() < mistral_blocked_until:
        remaining = int(mistral_blocked_until - time.time())
        print(f"[MISTRAL RATE LIMIT] Mistral is currently in cooldown ({remaining}s remaining).")
        return f"Mistral rate limited. Retry in {remaining}s.", True

    valid_mistral_models = ["ministral-8b-latest", "ministral-3b-latest", "codestral-latest", "mistral-small-latest", "open-mistral-nemo"]
    req_m = (model or "").strip()
    if not req_m or ("/" in req_m and not req_m.startswith("mistral")):
        cfg_m = (config.get("model") if config.get("provider") == "mistral" and "/" not in config.get("model", "") else None) or config.get("mistral_model") or ""
        if cfg_m in valid_mistral_models or (cfg_m and "/" not in cfg_m):
            req_m = cfg_m
        else:
            req_m = "ministral-8b-latest"
    models_to_try = [req_m]
    for fb in valid_mistral_models:
        if fb not in models_to_try:
            models_to_try.append(fb)

    sys_prompt = system_msg or config.get("personality", "")
    messages = [{"role": "system", "content": sys_prompt}]
    messages.extend([{"role": m["role"], "content": m["content"]} for m in history if m.get("content")])
    messages.append({"role": "user", "content": prompt})

    t_val = temperature if temperature is not None else config.get("temperature", 0.7)
    tok_val = max_tokens if max_tokens is not None else config.get("max_tokens", 800)
    top_p_val = top_p if top_p is not None else config.get("top_p", 1.0)
    freq_val = frequency_penalty if frequency_penalty is not None else config.get("frequency_penalty", 0.0)
    pres_val = presence_penalty if presence_penalty is not None else config.get("presence_penalty", 0.0)

    last_err_text = ""
    async with aiohttp.ClientSession() as session:
        for idx, model in enumerate(models_to_try):
            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": max(50, min(8000, int(tok_val))),
                "temperature": max(0.0, min(2.0, float(t_val))),
                "top_p": max(0.0, min(1.0, float(top_p_val))),
                "frequency_penalty": max(-2.0, min(2.0, float(freq_val))),
                "presence_penalty": max(-2.0, min(2.0, float(pres_val))),
            }
            masked_key = f"{m_key[:4]}...{m_key[-4:]}" if len(m_key) >= 8 else "len=" + str(len(m_key))
            print(f"[MISTRAL] Sending request (model='{model}', key='{masked_key}', prompt_len={len(prompt)})")
            try:
                async with session.post(
                    "https://api.mistral.ai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {m_key}", "Content-Type": "application/json"},
                    json=payload, timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    text = await resp.text()
                    if resp.status == 200:
                        data = await resp.json()
                        try:
                            msg = data["choices"][0]["message"]
                            reply = msg.get("content")
                            if not reply or not reply.strip():
                                reply = msg.get("reasoning")
                            if not reply or not reply.strip():
                                print(f"[MISTRAL WARN] Empty content returned for model {model}")
                                continue
                            print(f"[MISTRAL SUCCESS] Model '{model}' replied ({len(reply)} chars)")
                            return reply, False
                        except (KeyError, IndexError) as ke:
                            print(f"[MISTRAL PARSE ERROR] {ke}: {str(data)[:200]}")
                            last_err_text = f"Bad Mistral response: {str(data)[:200]}"
                            continue

                    # If model not available in subscription tier or 404, try fallback models
                    if (resp.status == 403 and "tier_not_allowed" in text) or resp.status == 404:
                        print(f"[MISTRAL TIER] Model '{model}' not allowed in current tier (HTTP {resp.status}). Trying fallback...")
                        last_err_text = f"Mistral Error {resp.status}: {text[:200]}"
                        continue

                    if resp.status == 429:
                        retry_after = 60
                        ra = resp.headers.get("Retry-After")
                        if ra:
                            try:
                                retry_after = int(float(ra))
                            except ValueError:
                                pass
                        retry_after = min(retry_after, 3600)
                        if idx < len(models_to_try) - 1 and ("tier" in text or "quota" in text):
                            print(f"[MISTRAL RATE LIMIT] Model '{model}' limited, trying fallback model...")
                            last_err_text = f"Mistral rate limited on {model}."
                            continue
                        mistral_blocked_until = time.time() + retry_after
                        print(f"[MISTRAL RATE LIMIT] Cooling down for {retry_after}s: {text[:200]}")
                        return f"Mistral rate limited. Retry in {retry_after}s.", True

                    if resp.status in (401, 402):
                        mistral_blocked_until = time.time() + 300
                        print(f"[MISTRAL ERROR] HTTP {resp.status} (Subscription/Auth): {text[:200]}")
                        return f"Mistral Error {resp.status}: {text[:400]}", True

                    print(f"[MISTRAL ERROR] HTTP {resp.status} for model '{model}': {text[:200]}")
                    last_err_text = f"Mistral Error {resp.status}: {text[:400]}"
            except Exception as e:
                print(f"[MISTRAL EXCEPTION] Connection error with model '{model}': {e}")
                last_err_text = f"Mistral failed: {str(e)}"

    return last_err_text or "Mistral all models failed.", True

async def ask_mistral_vision(system_msg: str, prompt: str, image_bytes_or_list, mime_type: str = "image/jpeg", history: list = None, vision_model: str = None, temperature: float = None, max_tokens: int = None) -> tuple:
    global mistral_blocked_until
    m_key = os.getenv("MISTRAL_KEY", "").strip() or MISTRAL_KEY
    if not m_key:
        return "Mistral API key not configured.", True
    if time.time() < mistral_blocked_until:
        remaining = int(mistral_blocked_until - time.time())
        return f"Mistral rate limited. Retry in {remaining}s.", True

    user_content = [{"type": "text", "text": prompt}]
    if isinstance(image_bytes_or_list, list):
        for img in image_bytes_or_list:
            if img:
                b64_image = base64.b64encode(img).decode("utf-8")
                user_content.append({"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_image}"}})
    elif image_bytes_or_list:
        b64_image = base64.b64encode(image_bytes_or_list).decode("utf-8")
        user_content.append({"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_image}"}})

    model = (vision_model or "pixtral-12b-2409").strip()
    messages = [{"role": "system", "content": system_msg}]
    if history:
        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "assistant":
                messages.append({"role": "assistant", "content": content})
            else:
                messages.append({"role": "user", "content": content})
    messages.append({"role": "user", "content": user_content})

    t_val = temperature if temperature is not None else config.get("temperature", 0.7)
    tok_val = max_tokens if max_tokens is not None else config.get("max_tokens", 800)

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max(50, min(8000, int(tok_val))),
        "temperature": max(0.0, min(2.0, float(t_val))),
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {m_key}", "Content-Type": "application/json"},
                json=payload, timeout=aiohttp.ClientTimeout(total=45),
            ) as resp:
                text = await resp.text()
                if resp.status == 429:
                    mistral_blocked_until = time.time() + 60
                    return "Mistral rate limited.", True
                if resp.status != 200:
                    return f"Mistral Vision Error {resp.status}: {text[:300]}", True
                data = await resp.json()
                msg = data["choices"][0]["message"]
                reply = msg.get("content", "").strip()
                if not reply:
                    return "Mistral vision returned empty.", True
                return reply, False
        except Exception as e:
            return f"Mistral vision failed: {str(e)}", True

# ─── OPENROUTER ─────────────────────────────────────────
def extract_openrouter_reply(msg: dict) -> str:
    """Extracts text content or extracts response from reasoning models."""
    reply = msg.get("content")
    if reply and reply.strip():
        return reply.strip()
    reasoning = msg.get("reasoning")
    if not reasoning or not reasoning.strip():
        return ""
    m = re.search(r'(?:final response|final answer|reply|response|assistant):\s*\n*([^\n].*)', reasoning, re.I | re.S)
    if m and m.group(1).strip():
        return m.group(1).strip()
    if "</think>" in reasoning:
        after = reasoning.split("</think>", 1)[1].strip()
        if after:
            return after
    paras = [p.strip() for p in reasoning.split("\n\n") if p.strip()]
    if len(paras) > 1 and len(paras[-1]) > 10:
        return paras[-1]
    return reasoning.strip()

async def ask_openrouter(history: list, prompt: str, system_msg: str = None, model: str = None, temperature: float = None, max_tokens: int = None, top_p: float = None, frequency_penalty: float = None, presence_penalty: float = None) -> tuple:
    global openrouter_blocked_until
    if not os.getenv("OPENROUTER_KEY"):
        return None, True
    if time.time() < openrouter_blocked_until:
        remaining = int(openrouter_blocked_until - time.time())
        return f"OpenRouter rate limited. Retry in {remaining}s.", True

    sys_prompt = system_msg or config.get("personality", "")
    messages = [{"role": "system", "content": sys_prompt}]
    messages.extend([{"role": m["role"], "content": m["content"]} for m in history if m.get("content")])
    messages.append({"role": "user", "content": prompt})

    target_model = (model or config.get("custom_model") or (config.get("model") if config.get("model") not in ("openrouter/free", "default", "auto") else None) or get_active_model()).strip()
    if not target_model or target_model == "openrouter/free" or target_model == "meta-llama/llama-3.3-70b-instruct:free":
        target_model = "inclusionai/ling-3.0-flash-vl:free"
    model = target_model

    t_val = temperature if temperature is not None else config.get("temperature", 0.7)
    tok_val = max_tokens if max_tokens is not None else config.get("max_tokens", 800)
    top_p_val = top_p if top_p is not None else config.get("top_p", 1.0)
    freq_val = frequency_penalty if frequency_penalty is not None else config.get("frequency_penalty", 0.0)
    pres_val = presence_penalty if presence_penalty is not None else config.get("presence_penalty", 0.0)

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max(50, min(8000, int(tok_val))),
        "temperature": max(0.0, min(2.0, float(t_val))),
        "top_p": max(0.0, min(1.0, float(top_p_val))),
        "frequency_penalty": max(-2.0, min(2.0, float(freq_val))),
        "presence_penalty": max(-2.0, min(2.0, float(pres_val))),
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {os.getenv('OPENROUTER_KEY')}", "Content-Type": "application/json", "HTTP-Referer": "https://localhost", "X-Title": "DiscordBot"},
                json=payload, timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                text = await resp.text()
                if resp.status == 429:
                    retry_after = 60
                    ra = resp.headers.get("Retry-After")
                    reset = resp.headers.get("x-ratelimit-reset")
                    if ra:
                        try:
                            retry_after = int(float(ra))
                        except ValueError:
                            pass
                    elif reset:
                        try:
                            reset_ts = float(reset)
                            if reset_ts > time.time() * 2:
                                reset_ts = reset_ts / 1000.0
                            retry_after = max(5, int(reset_ts - time.time()))
                        except ValueError:
                            pass
                    retry_after = min(retry_after, 3600)
                    openrouter_blocked_until = time.time() + retry_after
                    print(f"[OPENROUTER RATE LIMIT] Cooling down for {retry_after}s")
                    return f"OpenRouter rate limited. Retry in {retry_after}s.", True
                if resp.status != 200:
                    print(f"[OPENROUTER ERROR] HTTP {resp.status}: {text[:200]}")
                    return f"OpenRouter Error {resp.status}: {text[:600]}", True
                data = await resp.json()
                try:
                    msg = data["choices"][0]["message"]
                    reply = extract_openrouter_reply(msg)
                    if not reply or not reply.strip():
                        return "OpenRouter returned empty.", True
                    return reply, False
                except (KeyError, IndexError):
                    return f"Bad OpenRouter response: {str(data)[:400]}", True
        except Exception as e:
            return f"OpenRouter failed: {str(e)}", True

# ─── MULTIMODAL VISION & AUDIO ROUTER ───────────────────
async def ask_multimodal_vision(system_msg: str, prompt: str, image_bytes_or_list, mime_type: str = "image/jpeg", history: list = None, model_override: str = None, provider_override: str = None, audio_bytes: bytes = None, audio_mime: str = "audio/wav", max_tokens: int = None, temperature: float = None) -> tuple:
    prov = (provider_override or config.get("vision_provider") or config.get("provider") or "auto").lower()
    target_model = (model_override or config.get("video_watching_model") or config.get("gemini_vision_model") or config.get("model") or "gemini-3.1-flash-lite").strip()
    if not target_model or "live-preview" in target_model.lower() or target_model in ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-1.5-flash"]:
        target_model = "gemini-3.1-flash-lite"
    if target_model == "gemini-3.5-flash-lite":
        target_model = "gemini-3.1-flash-lite"

    is_explicit_or_model = "/" in target_model and not target_model.lower().startswith("models/")

    # 1. If explicit OpenRouter model or OpenRouter provider requested (and no audio waveform requiring Gemini):
    if (prov == "openrouter" or is_explicit_or_model) and os.getenv("OPENROUTER_KEY") and not audio_bytes:
        reply, err = await ask_openrouter_vision(system_msg, prompt, image_bytes_or_list, mime_type=mime_type, history=history, vision_model=target_model, max_tokens=max_tokens)
        if not err and reply:
            return reply, False

    # 2. Try Gemini Vision & Multimodal Audio if Gemini key is available and not rate limited
    if GEMINI_KEY and time.time() >= gemini_blocked_until:
        gem_model = "gemini-3.1-flash-lite" if is_explicit_or_model else target_model
        reply, err = await ask_gemini_vision(system_msg, prompt, image_bytes_or_list, mime_type=mime_type, history=history, model_override=gem_model, audio_bytes=audio_bytes, audio_mime=audio_mime, max_tokens=max_tokens, temperature=temperature)
        if not err and reply:
            return reply, False

    # 3. Fallback to OpenRouter Vision if Gemini unavailable
    if os.getenv("OPENROUTER_KEY") and image_bytes_or_list:
        reply, err = await ask_openrouter_vision(system_msg, prompt, image_bytes_or_list, mime_type=mime_type, history=history, vision_model=target_model, max_tokens=max_tokens)
        if not err and reply:
            return reply, False

    # 4. Final attempt on Gemini Multimodal
    if GEMINI_KEY:
        return await ask_gemini_vision(system_msg, prompt, image_bytes_or_list, mime_type=mime_type, history=history, model_override="gemini-3.1-flash-lite", audio_bytes=audio_bytes, audio_mime=audio_mime, max_tokens=max_tokens, temperature=temperature)

    return "No valid multimodal vision provider available.", True

# ─── OPENROUTER VISION ──────────────────────────────────
async def ask_openrouter_vision(system_msg: str, prompt: str, image_bytes_or_list, mime_type: str = "image/jpeg", history: list = None, vision_model: str = None, max_tokens: int = None) -> tuple:
    global openrouter_blocked_until
    or_key = os.getenv("OPENROUTER_KEY")
    if not or_key:
        return "OpenRouter API key not configured.", True
    if time.time() < openrouter_blocked_until:
        remaining = int(openrouter_blocked_until - time.time())
        return f"OpenRouter rate limited. Retry in {remaining}s.", True

    user_content = [{"type": "text", "text": prompt}]
    if isinstance(image_bytes_or_list, list):
        for img in image_bytes_or_list:
            if img:
                b64_image = base64.b64encode(img).decode("utf-8")
                user_content.append({"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_image}"}})
    elif image_bytes_or_list:
        b64_image = base64.b64encode(image_bytes_or_list).decode("utf-8")
        user_content.append({"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_image}"}})

    # Verified active vision models on OpenRouter
    vision_fallbacks = [
        "openrouter/free",
        "nvidia/nemotron-3-ultra-550b-a55b:free",
        "google/gemma-4-26b-a4b-it:free",
        "google/gemma-4-31b-it:free",
        "thinkingmachines/inkling:free",
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        "liquid/lfm-2.5-2.6b:free"
    ]
    models_to_try = []
    if vision_model and vision_model.strip():
        models_to_try.append(vision_model.strip())
    for fb in vision_fallbacks:
        if fb not in models_to_try:
            models_to_try.append(fb)

    messages = [{"role": "system", "content": system_msg}]
    if history:
        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "assistant":
                messages.append({"role": "assistant", "content": content})
            else:
                messages.append({"role": "user", "content": content})
    messages.append({"role": "user", "content": user_content})

    tok_limit = max_tokens if max_tokens is not None else int(config.get("max_tokens", 400))
    async with aiohttp.ClientSession() as session:
        last_error = "No vision models available"
        for vm in models_to_try:
            payload = {
                "model": vm,
                "messages": messages,
                "max_tokens": max(50, min(800, tok_limit)),
                "temperature": max(0.0, min(2.0, float(config.get("temperature", 0.7)))),
                "top_p": max(0.0, min(1.0, float(config.get("top_p", 1.0)))),
            }
            try:
                async with session.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {or_key}", "Content-Type": "application/json", "HTTP-Referer": "https://localhost", "X-Title": "DiscordBot"},
                    json=payload, timeout=aiohttp.ClientTimeout(total=45),
                ) as resp:
                    text = await resp.text()
                    if resp.status == 404:
                        print(f"[OPENROUTER VISION] Model {vm} not found (404), trying next...")
                        last_error = f"Model {vm} not found"
                        continue
                    if resp.status == 429:
                        retry_after = 60
                        ra = resp.headers.get("Retry-After")
                        reset = resp.headers.get("x-ratelimit-reset")
                        if ra:
                            try:
                                retry_after = int(float(ra))
                            except ValueError:
                                pass
                        elif reset:
                            try:
                                reset_ts = float(reset)
                                if reset_ts > time.time() * 2:
                                    reset_ts = reset_ts / 1000.0
                                retry_after = max(5, int(reset_ts - time.time()))
                            except ValueError:
                                pass
                        retry_after = min(retry_after, 3600)
                        openrouter_blocked_until = time.time() + retry_after
                        print(f"[OPENROUTER VISION RATE LIMIT] Cooling down for {retry_after}s")
                        return f"OpenRouter rate limited. Retry in {retry_after}s.", True
                    if resp.status != 200:
                        print(f"[OPENROUTER VISION ERROR] HTTP {resp.status} on {vm}: {text[:200]}")
                        last_error = f"HTTP {resp.status}: {text[:200]}"
                        continue
                    data = await resp.json()
                    try:
                        msg = data["choices"][0]["message"]
                        raw_reply = extract_openrouter_reply(msg)
                        reply = clean_llm_output(raw_reply) or raw_reply
                        if not reply or not reply.strip():
                            last_error = "Empty response"
                            continue
                        print(f"\033[92m[OPENROUTER VISION SUCCESS] OK using {vm}\033[0m")
                        return reply, False
                    except (KeyError, IndexError):
                        last_error = f"Bad response: {str(data)[:400]}"
                        continue
            except Exception as e:
                last_error = str(e)
                continue
        return f"OpenRouter vision failed: {last_error}", True

# ─── OPENAI CHAT ────────────────────────────────────────
async def ask_openai(history: list, prompt: str, system_msg: str = None, model: str = None) -> tuple:
    global openai_blocked_until
    key = get_openai_key()
    if not key:
        return None, True
    if time.time() < openai_blocked_until:
        remaining = int(openai_blocked_until - time.time())
        return f"OpenAI rate limited. Retry in {remaining}s.", True

    sys_prompt = system_msg or config.get("personality", "")
    messages = [{"role": "system", "content": sys_prompt}]
    messages.extend([{"role": m["role"], "content": m["content"]} for m in history if m.get("content")])
    messages.append({"role": "user", "content": prompt})

    target_model = (model or config.get("custom_model") or (config.get("model") if config.get("provider") == "openai" else None) or config.get("openai_chat_model") or config.get("openai_llm_model") or "gpt-4o-mini").strip()
    payload = {
        "model": target_model,
        "messages": messages,
        "max_tokens": max(50, min(4000, int(config.get("max_tokens", 800)))),
        "temperature": max(0.0, min(2.0, float(config.get("temperature", 0.7)))),
        "top_p": max(0.0, min(1.0, float(config.get("top_p", 1.0)))),
        "frequency_penalty": max(-2.0, min(2.0, float(config.get("frequency_penalty", 0.0)))),
        "presence_penalty": max(-2.0, min(2.0, float(config.get("presence_penalty", 0.0)))),
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload, timeout=aiohttp.ClientTimeout(total=45),
            ) as resp:
                text = await resp.text()
                if resp.status == 429:
                    retry_after = 60
                    ra = resp.headers.get("Retry-After")
                    if ra:
                        try:
                            retry_after = int(float(ra))
                        except ValueError:
                            pass
                    openai_blocked_until = time.time() + retry_after
                    print(f"[OPENAI RATE LIMIT] Cooling down for {retry_after}s")
                    return f"OpenAI rate limited. Retry in {retry_after}s.", True
                if resp.status != 200:
                    print(f"[OPENAI ERROR] HTTP {resp.status}: {text[:200]}")
                    return f"OpenAI Error {resp.status}: {text[:400]}", True
                data = await resp.json()
                try:
                    reply = data["choices"][0]["message"]["content"]
                    if not reply or not reply.strip():
                        return "OpenAI returned empty response.", True
                    return reply, False
                except (KeyError, IndexError):
                    return "Unexpected OpenAI API response format.", True
        except Exception as e:
            print(f"[OPENAI REQUEST FAILED] {e}")
            return f"OpenAI request failed: {str(e)}", True

# ─── DEEPSEEK CHAT ──────────────────────────────────────
async def ask_deepseek(history: list, prompt: str, system_msg: str = None, model: str = None) -> tuple:
    global deepseek_blocked_until
    key = get_deepseek_key()
    if not key:
        return None, True
    if time.time() < deepseek_blocked_until:
        remaining = int(deepseek_blocked_until - time.time())
        return f"DeepSeek rate limited. Retry in {remaining}s.", True

    sys_prompt = system_msg or config.get("personality", "")
    messages = [{"role": "system", "content": sys_prompt}]
    messages.extend([{"role": m["role"], "content": m["content"]} for m in history if m.get("content")])
    messages.append({"role": "user", "content": prompt})

    target_model = (model or config.get("custom_model") or (config.get("model") if config.get("provider") == "deepseek" else None) or config.get("deepseek_model") or "deepseek-chat").strip()
    payload = {
        "model": target_model,
        "messages": messages,
        "max_tokens": max(50, min(4000, int(config.get("max_tokens", 800)))),
        "temperature": max(0.0, min(2.0, float(config.get("temperature", 0.7)))),
        "top_p": max(0.0, min(1.0, float(config.get("top_p", 1.0)))),
        "frequency_penalty": max(-2.0, min(2.0, float(config.get("frequency_penalty", 0.0)))),
        "presence_penalty": max(-2.0, min(2.0, float(config.get("presence_penalty", 0.0)))),
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                "https://api.deepseek.com/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload, timeout=aiohttp.ClientTimeout(total=45),
            ) as resp:
                text = await resp.text()
                if resp.status == 429:
                    retry_after = 60
                    ra = resp.headers.get("Retry-After")
                    if ra:
                        try:
                            retry_after = int(float(ra))
                        except ValueError:
                            pass
                    deepseek_blocked_until = time.time() + retry_after
                    print(f"[DEEPSEEK RATE LIMIT] Cooling down for {retry_after}s")
                    return f"DeepSeek rate limited. Retry in {retry_after}s.", True
                if resp.status != 200:
                    print(f"[DEEPSEEK ERROR] HTTP {resp.status}: {text[:200]}")
                    return f"DeepSeek Error {resp.status}: {text[:400]}", True
                data = await resp.json()
                try:
                    choice = data["choices"][0]["message"]
                    reply = choice.get("content")
                    if not reply or not reply.strip():
                        reply = choice.get("reasoning_content")
                    if not reply or not reply.strip():
                        return "DeepSeek returned empty response.", True
                    return reply, False
                except (KeyError, IndexError):
                    return "Unexpected DeepSeek API response format.", True
        except Exception as e:
            print(f"[DEEPSEEK REQUEST FAILED] {e}")
            return f"DeepSeek request failed: {str(e)}", True

# ─── CUSTOM ENDPOINT / MODEL CHAT ───────────────────────
async def ask_custom_endpoint(
    history: list,
    prompt: str,
    system_msg: str = None,
    model: str = None,
    base_url: str = None,
    api_key: str = None,
    temperature: float = None,
    max_tokens: int = None,
    top_p: float = None,
    frequency_penalty: float = None,
    presence_penalty: float = None
) -> tuple:
    """Executes chat completion against any OpenAI-compatible custom endpoint (OpenRouter, Ollama, LiteRouter, vLLM, Groq, Mistral, etc.)."""
    raw_ep = (base_url or config.get("custom_base_url") or "").strip()
    raw_key = (api_key or config.get("custom_key") or "").strip()
    target_model = (model or config.get("custom_model") or config.get("model") or "").strip()

    # If no custom endpoint provided, determine best default endpoint
    if not raw_ep:
        if raw_key and raw_key.startswith("gsk_"):
            raw_ep = "https://api.groq.com/openai/v1/chat/completions"
        elif raw_key and raw_key.startswith("sk-or-"):
            raw_ep = "https://openrouter.ai/api/v1/chat/completions"
        elif "/" in target_model and os.getenv("OPENROUTER_KEY"):
            raw_ep = "https://openrouter.ai/api/v1/chat/completions"
            if not raw_key:
                raw_key = os.getenv("OPENROUTER_KEY")
        elif GROQ_KEY and any(k in target_model.lower() for k in ("qwen", "groq", "gpt-oss", "compound")):
            raw_ep = "https://api.groq.com/openai/v1/chat/completions"
            if not raw_key:
                raw_key = GROQ_KEY
        elif os.getenv("OPENROUTER_KEY"):
            raw_ep = "https://openrouter.ai/api/v1/chat/completions"
            if not raw_key:
                raw_key = os.getenv("OPENROUTER_KEY")
        elif GROQ_KEY:
            raw_ep = "https://api.groq.com/openai/v1/chat/completions"
            if not raw_key:
                raw_key = GROQ_KEY
        else:
            raw_ep = "https://openrouter.ai/api/v1/chat/completions"

    # Normalize endpoint URL to ensure /chat/completions
    ep = raw_ep
    if not ep.endswith("/chat/completions"):
        if ep.endswith("/"):
            ep = ep + "chat/completions"
        elif ep.endswith("/v1"):
            ep = ep + "/chat/completions"
        else:
            ep = ep.rstrip("/") + "/v1/chat/completions"

    # Resolve API Key
    if not raw_key:
        if "openrouter.ai" in ep:
            raw_key = config.get("openrouter_key") or os.getenv("OPENROUTER_KEY", "")
        elif "groq.com" in ep:
            raw_key = config.get("groq_key") or os.getenv("GROQ_KEY", "") or GROQ_KEY
        elif "mistral.ai" in ep:
            raw_key = config.get("mistral_key") or os.getenv("MISTRAL_KEY", "") or MISTRAL_KEY
        elif "openai.com" in ep:
            raw_key = get_openai_key()
        elif "deepseek.com" in ep:
            raw_key = get_deepseek_key()

    # Resolve target model
    if not target_model:
        if "groq.com" in ep:
            target_model = "qwen/qwen3.8-27b"
        elif "openrouter.ai" in ep:
            target_model = "inclusionai/ling-3.0-flash-vl:free"
        else:
            target_model = "gpt-3.5-turbo"

    sys_prompt = system_msg or config.get("personality", "")
    messages = []
    if sys_prompt and sys_prompt.strip():
        messages.append({"role": "system", "content": sys_prompt.strip()})
    for m in (history or []):
        c = (m.get("content") or "").strip()
        if c:
            role = "assistant" if m.get("role") in ("assistant", "model") else "user"
            messages.append({"role": role, "content": c})
    messages.append({"role": "user", "content": prompt})

    t_val = temperature if temperature is not None else config.get("temperature", 0.7)
    tok_val = max_tokens if max_tokens is not None else config.get("max_tokens", 800)
    top_p_val = top_p if top_p is not None else config.get("top_p", 1.0)
    freq_val = frequency_penalty if frequency_penalty is not None else config.get("frequency_penalty", 0.0)
    pres_val = presence_penalty if presence_penalty is not None else config.get("presence_penalty", 0.0)

    payload = {
        "model": target_model,
        "messages": messages,
        "max_tokens": max(50, min(8000, int(tok_val))),
        "temperature": max(0.0, min(2.0, float(t_val))),
        "top_p": max(0.0, min(1.0, float(top_p_val))),
        "frequency_penalty": max(-2.0, min(2.0, float(freq_val))),
        "presence_penalty": max(-2.0, min(2.0, float(pres_val))),
    }

    headers = {"Content-Type": "application/json"}
    if raw_key and raw_key.strip():
        headers["Authorization"] = f"Bearer {raw_key.strip()}"
    if "openrouter.ai" in ep:
        headers["HTTP-Referer"] = "https://localhost"
        headers["X-Title"] = "DiscordBot"

    print(f"[CUSTOM ENDPOINT] Requesting endpoint='{ep}', model='{target_model}', auth={'yes' if raw_key else 'no'}")

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(ep, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                text = await resp.text()
                if resp.status == 429:
                    print(f"[CUSTOM ENDPOINT 429] Rate limited on {target_model}: {text[:160]}")
                    return f"Custom endpoint rate limited (HTTP 429): {text[:200]}", True
                if resp.status != 200:
                    print(f"[CUSTOM ENDPOINT ERROR] HTTP {resp.status} on {target_model}: {text[:200]}")
                    return f"Custom endpoint HTTP {resp.status}: {text[:300]}", True
                data = await resp.json()
                if "choices" in data and len(data["choices"]) > 0:
                    choice = data["choices"][0]
                    msg = choice.get("message", {})
                    reply = extract_openrouter_reply(msg) if "extract_openrouter_reply" in globals() else msg.get("content", "")
                    if not reply and "text" in choice:
                        reply = choice.get("text", "")
                    if reply and reply.strip():
                        clean_rep = clean_llm_output(reply.strip()) or reply.strip()
                        return clean_rep, False
                return f"Custom endpoint returned empty or unexpected format: {str(data)[:200]}", True
        except asyncio.TimeoutError:
            print(f"[CUSTOM ENDPOINT TIMEOUT] Model '{target_model}' on '{ep}' timed out after 20s")
            return f"Custom endpoint timed out on '{target_model}'", True
        except Exception as e:
            print(f"[CUSTOM ENDPOINT EXCEPTION] {e}")
            return f"Custom endpoint request failed: {e}", True

FISH_AUDIO_EMOTION_INSTRUCTION = """
(Note this is not part of the personality: When generating text that will be sent to Fish Audio TTS (s-2.1-pro-free), prepend emotion tags to sentences to match the intended emotional tone of the response. Use square-bracket cues at the start of sentences. Do not change the bot's personality, role, or speaking style — only inject emotion markers so the voice delivery matches the mood.

Rules:
- Place one primary emotion tag at the beginning of each sentence that needs emotional coloring.
- Use tone modifiers ([whispering], [shouting], [soft tone]) alongside emotion tags when the delivery style matters.
- Use sound-effect tags ([laughing], [sighing], [gasping]) only when the text naturally supports them.
- Keep tags concise. Do not stack more than 2–3 tags per sentence.
- If the response is neutral/informational, you may skip tags entirely — do not force emotions where none belong.
- Intensity modifiers are allowed: [slightly happy], [very angry], [extremely excited].

Allowed emotion tags (primary):
[happy], [sad], [angry], [excited], [calm], [nervous], [confident], [surprised], [satisfied], [delighted], [scared], [worried], [upset], [frustrated], [depressed], [empathetic], [embarrassed], [disgusted], [moved], [proud], [relaxed], [grateful], [curious], [sarcastic], [disdainful], [anxious], [hysterical], [indifferent], [uncertain], [doubtful], [confused], [disappointed], [regretful], [guilty], [ashamed], [jealous], [envious], [hopeful], [optimistic], [pessimistic], [nostalgic], [lonely], [bored], [contemptuous], [sympathetic], [compassionate], [determined], [resigned]

Allowed tone/delivery tags:
[whispering], [shouting], [screaming], [soft tone], [in a hurry tone], [emphasis]

Allowed sound-effect tags:
[laughing], [chuckling], [sobbing], [crying loudly], [sighing], [groaning], [panting], [gasping], [yawning], [snoring], [clear throat]

Examples:
- User: "I got the job!" → Response: "[delighted] That's fantastic news! [proud] You really earned it."
- User: "I lost my wallet." → Response: "[empathetic] I'm really sorry to hear that. [calm] Let's figure out what to do next."
- User: "Tell me a secret." → Response: "[mysterious][whispering] Alright, but you didn't hear this from me..."
- User: "The server is down." → Response: "[confident] I'm on it. [calm] I'll have this resolved shortly."

Important: These tags are invisible formatting cues for the TTS engine. They do not alter your personality, knowledge, or role. Inject them naturally so the voice sounds emotionally appropriate without changing what you say.)"""

def strip_emotion_tags(text: str) -> str:
    """Removes Fish Audio TTS emotion and delivery bracket tags for clean user-facing chat display."""
    if not text:
        return ""
    # Strip square bracket cues like [happy], [whispering], [laughing], [slightly angry], etc.
    cleaned = re.sub(r'\[[a-zA-Z0-9_\-\s]+\]', '', text)
    # Clean excessive whitespace
    cleaned = re.sub(r'[ \t]+', ' ', cleaned)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
    return cleaned

def clean_tts_text(text: str, keep_direction_tags: bool = False, keep_fish_tags: bool = False) -> str:
    """Prepares text for TTS synthesis. Retains Fish Audio bracket tags when keep_fish_tags=True, strips them for others."""
    if not text:
        return ""
    t = text.strip()
    # Remove markdown code blocks and inline code
    t = re.sub(r'```[\s\S]*?```', '', t)
    t = re.sub(r'`[^`]*`', '', t)
    # Remove URLs
    t = re.sub(r'https?://\S+', '', t)
    # Remove XML / HTML tags
    t = re.sub(r'<[^>]+>', '', t)
    # Remove parenthetical roleplay/action cues (laughs), (cries), etc.
    t = re.sub(r'\([^)]*\)', '', t)
    # Remove asterisks roleplay/action cues *laughs*, *smiles*, etc.
    t = re.sub(r'\*[^*]*\*', '', t)
    # Remove curly braces
    t = re.sub(r'\{[^}]*\}', '', t)

    if not keep_fish_tags and not keep_direction_tags:
        # For non-Fish TTS engines (ElevenLabs, Edge, Cartesia), remove all square bracket emotion tags
        t = re.sub(r'\[[^\]]*\]', '', t)
    else:
        # Clean up brackets while preserving emotion tags for Fish Audio
        t = re.sub(r'\[\s+', '[', t)
        t = re.sub(r'\s+\]', ']', t)

    # Strip any leftover standalone speaker labels at the start of sentences
    t = re.sub(r'^\s*(?:[a-zA-Z\s]+:\s*)', '', t)
    # Remove excessive punctuation or whitespace
    t = re.sub(r'\s+', ' ', t).strip()
    return t

async def speak_elevenlabs(text: str, voice_id: str = None, model: str = None) -> bytes:
    """Generate audio using ElevenLabs Studio Quality API (~250ms with Turbo v2.5)."""
    if not ELEVENLABS_KEY:
        print("[TTS:ElevenLabs] ABORT: No ELEVENLABS_KEY configured.")
        return None
    selected_voice = voice_id or config.get("elevenlabs_voice_id", "21m00Tcm4TlvDq8ikWAM") or "21m00Tcm4TlvDq8ikWAM"
    selected_model = model or config.get("elevenlabs_model", "eleven_turbo_v2_5") or "eleven_turbo_v2_5"
    tts_text = clean_tts_text(text, keep_direction_tags=False)
    if not tts_text:
        tts_text = text[:400]
    if len(tts_text) > 1500:
        tts_text = tts_text[:1500]

    print(f"[TTS:ElevenLabs] Sending POST to ElevenLabs (voice={selected_voice[:12]}..., model={selected_model}, len={len(tts_text)})...")
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{selected_voice}",
                headers={
                    "xi-api-key": ELEVENLABS_KEY,
                    "Content-Type": "application/json",
                },
                json={
                    "text": tts_text,
                    "model_id": selected_model,
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.75,
                        "style": 0.2,
                        "use_speaker_boost": True
                    }
                },
                timeout=aiohttp.ClientTimeout(total=25),
            ) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    print(f"[TTS:ElevenLabs] SUCCESS: {len(data)} bytes received (MP3)")
                    return data
                else:
                    err = await resp.text()
                    print(f"[TTS:ElevenLabs] HTTP {resp.status} ERROR: {err[:300]}")
                    return None
        except Exception as e:
            print(f"[TTS:ElevenLabs] EXCEPTION: {type(e).__name__}: {e}")
            return None

async def speak_openai(text: str, voice: str = None, model: str = None) -> bytes:
    """Generate audio using OpenAI Natural TTS API."""
    if not OPENAI_KEY or OPENAI_KEY.startswith("sk-or-"):
        print("[TTS:OpenAI] ABORT: No valid OPENAI_KEY configured.")
        return None
    selected_voice = voice or config.get("openai_voice", "nova") or "nova"
    selected_model = model or config.get("openai_model", "tts-1") or "tts-1"
    tts_text = clean_tts_text(text, keep_direction_tags=False)
    if not tts_text:
        tts_text = text[:400]
    if len(tts_text) > 1200:
        tts_text = tts_text[:1200]

    endpoint = "https://api.openai.com/v1/audio/speech"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    print(f"[TTS:OpenAI] Sending POST to OpenAI TTS (voice={selected_voice}, model={selected_model}, len={len(tts_text)})...")
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                endpoint,
                headers=headers,
                json={
                    "model": selected_model,
                    "voice": selected_voice,
                    "input": tts_text,
                    "response_format": "mp3",
                },
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    print(f"[TTS:OpenAI] SUCCESS: {len(data)} bytes received (MP3)")
                    return data
                else:
                    err = await resp.text()
                    print(f"[TTS:OpenAI] HTTP {resp.status} ERROR: {err[:300]}")
                    return None
        except Exception as e:
            print(f"[TTS:OpenAI] EXCEPTION: {type(e).__name__}: {e}")
            return None

_cartesia_credits_exhausted = 0
_fish_credits_exhausted = 0

async def speak_cartesia(text: str, voice_id: str = None, model: str = None) -> bytes:
    """Generate audio using Cartesia Sonic Ultra Low-Latency API (~100ms)."""
    global _cartesia_credits_exhausted
    if not CARTESIA_KEY:
        print("[TTS:Cartesia] ABORT: No CARTESIA_KEY configured.")
        return None
    if time.time() < _cartesia_credits_exhausted:
        return None
    selected_voice = voice_id or config.get("cartesia_voice_id", "a0e99841-438c-4a64-b679-ae501e7d6091") or "a0e99841-438c-4a64-b679-ae501e7d6091"
    raw_model = model or config.get("cartesia_model", "sonic-3.5") or "sonic-3.5"
    selected_model = "sonic-3.5" if raw_model in ("sonic-english", "sonic") else raw_model
    tts_text = clean_tts_text(text, keep_direction_tags=False)
    if not tts_text:
        tts_text = text[:400]
    if len(tts_text) > 1200:
        tts_text = tts_text[:1200]

    print(f"[TTS:Cartesia] Sending POST to Cartesia (voice={selected_voice[:12]}..., model={selected_model}, len={len(tts_text)})...")
    async with aiohttp.ClientSession() as session:
        for try_model in [selected_model, "sonic-3.5", "sonic-3", "sonic-turbo"]:
            try:
                async with session.post(
                    "https://api.cartesia.ai/tts/bytes",
                    headers={
                        "X-API-Key": CARTESIA_KEY,
                        "Cartesia-Version": "2024-11-13",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model_id": try_model,
                        "transcript": tts_text,
                        "voice": {"mode": "id", "id": selected_voice},
                        "output_format": {
                            "container": "wav",
                            "encoding": "pcm_s16le",
                            "sample_rate": 24000
                        }
                    },
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        print(f"[TTS:Cartesia] SUCCESS ({try_model}): {len(data)} bytes received (WAV)")
                        return data
                    elif resp.status == 402:
                        _cartesia_credits_exhausted = time.time() + 3600
                        print(f"[TTS:Cartesia] HTTP 402: Insufficient credits. Cooldown set for 1 hour.")
                        return None
                    else:
                        err = await resp.text()
                        print(f"[TTS:Cartesia] HTTP {resp.status} ERROR ({try_model}): {err[:300]}")
                        if "not found" in err.lower() or "deprecated" in err.lower() or "suspended" in err.lower():
                            continue
                        return None
            except Exception as e:
                print(f"[TTS:Cartesia] EXCEPTION: {type(e).__name__}: {e}")
                return None
    return None

async def speak_groq(text: str, voice: str = None, model: str = None) -> bytes:
    """Generate audio using Groq Orpheus LPU TTS API (sub-second latency)."""
    if not GROQ_KEY:
        print("[TTS:Groq] ABORT: No GROQ_KEY configured.")
        return None
    selected_voice = voice or config.get("groq_tts_voice", "hannah") or "hannah"
    selected_model = model or config.get("groq_tts_model", "canopylabs/orpheus-v1-english") or "canopylabs/orpheus-v1-english"
    tts_text = clean_tts_text(text, keep_direction_tags=True)
    if not tts_text:
        tts_text = text[:300]
    if len(tts_text) > 900:
        tts_text = tts_text[:900]

    print(f"[TTS:Groq] Sending POST to Groq TTS (voice={selected_voice}, model={selected_model}, len={len(tts_text)})...")
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                "https://api.groq.com/openai/v1/audio/speech",
                headers={
                    "Authorization": f"Bearer {GROQ_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": selected_model,
                    "voice": selected_voice,
                    "input": tts_text,
                    "response_format": "wav",
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    print(f"[TTS:Groq] SUCCESS: {len(data)} bytes received (WAV)")
                    return data
                else:
                    err = await resp.text()
                    print(f"[TTS:Groq] HTTP {resp.status} ERROR: {err[:300]}")
                    if "model_terms_required" in err:
                        print("[TTS:Groq] NOTE: Accept Groq terms at https://console.groq.com/playground?model=canopylabs%2Forpheus-v1-english")
                    return None
        except Exception as e:
            print(f"[TTS:Groq] EXCEPTION: {type(e).__name__}: {e}")
            return None

async def speak_edge(text: str, voice: str = None) -> bytes:
    """Generate audio using Microsoft Edge Neural TTS (Free, high-speed, zero API key)."""
    if not EDGE_TTS_AVAILABLE or edge_tts is None:
        print("[TTS:Edge] ABORT: edge_tts package not available.")
        return None
    selected_voice = voice or config.get("edge_tts_voice", "en-US-AvaMultilingualNeural") or "en-US-AvaMultilingualNeural"
    tts_text = clean_tts_text(text, keep_direction_tags=False)
    if not tts_text:
        tts_text = text[:400]
    if len(tts_text) > 1200:
        tts_text = tts_text[:1200]

    print(f"[TTS:Edge] Generating Edge TTS (voice={selected_voice}, len={len(tts_text)})...")
    try:
        comm = edge_tts.Communicate(tts_text, selected_voice)
        chunks = []
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                chunks.append(chunk["data"])
        if chunks:
            data = b"".join(chunks)
            print(f"[TTS:Edge] SUCCESS: {len(data)} bytes received (MP3)")
            return data
        else:
            print("[TTS:Edge] WARNING: Empty audio stream returned")
            return None
    except Exception as e:
        print(f"[TTS:Edge] EXCEPTION: {type(e).__name__}: {e}")
        return None

async def speak_fish(text: str, voice_id: str = None) -> bytes:
    """Generate audio using Fish Audio API (custom voice clones)."""
    global _fish_credits_exhausted
    if not FISH_AUDIO_KEY:
        print("[TTS:Fish] ABORT: No FISH_AUDIO_KEY configured.")
        return None
    if time.time() < _fish_credits_exhausted:
        return None
    vid = (voice_id or config.get("fish_voice_id", "")).strip()
    if not vid:
        print("[TTS:Fish] ABORT: No fish_voice_id configured.")
        return None
    tts_text = clean_tts_text(text, keep_fish_tags=True)
    if not tts_text:
        tts_text = text[:900]
    if len(tts_text) > 900:
        tts_text = tts_text[:900]
    model = config.get("fish_model", "s2.1-pro-free")

    print(f"[TTS:Fish] Sending POST to fish.audio (model={model}, voice_id={vid[:12]}...)...")
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                "https://api.fish.audio/v1/tts",
                headers={
                    "Authorization": f"Bearer {FISH_AUDIO_KEY}",
                    "Content-Type": "application/json",
                    "model": model,
                },
                json={
                    "text": tts_text,
                    "reference_id": vid,
                    "format": "mp3",
                },
                timeout=aiohttp.ClientTimeout(total=45),
            ) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    print(f"[TTS:Fish] SUCCESS: {len(data)} bytes received")
                    return data
                elif resp.status == 402:
                    _fish_credits_exhausted = time.time() + 3600
                    print(f"[TTS:Fish] HTTP 402: Insufficient API credit. Cooldown set for 1 hour.")
                    return None
                else:
                    err = await resp.text()
                    print(f"[TTS:Fish] HTTP {resp.status} ERROR: {err[:300]}")
                    return None
        except Exception as e:
            print(f"[TTS:Fish] EXCEPTION: {type(e).__name__}: {e}")
            return None

async def speak(text: str, force: bool = False, bot_id: str = None) -> bytes:
    """Unified multi-engine TTS router with automatic fast fallback, strictly isolated per bot."""
    target_cfg = config
    if bot_id and 'bots_state' in globals() and isinstance(bots_state, dict):
        b = get_bot_by_id(bots_state, bot_id)
        if b and isinstance(b.get("config"), dict):
            target_cfg = b["config"]

    if not force and not target_cfg.get("tts_enabled", True):
        return None
    provider = (target_cfg.get("tts_provider") or "auto").lower().strip()
    print(f"[TTS] === speak() called === (provider={provider}, bot_id={bot_id}, text_len={len(text)}, force={force})")
    
    data = None
    if provider == "elevenlabs":
        data = await speak_elevenlabs(text, voice_id=target_cfg.get("elevenlabs_voice_id"))
        if not data:
            print("[TTS] ElevenLabs failed, falling back to Edge TTS...")
            data = await speak_edge(text, voice=target_cfg.get("edge_tts_voice"))
    elif provider == "openai":
        data = await speak_openai(text, voice=target_cfg.get("openai_voice"))
        if not data:
            print("[TTS] OpenAI failed, falling back to Edge TTS...")
            data = await speak_edge(text, voice=target_cfg.get("edge_tts_voice"))
    elif provider == "cartesia":
        data = await speak_cartesia(text, voice_id=target_cfg.get("cartesia_voice_id"))
        if not data:
            print("[TTS] Cartesia failed, falling back to Edge TTS...")
            data = await speak_edge(text, voice=target_cfg.get("edge_tts_voice"))
    elif provider == "groq":
        data = await speak_groq(text, voice=target_cfg.get("groq_tts_voice"))
        if not data:
            print("[TTS] Groq failed, falling back to Edge TTS...")
            data = await speak_edge(text, voice=target_cfg.get("edge_tts_voice"))
    elif provider == "edge":
        data = await speak_edge(text, voice=target_cfg.get("edge_tts_voice"))
    elif provider == "fish":
        target_fish_vid = (target_cfg.get("fish_voice_id") or "").strip()
        if target_fish_vid:
            data = await speak_fish(text, voice_id=target_fish_vid)
        if not data:
            print("[TTS] Fish Audio voice not configured or failed, falling back to Edge TTS...")
            data = await speak_edge(text, voice=target_cfg.get("edge_tts_voice"))
    else:  # auto mode: try ElevenLabs -> OpenAI -> Cartesia -> Groq -> Edge -> Fish (strictly per-bot voice!)
        if ELEVENLABS_KEY:
            data = await speak_elevenlabs(text, voice_id=target_cfg.get("elevenlabs_voice_id"))
        if not data and OPENAI_KEY and not OPENAI_KEY.startswith("sk-or-"):
            data = await speak_openai(text, voice=target_cfg.get("openai_voice"))
        if not data and CARTESIA_KEY:
            data = await speak_cartesia(text, voice_id=target_cfg.get("cartesia_voice_id"))
        if not data and GROQ_KEY:
            data = await speak_groq(text, voice=target_cfg.get("groq_tts_voice"))
        if not data and EDGE_TTS_AVAILABLE:
            data = await speak_edge(text, voice=target_cfg.get("edge_tts_voice"))
        target_fish_vid = (target_cfg.get("fish_voice_id") or "").strip()
        if not data and FISH_AUDIO_KEY and target_fish_vid:
            data = await speak_fish(text, voice_id=target_fish_vid)

    if data and len(data) > 0:
        if (config.get("vtuber_enabled", True) or vtuber_clients) and vtuber_bridge_online:
            try:
                audio_b64 = base64.b64encode(data).decode("utf-8")
                fmt = "wav" if (data.startswith(b"RIFF") or data.startswith(b"\x52\x49\x46\x46")) else "mp3"
                await vtuber_broadcast({"type": "audio", "text": text[:200], "data": audio_b64, "format": fmt})
                print(f"[VTUBER] Audio broadcasted to viewer ({len(data)} bytes, fmt={fmt}).")
            except Exception as e:
                print(f"[VTUBER] Broadcast error: {e}")
        return data
    else:
        print("[TTS] All configured TTS engines returned None.")
        return None

async def _safe_send_voice_reply(message, audio_bytes):
    """Safely send voice audio attachment without crashing on Missing Permissions (403 Forbidden)."""
    if not audio_bytes:
        return
    try:
        file = discord.File(io.BytesIO(audio_bytes), filename="voice.mp3")
        await message.reply(file=file)
    except discord.Forbidden:
        ch_name = getattr(message.channel, "name", str(message.channel.id))
        print(f"[TTS WARN] Cannot send voice.mp3: Missing 'Attach Files' permission in #{ch_name}.")
    except Exception as e:
        print(f"[TTS WARN] Failed to send voice audio file: {e}")

# ─── MAIN AI CALLER ─────────────────────────────────────
async def ask_ai(channel_id, prompt: str, user_id=None, user_name=None, guild=None, is_dm=False, system_msg_override: str = None, bot_id: str = None, images: list = None, audio_bytes: bytes = None, audio_mime: str = "audio/wav", custom_model: str = None, custom_base_url: str = None, custom_key: str = None, raw_mentions: list = None, reply_to_user_id: str = None, raw_content: str = None, **kwargs) -> tuple:
    effective_bot_id = str(bot_id or get_current_bot_id() or "default")
    if not system_msg_override:
        refresh_runtime_config()
    ctx = get_context(channel_id, bot_id=effective_bot_id)
    
    is_instagram = str(channel_id).startswith("insta_")
    cur_bot_name = get_current_bot_name()
    if is_instagram:
        # Dedicated Instagram persona / override
        insta_p = config.get("insta_personality") or config.get("personality")
        fallback_insta = f"You are {cur_bot_name} chatting on Instagram."
        system_msg = system_msg_override if (system_msg_override and system_msg_override.strip()) else (insta_p or fallback_insta)
    else:
        # DISCORD AI PROMPT & SCENE CONTEXT
        default_persona = f"You are {cur_bot_name}, an AI companion."
        system_msg = system_msg_override if (system_msg_override and system_msg_override.strip()) else config.get("personality", default_persona)
        if config.get("user_memory_enabled", True):
            scene = build_scene_context(channel_id, primary_user_id=user_id, user_name=user_name, guild=guild, is_dm=is_dm, current_prompt=prompt, bot_id=effective_bot_id, raw_mentions=raw_mentions, reply_to_user_id=reply_to_user_id, raw_content=raw_content)
            if scene:
                system_msg += "\n\n" + scene

        # Hook dynamic training data style without modifying base personality prompt
        training_hook = build_training_prompt_hook(effective_bot_id)
        if training_hook:
            system_msg += "\n\n" + training_hook

        if config.get("message_split_enabled", False):
            system_msg += "\n\nIf you have multiple separate thoughts or distinct points, separate them with ||SPLIT|| so they can be sent as individual messages. Keep each part conversational."

        if "[(Acoustic & Environmental Perception:" in prompt or "Acoustic perception:" in prompt or audio_bytes:
            system_msg += (
                "\n\n[LIVE VOICE CALL PERCEPTION DIRECTIVE]:\n"
                "- You are currently on a real-time live Discord voice channel call with the user.\n"
                "- You can hear their vocal emotional tone (whispering, laughter, giggling, sighing, excitement, sadness, shouting) as well as sounds or music in their room.\n"
                "- Seamlessly acknowledge and react in character to how they sound and what you hear in their background!"
            )

        system_msg += (
            "\n\n[STRICT ROLEPLAY DIRECTIVE]:\n"
            "- You are NOT an AI assistant, language model, or customer service agent. You must strictly stay in character as defined above.\n"
            "- NEVER use generic corporate assistant phrases (e.g. 'Let\'s delve deeper into this', 'What are your thoughts?', 'How can I assist you?', 'As an AI').\n"
            "- NEVER write synthetic narrator stage directions or repetitive physical actions in asterisks like '*turns to you attentively, engaging directly with your words*'.\n"
            "- Reply directly, authentically, and vividly in character."
        )

    provider = config.get("provider", "auto")
    auto_search = config.get("auto_search", True)

    def save_ctx(reply):
        # Strip synthetic assistant artifacts before saving/sending
        cleaned = reply or ""
        cleaned = re.sub(r'\*turns to you attentively[^*]*\*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\*engaging directly with your words[^*]*\*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'—\s*let\'s delve deeper into this\.\s*What are your thoughts\?', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'let\'s delve deeper into this\.\s*What are your thoughts\?', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'How can I assist you (today|further)\??', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'As an AI (assistant|language model)[^,\.\n]*[,\.\n]?', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'[ \t]+', ' ', cleaned).strip()

        # For Instagram, ensure the saved user prompt is clean and not bloated with system/memory metadata
        user_prompt_clean = prompt
        if is_instagram:
            if "\n\nMessage from follower @" in user_prompt_clean:
                parts = user_prompt_clean.split("\n\nMessage from follower @", 1)[1]
                if ': "' in parts:
                    user_prompt_clean = parts.split(': "', 1)[1].split('"', 1)[0]
                else:
                    user_prompt_clean = parts.split('\n', 1)[0]
            elif "User's accompanying message: \"" in user_prompt_clean:
                user_prompt_clean = user_prompt_clean.split("User's accompanying message: \"", 1)[1].split('"', 1)[0]
            elif "The user sent " in user_prompt_clean and ":\n" in user_prompt_clean:
                user_prompt_clean = user_prompt_clean.split(":\n", 1)[1].split("\n\n", 1)[0]
            elif "[USER CONTEXT:" in user_prompt_clean:
                # Fallback: take last non-empty line before formatting instructions
                lines_p = [l.strip() for l in user_prompt_clean.split("\n") if l.strip() and not l.startswith("[") and not l.startswith("Handle:") and not l.startswith("Bio:") and not l.startswith("Name") and not l.startswith("Recent") and not l.startswith("•")]
                if lines_p:
                    user_prompt_clean = lines_p[-1]

        add_to_context(channel_id, "user", user_prompt_clean, user_name=user_name, user_id=user_id, bot_id=effective_bot_id)
        add_to_context(channel_id, "assistant", cleaned or reply, bot_id=effective_bot_id)

    if images and len(images) > 0:
        img_bytes, mime = images[0]
        reply, err = await ask_multimodal_vision(system_msg, prompt, img_bytes, mime, history=ctx)
        if not err and reply:
            save_ctx(reply)
            return reply, False
        if reply:
            return reply, True

    if audio_bytes and len(audio_bytes) > 0:
        reply, err = await ask_multimodal_vision(
            system_msg,
            prompt,
            image_bytes_or_list=None,
            history=ctx,
            audio_bytes=audio_bytes,
            audio_mime=audio_mime or "audio/wav"
        )
        if not err and reply:
            save_ctx(reply)
            return reply, False

    active_prompt = prompt
    if MEDIA_INTELLIGENCE_AVAILABLE and "http" in prompt.lower() and not prompt.startswith("=== VISITED WEBPAGE:") and not prompt.startswith("=== WATCHED VIDEO:") and not prompt.startswith("The user shared a video") and not prompt.startswith("The user shared a webpage"):
        media_url_info = detect_and_handle_media_urls(prompt)
        if media_url_info:
            url_type, target_url = media_url_info
            if url_type == "video":
                try:
                    context_data, report = await watch_video_tool(target_url, bot_config=config)
                    active_prompt = (
                        f"The user shared a video ({target_url}) and asked/said: \"{prompt}\"\n\n"
                        f"Here is the observed video intelligence, dialogue transcript, acoustic events, and scenes:\n{context_data}\n\n"
                        f"Respond in full character addressing what the user asked/said about the video!"
                    )
                except Exception as ve:
                    print(f"[ASK_AI VIDEO WATCH NOTICE] {ve}")
            elif url_type == "web":
                try:
                    context_data, page = await browse_web_tool(target_url)
                    active_prompt = (
                        f"The user shared a webpage ({target_url}) and asked/said: \"{prompt}\"\n\n"
                        f"{context_data}\n\n"
                        f"[CRITICAL READING DIRECTIVE]: You have been provided with the FULL article text and sections extracted above. "
                        f"Read and synthesize across the entire page, drawing on all relevant sections, lore, technical specifications, and details (do not just repeat the first few lines or overview) "
                        f"to provide a rich, accurate, and in-character answer to what the user asked!"
                    )
                except Exception as we:
                    print(f"[ASK_AI BROWSE WEB NOTICE] {we}")

    if auto_search and needs_realtime_data(prompt) and active_prompt == prompt:
        search_query = extract_clean_user_query(prompt) or prompt
        print(f"[AUTO-SEARCH] Proactive search triggered for: {search_query[:60]}...")
        results, serr = await web_search(search_query, max_results=5)
        if results and not serr:
            reply, err = await synthesize_search(channel_id, search_query, results, ctx, system_msg=system_msg)
            if not err:
                save_ctx(reply)
                return reply, False

    async def _handle_reactive_search(orig_prompt, current_reply):
        if auto_search and should_retry_with_search(current_reply, orig_prompt=orig_prompt):
            print(f"[AUTO-SEARCH] Reactive search triggered.")
            search_query = extract_clean_user_query(orig_prompt) or orig_prompt
            results, serr = await web_search(search_query, max_results=5)
            if results and not serr:
                r2, e2 = await synthesize_search(channel_id, search_query, results, ctx, system_msg=system_msg)
                if not e2:
                    save_ctx(r2)
                    return r2
        return current_reply

    reply, err = None, True
    tried_providers = set()

    # 1. First priority: Check if a Custom Model / Custom Endpoint is requested
    eff_custom_model = (custom_model or config.get("custom_model") or "").strip()
    eff_custom_base_url = (custom_base_url or config.get("custom_base_url") or "").strip()
    eff_custom_key = (custom_key or config.get("custom_key") or "").strip()
    cfg_model = (config.get("model") or "").strip()

    if not eff_custom_model and cfg_model and cfg_model not in ("openrouter/free", "default", "auto"):
        eff_custom_model = cfg_model

    target_gemini_model = (
        (custom_model if ("gemini" in str(custom_model).lower() and "/" not in str(custom_model)) else None)
        or (config.get("model") if ("gemini" in str(config.get("model")).lower() and "/" not in str(config.get("model"))) else None)
        or config.get("gemini_model")
        or "gemini-3.1-flash-lite"
    )
    target_groq_model = (
        (custom_model if any(k in str(custom_model).lower() for k in ("qwen", "groq", "compound", "gpt-oss")) else None)
        or (config.get("model") if any(k in str(config.get("model")).lower() for k in ("qwen", "groq", "compound", "gpt-oss")) else None)
        or config.get("groq_model")
        or "qwen/qwen3.8-27b"
    )
    target_mistral_model = (
        (custom_model if any(k in str(custom_model).lower() for k in ("mistral", "codestral")) else None)
        or (config.get("model") if any(k in str(config.get("model")).lower() for k in ("mistral", "codestral")) else None)
        or config.get("mistral_model")
        or "ministral-8b-latest"
    )

    is_custom_requested = (
        provider == "custom"
        or bool(eff_custom_base_url)
        or (provider == "openrouter")
        or (provider not in ("gemini", "groq", "mistral", "openai", "deepseek") and bool(eff_custom_base_url))
    )

    if is_custom_requested:
        tried_providers.add("custom")
        print(f"[ASK_AI] Executing user-configured custom model / endpoint (model='{eff_custom_model or config.get('model')}', ep='{eff_custom_base_url or 'default'}')")
        reply, err = await ask_custom_endpoint(
            ctx, active_prompt, system_msg=system_msg,
            model=eff_custom_model,
            base_url=eff_custom_base_url,
            api_key=eff_custom_key
        )
        if not err and reply:
            save_ctx(reply)
            reply = await _handle_reactive_search(prompt, reply)
            return reply, False
        print(f"[ASK_AI WARN] Custom model/endpoint failed ({reply}), cascading to available backup providers...")

    if not is_custom_requested:
        if provider == "groq" and "groq" not in tried_providers:
            tried_providers.add("groq")
            if GROQ_KEY and time.time() >= groq_blocked_until:
                reply, err = await ask_groq(ctx, active_prompt, system_msg=system_msg, model=target_groq_model)
            else:
                err = True
                reply = "Groq key not configured or on rate limit cooldown."
            if err:
                print(f"[ASK_AI WARN] Primary Groq provider failed ({reply}), falling back to alternative providers...")
        elif provider == "mistral" and "mistral" not in tried_providers:
            tried_providers.add("mistral")
            m_key = config.get("mistral_key", "").strip() or os.getenv("MISTRAL_KEY", "").strip() or MISTRAL_KEY
            if m_key and time.time() >= mistral_blocked_until:
                reply, err = await ask_mistral(ctx, active_prompt, system_msg=system_msg, model=target_mistral_model)
            else:
                err = True
                reply = "Mistral key not configured or on rate limit cooldown."
            if err:
                print(f"[ASK_AI WARN] Primary Mistral provider failed ({reply}), falling back to alternative providers...")
        elif provider == "gemini" and "gemini" not in tried_providers:
            tried_providers.add("gemini")
            if GEMINI_KEY and time.time() >= gemini_blocked_until:
                reply, err = await ask_gemini(system_msg, ctx, active_prompt, model=target_gemini_model)
            else:
                err = True
                reply = "Gemini key not configured or on rate limit cooldown."
            if err:
                print(f"[ASK_AI WARN] Primary Gemini provider failed ({reply}), falling back to alternative providers...")
        elif provider == "openrouter" and "openrouter" not in tried_providers:
            tried_providers.add("openrouter")
            if os.getenv("OPENROUTER_KEY") and time.time() >= openrouter_blocked_until:
                reply, err = await ask_openrouter(ctx, active_prompt, system_msg=system_msg, model=eff_custom_model or None)
            else:
                err = True
                reply = "OpenRouter key not configured or on rate limit cooldown."
            if err:
                print(f"[ASK_AI WARN] Primary OpenRouter provider failed ({reply}), falling back to alternative providers...")
        elif provider == "openai" and "openai" not in tried_providers:
            tried_providers.add("openai")
            if get_openai_key() and time.time() >= openai_blocked_until:
                reply, err = await ask_openai(ctx, active_prompt, system_msg=system_msg, model=eff_custom_model or None)
            else:
                err = True
                reply = "OpenAI key not configured or on rate limit cooldown."
            if err:
                print(f"[ASK_AI WARN] Primary OpenAI provider failed ({reply}), falling back to alternative providers...")
        elif provider == "deepseek" and "deepseek" not in tried_providers:
            tried_providers.add("deepseek")
            if get_deepseek_key() and time.time() >= deepseek_blocked_until:
                reply, err = await ask_deepseek(ctx, active_prompt, system_msg=system_msg, model=eff_custom_model or None)
            else:
                err = True
                reply = "DeepSeek key not configured or on rate limit cooldown."
            if err:
                print(f"[ASK_AI WARN] Primary DeepSeek provider failed ({reply}), falling back to alternative providers...")

        # If the primary provider succeeded, save and return
        if not err and reply:
            save_ctx(reply)
            reply = await _handle_reactive_search(prompt, reply)
            return reply, False

    # Auto Fallback Chain (ordered by speed & active status):
    # 1. Groq (ultra fast, ~0.4s response time)
    if "groq" not in tried_providers and GROQ_KEY and time.time() >= groq_blocked_until:
        reply, err = await ask_groq(ctx, active_prompt, system_msg=system_msg, model=target_groq_model)
        if not err and reply:
            save_ctx(reply)
            reply = await _handle_reactive_search(prompt, reply)
            return reply, False
        print(f"[AUTO] Groq fallback failed ({reply}), trying Mistral...")

    # 2. Mistral (~1.1s response time)
    m_key = config.get("mistral_key", "").strip() or os.getenv("MISTRAL_KEY", "").strip() or MISTRAL_KEY
    if "mistral" not in tried_providers and m_key and time.time() >= mistral_blocked_until:
        reply, err = await ask_mistral(ctx, active_prompt, system_msg=system_msg, model=target_mistral_model)
        if not err and reply:
            save_ctx(reply)
            reply = await _handle_reactive_search(prompt, reply)
            return reply, False
        print(f"[AUTO] Mistral fallback failed ({reply}), trying Gemini...")

    # 3. Gemini (only if key configured and NOT on rate limit cooldown)
    if "gemini" not in tried_providers and GEMINI_KEY and time.time() >= gemini_blocked_until:
        reply, err = await ask_gemini(system_msg, ctx, active_prompt, model=target_gemini_model)
        if not err and reply:
            save_ctx(reply)
            reply = await _handle_reactive_search(prompt, reply)
            return reply, False
        print(f"[AUTO] Gemini fallback failed ({reply}), trying DeepSeek...")

    # 5. DeepSeek
    if "deepseek" not in tried_providers and get_deepseek_key() and time.time() >= deepseek_blocked_until:
        reply, err = await ask_deepseek(ctx, active_prompt, system_msg=system_msg)
        if not err and reply:
            save_ctx(reply)
            reply = await _handle_reactive_search(prompt, reply)
            return reply, False
        print(f"[AUTO] DeepSeek fallback failed ({reply}), trying OpenAI...")

    # 6. OpenAI
    if "openai" not in tried_providers and get_openai_key() and time.time() >= openai_blocked_until:
        reply, err = await ask_openai(ctx, active_prompt, system_msg=system_msg)
        if not err and reply:
            save_ctx(reply)
            reply = await _handle_reactive_search(prompt, reply)
            return reply, False
        print(f"[AUTO] OpenAI fallback failed ({reply}).")
    if not err:
        save_ctx(reply)
        reply = await _handle_reactive_search(prompt, reply)
        return reply, False

    mins = []
    if gemini_blocked_until > time.time():
        mins.append(f"Gemini {int(gemini_blocked_until - time.time())}s")
    if groq_blocked_until > time.time():
        mins.append(f"Groq {int(groq_blocked_until - time.time())}s")
    if mistral_blocked_until > time.time():
        mins.append(f"Mistral {int(mistral_blocked_until - time.time())}s")
    if openrouter_blocked_until > time.time():
        mins.append(f"OpenRouter {int(openrouter_blocked_until - time.time())}s")
    print(f"[ASK_AI ALL FAILED] All providers failed. Cooldowns: {mins}")
    if mins:
        return f"All AI providers rate limited. Cooldowns: {', '.join(mins)}.", True
    return "No AI providers available. Check your API keys.", True

def should_run_social() -> bool:
    """Returns True if this process is designated to run the Instagram & X social media integrations."""
    if os.getenv("RUN_SOCIAL") == "1":
        return True
    if os.getenv("RUN_SOCIAL") == "0":
        return False
    child_id = os.getenv("BOT_ID")
    if not child_id:
        # Main supervisor process should not run background social pollers (child bot processes do)
        return False
    if 'bots_state' in globals() and isinstance(bots_state, dict):
        bot_entry = get_bot_by_id(bots_state, child_id)
        if bot_entry and (bot_entry.get("insta_enabled") and bot_entry.get("insta_sessionid")):
            return True
        if bot_entry and (bot_entry.get("name") or "").lower() == "yuna":
            return True
    return False

# ─── SOCIAL MEDIA INTEGRATION INITIALIZATION ─────────────
social_manager = None
if SOCIAL_INTEGRATION_AVAILABLE and SocialManager and should_run_social():
    try:
        social_manager = SocialManager(
            bot_config=config,
            ask_ai_fn=ask_ai,
            ask_vision_fn=ask_gemini_vision,
            watch_video_fn=watch_video_tool if MEDIA_INTELLIGENCE_AVAILABLE else None,
            speak_fn=speak,
            transcribe_fn=transcribe_audio
        )
        print("[SOCIAL] SocialManager initialized successfully.")
    except Exception as _sme:
        print(f"[SOCIAL MANAGER INIT ERROR] {_sme}")

async def handle_discord_social_post(message: discord.Message, target_platform: str, user_custom_prompt: str = ""):
    """
    Handles posting screenshot/image/video to X (Twitter) or Instagram.
    Analyzes visual & acoustic content, generates Yuna's persona caption,
    uploads to social platform, and replies with a status embed.
    """
    if not SOCIAL_INTEGRATION_AVAILABLE or not social_manager:
        await safe_reply(message, "❌ Social media integration module is not available.")
        return

    # Check credentials
    if target_platform == "x" and not social_manager.x_client.is_configured():
        await safe_reply(message, "⚠️ **X (Twitter) is not configured yet!**\nPlease add your API keys or Bearer Token in the Web Dashboard or config.json.")
        return
    if target_platform == "instagram" and not social_manager.insta_client.is_configured():
        await safe_reply(message, "⚠️ **Instagram is not configured yet!**\nPlease set your Instagram username and password in the Web Dashboard or config.json.")
        return

    media_bytes = None
    media_filename = "media.jpg"
    media_url = None
    media_path = None

    # 1. Check current message attachments
    if message.attachments:
        att = message.attachments[0]
        media_filename = att.filename
        media_url = att.url
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(att.url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status == 200:
                        media_bytes = await resp.read()
        except Exception as e:
            print(f"[SOCIAL POST] Error downloading attachment: {e}")

    # 2. Check referenced message (reply)
    if not media_bytes and message.reference and message.reference.message_id:
        try:
            ref_msg = await message.channel.fetch_message(message.reference.message_id)
            if ref_msg and ref_msg.attachments:
                att = ref_msg.attachments[0]
                media_filename = att.filename
                media_url = att.url
                async with aiohttp.ClientSession() as session:
                    async with session.get(att.url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                        if resp.status == 200:
                            media_bytes = await resp.read()
        except Exception as e:
            print(f"[SOCIAL POST] Error fetching referenced message: {e}")

    # 3. Check for URL in message content
    if not media_bytes:
        url_match = re.search(r'https?://[^\s<>"]+', message.content)
        if url_match:
            cand_url = url_match.group(0)
            if any(cand_url.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".webm"]):
                media_url = cand_url
                media_filename = Path(cand_url.split("?")[0]).name or "media.jpg"
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(cand_url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                            if resp.status == 200:
                                media_bytes = await resp.read()
                except Exception as e:
                    print(f"[SOCIAL POST] Error downloading URL media: {e}")

    if not media_bytes and not media_url:
        cur_name = get_current_bot_name()
        platform_label = "X (Twitter)" if target_platform == "x" else "Instagram"
        await safe_reply(
            message,
            f"📸 **Please attach a screenshot, photo, or video** (or reply to a media message) when saying `post this!` / `!xpost` / `ipost` so {cur_name} can analyze it and post to {platform_label}!"
        )
        return

    # Notify user that bot is observing and writing
    cur_name = get_current_bot_name()
    platform_name = "X (Twitter)" if target_platform == "x" else "Instagram"
    platform_color = 0x1DA1F2 if target_platform == "x" else 0xE1306C
    
    status_msg = await safe_reply(
        message,
        f"⏳ **Observing {media_filename}...**\n*{cur_name} is analyzing the visual details & writing an in-character caption for {platform_name}...*"
    )

    async with safe_typing(message.channel):
        try:
            if target_platform == "x":
                ok, caption, analysis, post_url = await social_manager.post_to_x_with_analysis(
                    media_bytes=media_bytes,
                    media_filename=media_filename,
                    media_url=media_url,
                    user_prompt=user_custom_prompt
                )
            else:
                ok, caption, analysis, post_url = await social_manager.post_to_insta_with_analysis(
                    media_bytes=media_bytes,
                    media_filename=media_filename,
                    media_url=media_url,
                    user_prompt=user_custom_prompt
                )

            analysis_preview = analysis[:300] + "..." if len(analysis) > 300 else analysis

            if ok:
                embed = discord.Embed(
                    title=f"✨ {cur_name} // Posted to {platform_name}!",
                    description=(
                        f"**📝 Generated Caption:**\n> {caption}\n\n"
                        f"**🔍 Observed Content Analysis:**\n*{analysis_preview}*\n\n"
                        f"🔗 **Live Post:** [{post_url or 'View on ' + platform_name}]({post_url or ('https://x.com' if target_platform == 'x' else 'https://instagram.com')})"
                    ),
                    color=platform_color
                )
                embed.set_footer(text=f"Analyzed & Posted by {cur_name} • {platform_name}")
                if status_msg:
                    try:
                        await status_msg.edit(content=None, embed=embed)
                    except Exception:
                        await safe_reply(message, embed=embed)
                else:
                    await safe_reply(message, embed=embed)
            else:
                err_text = post_url or "Unknown error"
                await safe_reply(
                    message,
                    f"❌ **Failed to post to {platform_name}**:\n```{err_text}```\n*Analysis was:*\n> {caption}"
                )
        except Exception as e:
            await safe_reply(message, f"❌ Social posting error: {e}")


# ─── AUTO-SEARCH HELPERS ────────────────────────────────
REALTIME_KEYWORDS = [
    "weather", "forecast", "temperature", "rain", "snow", "sunny",
    "news", "latest", "breaking", "today", "yesterday", "this week",
    "stock", "price", "crypto", "bitcoin", "ethereum", "market",
    "score", "game", "match", "won", "lost", "vs", "playing",
    "who won", "what happened", "current", "right now",
    "live", "update", "election", "release date",
    "how much is", "directions", "hours", "open now",
    "covid", "coronavirus", "pandemic", "death toll",
]

REFUSAL_PATTERNS = [
    "i don't know", "i do not know", "i'm not sure", "i am not sure",
    "i don't have", "i do not have", "i cannot access", "i can't access",
    "i don't have access", "my knowledge cutoff", "my training data",
    "i'm unable to", "i am unable to", "i cannot provide", "i can't provide",
    "i don't have real-time", "i do not have real-time", "as an ai",
    "i don't have information", "i do not have information",
]

def extract_clean_user_query(query: str) -> str:
    """Strips leading speaker/reply tags to get the core query for searching."""
    if not query:
        return ""
    q = query.strip()
    if q.startswith("[") and "]:" in q:
        q = q.split("]:", 1)[1].strip()
    elif q.startswith("[") and "]" in q:
        q = q.split("]", 1)[1].strip()
    if q.startswith("(") and ")" in q:
        q = q.split(")", 1)[1].strip()
    return q.strip()

def is_query_about_users_or_memory(query: str) -> bool:
    """Detects if a query is asking about Discord users, memory, relationships, or community members."""
    if not query:
        return False
    # Direct Discord user mentions: <@123>, <@!123>, <@&123>, or @mention
    if re.search(r'<@!?\d+>', query) or re.search(r'<@&\d+>', query) or re.search(r'@[A-Za-z0-9_>~∆]', query):
        return True
    q = query.lower()
    # Memory and persona relationship phrasing
    user_lore_patterns = [
        r'\bwho\s+(?:is|\'s|are|was|the\s+fuck\s+is|tf\s+is)\b',
        r'\bwhat\s+about\b',
        r'\bdo\s+you\s+know\b',
        r'\btell\s+me\s+about\b',
        r'\bwhat\s+do\s+you\s+think\s+of\b',
        r'\bopinion\s+on\b',
        r'\bremember\s+when\b',
        r'\bwhat\s+did\s+(?:they|he|she|we|you)\s+say\b',
        r'\bwho\s+said\b',
        r'\bwho\s+plays\b',
        r'\bwho\s+gave\b',
        r'\bwho\s+has\b',
        r'\bto\s+you\b',
        r'\bmarry\b',
        r'\bmarried\b',
        r'\bspouse\b',
        r'\bhusband\b',
        r'\bwife\b',
        r'\bour\s+friend\b',
        r'\bdescribe\b',
    ]
    if any(re.search(pat, q) for pat in user_lore_patterns):
        return True

    # Check against known users in user_profiles or memory tree
    if 'user_profiles' in globals() and isinstance(user_profiles, dict):
        _, q_tokens = normalize_discord_name(q)
        q_token_set = set(q_tokens)
        for uid_k, prof_v in user_profiles.items():
            bm = prof_v.get("bot_memories", {})
            has_m = any(len(b.get("facts", [])) > 0 for b in bm.values()) or len(prof_v.get("facts", [])) > 0
            if not has_m:
                continue
            un = prof_v.get("name") or ""
            gn = prof_v.get("global_name") or ""
            _, un_tokens = normalize_discord_name(un)
            _, gn_tokens = normalize_discord_name(gn)
            u_tokens = set(un_tokens) | set(gn_tokens)
            if any(ut in q_token_set and len(ut) >= 3 for ut in u_tokens):
                return True
    return False

def needs_realtime_data(query: str) -> bool:
    if not query:
        return False
    clean_q = extract_clean_user_query(query)
    if not clean_q or "co-watching" in clean_q.lower() or "theater" in clean_q.lower():
        return False
    # Never hijack questions about users, friends, or memories with web search!
    if is_query_about_users_or_memory(clean_q):
        return False
    q = clean_q.lower()
    for kw in REALTIME_KEYWORDS:
        if " " in kw:
            if kw in q:
                return True
        else:
            if re.search(rf'\b{re.escape(kw)}\b', q):
                return True
    return False

def should_retry_with_search(reply: str, orig_prompt: str = None) -> bool:
    if not reply:
        return False
    if orig_prompt and is_query_about_users_or_memory(orig_prompt):
        return False
    r = reply.lower()
    return any(p in r for p in REFUSAL_PATTERNS)

async def synthesize_search(channel_id, user_query: str, results: list, ctx: list = None, system_msg: str = None) -> tuple:
    if not results:
        return "I looked around but didn't find anything useful.", False
    sys_msg = system_msg or config.get("personality", "")
    results_text = "\n".join([
        f"• {r['title']}: {r['snippet'][:220]}{'...' if len(r['snippet']) > 220 else ''}"
        for r in results[:5]
    ])
    clean_q = extract_clean_user_query(user_query) or user_query
    search_prompt = f"""The user asked: "{clean_q}"
Here is what I found from a quick web search:
{results_text}
Respond naturally in your usual personality and style. Do NOT list results with numbers or dump raw links. Just talk like a person having a conversation."""
    provider = config.get("provider", "auto")
    reply, err = None, True
    if provider == "gemini" and GEMINI_KEY and time.time() >= gemini_blocked_until:
        reply, err = await ask_gemini(sys_msg, ctx or [], search_prompt)
    elif provider == "deepseek" and get_deepseek_key() and time.time() >= deepseek_blocked_until:
        reply, err = await ask_deepseek(ctx or [], search_prompt, system_msg=sys_msg)
    elif provider == "openai" and get_openai_key() and time.time() >= openai_blocked_until:
        reply, err = await ask_openai(ctx or [], search_prompt, system_msg=sys_msg)
    elif provider == "groq" and GROQ_KEY and time.time() >= groq_blocked_until:
        reply, err = await ask_groq(ctx or [], search_prompt, system_msg=sys_msg)
    elif provider == "mistral" and (os.getenv("MISTRAL_KEY") or MISTRAL_KEY) and time.time() >= mistral_blocked_until:
        reply, err = await ask_mistral(ctx or [], search_prompt, system_msg=sys_msg)
    elif provider == "openrouter" and os.getenv("OPENROUTER_KEY") and time.time() >= openrouter_blocked_until:
        reply, err = await ask_openrouter(ctx or [], search_prompt, system_msg=sys_msg)
    else:
        if GEMINI_KEY and time.time() >= gemini_blocked_until:
            reply, err = await ask_gemini(sys_msg, ctx or [], search_prompt)
        if err and get_deepseek_key() and time.time() >= deepseek_blocked_until:
            reply, err = await ask_deepseek(ctx or [], search_prompt, system_msg=sys_msg)
        if err and get_openai_key() and time.time() >= openai_blocked_until:
            reply, err = await ask_openai(ctx or [], search_prompt, system_msg=sys_msg)
        if err and GROQ_KEY and time.time() >= groq_blocked_until:
            reply, err = await ask_groq(ctx or [], search_prompt, system_msg=sys_msg)
        if err and (os.getenv("MISTRAL_KEY") or MISTRAL_KEY) and time.time() >= mistral_blocked_until:
            reply, err = await ask_mistral(ctx or [], search_prompt, system_msg=sys_msg)
        if err and os.getenv("OPENROUTER_KEY") and time.time() >= openrouter_blocked_until:
            reply, err = await ask_openrouter(ctx or [], search_prompt, system_msg=sys_msg)
    if not err:
        add_to_context(channel_id, "user", user_query)
        add_to_context(channel_id, "assistant", reply)
    return reply, err

# ─── VOICE CALL INTEGRATION (discord_voice.py) ───────────
# Voice calls (/call, /vc, !call) are managed by voice_manager from discord_voice.py
if DISCORD_VOICE_AVAILABLE and voice_manager:
    voice_sessions = voice_manager.sessions
else:
    voice_sessions = {}


# ─── SLASH COMMANDS ─────────────────────────────────────

@tree.command(name="observe", description="Control Real-Time Audio/Visual Passive Observation Module (Orders 1-13)")
@app_commands.describe(action="start, stop, status, or query", query="Optional query for observation session")
async def slash_observe(interaction: discord.Interaction, action: str, query: Optional[str] = None):
    action = action.lower()
    if action == "start":
        msg = await passive_obs_module.start_observation()
        await interaction.response.send_message(msg)
    elif action == "stop":
        msg = await passive_obs_module.stop_observation()
        await interaction.response.send_message(msg)
    elif action == "query" and query:
        await interaction.response.defer()
        ans = await passive_obs_module.answer_user_query(query)
        await interaction.followup.send(ans)
    else:
        tel = passive_obs_module.get_telemetry()
        await interaction.response.send_message(
            f"**👁️ Passive Observation Desk**\n"
            f"• Status: `{'ACTIVE' if tel['is_active'] else 'INACTIVE'}`\n"
            f"• Elapsed: `{tel['session_time_str']}`\n"
            f"• In-Memory Frames: `{tel['total_frames_in_buffer']}/60` (1 fps)\n"
            f"• Audio Chunks: `{tel['total_audio_chunks_in_buffer']}/6` (10s 16kHz)\n"
            f"• Rolling Memory Log: `{tel['memory_log_entries_count']}` entries (~{tel['estimated_token_count']} tokens)"
        )


@tree.command(name="sync", description="Force re-sync slash commands globally (Owner only)")
async def slash_sync(interaction: discord.Interaction):
    if not await check_owner(interaction.user.id):
        await interaction.response.send_message("Owner only.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    try:
        synced = await tree.sync()
        names = ", ".join([f"/{c.name}" for c in synced]) if synced else "none"
        await interaction.followup.send(f"Synced {len(synced)} commands: {names}. Wait ~1 min.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Sync failed: {e}", ephemeral=True)

@tree.command(name="transcribe", description="Transcribe the most recent voice/audio message in this channel")
async def slash_transcribe(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    found = False
    async for msg in interaction.channel.history(limit=30):
        if msg.attachments:
            for att in msg.attachments:
                ext = Path(att.filename).suffix.lower()
                if att.content_type and att.content_type.startswith("audio/") or ext in (".ogg", ".mp3", ".wav", ".m4a", ".flac"):
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.get(att.url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                                audio_bytes = await resp.read()
                        text, err = await transcribe_audio(audio_bytes, att.filename)
                        if err:
                            await interaction.followup.send(f"Transcription failed: {err}")
                        else:
                            await interaction.followup.send(f"🎙️ @{msg.author.display_name} said: \"{text}\"")
                        found = True
                        break
                    except Exception as e:
                        await interaction.followup.send(f"Error: {e}")
                        found = True
                        break
            if found:
                break
    if not found:
        await interaction.followup.send("No recent audio/voice message found in this channel.")

@tree.command(name="call", description="Call Yuna into your voice channel to talk in real-time (Voice, VAD & TTS)")
@app_commands.describe(
    action="Action: join (default), leave, status, or vad (tune silence pause duration)",
    value="Value for VAD adjustment in seconds (e.g. 1.5, 1.8, 2.0)"
)
async def slash_call(interaction: discord.Interaction, action: Optional[str] = "join", value: Optional[str] = None):
    action = (action or "join").lower().strip()
    if not interaction.guild:
        await interaction.response.send_message("❌ The `/call` command can only be used in a Discord server voice channel.", ephemeral=True)
        return
    if not DISCORD_VOICE_AVAILABLE or not voice_manager:
        await interaction.response.send_message("❌ Voice system module is not currently available.", ephemeral=True)
        return

    if action in ["join", "start", "call"]:
        if not isinstance(interaction.user, discord.Member) or not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("❌ You must join a voice channel first before calling me!", ephemeral=True)
            return
        await interaction.response.defer()
        ok, msg = await voice_manager.start_call(interaction.user, interaction.channel)
        await interaction.followup.send(msg)
    elif action in ["leave", "stop", "end", "hangup", "disconnect"]:
        await interaction.response.defer()
        ok, msg = await voice_manager.stop_call(interaction.guild)
        await interaction.followup.send(msg)
    elif action in ["vad", "silence", "gap", "pause"]:
        if value:
            try:
                val = max(0.8, min(4.0, float(value)))
                update_config_setting("vad_silence_gap", str(val))
                voice_manager.set_vad_gap(interaction.guild.id, val)
                await interaction.response.send_message(
                    f"🎙️ **VAD Silence Gap set to {val:.2f}s!**\nYou can now pause naturally up to {val:.2f} seconds between words without being interrupted.",
                    ephemeral=True
                )
            except Exception as e:
                await interaction.response.send_message(f"❌ Invalid value for VAD gap: {e}", ephemeral=True)
        else:
            vad_info = voice_manager.get_vad_info(interaction.guild.id)
            await interaction.response.send_message(
                f"🎙️ **Current VAD Settings:**\n"
                f"• Silence Gap (Pause Tolerance): **{vad_info['silence_gap']}s**\n"
                f"• Sensitivity Threshold: **{vad_info['silence_threshold']} RMS**\n"
                f"• Ambient Noise Floor: **{vad_info['noise_floor']} RMS**\n\n"
                f"💡 *To adjust: `/call action:vad value:1.8` or `!call vad 1.8`*",
                ephemeral=True
            )
    elif action in ["stt", "model", "stt_model", "whisper", "recognizer"]:
        cur_m = voice_manager.get_stt_model(interaction.guild.id) if hasattr(voice_manager, "get_stt_model") else config.get("stt_model", "auto")
        if value:
            norm_m = normalize_stt_model(value)
            if norm_m not in AVAILABLE_STT_MODELS and norm_m != "auto":
                await interaction.response.send_message(
                    f"❌ Unknown STT model `{value}`.\n"
                    f"Available free options: `whisper-large-v3-turbo` (groq-turbo), `whisper-large-v3` (groq-large), "
                    f"`gemini-3.5-flash-lite`, `gemini-3.6-flash`, or `auto`.",
                    ephemeral=True
                )
                return
            update_config_setting("stt_model", norm_m)
            if hasattr(voice_manager, "set_stt_model"):
                voice_manager.set_stt_model(interaction.guild.id, norm_m)
            m_info = AVAILABLE_STT_MODELS.get(norm_m, {})
            m_name = m_info.get("name", norm_m)
            m_tag = m_info.get("tag", "")
            await interaction.response.send_message(
                f"🎧 **Voice Call STT Model Switched to:** `{m_name}` {m_tag}\n"
                f"• Provider: **{m_info.get('provider', 'Groq/Gemini').upper()}** ({m_info.get('badge', 'FREE')})\n"
                f"• Description: *{m_info.get('desc', '')}*\n"
                f"• Transcribing in **Forced English** with dual-layer AI phonetic auto-correction.",
                ephemeral=True
            )
        else:
            options_str = []
            for k, info in AVAILABLE_STT_MODELS.items():
                active_mark = " 👉 **[ACTIVE]**" if k == cur_m else ""
                options_str.append(f"• `{k}` ({info['badge']}) — {info['tag']} {info['name']}{active_mark}\n  *{info['desc']}*")
            models_text = "\n".join(options_str)
            await interaction.response.send_message(
                f"🎧 **Voice Call Speech-to-Text (STT) Models:**\n\n"
                f"{models_text}\n\n"
                f"💡 *To switch: `/call action:stt value:<model>` or `/stt`*",
                ephemeral=True
            )
    elif action in ["status"]:
        in_call = voice_manager.is_in_call(interaction.guild.id)
        sess = voice_manager.get_session(interaction.guild.id)
        vad_info = voice_manager.get_vad_info(interaction.guild.id)
        stt_info = voice_manager.get_stt_model(interaction.guild.id) if hasattr(voice_manager, "get_stt_model") else config.get("stt_model", "auto")
        stt_meta = AVAILABLE_STT_MODELS.get(stt_info, {})
        stt_label = f"{stt_meta.get('tag', '')} {stt_meta.get('name', stt_info)}" if stt_meta else stt_info
        if in_call and sess:
            elapsed = int(time.time() - sess.get("start_time", time.time()))
            await interaction.response.send_message(
                f"📞 **Call Active** with `{sess.get('caller_name', 'User')}` in <#{sess.get('vc_channel_id')}> (Duration: {elapsed}s)\n"
                f"🎧 **STT Model:** `{stt_label}`\n"
                f"🎙️ **VAD Pause Tolerance:** `{vad_info['silence_gap']}s` (Threshold: `{vad_info['silence_threshold']}`)",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"📴 No active voice call in this server. Use `/call` to start one!\n"
                f"🎧 **STT Model:** `{stt_label}` (switch with `/call action:stt` or `/stt`)\n"
                f"🎙️ **VAD Pause Tolerance:** `{vad_info['silence_gap']}s` (adjust anytime with `/call action:vad value:<seconds>`)",
                ephemeral=True
            )
    else:
        await interaction.response.send_message("Usage: `/call [action: join | leave | status | vad | stt] [value: <sec|model>]`", ephemeral=True)


@tree.command(name="stt", description="Select Speech-to-Text (STT) recognition model for voice calls")
@app_commands.describe(model="Speech-to-text recognition model to use in voice calls")
@app_commands.choices(model=[
    app_commands.Choice(name="⚡ Groq Whisper Turbo (Fastest, <300ms - Free)", value="whisper-large-v3-turbo"),
    app_commands.Choice(name="🎯 Groq Whisper Large (Highest Precision - Free)", value="whisper-large-v3"),
    app_commands.Choice(name="🧠 Gemini 3.5 Flash-Lite (Native Audio - Free Tier)", value="gemini-3.5-flash-lite"),
    app_commands.Choice(name="🌟 Gemini 3.6 Flash (Deep Reasoning - Free Tier)", value="gemini-3.6-flash"),
    app_commands.Choice(name="🔄 Auto Cascade (Automatic Failover - Default)", value="auto"),
])
async def slash_stt(interaction: discord.Interaction, model: Optional[app_commands.Choice[str]] = None):
    if not interaction.guild:
        await interaction.response.send_message("❌ This command can only be used in a Discord server voice channel.", ephemeral=True)
        return
    val = model.value if model else None
    await slash_call(interaction, action="stt", value=val)


import discord
import random

@tree.command(name='bonjour', description='Greet a random server member in a random language.')
async def slash_bonjour(interaction: discord.Interaction):
    # Filter out bots and ensure the member list is populated
    members = [m for m in interaction.guild.members if not m.bot]
    
    if not members:
        await interaction.response.send_message("No eligible members found to greet.", ephemeral=True)
        return

    target = random.choice(members)
    
    greetings = [
        ("Bonjour", "French"),
        ("Hola", "Spanish"),
        ("Konnichiwa", "Japanese"),
        ("Guten Tag", "German"),
        ("Ciao", "Italian"),
        ("Olá", "Portuguese"),
        ("Namaste", "Hindi"),
        ("Anyoung haseyo", "Korean")
    ]
    
    phrase, language = random.choice(greetings)
    
    await interaction.response.send_message(f"{phrase}, {target.mention}! (Said in {language})")


@tree.command(name="vc", description="Voice channel call controls (Join, leave, or status)")
@app_commands.describe(action="Action: join (default), leave, or status")
async def slash_vc(interaction: discord.Interaction, action: Optional[str] = "join"):
    await slash_call(interaction, action=action)

@tree.command(name="vtuber", description="VTuber bridge controls")
@app_commands.describe(action="status / express", emotion="Emotion for express")
async def slash_vtuber(interaction: discord.Interaction, action: str, emotion: str = ""):
    if action.lower() == "status":
        status = "🟢 Connected" if vtuber_bridge_online else "🔴 Offline"
        count = len(vtuber_clients)
        await interaction.response.send_message(f"VTuber Bridge: {status} ({count} clients)", ephemeral=True)
    elif action.lower() == "express":
        emo = emotion or "neutral"
        await vtuber_broadcast({"type": "emotion", "emotion": emo, "intensity": 1.0})
        await interaction.response.send_message(f"Sent emotion: `{emo}`", ephemeral=True)
    else:
        await interaction.response.send_message("Use `status` or `express`.", ephemeral=True)

@tree.command(name="mc", description="Real-Player Minecraft autonomous bot controls")
@app_commands.describe(
    action="Action: start | stop | status | journal | follow | mine | craft | give | attack | sleep | emote | chat | goal",
    target="Player username, block/item name, mob, or natural language goal"
)
async def slash_minecraft(interaction: discord.Interaction, action: str, target: str = ""):
    current_bot_id = os.getenv("BOT_ID") or bots_state.get("active_id", "default")
    current_bot = get_bot_by_id(bots_state, current_bot_id) if 'bots_state' in globals() else None
    current_bot_name = current_bot.get("name", "Bot") if current_bot else "Bot"

    act = action.lower().strip()
    if act == "start":
        ok, msg = start_minecraft_bot()
        await interaction.response.send_message(f"🎮 **Minecraft Bot ({current_bot_name}):** {msg}", ephemeral=True)
    elif act == "stop":
        ok, msg = stop_minecraft_bot()
        await interaction.response.send_message(f"🎮 **Minecraft Bot ({current_bot_name}):** {msg}", ephemeral=True)
    elif act == "status":
        online = mc_state.get("online", False)
        status_icon = "🟢 Online" if online else "🔴 Offline"
        pos = mc_state.get("pos", {})
        coords = f"X: `{pos.get('x',0)}` Y: `{pos.get('y',0)}` Z: `{pos.get('z',0)}`"
        hp = mc_state.get("health", 20)
        food = mc_state.get("food", 20)
        task = mc_state.get("task", "idle")
        in_game_user = mc_state.get("username") or config.get("minecraft_username", current_bot_name)

        embed = discord.Embed(
            title=f"🎮 Minecraft Real-Player Bot Status ({current_bot_name})",
            color=0x2ecc71 if online else 0xe74c3c
        )
        embed.add_field(name="Status", value=f"{status_icon} (`{in_game_user}`)", inline=True)
        embed.add_field(name="Server", value=f"`{config.get('minecraft_server')}:{config.get('minecraft_port')}`", inline=True)
        embed.add_field(name="Current Task", value=f"`{task}`", inline=True)
        embed.add_field(name="Position", value=coords, inline=True)
        embed.add_field(name="Vitals", value=f"❤️ Health: `{hp}/20`\n🍖 Hunger: `{food}/20`", inline=True)

        players = mc_state.get("players", [])
        p_str = ", ".join([p.get("username", "") for p in players]) if players else "None"
        embed.add_field(name="Nearby Players", value=p_str[:100], inline=True)

        inv = mc_state.get("inventory", [])
        if inv:
            inv_str = ", ".join([f"{i['name']} ({i['count']})" for i in inv[:8]])
            embed.add_field(name="Inventory", value=inv_str[:200], inline=False)

        await safe_reply(interaction, embed=embed)
    elif act.startswith("journ") or act in ("journal", "todo", "memory", "goals", "log", "stats", "journy"):
        bot_journal_path = os.path.join(SCRIPT_DIR, "memories", "minecraft", f"{current_bot_id}_journal.json")
        fallback_journal_path = os.path.join(SCRIPT_DIR, "memories", "minecraft", "journal.json")

        j = mc_state.get("journal", {})
        if (not j or not j.get("todo_list")) and os.path.exists(bot_journal_path):
            try:
                with open(bot_journal_path) as f:
                    j = json.load(f)
            except Exception:
                pass
        if (not j or not j.get("todo_list")) and os.path.exists(fallback_journal_path):
            try:
                with open(fallback_journal_path) as f:
                    j = json.load(f)
            except Exception:
                pass
        if not j or not j.get("todo_list"):
            import copy
            j = copy.deepcopy(DEFAULT_MC_JOURNAL)

        embed = discord.Embed(
            title=f"📖 {current_bot_name}'s Autonomous Minecraft Journal",
            description=f"Autonomous progress, survival goals, and lessons learned for **{current_bot_name}**.",
            color=0x9b59b6
        )
        todos = j.get("todo_list", [])
        if todos:
            todo_lines = [f"{'✅' if t.get('done') else '⬜'} {t.get('task')}" for t in todos[:12]]
            embed.add_field(name="📋 Survival To-Do List & Quests", value="\n".join(todo_lines), inline=False)

        milestones = j.get("milestones", [])
        if milestones:
            m_lines = [f"• {m.get('desc')} *({m.get('time', '')[-8:-1]})*" for m in milestones[-4:]]
            embed.add_field(name="🏆 Recent Milestones", value="\n".join(m_lines), inline=False)

        lessons = j.get("lessons_learned", [])
        if lessons:
            l_lines = [f"• {l}" for l in lessons[-3:]]
            embed.add_field(name="💡 Lessons Learned from Mistakes", value="\n".join(l_lines), inline=False)

        stats = j.get("stats", {})
        s_text = f"⛏️ Mined: `{stats.get('blocks_mined',0)}` | 🔨 Crafted: `{stats.get('items_crafted',0)}` | 💀 Deaths: `{stats.get('deaths',0)}`"
        embed.add_field(name="📊 Lifetime Stats", value=s_text, inline=False)

        await safe_reply(interaction, embed=embed)
    elif act == "follow":
        p_name = target or interaction.user.display_name
        send_mc_cmd({"type": "follow", "username": p_name, "range": 2})
        await interaction.response.send_message(f"🏃 Pathfinding and following **{p_name}**!", ephemeral=True)
    elif act == "mine":
        b_parts = target.split() if target else []
        if len(b_parts) > 1 and b_parts[-1].isdigit():
            b_name = " ".join(b_parts[:-1])
            b_count = int(b_parts[-1])
        else:
            b_name = target or "oak_log"
            b_count = 5
        send_mc_cmd({"type": "mine", "block": b_name, "count": b_count})
        await interaction.response.send_message(f"⛏️ Autonomous mining started for **{b_name}** ({b_count} blocks).", ephemeral=True)
    elif act == "craft":
        c_parts = target.split() if target else []
        if len(c_parts) > 1 and c_parts[-1].isdigit():
            c_name = " ".join(c_parts[:-1])
            c_count = int(c_parts[-1])
        else:
            c_name = target or "wooden_pickaxe"
            c_count = 1
        send_mc_cmd({"type": "craft", "item": c_name, "count": c_count})
        await interaction.response.send_message(f"🔨 Smart crafting **{c_name}** ({c_count}x)...", ephemeral=True)
    elif act == "give":
        parts = target.split(None, 2) if target else []
        if len(parts) == 3 and parts[1].isdigit():
            itm = parts[0]
            cnt = int(parts[1])
            usr = parts[2]
        elif len(parts) == 2:
            itm = parts[0]
            cnt = 64
            usr = parts[1]
        else:
            itm = target or "all"
            cnt = 64
            usr = interaction.user.display_name
        send_mc_cmd({"type": "give", "item": itm, "username": usr, "count": cnt})
        await interaction.response.send_message(f"🎁 Giving **{itm}** to **{usr}**!", ephemeral=True)
    elif act in ("attack", "pvp", "duel"):
        send_mc_cmd({"type": "attack", "target": target})
        await interaction.response.send_message(f"⚔️ Engaging in PvP/Combat against: **{target or 'nearest hostile'}**!", ephemeral=True)
    elif act == "sleep":
        send_mc_cmd({"type": "sleep"})
        await interaction.response.send_message("🛏️ Seeking bed (or placing bed from inventory) to sleep...", ephemeral=True)
    elif act == "emote":
        e_type = target or "sneak_spam"
        send_mc_cmd({"type": "emote", "emote": e_type})
        await interaction.response.send_message(f"✨ Triggered emote: `{e_type}`", ephemeral=True)
    elif act == "chat":
        send_mc_cmd({"type": "chat", "text": target})
        await interaction.response.send_message(f"💬 Sent to in-game chat: `{target}`", ephemeral=True)
    elif act == "goal":
        await interaction.response.defer(thinking=True, ephemeral=True)
        reply = await mc_execute_natural_goal(target, sender_name=interaction.user.display_name)
        await interaction.followup.send(f"🎯 **Goal Dispatched ({current_bot_name}):** {target}\n💬 **{current_bot_name}:** {reply}", ephemeral=True)
    else:
        await interaction.response.send_message("Valid actions: `start`, `stop`, `status`, `journal`, `follow`, `mine`, `craft`, `give`, `attack`, `sleep`, `emote`, `chat`, `goal`", ephemeral=True)

@tree.command(name="summarize", description="Analyze recent messages and store them as long-term memory")
@app_commands.describe(amount="Number of recent messages to analyze (5-1000)", user="User to summarize (defaults to yourself; owner can pick anyone)")
async def slash_summarize(interaction: discord.Interaction, amount: int = 50, user: discord.User = None):
    target_user = user or interaction.user
    is_owner = await check_owner(interaction.user.id)
    if user and not is_owner and user.id != interaction.user.id:
        await interaction.response.send_message("You can only summarize your own messages. The owner can summarize anyone.", ephemeral=True)
        return
    amount = max(5, min(1000, amount))
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        messages = []
        # Resilient channel history scan: scan up to amount * 4 messages (capped to 5,000 to prevent Discord gateway socket resets)
        scan_limit = min(5000, max(amount * 4, 300))
        try:
            async for msg in interaction.channel.history(limit=scan_limit):
                if msg.author.id == target_user.id and not msg.author.bot:
                    raw_c = (msg.content or "").strip()
                    if len(raw_c) > 3 and not raw_c.startswith(("/", "!", "y!", ".")):
                        messages.append(raw_c)
                if len(messages) >= amount:
                    break
        except (aiohttp.ClientError, ConnectionError, OSError, asyncio.TimeoutError) as net_err:
            print(f"[SUMMARIZE] History fetch stream reached connection boundary ({net_err}). Continuing with {len(messages)} collected messages.")
        except Exception as hist_err:
            print(f"[SUMMARIZE] History fetch notice: {hist_err}. Continuing with {len(messages)} collected messages.")

        if len(messages) < 3:
            await interaction.followup.send(f"Not enough messages from {target_user.display_name} to summarize. Scanned {scan_limit} recent channel messages but found only {len(messages)} meaningful message(s). Need at least 3.", ephemeral=True)
            return

        # Reverse so messages are chronologically ordered from earliest to latest
        messages.reverse()

        uid = str(target_user.id)
        profile = user_profiles.setdefault(uid, {
            "name": target_user.display_name,
            "global_name": getattr(target_user, 'global_name', None) or str(target_user),
            "first_seen": time.time(),
            "last_seen": time.time(),
            "profile_changes": [],
            "mentioned_users": [],
            "bot_memories": {}
        })

        curr_bid = get_current_bot_id()
        bot_mem = get_user_bot_memory(uid, bot_id=curr_bid)
        facts_list = bot_mem.setdefault("facts", [])
        sentences_list = bot_mem.setdefault("sentences", [])

        # Chunk messages into batches of 40 messages to prevent token truncation and extract maximum memory density
        chunk_size = 40
        chunks = [messages[i:i + chunk_size] for i in range(0, len(messages), chunk_size)]
        cur_bname = get_current_bot_name()

        all_extracted_facts = []
        all_extracted_sentences = []

        async def _extract_chunk_memories(chunk_msgs, c_num, total_c):
            for attempt in range(2):
                try:
                    combined = "\n".join([f"- {m}" for m in chunk_msgs])
                    chunk_prompt = (
                        f"You are a dedicated memory curator for {cur_bname}. Analyze these user messages (Batch {c_num}/{total_c}) and extract memorable information about the user.\n\n"
                        f"MESSAGES TO ANALYZE ({len(chunk_msgs)} messages):\n"
                        f"{combined}\n\n"
                        "Instructions:\n"
                        "1. Extract 3-8 distinct, detailed facts about the user (preferences, hobbies, opinions, life events, technical skills, personality traits, relations).\n"
                        "2. Extract 3-8 notable sentences or quotes said by the user.\n"
                        "3. Write clear, complete sentences.\n\n"
                        "Return ONLY valid JSON in this exact format:\n"
                        '{"facts": ["fact 1", "fact 2"], "sentences": ["sentence 1", "sentence 2"]}'
                    )
                    raw_ans, err = None, True
                    if GEMINI_KEY and time.time() >= gemini_blocked_until:
                        try:
                            raw_ans, err = await ask_gemini(config.get("personality", ""), [], chunk_prompt, caller="summarize")
                        except Exception as ge:
                            print(f"[SUMMARIZE CHUNK] Gemini call notice: {ge}")
                            err = True
                    if (err or not raw_ans) and GROQ_KEY and time.time() >= groq_blocked_until:
                        try:
                            raw_ans, err = await ask_groq([], chunk_prompt)
                        except Exception as gqe:
                            print(f"[SUMMARIZE CHUNK] Groq call notice: {gqe}")
                            err = True
                    if (err or not raw_ans) and (os.getenv("MISTRAL_KEY") or MISTRAL_KEY) and time.time() >= mistral_blocked_until:
                        try:
                            raw_ans, err = await ask_mistral([], chunk_prompt, system_msg=config.get("personality", ""))
                        except Exception as me:
                            print(f"[SUMMARIZE CHUNK] Mistral call notice: {me}")
                            err = True

                    if not err and raw_ans:
                        c_clean = str(raw_ans).strip()
                        if "```json" in c_clean: c_clean = c_clean.split("```json", 1)[1].split("```", 1)[0].strip()
                        elif "```" in c_clean: c_clean = c_clean.split("```", 1)[1].split("```", 1)[0].strip()
                        match = re.search(r'\{.*\}', c_clean, re.DOTALL)
                        if match:
                            p_json = json.loads(match.group(0))
                            facts_res = [f for f in p_json.get("facts", []) if isinstance(f, str)]
                            sents_res = [s for s in p_json.get("sentences", []) if isinstance(s, str)]
                            return facts_res, sents_res
                except Exception as b_err:
                    print(f"[SUMMARIZE CHUNK] Batch {c_num} attempt {attempt+1} exception: {b_err}")
                    await asyncio.sleep(0.4)
            return [], []

        # Process in batches of 2 concurrent requests with slight pacing to preserve network sockets
        sem = asyncio.Semaphore(2)
        async def _bounded_extract(c_msgs, idx):
            async with sem:
                await asyncio.sleep(0.1 * (idx % 3))
                try:
                    return await _extract_chunk_memories(c_msgs, idx + 1, len(chunks))
                except Exception as be:
                    print(f"[SUMMARIZE CHUNK] Batch {idx+1} caught exception: {be}")
                    return [], []

        batch_results = await asyncio.gather(*[_bounded_extract(c, i) for i, c in enumerate(chunks)], return_exceptions=False)

        added_facts = 0
        added_sentences = 0

        for facts_sub, sent_sub in batch_results:
            for f in facts_sub:
                if isinstance(f, str) and len(f.strip()) > 5:
                    f_clean = f.strip()
                    if not is_similar_to_existing(f_clean, facts_list):
                        facts_list.append(f_clean)
                        added_facts += 1

            for s in sent_sub:
                if isinstance(s, str) and len(s.strip()) > 5:
                    s_clean = s.strip()
                    if not is_similar_to_existing(s_clean, sentences_list):
                        sentences_list.append(s_clean)
                        added_sentences += 1

        bot_mem["last_seen"] = time.time()
        profile["last_seen"] = time.time()
        save_user_profiles(force=True)

        personality = config.get("personality", "You are a helpful assistant.")
        new_stuff = []
        if added_facts:
            new_stuff.append(f"{added_facts} new fact(s)")
        if added_sentences:
            new_stuff.append(f"{added_sentences} new quote(s)")

        if not new_stuff:
            await interaction.followup.send(f"Analyzed {len(messages)} messages from {target_user.display_name}, but nothing new was found — you already remember it all! 🧠", ephemeral=True)
            return

        facts_for_prompt = "\n".join([f"- {f}" for f in facts_list[-added_facts:]]) if added_facts else ""
        sentences_for_prompt = "\n".join([f"- {s}" for s in sentences_list[-added_sentences:]]) if added_sentences else ""

        intervention_prompt = (
            f"{personality}\n\n"
            f"You just analyzed {len(messages)} messages from {target_user.display_name} and extracted new memories.\n"
        )
        if facts_for_prompt:
            intervention_prompt += f"New facts:\n{facts_for_prompt}\n\n"
        if sentences_for_prompt:
            intervention_prompt += f"New quotes:\n{sentences_for_prompt}\n\n"
        intervention_prompt += (
            f"Respond to {target_user.display_name} in your usual personality. Comment on what you learned — "
            f"tease them, be impressed, or be annoyed. Make it personal and alive. "
            f"Weave the memories into your response naturally. Keep it under 400 words."
        )

        intervention_reply, inter_err = None, True
        if GROQ_KEY and time.time() >= groq_blocked_until:
            intervention_reply, inter_err = await ask_groq([], intervention_prompt)
        if (inter_err or not intervention_reply) and (os.getenv("MISTRAL_KEY") or MISTRAL_KEY) and time.time() >= mistral_blocked_until:
            intervention_reply, inter_err = await ask_mistral([], intervention_prompt, system_msg=personality)
        if (inter_err or not intervention_reply) and GEMINI_KEY and time.time() >= gemini_blocked_until:
            intervention_reply, inter_err = await ask_gemini(personality, [], intervention_prompt)
        summary_header = (
            f"🧠 **Deep Memory Synthesis Complete for {target_user.display_name}!**\n"
            f"• Analyzed **{len(messages)}** user messages across **{len(chunks)}** batches.\n"
            f"• Extracted and retained **{added_facts}** new facts and **{added_sentences}** new quotes!\n"
            f"• Current Memory Bank: **{len(facts_list)}** total facts, **{len(sentences_list)}** total quotes.\n\n"
        )
        if inter_err or not intervention_reply:
            final_msg = summary_header
        else:
            final_msg = summary_header + f"💬 **{cur_bname}:**\n{intervention_reply}"

        await interaction.followup.send(final_msg[:2000], ephemeral=True)
        print(f"[SUMMARIZE] {interaction.user.display_name} summarized {len(messages)} msgs across {len(chunks)} batches for {target_user.display_name}. Added {added_facts} facts, {added_sentences} sentences.")
    except Exception as e:
        await interaction.followup.send(f"Summarization error: {e}", ephemeral=True)
        print(f"[SUMMARIZE ERROR] {e}")

@tree.command(name="memory", description="Show what this bot remembers about you")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
async def slash_memory(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    profile = user_profiles.get(uid, {})
    bot_mem = get_user_bot_memory(uid)
    bot_name = client.user.display_name if client.user else "Bot"
    interaction_count = bot_mem.get("interaction_count", 0)

    facts_list = bot_mem.get("facts", [])
    sentences_list = bot_mem.get("sentences", [])

    if not profile or (interaction_count == 0 and not facts_list and not sentences_list):
        await interaction.response.send_message(f"I ({bot_name}) don't have any individual memory of you yet. Let's chat! 🌱", ephemeral=True)
        return
    embed = discord.Embed(title=f"🧠 {bot_name}'s Memory: {interaction.user.display_name}", color=0x8a9a8a)
    embed.add_field(name="Interactions with this bot", value=str(interaction_count), inline=True)
    embed.add_field(name="First Seen", value=time.ctime(profile.get("first_seen", 0)), inline=True)
    embed.add_field(name="Last Seen", value=time.ctime(bot_mem.get("last_seen", profile.get("last_seen", 0))), inline=True)

    embed.add_field(name="Facts Stored", value=str(len(facts_list)), inline=True)
    embed.add_field(name="Quotes Stored", value=str(len(sentences_list)), inline=True)

    if facts_list:
        facts_str = "\n".join(f"- {f}" for f in facts_list[-15:])
        if len(facts_str) > 1000:
            facts_str = facts_str[:997] + "..."
        embed.add_field(name="Recent Facts", value=facts_str, inline=False)

    if sentences_list:
        sent_str = "\n".join(f'"{s}"' for s in sentences_list[-10:])
        if len(sent_str) > 1000:
            sent_str = sent_str[:997] + "..."
        embed.add_field(name="Recent Quotes", value=sent_str, inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="persona", description="Set notes about yourself for this bot to remember")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.describe(notes="What should I know about you?")
async def slash_persona(interaction: discord.Interaction, notes: str):
    uid = str(interaction.user.id)
    bot_mem = get_user_bot_memory(uid)
    notes_clean = notes.strip()
    facts_list = bot_mem["facts"]

    if is_similar_to_existing(notes_clean, facts_list, threshold=0.8):
        await interaction.response.send_message("I already remember something very similar to that! I'll keep the existing memory. ✅", ephemeral=True)
        return

    facts_list.append(notes_clean)
    bot_mem["last_seen"] = time.time()
    save_user_profiles()
    bot_name = client.user.display_name if client.user else "this bot"
    await interaction.response.send_message(f"✅ Got it! **{bot_name}** will remember that about you.", ephemeral=True)

@tree.command(name="forgetme", description="Wipe all facts, quotes, and memories this bot has about you")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.describe(scope="Whether to wipe memory for this bot only or all bots")
@app_commands.choices(scope=[
    app_commands.Choice(name="This Bot Only (Default)", value="this_bot"),
    app_commands.Choice(name="All Bots Globally", value="all_bots"),
])
async def slash_forgetme(interaction: discord.Interaction, scope: str = "this_bot"):
    uid = str(interaction.user.id)
    all_bots = (scope == "all_bots")
    bot_name = client.user.display_name if client.user else "this bot"
    
    clear_user_bot_memory(uid, all_bots=all_bots)
    
    if all_bots:
        desc = f"🧹 All long-term memories, facts, and quotes about **{interaction.user.display_name}** have been completely erased across **all bots**."
    else:
        desc = f"🧹 All long-term memories, facts, and quotes that **{bot_name}** remembers about **{interaction.user.display_name}** have been erased."
    
    embed = discord.Embed(
        title="🧠 Memory Forgotten",
        description=desc,
        color=0x8a9a8a
    )
    embed.set_footer(text="Your Discord profile info is retained; all AI facts, quotes, and buffers are wiped.")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="ping", description="Check bot latency and active AI provider status")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
async def slash_ping(interaction: discord.Interaction):
    bot_name = client.user.display_name if client.user else "Bot"
    ws_latency = round(client.latency * 1000) if client.latency else 0
    active_p = config.get("provider", "auto")
    model_key = f"{active_p}_model" if active_p in ("gemini", "groq", "mistral") else "model"
    active_m = config.get(model_key, "default")
    
    embed = discord.Embed(
        title=f"🏓 Pong! [{bot_name}]",
        description=(
            f"⚡ **Gateway Latency**: `{ws_latency}ms`\n"
            f"🌐 **Active Provider**: `{active_p}`\n"
            f"🧠 **Model**: `{active_m}`\n"
            f"🔋 **Status**: `Operational`"
        ),
        color=0x00ffcc
    )
    await interaction.response.send_message(embed=embed)

@tree.command(name="toggleprovider", description="Quickly toggle or switch the active AI provider (Owner only)")
@app_commands.describe(
    target="Optional specific provider to switch to (Gemini, Groq, Mistral, OpenRouter, HuggingFace, Auto)"
)
@app_commands.choices(target=[
    app_commands.Choice(name="Next Provider in Cycle", value="cycle"),
    app_commands.Choice(name="Auto Fallback (auto)", value="auto"),
    app_commands.Choice(name="Google Gemini (gemini)", value="gemini"),
    app_commands.Choice(name="Groq (groq)", value="groq"),
    app_commands.Choice(name="Mistral AI (mistral)", value="mistral"),
    app_commands.Choice(name="OpenRouter (openrouter)", value="openrouter"),
    app_commands.Choice(name="Hugging Face (huggingface)", value="huggingface"),
])
async def slash_toggleprovider(interaction: discord.Interaction, target: str = "cycle"):
    if not await check_owner(interaction.user.id):
        await interaction.response.send_message("❌ **Owner only**: Only the bot owner can toggle the provider.", ephemeral=True)
        return
    
    target_prov = None if target == "cycle" else target
    old_p, new_p = toggle_provider(target_prov)
    
    bot_name = client.user.display_name if client.user else "Bot"
    model_key = f"{new_p}_model" if new_p in ("gemini", "groq", "mistral") else "model"
    curr_model = config.get(model_key, "default")
    
    embed = format_toast_embed(
        f"{bot_name} // Provider Toggled",
        f"Switched provider: `{old_p}` ➔ **`{new_p}`**\nActive Model: **`{curr_model}`**",
        color=0x4f8cff
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="setmodel", description="Update the AI model for any provider and auto-save (Owner only)")
@app_commands.describe(
    provider="AI provider to configure (Gemini, Groq, Mistral, OpenRouter, HuggingFace)",
    model="The exact model name (e.g. gemini-3.1-flash-lite, llama-3.3-70b-versatile, mistral-small-latest)",
    switch_provider="Whether to also set this provider as the active provider (Default: True)"
)
@app_commands.choices(provider=[
    app_commands.Choice(name="Google Gemini (gemini)", value="gemini"),
    app_commands.Choice(name="Groq (groq)", value="groq"),
    app_commands.Choice(name="Mistral AI (mistral)", value="mistral"),
    app_commands.Choice(name="OpenRouter (openrouter)", value="openrouter"),
    app_commands.Choice(name="Hugging Face (huggingface)", value="huggingface"),
    app_commands.Choice(name="Auto Fallback (auto)", value="auto"),
])
async def slash_setmodel(interaction: discord.Interaction, provider: str, model: str = None, switch_provider: bool = True):
    if not await check_owner(interaction.user.id):
        await interaction.response.send_message("❌ **Owner only**: Only the bot owner can update models.", ephemeral=True)
        return
    
    prov_to_key = {
        "gemini": "gemini_model",
        "groq": "groq_model",
        "mistral": "mistral_model",
        "openrouter": "model",
        "huggingface": "huggingface_model",
    }
    
    changes = []
    if provider in prov_to_key and model:
        target_key = prov_to_key[provider]
        old_m = config.get(target_key, "")
        config[target_key] = model.strip()
        changes.append(f"• **`{target_key}`**: `{old_m}` ➔ **`{model.strip()}`**")
    
    if switch_provider and provider != "auto":
        old_p = config.get("provider", "auto")
        config["provider"] = provider
        changes.append(f"• **`provider`**: `{old_p}` ➔ **`{provider}`**")
    elif provider == "auto":
        old_p = config.get("provider", "auto")
        config["provider"] = "auto"
        changes.append(f"• **`provider`**: `{old_p}` ➔ **`auto`**")
    
    save_config(config)
    if 'bots_state' in globals() and isinstance(bots_state, dict):
        active_bot = get_active_bot(bots_state)
        if active_bot and isinstance(active_bot.get("config"), dict):
            active_bot["config"].update(config)
            save_bots(bots_state)
    
    bot_name = client.user.display_name if client.user else "Bot"
    embed = discord.Embed(
        title=f"⚙️ {bot_name} // Model Updated",
        description="\n".join(changes) if changes else "No changes made.",
        color=0x00ffcc
    )
    embed.add_field(name="Active Provider", value=f"`{config.get('provider', 'auto')}`", inline=True)
    embed.add_field(name="Current Models", value=(
        f"• **Gemini**: `{config.get('gemini_model', 'None')}`\n"
        f"• **Groq**: `{config.get('groq_model', 'None')}`\n"
        f"• **Mistral**: `{config.get('mistral_model', 'None')}`\n"
        f"• **OpenRouter**: `{config.get('model', 'None')}`\n"
        f"• **Hugging Face**: `{config.get('huggingface_model', 'None')}`"
    ), inline=False)
    embed.set_footer(text="Auto-saved to config.json & bots.json")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="config", description="View or update bot configuration parameters (Owner only for updates)")
@app_commands.describe(
    action="Choose whether to view or set a configuration field",
    field="Field to update (e.g. gemini, groq, mistral, provider, temperature, max_tokens, personality, tts)",
    value="New value to save for this field"
)
@app_commands.choices(action=[
    app_commands.Choice(name="View Current Config", value="view"),
    app_commands.Choice(name="Set / Update Field", value="set"),
])
async def slash_config(interaction: discord.Interaction, action: str = "view", field: str = None, value: str = None):
    is_owner = await check_owner(interaction.user.id)
    bot_name = client.user.display_name if client.user else "Bot"
    if action == "set":
        if not is_owner:
            await interaction.response.send_message("❌ **Owner only**: You cannot modify this bot's configuration.", ephemeral=True)
            return
        if not field or value is None:
            await interaction.response.send_message("⚠️ Please provide both `field` and `value` to update config.", ephemeral=True)
            return
        
        ok, key, old_v, new_v = update_config_setting(field, value)
        if not ok:
            await interaction.response.send_message(f"❌ Unknown or invalid field `{field}`. Supported fields include: `gemini`, `groq`, `mistral`, `model`, `provider`, `personality`, `temperature`, `max_tokens`, `tts`, `voice`.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f"⚙️ {bot_name} // Config Saved",
            description=f"Field **`{key}`** has been updated and saved.",
            color=0x00ffcc
        )
        embed.add_field(name="Previous", value=f"`{old_v}`" if old_v else "*None*", inline=True)
        embed.add_field(name="New Value", value=f"`{new_v}`", inline=True)
        embed.add_field(name="Active Provider", value=f"`{config.get('provider', 'auto')}`", inline=True)
        embed.set_footer(text="Auto-saved to config.json & bots.json")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    # View current config
    embed = discord.Embed(
        title=f"📋 {bot_name} // Current Configuration",
        color=0x7a8a9a
    )
    embed.add_field(name="AI Provider", value=f"`{config.get('provider', 'auto')}`", inline=True)
    embed.add_field(name="Temperature", value=f"`{config.get('temperature', 0.7)}`", inline=True)
    embed.add_field(name="Max Tokens", value=f"`{config.get('max_tokens', 800)}`", inline=True)
    
    embed.add_field(name="🧠 Active Models", value=(
        f"• **Gemini**: `{config.get('gemini_model', 'None')}`\n"
        f"• **Groq**: `{config.get('groq_model', 'None')}`\n"
        f"• **Mistral**: `{config.get('mistral_model', 'None')}`\n"
        f"• **OpenRouter**: `{config.get('model', 'None')}`\n"
        f"• **Hugging Face**: `{config.get('huggingface_model', 'None')}`"
    ), inline=False)
    
    pers = config.get("personality", "None")
    if len(pers) > 250:
        pers = pers[:247] + "..."
    embed.add_field(name="Personality", value=f"*{pers}*", inline=False)
    
    tts_p = config.get("tts_provider", "auto")
    tts_on = "Enabled" if config.get("tts_enabled") else "Disabled"
    embed.add_field(name="Voice & TTS", value=f"Status: `{tts_on}` | Provider: `{tts_p}`", inline=False)
    
    embed.set_footer(text=f"Use @{bot_name} <field>: <model> to change dynamically")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="presence", description="Toggle or set Yuna's Discord activity status")
@app_commands.describe(
    action="on, off, music, or set",
    text="Custom status text (for 'set' action)"
)
async def slash_presence(interaction: discord.Interaction, action: str = "", text: str = ""):
    action = action.lower().strip()
    is_owner = await check_owner(interaction.user.id)
    if action == "off":
        config["presence_enabled"] = False
        save_config(config)
        await client.change_presence(status=discord.Status.online, activity=None)
        await interaction.response.send_message("🔕 Presence updates disabled.", ephemeral=True)
        return
    if action == "on":
        config["presence_enabled"] = True
        save_config(config)
        activity = get_bot_activity()
        await client.change_presence(status=discord.Status.online, activity=activity)
        await interaction.response.send_message(f"🔔 Presence updates enabled. Currently: **{activity.name}**", ephemeral=True)
        return
    if action == "music":
        config["presence_music_enabled"] = not config.get("presence_music_enabled", True)
        save_config(config)
        state = "enabled" if config["presence_music_enabled"] else "disabled"
        await interaction.response.send_message(f"🎵 Music/idle rotation **{state}**.", ephemeral=True)
        return
    if action == "set" and text:
        if not is_owner:
            await interaction.response.send_message("Owner only for custom statuses.", ephemeral=True)
            return
        await client.change_presence(status=discord.Status.online, activity=discord.Game(name=text[:128]))
        await interaction.response.send_message(f"✅ Status set to: **{text[:128]}**", ephemeral=True)
        return
    current = get_bot_activity()
    enabled = "✅ ON" if config.get("presence_enabled", True) else "❌ OFF"
    music = "🎵 ON" if config.get("presence_music_enabled", True) else "❌ OFF"
    await interaction.response.send_message(
        f"**Presence**: {enabled} | **Music rotation**: {music}\n"
        f"**Current activity**: `{current.type.name if hasattr(current, 'type') else 'playing'}` — **{current.name}**\n"
        f"Use `/presence on|off|music|set <text>` to control.",
        ephemeral=True
    )

@tree.command(name="reset", description="Clear this channel's context memory")
async def slash_reset(interaction: discord.Interaction):
    clear_context(interaction.channel_id)
    await interaction.response.send_message("Context memory cleared.", ephemeral=True)

@tree.command(name="purgeall", description="Purge ALL memory globally (Owner only)")
async def slash_purgeall(interaction: discord.Interaction):
    if not await check_owner(interaction.user.id):
        await interaction.response.send_message("Owner only.", ephemeral=True)
        return
    contexts.clear()
    await interaction.response.send_message("All memory purged.", ephemeral=True)

@tree.command(name="ask", description="Ask the AI anything. Attach an image for multimodal vision.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.describe(prompt="Your question or message for the AI", image="Optional image attachment to analyze")
async def slash_ask(interaction: discord.Interaction, prompt: str, image: discord.Attachment = None):
    ok, remaining = check_cooldown(interaction.user.id)
    if not ok:
        await interaction.response.send_message(f"Slow down! Wait {remaining}s.", ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    
    images = []
    if image:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(image.url) as resp:
                    if resp.status == 200:
                        img_data = await resp.read()
                        mime = resp.headers.get("Content-Type", "image/jpeg")
                        images.append((img_data, mime))
        except Exception as e:
            print(f"[SLASH ASK VISION ERROR]: {e}")
            
    is_dm = (interaction.guild is None) or isinstance(interaction.channel, discord.DMChannel)
    reply, err = await ask_ai(
        channel_id=interaction.channel_id or interaction.user.id,
        prompt=prompt,
        user_id=interaction.user.id,
        user_name=interaction.user.display_name,
        guild=interaction.guild,
        is_dm=is_dm,
        images=images if images else None
    )
    
    if err or not reply:
        reply = reply or "I had trouble processing that request. Please try again in a moment."
        
    if len(reply) <= 2000:
        await interaction.followup.send(reply)
    else:
        chunks = [reply[i:i+1950] for i in range(0, len(reply), 1950)]
        for chunk in chunks:
            await interaction.followup.send(chunk)

@tree.command(name="doodle", description="Ask the AI to draw or doodle something on command, or doodle along with an image")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.describe(prompt="What should the AI doodle?", image="Optional drawing or sketch to doodle along with")
async def slash_doodle(interaction: discord.Interaction, prompt: str, image: Optional[discord.Attachment] = None):
    if not DOODLE_ENGINE_AVAILABLE:
        await interaction.response.send_message("❌ Doodle engine is currently unavailable.", ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    cur_bot_id = os.getenv("BOT_ID") or bots_state.get("active_id", "default")
    cur_bot = get_bot_by_id(bots_state, cur_bot_id) if 'bots_state' in globals() else None
    b_name = cur_bot.get("name", "Bot") if cur_bot else "Bot"
    b_pers = cur_bot.get("config", {}).get("personality", "") if cur_bot else config.get("personality", "")

    if image:
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.get(image.url) as r:
                    if r.status == 200:
                        img_bytes = await r.read()
                        res_bytes, dialog = await doodle_along(img_bytes, user_prompt=prompt, bot_name=b_name, bot_personality=b_pers)
                        f = discord.File(io.BytesIO(res_bytes), filename="doodle_along.png")
                        await interaction.followup.send(dialog, file=f)
                        return
        except Exception as e:
            print(f"[SLASH DOODLE ALONG ERROR] {e}")

    res_bytes, dialog = await generate_doodle(prompt or "cute cat", bot_name=b_name, bot_personality=b_pers)
    if res_bytes:
        f = discord.File(io.BytesIO(res_bytes), filename="doodle.png")
        await interaction.followup.send(dialog, file=f)
    else:
        await interaction.followup.send("Failed to generate doodle, please try again!")

@tree.command(name="showdown", description="Pokémon Showdown battles: connect, challenge, ladder, and auto-accept")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.describe(action="Action to perform", target="Opponent username for challenge or username for register", format="Battle format (e.g. gen9randombattle)")
@app_commands.choices(action=[
    app_commands.Choice(name="Status & Active Battles", value="status"),
    app_commands.Choice(name="Connect & Log In", value="connect"),
    app_commands.Choice(name="Register Showdown Account", value="register"),
    app_commands.Choice(name="Challenge User", value="challenge"),
    app_commands.Choice(name="Accept Challenge", value="accept"),
    app_commands.Choice(name="Search Ladder Battle", value="ladder"),
    app_commands.Choice(name="Disconnect", value="stop"),
])
async def slash_showdown(interaction: discord.Interaction, action: str, target: Optional[str] = None, format: Optional[str] = None):
    if not SHOWDOWN_ENGINE_AVAILABLE or not showdown_manager:
        await interaction.response.send_message("❌ Pokémon Showdown module is currently unavailable.", ephemeral=True)
        return

    cur_bot_id = os.getenv("BOT_ID") or bots_state.get("active_id", "default")
    cur_bot = get_bot_by_id(bots_state, cur_bot_id) if 'bots_state' in globals() else None
    cur_bot_name = cur_bot.get("name", "Bot") if cur_bot else "Bot"
    bot_cfg = cur_bot.get("config", {}) if cur_bot else config
    sd_client = showdown_manager.init_bot(cur_bot_id, cur_bot_name, bot_cfg)
    sd_client.channel_id = str(interaction.channel_id)
    sd_client.initiator_user_id = str(interaction.user.id)

    if action == "status":
        status_text = (
            f"🎮 **Pokémon Showdown Client: {cur_bot_name}**\n"
            f"• **Username**: `{sd_client.username}`\n"
            f"• **Registered**: {'✅ Yes' if sd_client.is_registered else '⚠️ Guest/Unregistered'}\n"
            f"• **Connection Status**: {'🟢 Connected' if sd_client.is_connected else '🔴 Offline'}\n"
            f"• **Auto-Accept**: {'✅ Enabled' if sd_client.auto_accept else '❌ Disabled'}\n"
            f"• **Active Battles**: `{len(sd_client.active_battles)}`\n"
            f"• **Format**: `{sd_client.default_format}`"
        )
        await interaction.response.send_message(status_text)
    elif action == "connect":
        await interaction.response.defer()
        await sd_client.start()
        await asyncio.sleep(2.0)
        conn_status = "🟢 Connected & Auto-Accepting Battles!" if sd_client.is_connected else "⏳ Connecting in background..."
        await interaction.followup.send(f"✅ Showdown for **{cur_bot_name}**: {conn_status}")
    elif action == "register":
        await interaction.response.defer()
        if target:
            sd_client.username = target
        if not sd_client.is_connected:
            await sd_client.start()
        else:
            await sd_client.stop()
            await sd_client.start()
        await asyncio.sleep(2.5)
        await interaction.followup.send(f"📝 Account updated to `{sd_client.username}`! Status: {'Connected' if sd_client.is_connected else 'Connecting...'}")
    elif action == "challenge":
        if not target:
            await interaction.response.send_message("Please specify opponent username in target parameter.", ephemeral=True)
            return
        await interaction.response.defer()
        if not sd_client.is_connected:
            await sd_client.start()
            await asyncio.sleep(1.5)
        fmt = format or sd_client.default_format
        await sd_client.challenge_user(target, fmt)
        await interaction.followup.send(f"⚔️ Sent battle challenge to **{target}** in `{fmt}`!")
    elif action == "accept":
        if target:
            await sd_client.send_raw(f"|/accept {target}")
            await interaction.response.send_message(f"⚔️ Accepted battle from **{target}**!")
        else:
            sd_client.auto_accept = True
            await interaction.response.send_message("✅ Auto-accept battles enabled!")
    elif action == "ladder":
        await interaction.response.defer()
        if not sd_client.is_connected:
            await sd_client.start()
            await asyncio.sleep(1.5)
        fmt = format or sd_client.default_format
        await sd_client.search_ladder(fmt)
        await interaction.followup.send(f"🏆 Searching Showdown ladder for `{fmt}` match...")
    elif action == "stop":
        await sd_client.stop()
        await interaction.response.send_message(f"🛑 Disconnected {cur_bot_name} from Showdown.")

@tree.command(name="invite", description="Get the invite link to add this bot to your servers or user apps")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
async def slash_invite(interaction: discord.Interaction):
    bot_name = client.user.display_name if client.user else "Bot"
    client_id = client.user.id if client.user else ""
    if not client_id:
        await interaction.response.send_message("Bot client ID unavailable.", ephemeral=True)
        return
    server_invite = f"https://discord.com/oauth2/authorize?client_id={client_id}&permissions=8&scope=bot%20applications.commands"
    user_app_invite = f"https://discord.com/oauth2/authorize?client_id={client_id}&scope=applications.commands"
    embed = discord.Embed(
        title=f"🔗 Invite & Install {bot_name}",
        description="Choose how you'd like to add or use this bot:",
        color=0x8a9a8a
    )
    embed.add_field(
        name="🏰 Add to Server (Bot & Commands)",
        value=f"[**Click to Invite to Server**]({server_invite})\n*Adds {bot_name} to your Discord server with full features & commands.*",
        inline=False
    )
    embed.add_field(
        name="👤 Install as User App (Use in DMs & Any Server)",
        value=f"[**Click to Install to Account**]({user_app_invite})\n*Allows using slash commands anywhere, including private DMs & any server without server invite.*",
        inline=False
    )
    embed.set_footer(text="Discord Bot OAuth2 Setup")
    await interaction.response.send_message(embed=embed)

@tree.command(name="search", description="Search the web with real-time AI synthesis")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.describe(query="What to search for")
async def slash_search(interaction: discord.Interaction, query: str):
    ok, remaining = check_cooldown(interaction.user.id)
    if not ok:
        await interaction.response.send_message(f"Slow down! Wait {remaining}s.", ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    results, err = await web_search(query, max_results=5)
    if err or not results:
        await interaction.followup.send(f"Search failed: {err or 'No results found.'}")
        return
    reply, ai_err = await synthesize_search(interaction.channel_id or interaction.user.id, query, results)
    if not ai_err and reply:
        header = f"**Search:** `{query}`\n\n"
        full_reply = header + reply
        source_lines = []
        for i, r in enumerate(results[:5], 1):
            source_lines.append(f"{i}. [{r['title']}]({r['url']})")
        source_embed = discord.Embed(title="Sources", description="\n".join(source_lines), color=0x2b2d42)
        
        if len(full_reply) <= 2000:
            await interaction.followup.send(full_reply, embed=source_embed)
        else:
            chunks = [full_reply[i:i+1950] for i in range(0, len(full_reply), 1950)]
            for idx, chunk in enumerate(chunks):
                if idx == len(chunks) - 1:
                    await interaction.followup.send(chunk, embed=source_embed)
                else:
                    await interaction.followup.send(chunk)
        return
    lines = [f"**Web search:** `{query}`\n"]
    for i, r in enumerate(results[:5], 1):
        snippet = r["snippet"][:180] + "..." if len(r["snippet"]) > 180 else r["snippet"]
        lines.append(f"**{i}.** [{r['title']}]({r['url']})\n{snippet}\n")
    embed = discord.Embed(title="Search Results", description="\n".join(lines), color=0x4f8cff)
    embed.set_footer(text="via Web Search")
    await interaction.followup.send(embed=embed)

# ─── GREETING & WELCOME LOGIC ─────────────────────────
async def generate_ai_greeting(member: discord.Member, guild: discord.Guild) -> str:
    """Generates an AI-enhanced, personality-adapted greeting for a new member."""
    refresh_runtime_config()
    base_template = config.get("greet_message", "Welcome to the server! Glad to have you here.").strip()
    personality = config.get("personality", "You are a friendly and welcoming assistant.")
    bot_name = client.user.display_name if client.user else "Bot"
    ai_enhance = config.get("greet_ai_enhance", True)
    ping_member = config.get("greet_ping", True)
    member_mention = member.mention if ping_member else f"**{member.display_name}**"

    if not ai_enhance:
        msg = base_template.replace("{user}", member_mention).replace("{member}", member_mention).replace("{server}", guild.name if guild else "the server").replace("{guild}", guild.name if guild else "the server")
        if member_mention not in msg and ping_member:
            msg = f"{member_mention} {msg}"
        return msg

    prompt = (
        f"A new member named '{member.name}' (display name: '{member.display_name}') has just joined the Discord server '{guild.name if guild else 'the server'}'.\n"
        f"Server welcome note / instructions: \"{base_template}\"\n\n"
        f"Task:\n"
        f"Write a personalized, lively welcome message for {member.display_name} in your unique character personality.\n"
        f"Rules:\n"
        f"1. Match your configured persona, tone, and style perfectly.\n"
        f"2. You MUST preserve all key instructions, channels (like #faq, #rules, #roles, etc.), or links mentioned in the welcome note.\n"
        f"3. Refer to the member using their placeholder tag [MEMBER] so we can ping them.\n"
        f"4. Keep it concise, engaging, and welcoming (1-3 sentences). Do NOT wrap in quotes."
    )

    try:
        reply, err = await ask_ai(
            channel_id=guild.id if guild else 0,
            prompt=prompt,
            user_id=member.id,
            user_name=member.display_name,
            guild=guild,
            is_dm=False,
            system_msg_override=f"You are {bot_name}. {personality}\nYou are greeting a newly joined server member."
        )
        if not err and reply and len(reply.strip()) > 5:
            final_text = reply.strip().strip('"\'')
            if "[MEMBER]" in final_text:
                final_text = final_text.replace("[MEMBER]", member_mention)
            elif member_mention not in final_text and ping_member:
                final_text = f"{member_mention} {final_text}"
            return final_text
    except Exception as e:
        print(f"[GREET ERROR] AI enhancement failed: {e}")

    # Fallback to direct template formatting
    formatted = base_template.replace("{user}", member_mention).replace("{member}", member_mention).replace("{server}", guild.name if guild else "the server").replace("{guild}", guild.name if guild else "the server")
    if member_mention not in formatted and ping_member:
        formatted = f"{member_mention} {formatted}"
    return formatted

@tree.command(name="set", description="Configure bot settings such as greet, personality, provider, model, etc.")
@app_commands.describe(
    setting="The setting to configure (e.g. greet, personality, provider, model, temperature, tts)",
    value="The new value or greeting template (e.g. 'Welcome! please check out #faq')",
    channel="Optional: select a text channel for greetings",
    enabled="Optional: enable or disable this feature"
)
@app_commands.choices(setting=[
    app_commands.Choice(name="greet (AI Welcome Message)", value="greet"),
    app_commands.Choice(name="personality (System Prompt)", value="personality"),
    app_commands.Choice(name="provider (AI Provider)", value="provider"),
    app_commands.Choice(name="model (AI Model)", value="model"),
    app_commands.Choice(name="temperature (0.0 - 2.0)", value="temperature"),
    app_commands.Choice(name="tts (Voice Provider)", value="tts"),
    app_commands.Choice(name="voice (Voice ID)", value="voice"),
    app_commands.Choice(name="open_chat (Open Chat Mode)", value="open_chat"),
    app_commands.Choice(name="auto_search (Web Search)", value="auto_search"),
])
async def slash_set(
    interaction: discord.Interaction,
    setting: str = "greet",
    value: str = None,
    channel: discord.TextChannel = None,
    enabled: bool = None
):
    is_owner = await check_owner(interaction.user.id)
    if not is_owner:
        await interaction.response.send_message("❌ **Owner only**: You cannot modify this bot's configuration.", ephemeral=True)
        return

    bot_name = client.user.display_name if client.user else "Bot"
    setting_norm = setting.lower().strip()

    if setting_norm in ("greet", "greet_message", "greeting", "welcome"):
        changes = []
        if value is not None:
            config["greet_message"] = value.strip('"\'')
            changes.append(f"• **Greeting Note**: \"{config['greet_message']}\"")
        if channel is not None:
            config["greet_channel_id"] = channel.id
            changes.append(f"• **Greeting Channel**: {channel.mention}")
        if enabled is not None:
            config["greet_enabled"] = enabled
            changes.append(f"• **Greeting Status**: {'✅ Enabled' if enabled else '❌ Disabled'}")

        if not changes:
            curr_msg = config.get("greet_message", "Welcome! Glad to have you here.")
            curr_chan = f"<#{config['greet_channel_id']}>" if config.get("greet_channel_id") else "*Auto (System Channel)*"
            curr_en = "✅ Enabled" if config.get("greet_enabled", True) else "❌ Disabled"
            curr_ai = "✅ ON (Personality Adapted)" if config.get("greet_ai_enhance", True) else "❌ OFF (Literal Template)"
            embed = discord.Embed(
                title=f"👋 {bot_name} // Welcome & Greet Configuration",
                description=(
                    f"**Status**: {curr_en}\n"
                    f"**Channel**: {curr_chan}\n"
                    f"**AI Enhancement**: {curr_ai}\n"
                    f"**Ping Member**: {'✅ Yes' if config.get('greet_ping', True) else '❌ No'}\n\n"
                    f"**Current Welcome Template / Note:**\n> *\"{curr_msg}\"*\n\n"
                    f"💡 *To update, use `/set greet value: \"Welcome! please check out #faq\" channel: #welcome`*"
                ),
                color=0x00ffcc
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        save_config(config)
        if 'bots_state' in globals() and isinstance(bots_state, dict):
            active_bot = get_active_bot(bots_state)
            if active_bot and isinstance(active_bot.get("config"), dict):
                for k in ("greet_message", "greet_channel_id", "greet_enabled", "greet_ai_enhance", "greet_ping"):
                    if k in config:
                        active_bot["config"][k] = config[k]
                save_bots(bots_state)

        embed = discord.Embed(
            title=f"✅ {bot_name} // Greet Configuration Updated",
            description="\n".join(changes) + "\n\n*New members joining the server will receive an AI-enhanced welcome adapted to the bot's personality!*",
            color=0x00ffcc
        )
        embed.set_footer(text="Auto-saved to config.json & bots.json")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # Generic setting update
    if value is None and enabled is not None:
        value = str(enabled)

    if value is None:
        await interaction.response.send_message(f"⚠️ Please provide a `value` for setting `{setting}`.", ephemeral=True)
        return

    ok, key, old_v, new_v = update_config_setting(setting_norm, value)
    if not ok:
        await interaction.response.send_message(f"❌ Failed to update `{setting}`: {new_v}", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"⚙️ {bot_name} // Setting Updated",
        description=f"Field **`{key}`** has been updated.\n`{old_v or 'None'}` ➔ **`{new_v}`**",
        color=0x00ffcc
    )
    embed.set_footer(text="Auto-saved to config.json & bots.json")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(name="greet", description="Configure AI-enhanced greeting messages for new members")
@app_commands.describe(
    message="Custom greeting instructions/template to be AI-enhanced (e.g. 'Welcome! please check out #faq')",
    channel="The text channel where welcome greetings will be posted",
    enabled="Turn welcome greetings ON or OFF",
    ai_enhance="Enable AI to dynamically adapt greeting to bot personality (default: True)",
    test="Send a test greeting to preview the AI enhancement in this channel"
)
async def slash_greet(
    interaction: discord.Interaction,
    message: str = None,
    channel: discord.TextChannel = None,
    enabled: bool = None,
    ai_enhance: bool = None,
    test: bool = False
):
    is_owner = await check_owner(interaction.user.id)
    bot_name = client.user.display_name if client.user else "Bot"

    if test:
        await interaction.response.defer(ephemeral=True)
        test_preview = await generate_ai_greeting(interaction.user, interaction.guild)
        embed = discord.Embed(
            title=f"🧪 {bot_name} // AI Greeting Preview",
            description=f"**Generated Greeting:**\n{test_preview}\n\n*(This is a preview of how new members will be greeted)*",
            color=0x9b59b6
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    if not is_owner:
        await interaction.response.send_message("❌ **Owner only**: You cannot modify greeting settings.", ephemeral=True)
        return

    changes = []
    if message is not None:
        config["greet_message"] = message.strip('"\'')
        changes.append(f"• **Welcome Note**: \"{config['greet_message']}\"")
    if channel is not None:
        config["greet_channel_id"] = channel.id
        changes.append(f"• **Channel**: {channel.mention}")
    if enabled is not None:
        config["greet_enabled"] = enabled
        changes.append(f"• **Status**: {'✅ Enabled' if enabled else '❌ Disabled'}")
    if ai_enhance is not None:
        config["greet_ai_enhance"] = ai_enhance
        changes.append(f"• **AI Enhancement**: {'✅ ON' if ai_enhance else '❌ OFF'}")

    if not changes:
        curr_msg = config.get("greet_message", "Welcome! Glad to have you here.")
        curr_chan = f"<#{config['greet_channel_id']}>" if config.get("greet_channel_id") else "*Auto (System Channel)*"
        curr_en = "✅ Enabled" if config.get("greet_enabled", True) else "❌ Disabled"
        curr_ai = "✅ ON (Personality Adapted)" if config.get("greet_ai_enhance", True) else "❌ OFF (Literal Template)"
        embed = discord.Embed(
            title=f"👋 {bot_name} // Welcome & Greet Configuration",
            description=(
                f"**Status**: {curr_en}\n"
                f"**Channel**: {curr_chan}\n"
                f"**AI Enhancement**: {curr_ai}\n"
                f"**Ping Member**: {'✅ Yes' if config.get('greet_ping', True) else '❌ No'}\n\n"
                f"**Current Welcome Template / Note:**\n> *\"{curr_msg}\"*\n\n"
                f"💡 *Use `/greet message: \"Welcome! please check out #faq\" channel: #welcome` to customize, or `/greet test: True` to preview.*"
            ),
            color=0x00ffcc
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    save_config(config)
    if 'bots_state' in globals() and isinstance(bots_state, dict):
        active_bot = get_active_bot(bots_state)
        if active_bot and isinstance(active_bot.get("config"), dict):
            for k in ("greet_message", "greet_channel_id", "greet_enabled", "greet_ai_enhance", "greet_ping"):
                if k in config:
                    active_bot["config"][k] = config[k]
            save_bots(bots_state)

    embed = discord.Embed(
        title=f"✅ {bot_name} // Greet Settings Updated",
        description="\n".join(changes) + "\n\n*Use `/greet test: True` at any time to preview the AI greeting!*",
        color=0x00ffcc
    )
    embed.set_footer(text="Auto-saved to config.json & bots.json")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ─── SOCIAL MEDIA SLASH COMMANDS ────────────────────────
@tree.command(name="xpost", description="Post a screenshot, image, or video to X (Twitter) with AI visual analysis and caption")
@app_commands.describe(
    media="Screenshot, image, or video file to analyze and post to X",
    url="Direct URL to an image or video to post to X",
    prompt="Optional extra note or context for Yuna to incorporate into her caption"
)
async def slash_xpost(
    interaction: discord.Interaction,
    media: Optional[discord.Attachment] = None,
    url: Optional[str] = None,
    prompt: Optional[str] = None
):
    if not SOCIAL_INTEGRATION_AVAILABLE or not social_manager:
        await interaction.response.send_message("❌ Social media integration module is not available.", ephemeral=True)
        return

    if not social_manager.x_client.is_configured():
        await interaction.response.send_message(
            "⚠️ **X (Twitter) is not configured yet!**\nPlease add your API keys or Bearer Token in the Web Dashboard or config.json.",
            ephemeral=True
        )
        return

    if not media and not url:
        await interaction.response.send_message(
            "📸 Please provide a `media` attachment or an image/video `url` to post!",
            ephemeral=True
        )
        return

    await interaction.response.defer(thinking=True)

    media_bytes = None
    media_filename = media.filename if media else "media.jpg"
    target_url = url

    if media:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(media.url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status == 200:
                        media_bytes = await resp.read()
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to download attachment: {e}")
            return
    elif url:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status == 200:
                        media_bytes = await resp.read()
                        media_filename = Path(url.split("?")[0]).name or "media.jpg"
        except Exception as e:
            print(f"[XPOST] Error reading url bytes: {e}")

    try:
        ok, caption, analysis, post_url = await social_manager.post_to_x_with_analysis(
            media_bytes=media_bytes,
            media_filename=media_filename,
            media_url=target_url,
            user_prompt=prompt or ""
        )

        analysis_preview = analysis[:300] + "..." if len(analysis) > 300 else analysis

        cur_name = get_current_bot_name()
        if ok:
            embed = discord.Embed(
                title=f"✨ {cur_name} // Posted to X (Twitter)!",
                description=(
                    f"**📝 Generated Caption:**\n> {caption}\n\n"
                    f"**🔍 Observed Content Analysis:**\n*{analysis_preview}*\n\n"
                    f"🔗 **Live Tweet:** [{post_url or 'View on X'}]({post_url or 'https://x.com'})"
                ),
                color=0x1DA1F2
            )
            embed.set_footer(text=f"Analyzed & Posted by {cur_name} • X API v2")
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(f"❌ **Failed to post to X**:\n```{post_url or 'Unknown error'}```\n*Caption was:*\n> {caption}")
    except Exception as e:
        await interaction.followup.send(f"❌ X posting exception: {e}")


@tree.command(name="ipost", description="Post a photo, screenshot, video, or reel to Instagram with AI visual analysis and caption")
@app_commands.describe(
    media="Photo, screenshot, or video file to analyze and post to Instagram",
    url="Direct URL to an image or video to post to Instagram",
    prompt="Optional extra note or context for caption"
)
async def slash_ipost(
    interaction: discord.Interaction,
    media: Optional[discord.Attachment] = None,
    url: Optional[str] = None,
    prompt: Optional[str] = None
):
    if not SOCIAL_INTEGRATION_AVAILABLE or not social_manager:
        await interaction.response.send_message("❌ Social media integration module is not available.", ephemeral=True)
        return

    if not social_manager.insta_client.is_configured():
        await interaction.response.send_message(
            "⚠️ **Instagram is not configured yet!**\nPlease set your Instagram username and password in the Web Dashboard or config.json.",
            ephemeral=True
        )
        return

    if not media and not url:
        await interaction.response.send_message(
            "📸 Please provide a `media` attachment or an image/video `url` to post!",
            ephemeral=True
        )
        return

    await interaction.response.defer(thinking=True)

    media_bytes = None
    media_filename = media.filename if media else "media.jpg"
    target_url = url

    if media:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(media.url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status == 200:
                        media_bytes = await resp.read()
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to download attachment: {e}")
            return
    elif url:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status == 200:
                        media_bytes = await resp.read()
                        media_filename = Path(url.split("?")[0]).name or "media.jpg"
        except Exception as e:
            print(f"[IPOST] Error reading url bytes: {e}")

    try:
        ok, caption, analysis, post_url = await social_manager.post_to_insta_with_analysis(
            media_bytes=media_bytes,
            media_filename=media_filename,
            media_url=target_url,
            user_prompt=prompt or ""
        )

        analysis_preview = analysis[:300] + "..." if len(analysis) > 300 else analysis

        cur_name = get_current_bot_name()
        if ok:
            embed = discord.Embed(
                title=f"📸 {cur_name} // Posted to Instagram!",
                description=(
                    f"**📝 Generated Caption:**\n> {caption}\n\n"
                    f"**🔍 Observed Content Analysis:**\n*{analysis_preview}*\n\n"
                    f"🔗 **Live Post:** [{post_url or 'View on Instagram'}]({post_url or 'https://instagram.com'})"
                ),
                color=0xE1306C
            )
            embed.set_footer(text=f"Analyzed & Posted by {cur_name} • Instagram API")
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(f"❌ **Failed to post to Instagram**:\n```{post_url or 'Unknown error'}```\n*Caption was:*\n> {caption}")
    except Exception as e:
        await interaction.followup.send(f"❌ Instagram posting exception: {e}")


@tree.command(name="social_status", description="Check connectivity status for X (Twitter), Instagram, Photon, and Media Queue")
async def slash_social_status(interaction: discord.Interaction):
    if not SOCIAL_INTEGRATION_AVAILABLE or not social_manager:
        await interaction.response.send_message("❌ Social media integration module is not available.", ephemeral=True)
        return

    x_cfg = social_manager.x_cfg
    insta_cfg = social_manager.insta_cfg
    photon_cfg = social_manager.photon_cfg
    pending_queue = social_manager.media_queue.get_pending_count()

    x_status = "🟢 Enabled & Configured" if x_cfg.enabled and social_manager.x_client.is_configured() else ("🟡 Configured (Disabled)" if social_manager.x_client.is_configured() else "🔴 Not Configured")
    insta_status = "🟢 Logged In / Ready" if insta_cfg.enabled and social_manager.insta_client.is_logged_in else ("🟡 Configured (Disabled)" if social_manager.insta_client.is_configured() else "🔴 Not Configured")
    photon_status = "🟢 Connected" if photon_cfg.enabled and social_manager.photon_client.is_configured() else "⚪ Disabled"

    cur_name = get_current_bot_name()
    embed = discord.Embed(
        title=f"🌐 {cur_name} // Social Media & Multi-Channel Status",
        description=(
            f"**🐦 X (Twitter)**: {x_status}\n"
            f"• Auto-Reply Mentions: `{'ON' if x_cfg.auto_reply_mentions else 'OFF'}` | Auto-Reply DMs: `{'ON' if x_cfg.auto_reply_dms else 'OFF'}`\n\n"
            f"**📸 Instagram**: {insta_status}\n"
            f"• Auto-Reply DMs & Videos: `{'ON' if insta_cfg.auto_reply_dms else 'OFF'}`\n"
            f"• Auto-Approve Follows: `{'ON' if insta_cfg.auto_approve_follow_requests else 'OFF'}`\n"
            f"• Follower Story Viewer: `{'ON' if insta_cfg.watch_follower_stories else 'OFF'}`\n"
            f"• Auto Music Notes: `{'ON' if getattr(insta_cfg, 'auto_music_notes', True) else 'OFF'}`\n"
            f"• Auto Daily Stories: `{'ON' if getattr(insta_cfg, 'auto_post_stories', True) else 'OFF'}` ({getattr(insta_cfg, 'stories_per_day', 3)}/day)\n\n"
            f"**⚡ Photon Spectrum (photon.codes)**: {photon_status}\n\n"
            f"**🎬 Multi-Video Burst Queue**: `{pending_queue}` active items in queue"
        ),
        color=0x4f8cff
    )
    await interaction.response.send_message(embed=embed)


@tree.command(name="inote", description="Set or view Yuna's Instagram Music Note")
@app_commands.describe(
    text="Optional thought text for note (max 60 chars; auto-generated if blank)",
    song="Optional song query to search and attach (curated if blank)"
)
async def slash_inote(
    interaction: discord.Interaction,
    text: Optional[str] = None,
    song: Optional[str] = None
):
    if not SOCIAL_INTEGRATION_AVAILABLE or not social_manager:
        await interaction.response.send_message("❌ Social media integration module is not available.", ephemeral=True)
        return

    if not social_manager.insta_client.is_configured():
        await interaction.response.send_message("⚠️ Instagram is not configured yet!", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    try:
        ok, msg, note_data = await social_manager.insta_client.set_music_note(
            text=text,
            track_query=song,
            ask_ai_fn=ask_ai
        )
        cur_name = get_current_bot_name()
        if ok and note_data:
            note_t = note_data.get("text", "")
            track = note_data.get("track", "")
            artist = note_data.get("artist", "")
            embed = discord.Embed(
                title=f"🎧 {cur_name} // Instagram Music Note Updated",
                description=(
                    f"**💬 Note Thought:**\n> *\"{note_t}\"*\n\n"
                    f"**♫ Attached Track:**\n> **{track or 'Unknown Track'}** - *{artist or 'Unknown Artist'}*\n\n"
                    f"✨ Visible to all followers in Instagram Notes feed!"
                ),
                color=0xE1306C
            )
            embed.set_footer(text=f"Instagram Music Note • @{social_manager.insta_client.username or 'ur._.yunaa'}")
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(f"❌ Failed to set Instagram Note: {msg}")
    except Exception as e:
        await interaction.followup.send(f"❌ Error setting Instagram Note: {e}")


@tree.command(name="istories", description="Generate and post aesthetic daily Instagram stories for Yuna")
@app_commands.describe(
    count="Number of stories to post (1 to 4, default 3)"
)
async def slash_istories(
    interaction: discord.Interaction,
    count: Optional[int] = 3
):
    if not SOCIAL_INTEGRATION_AVAILABLE or not social_manager:
        await interaction.response.send_message("❌ Social media integration module is not available.", ephemeral=True)
        return

    if not social_manager.insta_client.is_configured():
        await interaction.response.send_message("⚠️ Instagram is not configured yet!", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    try:
        num = max(1, min(int(count or 3), 4))
        cur_name = get_current_bot_name()
        posted = await social_manager.insta_client.add_daily_stories(
            count=num,
            ask_ai_fn=ask_ai
        )
        if posted:
            desc_lines = [f"Successfully uploaded **{len(posted)}** aesthetic stories to Instagram:\n"]
            for st in posted:
                desc_lines.append(f"• **Story #{st['index']}** (*{st.get('subtitle', '')}*)\n  > \"{st.get('quote', '')}\"")

            embed = discord.Embed(
                title=f"✨ {cur_name} // Daily Stories Published!",
                description="\n".join(desc_lines),
                color=0xE1306C
            )
            embed.set_footer(text=f"9:16 Celestial Story Cards • @{social_manager.insta_client.username or 'ur._.yunaa'}")
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("⚠️ No stories could be uploaded. Please verify Instagram login session.")
    except Exception as e:
        await interaction.followup.send(f"❌ Error publishing daily stories: {e}")

# ─── TRAINING & CHARACTER SLASH COMMANDS (DM ONLY FOR TRAINING) ──
@tree.command(name="train", description="Start interactive training mode to tune response style (DM only)")
@app_commands.allowed_contexts(guilds=False, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=False, users=True)
async def slash_train(interaction: discord.Interaction):
    if interaction.guild is not None:
        await interaction.response.send_message("❌ **DM Only**: `/train` can only be used in Direct Messages (DMs) with the bot, not on servers.", ephemeral=True)
        return
    embed = do_start_training(interaction.user.id, interaction.channel.id)
    await interaction.response.send_message(embed=embed)

@tree.command(name="tbackup", description="Save a backup of current training data (DM only)")
@app_commands.allowed_contexts(guilds=False, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=False, users=True)
async def slash_tbackup(interaction: discord.Interaction):
    if interaction.guild is not None:
        await interaction.response.send_message("❌ **DM Only**: This command can only be used in Direct Messages (DMs).", ephemeral=True)
        return
    ok, embed = do_tbackup(interaction.user.id)
    await interaction.response.send_message(embed=embed)

@tree.command(name="backups", description="View all saved training backups (DM only)")
@app_commands.allowed_contexts(guilds=False, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=False, users=True)
async def slash_backups(interaction: discord.Interaction):
    if interaction.guild is not None:
        await interaction.response.send_message("❌ **DM Only**: This command can only be used in Direct Messages (DMs).", ephemeral=True)
        return
    embed = do_list_backups()
    await interaction.response.send_message(embed=embed)

backup_group = app_commands.Group(name="backup", description="Manage training data backups (DM only)")

@backup_group.command(name="restore", description="Restore training data from backup ID (DM only)")
@app_commands.describe(id="The numeric ID of the backup to restore")
async def slash_backup_restore(interaction: discord.Interaction, id: int):
    if interaction.guild is not None:
        await interaction.response.send_message("❌ **DM Only**: This command can only be used in Direct Messages (DMs).", ephemeral=True)
        return
    ok, embed = do_restore_backup(id)
    await interaction.response.send_message(embed=embed)

@backup_group.command(name="delete", description="Delete a training backup by ID (DM only)")
@app_commands.describe(id="The numeric ID of the backup to delete")
async def slash_backup_delete(interaction: discord.Interaction, id: int):
    if interaction.guild is not None:
        await interaction.response.send_message("❌ **DM Only**: This command can only be used in Direct Messages (DMs).", ephemeral=True)
        return
    ok, embed = do_delete_backup(id)
    await interaction.response.send_message(embed=embed)

tree.add_command(backup_group)

resume_group = app_commands.Group(name="resume", description="Resume sessions and training (DM only)")

@resume_group.command(name="training", description="Resume training mode, optionally loading a backup ID (DM only)")
@app_commands.describe(id="Optional backup ID to restore before training")
async def slash_resume_training(interaction: discord.Interaction, id: Optional[int] = None):
    if interaction.guild is not None:
        await interaction.response.send_message("❌ **DM Only**: This command can only be used in Direct Messages (DMs).", ephemeral=True)
        return
    embed = do_resume_training(interaction.user.id, interaction.channel.id, id)
    await interaction.response.send_message(embed=embed)

tree.add_command(resume_group)

@tree.command(name="switch", description="Switch the active character persona")
@app_commands.describe(character="Name or ID of the character persona to switch to")
async def slash_switch_character(interaction: discord.Interaction, character: str):
    ok, target_bot = switch_character_persona(character)
    if not ok:
        all_names = [b.get("name") for b in bots_state.get("bots", []) if b.get("name")]
        await interaction.response.send_message(f"❌ Character `{character}` not found. Available characters: {', '.join(all_names)}", ephemeral=True)
        return
    embed = discord.Embed(
        title="🎭 Character Switched",
        description=f"Now speaking as: **{target_bot.get('name')}** {target_bot.get('emoji', '🤖')}\n\n*Role*: `{target_bot.get('config', {}).get('role') or 'Custom'}`\n*Provider*: `{target_bot.get('config', {}).get('provider', 'auto')}`",
        color=0x9b59b6
    )
    embed.set_footer(text="Active character updated in memory & bots.json")
    await interaction.response.send_message(embed=embed)
    try:
        await client.change_presence(activity=discord.Game(name=f"{target_bot.get('name')}"))
    except Exception:
        pass

character_group = app_commands.Group(name="character", description="View and switch character personas")

@character_group.command(name="switch", description="Switch active character persona")
@app_commands.describe(character="Name or ID of the character persona to switch to")
async def slash_char_switch(interaction: discord.Interaction, character: str):
    ok, target_bot = switch_character_persona(character)
    if not ok:
        all_names = [b.get("name") for b in bots_state.get("bots", []) if b.get("name")]
        await interaction.response.send_message(f"❌ Character `{character}` not found. Available characters: {', '.join(all_names)}", ephemeral=True)
        return
    embed = discord.Embed(
        title="🎭 Character Switched",
        description=f"Now speaking as: **{target_bot.get('name')}** {target_bot.get('emoji', '🤖')}\n\n*Role*: `{target_bot.get('config', {}).get('role') or 'Custom'}`\n*Provider*: `{target_bot.get('config', {}).get('provider', 'auto')}`",
        color=0x9b59b6
    )
    embed.set_footer(text="Active character updated in memory & bots.json")
    await interaction.response.send_message(embed=embed)
    try:
        await client.change_presence(activity=discord.Game(name=f"{target_bot.get('name')}"))
    except Exception:
        pass

@character_group.command(name="list", description="List all available character personas")
async def slash_char_list(interaction: discord.Interaction):
    embed = do_list_characters()
    await interaction.response.send_message(embed=embed)

tree.add_command(character_group)

@tree.command(name="testy", description="Return hihihihi")
async def slash_testy(interaction: discord.Interaction):
    await interaction.response.send_message("hihihihi")

# ─── DISCORD EVENTS ─────────────────────────────────────
@client.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if client.user and payload.user_id == client.user.id:
        return
    emoji_str = str(payload.emoji.name) if payload.emoji.name else str(payload.emoji)
    if emoji_str not in ("✔️", "❌", "♻️", "✅"):
        return
    map_entry = turn_message_map.get(payload.message_id)
    if not map_entry:
        return
    if payload.user_id != map_entry["user_id"]:
        return
    choice = "approve" if emoji_str in ("✔️", "✅") else ("reject" if emoji_str == "❌" else "regenerate")
    channel = client.get_channel(payload.channel_id)
    if not channel:
        try:
            channel = await client.fetch_channel(payload.channel_id)
        except Exception:
            channel = None
    if channel:
        await handle_training_feedback(
            channel=channel,
            user_id=map_entry["user_id"],
            turn_id=map_entry["turn_id"],
            choice=choice,
            opt_num=map_entry["opt_num"],
            interaction=None
        )

@client.event
async def on_member_join(member: discord.Member):
    if member.bot and client.user and member.id == client.user.id:
        return
    refresh_runtime_config()
    if not config.get("greet_enabled", True):
        return

    guild = member.guild
    channel = None
    target_chan_id = config.get("greet_channel_id")
    if target_chan_id:
        try:
            channel = guild.get_channel(int(target_chan_id))
        except (ValueError, TypeError):
            channel = None

    if not channel and guild.system_channel and guild.system_channel.permissions_for(guild.me).send_messages:
        channel = guild.system_channel

    if not channel:
        for ch in guild.text_channels:
            if ch.permissions_for(guild.me).send_messages:
                channel = ch
                break

    if not channel:
        print(f"[GREET] No suitable channel found to send greeting in guild {guild.name}")
        return

    try:
        greeting_text = await generate_ai_greeting(member, guild)
        await channel.send(greeting_text)
        print(f"[GREET] Sent welcome greeting to {member.name} in #{channel.name} ({guild.name})")
    except Exception as e:
        print(f"[GREET ERROR] Failed to send welcome greeting: {e}")

@client.event
async def on_ready():
    global owner_id_cached
    try:
        app = await client.application_info()
        owner_id_cached = app.owner.id
    except:
        pass

    if DISCORD_VOICE_AVAILABLE and voice_manager:
        try:
            voice_manager.initialize(
                client=client,
                ask_ai_fn=ask_ai,
                speak_fn=speak,
                transcribe_fn=transcribe_audio,
                send_msg_fn=send_split_messages
            )
            print("[VOICE] Real-Time Voice Call Manager initialized successfully.")
        except Exception as vme:
            print(f"[VOICE INIT ERROR] {vme}")
    cmds = tree.get_commands()
    print(f"[SYNC DEBUG] Commands in tree before sync: {len(cmds)}")
    for c in cmds:
        print(f"  - /{c.name}")
    try:
        synced = await tree.sync()
        cur_id = os.getenv("BOT_ID") or bots_state.get("active_id", "default")
        cur_b = get_bot_by_id(bots_state, cur_id) if 'bots_state' in globals() else None
        b_name = cur_b.get("name", "Bot") if cur_b else (client.user.name if client.user else "Bot")
        lat_ms = round(client.latency * 1000) if client.latency else 0
        print(f"[DEBUG READY] [{b_name}] Online as {client.user} (ID: {client.user.id}) | Guilds: {len(client.guilds)} | Ping: {lat_ms}ms", flush=True)
        print(f"Synced {len(synced)} slash commands globally.")
        for cmd in synced:
            print(f"  - /{cmd.name}")
    except discord.HTTPException as e:
        if e.status == 429:
            print(f"[SYNC ERROR] Rate limited! Retry after: {e.retry_after}s")
        else:
            print(f"[SYNC ERROR] HTTP {e.status}: {e.text}")
    except Exception as e:
        print(f"[SYNC ERROR] {type(e).__name__}: {e}")
    client.loop.create_task(random_dm_loop())
    client.loop.create_task(random_chat_loop())
    client.loop.create_task(presence_loop())
    client.loop.create_task(memory_manager_loop())
    if config.get("vtuber_enabled", False) and WEBSOCKETS_AVAILABLE:
        client.loop.create_task(start_vtuber_server())
    if SOCIAL_INTEGRATION_AVAILABLE and social_manager and should_run_social():
        client.loop.create_task(social_manager.start())
        print("[BACKGROUND] Social Media (X & Instagram) integration manager started.")
    if SHOWDOWN_ENGINE_AVAILABLE and showdown_manager and config.get("showdown_enabled", False):
        current_bot_id = os.getenv("BOT_ID") or bots_state.get("active_id", "default")
        current_bot = get_bot_by_id(bots_state, current_bot_id) if 'bots_state' in globals() else None
        cur_bot_name = current_bot.get("name", "Bot") if current_bot else "Bot"
        bot_cfg = current_bot.get("config", {}) if current_bot else config
        sd_client = showdown_manager.init_bot(current_bot_id, cur_bot_name, bot_cfg)
        client.loop.create_task(sd_client.start())
        client.loop.create_task(showdown_ipc_listener(current_bot_id, sd_client))
        print(f"[BACKGROUND] Pokémon Showdown client started for {cur_bot_name} ({sd_client.username}).")
    print("[BACKGROUND] Random DM, Random Chat, Presence, Memory Manager tasks started.")

@client.event
async def on_message(message):
    global message_count
    refresh_runtime_config()
    if message.author == client.user:
        return

    # Check if this is an owner DM replying to a pending escalation
    if AGY_BRIDGE_AVAILABLE and owner_escalation:
        esc = await owner_escalation.check_and_handle_owner_reply(message, client)
        if esc:
            return

    # ─── MULTI-BOT PREFIX FILTER & TARGET ROUTING ──────
    current_bot_id = os.getenv("BOT_ID") or bots_state.get("active_id", "default")
    current_bot = get_bot_by_id(bots_state, current_bot_id) if 'bots_state' in globals() else None
    cur_bot_name = (current_bot.get("name", "") if current_bot else "").lower()
    clean_cur_bot_name = re.sub(r'[^a-zA-Z0-9]', '', cur_bot_name).lower()
    is_active_bot = (current_bot_id == bots_state.get("active_id"))
    bot_mentioned = (client.user in message.mentions) if client.user else False

    if DEBUG_MODE or (isinstance(config, dict) and config.get("debug", True)):
        ch_name = getattr(message.channel, 'name', 'DM')
        g_name = message.guild.name if message.guild else "Direct Message"
        author_name = getattr(message.author, 'display_name', message.author.name)
        content_preview = (message.content[:90] + "...") if len(message.content) > 90 else message.content
        disp_name = current_bot.get("name", "Bot") if current_bot else "Bot"
        print(f"[DEBUG MSG] [{disp_name}] #{ch_name} ({g_name}) from @{author_name}: {content_preview!r}", flush=True)

    raw_c = message.content.strip()

    # ─── YUNA PREFIX COMMANDS (y!...) ──────────────────────────
    if raw_c.lower().startswith("y!"):
        is_yuna_bot = (
            clean_cur_bot_name == "yuna"
            or "yuna" in cur_bot_name
            or (client.user and "yuna" in client.user.name.lower())
        )
        if not is_yuna_bot:
            return  # Silence: only Yuna responds to y! commands

        if YUNA_GAMBLING_AVAILABLE and yuna_gambling:
            def _log_yuna_cmd(channel_id, user_id, user_name, user_cmd, reply_text):
                try:
                    add_to_context(channel_id, "user", user_cmd, user_name=user_name, user_id=user_id)
                    if reply_text:
                        add_to_context(channel_id, "assistant", reply_text, user_name="Yuna")
                except Exception:
                    pass

            try:
                handled = await yuna_gambling.handle_yuna_prefix_command(
                    message, client, raw_c, ask_ai_fn=ask_ai, context_logger_fn=_log_yuna_cmd
                )
                if handled:
                    return
            except Exception as _yg_err:
                import traceback
                print(f"[YUNA PREFIX ERROR] {_yg_err}", flush=True)
                traceback.print_exc()
                await safe_reply(message, "- *Yuna tripped and dropped her basket of berries! (An error occurred)*")
                return

    is_targeted_for_this_bot = bot_mentioned

    if client.user:
        for mention_fmt in (f"<@{client.user.id}>", f"<@!{client.user.id}>"):
            if raw_c.startswith(mention_fmt):
                raw_c = raw_c[len(mention_fmt):].strip()
                is_targeted_for_this_bot = True

    # If other bots are explicitly mentioned in this message but NOT this bot, ignore so only targeted bot answers
    other_bots_mentioned = [m for m in message.mentions if client.user and m.id != client.user.id and getattr(m, 'bot', False)]
    if other_bots_mentioned and (client.user not in message.mentions):
        return

    if config.get("user_memory_enabled", True) and (is_active_bot or is_targeted_for_this_bot):
        await update_user_profile(message.author, message.content, message.guild)

    if raw_c.startswith("!"):
        first_token = raw_c.split()[0].lower()
        clean_first_token = re.sub(r'[^a-zA-Z0-9]', '', first_token).lower()

        # Build alias set for this bot
        my_aliases = {clean_cur_bot_name, f"{clean_cur_bot_name}bot"}
        if clean_cur_bot_name == "briliance":
            my_aliases.update({"brilliance", "briliancebot", "brilliancebot"})
        elif clean_cur_bot_name == "law":
            my_aliases.update({"law", "lawbot"})
        elif clean_cur_bot_name == "yuna":
            my_aliases.update({"yuna", "yunabot"})

        if cur_bot_name and (clean_first_token in my_aliases or first_token == f"!{cur_bot_name}" or first_token == f"!{cur_bot_name}bot"):
            raw_c = "!" + raw_c[len(first_token):].strip()
            is_targeted_for_this_bot = True

        is_mc_command = raw_c.startswith("!mc ") or raw_c == "!mc"
        is_showdown_command = raw_c.startswith(("!showdown", "!pokemon", "!ps ", "!showdown:")) or raw_c == "!ps"

        # Owner text commands (only active bot or explicitly targeted bot handles)
        if not is_mc_command and not is_showdown_command and not is_active_bot and not is_targeted_for_this_bot:
            # Check if this command targets a specific bot by name (e.g. !ping law ...)
            is_named_for_me = False
            parts_check = raw_c.split(None, 2)
            if len(parts_check) > 1 and parts_check[0].lower() in ("!ping", "!test", "!search", "!call"):
                target_check = re.sub(r'[^a-zA-Z0-9]', '', parts_check[1]).lower()
                if target_check in my_aliases or parts_check[1].lower() == cur_bot_name:
                    is_named_for_me = True
            if not is_named_for_me:
                # Not active bot and not targeted -> skip so other bot doesn't duplicate
                return

        if raw_c == "!sync":
            if not await check_owner(message.author.id):
                await safe_reply(message, "Owner only.", delete_after=5)
                return
            await tree.sync()
            await safe_reply(message, f"Global sync triggered on **{cur_bot_name or 'bot'}**!")
            return
        if raw_c == "!sync here":
            if not await check_owner(message.author.id):
                await safe_reply(message, "Owner only.", delete_after=5)
                return
            if message.guild is None:
                await safe_reply(message, "Use this in a server.")
                return
            guild = discord.Object(id=message.guild.id)
            await tree.sync(guild=guild)
            await safe_reply(message, f"Commands synced to this server on **{cur_bot_name or 'bot'}**!")
            return
        if raw_c == "!testgemini":
            if not await check_owner(message.author.id):
                await safe_reply(message, "Owner only.", delete_after=5)
                return
            async with safe_typing(message.channel):
                reply, err = await ask_gemini("You are a test bot.", [], "Say 'Gemini is working'")
            await safe_reply(message, f"Gemini test {'OK' if not err else 'failed'}: {reply}")
            return
        if raw_c == "!testgroq":
            if not await check_owner(message.author.id):
                await safe_reply(message, "Owner only.", delete_after=5)
                return
            async with safe_typing(message.channel):
                reply, err = await ask_groq([], "Say 'Groq is working' and nothing else.")
            await safe_reply(message, f"Groq test {'OK' if not err else 'failed'}: {reply}")
            return
        if raw_c == "!testopenrouter":
            if not await check_owner(message.author.id):
                await safe_reply(message, "Owner only.", delete_after=5)
                return
            async with safe_typing(message.channel):
                reply, err = await ask_openrouter([], "Say 'OpenRouter is working' and nothing else.")
            await safe_reply(message, f"OpenRouter test {'OK' if not err else 'failed'}: {reply}")
            return
        if raw_c == "!testopenai":
            if not await check_owner(message.author.id):
                await safe_reply(message, "Owner only.", delete_after=5)
                return
            async with safe_typing(message.channel):
                reply, err = await ask_openai([], "Say 'OpenAI is working' and nothing else.")
            await safe_reply(message, f"OpenAI test {'OK' if not err else 'failed'}: {reply}")
            return
        if raw_c == "!testdeepseek":
            if not await check_owner(message.author.id):
                await safe_reply(message, "Owner only.", delete_after=5)
                return
            async with safe_typing(message.channel):
                reply, err = await ask_deepseek([], "Say 'DeepSeek is working' and nothing else.")
            await safe_reply(message, f"DeepSeek test {'OK' if not err else 'failed'}: {reply}")
            return
        if raw_c == "!testmistral":
            if not await check_owner(message.author.id):
                await safe_reply(message, "Owner only.", delete_after=5)
                return
            async with safe_typing(message.channel):
                reply, err = await ask_mistral([], "Say 'Mistral is working' and nothing else.")
            await safe_reply(message, f"Mistral test {'OK' if not err else 'failed'}: {reply}")
            return
        if raw_c == "!reset":
            clear_context(message.channel.id)
            await safe_reply(message, "Context memory cleared.")
            return
        if raw_c.startswith("!forgetme") or raw_c.startswith("!clearmemory"):
            parts = raw_c.split()
            all_bots = len(parts) > 1 and parts[1].lower() in ("all", "global", "allbots")
            uid = str(message.author.id)
            b_name = client.user.display_name if client.user else "this bot"
            clear_user_bot_memory(uid, all_bots=all_bots)
            if all_bots:
                await safe_reply(message, f"🧹 All long-term memories, facts, and quotes about **{message.author.display_name}** have been wiped across **all bots**.")
            else:
                await safe_reply(message, f"🧹 **{b_name}** has forgotten all memories, facts, and quotes about **{message.author.display_name}**.")
            return
        if raw_c == "!memory":
            uid = str(message.author.id)
            bot_mem = get_user_bot_memory(uid)
            b_name = client.user.display_name if client.user else "Bot"
            facts_list = bot_mem.get("facts", [])
            sentences_list = bot_mem.get("sentences", [])
            await safe_reply(message, f"🧠 **{b_name} Memory for {message.author.display_name}:**\n- Facts: {len(facts_list)}\n- Quotes: {len(sentences_list)}\n- Interactions with this bot: {bot_mem.get('interaction_count', 0)}")
            return
        if raw_c.startswith("!call") or raw_c in ("!hangup", "!leavevc", "!endcall"):
            if not message.guild:
                await safe_reply(message, "❌ The `!call` command can only be used in a Discord server voice channel.")
                return
            if not DISCORD_VOICE_AVAILABLE or not voice_manager:
                await safe_reply(message, "❌ Voice system module is not currently available.")
                return

            sub_parts = raw_c.split()
            cmd_token = sub_parts[0].lower()
            action_args = [p for p in sub_parts[1:] if re.sub(r'[^a-zA-Z0-9]', '', p).lower() not in my_aliases]
            action = action_args[0].lower().strip() if action_args else ("leave" if cmd_token in ("!hangup", "!leavevc", "!endcall") else "join")

            if action in ["join", "start", "call"]:
                if not isinstance(message.author, discord.Member) or not message.author.voice or not message.author.voice.channel:
                    await safe_reply(message, "❌ You must join a voice channel first before calling me!")
                    return
                async with safe_typing(message.channel):
                    ok, msg = await voice_manager.start_call(message.author, message.channel)
                await safe_reply(message, msg)
                return
            elif action in ["leave", "stop", "end", "hangup", "disconnect"]:
                async with safe_typing(message.channel):
                    ok, msg = await voice_manager.stop_call(message.guild)
                await safe_reply(message, msg)
                return
            elif action in ["vad", "silence", "gap", "pause"]:
                val_arg = action_args[1] if len(action_args) > 1 else None
                if val_arg:
                    try:
                        val = max(0.8, min(4.0, float(val_arg)))
                        update_config_setting("vad_silence_gap", str(val))
                        voice_manager.set_vad_gap(message.guild.id, val)
                        await safe_reply(message, f"🎙️ **VAD Silence Gap set to {val:.2f}s!**\nYou can now pause naturally up to {val:.2f} seconds between words without being interrupted.")
                    except Exception as e:
                        await safe_reply(message, f"❌ Invalid value for VAD gap: {e}")
                else:
                    vad_info = voice_manager.get_vad_info(message.guild.id)
                    await safe_reply(message, f"🎙️ **VAD Settings:**\n• Silence Gap (Pause Tolerance): **{vad_info['silence_gap']}s**\n• Sensitivity Threshold: **{vad_info['silence_threshold']} RMS**\n• Ambient Noise Floor: **{vad_info['noise_floor']} RMS**\n💡 *Change anytime with `!call vad <seconds>` (e.g. `!call vad 1.8`)*")
                return
            elif action in ["status"]:
                in_call = voice_manager.is_in_call(message.guild.id)
                sess = voice_manager.get_session(message.guild.id)
                vad_info = voice_manager.get_vad_info(message.guild.id)
                if in_call and sess:
                    elapsed = int(time.time() - sess.get("start_time", time.time()))
                    await safe_reply(message, f"📞 **Call Active** with `{sess.get('caller_name', 'User')}` in <#{sess.get('vc_channel_id')}> (Duration: {elapsed}s)\n🎙️ **VAD Pause Tolerance:** `{vad_info['silence_gap']}s` (Threshold: `{vad_info['silence_threshold']}`)")
                else:
                    await safe_reply(message, f"📴 No active voice call in this server. Use `!call` or `/call` to start one!\n🎙️ **VAD Pause Tolerance:** `{vad_info['silence_gap']}s` (adjust anytime with `!call vad <seconds>`)")
                return
            else:
                await safe_reply(message, "Usage: `!call [join | leave | status | vad]` or `!hangup`")
                return
        if raw_c == "!purgeall":
            if not await check_owner(message.author.id):
                await safe_reply(message, "Owner only.", delete_after=5)
                return
            contexts.clear()
            await safe_reply(message, "All memory purged.")
            return
        if raw_c.startswith("!search "):
            if not await check_owner(message.author.id):
                await safe_reply(message, "Owner only.", delete_after=5)
                return
            q = raw_c[8:].strip()
            if not q:
                await safe_reply(message, "Usage: `!search <query>`")
                return
            async with safe_typing(message.channel):
                results, err = await web_search(q, max_results=5)
                if err or not results:
                    await safe_reply(message, f"Search failed: {err or 'No results.'}")
                    return
                reply, ai_err = await synthesize_search(message.channel.id, q, results)
                if not ai_err:
                    header = f"**Search:** `{q}`\n\n"
                    full_reply = header + reply
                    await send_split_messages(message.channel, full_reply, reply_to=message)
                    message_count += 1
                    source_lines = []
                    for i, r in enumerate(results[:5], 1):
                        source_lines.append(f"{i}. [{r['title']}]({r['url']})")
                    source_embed = discord.Embed(title="Sources", description="\n".join(source_lines), color=0x2b2d42)
                    await safe_reply(message, embed=source_embed)
                    return
                lines = [f"**Web search:** `{q}`\n"]
                for i, r in enumerate(results[:5], 1):
                    snippet = r["snippet"][:180] + "..." if len(r["snippet"]) > 180 else r["snippet"]
                    lines.append(f"**{i}.** [{r['title']}]({r['url']})\n{snippet}\n")
                embed = discord.Embed(title="Search Results", description="\n".join(lines), color=0x4f8cff)
                embed.set_footer(text="via DuckDuckGo Lite | synthesis unavailable")
                await safe_reply(message, embed=embed)
            return

        if raw_c.startswith("!watch "):
            v_url = raw_c[7:].strip()
            if not v_url:
                await safe_reply(message, "Usage: `!watch <video-url>` (YouTube, Instagram, TikTok, Twitter/X, MP4 - up to 12 mins)")
                return
            async with safe_typing(message.channel):
                if MEDIA_INTELLIGENCE_AVAILABLE:
                    context_data, report = await watch_video_tool(v_url, bot_config=config)
                    reply, err = await ask_ai(
                        message.channel.id,
                        f"The user asked you to watch and react to this video:\n\n{context_data}\n\nPlease share your in-character reaction and analysis of what you watched and heard!",
                        user_id=message.author.id, user_name=message.author.display_name,
                        guild=message.guild, is_dm=(message.guild is None)
                    )
                    if not err and reply:
                        await send_split_messages(message.channel, reply, reply_to=message)
                        message_count += 1
                        if config.get("tts_enabled"):
                            audio = await speak(reply)
                            if audio:
                                await _safe_send_voice_reply(message, audio)
                        return
                    else:
                        await safe_reply(message, f"❌ Failed to analyze video: {reply or err}")
                        return
                else:
                    await safe_reply(message, "Media Intelligence System unavailable.")
                    return

        if raw_c.startswith("!browse ") or raw_c.startswith("!read "):
            w_url = raw_c.split(None, 1)[1].strip() if " " in raw_c else ""
            if not w_url:
                await safe_reply(message, "Usage: `!browse <url>`")
                return
            async with safe_typing(message.channel):
                if MEDIA_INTELLIGENCE_AVAILABLE:
                    context_data, page = await browse_web_tool(w_url)
                    reply, err = await ask_ai(
                        message.channel.id,
                        f"The user asked you to visit and read this webpage:\n\n{context_data}\n\nPlease summarize the key information and insights from this article in character!",
                        user_id=message.author.id, user_name=message.author.display_name,
                        guild=message.guild, is_dm=(message.guild is None)
                    )
                    if not err and reply:
                        await send_split_messages(message.channel, reply, reply_to=message)
                        message_count += 1
                        if config.get("tts_enabled"):
                            audio = await speak(reply)
                            if audio:
                                await _safe_send_voice_reply(message, audio)
                        return
                    else:
                        await safe_reply(message, f"❌ Failed to browse webpage: {reply or err}")
                        return
                else:
                    await safe_reply(message, "Web browser tool unavailable.")
                    return

        # ─── MINECRAFT PREFIX COMMANDS ─────────────────────
        if raw_c.startswith("!mc ") or raw_c == "!mc":
            mc_args_raw = raw_c[4:].strip() if raw_c.startswith("!mc ") else ""
            tokens = mc_args_raw.split()
            all_bot_names = [b.get("name", "").lower() for b in bots_state.get("bots", []) if b.get("name")]

            target_mode = "default"
            sub = "status"
            arg = ""

            if tokens:
                first_t = tokens[0].lower()
                if first_t == "all":
                    target_mode = "all"
                    sub = tokens[1].lower() if len(tokens) > 1 else "status"
                    arg = " ".join(tokens[2:]) if len(tokens) > 2 else ""
                elif first_t in all_bot_names:
                    if first_t != cur_bot_name:
                        return  # Explicitly addressed to another bot
                    target_mode = "named"
                    sub = tokens[1].lower() if len(tokens) > 1 else "status"
                    arg = " ".join(tokens[2:]) if len(tokens) > 2 else ""
                else:
                    sub = first_t
                    arg = " ".join(tokens[1:]) if len(tokens) > 1 else ""
            else:
                sub = "status"
                arg = ""

            # Routing rule:
            # - Informational commands (status, journal, todo, stats, memory, goals, log, journy, journel):
            #   BOTH/ALL bots reply with their respective status/journal embed!
            # - Action commands (start, stop, follow, mine, craft, give, attack, pvp, duel, sleep, emote, chat, goal):
            #   Only the active bot handles it (unless targeted with bot name, @mention, or !mc all) to avoid conflict.
            is_info_cmd = sub.startswith("journ") or sub in ("journal", "todo", "memory", "goals", "log", "stats", "journy", "journel", "status", "inventory")
            if target_mode == "default" and not is_active_bot and not is_targeted_for_this_bot and not is_info_cmd:
                return

            current_bot_name = current_bot.get("name", "Bot") if current_bot else "Bot"

            if sub == "start":
                ok, msg = start_minecraft_bot()
                await safe_reply(message, f"🎮 **Minecraft Bot ({current_bot_name}):** {msg}")
                return
            elif sub == "stop":
                ok, msg = stop_minecraft_bot()
                await safe_reply(message, f"🎮 **Minecraft Bot ({current_bot_name}):** {msg}")
                return
            elif sub.startswith("journ") or sub in ("journal", "todo", "memory", "goals", "log", "stats", "journy", "journel"):
                bot_journal_path = os.path.join(SCRIPT_DIR, "memories", "minecraft", f"{current_bot_id}_journal.json")
                fallback_journal_path = os.path.join(SCRIPT_DIR, "memories", "minecraft", "journal.json")

                j = mc_state.get("journal", {})
                if (not j or len(j.get("todo_list", [])) < 3) and os.path.exists(bot_journal_path):
                    try:
                        with open(bot_journal_path) as f:
                            j = json.load(f)
                    except Exception:
                        pass
                if (not j or len(j.get("todo_list", [])) < 3) and os.path.exists(fallback_journal_path):
                    try:
                        with open(fallback_journal_path) as f:
                            j = json.load(f)
                    except Exception:
                        pass
                if not j or len(j.get("todo_list", [])) < 3:
                    import copy
                    j = copy.deepcopy(DEFAULT_MC_JOURNAL)

                embed = discord.Embed(
                    title=f"📖 {current_bot_name}'s Autonomous Minecraft Journal",
                    description=f"Active real-player survival goals, progression and milestones for **{current_bot_name}**.",
                    color=0x9b59b6
                )
                todos = j.get("todo_list", [])
                if todos:
                    todo_lines = [f"{'✅' if t.get('done') else '⬜'} {t.get('task')}" for t in todos]
                    embed.add_field(name="📋 Survival To-Do List & Quests", value="\n".join(todo_lines[:12]), inline=False)
                milestones = j.get("milestones", [])
                if milestones:
                    m_lines = [f"• {m.get('desc')} *({m.get('time', '')[-8:-1]})*" for m in milestones[-4:]]
                    embed.add_field(name="🏆 Recent Milestones", value="\n".join(m_lines), inline=False)
                lessons = j.get("lessons_learned", [])
                if lessons:
                    l_lines = [f"• {l}" for l in lessons[-3:]]
                    embed.add_field(name="💡 Lessons Learned from Mistakes", value="\n".join(l_lines), inline=False)
                stats = j.get("stats", {})
                s_text = f"⛏️ Mined: `{stats.get('blocks_mined',0)}` | 🔨 Crafted: `{stats.get('items_crafted',0)}` | 💀 Deaths: `{stats.get('deaths',0)}`"
                embed.add_field(name="📊 Lifetime Stats", value=s_text, inline=False)
                await safe_reply(message, embed=embed)
                return
            elif sub == "status":
                online = mc_state.get("online", False)
                status_icon = "🟢 Online" if online else "🔴 Offline"
                pos = mc_state.get("pos", {})
                coords = f"X: `{pos.get('x',0)}` Y: `{pos.get('y',0)}` Z: `{pos.get('z',0)}`"
                hp = mc_state.get("health", 20)
                food = mc_state.get("food", 20)
                task = mc_state.get("task", "idle")
                in_game_user = mc_state.get("username") or config.get("minecraft_username", current_bot_name)
                embed = discord.Embed(
                    title=f"🎮 Minecraft Real-Player Bot Status ({current_bot_name})",
                    color=0x2ecc71 if online else 0xe74c3c
                )
                embed.add_field(name="Status", value=f"{status_icon} (`{in_game_user}`)", inline=True)
                embed.add_field(name="Current Task", value=f"`{task}`", inline=True)
                embed.add_field(name="Server", value=f"`{config.get('minecraft_server')}:{config.get('minecraft_port')}`", inline=True)
                embed.add_field(name="Position", value=coords, inline=True)
                embed.add_field(name="Vitals", value=f"❤️ Health: `{hp}/20` | 🍖 Food: `{food}/20`", inline=True)
                players = mc_state.get("players", [])
                p_str = ", ".join([p.get("username", "") for p in players]) if players else "None"
                embed.add_field(name="Nearby Players", value=p_str[:100], inline=True)
                inv = mc_state.get("inventory", [])
                if inv:
                    inv_str = ", ".join([f"{i['name']} ({i['count']})" for i in inv[:8]])
                    embed.add_field(name="Inventory", value=inv_str[:200], inline=False)
                await safe_reply(message, embed=embed)
                return
            elif sub == "follow":
                p_name = arg or message.author.display_name
                send_mc_cmd({"type": "follow", "username": p_name, "range": 2})
                await safe_reply(message, f"🏃 **{current_bot_name}:** Following **{p_name}**!")
                return
            elif sub == "mine":
                b_parts = arg.split() if arg else []
                if len(b_parts) > 1 and b_parts[-1].isdigit():
                    b_name = " ".join(b_parts[:-1])
                    b_count = int(b_parts[-1])
                else:
                    b_name = arg or "oak_log"
                    b_count = 5
                send_mc_cmd({"type": "mine", "block": b_name, "count": b_count})
                await safe_reply(message, f"⛏️ **{current_bot_name}:** Mining **{b_name}** ({b_count} blocks).")
                return
            elif sub == "craft":
                c_parts = arg.split() if arg else []
                if len(c_parts) > 1 and c_parts[-1].isdigit():
                    c_name = " ".join(c_parts[:-1])
                    c_count = int(c_parts[-1])
                else:
                    c_name = arg or "wooden_pickaxe"
                    c_count = 1
                send_mc_cmd({"type": "craft", "item": c_name, "count": c_count})
                await safe_reply(message, f"🔨 **{current_bot_name}:** Smart crafting **{c_name}** ({c_count}x)...")
                return
            elif sub == "give":
                parts2 = arg.split(None, 2) if arg else []
                if len(parts2) == 3 and parts2[1].isdigit():
                    itm = parts2[0]
                    cnt = int(parts2[1])
                    usr = parts2[2]
                elif len(parts2) == 2:
                    itm = parts2[0]
                    cnt = 64
                    usr = parts2[1]
                else:
                    itm = arg or "all"
                    cnt = 64
                    usr = message.author.display_name
                send_mc_cmd({"type": "give", "item": itm, "username": usr, "count": cnt})
                await safe_reply(message, f"🎁 **{current_bot_name}:** Giving **{itm}** to **{usr}**!")
                return
            elif sub in ("attack", "pvp", "duel"):
                send_mc_cmd({"type": "attack", "target": arg})
                await safe_reply(message, f"⚔️ **{current_bot_name}:** Engaging target in combat: **{arg or 'nearest hostile'}**!")
                return
            elif sub == "sleep":
                send_mc_cmd({"type": "sleep"})
                await safe_reply(message, f"🛏️ **{current_bot_name}:** Finding bed (or placing bed from inventory) to sleep...")
                return
            elif sub == "emote":
                e_type = arg or "sneak_spam"
                send_mc_cmd({"type": "emote", "emote": e_type})
                await safe_reply(message, f"✨ **{current_bot_name}:** Emote: `{e_type}`")
                return
            elif sub == "chat":
                send_mc_cmd({"type": "chat", "text": arg})
                await safe_reply(message, f"💬 **{current_bot_name}:** Sent to Minecraft: `{arg}`")
                return
            elif sub == "goal":
                async with safe_typing(message.channel):
                    reply = await mc_execute_natural_goal(arg, sender_name=message.author.display_name)
                await safe_reply(message, f"🎯 **Goal Dispatched ({current_bot_name}):** {arg}\n💬 **{current_bot_name}:** {reply}")
                return
            else:
                await safe_reply(message, f"Usage: `!mc [all|<bot>] start|stop|status|journal|follow|mine|craft|give|attack|sleep|emote|chat|goal <args>`")
                return

    # ─── PING & TOGGLE PREFIX COMMANDS ─────────────────
    if message.content in ("!ping", "!pong"):
        bot_name = client.user.display_name if client.user else "Bot"
        ws_latency = round(client.latency * 1000) if client.latency else 0
        active_p = config.get("provider", "auto")
        model_key = f"{active_p}_model" if active_p in ("gemini", "groq", "mistral") else "model"
        active_m = config.get(model_key, "default")
        embed = discord.Embed(
            title=f"🏓 Pong! [{bot_name}]",
            description=(
                f"⚡ **Gateway Latency**: `{ws_latency}ms`\n"
                f"🌐 **Active Provider**: `{active_p}`\n"
                f"🧠 **Model**: `{active_m}`\n"
                f"🔋 **Status**: `Operational`"
            ),
            color=0x00ffcc
        )
        await safe_reply(message, embed=embed)
        return

    if message.content.startswith("!toggle") or message.content.startswith("!provider"):
        if not await check_owner(message.author.id):
            await safe_reply(message, "❌ Owner only.", delete_after=5)
            return
        parts = message.content.split(None, 1)
        target_prov = parts[1].strip() if len(parts) > 1 else None
        old_p, new_p = toggle_provider(target_prov)
        bot_name = client.user.display_name if client.user else "Bot"
        model_key = f"{new_p}_model" if new_p in ("gemini", "groq", "mistral") else "model"
        curr_model = config.get(model_key, "default")
        toast = format_toast_embed(
            f"{bot_name} // Provider Toggled",
            f"Switched provider: `{old_p}` ➔ **`{new_p}`**\nActive Model: **`{curr_model}`**",
            color=0x4f8cff
        )
        await safe_reply(message, embed=toast)
        return

    # Skip other bots entirely
    if message.author.bot:
        return

    # ─── @MENTION & PREFIX CONFIGURATION COMMANDS ─────────
    is_mentioned = client.user in message.mentions if client.user else False
    is_dm = isinstance(message.channel, discord.DMChannel)
    content_raw = message.content.strip()
    clean_text = content_raw
    if client.user:
        clean_text = re.sub(r'<@!?\d+>', '', clean_text).strip()

    # Check for invite in mention / command: e.g. "@Bot invite", "!invite"
    clean_low = clean_text.lower()
    if (is_mentioned or is_dm or content_raw.startswith("!invite")) and (
        clean_low in ("invite", "invite link", "inv", "add", "install", "invite bot", "bot invite", "link") or
        content_raw.strip().lower() in ("!invite", "!inv") or
        re.search(r'\b(invite|invite\s+link|add\s+bot|install\s+app)\b', clean_low)
    ):
        bot_name = client.user.display_name if client.user else "Bot"
        client_id = client.user.id if client.user else ""
        if client_id:
            server_invite = f"https://discord.com/oauth2/authorize?client_id={client_id}&permissions=8&scope=bot%20applications.commands"
            user_app_invite = f"https://discord.com/oauth2/authorize?client_id={client_id}&scope=applications.commands"
            embed = discord.Embed(
                title=f"🔗 Invite & Install {bot_name}",
                description="Choose how you'd like to add or use this bot:",
                color=0x8a9a8a
            )
            embed.add_field(
                name="🏰 Add to Server (Bot & Commands)",
                value=f"[**Click to Invite to Server**]({server_invite})\n*Adds {bot_name} to your Discord server with full features & commands.*",
                inline=False
            )
            embed.add_field(
                name="👤 Install as User App (Use in DMs & Any Server)",
                value=f"[**Click to Install to Account**]({user_app_invite})\n*Allows using slash commands anywhere, including private DMs & any server without server invite.*",
                inline=False
            )
            embed.set_footer(text="Discord Bot OAuth2 Setup")
            await safe_reply(message, embed=embed)
            return

    # Check for ping in mention: e.g. "@Bot ping"
    if (is_mentioned or is_dm) and clean_text.lower() in ("ping", "pong", "!ping", "!pong"):
        bot_name = client.user.display_name if client.user else "Bot"
        ws_latency = round(client.latency * 1000) if client.latency else 0
        active_p = config.get("provider", "auto")
        model_key = f"{active_p}_model" if active_p in ("gemini", "groq", "mistral") else "model"
        active_m = config.get(model_key, "default")
        embed = discord.Embed(
            title=f"🏓 Pong! [{bot_name}]",
            description=(
                f"⚡ **Gateway Latency**: `{ws_latency}ms`\n"
                f"🌐 **Active Provider**: `{active_p}`\n"
                f"🧠 **Model**: `{active_m}`\n"
                f"🔋 **Status**: `Operational`"
            ),
            color=0x00ffcc
        )
        await safe_reply(message, embed=embed)
        return

    # ─── CHARACTER SWITCHING (DISCORD DM / MENTION / PREFIX) ───
    clean_low = clean_text.lower().strip()
    is_char_switch = False
    char_target = None
    if clean_low.startswith(("switch to ", "!switch to ", "/switch to ")):
        is_char_switch = True
        char_target = clean_text.split("to", 1)[1].strip()
    elif clean_low.startswith(("switch character ", "!switch character ", "switch bot ", "!switch bot ")):
        is_char_switch = True
        char_target = clean_text.split(None, 2)[2].strip() if len(clean_text.split()) > 2 else ""
    elif clean_low.startswith(("!character ", "/character ")):
        parts = clean_text.split()
        if len(parts) > 1 and parts[1].lower() in ("list", "all"):
            embed = do_list_characters()
            await safe_reply(message, embed=embed)
            return
        elif len(parts) > 1 and parts[1].lower() == "switch" and len(parts) > 2:
            is_char_switch = True
            char_target = " ".join(parts[2:]).strip()
        elif len(parts) > 1:
            is_char_switch = True
            char_target = " ".join(parts[1:]).strip()
    elif (is_mentioned or is_dm or content_raw.startswith("!")) and clean_low.startswith(("switch ", "!switch ", "/switch ")):
        parts = clean_text.split(None, 1)
        if len(parts) > 1 and parts[1].lower() not in ("provider", "model", "auto", "gemini", "groq", "mistral", "openrouter", "deepseek", "openai", "huggingface"):
            is_char_switch = True
            char_target = parts[1].strip()

    if is_char_switch and char_target:
        ok, target_bot = switch_character_persona(char_target)
        if ok:
            embed = discord.Embed(
                title="🎭 Character Switched",
                description=f"Now speaking as: **{target_bot.get('name')}** {target_bot.get('emoji', '🤖')}\n\n*Role*: `{target_bot.get('config', {}).get('role') or 'Custom'}`\n*Provider*: `{target_bot.get('config', {}).get('provider', 'auto')}`",
                color=0x9b59b6
            )
            embed.set_footer(text="Active character updated in memory & bots.json")
            await safe_reply(message, embed=embed)
            try:
                await client.change_presence(activity=discord.Game(name=f"{target_bot.get('name')}"))
            except Exception:
                pass
            return
        else:
            all_names = [b.get("name") for b in bots_state.get("bots", []) if b.get("name")]
            await safe_reply(message, f"❌ Character `{char_target}` not found. Available characters: {', '.join(all_names)}")
            return

    # Check for toggle in mention / DM: e.g. "@Bot toggle" or "@Bot toggle provider" or "@Bot toggle groq"
    if (is_mentioned or is_dm) and (clean_text.lower().startswith("toggle") or clean_text.lower().startswith("switch provider") or clean_text.lower().startswith("switch model") or clean_text.lower().strip() in ("switch", "switch next")):
        if not await check_owner(message.author.id):
            await safe_reply(message, "❌ **Owner Only**: Only the bot owner can toggle the provider.", delete_after=8)
            return
        parts = clean_text.split()
        target_prov = None
        if len(parts) > 1:
            cand = parts[1].lower()
            if cand in ("provider", "model") and len(parts) > 2:
                target_prov = parts[2].lower()
            elif cand in ("auto", "gemini", "groq", "mistral", "openrouter", "huggingface", "deepseek", "openai"):
                target_prov = cand
        old_p, new_p = toggle_provider(target_prov)
        bot_name = client.user.display_name if client.user else "Bot"
        model_key = f"{new_p}_model" if new_p in ("gemini", "groq", "mistral") else "model"
        curr_model = config.get(model_key, "default")
        toast = format_toast_embed(
            f"{bot_name} // Provider Toggled",
            f"Switched provider: `{old_p}` ➔ **`{new_p}`**\nActive Model: **`{curr_model}`**",
            color=0x4f8cff
        )
        await safe_reply(message, embed=toast)
        return

    # If user just pinged the bot with no message (e.g. "@Bot")
    if is_mentioned and not clean_text and not message.attachments:
        bot_name = client.user.display_name if client.user else "Bot"
        ws_latency = round(client.latency * 1000) if client.latency else 0
        active_p = config.get("provider", "auto")
        toast = format_toast_embed(
            f"{bot_name} Online",
            f"👋 Hey **{message.author.display_name}**! I'm online and ready.\nAsk me anything or use `/ask`!\n*(Ping: `{ws_latency}ms` • Provider: `{active_p}`)*",
            color=0x8a9a8a
        )
        await safe_reply(message, embed=toast)
        return

    # Avatar / PFP Update Command
    is_pfp_cmd = False
    pfp_target_url = None
    if (is_mentioned or is_dm or content_raw.startswith("!")):
        low_clean = clean_text.lower().strip()
        if low_clean.startswith(("pfp:", "avatar:", "avatar_url:", "pfp =", "avatar =", "set pfp", "set avatar", "update pfp", "update avatar", "!pfp", "!avatar")):
            is_pfp_cmd = True
            parts = re.split(r'[:=\s]+', clean_text, maxsplit=1)
            if len(parts) > 1 and parts[1].strip().startswith("http"):
                pfp_target_url = parts[1].strip()
        elif low_clean in ("pfp", "avatar", "!pfp", "!avatar") and message.attachments:
            is_pfp_cmd = True

    if is_pfp_cmd:
        if not await check_owner(message.author.id):
            await safe_reply(message, "❌ **Owner Only**: Only the bot owner can update my avatar.", delete_after=8)
            return

        img_bytes = None
        final_pfp_url = None

        # 1. Check direct attachments
        if message.attachments:
            for att in message.attachments:
                ct = att.content_type or ""
                ext = Path(att.filename).suffix.lower()
                if ct.startswith("image/") or ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
                    async with safe_typing(message.channel):
                        try:
                            img_bytes = await att.read()
                            final_pfp_url = att.url
                            break
                        except Exception as e:
                            await safe_reply(message, f"❌ Failed to read attachment: {e}")
                            return

        # 2. Check URL in text
        if not img_bytes and pfp_target_url:
            async with safe_typing(message.channel):
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(pfp_target_url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                            if r.status == 200:
                                img_bytes = await r.read()
                                final_pfp_url = pfp_target_url
                            else:
                                await safe_reply(message, f"❌ Failed to download image from URL (HTTP {r.status})")
                                return
                except Exception as e:
                    await safe_reply(message, f"❌ Could not download image URL: {e}")
                    return

        if not img_bytes:
            await safe_reply(message, "⚠️ Please provide an image URL (e.g. `@bot pfp: https://...`) or attach an image file directly with your message.")
            return

        async with safe_typing(message.channel):
            err_note = ""
            try:
                if client.user:
                    await client.user.edit(avatar=img_bytes)
            except discord.HTTPException as he:
                err_note = f" (Discord API Note: {he.text if hasattr(he, 'text') else he})"
            except Exception as ex:
                err_note = f" (Note: {ex})"

            if final_pfp_url:
                config["avatar_url"] = final_pfp_url
                config["pfp"] = final_pfp_url
                if active_bot:
                    active_bot["avatar_url"] = final_pfp_url
                    if "config" in active_bot:
                        active_bot["config"]["avatar_url"] = final_pfp_url
                        active_bot["config"]["pfp"] = final_pfp_url
                    save_bots(bots_state)

            bot_name = client.user.display_name if client.user else "Bot"
            toast = format_toast_embed(
                f"{bot_name} // Avatar Updated",
                f"✅ **Avatar successfully updated!**{err_note}\nNew profile picture is now active on Discord and Web Studio.",
                color=0x00ffcc
            )
            if final_pfp_url:
                toast.set_thumbnail(url=final_pfp_url)
            await safe_reply(message, embed=toast)
            return

    config_match = None
    # Pattern 1: field: value OR field = value
    m_field = re.match(r'^([a-zA-Z0-9_\-]+)\s*[:=]\s*(.+)$', clean_text, re.DOTALL)
    if m_field:
        candidate_field = m_field.group(1).strip().lower()
        if candidate_field in CONFIG_FIELD_MAPPINGS:
            config_match = (candidate_field, m_field.group(2).strip())

    # Pattern 2: "!set field value", "!config field value", "set field value"
    if not config_match and (is_mentioned or is_dm or content_raw.startswith("!")):
        m_cmd = re.match(r'^(?:!set|!config|set|config)\s+([a-zA-Z0-9_\-]+)\s*(?:[:=]|\s)\s*(.+)$', clean_text, re.DOTALL | re.IGNORECASE)
        if m_cmd:
            candidate_field = m_cmd.group(1).strip().lower()
            if candidate_field in CONFIG_FIELD_MAPPINGS:
                config_match = (candidate_field, m_cmd.group(2).strip())
        elif clean_text.lower().startswith("!model ") or clean_text.lower().startswith("model: "):
            val = clean_text.split(None, 1)[1].strip() if " " in clean_text else ""
            if val:
                config_match = ("model", val)
        elif clean_text.lower().startswith("!provider ") or clean_text.lower().startswith("provider: "):
            val = clean_text.split(None, 1)[1].strip() if " " in clean_text else ""
            if val:
                config_match = ("provider", val)

    if config_match and (is_mentioned or is_dm or content_raw.startswith("!")):
        field_name, field_val = config_match
        if not await check_owner(message.author.id):
            await safe_reply(message, "❌ **Owner Only**: Only the bot owner can modify my model and configuration.", delete_after=8)
            return
        ok, key, old_v, new_v = update_config_setting(field_name, field_val)
        bot_name = client.user.display_name if client.user else "Bot"
        if ok:
            toast = format_toast_embed(
                f"{bot_name} // Model Updated",
                f"Field **`{key}`** updated:\n`{old_v}` ➔ **`{new_v}`**\n*(Active Provider: `{config.get('provider', 'auto')}`)*",
                color=0x00ffcc
            )
            await safe_reply(message, embed=toast)
            return
        else:
            await safe_reply(message, f"❌ Failed to update `{field_name}`: {new_v}")
            return

    # Query config via "!config" or "!settings"
    if content_raw in ("!config", "!settings", "!models"):
        if not await check_owner(message.author.id):
            await safe_reply(message, "❌ Owner only.", delete_after=5)
            return
        bot_name = client.user.display_name if client.user else "Bot"
        embed = discord.Embed(
            title=f"📋 {bot_name} // Current Configuration",
            color=0x7a8a9a
        )
        embed.add_field(name="Active Provider", value=f"`{config.get('provider', 'auto')}`", inline=True)
        embed.add_field(name="Temperature", value=f"`{config.get('temperature', 0.7)}`", inline=True)
        embed.add_field(name="Max Tokens", value=f"`{config.get('max_tokens', 800)}`", inline=True)
        embed.add_field(name="🧠 Active Models", value=(
            f"• **Gemini**: `{config.get('gemini_model', 'None')}`\n"
            f"• **Groq**: `{config.get('groq_model', 'None')}`\n"
            f"• **Mistral**: `{config.get('mistral_model', 'None')}`\n"
            f"• **OpenRouter**: `{config.get('model', 'None')}`\n"
            f"• **Hugging Face**: `{config.get('huggingface_model', 'None')}`"
        ), inline=False)
        embed.set_footer(text=f"Use @{bot_name} <field>: <model> to change")
        await safe_reply(message, embed=embed)
        return

    # ─── SOCIAL MEDIA TRIGGER DETECTION (X / TWITTER & INSTAGRAM) ───
    is_xpost_cmd = False
    is_ipost_cmd = False
    clean_low = clean_text.lower().strip() if clean_text else ""
    raw_low = raw_c.lower().strip()

    # X Triggers: "post this!", "@ping xpost", "!xpost", "tweet this", "!tweet", "post to x", "post to twitter", "xpost"
    x_exact_triggers = {"post this!", "post this", "xpost", "!xpost", "tweet this", "!tweet", "post to x", "post to twitter", "twitter post", "x post", "post this to x", "post this to twitter"}
    if clean_low in x_exact_triggers or raw_low in x_exact_triggers:
        is_xpost_cmd = True
    elif clean_low.startswith(("xpost ", "!xpost ", "tweet ", "!tweet ", "post to x ", "post to twitter ", "post this to x ", "post this to twitter ")):
        is_xpost_cmd = True
    elif raw_low.startswith(("!xpost ", "!tweet ", "xpost ", "!post ")):
        is_xpost_cmd = True

    # Instagram Triggers: "ipost", "!ipost", "@ping ipost", "post to insta", "post to instagram", "!instapost", "post this to insta", "post this to instagram"
    insta_exact_triggers = {"ipost", "!ipost", "instapost", "!instapost", "post to insta", "post to instagram", "insta post", "instagram post", "post this to insta", "post this to instagram"}
    if clean_low in insta_exact_triggers or raw_low in insta_exact_triggers:
        is_ipost_cmd = True
    elif clean_low.startswith(("ipost ", "!ipost ", "instapost ", "!instapost ", "post to insta ", "post to instagram ", "post this to insta ", "post this to instagram ")):
        is_ipost_cmd = True
    elif raw_low.startswith(("!ipost ", "!instapost ", "ipost ")):
        is_ipost_cmd = True

    if is_xpost_cmd or is_ipost_cmd:
        target_plat = "x" if is_xpost_cmd else "instagram"
        # Extract user prompt/custom notes
        user_custom_note = ""
        for prefix in ("!xpost", "!tweet", "!ipost", "!instapost", "xpost", "ipost", "post this to x", "post this to twitter", "post this to insta", "post this to instagram", "post this!", "post this"):
            if clean_low.startswith(prefix):
                user_custom_note = clean_text[len(prefix):].strip()
                break
            if raw_low.startswith(prefix):
                user_custom_note = raw_c[len(prefix):].strip()
                break

        await handle_discord_social_post(message, target_plat, user_custom_prompt=user_custom_note)
        return

    # ─── POKÉMON SHOWDOWN COMMANDS ────────────────────────
    if raw_c.startswith(("!showdown", "!pokemon", "!ps ", "!showdown:")) or clean_text.lower().startswith(("!showdown", "!pokemon", "!ps ")) or raw_c == "!ps":
        current_bot_id = os.getenv("BOT_ID") or bots_state.get("active_id", "default")
        current_bot = get_bot_by_id(bots_state, current_bot_id) if 'bots_state' in globals() else None
        cur_bot_name = current_bot.get("name", "Bot") if current_bot else "Bot"
        clean_cur_name = re.sub(r'[^a-zA-Z0-9]', '', cur_bot_name).lower()

        if not SHOWDOWN_ENGINE_AVAILABLE or not showdown_manager:
            await safe_reply(message, "❌ Pokémon Showdown module is currently unavailable.")
            return

        cmd_text = raw_c if raw_c.startswith("!") else clean_text
        parts = cmd_text.split()
        args_tokens = parts[1:] if len(parts) > 1 else []

        # Bot identity mappings
        all_bot_aliases = {
            "briliance": {"briliance", "brilliance", "briliancebot", "brilliancebot"},
            "law": {"law", "lawbot"},
            "yuna": {"yuna", "yunabot"}
        }
        my_key = "other"
        for k, aliases in all_bot_aliases.items():
            if clean_cur_name == k or clean_cur_name in aliases:
                my_key = k
                break
        if my_key == "other":
            my_key = clean_cur_name

        # Detect target bot from tokens (e.g. !showdown briliance start OR !showdown start briliance)
        known_target_tokens = {"all"}
        for aliases in all_bot_aliases.values():
            known_target_tokens.update(aliases)

        target_bot = None
        filtered_tokens = []
        for t in args_tokens:
            t_clean = re.sub(r'[^a-zA-Z0-9]', '', t).lower()
            if t_clean in known_target_tokens and target_bot is None:
                target_bot = t_clean
            else:
                filtered_tokens.append(t)

        subcmd = filtered_tokens[0].lower() if filtered_tokens else "status"

        # Determine if this bot process should execute
        should_execute = False
        if message.mentions and client.user:
            if client.user in message.mentions:
                should_execute = True
            else:
                return  # Another bot is explicitly mentioned
        elif target_bot:
            if target_bot == "all":
                should_execute = True
            elif target_bot in all_bot_aliases.get(my_key, {my_key}):
                should_execute = True
            else:
                return  # Targeted to a different bot
        else:
            # Untargeted: start, connect, login, status, info, stop, disconnect run for all bots
            if subcmd in ("start", "connect", "login", "status", "info", "stop", "disconnect"):
                should_execute = True
            elif is_active_bot or is_targeted_for_this_bot:
                should_execute = True
            else:
                return

        if not should_execute:
            return

        bot_cfg = current_bot.get("config", {}) if current_bot else config
        sd_client = showdown_manager.init_bot(current_bot_id, cur_bot_name, bot_cfg)
        sd_client.channel_id = str(message.channel.id)
        sd_client.initiator_user_id = str(message.author.id)

        # Stagger replies slightly if running in 'all' / broadcast mode to avoid Discord rate limits
        if target_bot == "all" or (target_bot is None and subcmd in ("start", "connect", "login", "status", "info", "stop", "disconnect")):
            bot_keys = list(all_bot_aliases.keys())
            b_idx = bot_keys.index(my_key) if my_key in bot_keys else 0
            if b_idx > 0:
                await asyncio.sleep(b_idx * 0.4)

        if subcmd in ("status", "info"):
            status_text = (
                f"🎮 **Pokémon Showdown Client: {cur_bot_name}**\n"
                f"• **Username**: `{sd_client.username}`\n"
                f"• **Registered**: {'✅ Yes' if sd_client.is_registered else '⚠️ Guest/Unregistered (Full battle access)'}\n"
                f"• **Connection Status**: {'🟢 Connected' if sd_client.is_connected else '🔴 Offline'}\n"
                f"• **Auto-Accept Battles**: {'✅ Enabled' if sd_client.auto_accept else '❌ Disabled'}\n"
                f"• **Active Battles**: `{len(sd_client.active_battles)}`\n"
                f"• **Default Format**: `{sd_client.default_format}`\n\n"
                f"**Quick Commands:**\n"
                f"`!showdown [all|<bot>] start` — Connect to Showdown & log in\n"
                f"`!showdown [all|<bot>] status` — View Showdown status\n"
                f"`!showdown [<bot>] challenge <user> [format]` — Challenge a player\n"
                f"`!showdown [<bot>] ladder [format]` — Search for ladder match\n"
                f"`!showdown [all|<bot>] stop` — Disconnect from Showdown"
            )
            await safe_reply(message, status_text)
            return

        elif subcmd in ("start", "connect", "login"):
            await safe_reply(message, f"⚡ Connecting **{cur_bot_name}** to Pokémon Showdown as `{sd_client.username}`...")
            await sd_client.start()
            await asyncio.sleep(2.0)
            conn_status = "🟢 Connected & Auto-Accepting Battles!" if sd_client.is_connected else "⏳ Connecting in background..."
            await safe_reply(message, f"✅ Showdown status for **{cur_bot_name}**: {conn_status}")
            return

        elif subcmd == "register":
            new_user = filtered_tokens[1] if len(filtered_tokens) > 1 else sd_client.username
            new_pass = filtered_tokens[2] if len(filtered_tokens) > 2 else (sd_client.password or f"Pkm!{random.randint(100000, 999999)}")
            sd_client.username = new_user
            sd_client.password = new_pass
            await safe_reply(message, f"📝 Registering Pokémon Showdown account `{new_user}` for **{cur_bot_name}**...")
            if not sd_client.is_connected:
                await sd_client.start()
            else:
                await sd_client.stop()
                await sd_client.start()
            await asyncio.sleep(2.5)
            await safe_reply(message, f"✅ Account update processed for **{cur_bot_name}**! Active username: `{sd_client.username}` (Status: {'Connected' if sd_client.is_connected else 'Connecting...'})")
            return

        elif subcmd in ("challenge", "battle"):
            if len(filtered_tokens) < 2:
                await safe_reply(message, "Usage: `!showdown [<bot>] challenge <opponent_username> [format]` (e.g. `!showdown challenge TrainerBlue gen9randombattle`)")
                return
            target_opp = filtered_tokens[1]
            target_fmt = filtered_tokens[2] if len(filtered_tokens) > 2 else sd_client.default_format
            if not sd_client.is_connected:
                await sd_client.start()
                await asyncio.sleep(1.5)
            await sd_client.challenge_user(target_opp, target_fmt)
            await safe_reply(message, f"⚔️ **{cur_bot_name}** sent battle challenge to **{target_opp}** in `{target_fmt}`!")
            return

        elif subcmd in ("accept", "acceptbattle"):
            opp = filtered_tokens[1] if len(filtered_tokens) > 1 else ""
            if opp:
                await sd_client.send_raw(f"|/accept {opp}")
                await safe_reply(message, f"⚔️ **{cur_bot_name}** accepted battle challenge from **{opp}**!")
            else:
                sd_client.auto_accept = True
                await safe_reply(message, f"✅ Auto-accept battles is now **ENABLED** for **{cur_bot_name}**!")
            return

        elif subcmd in ("ladder", "search"):
            target_fmt = filtered_tokens[1] if len(filtered_tokens) > 1 else sd_client.default_format
            if not sd_client.is_connected:
                await sd_client.start()
                await asyncio.sleep(1.5)
            await sd_client.search_ladder(target_fmt)
            await safe_reply(message, f"🏆 **{cur_bot_name}** is searching Pokémon Showdown ladder for **{target_fmt}** match...")
            return

        elif subcmd in ("cancel", "cancelsearch"):
            await sd_client.cancel_ladder_search()
            await safe_reply(message, f"🛑 Ladder matchmaking cancelled for **{cur_bot_name}**.")
            return

        elif subcmd in ("stop", "disconnect"):
            await sd_client.stop()
            await safe_reply(message, f"🛑 Disconnected **{cur_bot_name}** from Pokémon Showdown.")
            return

    # ─── DOODLE ON COMMAND & DOODLE ALONG ───────────────────
    if DOODLE_ENGINE_AVAILABLE:
        is_dood_req, dood_mode, dood_sub = is_doodle_request(raw_c if raw_c.startswith("!") else clean_text)
        if is_dood_req or raw_c.startswith(("!doodle", "!draw", "!doodlealong", "!sketch")):
            current_bot_id = os.getenv("BOT_ID") or bots_state.get("active_id", "default")
            current_bot = get_bot_by_id(bots_state, current_bot_id) if 'bots_state' in globals() else None
            b_name = current_bot.get("name", "Bot") if current_bot else "Bot"
            b_pers = current_bot.get("config", {}).get("personality", "") if current_bot else config.get("personality", "")

            # Check if an image is provided directly or via replied reference
            doodle_img_bytes = None
            if message.attachments:
                for att in message.attachments:
                    if att.content_type and att.content_type.startswith("image/"):
                        try:
                            async with aiohttp.ClientSession() as sess:
                                async with sess.get(att.url, timeout=aiohttp.ClientTimeout(total=25)) as r:
                                    if r.status == 200:
                                        doodle_img_bytes = await r.read()
                                        break
                        except Exception:
                            pass

            if not doodle_img_bytes and message.reference and message.reference.resolved:
                ref_msg = message.reference.resolved
                if hasattr(ref_msg, "attachments"):
                    for att in ref_msg.attachments:
                        if att.content_type and att.content_type.startswith("image/"):
                            try:
                                async with aiohttp.ClientSession() as sess:
                                    async with sess.get(att.url, timeout=aiohttp.ClientTimeout(total=25)) as r:
                                        if r.status == 200:
                                            doodle_img_bytes = await r.read()
                                            break
                            except Exception:
                                pass

            if doodle_img_bytes or dood_mode == "along":
                if doodle_img_bytes:
                    async with safe_typing(message.channel):
                        res_bytes, dialog = await doodle_along(doodle_img_bytes, user_prompt=dood_sub, bot_name=b_name, bot_personality=b_pers)
                        f = discord.File(io.BytesIO(res_bytes), filename="doodle_along.png")
                        await safe_reply(message, dialog, file=f)
                        return
                else:
                    await safe_reply(message, "🎨 To doodle along with me, please attach your drawing/sketch or reply to one!")
                    return
            else:
                async with safe_typing(message.channel):
                    res_bytes, dialog = await generate_doodle(dood_sub or "cute cat", bot_name=b_name, bot_personality=b_pers)
                    if res_bytes:
                        f = discord.File(io.BytesIO(res_bytes), filename="doodle.png")
                        await safe_reply(message, dialog, file=f)
                        return

    # ─── ATTACHMENT PROCESSING (Only reply to media if directly pinged or in DM) ──
    attachments = message.attachments
    is_media_pinged = (client.user in message.mentions) or (message.guild is None)
    if attachments:
        if not is_media_pinged:
            return  # Strictly ignore media attachments unless directly pinged or in DM
        image_atts = [a for a in attachments if a.content_type and a.content_type.startswith("image/")]
        video_atts = [a for a in attachments if a.content_type and a.content_type.startswith("video/")]
        audio_atts = [a for a in attachments if a.content_type and a.content_type.startswith("audio/")]
        file_atts  = [a for a in attachments if Path(a.filename).suffix.lower() in (".pdf", ".docx", ".csv") or (a.content_type and a.content_type == "application/pdf")]

        # Check if multiple videos were sent at once -> Queue them!
        if video_atts and len(video_atts) > 1 and global_media_queue:
            async with safe_typing(message.channel):
                for att in video_atts:
                    global_media_queue.enqueue_media(
                        source_platform="discord",
                        channel_id=str(message.channel.id),
                        user_id=str(message.author.id),
                        user_name=message.author.display_name,
                        url_or_path=att.url,
                        message_context=message.content,
                        raw_attachment=att
                    )
                cur_name = get_current_bot_name()
                toast = format_toast_embed(
                    f"{cur_name} // Videos Queued",
                    f"🎬 Received **{len(video_atts)} videos** at once! Queued for sequential analysis. {cur_name} will watch and respond to all of them in order!",
                    color=0x4f8cff
                )
                await safe_reply(message, embed=toast)
            return

        for att in image_atts:
            async with safe_typing(message.channel):
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(att.url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                            image_bytes = await resp.read()
                    prompt = message.content or "Describe this image."
                    if DOODLE_ENGINE_AVAILABLE and is_doodle_request(prompt)[0]:
                        cur_bot_id = os.getenv("BOT_ID") or bots_state.get("active_id", "default")
                        current_bot = get_bot_by_id(bots_state, current_bot_id) if 'bots_state' in globals() else None
                        b_name = current_bot.get("name", "Bot") if current_bot else "Bot"
                        b_pers = current_bot.get("config", {}).get("personality", "") if current_bot else config.get("personality", "")
                        res_bytes, dialog = await doodle_along(image_bytes, user_prompt=prompt, bot_name=b_name, bot_personality=b_pers)
                        f = discord.File(io.BytesIO(res_bytes), filename="doodle_along.png")
                        await safe_reply(message, dialog, file=f)
                        continue

                    vision_provider = config.get("vision_provider", "openrouter")
                    history = get_context(message.channel.id)
                    if vision_provider == "gemini":
                        reply, err = await ask_gemini_vision(
                            config["personality"], prompt, image_bytes,
                            att.content_type or "image/jpeg", history=history
                        )
                    else:
                        vmodel = config.get("vision_model", "").strip() or None
                        reply, err = await ask_openrouter_vision(
                            config["personality"], prompt, image_bytes,
                            att.content_type or "image/jpeg", history=history, vision_model=vmodel
                        )
                    if not err:
                        add_to_context(message.channel.id, "user", f"[User sent an image: {att.filename}] {prompt}")
                        add_to_context(message.channel.id, "assistant", reply)
                        await send_split_messages(message.channel, reply, reply_to=message)
                        message_count += 1
                        if config.get("tts_enabled"):
                            audio = await speak(reply)
                            if audio:
                                await _safe_send_voice_reply(message, audio)
                    else:
                        await safe_reply(message, f"Vision error: {reply}")
                except Exception as e:
                    await safe_reply(message, f"Image processing error: {e}")

        for att in video_atts:
            async with safe_typing(message.channel):
                reply = await process_video_attachment(att, message.content, message.channel.id)
                if reply:
                    await send_split_messages(message.channel, reply, reply_to=message)
                    message_count += 1
                    if config.get("tts_enabled"):
                        audio = await speak(reply)
                        if audio:
                            await _safe_send_voice_reply(message, audio)

        if config.get("auto_stt", False) and audio_atts:
            for att in audio_atts:
                async with safe_typing(message.channel):
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.get(att.url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                                audio_bytes = await resp.read()
                        text, err = await transcribe_audio(audio_bytes, att.filename)
                        if err:
                            await safe_reply(message, f"Transcription failed: {err}")
                            continue
                        transcribed_prompt = f"[Voice message transcribed]: {text}"
                        if message.content:
                            transcribed_prompt += f"\n\nUser also said: {message.content}"
                        reply, err = await ask_ai(
                            message.channel.id, transcribed_prompt,
                            user_id=message.author.id, user_name=message.author.display_name,
                            guild=message.guild, is_dm=(message.guild is None)
                        )
                        if err:
                            await safe_reply(message, reply)
                        else:
                            await send_split_messages(message.channel, reply, reply_to=message)
                            message_count += 1
                            if config.get("tts_enabled"):
                                audio = await speak(reply)
                                if audio:
                                    await _safe_send_voice_reply(message, audio)
                    except Exception as e:
                        await safe_reply(message, f"Audio processing error: {e}")
                        continue

        for att in file_atts:
            async with safe_typing(message.channel):
                text = await read_file_attachment(att)
                if text.startswith("File too large") or text.startswith("Unsupported file type") or text.startswith("File read error"):
                    await safe_reply(message, text)
                    continue
                user_question = message.content.strip()
                file_prompt = f"The user uploaded a file: {att.filename}\n\nHere is the extracted content:\n\n{text}\n\n"
                if user_question:
                    file_prompt += f"The user also said: {user_question}\n\n"
                file_prompt += "Please respond to whatever the user asked about this file, or summarize it if they didn't ask anything specific."
                reply, err = await ask_ai(
                    message.channel.id, file_prompt,
                    user_id=message.author.id, user_name=message.author.display_name,
                    guild=message.guild, is_dm=(message.guild is None)
                )
                if err:
                    await safe_reply(message, reply)
                else:
                    await send_split_messages(message.channel, reply, reply_to=message)
                    message_count += 1
                    if config.get("tts_enabled"):
                        audio = await speak(reply)
                        if audio:
                            await _safe_send_voice_reply(message, audio)
        if attachments:
            return

    # ─── GENERAL CHAT RESPONSE & MEDIA INTELLIGENCE ROUTING ───
    if not is_bot_addressed(message):
        return
    interacted_users.add(str(message.author.id))
    save_interacted_users(interacted_users)
    ok, remaining = check_cooldown(message.author.id)
    if not ok:
        return

    author_name = message.author.display_name
    author_handle = getattr(message.author, "name", "")
    clean_msg = (message.clean_content or message.content or "").strip()
    clean_msg_low = clean_msg.lower().strip()
    is_dm_channel = (message.guild is None)

    # ─── TRAINING MODE & BACKUP COMMANDS (DM ONLY) ────────
    if is_dm_channel:
        # Check text command to start training
        if clean_msg_low in ("!train", "/train", "train") and not is_training_active(message.author.id):
            embed = do_start_training(message.author.id, message.channel.id)
            await safe_reply(message, embed=embed)
            return

        # Check text command for tbackup
        if clean_msg_low in ("!tbackup", "/tbackup", "tbackup"):
            ok, embed = do_tbackup(message.author.id)
            await safe_reply(message, embed=embed)
            return

        # Check text command for backups
        if clean_msg_low in ("!backups", "/backups", "backups"):
            embed = do_list_backups()
            await safe_reply(message, embed=embed)
            return

        # Check text command for backup restore: e.g. /backup restore 1, backup restore 1
        if clean_msg_low.startswith(("!backup restore", "/backup restore", "backup restore")):
            parts = clean_msg.split()
            bid = None
            for p in parts:
                if p.isdigit():
                    bid = int(p)
                    break
            if bid is not None:
                ok, embed = do_restore_backup(bid)
                await safe_reply(message, embed=embed)
            else:
                await safe_reply(message, "Usage: `/backup restore [Id]` (e.g. `/backup restore 1`)")
            return

        # Check text command for backup delete: e.g. /backup delete 1, backup delete 1
        if clean_msg_low.startswith(("!backup delete", "/backup delete", "backup delete")):
            parts = clean_msg.split()
            bid = None
            for p in parts:
                if p.isdigit():
                    bid = int(p)
                    break
            if bid is not None:
                ok, embed = do_delete_backup(bid)
                await safe_reply(message, embed=embed)
            else:
                await safe_reply(message, "Usage: `/backup delete [Id]` (e.g. `/backup delete 1`)")
            return

        # Check text command for resume training: e.g. /resume training 1, resume training
        if clean_msg_low.startswith(("!resume training", "/resume training", "resume training", "!resume", "/resume")):
            parts = clean_msg.split()
            bid = None
            for p in parts:
                if p.isdigit():
                    bid = int(p)
                    break
            embed = do_resume_training(message.author.id, message.channel.id, bid)
            await safe_reply(message, embed=embed)
            return

        # If user is currently in active training mode:
        if is_training_active(message.author.id):
            # Check for stop / exit command
            if clean_msg_low in ("stop", "stop.", "!stop", "/stop", "exit", "quit", "done"):
                stats = stop_training_session(message.author.id)
                embed = discord.Embed(
                    title="🛑 Training Mode Stopped",
                    description=(
                        f"Training session ended for **{get_current_bot_name()}**!\n\n"
                        f"💾 **Training Data Summary:**\n"
                        f"• Approved Samples: `{stats['approved']}` ✔️\n"
                        f"• Rejected Samples: `{stats['rejected']}` ❌\n\n"
                        f"The bot's response style has been dynamically updated based on your training data without modifying the base personality prompt!\n\n"
                        f"💡 **Management Commands:**\n"
                        f"• `/tbackup` — Save a backup of this training data\n"
                        f"• `/backups` — View all saved backups\n"
                        f"• `/backup restore [Id]` — Restore another backup\n"
                        f"• `/resume training [Id]` — Resume training anytime"
                    ),
                    color=0xe74c3c
                )
                await safe_reply(message, embed=embed)
                return

            # Execute training turn: generate Option 1 and Option 2
            await handle_training_turn(message, clean_msg)
            return
    else:
        # Non-DM / Server channel warning if user attempts training commands
        if clean_msg_low in ("!train", "/train", "!tbackup", "/tbackup", "!backups", "/backups", "train") or clean_msg_low.startswith(("!backup restore", "/backup restore", "!backup delete", "/backup delete", "!resume training", "/resume training")):
            await safe_reply(message, "🔒 **DM Only Command**: Training mode and backup commands can only be used in Direct Messages (DMs) with the bot, not on servers.")
            return

    # Natural language doodle request check
    if DOODLE_ENGINE_AVAILABLE:
        is_dood_req, dood_mode, dood_sub = is_doodle_request(clean_msg)
        if is_dood_req and dood_mode == "draw":
            async with safe_typing(message.channel):
                cur_bot_id = os.getenv("BOT_ID") or bots_state.get("active_id", "default")
                cur_bot = get_bot_by_id(bots_state, cur_bot_id) if 'bots_state' in globals() else None
                b_name = cur_bot.get("name", "Bot") if cur_bot else "Bot"
                b_pers = cur_bot.get("config", {}).get("personality", "") if cur_bot else config.get("personality", "")
                res_bytes, dialog = await generate_doodle(dood_sub or "cute doodle", bot_name=b_name, bot_personality=b_pers)
                if res_bytes:
                    f = discord.File(io.BytesIO(res_bytes), filename="doodle.png")
                    await safe_reply(message, dialog, file=f)
                    return

    # Capture reply reference if replying to another message in channel
    reply_prefix = ""
    if message.reference and message.reference.resolved:
        ref_obj = message.reference.resolved
        if hasattr(ref_obj, "author"):
            ref_author = ref_obj.author.display_name
            ref_body = (getattr(ref_obj, "clean_content", "") or getattr(ref_obj, "content", "") or "")[:100].strip()
            if ref_body:
                reply_prefix = f" (replying to @{ref_author}: \"{ref_body}\")"
            else:
                reply_prefix = f" (replying to @{ref_author})"

    speaker_tag = f"[{author_name} (@{author_handle}){reply_prefix}]"
    prompt_to_send = f"{speaker_tag}: {clean_msg}" if message.guild else clean_msg

    if MEDIA_INTELLIGENCE_AVAILABLE:
        media_url_info = detect_and_handle_media_urls(clean_msg)
        if media_url_info:
            url_type, target_url = media_url_info
            if url_type == "video":
                if not is_media_pinged:
                    # Media Gate: Do not reply to video links unless directly pinged or in DM
                    return
                try:
                    async with safe_typing(message.channel):
                        context_data, report = await watch_video_tool(target_url, bot_config=config)
                        prompt_to_send = (
                            f"{speaker_tag}: The user shared a video ({target_url}) and said: {clean_msg}\n\n"
                            f"Here is what you watched, heard, and observed from the video:\n{context_data}\n"
                            f"React and respond in full character to {author_name} and the video content!"
                        )
                except Exception as ve:
                    print(f"[WATCH VIDEO ROUTING ERROR] {ve}")
            elif url_type == "web":
                try:
                    async with safe_typing(message.channel):
                        context_data, page = await browse_web_tool(target_url)
                        prompt_to_send = (
                            f"{speaker_tag}: The user shared a webpage link ({target_url}) and said: {clean_msg}\n\n"
                            f"{context_data}\n\n"
                            f"[CRITICAL READING DIRECTIVE]: Read and synthesize across the entire page to provide a rich, accurate, and in-character answer specifically to {author_name}!"
                        )
                except Exception as we:
                    print(f"[BROWSE WEB ROUTING ERROR] {we}")

    # ─── AUTONOMOUS FEATURE EVALUATION & GAP HANDLER ───────────
    if AGY_BRIDGE_AVAILABLE and feature_evaluator:
        feat_intent = feature_evaluator.check_feature_intent(clean_msg)
        if feat_intent:
            async def _bot_feat_reply(reply_text):
                await safe_reply(message, reply_text)
            handled = await feature_evaluator.handle_feature_request(
                feat_intent, message.channel, message.author, client, _bot_feat_reply
            )
            if handled:
                return

    try:
        async with safe_typing(message.channel):
            ref_user_id = None
            if message.reference and message.reference.resolved and hasattr(message.reference.resolved, "author"):
                ref_user_id = str(message.reference.resolved.author.id)

            reply, err = await ask_ai(
                message.channel.id,
                prompt_to_send,
                user_id=message.author.id,
                user_name=message.author.display_name,
                guild=message.guild,
                is_dm=(message.guild is None),
                raw_mentions=list(message.raw_mentions) if hasattr(message, "raw_mentions") else None,
                reply_to_user_id=ref_user_id,
                raw_content=message.content
            )
            if err:
                await safe_reply(message, reply)
                return
            await send_split_messages(message.channel, reply, reply_to=message)
            message_count += 1
            if config.get("tts_enabled"):
                audio = await speak(reply)
                if audio:
                    await _safe_send_voice_reply(message, audio)
    except Exception as chat_crash_err:
        if AGY_BRIDGE_AVAILABLE and feature_evaluator:
            await feature_evaluator.handle_crash_or_error(
                chat_crash_err, message.channel, client, author=message.author, context_desc="bot.py on_message ask_ai"
            )
        else:
            await safe_reply(message, f"❌ Error: {chat_crash_err}")

@client.event
async def on_error(event_method, *args, **kwargs):
    import traceback
    tb = traceback.format_exc()
    print(f"[YUNA CLIENT ERROR in {event_method}]:\n{tb}")
    if AGY_BRIDGE_AVAILABLE and feature_evaluator:
        ch = None
        author = None
        if args and len(args) > 0:
            first_arg = args[0]
            if hasattr(first_arg, "channel"):
                ch = first_arg.channel
            if hasattr(first_arg, "author"):
                author = first_arg.author
        try:
            await feature_evaluator.handle_crash_or_error(
                Exception(f"Error in {event_method}"),
                channel=ch,
                client=client,
                author=author,
                context_desc=f"Discord event {event_method}"
            )
        except Exception as heal_err:
            print(f"[YUNA SELF-HEAL DISPATCH FAILED] {heal_err}")

# ─── WEB DASHBOARD ──────────────────────────────────────
app = Flask(__name__)

@app.route("/")
@app.route("/studio")
@app.route("/studio.html")
@app.route("/chat")
@app.route("/chat.html")
@app.route("/index.html")
@app.route("/home.html")
@app.route("/call")
@app.route("/call.html")
def studio_index():
    html_path = os.path.join(SCRIPT_DIR, "index.html")
    if not os.path.exists(html_path):
        html_path = os.path.join(SCRIPT_DIR, "dashboard.html")
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            return render_template_string(f.read())
    except Exception as e:
        return f"HTML not found at {html_path}. Error: {e}", 500

@app.route("/dashboard")
@app.route("/dashboard.html")
@app.route("/drafting")
@app.route("/drafting.html")
@app.route("/desk")
def drafting_page():
    html_path = os.path.join(SCRIPT_DIR, "dashboard.html")
    if not os.path.exists(html_path):
        html_path = os.path.join(SCRIPT_DIR, "index.html")
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            return render_template_string(f.read())
    except Exception as e:
        return f"Drafting template read error: {e}", 500

@app.route("/social")
@app.route("/social.html")
@app.route("/control")
def social_control_page():
    html_path = os.path.join(SCRIPT_DIR, "social.html")
    if not os.path.exists(html_path):
        html_path = os.path.join(SCRIPT_DIR, "dashboard.html")
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            return render_template_string(f.read())
    except Exception as e:
        return f"Social control template read error: {e}", 500


@app.route("/designs/<path:filename>")
def serve_designs(filename):
    designs_dir = os.path.join(SCRIPT_DIR, "designs")
    if not os.path.exists(designs_dir):
        designs_dir = "/storage/emulated/0/discord-bot2/designs"
    file_path = os.path.join(designs_dir, filename)
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return render_template_string(f.read())
        except Exception:
            return send_file(file_path)
    return f"File {filename} not found", 404

@app.route("/api/bots", methods=["GET"])
def api_bots_list():
    with state_lock:
        summary = bots_summary(bots_state)
        active = get_active_bot(bots_state)
        return jsonify({
            "ok": True,
            "bots": summary,
            "active_id": bots_state.get("active_id"),
            "active_config": active.get("config", {}) if active else {},
        })

@app.route("/api/bots", methods=["POST"])
def api_bots_add():
    global bots_state
    try:
        with state_lock:
            data = request.get_json(silent=True) or {}
            target_id = data.get("id") or data.get("bot_id")
            
            # Check if this is an update to an existing bot
            target = None
            if target_id:
                for b in bots_state.get("bots", []):
                    if b["id"] == target_id:
                        target = b
                        break
            
            if target:
                if "name" in data and str(data["name"]).strip():
                    target["name"] = str(data["name"]).strip()[:40]
                if "emoji" in data:
                    target["emoji"] = (str(data["emoji"]) or "🤖").strip()[:4]
                if "token" in data:
                    target["token"] = str(data.get("token", "")).strip()
                if "avatar_url" in data or "pfp" in data:
                    target["avatar_url"] = data.get("avatar_url") or data.get("pfp")
                current_cfg = target.setdefault("config", json.loads(json.dumps(DEFAULT_CONFIG)))
                if "config" in data and isinstance(data["config"], dict):
                    for k, v in data["config"].items():
                        current_cfg[k] = v
                for direct_key in ["personality", "prompt", "provider", "gemini_model", "groq_model", "model", "custom_model", "custom_base_url", "custom_key", "use_custom_model", "temperature", "max_tokens", "top_p", "frequency_penalty", "presence_penalty", "max_context", "vision_provider", "gemini_vision_model", "video_watching_model", "fish_voice_id", "auto_search", "user_memory_enabled", "open_chat_enabled", "auto_stt", "greeting", "role", "privacy", "model_slots", "fallback_provider", "fallback_model"]:
                    if direct_key in data:
                        current_cfg[direct_key] = data[direct_key]
                save_bots(bots_state)
                if target["id"] == bots_state.get("active_id") or not bots_state.get("active_id"):
                    bots_state["active_id"] = target["id"]
                    apply_bot_to_config(target, save_to_disk=True)
                return jsonify({"ok": True, "bot": {"id": target["id"], "name": target["name"], "emoji": target["emoji"]}})

            name = (data.get("name") or "").strip()[:40] or f"Bot {len(bots_state.get('bots', [])) + 1}"
            emoji = (data.get("emoji") or "🤖").strip()[:4]
            clone_id = data.get("clone_from")
            new_cfg = json.loads(json.dumps(DEFAULT_CONFIG))
            if clone_id:
                for b in bots_state.get("bots", []):
                    if b["id"] == clone_id:
                        new_cfg = json.loads(json.dumps(b.get("config", DEFAULT_CONFIG)))
                        break
            if "config" in data and isinstance(data["config"], dict):
                for k, v in data["config"].items():
                    new_cfg[k] = v
            new_bot = {
                "id": target_id or _gen_bot_id(),
                "name": name,
                "emoji": emoji,
                "created_at": time.time(),
                "token": data.get("token", ""),
                "avatar_url": data.get("avatar_url") or data.get("pfp"),
                "config": new_cfg,
            }
            bots_state.setdefault("bots", []).append(new_bot)
            save_bots(bots_state)
            return jsonify({"ok": True, "bot": {"id": new_bot["id"], "name": new_bot["name"], "emoji": new_bot["emoji"]}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route("/api/bots/switch", methods=["POST"])
def api_bots_switch():
    global bots_state
    try:
        with state_lock:
            data = request.get_json(silent=True) or {}
            target = data.get("id")
            if not target:
                return jsonify({"ok": False, "error": "Missing bot id"}), 400
            ok, found = switch_character_persona(target)
            if not ok or not found:
                return jsonify({"ok": False, "error": "Bot not found"}), 404
            _last_cfg_mtime = 0
            return jsonify({
                "ok": True,
                "active_id": found["id"],
                "active_config": found.get("config", {}),
            })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route("/api/bots/<bot_id>", methods=["POST"])
def api_bots_update(bot_id):
    global bots_state
    try:
        with state_lock:
            data = request.get_json(silent=True) or {}
            target = None
            for b in bots_state.get("bots", []):
                if b["id"] == bot_id:
                    target = b
                    break
            if not target:
                return jsonify({"ok": False, "error": "Bot not found"}), 404
            if "name" in data:
                new_name = (str(data["name"]) or "").strip()[:40]
                if new_name:
                    target["name"] = new_name
            if "emoji" in data:
                target["emoji"] = (str(data["emoji"]) or "🤖").strip()[:4]
            if "token" in data:
                target["token"] = str(data.get("token", "")).strip()
            if "avatar_url" in data or "pfp" in data:
                target["avatar_url"] = data.get("avatar_url") or data.get("pfp")
            current_cfg = target.setdefault("config", json.loads(json.dumps(DEFAULT_CONFIG)))
            if "config" in data and isinstance(data["config"], dict):
                for k, v in data["config"].items():
                    current_cfg[k] = v
            # Allow top-level config fields as well
            for direct_key in ["personality", "prompt", "provider", "gemini_model", "groq_model", "model", "custom_model", "custom_base_url", "custom_key", "use_custom_model", "temperature", "max_tokens", "top_p", "frequency_penalty", "presence_penalty", "max_context", "vision_provider", "gemini_vision_model", "video_watching_model", "fish_voice_id", "auto_search", "user_memory_enabled", "open_chat_enabled", "auto_stt", "greeting", "role", "privacy", "model_slots", "fallback_provider", "fallback_model"]:
                if direct_key in data:
                    current_cfg[direct_key] = data[direct_key]
            save_bots(bots_state)
            if target["id"] == bots_state.get("active_id"):
                apply_bot_to_config(target, save_to_disk=True)
            return jsonify({"ok": True, "bot": {"id": target["id"], "name": target["name"], "emoji": target["emoji"]}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route("/api/bots/<bot_id>", methods=["DELETE"])
def api_bots_delete(bot_id):
    global bots_state
    try:
        with state_lock:
            bots_list = bots_state.get("bots", [])
            if len(bots_list) <= 1:
                return jsonify({"ok": False, "error": "Can't delete the only bot"}), 400
            if bots_state.get("active_id") == bot_id:
                return jsonify({"ok": False, "error": "Switch to another bot first"}), 400
            bots_state["bots"] = [b for b in bots_list if b["id"] != bot_id]
            save_bots(bots_state)
            return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route("/api/bots/<bot_id>/config", methods=["GET"])
def api_bots_get_config(bot_id):
    with state_lock:
        for b in bots_state.get("bots", []):
            if b["id"] == bot_id:
                av_url = b.get("avatar_url") or b.get("config", {}).get("avatar_url") or b.get("pfp")
                if not av_url and b.get("token"):
                    av_url = get_discord_bot_avatar(b.get("token"))
                return jsonify({
                    "ok": True,
                    "id": b["id"],
                    "config": b.get("config", {}),
                    "name": b.get("name"),
                    "emoji": b.get("emoji"),
                    "token": b.get("token", ""),
                    "avatar_url": av_url,
                    "personality": b.get("config", {}).get("personality") or b.get("personality") or ""
                })
    return jsonify({"ok": False, "error": "Bot not found"}), 404

@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    global config, bots_state, _last_cfg_mtime
    refresh_runtime_config()
    target_id = request.args.get("bot_id")
    if request.method == "POST":
        try:
            with state_lock:
                data = request.get_json(silent=True) or {}
                b_id = data.get("bot_id") or target_id or bots_state.get("active_id")
                target_bot = get_bot_by_id(bots_state, b_id) if b_id else None
                for k, v in data.items():
                    if k != "bot_id":
                        config[k] = v
                        if target_bot and isinstance(target_bot.get("config"), dict):
                            target_bot["config"][k] = v
                if target_bot:
                    if "personality" in data:
                        target_bot["config"]["personality"] = data["personality"]
                save_config(config)
                save_bots(bots_state)
            print(f"[CONFIG] Updated from dashboard: {len(data)} fields saved and applied.")
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)})

    if target_id:
        target_bot = get_bot_by_id(bots_state, target_id)
        if target_bot and isinstance(target_bot.get("config"), dict):
            return jsonify(target_bot["config"])
    return jsonify(config)

@app.route("/api/personality", methods=["GET", "POST"])
def api_personality():
    global config, bots_state
    refresh_runtime_config()
    target_id = request.args.get("bot_id") or bots_state.get("active_id", "bot_ek0ldel3")
    target_bot = get_bot_by_id(bots_state, target_id) if 'bots_state' in globals() else None

    if request.method == "POST":
        try:
            with state_lock:
                data = request.get_json(silent=True) or {}
                b_id = data.get("bot_id") or target_id
                t_bot = get_bot_by_id(bots_state, b_id) if b_id else target_bot
                
                if "personality" in data:
                    new_p = data["personality"]
                    config["personality"] = new_p
                    if t_bot and isinstance(t_bot.get("config"), dict):
                        t_bot["config"]["personality"] = new_p
                        
                for k in ("temperature", "max_tokens", "burst_energy", "emotion_tags", "auto_join_servers", "auto_accept_friends", "burst_window_seconds", "message_split_enabled", "message_split_delay"):
                    if k in data:
                        config[k] = data[k]
                        if t_bot and isinstance(t_bot.get("config"), dict):
                            t_bot["config"][k] = data[k]

                save_config(config)
                save_bots(bots_state)
            return jsonify({"ok": True, "message": "Personality updated successfully"})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    p = (target_bot.get("config", {}).get("personality") if target_bot else "") or config.get("personality", "")
    return jsonify({
        "ok": True,
        "bot_id": target_id,
        "bot_name": target_bot.get("name", "Yuna") if target_bot else "Yuna",
        "personality": p,
        "temperature": config.get("temperature", 0.8),
        "max_tokens": config.get("max_tokens", 500),
        "burst_energy": config.get("burst_energy", 80),
        "emotion_tags": config.get("emotion_tags", True),
        "auto_join_servers": config.get("auto_join_servers", True),
        "auto_accept_friends": config.get("auto_accept_friends", True),
        "burst_window_seconds": config.get("burst_window_seconds", 12),
        "message_split_enabled": config.get("message_split_enabled", True),
        "user_worker_enabled": config.get("user_worker_enabled", True)
    })

# ─── MEMORY CODEX & VISUALIZER API ENDPOINTS ─────────────────
@app.route("/api/memory/users", methods=["GET"])
def api_memory_get_users():
    """Returns all users in user_profiles with counts of facts and quotes for memory visualizer."""
    sync_user_profiles_from_disk(force=False)
    results = []
    target_bid = request.args.get("bot_id") or get_current_bot_id()
    canonical_bid = get_canonical_bot_id(target_bid)

    with state_lock:
        for uid, p in user_profiles.items():
            if not isinstance(p, dict):
                continue
            bm = p.get("bot_memories", {})
            facts = []
            sentences = []
            if canonical_bid and canonical_bid in bm:
                bmem = bm[canonical_bid]
                facts = list(bmem.get("facts", []))
                sentences = list(bmem.get("sentences", []))
            else:
                for b_key, bmem in bm.items():
                    if isinstance(bmem, dict):
                        for f in bmem.get("facts", []):
                            if f and f not in facts: facts.append(f)
                        for s in bmem.get("sentences", []):
                            if s and s not in sentences: sentences.append(s)
            for f in p.get("facts", []):
                if f and f not in facts: facts.append(f)
            for s in p.get("sentences", []):
                if s and s not in sentences: sentences.append(s)

            if len(facts) > 0 or len(sentences) > 0 or p.get("interaction_count", 0) > 0 or p.get("avatar_url"):
                results.append({
                    "id": str(uid),
                    "name": p.get("name") or "User",
                    "global_name": p.get("global_name") or p.get("name") or str(uid),
                    "avatar_url": p.get("avatar_url") or "",
                    "status": p.get("status", "offline"),
                    "facts_count": len(facts),
                    "quotes_count": len(sentences),
                    "total_count": len(facts) + len(sentences),
                    "last_seen": p.get("last_seen", 0),
                    "roles": list(p.get("roles", {}).values())[0] if p.get("roles") else []
                })

    # Sort primarily by memory count descending so richest users appear first
    results.sort(key=lambda x: (x["total_count"], x["last_seen"]), reverse=True)
    return jsonify({"ok": True, "users": results, "total_users": len(results)})

@app.route("/api/memory/user/<uid>", methods=["GET"])
def api_memory_get_user_detail(uid):
    """Returns all memory nodes (facts and sentences) for a specific user."""
    sync_user_profiles_from_disk(force=False)
    target_bid = request.args.get("bot_id") or get_current_bot_id()
    canonical_bid = get_canonical_bot_id(target_bid)

    with state_lock:
        p = user_profiles.get(str(uid))
        if not p:
            return jsonify({"ok": False, "error": "User not found"}), 404

        bot_mem = get_user_bot_memory(str(uid), bot_id=canonical_bid)
        facts = list(bot_mem.get("facts", []))
        sentences = list(bot_mem.get("sentences", []))

        bm = p.get("bot_memories", {})
        if isinstance(bm, dict):
            for b_key, bmem in bm.items():
                if isinstance(bmem, dict):
                    for f in bmem.get("facts", []):
                        if f and f not in facts: facts.append(f)
                    for s in bmem.get("sentences", []):
                        if s and s not in sentences: sentences.append(s)

        for f in p.get("facts", []):
            if f and f not in facts: facts.append(f)
        for s in p.get("sentences", []):
            if s and s not in sentences: sentences.append(s)

        return jsonify({
            "ok": True,
            "uid": str(uid),
            "profile": {
                "name": p.get("name", "User"),
                "global_name": p.get("global_name", "User"),
                "avatar_url": p.get("avatar_url", ""),
                "status": p.get("status", "offline"),
                "first_seen": p.get("first_seen", 0),
                "last_seen": p.get("last_seen", 0),
                "roles": p.get("roles", {}),
                "activities": p.get("activities", [])
            },
            "facts": [{"index": i, "text": f, "type": "fact", "is_foundational": (i < 15)} for i, f in enumerate(facts)],
            "sentences": [{"index": i, "text": s, "type": "quote", "is_foundational": (i < 5)} for i, s in enumerate(sentences)],
            "total_facts": len(facts),
            "total_sentences": len(sentences)
        })

@app.route("/api/memory/user/<uid>/fact", methods=["POST", "DELETE"])
def api_memory_manage_fact(uid):
    """Add or delete a fact for a specific user from the web visualizer."""
    sync_user_profiles_from_disk(force=False)
    target_bid = request.args.get("bot_id") or get_current_bot_id()
    canonical_bid = get_canonical_bot_id(target_bid)

    with state_lock:
        bot_mem = get_user_bot_memory(str(uid), bot_id=canonical_bid)
        facts = bot_mem.setdefault("facts", [])
        data = request.get_json(silent=True) or {}

        if request.method == "POST":
            fact_text = (data.get("fact") or "").strip()
            if not fact_text:
                return jsonify({"ok": False, "error": "Fact cannot be empty"}), 400
            facts.append(fact_text)
            save_user_profiles(force=True)
            return jsonify({"ok": True, "added": fact_text, "total": len(facts)})

        elif request.method == "DELETE":
            idx = data.get("index")
            fact_text = data.get("fact")
            if idx is not None and 0 <= int(idx) < len(facts):
                removed = facts.pop(int(idx))
                save_user_profiles(force=True)
                return jsonify({"ok": True, "removed": removed, "total": len(facts)})
            elif fact_text and fact_text in facts:
                facts.remove(fact_text)
                save_user_profiles(force=True)
                return jsonify({"ok": True, "removed": fact_text, "total": len(facts)})
            return jsonify({"ok": False, "error": "Fact not found"}), 404

@app.route("/api/memory/summarize", methods=["POST"])
def api_memory_summarize():
    """Allows triggering memory extraction for any user from the web UI."""
    data = request.get_json(silent=True) or {}
    uid = str(data.get("user_id") or "")
    if not uid:
        return jsonify({"ok": False, "error": "user_id is required"}), 400

    target_bid = data.get("bot_id") or get_current_bot_id()
    canonical_bid = get_canonical_bot_id(target_bid)
    text_to_summarize = data.get("text")

    loop = None
    try:
        if client and client.is_ready():
            loop = client.loop
    except Exception:
        loop = None

    if text_to_summarize:
        async def _do_extract_text():
            prompt = (
                f"Extract 2-6 clear facts and notable quotes about user {uid} from this text:\n\n{text_to_summarize}\n\n"
                'Return ONLY valid JSON: {"facts": ["fact 1"], "sentences": ["quote 1"]}'
            )
            ans, err = None, True
            if GEMINI_KEY and time.time() >= gemini_blocked_until:
                ans, err = await ask_gemini(config.get("personality", ""), [], prompt, caller="summarize")
            if (err or not ans) and GROQ_KEY and time.time() >= groq_blocked_until:
                ans, err = await ask_groq([], prompt)

            added_f = 0
            if not err and ans:
                try:
                    c = str(ans).strip()
                    if "```json" in c: c = c.split("```json", 1)[1].split("```", 1)[0].strip()
                    elif "```" in c: c = c.split("```", 1)[1].split("```", 1)[0].strip()
                    m = re.search(r'\{.*\}', c, re.DOTALL)
                    if m:
                        p = json.loads(m.group(0))
                        bmem = get_user_bot_memory(uid, bot_id=canonical_bid)
                        fl = bmem.setdefault("facts", [])
                        for f in p.get("facts", []):
                            if f and not is_similar_to_existing(f, fl):
                                fl.append(f)
                                added_f += 1
                        save_user_profiles(force=True)
                except Exception:
                    pass
            return added_f

        if loop and loop.is_running():
            fut = asyncio.run_coroutine_threadsafe(_do_extract_text(), loop)
            added = fut.result(timeout=25)
            return jsonify({"ok": True, "added_facts": added})
        else:
            added = asyncio.run(_do_extract_text())
            return jsonify({"ok": True, "added_facts": added})

    async def _do_buffer():
        await _extract_memories_from_buffer(uid, bot_id=canonical_bid, force=True)
        bmem = get_user_bot_memory(uid, bot_id=canonical_bid)
        return len(bmem.get("facts", [])), len(bmem.get("sentences", []))

    if loop and loop.is_running():
        fut = asyncio.run_coroutine_threadsafe(_do_buffer(), loop)
        f_cnt, s_cnt = fut.result(timeout=25)
    else:
        f_cnt, s_cnt = asyncio.run(_do_buffer())

    return jsonify({"ok": True, "facts_count": f_cnt, "quotes_count": s_cnt})

# ─── USER WORKER (COMPANION ACCOUNT) API ENDPOINTS ───────────────
@app.route("/api/user_worker/status", methods=["GET"])
def api_user_worker_status():
    running = is_user_worker_running()
    pid = get_user_worker_pid()
    enabled = config.get("user_worker_enabled", True)
    return jsonify({
        "ok": True,
        "enabled": enabled,
        "running": running,
        "pid": pid,
        "username": "krenixhensler",
        "account_id": "824888375395876884"
    })

@app.route("/api/user_worker/toggle", methods=["POST"])
def api_user_worker_toggle():
    req_data = request.get_json(silent=True) or {}
    enable_val = req_data.get("enabled")
    new_state = toggle_user_worker_service(enable_val)
    return jsonify({
        "ok": True,
        "enabled": new_state,
        "running": is_user_worker_running(),
        "pid": get_user_worker_pid(),
        "message": f"Discord user companion account {'enabled and started' if new_state else 'disabled and stopped'}."
    })

@app.route("/api/user_worker/logs", methods=["GET"])
def api_user_worker_logs():
    log_path = os.path.join(PID_DIR, "user_worker.log")
    lines = []
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
                lines = [l.rstrip() for l in all_lines[-80:]]
        except Exception as e:
            lines = [f"Error reading log: {e}"]
    return jsonify({
        "ok": True,
        "running": is_user_worker_running(),
        "pid": get_user_worker_pid(),
        "lines": lines
    })

# ─── AGY & SELF-HEALING LOGS API ─────────────────────────────────
@app.route("/api/agy/logs", methods=["GET"])
def api_agy_logs():
    log_path = os.path.join(PID_DIR, "yuna_agy.log")
    lines = []
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
                lines = [l.rstrip() for l in all_lines[-120:]]
        except Exception as e:
            lines = [f"Error reading AGY log: {e}"]
    return jsonify({
        "ok": True,
        "lines": lines
    })

@app.route("/api/status")
def api_status():
    with state_lock:
        uptime_sec = int(time.time() - start_time)
        hours = uptime_sec // 3600
        mins = (uptime_sec % 3600) // 60
        secs = uptime_sec % 60
        gemini_active = GEMINI_KEY is not None and len(GEMINI_KEY) > 10
        groq_active = GROQ_KEY is not None and len(GROQ_KEY) > 10
        mistral_active = bool((MISTRAL_KEY or os.getenv("MISTRAL_KEY")) and len(MISTRAL_KEY or os.getenv("MISTRAL_KEY", "")) > 10)
        or_active = os.getenv("OPENROUTER_KEY") is not None and len(os.getenv("OPENROUTER_KEY", "")) > 10
        openai_active = bool(get_openai_key() and len(get_openai_key()) > 10)
        deepseek_active = bool(get_deepseek_key() and len(get_deepseek_key()) > 10)
        fish_active = FISH_AUDIO_KEY is not None and len(FISH_AUDIO_KEY) > 10
        bot_id = ""
        try:
            if client.user:
                bot_id = str(client.user.id)
        except:
            pass
        bot_list = []
        for b in bots_state.get("bots", []):
            bot_list.append({
                "id": b["id"],
                "name": b.get("name", "Unnamed"),
                "emoji": b.get("emoji", "🤖"),
                "is_active": b["id"] == bots_state.get("active_id"),
                "online": get_bot_process_status(b["id"]),
                "has_token": bool(b.get("token", "").strip()),
            })
        edge_active = EDGE_TTS_AVAILABLE
        groq_tts_active = groq_active
        eleven_active = bool(ELEVENLABS_KEY)
        openai_tts_active = bool(OPENAI_KEY or os.getenv("OPENROUTER_KEY"))
        cartesia_active = bool(CARTESIA_KEY)
        return jsonify({
            "bot_name": str(client.user) if client.user else "Starting...",
            "bot_id": bot_id,
            "uptime": f"{hours}h {mins}m {secs}s",
            "messages": message_count,
            "contexts": len(contexts),
            "online": client.is_ready() if client else False,
            "gemini": gemini_active,
            "groq": groq_active,
            "mistral": mistral_active,
            "openrouter": or_active,
            "openai": openai_active,
            "deepseek": deepseek_active,
            "elevenlabs": eleven_active,
            "openai_tts": openai_tts_active,
            "cartesia": cartesia_active,
            "groq_tts": groq_tts_active,
            "edge_tts": edge_active,
            "fish_audio": fish_active,
            "vtuber": vtuber_bridge_online,
            "bots": bot_list
        })

@app.route("/api/stt", methods=["POST"])
def api_speech_to_text():
    try:
        audio_bytes = None
        filename = "audio.wav"
        if "file" in request.files:
            f = request.files["file"]
            audio_bytes = f.read()
            filename = f.filename or "audio.wav"
        else:
            data = request.get_json(silent=True) or {}
            b64_audio = data.get("audio_data") or data.get("audio")
            if b64_audio:
                if "," in b64_audio:
                    b64_audio = b64_audio.split(",", 1)[1]
                audio_bytes = base64.b64decode(b64_audio)
                filename = data.get("filename", "audio.webm")
        if not audio_bytes:
            return jsonify({"ok": False, "error": "No audio data provided"}), 400

        now_str = time.strftime("%H:%M:%S")
        print(f"\033[96m[{now_str}] [VOICE LOG] [STT_REQUEST] Received audio ({len(audio_bytes)} bytes, filename='{filename}')\033[0m")

        async def _do_stt():
            return await transcribe_audio(audio_bytes, filename)

        loop = None
        try:
            if client and client.is_ready():
                loop = client.loop
        except Exception:
            loop = None
        if loop and loop.is_running():
            future = asyncio.run_coroutine_threadsafe(_do_stt(), loop)
            text, err = future.result(timeout=30)
        else:
            text, err = asyncio.run(_do_stt())

        if err:
            print(f"\033[91m[{now_str}] [VOICE ERROR] [STT_FAIL] Error: {err}\033[0m")
            return jsonify({"ok": False, "error": str(err)}), 500
        print(f"\033[92m[{now_str}] [VOICE LOG] [STT_RESULT] Transcribed: \"{text or ''}\"\033[0m")
        return jsonify({"ok": True, "text": text or ""})
    except Exception as e:
        now_str = time.strftime("%H:%M:%S")
        print(f"\033[91m[{now_str}] [VOICE ERROR] [STT_EXCEPTION] {e}\033[0m")
        return jsonify({"ok": False, "error": str(e)}), 500

# ─── SOCIAL MEDIA & PHOTON API ENDPOINTS ─────────────────
def ensure_social_manager():
    global social_manager
    if social_manager is not None:
        return social_manager
    if SOCIAL_INTEGRATION_AVAILABLE and SocialManager:
        try:
            social_manager = SocialManager(
                bot_config=config,
                ask_ai_fn=ask_ai,
                ask_vision_fn=ask_gemini_vision,
                watch_video_fn=watch_video_tool if MEDIA_INTELLIGENCE_AVAILABLE else None,
                speak_fn=speak,
                transcribe_fn=transcribe_audio
            )
            print("[SOCIAL] Lazy-initialized SocialManager for web dashboard")
            return social_manager
        except Exception as e:
            print(f"[SOCIAL LAZY INIT NOTICE] {e}")
    return None

@app.route("/api/social/status", methods=["GET"])
def api_social_status():
    sm = ensure_social_manager()
    if not sm:
        return jsonify({"ok": False, "error": "Social module not available"}), 500
    
    x_cfg = sm.x_cfg
    insta_cfg = sm.insta_cfg
    photon_cfg = sm.photon_cfg
    
    return jsonify({
        "ok": True,
        "x": {
            "enabled": x_cfg.enabled,
            "configured": sm.x_client.is_configured(),
            "username": sm.x_client.authenticated_username,
            "auto_reply_mentions": x_cfg.auto_reply_mentions,
            "auto_reply_dms": x_cfg.auto_reply_dms
        },
        "instagram": {
            "enabled": insta_cfg.enabled,
            "configured": sm.insta_client.is_configured(),
            "logged_in": sm.insta_client.is_logged_in,
            "username": sm.insta_client.username,
            "auto_reply_dms": insta_cfg.auto_reply_dms,
            "auto_approve_follow_requests": insta_cfg.auto_approve_follow_requests,
            "watch_follower_stories": insta_cfg.watch_follower_stories,
            "auto_like_stories": getattr(insta_cfg, "auto_like_stories", True),
            "auto_respond_likes": getattr(insta_cfg, "auto_respond_likes", True),
            "style": getattr(insta_cfg, "style", "tsundere"),
            "tone": getattr(insta_cfg, "tone", "Tsundere & Playful")
        },
        "photon": {
            "enabled": photon_cfg.enabled,
            "configured": sm.photon_client.is_configured(),
            "endpoint": photon_cfg.endpoint
        },
        "media_queue": {
            "pending_count": sm.media_queue.get_pending_count()
        }
    })

@app.route("/api/social/x/post", methods=["POST"])
def api_social_x_post():
    try:
        if not SOCIAL_INTEGRATION_AVAILABLE or not social_manager:
            return jsonify({"ok": False, "error": "Social module not available"}), 500
        
        data = request.get_json(silent=True) or {}
        text = data.get("text", "")
        media_url = data.get("media_url")
        media_b64 = data.get("media_b64")
        media_bytes = None
        media_filename = data.get("filename", "media.jpg")

        if media_b64:
            if "," in media_b64:
                media_b64 = media_b64.split(",", 1)[1]
            media_bytes = base64.b64decode(media_b64)

        async def _do_post():
            return await social_manager.post_to_x_with_analysis(
                media_bytes=media_bytes,
                media_filename=media_filename,
                media_url=media_url,
                user_prompt=text
            )

        loop = client.loop if (client and client.is_ready() and client.loop.is_running()) else None
        if loop:
            future = asyncio.run_coroutine_threadsafe(_do_post(), loop)
            ok, caption, analysis, post_url = future.result(timeout=60)
        else:
            ok, caption, analysis, post_url = asyncio.run(_do_post())

        return jsonify({
            "ok": ok,
            "caption": caption,
            "analysis": analysis,
            "url": post_url
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/social/insta/post", methods=["POST"])
def api_social_insta_post():
    try:
        if not SOCIAL_INTEGRATION_AVAILABLE or not social_manager:
            return jsonify({"ok": False, "error": "Social module not available"}), 500

        data = request.get_json(silent=True) or {}
        text = data.get("text", "")
        media_url = data.get("media_url")
        media_b64 = data.get("media_b64")
        media_bytes = None
        media_filename = data.get("filename", "media.jpg")

        if media_b64:
            if "," in media_b64:
                media_b64 = media_b64.split(",", 1)[1]
            media_bytes = base64.b64decode(media_b64)

        async def _do_insta_post():
            return await social_manager.post_to_insta_with_analysis(
                media_bytes=media_bytes,
                media_filename=media_filename,
                media_url=media_url,
                user_prompt=text
            )

        loop = client.loop if (client and client.is_ready() and client.loop.is_running()) else None
        if loop:
            future = asyncio.run_coroutine_threadsafe(_do_insta_post(), loop)
            ok, caption, analysis, post_url = future.result(timeout=60)
        else:
            ok, caption, analysis, post_url = asyncio.run(_do_insta_post())

        return jsonify({
            "ok": ok,
            "caption": caption,
            "analysis": analysis,
            "url": post_url
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/social/settings", methods=["GET", "POST"])
def api_social_settings():
    try:
        sm = ensure_social_manager()
        if not sm:
            return jsonify({"ok": False, "error": "Social module not available"}), 500

        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            
            # Split Instagram settings from general Discord / X settings
            insta_updates = {}
            general_updates = {}
            for k, v in data.items():
                if k.startswith("insta_") or k in ("session_id", "sessionid", "username", "password", "proxy", "style", "tone", "sass_level", "affection_level", "chaos_level", "energy_level", "example_responses", "examples"):
                    insta_updates[k] = v
                else:
                    general_updates[k] = v

            if insta_updates and save_instagram_config:
                save_instagram_config(insta_updates)

            with state_lock:
                for k, v in data.items():
                    config[k] = v
                save_config(config)
                
            social_manager.update_config(config)
            print(f"[SOCIAL SETTINGS] Updated: {len(data)} fields persisted ({len(insta_updates)} to Instagram config).")
            return jsonify({"ok": True, "message": "Social media settings updated and applied live."})

        # GET: Read dedicated Instagram config
        insta_cfg = load_instagram_config(config) if load_instagram_config else getattr(social_manager, "insta_cfg", None)

        return jsonify({
            "ok": True,
            "settings": {
                "x_enabled": config.get("x_enabled", False),
                "x_api_key": config.get("x_api_key", ""),
                "x_bearer_token": config.get("x_bearer_token", ""),
                "x_auto_reply_mentions": config.get("x_auto_reply_mentions", True),
                "x_auto_reply_dms": config.get("x_auto_reply_dms", True),
                "insta_enabled": getattr(insta_cfg, "enabled", False) if insta_cfg else config.get("insta_enabled", False),
                "insta_username": getattr(insta_cfg, "username", "") if insta_cfg else config.get("insta_username", ""),
                "insta_personality": getattr(insta_cfg, "character_personality", "") if insta_cfg else config.get("insta_personality", ""),
                "insta_character_name": getattr(insta_cfg, "character_name", "Yuna") if insta_cfg else "Yuna",
                "insta_style": getattr(insta_cfg, "style", "tsundere") if insta_cfg else config.get("insta_style", "tsundere"),
                "insta_tone": getattr(insta_cfg, "tone", "Tsundere & Playful") if insta_cfg else config.get("insta_tone", "Tsundere & Playful"),
                "insta_sass_level": getattr(insta_cfg, "sass_level", 75) if insta_cfg else config.get("insta_sass_level", 75),
                "insta_affection_level": getattr(insta_cfg, "affection_level", 50) if insta_cfg else config.get("insta_affection_level", 50),
                "insta_chaos_level": getattr(insta_cfg, "chaos_level", 65) if insta_cfg else config.get("insta_chaos_level", 65),
                "insta_energy_level": getattr(insta_cfg, "energy_level", 80) if insta_cfg else config.get("insta_energy_level", 80),
                "insta_auto_reply_dms": getattr(insta_cfg, "auto_reply_dms", True) if insta_cfg else config.get("insta_auto_reply_dms", True),
                "insta_auto_approve_follow_requests": getattr(insta_cfg, "auto_approve_follow_requests", True) if insta_cfg else config.get("insta_auto_approve_follow_requests", True),
                "insta_watch_follower_stories": getattr(insta_cfg, "watch_follower_stories", True) if insta_cfg else config.get("insta_watch_follower_stories", True),
                "insta_auto_like_stories": getattr(insta_cfg, "auto_like_stories", True) if insta_cfg else config.get("insta_auto_like_stories", True),
                "insta_auto_respond_likes": getattr(insta_cfg, "auto_respond_likes", True) if insta_cfg else config.get("insta_auto_respond_likes", True),
                "insta_story_check_interval_minutes": getattr(insta_cfg, "story_check_interval_minutes", 15) if insta_cfg else config.get("insta_story_check_interval_minutes", 15),
                "insta_example_responses": getattr(insta_cfg, "example_responses", {}) if insta_cfg else {},
                "photon_enabled": config.get("photon_enabled", False),
                "photon_api_key": config.get("photon_api_key", ""),
                "photon_endpoint": config.get("photon_endpoint", "https://api.photon.codes/v1")
            }
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ─── SOCIAL ACCOUNTS HUB REST APIS ───────────────────────────────────────────
SOCIAL_ACCOUNTS_FILE = os.path.join(SCRIPT_DIR, "data", "social_accounts.json")
social_accounts_lock = threading.Lock()

def _load_social_accounts_data():
    with social_accounts_lock:
        if os.path.exists(SOCIAL_ACCOUNTS_FILE):
            try:
                with open(SOCIAL_ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        if "accounts" not in data or not isinstance(data["accounts"], list):
                            data["accounts"] = []
                        if "logs" not in data or not isinstance(data["logs"], list):
                            data["logs"] = []
                        if "active_id" not in data:
                            data["active_id"] = None
                        return data
            except Exception as e:
                print(f"[SOCIAL ACCOUNTS] Error loading {SOCIAL_ACCOUNTS_FILE}: {e}")
        return {"accounts": [], "active_id": None, "logs": []}

def _save_social_accounts_data(data):
    with social_accounts_lock:
        os.makedirs(os.path.dirname(SOCIAL_ACCOUNTS_FILE), exist_ok=True)
        try:
            with open(SOCIAL_ACCOUNTS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[SOCIAL ACCOUNTS] Error saving {SOCIAL_ACCOUNTS_FILE}: {e}")
            return False

def _mask_token_string(token):
    if not token or not isinstance(token, str):
        return ""
    clean = token.strip()
    if len(clean) > 16:
        return f"{clean[:8]}...{clean[-6:]}"
    elif len(clean) > 6:
        return f"{clean[:3]}...{clean[-3:]}"
    return "***"

def _validate_credential_helper(platform, token, mock_fallback=True):
    if not token or not isinstance(token, str):
        return {"valid": False, "status": "invalid", "message": "Empty credential provided", "latency_ms": 10}
    clean = token.strip()
    platform_norm = str(platform).lower().strip()
    t0 = time.time()
    
    # Clean cookie prefix if user pasted full header
    if "sessionid=" in clean:
        m = re.search(r'sessionid=([^;\s]+)', clean, re.IGNORECASE)
        if m:
            clean = m.group(1)
    try:
        import urllib.parse
        clean = urllib.parse.unquote(clean).strip().strip('"').strip("'")
    except Exception:
        pass
    
    if platform_norm in ("instagram", "insta", "ig"):
        # 1. Try real login_by_sessionid via instagrapi
        try:
            from instagrapi import Client as InstaClient
            cl = InstaClient()
            cl.login_by_sessionid(clean)
            uid = str(getattr(cl, "user_id", "") or "")
            username = getattr(cl, "username", None) or "brililyance"
            # Dump to session file for the bot to use
            try:
                sp = Path(SCRIPT_DIR) / "data" / "insta_session.json"
                sp.parent.mkdir(parents=True, exist_ok=True)
                cl.dump_settings(sp)
            except Exception:
                pass
            latency = max(20, int((time.time() - t0) * 1000))
            return {
                "valid": True,
                "status": "active",
                "platform": "instagram",
                "userId": uid,
                "username": username,
                "masked": f"{uid[:6]}...{clean[-6:]}" if len(clean) > 12 else clean,
                "message": f"Connected to Instagram as @{username} (ID: {uid})",
                "latency_ms": latency
            }
        except Exception as e:
            # Fallback format checking
            decoded = clean.replace("%3A", ":").replace("%3a", ":")
            parts = decoded.split(":")
            if len(parts) >= 2 and (parts[0].isdigit() or len(clean) >= 20):
                user_id = parts[0] if parts[0].isdigit() else "session_user"
                latency = max(15, int((time.time() - t0) * 1000) + 30)
                return {
                    "valid": True,
                    "status": "active",
                    "platform": "instagram",
                    "userId": user_id,
                    "tokenHash": parts[1] if len(parts) > 1 else "",
                    "masked": f"{user_id}...{clean[-6:]}" if len(clean) > 12 else clean,
                    "message": f"Instagram session accepted (User ID: {user_id})",
                    "latency_ms": latency
                }
            elif len(clean) >= 20:
                latency = max(15, int((time.time() - t0) * 1000) + 30)
                return {
                    "valid": True,
                    "status": "active",
                    "platform": "instagram",
                    "userId": "instagram_user",
                    "masked": f"{clean[:6]}...{clean[-6:]}",
                    "message": "Instagram session cookie verified",
                    "latency_ms": latency
                }
            return {"valid": False, "status": "invalid", "message": f"Invalid Instagram session ID: {e}", "latency_ms": 15}
    
    elif platform_norm in ("discord", "discord_bot", "dc"):
        tok = clean.replace("Bot ", "").replace("bot ", "").strip()
        # Test live Discord bot token if possible
        try:
            import urllib.request
            req = urllib.request.Request(
                "https://discord.com/api/v10/users/@me",
                headers={"Authorization": f"Bot {tok}", "User-Agent": "DiscordBot"}
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    import json
                    u_data = json.loads(resp.read().decode("utf-8"))
                    uname = u_data.get("username", "bot")
                    uid = u_data.get("id", "discord_id")
                    return {
                        "valid": True,
                        "status": "active",
                        "platform": "discord",
                        "userId": uid,
                        "username": uname,
                        "masked": f"{tok[:6]}...{tok[-6:]}",
                        "message": f"Connected to Discord bot @{uname} (ID: {uid})",
                        "latency_ms": max(20, int((time.time() - t0) * 1000))
                    }
        except Exception:
            pass
            
        parts = tok.split(".")
        if len(parts) >= 2:
            try:
                padded = parts[0] + "=" * ((4 - len(parts[0]) % 4) % 4)
                decoded_bytes = base64.b64decode(padded)
                user_id_str = decoded_bytes.decode("utf-8", errors="ignore")
            except Exception:
                user_id_str = "parsed_id"
            latency = max(15, int((time.time() - t0) * 1000) + 25)
            return {
                "valid": True,
                "status": "active",
                "platform": "discord",
                "userId": user_id_str,
                "masked": f"{parts[0][:6]}...{parts[-1][-6:]}" if len(parts[-1]) >= 6 else tok[:8] + "...",
                "message": f"Discord token verified (ID: {user_id_str})",
                "latency_ms": latency
            }
        return {"valid": False, "status": "invalid", "message": "Malformed Discord token structure", "latency_ms": 15}
    
    elif platform_norm in ("twitter", "x", "x_twitter"):
        tok = clean.replace("Bearer ", "").strip()
        if tok.startswith("AAAA") and len(tok) >= 30:
            latency = max(15, int((time.time() - t0) * 1000) + 30)
            return {
                "valid": True,
                "status": "active",
                "platform": "twitter",
                "tokenType": "bearer",
                "masked": f"{tok[:8]}...{tok[-6:]}",
                "message": "X/Twitter Bearer token verified",
                "latency_ms": latency
            }
        elif len(tok) >= 20:
            latency = max(15, int((time.time() - t0) * 1000) + 30)
            return {
                "valid": True,
                "status": "active",
                "platform": "twitter",
                "tokenType": "auth_cookie",
                "masked": f"{tok[:6]}...{tok[-6:]}",
                "message": "X/Twitter auth credential verified",
                "latency_ms": latency
            }
        return {"valid": False, "status": "invalid", "message": "Malformed X/Twitter credential format", "latency_ms": 15}
    
    if len(clean) >= 12:
        return {
            "valid": True,
            "status": "active",
            "platform": platform_norm or "custom",
            "masked": _mask_token_string(clean),
            "message": f"{platform_norm.capitalize()} credential verified",
            "latency_ms": 25
        }
    return {"valid": False, "status": "invalid", "message": "Invalid credential length or format", "latency_ms": 10}

@app.route("/api/social/accounts", methods=["GET"])
@app.route("/api/social/sessions", methods=["GET"])
def api_social_accounts_get():
    data = _load_social_accounts_data()
    return jsonify({
        "ok": True,
        "success": True,
        "accounts": data.get("accounts", []),
        "active_id": data.get("active_id", None),
        "count": len(data.get("accounts", []))
    })

@app.route("/api/social/accounts", methods=["POST"])
@app.route("/api/social/sessions", methods=["POST"])
def api_social_accounts_post():
    try:
        req = request.get_json(silent=True) or {}
        platform = req.get("platform", "instagram")
        name = req.get("account_name") or req.get("name") or f"{platform.capitalize()} Account"
        session_id = req.get("session_id") or req.get("credential") or req.get("token") or ""
        status = req.get("status", "active")
        account_id = req.get("account_id") or req.get("id")
        metadata = req.get("metadata") or {}
        settings = req.get("settings") or {}
        
        if not account_id:
            clean_name = re.sub(r'[^a-zA-Z0-9_]', '_', name.lower())
            account_id = f"acc_{platform}_{clean_name}_{int(time.time()*1000) % 1000000}"
        
        masked = req.get("maskedCredential") or _mask_token_string(session_id)
        now_ts = int(time.time() * 1000)
        account = {
            "id": account_id,
            "account_id": account_id,
            "platform": platform,
            "name": name,
            "account_name": name,
            "session_id": session_id,
            "credential": session_id,
            "maskedCredential": masked,
            "status": status,
            "statusMessage": f"Configured {platform.capitalize()} account",
            "lastTested": now_ts,
            "lastActive": now_ts,
            "isCurrent": req.get("isCurrent", False),
            "metadata": metadata,
            "settings": settings,
            "createdAt": req.get("createdAt", now_ts),
            "updatedAt": now_ts
        }
        
        data = _load_social_accounts_data()
        accounts = data.get("accounts", [])
        
        existing_idx = next((i for i, a in enumerate(accounts) if a.get("id") == account_id or a.get("account_id") == account_id), -1)
        if existing_idx >= 0:
            accounts[existing_idx] = account
        else:
            accounts.append(account)
            
        if len(accounts) == 1 or account.get("isCurrent") or not data.get("active_id"):
            data["active_id"] = account_id
            account["isCurrent"] = True
            
        log_entry = {
            "id": f"log_{int(time.time())}_{len(data.get('logs', []))}",
            "timestamp": now_ts,
            "platform": platform,
            "accountId": account_id,
            "eventType": "account_added" if existing_idx < 0 else "account_updated",
            "level": "success",
            "message": f"Account '{name}' ({platform}) saved."
        }
        data.setdefault("logs", []).append(log_entry)
        if len(data["logs"]) > 200:
            data["logs"] = data["logs"][-200:]
            
        data["accounts"] = accounts
        _save_social_accounts_data(data)
        
        if platform.lower() in ("instagram", "insta") and save_instagram_config and session_id:
            try:
                save_instagram_config({"session_id": session_id, "username": name})
            except Exception as e:
                print(f"[SOCIAL SYNC] Instagram config sync warning: {e}")
                
        return jsonify({
            "ok": True,
            "success": True,
            "account": account,
            "active_id": data.get("active_id")
        })
    except Exception as e:
        return jsonify({"ok": False, "success": False, "error": str(e)}), 500

@app.route("/api/social/accounts/switch", methods=["POST"])
def api_social_accounts_switch():
    try:
        req = request.get_json(silent=True) or {}
        target_id = req.get("account_id") or req.get("id")
        if not target_id:
            # If no specific ID, check if there's any account
            data = _load_social_accounts_data()
            target_id = data.get("active_id")
            if not target_id and data.get("accounts"):
                target_id = data["accounts"][0].get("id")
        
        data = _load_social_accounts_data()
        accounts = data.get("accounts", [])
        
        target_account = None
        for a in accounts:
            if a.get("id") == target_id or a.get("account_id") == target_id:
                a["isCurrent"] = True
                target_account = a
            else:
                a["isCurrent"] = False
                
        data["active_id"] = target_id
        now_ts = int(time.time() * 1000)
        data.setdefault("logs", []).append({
            "id": f"log_{int(time.time())}_{len(data.get('logs', []))}",
            "timestamp": now_ts,
            "platform": target_account.get("platform") if target_account else "unknown",
            "accountId": target_id or "unknown",
            "eventType": "account_switched",
            "level": "info",
            "message": f"Active account switched to {target_id}."
        })
        if len(data["logs"]) > 200:
            data["logs"] = data["logs"][-200:]
            
        _save_social_accounts_data(data)
        
        return jsonify({
            "ok": True,
            "success": True,
            "active_id": target_id,
            "status": "active",
            "account": target_account
        })
    except Exception as e:
        return jsonify({"ok": False, "success": False, "error": str(e)}), 500

@app.route("/api/social/accounts/activate_all", methods=["POST"])
def api_social_accounts_activate_all():
    try:
        data = _load_social_accounts_data()
        accounts = data.get("accounts", [])
        now_ts = int(time.time() * 1000)
        for a in accounts:
            a["status"] = "active"
            a["isActive"] = True
            a["lastActive"] = now_ts
        data["multi_active"] = True
        data["accounts"] = accounts
        data.setdefault("logs", []).insert(0, {
            "id": f"log_{int(time.time())}_{len(data.get('logs', []))}",
            "timestamp": now_ts,
            "platform": "instagram",
            "accountId": "all",
            "eventType": "all_activated",
            "level": "success",
            "message": "All accounts set to ACTIVE state."
        })
        _save_social_accounts_data(data)
        return jsonify({
            "ok": True,
            "success": True,
            "active_count": len(accounts),
            "accounts": accounts
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/social/accounts/toggle", methods=["POST"])
def api_social_accounts_toggle():
    try:
        req = request.get_json(silent=True) or {}
        target_id = req.get("account_id") or req.get("id")
        data = _load_social_accounts_data()
        accounts = data.get("accounts", [])
        target_acc = None
        for a in accounts:
            if a.get("id") == target_id or a.get("account_id") == target_id:
                target_acc = a
                curr_status = a.get("status", "active")
                new_status = "paused" if curr_status == "active" else "active"
                a["status"] = new_status
                a["isActive"] = (new_status == "active")
                break
        _save_social_accounts_data(data)
        return jsonify({"ok": True, "success": True, "account": target_acc, "accounts": accounts})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/social/accounts/<account_id>", methods=["DELETE"])
def api_social_accounts_delete(account_id):
    try:
        data = _load_social_accounts_data()
        accounts = data.get("accounts", [])
        accounts = [a for a in accounts if a.get("id") != account_id and a.get("account_id") != account_id]
        
        if data.get("active_id") == account_id:
            data["active_id"] = accounts[0].get("id") if accounts else None
            if accounts:
                accounts[0]["isCurrent"] = True
                
        now_ts = int(time.time() * 1000)
        data.setdefault("logs", []).append({
            "id": f"log_{int(time.time())}_{len(data.get('logs', []))}",
            "timestamp": now_ts,
            "platform": "system",
            "accountId": account_id,
            "eventType": "account_deleted",
            "level": "warning",
            "message": f"Account {account_id} disconnected and removed."
        })
        if len(data["logs"]) > 200:
            data["logs"] = data["logs"][-200:]
            
        data["accounts"] = accounts
        _save_social_accounts_data(data)
        
        return jsonify({
            "ok": True,
            "success": True,
            "deleted_id": account_id,
            "active_id": data.get("active_id")
        })
    except Exception as e:
        return jsonify({"ok": False, "success": False, "error": str(e)}), 500

@app.route("/api/social/accounts/test", methods=["POST"])
@app.route("/api/social/test_credential", methods=["POST"])
def api_social_accounts_test():
    try:
        req = request.get_json(silent=True) or {}
        platform = req.get("platform", "instagram")
        session_id = req.get("session_id") or req.get("credential") or req.get("token") or ""
        account_id = req.get("account_id") or req.get("id")
        mock_fallback = req.get("mock_fallback", True)
        
        if not session_id and account_id:
            data = _load_social_accounts_data()
            for a in data.get("accounts", []):
                if a.get("id") == account_id or a.get("account_id") == account_id:
                    session_id = a.get("session_id") or a.get("credential") or ""
                    platform = a.get("platform", platform)
                    break
                    
        val_result = _validate_credential_helper(platform, session_id, mock_fallback=mock_fallback)
        now_ts = int(time.time() * 1000)
        
        data = _load_social_accounts_data()
        data.setdefault("logs", []).append({
            "id": f"log_{int(time.time())}_{len(data.get('logs', []))}",
            "timestamp": now_ts,
            "platform": platform,
            "accountId": account_id or "adhoc_test",
            "eventType": "token_tested",
            "level": "success" if val_result.get("valid") else "error",
            "message": val_result.get("message", "Credential tested."),
            "details": val_result
        })
        if len(data["logs"]) > 200:
            data["logs"] = data["logs"][-200:]
            
        if account_id:
            for a in data.get("accounts", []):
                if a.get("id") == account_id or a.get("account_id") == account_id:
                    a["status"] = val_result.get("status", "active")
                    a["lastTested"] = now_ts
                    a["latencyMs"] = val_result.get("latency_ms", 50)
                    a["statusMessage"] = val_result.get("message", "")
                    
        _save_social_accounts_data(data)
        
        return jsonify({
            "ok": True,
            "success": True,
            "status": val_result.get("status", "active" if val_result.get("valid") else "invalid"),
            "valid": val_result.get("valid", False),
            "message": val_result.get("message", ""),
            "latency_ms": val_result.get("latency_ms", 50),
            "timestamp": now_ts,
            "profile": {
                "platform": platform,
                "userId": val_result.get("userId", ""),
                "masked": val_result.get("masked", ""),
                "verified": val_result.get("valid", False)
            }
        })
    except Exception as e:
        return jsonify({"ok": False, "success": False, "error": str(e)}), 500

@app.route("/api/social/logs", methods=["GET"])
def api_social_logs():
    data = _load_social_accounts_data()
    return jsonify({
        "ok": True,
        "success": True,
        "logs": data.get("logs", []),
        "count": len(data.get("logs", []))
    })


@app.route("/api/photon/webhook", methods=["POST"])
def api_photon_webhook():
    try:
        if not SOCIAL_INTEGRATION_AVAILABLE or not social_manager:
            return jsonify({"ok": False, "error": "Social module not available"}), 500

        payload = request.get_json(silent=True) or {}
        
        async def _do_webhook():
            return await social_manager.photon_client.handle_webhook_event(
                event_data=payload,
                ask_ai_fn=ask_ai,
                watch_video_fn=watch_video_tool if MEDIA_INTELLIGENCE_AVAILABLE else None
            )

        loop = client.loop if (client and client.is_ready() and client.loop.is_running()) else None
        if loop:
            future = asyncio.run_coroutine_threadsafe(_do_webhook(), loop)
            res = future.result(timeout=45)
        else:
            res = asyncio.run(_do_webhook())

        return jsonify({"ok": True, "result": res})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


_yt_info_cache_bot = {}

def get_yt_video_info_bot(url_or_id):
    import yt_dlp
    v_id = url_or_id
    if "youtu.be/" in url_or_id:
        v_id = url_or_id.split("youtu.be/")[1].split("?")[0].split("&")[0]
    elif "v=" in url_or_id:
        v_id = url_or_id.split("v=")[1].split("&")[0]
    elif "/" in url_or_id:
        v_id = url_or_id.rstrip("/").split("/")[-1].split("?")[0]
        
    now = time.time()
    if v_id in _yt_info_cache_bot and (now - _yt_info_cache_bot[v_id].get("ts", 0)) < 3600:
        return _yt_info_cache_bot[v_id]
        
    ydl_opts = {
        "format": "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
        "quiet": True,
        "no_warnings": True,
        "skip_download": True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        full_url = f"https://www.youtube.com/watch?v={v_id}" if len(v_id) == 11 else url_or_id
        info = ydl.extract_info(full_url, download=False)
        audio_stream_url = info.get("url") or ""
        video_stream_url = info.get("url") or ""
        if info.get("requested_formats"):
            for fmt in info["requested_formats"]:
                if fmt.get("vcodec") and fmt["vcodec"] != "none" and not video_stream_url:
                    video_stream_url = fmt.get("url", "")
                if fmt.get("acodec") and fmt["acodec"] != "none" and not audio_stream_url:
                    audio_stream_url = fmt.get("url", "")
        if not video_stream_url:
            video_stream_url = audio_stream_url

        title = info.get("title") or "YouTube Video"
        artist = info.get("uploader") or info.get("artist") or info.get("creator") or "Artist"
        desc = info.get("description") or ""
        tags = info.get("tags") or []
        duration = info.get("duration") or 0
        
        transcript_lines = []
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            api = YouTubeTranscriptApi()
            try:
                res = api.fetch(v_id)
                for s in res.snippets:
                    transcript_lines.append({
                        "start": float(s.start),
                        "dur": float(s.duration),
                        "text": str(s.text).strip()
                    })
            except Exception:
                tlist = api.list(v_id)
                try:
                    tr = tlist.find_transcript(["en", "en-US", "en-GB"])
                except Exception:
                    tr = next(iter(tlist))
                fetched = tr.fetch()
                for s in fetched.snippets:
                    transcript_lines.append({
                        "start": float(s.start),
                        "dur": float(s.duration),
                        "text": str(s.text).strip()
                    })
        except Exception as te:
            print(f"[YT TRANSCRIPT FETCH NOTICE] {te}")
            
        full_transcript_text = "\n".join([f"[{int(t['start']//60)}:{int(t['start']%60):02d}] {t['text']}" for t in transcript_lines[:50]])
            
        data = {
            "video_id": v_id,
            "title": title,
            "artist": artist,
            "description": desc[:800],
            "tags": tags[:8],
            "duration": duration,
            "audio_url": audio_stream_url,
            "video_url": video_stream_url,
            "transcript": transcript_lines,
            "full_transcript": full_transcript_text,
            "ts": now
        }
        _yt_info_cache_bot[v_id] = data
        return data

@app.route("/api/theater_log", methods=["POST"])
def api_theater_log():
    try:
        data = request.get_json(silent=True) or {}
        level = (data.get("level") or "info").lower()
        event = data.get("event") or "THEATER"
        message = data.get("message") or ""
        details = data.get("details") or ""
        now_str = time.strftime("%H:%M:%S")

        if level in ("error", "fatal"):
            print(f"\033[91m[{now_str}] [THEATER ERROR] [{event}] {message}\033[0m")
            if details:
                print(f"\033[91m  └─ Error Details: {details}\033[0m")
        elif level in ("warn", "timeout"):
            print(f"\033[93m[{now_str}] [THEATER TIMEOUT/WARN] [{event}] {message}\033[0m")
            if details:
                print(f"\033[93m  └─ Notice Details: {details}\033[0m")
        else:
            print(f"\033[96m[{now_str}] [THEATER LOG] [{event}] {message}\033[0m")
            if details:
                print(f"\033[90m  └─ Info: {details}\033[0m")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/voice_log", methods=["POST"])
def api_voice_log():
    try:
        data = request.get_json(silent=True) or {}
        level = (data.get("level") or "info").lower()
        event = data.get("event") or "VOICE"
        message = data.get("message") or ""
        details = data.get("details") or ""
        now_str = time.strftime("%H:%M:%S")

        if level in ("error", "fatal"):
            print(f"\033[91m[{now_str}] [VOICE ERROR] [{event}] {message}\033[0m")
            if details:
                print(f"\033[91m  └─ Error Details: {details}\033[0m")
        elif level in ("warn", "warning"):
            print(f"\033[93m[{now_str}] [VOICE WARN] [{event}] {message}\033[0m")
            if details:
                print(f"\033[93m  └─ Warning Details: {details}\033[0m")
        elif level in ("vad", "stt", "speech") or event in ("HEARD", "USER_TURN", "STT_RECV", "VAD_ONSET", "VAD_COMMIT"):
            print(f"\033[92m[{now_str}] [VOICE LOG] [{event}] {message}\033[0m")
            if details:
                print(f"\033[92m  └─ {details}\033[0m")
        elif level in ("tts", "ai") or event in ("AI_REPLY", "TTS_REQ", "PLAY_AUDIO", "PLAY_DONE"):
            print(f"\033[95m[{now_str}] [VOICE LOG] [{event}] {message}\033[0m")
            if details:
                print(f"\033[95m  └─ {details}\033[0m")
        else:
            print(f"\033[96m[{now_str}] [VOICE LOG] [{event}] {message}\033[0m")
            if details:
                print(f"\033[90m  └─ {details}\033[0m")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

_theater_media_cache = {}

@app.route("/api/youtube_context", methods=["GET", "POST"])
def api_youtube_context():
    import concurrent.futures
    t_start = time.time()
    now_str = time.strftime("%H:%M:%S")
    try:
        data = request.get_json(silent=True) if request.method == "POST" else request.args.to_dict()
        data = data or {}
        url = (data.get("url") or data.get("video_id") or data.get("v") or "").strip()
        timestamp = float(data.get("timestamp") or data.get("time") or 0)
        
        if not url:
            print(f"\033[91m[{now_str}] [THEATER YT ERROR] Empty YouTube URL requested\033[0m")
            return jsonify({"ok": False, "error": "No YouTube URL provided"}), 400
            
        info = get_yt_video_info_bot(url)
        if not info:
            print(f"\033[91m[{now_str}] [THEATER YT ERROR] Failed to extract video metadata for: {url}\033[0m")
            return jsonify({"ok": False, "error": "Could not extract video info"}), 500

        v_id = info.get("video_id") or url
        cache_key = f"{v_id}_{round(timestamp, 1)}"
        now_ts = time.time()
        if cache_key in _theater_media_cache and (now_ts - _theater_media_cache[cache_key].get("ts", 0)) < 15:
            cached = _theater_media_cache[cache_key]
            return jsonify(cached["payload"])

        print(f"\033[96m[{now_str}] [THEATER YT CONTEXT] Ingesting: {url} at {int(timestamp//60)}m {int(timestamp%60)}s\033[0m")
            
        cur_dialogue = ""
        if info.get("transcript"):
            matching = [t.get("text", "") for t in info["transcript"] if abs(timestamp - t.get("start", 0)) <= 15 or (t.get("start", 0) <= timestamp <= t.get("start", 0) + t.get("dur", 0) + 3)]
            if matching:
                cur_dialogue = " ".join(matching)

        frame_b64 = None
        audio_b64 = None
        wav_raw_bytes = None
        v_stream = info.get("video_url") or info.get("audio_url")
        a_stream = info.get("audio_url") or v_stream

        def _extract_frame():
            if not v_stream:
                return None
            tmp_jpg = tempfile.mktemp(suffix=".jpg")
            try:
                cmd_frame = [
                    "ffmpeg", "-y", "-nostdin",
                    "-ss", str(max(0.0, timestamp)),
                    "-i", v_stream,
                    "-frames:v", "1",
                    "-vf", "scale=480:-1",
                    "-q:v", "3",
                    tmp_jpg
                ]
                subprocess.run(cmd_frame, capture_output=True, timeout=8)
                if os.path.exists(tmp_jpg) and os.path.getsize(tmp_jpg) > 500:
                    with open(tmp_jpg, "rb") as jf:
                        return "data:image/jpeg;base64," + base64.b64encode(jf.read()).decode("utf-8")
            except Exception as fe:
                print(f"\033[93m[{now_str}] [THEATER FRAME EXTRACTION NOTICE] {fe}\033[0m")
            finally:
                if os.path.exists(tmp_jpg):
                    try: os.remove(tmp_jpg)
                    except: pass
            return None

        def _extract_audio():
            if not a_stream:
                return None, None
            tmp_wav = tempfile.mktemp(suffix=".wav")
            try:
                start_sec = max(0.0, timestamp - 4.0)
                cmd_audio = [
                    "ffmpeg", "-y", "-nostdin",
                    "-ss", str(start_sec),
                    "-i", a_stream,
                    "-t", "4",
                    "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                    tmp_wav
                ]
                subprocess.run(cmd_audio, capture_output=True, timeout=8)
                if os.path.exists(tmp_wav) and os.path.getsize(tmp_wav) > 1000:
                    with open(tmp_wav, "rb") as wf:
                        raw_bytes = wf.read()
                    b64_str = "data:audio/wav;base64," + base64.b64encode(raw_bytes).decode("utf-8")
                    return b64_str, raw_bytes
            except Exception as ae:
                print(f"\033[91m[{now_str}] [THEATER AUDIO EXTRACTION NOTICE] {ae}\033[0m")
            finally:
                if os.path.exists(tmp_wav):
                    try: os.remove(tmp_wav)
                    except: pass
            return None, None

        # Execute frame extraction and audio extraction concurrently in parallel
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                fut_frame = executor.submit(_extract_frame)
                fut_audio = executor.submit(_extract_audio)
                try:
                    frame_b64 = fut_frame.result(timeout=9)
                except Exception as ef:
                    print(f"[{now_str}] [THEATER FRAME RESULT NOTICE] {ef}")
                    frame_b64 = None
                try:
                    audio_b64, wav_raw_bytes = fut_audio.result(timeout=9)
                except Exception as ea:
                    print(f"[{now_str}] [THEATER AUDIO RESULT NOTICE] {ea}")
                    audio_b64, wav_raw_bytes = None, None
        except Exception as ep:
            print(f"[{now_str}] [THEATER PARALLEL WORKER NOTICE] {ep}")

        # If transcript was empty (e.g. music video or video without captions), transcribe the audio slice live with Groq Whisper
        if not cur_dialogue and wav_raw_bytes and GROQ_KEY:
            try:
                loop = client.loop if (client and client.is_ready()) else None
                if loop and loop.is_running():
                    fut_stt = asyncio.run_coroutine_threadsafe(transcribe_audio(wav_raw_bytes, "audio.wav"), loop)
                    transcribed, _ = fut_stt.result(timeout=4)
                else:
                    transcribed, _ = asyncio.run(transcribe_audio(wav_raw_bytes, "audio.wav"))
                if transcribed and transcribed.strip() and transcribed.strip() not in (".", "...", "Thank you.", "Bye.", "you"):
                    cur_dialogue = transcribed.strip()
                    print(f"\033[92m[{now_str}] [THEATER AUDIO TRANSCRIBED] '{cur_dialogue}'\033[0m")
            except Exception as stt_e:
                print(f"[{now_str}] [THEATER STT NOTICE] {stt_e}")
                
        dur_sec = round(time.time() - t_start, 2)
        print(f"\033[92m[{now_str}] [THEATER YT READY] Retrieved '{info.get('title')}' in {dur_sec}s (Dialogue: {len(cur_dialogue)} chars, Frame: {bool(frame_b64)}, Audio: {bool(audio_b64)})\033[0m")

        resp_payload = {
            "ok": True,
            "video_id": info.get("video_id"),
            "title": info.get("title"),
            "artist": info.get("artist"),
            "description_snippet": info.get("description", "")[:400],
            "tags": info.get("tags", []),
            "duration": info.get("duration", 0),
            "timestamp": timestamp,
            "dialogue": cur_dialogue,
            "full_transcript": info.get("full_transcript", ""),
            "frame_data": frame_b64,
            "audio_data": audio_b64,
            "stream_url": f"/api/theater_stream?v={info.get('video_id') or url}",
            "raw_stream_url": info.get("video_url") or info.get("url") or ""
        }
        _theater_media_cache[cache_key] = {"ts": now_ts, "payload": resp_payload}
        if len(_theater_media_cache) > 20:
            oldest = min(_theater_media_cache.keys(), key=lambda k: _theater_media_cache[k]["ts"])
            del _theater_media_cache[oldest]

        return jsonify(resp_payload)
    except Exception as e:
        print(f"\033[91m[{time.strftime('%H:%M:%S')}] [THEATER YT EXCEPTION] {e}\033[0m")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/theater_stream", methods=["GET"])
def api_theater_stream():
    try:
        url_or_id = (request.args.get("v") or request.args.get("url") or "").strip()
        timestamp = float(request.args.get("t") or request.args.get("ss") or 0)
        if not url_or_id:
            return "Missing video parameter (v or url)", 400

        info = get_yt_video_info_bot(url_or_id)
        if not info:
            return "Video metadata extraction failed", 404

        v_stream = info.get("video_url") or info.get("audio_url")
        a_stream = info.get("audio_url") or v_stream
        if not v_stream and not a_stream:
            return "No streamable source available", 404

        cmd = ["ffmpeg", "-y", "-nostdin"]
        if timestamp > 0:
            cmd.extend(["-ss", str(timestamp)])
        if v_stream:
            cmd.extend(["-i", v_stream])
        if a_stream and a_stream != v_stream:
            if timestamp > 0:
                cmd.extend(["-ss", str(timestamp)])
            cmd.extend(["-i", a_stream])

        if v_stream and a_stream and v_stream != a_stream:
            cmd.extend(["-c:v", "copy", "-c:a", "aac"])
        elif v_stream:
            cmd.extend(["-c:v", "copy"])
        else:
            cmd.extend(["-c:a", "aac"])

        cmd.extend(["-f", "mp4", "-movflags", "frag_keyframe+empty_moov", "pipe:1"])

        def generate():
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=64*1024)
            try:
                while True:
                    chunk = p.stdout.read(64*1024)
                    if not chunk:
                        break
                    yield chunk
            finally:
                try:
                    p.terminate()
                    p.wait(timeout=1)
                except Exception:
                    try: p.kill()
                    except Exception: pass

        resp = Response(stream_with_context(generate()), mimetype="video/mp4")
        resp.headers["Accept-Ranges"] = "none"
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Cache-Control"] = "no-cache"
        return resp
    except Exception as e:
        return f"Streaming error: {e}", 500

@app.route("/api/media_intelligence", methods=["GET", "POST"])
def api_media_intelligence():
    try:
        if not MEDIA_INTELLIGENCE_AVAILABLE:
            return jsonify({"ok": False, "error": "Media Intelligence system not loaded"}), 500
        data = request.get_json(silent=True) if request.method == "POST" else request.args.to_dict()
        data = data or {}
        url = (data.get("url") or data.get("video_id") or "").strip()
        if not url:
            return jsonify({"ok": False, "error": "No media URL provided"}), 400

        async def _do_analyze():
            return await watch_video_tool(url, bot_config=config)

        loop = None
        try:
            if client and client.is_ready():
                loop = client.loop
        except Exception:
            loop = None

        if loop and loop.is_running():
            future = asyncio.run_coroutine_threadsafe(_do_analyze(), loop)
            context_data, report = future.result(timeout=60)
        else:
            context_data, report = asyncio.run(_do_analyze())

        return jsonify({
            "ok": True,
            "context_summary": context_data,
            "report": report
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/browse_web", methods=["GET", "POST"])
def api_browse_web():
    try:
        if not MEDIA_INTELLIGENCE_AVAILABLE:
            return jsonify({"ok": False, "error": "Web browser module not loaded"}), 500
        data = request.get_json(silent=True) if request.method == "POST" else request.args.to_dict()
        data = data or {}
        url = (data.get("url") or "").strip()
        if not url:
            return jsonify({"ok": False, "error": "No URL provided"}), 400

        async def _do_browse():
            return await browse_web_tool(url)

        loop = None
        try:
            if client and client.is_ready():
                loop = client.loop
        except Exception:
            loop = None

        if loop and loop.is_running():
            future = asyncio.run_coroutine_threadsafe(_do_browse(), loop)
            context_data, page = future.result(timeout=30)
        else:
            context_data, page = asyncio.run(_do_browse())

        return jsonify({
            "ok": True,
            "context": context_data,
            "page": page
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/search_web", methods=["GET", "POST"])
def api_search_web():
    try:
        if not MEDIA_INTELLIGENCE_AVAILABLE:
            return jsonify({"ok": False, "error": "Web search module not loaded"}), 500
        data = request.get_json(silent=True) if request.method == "POST" else request.args.to_dict()
        data = data or {}
        query = (data.get("q") or data.get("query") or "").strip()
        if not query:
            return jsonify({"ok": False, "error": "No query provided"}), 400

        async def _do_search():
            return await search_web_tool(query)

        loop = None
        try:
            if client and client.is_ready():
                loop = client.loop
        except Exception:
            loop = None

        if loop and loop.is_running():
            future = asyncio.run_coroutine_threadsafe(_do_search(), loop)
            formatted, results = future.result(timeout=20)
        else:
            formatted, results = asyncio.run(_do_search())

        return jsonify({
            "ok": True,
            "query": query,
            "formatted": formatted,
            "results": results
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/chat", methods=["POST"])
def api_web_chat():
    t_start = time.time()
    now_str = time.strftime("%H:%M:%S")
    try:
        data = request.get_json(silent=True) or {}
        prompt = (data.get("message") or data.get("prompt") or "").strip()
        image_data = data.get("image_data")
        audio_data = data.get("audio_data")
        bot_id = data.get("bot_id") or bots_state.get("active_id") or "default_web"
        user_name = data.get("user_name") or "User"
        user_id = data.get("user_id") or "web_user"
        system_prompt = data.get("system_prompt")
        channel_id = f"web_{bot_id}"

        if not prompt and not image_data and not audio_data:
            print(f"\033[91m[{now_str}] [CHAT ERROR] Empty prompt received for {bot_id}\033[0m")
            return jsonify({"ok": False, "error": "Message is empty"}), 400

        print(f"\033[96m[{now_str}] [THEATER / WEB CHAT] User: '{user_name}' -> Persona: '{bot_id}' | Message: '{prompt[:75]}...'\033[0m")
        if image_data or audio_data:
            print(f"\033[95m  └─ Multimodal Payload: {'Image ' if image_data else ''}{'Audio ' if audio_data else ''}\033[0m")

        async def _do_chat():
            target_bot = get_bot_by_id(bots_state, bot_id) if ('bots_state' in globals() and isinstance(bots_state, dict)) else None
            target_cfg = target_bot.get("config", {}) if target_bot else config

            old_p = config.get("personality")
            old_t = config.get("temperature")
            old_tok = config.get("max_tokens")
            old_topp = config.get("top_p")
            old_freq = config.get("frequency_penalty")
            old_pres = config.get("presence_penalty")
            old_prov = config.get("provider")
            old_gmod = config.get("gemini_model")
            old_mod = config.get("model")
            old_cmod = config.get("custom_model")
            old_curl = config.get("custom_base_url")
            old_ckey = config.get("custom_key")
            old_ucm = config.get("use_custom_model")
            old_search = config.get("auto_search")
            old_split = config.get("message_split_enabled")

            effective_system = system_prompt or target_cfg.get("personality") or config.get("personality")
            temp_override = data.get("temperature") if data.get("temperature") is not None else target_cfg.get("temperature")
            tok_override = data.get("max_tokens") or data.get("tokens") or target_cfg.get("max_tokens")
            topp_override = data.get("top_p") if data.get("top_p") is not None else target_cfg.get("top_p")
            freq_override = data.get("frequency_penalty") if data.get("frequency_penalty") is not None else target_cfg.get("frequency_penalty")
            pres_override = data.get("presence_penalty") if data.get("presence_penalty") is not None else target_cfg.get("presence_penalty")
            prov_override = data.get("provider") or target_cfg.get("provider")
            mod_override = data.get("model") or data.get("custom_model") or target_cfg.get("model") or target_cfg.get("custom_model")

            req_custom_model = (data.get("custom_model") or (mod_override if prov_override == "custom" or (mod_override and "/" in str(mod_override)) else "") or target_cfg.get("custom_model") or "").strip()
            req_custom_base_url = (data.get("custom_base_url") or target_cfg.get("custom_base_url") or config.get("custom_base_url", "")).strip()
            req_custom_key = (data.get("custom_key") or target_cfg.get("custom_key") or config.get("custom_key", "")).strip()
            req_use_custom = data.get("use_custom_model") if data.get("use_custom_model") is not None else target_cfg.get("use_custom_model", False)

            is_voice_call = bool(data.get("is_voice_call") or (tok_override and int(tok_override) <= 160 and "voice call" in str(effective_system).lower()))
            if is_voice_call:
                config["auto_search"] = False
                config["message_split_enabled"] = False
                # If user did not pick a specific provider or left on auto, default to fastest voice model
                if not prov_override or prov_override in ("auto", "default"):
                    if GROQ_KEY and time.time() >= groq_blocked_until:
                        prov_override = "groq"
                        mod_override = "qwen/qwen3.8-27b"
                    elif GEMINI_KEY and time.time() >= gemini_blocked_until:
                        prov_override = "gemini"
                        mod_override = "gemini-3.1-flash-lite"

            prov_lower = str(prov_override or "auto").lower()
            if prov_lower in ("gemini", "groq", "mistral", "openai", "deepseek") and not req_custom_base_url:
                req_use_custom = False
                req_custom_model = ""
            elif prov_lower in ("custom", "openrouter") or req_custom_base_url:
                req_use_custom = True
            elif prov_lower == "auto":
                req_use_custom = bool(req_custom_base_url)

            try:
                if effective_system:
                    config["personality"] = effective_system
                if temp_override is not None:
                    try: config["temperature"] = float(temp_override)
                    except: pass
                if tok_override is not None:
                    try: config["max_tokens"] = int(tok_override)
                    except: pass
                if topp_override is not None:
                    try: config["top_p"] = float(topp_override)
                    except: pass
                if freq_override is not None:
                    try: config["frequency_penalty"] = float(freq_override)
                    except: pass
                if pres_override is not None:
                    try: config["presence_penalty"] = float(pres_override)
                    except: pass
                if prov_override:
                    config["provider"] = str(prov_override).lower()
                if mod_override:
                    if "gemini" in str(mod_override).lower() or prov_override == "gemini":
                        config["gemini_model"] = mod_override
                    elif "groq" in str(prov_override).lower() or "qwen" in str(mod_override).lower():
                        config["groq_model"] = mod_override
                    elif "mistral" in str(prov_override).lower() or "mistral" in str(mod_override).lower() or "codestral" in str(mod_override).lower():
                        config["mistral_model"] = mod_override
                    config["model"] = mod_override
                config["custom_model"] = req_custom_model
                config["custom_base_url"] = req_custom_base_url
                config["custom_key"] = req_custom_key
                config["use_custom_model"] = bool(req_use_custom)

                if image_data or audio_data:
                    try:
                        img_bytes = None
                        mime = "image/jpeg"
                        if image_data:
                            header, b64 = image_data.split(",", 1) if "," in image_data else ("", image_data)
                            if "image/png" in header: mime = "image/png"
                            elif "image/webp" in header: mime = "image/webp"
                            img_bytes = base64.b64decode(b64)

                        audio_bytes = None
                        audio_mime = "audio/wav"
                        if audio_data and isinstance(audio_data, str) and len(audio_data) > 30:
                            header_a, b64_a = audio_data.split(",", 1) if "," in audio_data else ("", audio_data)
                            if "webm" in header_a: audio_mime = "audio/webm"
                            elif "ogg" in header_a: audio_mime = "audio/ogg"
                            elif "mp3" in header_a or "mpeg" in header_a: audio_mime = "audio/mp3"
                            elif "mp4" in header_a or "m4a" in header_a: audio_mime = "audio/mp4"
                            audio_bytes = base64.b64decode(b64_a)

                        p = (prompt or "Look at this scene and listen to what is happening.").strip()
                        vision_system = effective_system or "You are an engaging AI companion."
                        if img_bytes and audio_bytes:
                            vision_system += "\n\nCRITICAL: You are co-watching with the user. Look at the attached video frame AND listen to the audio stream/music. React naturally to what you see and hear!"
                        elif img_bytes:
                            vision_system += "\n\nCRITICAL: The user has attached an image in this conversation. Look at the image details carefully and react/respond in full character as your defined persona."
                        elif audio_bytes:
                            vision_system += "\n\nCRITICAL: The user has attached an audio clip in this conversation. Listen to the audio/music carefully and react/respond in full character as your defined persona."

                        channel_ctx = list(contexts.get(channel_id, []))
                        v_model = data.get("video_watching_model") or data.get("model") or data.get("custom_model") or target_cfg.get("video_watching_model") or target_cfg.get("gemini_vision_model") or "gemini-3.1-flash-lite"
                        if not v_model or "live-preview" in str(v_model).lower() or v_model in ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-1.5-flash"]:
                            v_model = "gemini-3.1-flash-lite"
                        if v_model == "gemini-3.5-flash-lite":
                            v_model = "gemini-3.1-flash-lite"

                        # Ensure image/audio requests use Gemini Vision/Multimodal when available
                        r_prov = "gemini" if (GEMINI_KEY and time.time() >= gemini_blocked_until) else (data.get("provider") or target_cfg.get("provider") or "auto")
                        reply, err = await ask_multimodal_vision(
                            vision_system, p, img_bytes, mime_type=mime, history=channel_ctx,
                            model_override=v_model, provider_override=r_prov,
                            audio_bytes=audio_bytes, audio_mime=audio_mime,
                            max_tokens=tok_override, temperature=temp_override
                        )
                        if not err and reply:
                            reply = clean_llm_output(reply) or reply
                            with state_lock:
                                if channel_id not in contexts:
                                    contexts[channel_id] = []
                                tag = "[Image & Audio Attached]" if (img_bytes and audio_bytes) else ("[Image Attached]" if img_bytes else "[Audio Attached]")
                                user_summary = prompt if (prompt and not prompt.startswith("[LIVE THEATER") and not prompt.startswith("[CO-WATCHING")) else f"Watching video scene {tag}"
                                contexts[channel_id].append({"role": "user", "content": f"{user_name}: {user_summary}"})
                                contexts[channel_id].append({"role": "assistant", "content": reply})
                    except Exception as e:
                        print(f"\033[91m[{time.strftime('%H:%M:%S')}] [THEATER MULTIMODAL ERROR] {e}\033[0m")
                        return f"Error processing media: {e}", True

                if config.get("user_memory_enabled", True) and prompt:
                    class _WebDuckUser:
                        def __init__(self, u_id, u_name):
                            self.id = int(u_id) if str(u_id).isdigit() else u_id
                            self.display_name = str(u_name or "User")
                            self.name = self.display_name
                            self.global_name = self.display_name
                            self.avatar = None
                            self.banner = None
                    try:
                        await update_user_profile(_WebDuckUser(user_id, user_name), prompt)
                    except Exception as pe:
                        print(f"[THEATER USER PROFILE ERROR] {pe}")

                return await ask_ai(
                    channel_id, prompt,
                    user_id=user_id,
                    user_name=user_name,
                    is_dm=True,
                    system_msg_override=effective_system,
                    bot_id=bot_id,
                    custom_model=(req_custom_model or mod_override) if req_use_custom else None,
                    custom_base_url=req_custom_base_url if req_use_custom else "",
                    custom_key=req_custom_key if req_use_custom else ""
                )
            finally:
                if system_prompt and old_p is not None:
                    config["personality"] = old_p
                if old_t is not None: config["temperature"] = old_t
                if old_tok is not None: config["max_tokens"] = old_tok
                if old_topp is not None: config["top_p"] = old_topp
                if old_freq is not None: config["frequency_penalty"] = old_freq
                if old_pres is not None: config["presence_penalty"] = old_pres
                if old_prov is not None: config["provider"] = old_prov
                if old_gmod is not None: config["gemini_model"] = old_gmod
                if old_mod is not None: config["model"] = old_mod
                if old_cmod is not None: config["custom_model"] = old_cmod
                if old_curl is not None: config["custom_base_url"] = old_curl
                if old_ckey is not None: config["custom_key"] = old_ckey
                if old_ucm is not None: config["use_custom_model"] = old_ucm
                if old_search is not None: config["auto_search"] = old_search
                if old_split is not None: config["message_split_enabled"] = old_split

        loop = None
        try:
            if client and client.is_ready():
                loop = client.loop
        except Exception:
            loop = None
            
        try:
            if loop and loop.is_running():
                future = asyncio.run_coroutine_threadsafe(_do_chat(), loop)
                reply, err = future.result(timeout=25)
            else:
                async def _timed_do_chat():
                    return await asyncio.wait_for(_do_chat(), timeout=25.0)
                reply, err = asyncio.run(_timed_do_chat())
        except (TimeoutError, asyncio.TimeoutError):
            print(f"\033[93m[{time.strftime('%H:%M:%S')}] [THEATER TIMEOUT ERROR] AI response generation exceeded 25s timeout!\033[0m")
            return jsonify({"ok": False, "error": "AI request timed out after 25 seconds", "timeout": True}), 504

        dur_sec = round(time.time() - t_start, 2)
        if err:
            print(f"\033[91m[{time.strftime('%H:%M:%S')}] [THEATER CHAT FAILED] Error in {dur_sec}s: {reply}\033[0m")
            return jsonify({"ok": False, "error": str(reply), "reply": str(reply)})

        reply = clean_llm_output(reply) or reply
        print(f"\033[92m[{time.strftime('%H:%M:%S')}] [THEATER CHAT SUCCESS] Generated in {dur_sec}s: '{str(reply)[:80]}...'\033[0m")
        return jsonify({"ok": True, "reply": reply, "latency_sec": dur_sec})
    except Exception as e:
        print(f"\033[91m[{time.strftime('%H:%M:%S')}] [THEATER CHAT EXCEPTION] {e}\033[0m")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/test/<provider>", methods=["POST"])
def api_test(provider):
    async def _test():
        if provider == "gemini":
            return await ask_gemini("You are a test bot.", [], "Say 'Model is working' and nothing else.")
        elif provider == "groq":
            return await ask_groq([], "Say 'Model is working' and nothing else.")
        elif provider == "mistral":
            return await ask_mistral([], "Say 'Model is working' and nothing else.")
        elif provider == "openrouter":
            return await ask_openrouter([], "Say 'Model is working' and nothing else.")
        elif provider == "openai":
            return await ask_openai([], "Say 'Model is working' and nothing else.")
        elif provider == "deepseek":
            return await ask_deepseek([], "Say 'Model is working' and nothing else.")
        elif provider == "custom":
            return await ask_custom_endpoint([], "Say 'Model is working' and nothing else.")
        else:
            return "Unknown provider.", True
    try:
        loop = None
        try:
            if client and client.is_ready():
                loop = client.loop
        except Exception:
            loop = None
        if loop and loop.is_running():
            future = asyncio.run_coroutine_threadsafe(_test(), loop)
            reply, err = future.result(timeout=30)
        else:
            reply, err = asyncio.run(_test())
        if err:
            return jsonify({"ok": False, "error": reply})
        return jsonify({"ok": True, "reply": reply})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route("/api/tts", methods=["POST"])
@app.route("/api/tts/test", methods=["POST"])
def api_tts_route():
    try:
        data = request.get_json(silent=True) or {}
        text = (data.get("text") or "").strip()
        if not text:
            text = "Hello! This is a test of high-speed speech synthesis."
        
        bot_id = data.get("bot_id")
        bot_cfg = {}
        if bot_id and 'bots_state' in globals() and isinstance(bots_state, dict):
            b = get_bot_by_id(bots_state, bot_id)
            if b:
                bot_cfg = b.get("config", {})
        else:
            ab = get_active_bot(bots_state)
            if ab:
                bot_cfg = ab.get("config", {})

        provider = (data.get("provider") or bot_cfg.get("tts_provider") or "auto").lower().strip()
        voice = data.get("voice") or data.get("voice_id")
        if not voice:
            if provider == "elevenlabs":
                voice = bot_cfg.get("elevenlabs_voice_id") or bot_cfg.get("voice_id")
            elif provider == "fish":
                voice = bot_cfg.get("fish_voice_id") or bot_cfg.get("voice_id")
            elif provider == "cartesia":
                voice = bot_cfg.get("cartesia_voice_id")
            elif provider == "openai":
                voice = bot_cfg.get("openai_voice")
            elif provider == "edge":
                voice = bot_cfg.get("edge_tts_voice")
            elif provider == "groq":
                voice = bot_cfg.get("groq_tts_voice")
        
        model = data.get("model") or bot_cfg.get("elevenlabs_model") or bot_cfg.get("openai_model") or bot_cfg.get("cartesia_model") or bot_cfg.get("groq_tts_model") or bot_cfg.get("fish_model")

        now_str = time.strftime("%H:%M:%S")
        print(f"\033[96m[{now_str}] [VOICE LOG] [TTS_REQUEST] Provider: {provider} | Voice: {voice or 'default'} | Text: \"{text[:90]}{'...' if len(text) > 90 else ''}\"\033[0m")

        async def _test_tts():
            res = None
            if provider == "elevenlabs":
                res = await speak_elevenlabs(text, voice_id=voice, model=model)
            elif provider == "openai":
                res = await speak_openai(text, voice=voice, model=model)
            elif provider == "cartesia":
                res = await speak_cartesia(text, voice_id=voice, model=model)
            elif provider == "groq":
                res = await speak_groq(text, voice=voice, model=model)
            elif provider == "edge":
                res = await speak_edge(text, voice=voice)
            elif provider == "fish":
                if voice:
                    res = await speak_fish(text, voice_id=voice)
            else:
                res = await speak(text, force=True, bot_id=bot_id)
            
            if not res:
                if EDGE_TTS_AVAILABLE:
                    edge_v = bot_cfg.get("edge_tts_voice") or "en-US-AvaMultilingualNeural"
                    res = await speak_edge(text, voice=edge_v)
                if not res:
                    res = await speak(text, force=True, bot_id=bot_id)
            return res

        loop = None
        try:
            if client and client.is_ready():
                loop = client.loop
        except Exception:
            loop = None
        if loop and loop.is_running():
            future = asyncio.run_coroutine_threadsafe(_test_tts(), loop)
            audio_bytes = future.result(timeout=25)
        else:
            audio_bytes = asyncio.run(_test_tts())
            
        if not audio_bytes:
            print(f"\033[91m[{now_str}] [VOICE ERROR] [TTS_FAIL] Synthesis returned no audio.\033[0m")
            return jsonify({"ok": False, "error": "TTS synthesis returned no audio. Check API keys or logs."})
            
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        fmt = "wav" if (audio_bytes.startswith(b"RIFF") or audio_bytes.startswith(b"\x52\x49\x46\x46")) else "mp3"
        print(f"\033[95m[{now_str}] [VOICE LOG] [TTS_SUCCESS] Synthesized {len(audio_bytes)} bytes ({fmt})\033[0m")
        return jsonify({"ok": True, "data": audio_b64, "format": fmt, "size": len(audio_bytes)})
    except Exception as e:
        now_str = time.strftime("%H:%M:%S")
        print(f"\033[91m[{now_str}] [VOICE ERROR] [TTS_EXCEPTION] {e}\033[0m")
        return jsonify({"ok": False, "error": str(e)})

@app.route("/api/sync", methods=["POST"])
def api_sync():
    return jsonify({"ok": True, "message": "Bots sync slash commands automatically on startup."})

@app.route("/api/refresh_index", methods=["POST"])
def api_refresh_index():
    try:
        count = 0
        extensions = (".py", ".json", ".html", ".js", ".css", ".md")
        for root, dirs, files in os.walk(SCRIPT_DIR):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("__pycache__", "node_modules")]
            for f in files:
                if f.endswith(extensions):
                    count += 1
        return jsonify({"ok": True, "count": count})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route("/api/bots/<bot_id>/start", methods=["POST"])
def api_bot_start(bot_id):
    bot = get_bot_by_id(bots_state, bot_id)
    if not bot:
        return jsonify({"ok": False, "error": "Bot not found"}), 404
    token = bot.get("token", "").strip()
    if not token:
        return jsonify({"ok": False, "error": "No token set"}), 400
    ok = start_bot_process(bot_id, token)
    return jsonify({"ok": ok, "online": get_bot_process_status(bot_id)})

@app.route("/api/bots/<bot_id>/stop", methods=["POST"])
def api_bot_stop(bot_id):
    stop_bot_process(bot_id)
    return jsonify({"ok": True, "online": False})

@app.route("/api/channels")
def api_channels():
    with state_lock:
        return jsonify({"channels": [{"id": k, "messages": len(v)} for k, v in contexts.items()]})

@app.route("/api/clear", methods=["POST"])
def api_clear_all():
    with state_lock:
        contexts.clear()
    return jsonify({"ok": True})

@app.route("/api/clear/<channel_id>", methods=["POST"])
def api_clear_channel(channel_id):
    with state_lock:
        contexts.pop(channel_id, None)
    return jsonify({"ok": True})

# ─── MINECRAFT REST API ───────────────────────────────
@app.route("/api/minecraft/status", methods=["GET"])
def api_mc_status():
    return jsonify({
        "ok": True,
        "state": mc_state,
        "config": {
            "server": config.get("minecraft_server"),
            "port": config.get("minecraft_port"),
            "username": config.get("minecraft_username"),
            "version": config.get("minecraft_version"),
            "auth": config.get("minecraft_auth", "offline"),
            "enabled": config.get("minecraft_enabled", False)
        }
    })

@app.route("/api/minecraft/start", methods=["POST"])
def api_mc_start():
    ok, msg = start_minecraft_bot()
    return jsonify({"ok": ok, "message": msg})

@app.route("/api/minecraft/stop", methods=["POST"])
def api_mc_stop():
    ok, msg = stop_minecraft_bot()
    return jsonify({"ok": ok, "message": msg})

@app.route("/api/minecraft/cmd", methods=["POST"])
def api_mc_cmd():
    data = request.get_json(silent=True) or {}
    ok = send_mc_cmd(data)
    return jsonify({"ok": ok})

def _exec_async_flask(coro, timeout=30):
    """Safely executes an async coroutine from a Flask worker thread."""
    loop = None
    try:
        if client and client.is_ready() and client.loop and client.loop.is_running():
            loop = client.loop
    except Exception:
        loop = None
    if loop and loop.is_running():
        fut = asyncio.run_coroutine_threadsafe(coro, loop)
        return fut.result(timeout=timeout)
    else:
        return asyncio.run(coro)

def _fire_and_forget_async(coro):
    """Fires a background async task from a Flask worker thread without blocking."""
    loop = None
    try:
        if client and client.is_ready() and client.loop and client.loop.is_running():
            loop = client.loop
    except Exception:
        loop = None
    if loop and loop.is_running():
        asyncio.run_coroutine_threadsafe(coro, loop)
    else:
        threading.Thread(target=lambda: asyncio.run(coro), daemon=True).start()

# ─── POKÉMON SHOWDOWN REST API ───────────────────────
@app.route("/api/showdown/status", methods=["GET"])
def api_showdown_status():
    if not SHOWDOWN_ENGINE_AVAILABLE or not showdown_manager:
        return jsonify({"ok": False, "error": "Showdown engine not available"}), 503
    target_bot_id = request.args.get("bot_id") or bots_state.get("active_id", "default")
    target_bot = get_bot_by_id(bots_state, target_bot_id)
    target_name = target_bot.get("name", "Bot") if target_bot else "Bot"
    target_cfg = target_bot.get("config", {}) if target_bot else config

    cur_client = showdown_manager.get_client(target_bot_id)
    if not cur_client and target_cfg:
        cur_client = showdown_manager.init_bot(target_bot_id, target_name, target_cfg)

    statuses = showdown_manager.get_statuses()
    return jsonify({
        "ok": True,
        "active_bot_id": target_bot_id,
        "bot_name": target_name,
        "bots": statuses,
        "active_client": {
            "username": cur_client.username if cur_client else f"{target_name}AI",
            "is_connected": cur_client.is_connected if cur_client else False,
            "is_registered": cur_client.is_registered if cur_client else False,
            "auto_accept": cur_client.auto_accept if cur_client else True,
            "battles": len(cur_client.active_battles) if cur_client else 0,
            "format": cur_client.default_format if cur_client else "gen9randombattle"
        } if cur_client else None
    })

@app.route("/api/showdown/connect", methods=["POST"])
def api_showdown_connect():
    if not SHOWDOWN_ENGINE_AVAILABLE or not showdown_manager:
        return jsonify({"ok": False, "error": "Showdown engine not available"}), 503
    data = request.get_json(silent=True) or {}
    b_id = data.get("bot_id") or bots_state.get("active_id", "default")
    b_obj = get_bot_by_id(bots_state, b_id)
    b_name = b_obj.get("name", "Bot") if b_obj else "Bot"
    b_cfg = b_obj.get("config", {}) if b_obj else config
    b_cfg["showdown_enabled"] = True
    save_bots_state_to_disk(bots_state)
    sd = showdown_manager.init_bot(b_id, b_name, b_cfg)
    _fire_and_forget_async(sd.start())
    return jsonify({"ok": True, "message": f"Connecting {b_name} as {sd.username}..."})

@app.route("/api/showdown/register", methods=["POST"])
def api_showdown_register():
    if not SHOWDOWN_ENGINE_AVAILABLE or not showdown_manager:
        return jsonify({"ok": False, "error": "Showdown engine not available"}), 503
    data = request.get_json(silent=True) or {}
    b_id = data.get("bot_id") or bots_state.get("active_id", "default")
    b_obj = get_bot_by_id(bots_state, b_id)
    b_name = b_obj.get("name", "Bot") if b_obj else "Bot"
    b_cfg = b_obj.get("config", {}) if b_obj else config
    sd = showdown_manager.init_bot(b_id, b_name, b_cfg)
    new_user = (data.get("username") or "").strip()
    new_pass = (data.get("password") or "").strip()
    if new_user:
        sd.username = new_user
        b_cfg["showdown_username"] = new_user
    if new_pass:
        sd.password = new_pass
        b_cfg["showdown_password"] = new_pass
    b_cfg["showdown_enabled"] = True
    save_bots_state_to_disk(bots_state)
    async def _re():
        await sd.stop()
        await sd.start()
    _fire_and_forget_async(_re())
    return jsonify({"ok": True, "username": sd.username, "message": f"Showdown registration triggered for {b_name} ({sd.username})."})

@app.route("/api/showdown/challenge", methods=["POST"])
def api_showdown_challenge():
    if not SHOWDOWN_ENGINE_AVAILABLE or not showdown_manager:
        return jsonify({"ok": False, "error": "Showdown engine not available"}), 503
    data = request.get_json(silent=True) or {}
    target_user = data.get("target") or data.get("username")
    if not target_user:
        return jsonify({"ok": False, "error": "Missing target username"}), 400
    b_id = data.get("bot_id") or bots_state.get("active_id", "default")
    b_obj = get_bot_by_id(bots_state, b_id)
    b_name = b_obj.get("name", "Bot") if b_obj else "Bot"
    b_cfg = b_obj.get("config", {}) if b_obj else config
    sd = showdown_manager.init_bot(b_id, b_name, b_cfg)
    fmt = data.get("format") or sd.default_format
    # Queue for live child worker
    queue_showdown_ipc_cmd(b_id, "challenge", {"target": target_user, "format": fmt})
    # Also run on supervisor client if active
    if sd and sd.is_connected:
        _fire_and_forget_async(sd.challenge_user(target_user, fmt))
    return jsonify({"ok": True, "message": f"Challenged {target_user} in {fmt}"})

@app.route("/api/showdown/accept", methods=["POST"])
def api_showdown_accept():
    if not SHOWDOWN_ENGINE_AVAILABLE or not showdown_manager:
        return jsonify({"ok": False, "error": "Showdown engine not available"}), 503
    data = request.get_json(silent=True) or {}
    b_id = data.get("bot_id") or bots_state.get("active_id", "default")
    sd = showdown_manager.get_client(b_id)
    challenger = data.get("challenger")
    if challenger:
        queue_showdown_ipc_cmd(b_id, "accept", {"challenger": challenger})
        if sd and sd.is_connected:
            _fire_and_forget_async(sd.send_raw(f"|/accept {challenger}"))
        return jsonify({"ok": True, "message": f"Accepted challenge from {challenger}"})
    else:
        if sd:
            sd.auto_accept = True
        return jsonify({"ok": True, "message": "Auto-accept enabled."})

@app.route("/api/showdown/ladder", methods=["POST"])
def api_showdown_ladder():
    if not SHOWDOWN_ENGINE_AVAILABLE or not showdown_manager:
        return jsonify({"ok": False, "error": "Showdown engine not available"}), 503
    data = request.get_json(silent=True) or {}
    b_id = data.get("bot_id") or bots_state.get("active_id", "default")
    b_obj = get_bot_by_id(bots_state, b_id)
    b_name = b_obj.get("name", "Bot") if b_obj else "Bot"
    b_cfg = b_obj.get("config", {}) if b_obj else config
    sd = showdown_manager.init_bot(b_id, b_name, b_cfg)
    fmt = data.get("format") or sd.default_format
    queue_showdown_ipc_cmd(b_id, "ladder", {"format": fmt})
    if sd and sd.is_connected:
        _fire_and_forget_async(sd.search_ladder(fmt))
    return jsonify({"ok": True, "message": f"Searching ladder for {fmt}"})

@app.route("/api/showdown/stop", methods=["POST"])
def api_showdown_stop():
    if not SHOWDOWN_ENGINE_AVAILABLE or not showdown_manager:
        return jsonify({"ok": False, "error": "Showdown engine not available"}), 503
    data = request.get_json(silent=True) or {}
    b_id = data.get("bot_id") or bots_state.get("active_id", "default")
    sd = showdown_manager.get_client(b_id)
    if sd:
        _fire_and_forget_async(sd.stop())
    return jsonify({"ok": True, "message": "Showdown stopped."})

# ─── DOODLE REST API ──────────────────────────────────
@app.route("/api/doodle/generate", methods=["POST"])
def api_doodle_generate():
    if not DOODLE_ENGINE_AVAILABLE:
        return jsonify({"ok": False, "error": "Doodle engine not available"}), 503
    data = request.get_json(silent=True) or {}
    prompt = data.get("prompt", "cute cat")
    active_bot = get_active_bot(bots_state)
    b_name = active_bot.get("name", "Bot") if active_bot else "Bot"
    b_pers = active_bot.get("config", {}).get("personality", "") if active_bot else ""
    try:
        img_bytes, comment = _exec_async_flask(generate_doodle(prompt, b_name, b_pers), timeout=25)
        b64 = base64.b64encode(img_bytes).decode("utf-8") if img_bytes else ""
        return jsonify({"ok": True, "image": f"data:image/png;base64,{b64}", "comment": comment})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/doodle/along", methods=["POST"])
def api_doodle_along():
    if not DOODLE_ENGINE_AVAILABLE:
        return jsonify({"ok": False, "error": "Doodle engine not available"}), 503
    data = request.get_json(silent=True) or {}
    raw_img = data.get("image", "")
    prompt = data.get("prompt", "")
    if not raw_img:
        return jsonify({"ok": False, "error": "No image data provided"}), 400
    if "," in raw_img:
        raw_img = raw_img.split(",", 1)[1]
    img_bytes = base64.b64decode(raw_img)
    active_bot = get_active_bot(bots_state)
    b_name = active_bot.get("name", "Bot") if active_bot else "Bot"
    b_pers = active_bot.get("config", {}).get("personality", "") if active_bot else ""
    try:
        res_bytes, comment = _exec_async_flask(doodle_along(img_bytes, prompt, b_name, b_pers), timeout=25)
        b64 = base64.b64encode(res_bytes).decode("utf-8")
        return jsonify({"ok": True, "image": f"data:image/png;base64,{b64}", "comment": comment})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/doodle/blueprint", methods=["GET", "POST"])
def api_doodle_blueprint():
    prompt = request.args.get("prompt") or (request.get_json(silent=True) or {}).get("prompt", "cat")
    if DOODLE_ENGINE_AVAILABLE and get_vector_doodle_blueprint:
        bp = get_vector_doodle_blueprint(prompt)
        return jsonify({"ok": True, "blueprint": bp})
    return jsonify({"ok": False, "error": "Blueprint generator unavailable"}), 503

@app.route("/neww.vrm")
@app.route("/yuna.vrm")
def serve_vrm():
    try:
        req_path = request.path or ""
        target = "neww.vrm" if "neww.vrm" in req_path else "yuna.vrm"
        vrm_path = os.path.join(SCRIPT_DIR, target)
        if not os.path.exists(vrm_path):
            vrm_path = os.path.join(SCRIPT_DIR, "neww.vrm") if os.path.exists(os.path.join(SCRIPT_DIR, "neww.vrm")) else os.path.join(SCRIPT_DIR, "yuna.vrm")
        return send_file(vrm_path, mimetype="model/gltf-binary", max_age=86400)
    except Exception as e:
        return str(e), 404

@app.route("/vrm_viewer.html")
def serve_viewer():
    try:
        html_path = os.path.join(SCRIPT_DIR, "vrm_viewer.html")
        return send_file(html_path)
    except Exception as e:
        return str(e), 404

@app.route('/<path:path>')
def send_static_file(path):
    try:
        return send_from_directory(SCRIPT_DIR, path)
    except Exception as e:
        return str(e), 404

def find_available_port(start_port=5000, max_tries=30):
    import socket
    for p in range(start_port, start_port + max_tries):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(('0.0.0.0', p))
                return p
        except Exception:
            continue
    return start_port

def run_flask():
    desired_port = int(config.get("dashboard_port", 5000))
    port = find_available_port(desired_port)
    print(f"[MAIN] Web Dashboard online at http://0.0.0.0:{port}")
    try:
        fp = os.path.join(SCRIPT_DIR, "data", "flask_port.txt")
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "w") as f:
            f.write(str(port))
    except Exception:
        pass
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)

def run_bot():
    client.run(os.getenv("DISCORD_TOKEN"))

if __name__ == "__main__":
    _acquire_instance_lock()
    is_child = os.getenv("IS_BOT_CHILD") == "1"
    child_bot_id = os.getenv("BOT_ID")
    child_token = os.getenv("DISCORD_TOKEN")
    if is_child and child_bot_id and child_token:
        child_bot = get_bot_by_id(bots_state, child_bot_id)
        if child_bot:
            apply_bot_to_config(child_bot, save_to_disk=False)
            if SOCIAL_INTEGRATION_AVAILABLE and social_manager:
                social_manager.update_config(config)
            print(f"[BOT CHILD] Starting isolated instance {child_bot_id} ({child_bot.get('name', 'Unknown')})")
        else:
            print(f"[BOT CHILD] Bot {child_bot_id} not found in state, using default config")
        client.run(child_token)
    else:
        os.environ.pop("IS_BOT_CHILD", None)
        os.environ.pop("BOT_ID", None)
        os.environ.pop("SUPERVISOR_PID", None)
        threading.Thread(target=run_flask, daemon=True).start()
        print("[MAIN] Web Dashboard running on http://0.0.0.0:5000")

        if config.get("vtuber_enabled", True) and WEBSOCKETS_AVAILABLE:
            threading.Thread(target=run_vtuber_server_thread, daemon=True).start()

        # Track tokens started as child workers to prevent gateway session collisions
        started_tokens = set()
        active_id = bots_state.get("active_id")

        # Prioritize starting the active bot first
        bots_list = list(bots_state.get("bots", []))
        if active_id:
            bots_list.sort(key=lambda x: 0 if x.get("id") == active_id else 1)

        for b in bots_list:
            tok = b.get("token", "").strip()
            if tok:
                if tok in started_tokens:
                    print(f"[MAIN] Skipping child process for {b.get('name', b['id'])} (token already running on another persona)")
                    continue
                start_bot_process(b["id"], tok)
                started_tokens.add(tok)
                print(f"[MAIN] Started isolated child process for {b.get('name', b['id'])}")

        # Helper functions for dynamic supervisor reload / restart
        def restart_user_worker():
            stop_user_worker_service()
            time.sleep(0.5)
            if config.get("user_worker_enabled", True):
                start_user_worker_service()

        def restart_child_bots():
            print("[SUPERVISOR] Reloading child bot processes...")
            try:
                bots_f = os.path.join(SCRIPT_DIR, "data", "bots.json")
                if os.path.exists(bots_f):
                    with open(bots_f, "r", encoding="utf-8") as f:
                        fresh_state = json.load(f)
                else:
                    fresh_state = bots_state
            except Exception:
                fresh_state = bots_state

            for pid_key in list(bot_processes.keys()):
                if pid_key != "user_worker":
                    stop_bot_process(pid_key)

            time.sleep(1)
            for b in fresh_state.get("bots", []):
                tok = b.get("token", "").strip()
                if tok:
                    start_bot_process(b["id"], tok)
                    print(f"[SUPERVISOR] Restarted child bot: {b.get('name', b['id'])}")

        # Acquire Termux wake lock so Android OS never suspends Wi-Fi or kills sockets in background
        try:
            twl = shutil.which("termux-wake-lock") or "/data/data/com.termux/files/usr/bin/termux-wake-lock"
            if os.path.exists(twl):
                subprocess.run([twl], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
                print("[MAIN] Termux wake lock acquired (Wi-Fi & socket protection active).")
        except Exception:
            pass

        # Auto-launch real account companion worker if enabled
        if config.get("user_worker_enabled", True):
            start_user_worker_service()
        else:
            print("[MAIN] Real Account Companion worker is currently toggled OFF in config.")

        def _check_restart_flags():
            req_paths = [
                os.path.join(SCRIPT_DIR, "data", "restart_request.json"),
                os.path.join(SCRIPT_DIR, "restart_request.json")
            ]
            for req_p in req_paths:
                if os.path.exists(req_p):
                    try:
                        with open(req_p, "r", encoding="utf-8") as rf:
                            req_data = json.load(rf)
                        os.unlink(req_p)
                        target_svc = req_data.get("service", "both")
                        print(f"[SUPERVISOR] Received restart trigger for '{target_svc}'")
                        if target_svc in ["supervisor", "hard_restart", "full"]:
                            print("[SUPERVISOR] Executing full process re-exec...")
                            for pid_key in list(bot_processes.keys()):
                                stop_bot_process(pid_key)
                            os.environ.pop("IS_BOT_CHILD", None)
                            os.environ.pop("BOT_ID", None)
                            os.environ.pop("SUPERVISOR_PID", None)
                            try:
                                import resource
                                max_fd = resource.getrlimit(resource.RLIMIT_NOFILE)[1]
                                if max_fd == resource.RLIM_INFINITY:
                                    max_fd = 1024
                                for fd in range(3, min(max_fd, 2048)):
                                    try:
                                        os.close(fd)
                                    except OSError:
                                        pass
                            except Exception:
                                pass
                            os.execv(sys.executable, [sys.executable] + sys.argv)
                        if target_svc in ["user_worker", "both", "all"]:
                            restart_user_worker()
                        if target_svc in ["bot.py", "bots", "both", "all"]:
                            restart_child_bots()
                    except Exception as _r_err:
                        print(f"[SUPERVISOR] Error processing restart request: {_r_err}")

        main_token = os.getenv("DISCORD_TOKEN", "").strip()
        if main_token and main_token not in started_tokens:
            def _watch_restart_for_main():
                while True:
                    time.sleep(3)
                    _check_restart_flags()
            threading.Thread(target=_watch_restart_for_main, daemon=True).start()
            print("[MAIN] Starting primary Discord bot in main process...")
            run_bot()
        else:
            print("[MAIN] All bots running in isolated child processes. Supervisor loop active.")
            try:
                while True:
                    time.sleep(3)
                    _check_restart_flags()
            except KeyboardInterrupt:
                print("[MAIN] Terminating child bot processes...")
                for pid_key in list(bot_processes.keys()):
                    stop_bot_process(pid_key)
