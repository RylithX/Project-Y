#!/usr/bin/env python3
"""
Yuna Real Account Companion Worker
-----------------------------------
Connects a real Discord user account via discord.py-self,
bridging directly into Yuna's shared AI brain and memory running in bot.py.

Features:
- Auto-accept incoming friend requests
- Auto-join Discord servers when invite link is DMed (discord.gg / discord.com/invite)
- Conversational Burst Window (10-15s group batching & context relevance filter)
- Insta Burst Energy Effect (multi-bubble rapid fire message delivery)
"""

import os
import re
import sys
import json
import time
import random
import socket
import asyncio
import aiohttp
from typing import Dict, List, Set, Optional
from pathlib import Path

import discord
from dotenv import load_dotenv

import yuna_backup_guard as backup_guard
import yuna_agy_bridge as agy_bridge
import yuna_owner_escalation as owner_escalation
import yuna_feature_evaluator as feature_evaluator

try:
    import yuna_rpc
except Exception as _yrpc_err:
    print(f"[USER WORKER] Could not import yuna_rpc: {_yrpc_err}")
    yuna_rpc = None

BASE_DIR = Path(__file__).parent.resolve()
load_dotenv(BASE_DIR / ".env")

USER_TOKEN = os.getenv("DISCORD_USER_TOKEN", "").strip()
YUNA_BOT_ID = os.getenv("YUNA_BOT_ID", "bot_ek0ldel3")

if not USER_TOKEN:
    print("[ERROR] DISCORD_USER_TOKEN is missing or empty in .env!")
    sys.exit(1)

def find_brain_url():
    """Detects active Flask port by checking flask_port.txt or scanning local ports."""
    env_url = os.getenv("YUNA_API_URL")
    if env_url:
        return env_url

    port_file = BASE_DIR / "data" / "flask_port.txt"
    if port_file.exists():
        try:
            p = int(port_file.read_text().strip())
            return f"http://127.0.0.1:{p}"
        except Exception:
            pass

    for p in [5001, 5000, 5002, 5003]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.15)
            if s.connect_ex(('127.0.0.1', p)) == 0:
                return f"http://127.0.0.1:{p}"
    return "http://127.0.0.1:5001"

FLASK_API_URL = find_brain_url()
client = discord.Client()

def load_config() -> dict:
    """Reads latest settings from config.json."""
    cfg_file = BASE_DIR / "config.json"
    if cfg_file.exists():
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

# ─────────────────────────────────────────────────────────────
# CONVERSATIONAL BURST WINDOW STATE
# ─────────────────────────────────────────────────────────────
class BurstSession:
    def __init__(self, channel_id: int, initial_message: discord.Message, window_seconds: float = 12.0):
        self.channel_id = channel_id
        self.initial_message = initial_message
        self.start_time = time.time()
        # Strictly clamp window duration between 10.0 and 15.0 seconds as requested
        self.window_seconds = max(10.0, min(15.0, float(window_seconds)))
        self.participants: Dict[int, str] = {initial_message.author.id: getattr(initial_message.author, "display_name", initial_message.author.name)}
        self.participant_names: Set[str] = {
            initial_message.author.display_name.lower(),
            initial_message.author.name.lower()
        }
        self.relevant_messages: List[discord.Message] = [initial_message]
        self.message_ids: Set[int] = {initial_message.id}
        self.bot_message_ids: Set[int] = set()
        self.task: Optional[asyncio.Task] = None
        self.turn_count: int = 0

    def record_incoming_message(self, message: discord.Message):
        self.relevant_messages.append(message)
        self.message_ids.add(message.id)
        disp_name = getattr(message.author, "display_name", message.author.name)
        self.participants[message.author.id] = disp_name
        self.participant_names.add(disp_name.lower())
        self.participant_names.add(message.author.name.lower())

    def update_after_reply(self, sent_messages: List[discord.Message]):
        self.turn_count += 1
        for sm in (sent_messages or []):
            if hasattr(sm, "id"):
                self.message_ids.add(sm.id)
                self.bot_message_ids.add(sm.id)

active_burst_sessions: Dict[int, BurstSession] = {}

# Regex for Discord server invites
INVITE_REGEX = re.compile(r'(?:https?://)?(?:www\.)?(?:discord\.(?:gg|io|me|li)|discord(?:app)?\.com/invite)/([a-zA-Z0-9-]+)', re.IGNORECASE)

