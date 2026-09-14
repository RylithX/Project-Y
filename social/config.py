"""
Social Media Integrations Configuration
Supports X (Twitter), Instagram, Photon (Spectrum), and Social Media Queue.
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
import json
import os
import urllib.parse

@dataclass
class XConfig:
    enabled: bool = False
    api_key: str = ""
    api_secret: str = ""
    access_token: str = ""
    access_token_secret: str = ""
    bearer_token: str = ""
    client_id: str = ""
    client_secret: str = ""
    auto_reply_mentions: bool = True
    auto_reply_dms: bool = True
    poll_interval_seconds: int = 30
    auto_like_mentions: bool = True
    character_name: str = "Yuna"
    character_personality: str = ""

@dataclass
class InstagramConfig:
    enabled: bool = False
    username: str = ""
    password: str = ""
    session_id: str = ""
    session_file: str = "data/insta_session.json"
    proxy: str = ""
    auto_reply_dms: bool = True
    auto_reply_comments: bool = True
    auto_approve_follow_requests: bool = True
    watch_follower_stories: bool = True
    auto_like_stories: bool = True
    auto_respond_likes: bool = True
    story_check_interval_minutes: int = 15
    poll_interval_seconds: int = 4
    character_name: str = "Yuna"
    character_personality: str = ""
    style: str = "tsundere"
    tone: str = "Tsundere & Playful"
    sass_level: int = 75
    affection_level: int = 50
    chaos_level: int = 65
    energy_level: int = 80
    proactive_reels_enabled: bool = True
    reel_silence_cutoff_hours: float = 12.0
    min_reel_interval_hours: float = 4.0
    max_reel_interval_hours: float = 6.0
    auto_music_notes: bool = True
    auto_post_stories: bool = True
    stories_per_day: int = 3
    note_check_interval_hours: float = 12.0
    story_post_interval_hours: float = 24.0
    example_responses: Dict[str, str] = field(default_factory=lambda: {
        "reel_reaction": "Haha what did I just watch! That was crazy.",
        "text_dm": "Hey! What are you up to today?",
        "note_like": "Saw you liked my note~ 💕",
        "story_like": "Always catching my stories first! 😊",
        "sticker_reaction": "Cute sticker haha"
    })

@dataclass
class PhotonConfig:
    enabled: bool = False
    api_key: str = ""
    endpoint: str = "https://api.photon.codes/v1"
    gateway_url: str = ""
    webhook_secret: str = ""
    app_id: str = ""
    channels: List[str] = field(default_factory=lambda: ["x", "instagram", "discord"])

@dataclass
class MediaQueueConfig:
    debounce_seconds: float = 6.0
    max_batch_size: int = 10
    max_video_duration_sec: int = 720
    simultaneous_limit: int = 1

INSTA_CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "instagram_config.json")

def load_instagram_config(raw_config: Optional[Dict[str, Any]] = None) -> InstagramConfig:
    """
    Loads Instagram config exclusively from data/instagram_config.json,
    environment variables, and explicit insta_* keys.
    NEVER inherits Discord's personality, Discord bot names, or Discord-specific prompt instructions.
    """
    file_cfg = {}
    if os.path.exists(INSTA_CONFIG_FILE):
        try:
            with open(INSTA_CONFIG_FILE, "r", encoding="utf-8") as f:
                file_cfg = json.load(f) or {}
        except Exception as e:
            print(f"[SOCIAL CONFIG] Warning reading {INSTA_CONFIG_FILE}: {e}")

    cfg = raw_config or {}

    default_examples = {
        "reel_reaction": "Haha what did I just watch! That was crazy.",
        "text_dm": "Hey! What are you up to today?",
        "note_like": "Saw you liked my note~ 💕",
        "story_like": "Always catching my stories first! 😊",
        "sticker_reaction": "Cute sticker haha"
    }
    
    custom_examples = file_cfg.get("example_responses") or file_cfg.get("examples") or cfg.get("insta_example_responses") or cfg.get("insta_examples")
    if isinstance(custom_examples, dict):
        merged_examples = {**default_examples, **custom_examples}
    else:
        merged_examples = default_examples

    raw_session = (
        cfg.get("insta_sessionid")
        or cfg.get("insta_session_id")
        or file_cfg.get("session_id")
        or file_cfg.get("sessionid")
        or os.getenv("INSTA_SESSIONID", "")
        or os.getenv("INSTA_SESSION_ID", "")
    )
    clean_session = urllib.parse.unquote(str(raw_session).strip()) if raw_session else ""

    target_username = str(cfg.get("insta_username") or file_cfg.get("username") or os.getenv("INSTA_USERNAME", "") or os.getenv("INSTAGRAM_USERNAME", "ur._.yunaa"))
    default_session_file = f"data/insta_session_{target_username}.json" if target_username and target_username != "ur._.yunaa" else "data/insta_session.json"
    session_file_path = str(cfg.get("insta_session_file") or file_cfg.get("session_file") or default_session_file)

    is_yuna = (target_username == "ur._.yunaa" or (cfg.get("name") or "").lower() == "yuna")

    default_insta_personality = (
        "Yuna is an AI angel and girl who has bpd and darling syndrome. "
        "She acts narcissistic/loving/evil/tsundere with her followers on Instagram, "
        "she is silly, witty, affectionate, and completely unpredictable."
    )

    # Priority: bot's own specific persona first
    bot_pers = cfg.get("insta_personality") or cfg.get("insta_persona") or cfg.get("insta_prompt") or (cfg.get("personality") if not is_yuna else None)
    if bot_pers and str(bot_pers).strip():
        insta_pers = str(bot_pers).strip()
    elif is_yuna:
        insta_pers = str(file_cfg.get("character_personality") or file_cfg.get("personality") or default_insta_personality).strip()
    else:
        insta_pers = str(cfg.get("personality") or f"You are {target_username}, chatting on Instagram.").strip()

    char_name = str(cfg.get("insta_character_name") or cfg.get("name") or (file_cfg.get("character_name") if is_yuna else target_username) or "AI Companion")
    char_style = str(cfg.get("insta_style") or (file_cfg.get("style") if is_yuna else "direct") or "direct")
    char_tone = str(cfg.get("insta_tone") or (file_cfg.get("tone") if is_yuna else "Regal & Calm") or "Regal & Calm")

    def _get_slider(slider_name, yuna_default, non_yuna_default):
        if cfg.get(f"insta_{slider_name}") is not None:
            return int(cfg.get(f"insta_{slider_name}"))
        if is_yuna and file_cfg.get(slider_name) is not None:
            return int(file_cfg.get(slider_name))
        return yuna_default if is_yuna else non_yuna_default

    return InstagramConfig(
        enabled=bool(cfg.get("insta_enabled", file_cfg.get("enabled", True if clean_session else False))),
        username=target_username,
        password=str(cfg.get("insta_password") or (file_cfg.get("password") if is_yuna else "") or os.getenv("INSTA_PASSWORD", "") or os.getenv("INSTAGRAM_PASSWORD", "")),
        session_id=clean_session,
        session_file=session_file_path,
        proxy=str(cfg.get("insta_proxy") or file_cfg.get("proxy", "")),
        auto_reply_dms=bool(cfg.get("insta_auto_reply_dms", file_cfg.get("auto_reply_dms", True))),
        auto_reply_comments=bool(cfg.get("insta_auto_reply_comments", file_cfg.get("auto_reply_comments", True))),
        auto_approve_follow_requests=bool(cfg.get("insta_auto_approve_follow_requests", file_cfg.get("auto_approve_follow_requests", True))),
        watch_follower_stories=bool(cfg.get("insta_watch_follower_stories", file_cfg.get("watch_follower_stories", True))),
        auto_like_stories=bool(cfg.get("insta_auto_like_stories", file_cfg.get("auto_like_stories", True))),
        auto_respond_likes=bool(cfg.get("insta_auto_respond_likes", file_cfg.get("auto_respond_likes", True))),
        story_check_interval_minutes=int(cfg.get("insta_story_check_interval_minutes", file_cfg.get("story_check_interval_minutes", 15))),
        poll_interval_seconds=int(cfg.get("insta_poll_interval_seconds", file_cfg.get("poll_interval_seconds", 4))),
        character_name=char_name,
        character_personality=insta_pers,
        style=char_style,
        tone=char_tone,
        sass_level=_get_slider("sass_level", 75, 20),
        affection_level=_get_slider("affection_level", 50, 40),
        chaos_level=_get_slider("chaos_level", 65, 15),
        energy_level=_get_slider("energy_level", 80, 50),
        proactive_reels_enabled=bool(cfg.get("insta_proactive_reels_enabled", file_cfg.get("proactive_reels_enabled", True))),
        reel_silence_cutoff_hours=float(cfg.get("insta_reel_silence_cutoff_hours", file_cfg.get("reel_silence_cutoff_hours", 12.0))),
        min_reel_interval_hours=float(cfg.get("insta_min_reel_interval_hours", file_cfg.get("min_reel_interval_hours", 4.0))),
        max_reel_interval_hours=float(cfg.get("insta_max_reel_interval_hours", file_cfg.get("max_reel_interval_hours", 6.0))),
        auto_music_notes=bool(cfg.get("insta_auto_music_notes", file_cfg.get("auto_music_notes", True))),
        auto_post_stories=bool(cfg.get("insta_auto_post_stories", file_cfg.get("auto_post_stories", True))),
        stories_per_day=int(cfg.get("insta_stories_per_day", file_cfg.get("stories_per_day", 3))),
        note_check_interval_hours=float(cfg.get("insta_note_check_interval_hours", file_cfg.get("note_check_interval_hours", 12.0))),
        story_post_interval_hours=float(cfg.get("insta_story_post_interval_hours", file_cfg.get("story_post_interval_hours", 24.0))),
        example_responses=merged_examples
    )

def save_instagram_config(insta_cfg_dict: Dict[str, Any]):
    """Persists Instagram settings into data/instagram_config.json."""
    os.makedirs(os.path.dirname(INSTA_CONFIG_FILE), exist_ok=True)
    existing = {}
    if os.path.exists(INSTA_CONFIG_FILE):
        try:
            with open(INSTA_CONFIG_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f) or {}
        except Exception:
            existing = {}
    
    clean_dict = {}
    for k, v in insta_cfg_dict.items():
        clean_k = k[6:] if k.startswith("insta_") else k
        clean_dict[clean_k] = v
        if clean_k in ("personality", "character_personality", "persona", "prompt"):
            clean_dict["character_personality"] = v
            clean_dict["personality"] = v
        
    merged = {**existing, **clean_dict}
    try:
        with open(INSTA_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=2)
        return True
    except Exception as e:
        print(f"[SOCIAL CONFIG] Failed to save {INSTA_CONFIG_FILE}: {e}")
        return False

def load_social_config(raw_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = raw_config or {}
    
    x_cfg = XConfig(
        enabled=bool(cfg.get("x_enabled", False)),
        api_key=str(cfg.get("x_api_key") or os.getenv("X_API_KEY", "") or os.getenv("TWITTER_API_KEY", "")),
        api_secret=str(cfg.get("x_api_secret") or os.getenv("X_API_SECRET", "") or os.getenv("TWITTER_API_SECRET", "")),
        access_token=str(cfg.get("x_access_token") or os.getenv("X_ACCESS_TOKEN", "") or os.getenv("TWITTER_ACCESS_TOKEN", "")),
        access_token_secret=str(cfg.get("x_access_token_secret") or os.getenv("X_ACCESS_TOKEN_SECRET", "") or os.getenv("TWITTER_ACCESS_TOKEN_SECRET", "")),
        bearer_token=str(cfg.get("x_bearer_token") or os.getenv("X_BEARER_TOKEN", "") or os.getenv("TWITTER_BEARER_TOKEN", "")),
        client_id=str(cfg.get("x_client_id") or os.getenv("X_CLIENT_ID", "")),
        client_secret=str(cfg.get("x_client_secret") or os.getenv("X_CLIENT_SECRET", "")),
        auto_reply_mentions=bool(cfg.get("x_auto_reply_mentions", True)),
        auto_reply_dms=bool(cfg.get("x_auto_reply_dms", True)),
        poll_interval_seconds=int(cfg.get("x_poll_interval_seconds", 30)),
        auto_like_mentions=bool(cfg.get("x_auto_like_mentions", True)),
        character_name=str(cfg.get("x_character_name") or cfg.get("name", "Yuna")),
        character_personality=str(cfg.get("x_personality") or cfg.get("personality", ""))
    )

    insta_cfg = load_instagram_config(cfg)

    photon_cfg = PhotonConfig(
        enabled=bool(cfg.get("photon_enabled", False)),
        api_key=str(cfg.get("photon_api_key") or os.getenv("PHOTON_API_KEY", "")),
        endpoint=str(cfg.get("photon_endpoint", "https://api.photon.codes/v1")),
        gateway_url=str(cfg.get("photon_gateway_url", "")),
        webhook_secret=str(cfg.get("photon_webhook_secret", "")),
        app_id=str(cfg.get("photon_app_id", "")),
        channels=list(cfg.get("photon_channels", ["x", "instagram", "discord"]))
    )

    queue_cfg = MediaQueueConfig(
        debounce_seconds=float(cfg.get("social_media_queue_debounce_sec", 6.0)),
        max_batch_size=int(cfg.get("social_media_queue_max_batch", 10)),
        max_video_duration_sec=int(cfg.get("social_media_queue_max_duration", 720)),
        simultaneous_limit=int(cfg.get("social_media_queue_simultaneous", 1))
    )

    return {
        "x": x_cfg,
        "instagram": insta_cfg,
        "photon": photon_cfg,
        "queue": queue_cfg
    }
