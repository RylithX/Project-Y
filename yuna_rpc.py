"""
Yuna Rich Presence (RPC) & Music Engine
---------------------------------------
Enables Yuna to show rich "Listening to Spotify" status on Discord
with real track titles, artists, albums, accurate progress timestamps,
and cover art resolved via the Kizzy API (Discord Media Proxy assets).
"""

import os
import time
import json
import random
import asyncio
import urllib.parse
from typing import Optional, Dict, Any, Tuple, List
import aiohttp
import discord

# ─── CONFIGURATION & ENDPOINTS ────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, "data", "kizzy_rpc_cache.json")
STATE_FILE = os.path.join(BASE_DIR, "data", "yuna_rpc_state.json")

KIZZY_API_URL = "https://kizzy-api.cjjdxhdjd.workers.dev/image?url="
KIZZY_APP_ID = 962990036020756480  # Default Kizzy Discord Application ID
SPOTIFY_ICON_ASSET = "mp:external/bG4t1QWm70RBsJvXC9pvKNL3kz6vZ2Entu2nYLwP-g8/https/upload.wikimedia.org/wikipedia/commons/thumb/1/19/Spotify_logo_without_text.svg/500px-Spotify_logo_without_text.svg.png"
PLAY_ICON_ASSET = "app-assets/962990036020756480/1300361266212241430.png"

# Default Curated Playlist specifically matching Yuna's aesthetic (Vocaloid / J-Pop / Alt-Pop)
DEFAULT_PLAYLIST: List[str] = [
    "Darling Dance Kairiki Bear",
    "Venom Kairiki Bear",
    "Telecaster B-Boy Surii",
    "Mind Brand dj-Jo",
    "Vampire DECO*27",
    "King Kanaria",
    "Envy Baby Kanaria",
    "Usseewa Ado",
    "Odo Ado",
    "Show Ado",
    "Gira Gira Ado",
    "Idol YOASOBI",
    "Racing Into The Night YOASOBI",
    "Monster YOASOBI",
    "Kaikai Kitan Eve",
    "Dramaturgy Eve",
    "Lagtrain inabakumori",
    "Lost Umbrella inabakumori",
    "God-ish PinocchioP",
    "Anonymous M PinocchioP",
    "Kawaikute Gomen HoneyWorks",
    "Aishite Aishite Aishite Kikuo",
    "Shikabanenet Jon-YAKITORY",
    "Rolling Girl wowaka",
    "Unknown Mother-Goose wowaka",
    "Shinunoga E-Wa Fujii Kaze",
    "Matsuri Fujii Kaze",
    "Bling-Bang-Bang-Born Creepy Nuts",
    "Lovers Rock TV Girl",
    "Notion The Rare Occasions",
    "My Love Mine All Mine Mitski",
    "From The Start Laufey",
    "Specialz King Gnu",
    "Overdose Natori",
    "CH4NGE Giga",
    "BUG Kairiki Bear",
    "Girl A Shiina Mota",
]

# ─── IN-MEMORY STATE & CACHE ──────────────────────────────────────────────────
_kizzy_cache: Dict[str, str] = {}
_current_track: Optional[Dict[str, Any]] = None
_user_queue: List[Dict[str, Any]] = []
_playlist_index: int = 0
_lock = asyncio.Lock()

def _load_cache():
    global _kizzy_cache
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                _kizzy_cache = json.load(f)
    except Exception as e:
        print(f"[YUNA RPC] Could not load cache: {e}")
        _kizzy_cache = {}

def _save_cache():
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_kizzy_cache, f, indent=2)
    except Exception as e:
        print(f"[YUNA RPC] Could not save cache: {e}")

def _load_state():
    global _current_track
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                _current_track = data.get("current_track")
    except Exception as e:
        print(f"[YUNA RPC] Could not load state: {e}")

def _save_state():
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"current_track": _current_track}, f, indent=2)
    except Exception as e:
        print(f"[YUNA RPC] Could not save state: {e}")

_load_cache()
_load_state()