def get_user_spotify_activity(author: Optional[discord.abc.User]) -> Optional[Dict[str, str]]:
    """Extracts active Spotify listening details from a Discord user/member."""
    if not author:
        return None
    activities = getattr(author, "activities", [])
    if not activities and hasattr(client, "guilds"):
        for g in client.guilds:
            m = g.get_member(author.id)
            if m and getattr(m, "activities", None):
                activities = m.activities
                break
    for act in activities:
        if isinstance(act, discord.Spotify) or (getattr(act, "name", "") or "").lower() == "spotify":
            return {
                "title": getattr(act, "title", None) or getattr(act, "details", "Unknown Track"),
                "artist": getattr(act, "artist", None) or getattr(act, "state", "Unknown Artist"),
                "album": getattr(act, "album", None) or "Unknown Album"
            }
    return None

def build_music_awareness_context(author: Optional[discord.abc.User] = None) -> str:
    """Builds real-time music context for Yuna's current Spotify track and the user's Spotify track."""
    lines = []
    # 1. Yuna's own active track
    if yuna_rpc:
        try:
            curr_track = yuna_rpc.get_current_track_info()
            if curr_track:
                t_name = curr_track.get("title", "Unknown Track")
                t_artist = curr_track.get("artist", "Unknown Artist")
                t_album = curr_track.get("album", "Single")
                dur_bar = yuna_rpc.get_progress_bar(curr_track)
                lines.append("🎧 [YUNA'S CURRENT SPOTIFY PLAYBACK - KIZZY RPC]:")
                lines.append(f"- You are wearing your headphones listening to \"{t_name}\" by {t_artist} (Album: {t_album}) on Spotify.")
                lines.append(f"- Timeline: {dur_bar}")
                lines.append("- Your Discord status profile broadcasts this song live to everyone via Kizzy RPC.")
                lines.append("- You love Vocaloid, J-Pop (Kairiki Bear, Ado, Eve, Surii, YOASOBI), and high-energy bangers.")
                lines.append("- If users ask what song is playing, what you are listening to, or mention music, banter enthusiastically or tsundere-tease them about this track!")
        except Exception:
            pass

    # 2. Chat partner's active track
    if author:
        try:
            user_spotify = get_user_spotify_activity(author)
            if user_spotify:
                u_name = getattr(author, "display_name", author.name)
                lines.append(f"\n🎵 [CHAT PARTNER'S MUSIC ACTIVITY]:")
                lines.append(f"- @{u_name} is currently listening to \"{user_spotify['title']}\" by {user_spotify['artist']} (Album: {user_spotify['album']}) on Spotify.")
                lines.append("- You can see their Spotify status. Feel free to praise, tease, or question their taste in music naturally!")
        except Exception:
            pass

    return "\n".join(lines)