# ─── KIZZY API ASSET RESOLVER ─────────────────────────────────────────────────
async def resolve_kizzy_asset(image_url: str) -> Optional[str]:
    """Resolves an external cover art URL into a Discord Media Proxy ('mp:external/...') asset using Kizzy API."""
    if not image_url:
        return None

    if image_url in _kizzy_cache:
        return _kizzy_cache[image_url]

    target_url = image_url.strip()
    kizzy_url = KIZZY_API_URL + urllib.parse.quote(target_url, safe="")

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
            async with session.get(kizzy_url, headers={"User-Agent": "KizzyRPC/1.0.71 (Android)"}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    asset_id = data.get("id")
                    if asset_id and asset_id.startswith("mp:"):
                        _kizzy_cache[image_url] = asset_id
                        _save_cache()
                        return asset_id
    except Exception as e:
        print(f"[YUNA RPC] Kizzy API error for {image_url}: {e}")

    # Fallback to direct mp URL format if Kizzy API was unreachable
    clean_no_proto = target_url.replace("https://", "").replace("http://", "")
    fallback_id = f"mp:external/fallback/https/{clean_no_proto}"
    return fallback_id

# ─── MUSIC SEARCH (iTUNES & DEEZER APIS) ───────────────────────────────────────
async def search_track(query: str) -> Optional[Dict[str, Any]]:
    """Searches iTunes (and Deezer as fallback) for accurate track metadata and cover art."""
    if not query or not query.strip():
        return None

    clean_query = query.strip()
    # 1. Search iTunes API (fastest, high-res 600x600 artwork, accurate duration)
    itunes_url = f"https://itunes.apple.com/search?term={urllib.parse.quote(clean_query)}&entity=song&limit=3"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=6)) as session:
            async with session.get(itunes_url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    results = data.get("results", [])
                    if results:
                        r = results[0]
                        cover_100 = r.get("artworkUrl100", "")
                        cover_600 = cover_100.replace("100x100bb", "600x600bb") if cover_100 else ""
                        duration_ms = int(r.get("trackTimeMillis", 180000))
                        duration_ms = max(45000, min(duration_ms, 600000))

                        return {
                            "title": r.get("trackName", clean_query),
                            "artist": r.get("artistName", "Unknown Artist"),
                            "album": r.get("collectionName", r.get("trackName", "Single")),
                            "cover_url": cover_600,
                            "duration_ms": duration_ms,
                            "track_url": r.get("trackViewUrl", ""),
                            "source": "Apple Music"
                        }
    except Exception as e:
        print(f"[YUNA RPC] iTunes search failed for '{query}': {e}")

    # 2. Fallback to Deezer API
    deezer_url = f"https://api.deezer.com/search?q={urllib.parse.quote(clean_query)}&limit=3"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=6)) as session:
            async with session.get(deezer_url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    items = data.get("data", [])
                    if items:
                        item = items[0]
                        cover_url = item.get("album", {}).get("cover_big", "")
                        duration_ms = int(item.get("duration", 180)) * 1000
                        duration_ms = max(45000, min(duration_ms, 600000))

                        return {
                            "title": item.get("title", clean_query),
                            "artist": item.get("artist", {}).get("name", "Unknown Artist"),
                            "album": item.get("album", {}).get("title", "Single"),
                            "cover_url": cover_url,
                            "duration_ms": duration_ms,
                            "track_url": item.get("link", ""),
                            "source": "Deezer"
                        }
    except Exception as e:
        print(f"[YUNA RPC] Deezer search failed for '{query}': {e}")

    return None

# ─── ROTATION & STATE MANAGEMENT ──────────────────────────────────────────────
async def get_or_update_track(force_next: bool = False) -> Dict[str, Any]:
    """Retrieves current track or naturally advances to the next song if current track finished."""
    global _current_track, _playlist_index, _user_queue
    now = time.time()

    async with _lock:
        is_expired = False
        if _current_track:
            end_t = _current_track.get("end_time", 0)
            if now >= (end_t + 2):  # Finished song
                is_expired = True

        if _current_track and not is_expired and not force_next:
            return _current_track

        # Needs a new song!
        next_query = None
        requested_by = None
        if _user_queue:
            q_item = _user_queue.pop(0)
            next_query = q_item.get("query")
            requested_by = q_item.get("requested_by")
        else:
            if not DEFAULT_PLAYLIST:
                next_query = "Darling Dance Kairiki Bear"
            else:
                _playlist_index = (_playlist_index + 1) % len(DEFAULT_PLAYLIST)
                next_query = DEFAULT_PLAYLIST[_playlist_index]

        raw_info = await search_track(next_query)
        if not raw_info:
            raw_info = {
                "title": "Darling Dance",
                "artist": "Kairiki Bear",
                "album": "Darling Syndrome",
                "cover_url": "https://is1-ssl.mzstatic.com/image/thumb/Music115/v4/c4/bc/88/c4bc8860-a8a3-e662-0702-b4040d4dc4dc/4582109070611.jpg/600x600bb.jpg",
                "duration_ms": 206000,
                "track_url": "https://music.apple.com",
                "source": "Apple Music"
            }

        kizzy_asset = await resolve_kizzy_asset(raw_info["cover_url"])
        duration_sec = raw_info["duration_ms"] / 1000.0

        _current_track = {
            "title": raw_info["title"],
            "artist": raw_info["artist"],
            "album": raw_info["album"],
            "cover_url": raw_info["cover_url"],
            "kizzy_asset": kizzy_asset or SPOTIFY_ICON_ASSET,
            "duration_ms": raw_info["duration_ms"],
            "start_time": now,
            "end_time": now + duration_sec,
            "track_url": raw_info.get("track_url", ""),
            "requested_by": requested_by,
            "source": raw_info.get("source", "Spotify")
        }
        _save_state()
        print(f"[YUNA RPC] Now playing: '{_current_track['title']}' by '{_current_track['artist']}'", flush=True)
        return _current_track

async def set_custom_track(query: str, requested_by: Optional[str] = None) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """Manually commands Yuna to put on a specific song right now."""
    global _current_track
    raw_info = await search_track(query)
    if not raw_info:
        return False, None, f"Could not find any song matching '{query}' on iTunes or Deezer."

    kizzy_asset = await resolve_kizzy_asset(raw_info["cover_url"])
    now = time.time()
    duration_sec = raw_info["duration_ms"] / 1000.0

    async with _lock:
        _current_track = {
            "title": raw_info["title"],
            "artist": raw_info["artist"],
            "album": raw_info["album"],
            "cover_url": raw_info["cover_url"],
            "kizzy_asset": kizzy_asset or SPOTIFY_ICON_ASSET,
            "duration_ms": raw_info["duration_ms"],
            "start_time": now,
            "end_time": now + duration_sec,
            "track_url": raw_info.get("track_url", ""),
            "requested_by": requested_by,
            "source": raw_info.get("source", "Spotify")
        }
        _save_state()

    return True, _current_track, f"Now playing **{raw_info['title']}** by **{raw_info['artist']}**!"

def get_current_track_info() -> Optional[Dict[str, Any]]:
    """Synchronously returns the active playing track info."""
    return _current_track

def get_queue() -> List[Dict[str, Any]]:
    return list(_user_queue)

def queue_track(query: str, requested_by: Optional[str] = None):
    _user_queue.append({"query": query, "requested_by": requested_by})

# ─── DISCORD ACTIVITY BUILDER ─────────────────────────────────────────────────
def build_discord_activity(track: Dict[str, Any]) -> discord.Activity:
    """Builds a rich Discord Activity object with Spotify styling and Kizzy cover art."""
    start_ms = int(track.get("start_time", time.time()) * 1000)
    end_ms = int(track.get("end_time", time.time() + 180) * 1000)

    title = track.get("title", "Music")
    artist = track.get("artist", "Unknown Artist")
    album = track.get("album", "Single")
    kizzy_cover = track.get("kizzy_asset") or SPOTIFY_ICON_ASSET

    assets = {
        "large_image": kizzy_cover,
        "large_text": f"{album[:120]}",
        "small_image": SPOTIFY_ICON_ASSET,
        "small_text": "Spotify"
    }

    timestamps = {
        "start": start_ms,
        "end": end_ms
    }

    return discord.Activity(
        name="Spotify",
        type=discord.ActivityType.listening,
        details=title[:128],
        state=f"{title[:60]} • {artist[:60]}",
        application_id=KIZZY_APP_ID,
        assets=assets,
        timestamps=timestamps
    )

async def get_or_update_activity() -> discord.Activity:
    """Convenience helper to advance track if needed and return current discord.Activity."""
    track = await get_or_update_track()
    return build_discord_activity(track)

# ─── UI & EMBED HELPERS ───────────────────────────────────────────────────────
def format_time(seconds: float) -> str:
    s = max(0, int(seconds))
    m, sec = divmod(s, 60)
    return f"{m}:{sec:02d}"

def get_progress_bar(track: Dict[str, Any], length: int = 14) -> str:
    now = time.time()
    start = track.get("start_time", now)
    end = track.get("end_time", now + 180)
    total = max(1.0, end - start)
    elapsed = min(total, max(0.0, now - start))
    ratio = min(1.0, elapsed / total)

    pos = int(ratio * length)
    bar = ""
    for i in range(length):
        if i == pos:
            bar += "🔘"
        elif i < pos:
            bar += "▬"
        else:
            bar += "─"

    return f"{bar} `[{format_time(elapsed)} / {format_time(total)}]`"

def build_now_playing_embed(track: Dict[str, Any]) -> discord.Embed:
    """Builds a gorgeous Discord embed representing Yuna's active Spotify playback with full cover art."""
    embed = discord.Embed(
        title=f"🎧 {track.get('title', 'Unknown Track')}",
        url=track.get("track_url") or None,
        color=discord.Color.from_rgb(30, 215, 96)  # Spotify Green
    )
    embed.set_author(
        name="Yuna's Spotify • Kizzy RPC",
        icon_url="https://upload.wikimedia.org/wikipedia/commons/thumb/1/19/Spotify_logo_without_text.svg/500px-Spotify_logo_without_text.svg.png"
    )
    
    desc_lines = [
        f"**Artist:** {track.get('artist', 'Unknown')}",
        f"**Album:** {track.get('album', 'Single')}",
        f"**Timeline:** {get_progress_bar(track)}",
    ]
    if track.get("requested_by"):
        desc_lines.append(f"**Requested by:** {track['requested_by']}")
    
    embed.description = "\n".join(desc_lines)
    if track.get("cover_url"):
        embed.set_thumbnail(url=track["cover_url"])
        embed.set_image(url=track["cover_url"])

    embed.set_footer(
        text="Powered by Kizzy API • Type y!play <song> to change songs!"
    )
    return embed