async def query_yuna_brain(prompt: str, user_name: str, user_id: str, channel_id: str, author: Optional[discord.abc.User] = None) -> str:
    """
    Queries Yuna's AI brain via local REST API with a strict 10s timeout and direct Gemini fallback
    so the bot NEVER hangs or waits indefinitely to reply.
    Injects real-time Spotify and music awareness.
    """
    global FLASK_API_URL
    music_ctx = build_music_awareness_context(author)

    full_prompt = prompt
    if music_ctx:
        full_prompt = f"{prompt}\n\n{music_ctx}"

    payload = {
        "message": full_prompt,
        "bot_id": YUNA_BOT_ID,
        "user_name": user_name,
        "user_id": str(user_id)
    }

    # 1. Try local Flask brain (15s attempt 1, 8s attempt 2)
    for attempt in range(2):
        try:
            timeout = aiohttp.ClientTimeout(total=15 if attempt == 0 else 8)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(f"{FLASK_API_URL}/api/chat", json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("ok"):
                            reply = data.get("reply", "").strip()
                            if reply:
                                return reply
                        else:
                            print(f"[YUNA BRAIN ERROR] {data.get('error')}")
                    else:
                        print(f"[YUNA BRAIN HTTP] Status {resp.status} from {FLASK_API_URL}/api/chat")
        except Exception as e:
            print(f"[YUNA BRAIN ATTEMPT] {attempt+1} failed: {e or type(e).__name__}")
            FLASK_API_URL = find_brain_url()
            await asyncio.sleep(0.3)

    # 2. Fast direct Gemini fallback if Flask is congested/restarting (prevents infinite wait)
    try:
        from yuna_feature_evaluator import _get_gemini_key
        key = _get_gemini_key()
        if key:
            sys_prompt = (
                "You are Yuna, an unhinged, playful, loving, chaotic, and tsundere anime girl on Discord.\n"
                "Speak in short, punchy responses like a real Discord chatter. Never break character."
            )
            if music_ctx:
                sys_prompt += f"\n\n{music_ctx}"
            models_to_try = ["gemini-flash-latest", "gemini-flash-lite-latest", "gemini-pro-latest"]
            payload_direct = {
                "contents": [{"parts": [{"text": f"User {user_name} says: {prompt}"}]}],
                "systemInstruction": {"parts": [{"text": sys_prompt}]},
                "generationConfig": {"maxOutputTokens": 600, "temperature": 0.8}
            }
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for m in models_to_try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={key}"
                    try:
                        async with session.post(url, json=payload_direct) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                reply_txt = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                                if reply_txt:
                                    return reply_txt
                    except Exception:
                        continue
    except Exception as fb_err:
        print(f"[YUNA DIRECT FALLBACK ERROR] {fb_err}")

    return ""

async def deliver_burst_messages(channel: discord.abc.Messageable, reply_text: str, reply_to_msg: Optional[discord.Message] = None) -> List[discord.Message]:
    """
    Insta Burst Energy Effect:
    Sends messages with natural rapid-texting pacing, splitting multi-part responses
    into 2-3 quick successive chat bubbles if burst energy is active.
    Returns the list of sent discord.Message objects.
    """
    cfg = load_config()
    burst_energy = int(cfg.get("burst_energy", 85))
    sent_msgs = []

    # Split on explicit split markers or multi-sentence paragraphs if burst energy > 60%
    parts = []
    if "||SPLIT||" in reply_text:
        parts = [p.strip() for p in reply_text.split("||SPLIT||") if p.strip()]
    elif burst_energy >= 70 and "\n\n" in reply_text:
        parts = [p.strip() for p in reply_text.split("\n\n") if p.strip()]
    elif burst_energy >= 80 and len(reply_text) > 120 and (". " in reply_text or "! " in reply_text):
        # Natural two-bubble split
        sents = re.split(r'(?<=[.!?])\s+', reply_text)
        if len(sents) >= 2:
            mid = len(sents) // 2
            part1 = " ".join(sents[:mid]).strip()
            part2 = " ".join(sents[mid:]).strip()
            if part1 and part2:
                parts = [part1, part2]

    if not parts:
        parts = [reply_text]

    # Send parts with rapid burst delay
    for idx, part in enumerate(parts):
        try:
            sent = None
            if idx == 0 and reply_to_msg:
                try:
                    sent = await reply_to_msg.reply(part, mention_author=False)
                except Exception:
                    sent = await channel.send(part)
            else:
                sent = await channel.send(part)

            if sent:
                sent_msgs.append(sent)

            if idx < len(parts) - 1:
                # Rapid texting pause: 0.6s to 1.2s
                await asyncio.sleep(random.uniform(0.6, 1.2))
        except Exception as e:
            print(f"[YUNA BURST SEND ERROR] {e}")

    return sent_msgs

# ─────────────────────────────────────────────────────────────
# DISCORD CLIENT EVENTS
# ─────────────────────────────────────────────────────────────
@client.event
async def on_ready():
    print("=" * 60)
    print(f"[YUNA REAL ACCOUNT] Online as: {client.user.name}#{client.user.discriminator} (ID: {client.user.id})")
    print(f"[YUNA REAL ACCOUNT] Connected to AI brain at: {FLASK_API_URL}")
    print(f"[YUNA REAL ACCOUNT] Guilds joined: {len(client.guilds)} | Relationships: {len(getattr(client, 'relationships', []))}")
    print("=" * 60)

    # Periodic heartbeat task for easy health monitoring
    async def _heartbeat_loop():
        while True:
            await asyncio.sleep(60)
            try:
                print(f"[YUNA REAL ACCOUNT HEARTBEAT] Active | Latency: {client.latency*1000:.1f}ms | Guilds: {len(client.guilds)}")
            except Exception:
                pass
    asyncio.create_task(_heartbeat_loop())

    # Yuna Rich Presence (Kizzy RPC) for companion account
    async def _rpc_presence_loop():
        while True:
            try:
                if yuna_rpc:
                    activity = await yuna_rpc.get_or_update_activity()
                    if activity:
                        await client.change_presence(status=discord.Status.online, activity=activity)
            except Exception as _e:
                print(f"[YUNA USER RPC ERROR] {_e}")
            await asyncio.sleep(25)
    asyncio.create_task(_rpc_presence_loop())

    # Auto-accept pending incoming friend requests on launch
    cfg = load_config()
    if cfg.get("auto_accept_friends", True):
        accepted_count = 0
        try:
            for rel in getattr(client, "relationships", []):
                if rel.type == discord.RelationshipType.incoming_request:
                    await rel.accept()
                    accepted_count += 1
                    print(f"[YUNA FRIEND AUTO-ACCEPT] Accepted pending friend request from @{rel.user.name}")
                    await asyncio.sleep(0.5)
            if accepted_count > 0:
                print(f"[YUNA FRIEND AUTO-ACCEPT] Accepted {accepted_count} pending friend request(s) on startup.")
        except Exception as e:
            print(f"[YUNA FRIEND CHECK ERROR] {e}")

@client.event
async def on_relationship_add(relationship: discord.Relationship):
    """Automatically accepts incoming friend requests in real-time."""
    cfg = load_config()
    if not cfg.get("auto_accept_friends", True):
        return

    if relationship.type == discord.RelationshipType.incoming_request:
        try:
            await relationship.accept()
            print(f"[YUNA REAL ACCOUNT] Auto-accepted incoming friend request from: @{relationship.user.name} ({relationship.user.id})")
        except Exception as e:
            print(f"[YUNA REAL ACCOUNT] Failed to accept friend request from {relationship.user}: {e}")

async def handle_burst_window_completion(session: BurstSession):
    """
    Continuous Conversational Context Window:
    1. Keeps window open for 10-15 seconds.
    2. Synthesizes and delivers the response.
    3. Reopens the window right away for another 10-15s to keep the conversation going seamlessly.
    4. Closes gracefully only when a 10-15s follow-up window passes with no new in-context messages.
    """
    channel_id = session.channel_id
    try:
        while True:
            # 1. Wait out the 10-15s conversational collection window
            await asyncio.sleep(session.window_seconds)

            # Retrieve channel object
            channel = client.get_channel(channel_id)
            if not channel:
                try:
                    channel = await client.fetch_channel(channel_id)
                except Exception:
                    break

            # 2. Extract and flush current buffered messages
            relevant_msgs = list(session.relevant_messages)
            session.relevant_messages.clear()

            if not relevant_msgs:
                # No new messages received during this open window -> conversation naturally idled out
                ch_title = "DM" if isinstance(channel, (discord.DMChannel, discord.GroupChannel)) else f"#{getattr(channel, 'name', 'chat')}"
                print(f"[YUNA BURST WINDOW CLOSED] {ch_title} idled out naturally after turn {session.turn_count}.")
                break

            # 3. Process the messages
            sent_msgs = []
            if len(relevant_msgs) == 1:
                m = relevant_msgs[0]
                clean_text = m.content.replace(f"<@{client.user.id}>", "").replace(f"<@!{client.user.id}>", "").strip()
                author_name = getattr(m.author, "display_name", m.author.name)

                # Check if user asked for a missing feature
                feat_intent = feature_evaluator.check_feature_intent(clean_text)
                if feat_intent:
                    async def _burst_reply_fn(reply_text):
                        nonlocal sent_msgs
                        sent_msgs = await deliver_burst_messages(channel, reply_text, reply_to_msg=m)
                    handled = await feature_evaluator.handle_feature_request(
                        feat_intent, channel, m.author, client, _burst_reply_fn
                    )
                    if handled:
                        session.update_after_reply(sent_msgs)
                        continue

                async with channel.typing():
                    try:
                        reply = await query_yuna_brain(
                            prompt=clean_text or "Hello",
                            user_name=author_name,
                            user_id=str(m.author.id),
                            channel_id=str(channel_id),
                            author=m.author
                        )
                        if reply:
                            sent_msgs = await deliver_burst_messages(channel, reply, reply_to_msg=m)
                            ch_title = "DM" if isinstance(channel, (discord.DMChannel, discord.GroupChannel)) else f"#{getattr(channel, 'name', 'chat')}"
                            print(f"[YUNA BURST FINISHED] Replied to message from @{author_name} in {ch_title}")
                    except Exception as b_err:
                        await feature_evaluator.handle_crash_or_error(b_err, channel, client, author=m.author, context_desc="single burst message")
            else:
                # Multi-message conversation batch!
                transcript_lines = []
                for msg in relevant_msgs:
                    s_name = getattr(msg.author, "display_name", msg.author.name)
                    c_clean = msg.content.replace(f"<@{client.user.id}>", "").replace(f"<@!{client.user.id}>", "").strip()
                    transcript_lines.append(f"@{s_name}: \"{c_clean}\"")

                transcript_str = "\n".join(transcript_lines)
                participants_str = ", ".join([f"@{name}" for name in session.participants.values()])

                prompt_batch = (
                    f"[DISCORD CONVERSATION BATCH in {getattr(channel, 'name', 'chat')}]:\n"
                    f"The following messages occurred in the active conversation thread within {int(session.window_seconds)} seconds:\n"
                    f"{transcript_str}\n\n"
                    f"[RELEVANCE DIRECTIVE]:\n"
                    f"- You are responding to the ongoing discussion involving: {participants_str}.\n"
                    f"- Acknowledge and react to what everyone in the conversation said together in ONE lively, cohesive in-character response!\n"
                    f"- Address the participants naturally by their names.\n"
                    f"- DO NOT repeat each message back line-by-line; synthesize the conversation naturally in character as Yuna."
                )

                primary_msg = relevant_msgs[-1]
                primary_user_name = getattr(primary_msg.author, "display_name", primary_msg.author.name)
                primary_user_id = str(primary_msg.author.id)

                async with channel.typing():
                    try:
                        reply = await query_yuna_brain(
                            prompt=prompt_batch,
                            user_name=primary_user_name,
                            user_id=primary_user_id,
                            channel_id=str(channel_id),
                            author=primary_msg.author
                        )
                        if reply:
                            sent_msgs = await deliver_burst_messages(channel, reply, reply_to_msg=primary_msg)
                            ch_title = "DM" if isinstance(channel, (discord.DMChannel, discord.GroupChannel)) else f"#{getattr(channel, 'name', 'chat')}"
                            print(f"[YUNA BURST FINISHED] Cohesively replied to {len(relevant_msgs)} in-context messages from {len(session.participants)} users in {ch_title}")
                    except Exception as b_err:
                        await feature_evaluator.handle_crash_or_error(b_err, channel, client, author=primary_msg.author, context_desc="batch burst message")

            # 4. Record sent messages into session tracking and REOPEN RIGHT AWAY
            session.update_after_reply(sent_msgs)
            ch_title = "DM" if isinstance(channel, (discord.DMChannel, discord.GroupChannel)) else f"#{getattr(channel, 'name', 'chat')}"
            print(f"[YUNA BURST REOPENED] Context window reopened ({session.window_seconds}s) in {ch_title} waiting for responses...")

    except Exception as e:
        print(f"[YUNA BURST WINDOW ERROR] {e}")
    finally:
        active_burst_sessions.pop(channel_id, None)

# ─────────────────────────────────────────────────────────────
# REAL-TIME MUSIC SELF-AWARENESS & INTERACTIVE CONTROLS
# ─────────────────────────────────────────────────────────────
async def handle_music_interaction(message: discord.Message) -> bool:
    """
    Handles music commands and natural music inquiries on the real account:
    - y!play <song> / y!listen <song> / "yuna play <song>" / "put on <song>"
    - y!song / y!np / y!nowplaying / "what are you listening to" / "what song is that"
    - y!skip / "yuna skip"
    - y!playlist / "what's your playlist"
    Returns True if handled, False otherwise.
    """
    if not yuna_rpc:
        return False

    raw_text = message.content.strip()
    is_dm = isinstance(message.channel, (discord.DMChannel, discord.GroupChannel))
    is_mentioned = (client.user in message.mentions) or (f"<@{client.user.id}>" in raw_text) or (f"<@!{client.user.id}>" in raw_text)
    bot_names = ["yuna", "yunaa", "krenix", "krenixhensler"]
    if client.user and client.user.name:
        bot_names.append(client.user.name.lower())
    bot_pattern = r'\b(' + '|'.join(re.escape(n) for n in set(bot_names)) + r')\b'
    is_name_called = bool(re.search(bot_pattern, raw_text, re.IGNORECASE))

    # Only process if in DM, pinged/called, or explicitly using y! or ! prefix
    is_y_prefix = raw_text.startswith("y!") or raw_text.startswith("!play") or raw_text.startswith("!song")
    if not (is_dm or is_mentioned or is_name_called or is_y_prefix):
        return False

    clean_text = raw_text
    for n in bot_names:
        clean_text = re.sub(rf'\b{re.escape(n)}\b', '', clean_text, flags=re.IGNORECASE)
    clean_text = clean_text.replace(f"<@{client.user.id}>", "").replace(f"<@!{client.user.id}>", "").strip()
    lower_text = clean_text.lower().strip()

    author_name = getattr(message.author, "display_name", message.author.name)

    # 1. PLAY COMMAND: y!play <song> or "play <song>", "put on <song>", "listen to <song>"
    play_match = re.match(r'^(?:y!play|!play|y!listen|\b(?:play|put on|listen to)\b)\s+(.+)$', clean_text, re.IGNORECASE)
    if play_match:
        query = play_match.group(1).strip()
        # Avoid non-music false positives like "play with me" or "play showdown"
        if query and not any(w in query.lower() for w in ["with me", "minecraft", "showdown", "blackjack", "coinflip", "higherlower", "game"]):
            print(f"[YUNA USER MUSIC] Received play request for '{query}' from @{author_name}")
            async with message.channel.typing():
                try:
                    ok, track, msg = await yuna_rpc.set_custom_track(query, requested_by=author_name)
                    if ok and track:
                        activity = yuna_rpc.build_discord_activity(track)
                        await client.change_presence(status=discord.Status.online, activity=activity)
                        t_name = track.get("title", query)
                        t_artist = track.get("artist", "Unknown Artist")
                        dur_bar = yuna_rpc.get_progress_bar(track)
                        replies = [
                            f"*slides on headphones with a smirk* Fine! Putting on **{t_name}** by **{t_artist}** just for you~ 🎧 Look at my status, it's playing on Spotify right now!\n{dur_bar}",
                            f"*taps foot to the rhythm* Ooh, good choice! Now playing **{t_name}** by **{t_artist}**~ ✨ Check my profile, Spotify RPC is synced!\n{dur_bar}",
                            f"*turns up the volume* Putting on **{t_name}** by **{t_artist}**! Hope your music taste isn't terrible~ 🎶\n{dur_bar}"
                        ]
                        await message.reply(random.choice(replies), mention_author=False)
                        return True
                    else:
                        await message.reply(f"*pouts* Couldn't find that song '{query}' on Apple Music or Deezer! Give me a real song name, dummy~", mention_author=False)
                        return True
                except Exception as p_err:
                    print(f"[YUNA USER MUSIC ERROR] {p_err}")
                    return False

    # 2. NOW PLAYING: y!song / y!np / !song / "what are you listening to" / "what song is that"
    is_np = lower_text in ("y!song", "y!np", "!song", "!np", "y!nowplaying", "y!music") or bool(
        re.search(r'\b(what(\'s| is)? (that|this|the) song|what are you listening to|what music are you listening to|what song is playing|what\'s playing|current song)\b', lower_text)
    )
    if is_np:
        print(f"[YUNA USER MUSIC] Received now-playing query from @{author_name}")
        async with message.channel.typing():
            try:
                track = await yuna_rpc.get_or_update_track()
                if track:
                    t_name = track.get("title", "Unknown Track")
                    t_artist = track.get("artist", "Unknown Artist")
                    t_album = track.get("album", "Single")
                    bar = yuna_rpc.get_progress_bar(track)
                    url = track.get("track_url", "")
                    link_str = f"\n🔗 [Listen along]({url})" if url else ""
                    resp = (
                        f"🎧 **Now Playing on my Spotify:**\n"
                        f"**{t_name}** — *{t_artist}* ({t_album})\n"
                        f"{bar}{link_str}\n\n"
                        f"*Wearing my headphones jamming to this banger right now! Type `y!play <song>` if you want me to put on something else~*"
                    )
                    await message.reply(resp, mention_author=False)
                    return True
            except Exception as np_err:
                print(f"[YUNA USER MUSIC ERROR] {np_err}")
                return False

    # 3. SKIP COMMAND: y!skip / !skip / "skip song"
    is_skip = lower_text in ("y!skip", "!skip", "y!next") or bool(re.search(r'\b(?:skip(\s+this)?(\s+song)?|next song)\b', lower_text))
    if is_skip:
        print(f"[YUNA USER MUSIC] Received skip request from @{author_name}")
        async with message.channel.typing():
            try:
                track = await yuna_rpc.get_or_update_track(force_next=True)
                if track:
                    activity = yuna_rpc.build_discord_activity(track)
                    await client.change_presence(status=discord.Status.online, activity=activity)
                    t_name = track.get("title", "Unknown Track")
                    t_artist = track.get("artist", "Unknown Artist")
                    dur_bar = yuna_rpc.get_progress_bar(track)
                    await message.reply(f"*clicks next track* Skipped! Now playing **{t_name}** by **{t_artist}**~ 🎧\n{dur_bar}", mention_author=False)
                    return True
            except Exception as sk_err:
                print(f"[YUNA USER MUSIC ERROR] {sk_err}")
                return False

    # 4. PLAYLIST COMMAND: y!playlist / !playlist / "show playlist"
    is_playlist = lower_text in ("y!playlist", "!playlist", "y!queue") or bool(re.search(r'\b(show|what(\'s| is)?)\s+(your\s+)?(playlist|queue)\b', lower_text))
    if is_playlist:
        print(f"[YUNA USER MUSIC] Received playlist request from @{author_name}")
        preview = yuna_rpc.DEFAULT_PLAYLIST[:8]
        lines = [f"• {song}" for song in preview]
        msg = (
            f"🎶 **Yuna's Favorite Rotation (Vocaloid / J-Pop / Banger Beats):**\n" +
            "\n".join(lines) +
            f"\n\n*Type `y!play <song>` anytime to put on whatever you want!*"
        )
        await message.reply(msg, mention_author=False)
        return True

    return False

@client.event
async def on_message(message: discord.Message):
    # Ignore own messages
    if message.author.id == client.user.id:
        return

    # Ignore system messages or bots
    if message.author.bot:
        return

    raw_text = message.content.strip()
    if not raw_text:
        return

    is_dm = isinstance(message.channel, (discord.DMChannel, discord.GroupChannel))
    channel_id = message.channel.id
    cfg = load_config()

    # ─────────────────────────────────────────────────────────────
    # 1. AUTO-JOIN DISCORD SERVER VIA DM INVITE LINK
    # ─────────────────────────────────────────────────────────────
    if is_dm and cfg.get("auto_join_servers", True):
        invite_match = INVITE_REGEX.search(raw_text)
        if invite_match:
            invite_code = invite_match.group(1)
            print(f"[YUNA SERVER INVITE] Detected invite code '{invite_code}' in DM from @{message.author.name}")
            try:
                invite = await client.accept_invite(invite_code)
                guild_name = getattr(invite, "guild", None)
                g_title = guild_name.name if guild_name else invite_code
                print(f"[YUNA SERVER JOINED] Successfully joined server: {g_title} (code: {invite_code})")
                await message.reply(f"*smirks and flips hair* I just joined your server ({g_title})! Hope it's not boring in there~ <a:s_omori:1202140066219294763>")
                return
            except Exception as inv_err:
                print(f"[YUNA SERVER JOIN FAILED] {inv_err}")
                await message.reply(f"Ugh, couldn't join with that invite ({inv_err}). Is it expired or invalid?")
                return

    # ─────────────────────────────────────────────────────────────
    # 2. OWNER ESCALATION RESPONSE IN DM
    # ─────────────────────────────────────────────────────────────
    if is_dm:
        esc = await owner_escalation.check_and_handle_owner_reply(message, client)
        if esc:
            return

    # ─────────────────────────────────────────────────────────────
    # 2.5 REAL-TIME MUSIC INTERACTION (COMMANDS & INQUIRIES)
    # ─────────────────────────────────────────────────────────────
    handled_music = await handle_music_interaction(message)
    if handled_music:
        return

    # ─────────────────────────────────────────────────────────────
    # 3. CONVERSATIONAL BURST WINDOW & CONTEXT RELEVANCE FILTER
    # ─────────────────────────────────────────────────────────────
    is_mentioned = (client.user in message.mentions) or (f"<@{client.user.id}>" in raw_text) or (f"<@!{client.user.id}>" in raw_text)
    bot_names = ["yuna", "yunaa", "krenix", "krenixhensler"]
    if client.user and client.user.name:
        bot_names.append(client.user.name.lower())
    bot_pattern = r'\b(' + '|'.join(re.escape(n) for n in set(bot_names)) + r')\b'
    is_name_called = bool(re.search(bot_pattern, raw_text, re.IGNORECASE))

    # Check if a burst window is currently active for this channel/DM
    session = active_burst_sessions.get(channel_id)

    if session is not None:
        # A burst window is already running!
        in_context = False

        # In DMs, all messages from the chat partner are automatically in-context
        if is_dm:
            in_context = True

        # Criterion A: Explicitly mentions Yuna or calls her name
        elif is_mentioned or is_name_called:
            in_context = True

        # Criterion B: Replying to any message in the current burst batch or any of Yuna's messages
        elif message.reference and (message.reference.message_id in session.message_ids or message.reference.message_id in session.bot_message_ids):
            in_context = True

        # Criterion C: Mentions any previous participant in the thread
        elif any(p_id in [u.id for u in message.mentions] for p_id in session.participants.keys()):
            in_context = True

        # Criterion D: From an existing participant in the active conversation
        elif message.author.id in session.participants:
            in_context = True

        # Criterion E: Uses contextual pronouns/continuity towards the topic (including music)
        elif re.search(r'\b(she|her|shes|she\'s|smarter|better|genius|idiot|true|agreed|nah|nope|fr|cap|why|what|how|wait|lol|lmao|haha|yeah|yes|no|music|song|track|spotify|listen|listening|banger|earbuds|headphones|playlist|album|artist)\b', raw_text, re.IGNORECASE):
            in_context = True

        if in_context:
            session.record_incoming_message(message)
            print(f"[YUNA BURST BUFFER] Added in-context message from @{message.author.display_name}: '{raw_text[:50]}'")
        else:
            print(f"[YUNA BURST FILTER] Ignored off-topic message from @{message.author.display_name}: '{raw_text[:50]}'")

    else:
        # No active burst window yet. Open one if:
        # 1) It's a DM, OR
        # 2) Yuna is pinged or her name is called in a server channel, OR
        # 3) Direct music question towards Yuna
        is_music_query = bool(re.search(r'\b(music|song|spotify|listening|listen|playlist)\b', raw_text, re.IGNORECASE)) and is_name_called
        if is_dm or is_mentioned or is_name_called or is_music_query:
            burst_sec = float(cfg.get("burst_window_seconds", 12.0))
            # Clamp between 10.0 and 15.0 seconds strictly as requested
            burst_sec = max(10.0, min(15.0, burst_sec))
            new_session = BurstSession(channel_id, message, window_seconds=burst_sec)
            active_burst_sessions[channel_id] = new_session
            loc_name = "DM" if is_dm else f"#{getattr(message.channel, 'name', 'chat')}"
            print(f"\n[YUNA BURST WINDOW OPENED] In {loc_name} by @{message.author.display_name} (Window: {burst_sec}s): '{raw_text[:60]}'")

            # Launch the continuous loop task
            new_session.task = asyncio.create_task(handle_burst_window_completion(new_session))

if __name__ == "__main__":
    pid_dir = BASE_DIR / "memories" / "pids"
    pid_dir.mkdir(parents=True, exist_ok=True)
    pid_file = pid_dir / "user_worker.pid"
    pid_file.write_text(str(os.getpid()))
    try:
        client.run(USER_TOKEN)
    except Exception as e:
        print(f"[YUNA USER CRASH] {e}")
    finally:
        try:
            if pid_file.exists():
                pid_file.unlink(missing_ok=True)
        except Exception:
            pass
