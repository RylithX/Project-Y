"""
Comprehensive Instagram Integration Engine.
Features:
- Post creation (Photos, Videos, Reels, Carousels, Stories) with AI Captions
- Direct Message (DM) Watching: When a user sends a video/reel/clip in DMs,
  Yuna watches, hears, and analyzes it, then sends an in-character reaction.
- Follower Story Viewer: Automatically watches stories of followers and logs memories.
- Auto-Approve Follow Requests: Automatically accepts incoming follow requests.
- Comment Reading and Replying
- Instagrapi + Native Web/REST Session Engine
"""

import asyncio
import io
import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple, Union, Callable

import aiohttp

try:
    from PIL import Image
    HAVE_PIL = True
except Exception:
    Image = None
    HAVE_PIL = False

from .config import InstagramConfig

logger = logging.getLogger("Social.InstagramClient")

try:
    from instagrapi import Client as InstagrapiClient
    from instagrapi.exceptions import LoginRequired, ChallengeRequired
    import logging as _logging
    for _noisy_name in ['private_request', 'public_request', 'instagrapi', 'urllib3', 'requests', 'instaloader']:
        _nl = _logging.getLogger(_noisy_name)
        _nl.setLevel(_logging.CRITICAL)
        _nl.disabled = True
        _nl.propagate = False
    HAVE_INSTAGRAPI = True
except Exception:
    InstagrapiClient = None
    LoginRequired = Exception
    ChallengeRequired = Exception
    HAVE_INSTAGRAPI = False

PROCESSED_DMS_FILE = Path("/storage/emulated/0/discord-bot/data/insta_processed_dms.json")
LIKE_COOLDOWNS_FILE = Path("/storage/emulated/0/discord-bot/data/insta_like_cooldowns.json")
REEL_SHARING_FILE = Path("/storage/emulated/0/discord-bot/data/insta_reel_sharing.json")
NOTES_STATE_FILE = Path("/storage/emulated/0/discord-bot/data/insta_notes_state.json")
STORIES_STATE_FILE = Path("/storage/emulated/0/discord-bot/data/insta_stories_state.json")

class InstagramClient:
    """
    Full Instagram Client for Bot Social Management.
    """

    def __init__(self, config: InstagramConfig):
        self.config = config
        self.client = None
        self.is_logged_in = False
        self.user_id: Optional[str] = None
        self.username: Optional[str] = None
        self.last_checked_dms: float = 0.0
        self.last_story_check: float = 0.0
        self.processed_dm_item_ids: set = set()
        self.like_cooldowns: Dict[str, float] = {}
        self.reel_sharing_state: Dict[str, Any] = {"last_shared": {}, "shared_codes": [], "cached_reels": []}
        self.notes_state: Dict[str, Any] = {"last_note_time": 0.0, "text": "", "track": "", "artist": ""}
        self.stories_state: Dict[str, Any] = {"last_story_post_time": 0.0, "posted_stories": []}
        self.viewed_story_pk_ids: set = set()
        self._initial_likes_seeded: bool = False
        self._login_lock = asyncio.Lock()
        self._login_blocked_until: float = 0.0
        self._load_processed_dms()
        self._load_like_cooldowns()
        self._load_reel_sharing_state()
        self._load_notes_state()
        self._load_stories_state()

    def _load_notes_state(self):
        """Loads persistent Instagram notes state from disk."""
        if NOTES_STATE_FILE.exists():
            try:
                with open(NOTES_STATE_FILE, "r", encoding="utf-8") as f:
                    self.notes_state = json.load(f) or {}
            except Exception as e:
                logger.error(f"[INSTA CLIENT] Error loading {NOTES_STATE_FILE}: {e}")
                self.notes_state = {"last_note_time": 0.0, "text": "", "track": "", "artist": ""}
        else:
            self.notes_state = {"last_note_time": 0.0, "text": "", "track": "", "artist": ""}

    def _save_notes_state(self, data: Optional[Dict[str, Any]] = None):
        """Persists notes state to disk."""
        try:
            if data:
                self.notes_state.update(data)
            NOTES_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(NOTES_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.notes_state, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"[INSTA CLIENT] Error saving {NOTES_STATE_FILE}: {e}")

    def _load_stories_state(self):
        """Loads persistent Instagram stories state from disk."""
        if STORIES_STATE_FILE.exists():
            try:
                with open(STORIES_STATE_FILE, "r", encoding="utf-8") as f:
                    self.stories_state = json.load(f) or {}
            except Exception as e:
                logger.error(f"[INSTA CLIENT] Error loading {STORIES_STATE_FILE}: {e}")
                self.stories_state = {"last_story_post_time": 0.0, "posted_stories": []}
        else:
            self.stories_state = {"last_story_post_time": 0.0, "posted_stories": []}

    def _save_stories_state(self, data: Optional[Dict[str, Any]] = None):
        """Persists stories state to disk."""
        try:
            if data:
                self.stories_state.update(data)
            STORIES_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(STORIES_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.stories_state, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"[INSTA CLIENT] Error saving {STORIES_STATE_FILE}: {e}")

    def _load_reel_sharing_state(self):
        """Loads persistent reel sharing state from disk."""
        if REEL_SHARING_FILE.exists():
            try:
                with open(REEL_SHARING_FILE, "r", encoding="utf-8") as f:
                    self.reel_sharing_state = json.load(f) or {}
            except Exception as e:
                logger.error(f"[INSTA CLIENT] Error loading {REEL_SHARING_FILE}: {e}")
                self.reel_sharing_state = {"last_shared": {}, "shared_codes": [], "cached_reels": []}
        else:
            self.reel_sharing_state = {"last_shared": {}, "shared_codes": [], "cached_reels": []}

    def _save_reel_sharing_state(self):
        """Persists reel sharing state to disk."""
        try:
            REEL_SHARING_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(REEL_SHARING_FILE, "w", encoding="utf-8") as f:
                json.dump(self.reel_sharing_state, f, indent=2)
        except Exception as e:
            logger.error(f"[INSTA CLIENT] Error saving {REEL_SHARING_FILE}: {e}")

    def _load_like_cooldowns(self):
        """Loads follower like reaction timestamps to enforce a 12-hour per-user cooldown."""
        if LIKE_COOLDOWNS_FILE.exists():
            try:
                with open(LIKE_COOLDOWNS_FILE, "r", encoding="utf-8") as f:
                    self.like_cooldowns = json.load(f) or {}
            except Exception as e:
                logger.error(f"[INSTA CLIENT] Error loading {LIKE_COOLDOWNS_FILE}: {e}")
                self.like_cooldowns = {}
        else:
            self.like_cooldowns = {}

    def _save_like_cooldowns(self):
        """Persists like reaction timestamps to disk."""
        try:
            LIKE_COOLDOWNS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(LIKE_COOLDOWNS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.like_cooldowns, f)
        except Exception as e:
            logger.error(f"[INSTA CLIENT] Error saving {LIKE_COOLDOWNS_FILE}: {e}")

    def can_send_like_dm(self, user_id: str, cooldown_hours: float = 12.0) -> bool:
        """Ensures a user never receives more than 1 like reaction DM within cooldown period."""
        if not user_id:
            return False
        last_t = self.like_cooldowns.get(str(user_id), 0.0)
        return (time.time() - last_t) >= (cooldown_hours * 3600.0)

    def record_like_dm_sent(self, user_id: str):
        """Records timestamp of sent like reaction DM."""
        if user_id:
            self.like_cooldowns[str(user_id)] = time.time()
            self._save_like_cooldowns()

    def _get_processed_dms_file(self) -> Path:
        u = getattr(self, "username", "") or (self.config.username if hasattr(self, "config") else "")
        if u and u != "ur._.yunaa":
            return Path(f"/storage/emulated/0/discord-bot/data/insta_processed_dms_{u}.json")
        return PROCESSED_DMS_FILE

    def _load_processed_dms(self):
        """Loads persistent set of processed DM item IDs from disk."""
        target_file = self._get_processed_dms_file()
        if target_file.exists():
            try:
                with open(target_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.processed_dm_item_ids = set(data) if isinstance(data, list) else set()
                logger.info(f"[INSTA CLIENT] Loaded {len(self.processed_dm_item_ids)} processed DM IDs from disk ({target_file.name}).")
            except Exception as e:
                logger.error(f"[INSTA CLIENT] Error loading {target_file}: {e}")
                self.processed_dm_item_ids = set()
        else:
            self.processed_dm_item_ids = set()

    def _save_processed_dms(self):
        """Persists processed DM item IDs to disk, capped at 5000 IDs."""
        try:
            target_file = self._get_processed_dms_file()
            target_file.parent.mkdir(parents=True, exist_ok=True)
            # Keep up to 5000 recent IDs
            id_list = list(self.processed_dm_item_ids)[-5000:]
            with open(target_file, "w", encoding="utf-8") as f:
                json.dump(id_list, f)
        except Exception as e:
            logger.error(f"[INSTA CLIENT] Error saving {self._get_processed_dms_file()}: {e}")

    def mark_dm_processed(self, msg_id: str):
        """Marks a message ID as processed and saves to disk."""
        if msg_id:
            self.processed_dm_item_ids.add(str(msg_id))
            self._save_processed_dms()

    def is_dm_processed(self, msg_id: str) -> bool:
        """Checks if a message ID has already been processed."""
        return str(msg_id) in self.processed_dm_item_ids

    def is_configured(self) -> bool:
        return bool(self.config.username and self.config.password) or os.path.exists(self.config.session_file)

    async def login(self) -> Tuple[bool, str]:
        """Authenticates with Instagram via cached session or credentials with rate-limit protection."""
        if self.is_logged_in and self.client:
            return True, f"Already logged in as @{self.username}"

        if time.time() < self._login_blocked_until:
            rem = int(self._login_blocked_until - time.time())
            return False, f"Instagram login cooling down after rate limit (retry in {rem}s)"

        if not self.is_configured():
            return False, "Instagram credentials or session file not configured."

        if not HAVE_INSTAGRAPI:
            self.username = self.config.username
            self.is_logged_in = True
            logger.info("[INSTA CLIENT] Running in native Instagram session mode.")
            return True, f"Native session initialized for {self.config.username}."

        async with self._login_lock:
            if self.is_logged_in and self.client:
                return True, f"Already logged in as @{self.username}"

            try:
                def _do_login():
                    cl = InstagrapiClient()
                    cl.expose = lambda *args, **kwargs: {}
                    if hasattr(cl, "private_request_logger"):
                        cl.private_request_logger.setLevel(_logging.CRITICAL)
                        cl.private_request_logger.disabled = True
                        cl.private_request_logger.propagate = False
                    if hasattr(cl, "logger"):
                        cl.logger.setLevel(_logging.CRITICAL)
                        cl.logger.disabled = True
                        cl.logger.propagate = False
                    if self.config.proxy:
                        cl.set_proxy(self.config.proxy)

                    # 1. First, attempt to load and validate cached session (zero credential hits)
                    session_path = Path(self.config.session_file)
                    session_loaded = False
                    if session_path.exists():
                        try:
                            cl.load_settings(session_path)
                            cl.get_timeline_feed()
                            session_loaded = True
                            logger.info(f"[INSTA CLIENT] Successfully restored active session from {session_path}")
                        except Exception as se:
                            err_str = str(se).lower()
                            if "429" in err_str or "throttled" in err_str or "too many requests" in err_str:
                                raise se
                            logger.info(f"[INSTA CLIENT] Saved session expired or invalid ({se}), attempting re-login...")
                            session_loaded = False

                    # 2. Only if cached session failed, authenticate with session_id or credentials
                    if not session_loaded:
                        logged = False
                        last_err = None
                        if self.config.session_id:
                            try:
                                import urllib.parse
                                raw_sid = urllib.parse.unquote(str(self.config.session_id).strip())
                                cl.login_by_sessionid(raw_sid)
                                logged = True
                            except Exception as se:
                                last_err = se
                                logger.warning(f"[INSTA CLIENT] Session ID login failed ({se}), falling back to username/password...")
                        
                        if not logged:
                            if self.config.username and self.config.password:
                                try:
                                    cl.login(self.config.username, self.config.password)
                                    logged = True
                                except Exception as le:
                                    last_err = le
                                    raise le
                            elif last_err:
                                raise last_err
                            else:
                                raise ValueError("No valid session and no credentials provided.")

                        if logged:
                            session_path.parent.mkdir(parents=True, exist_ok=True)
                            cl.dump_settings(session_path)

                    return cl

                self.client = await asyncio.to_thread(_do_login)
                self.user_id = str(self.client.user_id) if hasattr(self.client, "user_id") and self.client.user_id else None
                if not self.user_id and self.config.session_id and ":" in self.config.session_id:
                    self.user_id = self.config.session_id.split(":")[0]
                self.username = self.config.username or getattr(self.client, "username", None) or "ur._.yunaa"
                self.is_logged_in = True
                self._login_blocked_until = 0.0
                logger.info(f"[INSTA CLIENT] Logged in successfully as @{self.username} (ID: {self.user_id})")
                return True, f"Logged in as @{self.username}"
            except Exception as e:
                self.is_logged_in = False
                err_str = str(e).lower()
                if "429" in err_str or "too many requests" in err_str or "please try again" in err_str or "pleasewaitfewminutes" in err_str or "clientthrottlederror" in err_str:
                    self._login_blocked_until = time.time() + 600
                    logger.warning(f"[INSTA CLIENT] Rate-limited by Instagram (Status 429 / Throttled). Cool-down activated for 10 minutes (or change IP/network).")
                elif "challenge" in err_str or "checkpoint" in err_str:
                    self._login_blocked_until = time.time() + 600
                    logger.warning(f"[INSTA CLIENT] Instagram Security Checkpoint / Verification required for @{self.config.username or self.username}. Please verify login on your phone/browser or update INSTA_SESSIONID in .env. Cooling down for 10 minutes.")
                elif "loginrequired" in err_str or "redirect" in err_str or "403" in err_str:
                    self._login_blocked_until = time.time() + 300
                    logger.warning(f"[INSTA CLIENT] Instagram login required / session expired for @{self.config.username or self.username} ({e}). Please update INSTA_SESSIONID in .env or verify credentials. Cooling down for 5 minutes.")
                else:
                    self._login_blocked_until = time.time() + 60
                    logger.error(f"[INSTA CLIENT] Login failed: {e}")
                return False, f"Instagram login error: {e}"

    async def post_photo(self, image_path_or_bytes: Union[str, bytes], caption: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """Posts a photo to the Instagram feed."""
        if not self.is_logged_in:
            ok, msg = await self.login()
            if not ok:
                return False, None, msg

        tmp_path = None
        try:
            if isinstance(image_path_or_bytes, bytes):
                tmp_fd, tmp_path = tempfile.mkstemp(suffix=".jpg")
                os.close(tmp_fd)
                with open(tmp_path, "wb") as f:
                    f.write(image_path_or_bytes)
                target_path = tmp_path
            else:
                target_path = image_path_or_bytes

            if self.client and HAVE_INSTAGRAPI:
                def _do_upload():
                    media = self.client.photo_upload(
                        path=Path(target_path),
                        caption=caption
                    )
                    return media.dict() if hasattr(media, "dict") else {"pk": getattr(media, "pk", str(time.time()))}

                media_dict = await asyncio.to_thread(_do_upload)
                pk = media_dict.get("pk") or media_dict.get("id")
                insta_url = f"https://www.instagram.com/p/{media_dict.get('code', pk)}/" if media_dict.get("code") else f"https://www.instagram.com/"
                return True, media_dict, insta_url
            else:
                return True, {"mock": True}, f"https://www.instagram.com/{self.username}/"
        except Exception as e:
            return False, None, f"Instagram photo upload error: {e}"
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    async def post_video(self, video_path: str, caption: str, is_reel: bool = True) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """Posts a video or reel to Instagram."""
        if not self.is_logged_in:
            ok, msg = await self.login()
            if not ok:
                return False, None, msg

        try:
            if self.client and HAVE_INSTAGRAPI:
                def _do_video_upload():
                    if is_reel:
                        media = self.client.clip_upload(
                            path=Path(video_path),
                            caption=caption
                        )
                    else:
                        media = self.client.video_upload(
                            path=Path(video_path),
                            caption=caption
                        )
                    return media.dict() if hasattr(media, "dict") else {"pk": getattr(media, "pk", str(time.time()))}

                media_dict = await asyncio.to_thread(_do_video_upload)
                pk = media_dict.get("pk") or media_dict.get("id")
                insta_url = f"https://www.instagram.com/reel/{media_dict.get('code', pk)}/" if is_reel and media_dict.get("code") else f"https://www.instagram.com/p/{media_dict.get('code', pk)}/"
                return True, media_dict, insta_url
            else:
                return True, {"mock": True}, f"https://www.instagram.com/{self.username}/"
        except Exception as e:
            return False, None, f"Instagram video upload error: {e}"

    async def auto_approve_follow_requests(self) -> List[Dict[str, Any]]:
        """
        Auto approves pending follow requests on private accounts and pending DMs.
        Returns list of approved users.
        """
        if not self.is_logged_in or not self.client or not HAVE_INSTAGRAPI:
            return []

        approved_list = []
        try:
            def _approve():
                results = []
                # 1. Approve follow requests + follow back newly approved users
                try:
                    if hasattr(self.client, "user_follow_requests"):
                        pending = self.client.user_follow_requests() or []
                        for user in pending:
                            try:
                                u_id = user.pk if hasattr(user, "pk") else user.get("pk")
                                u_name = user.username if hasattr(user, "username") else user.get("username")
                                if hasattr(self.client, "user_follow_request_approve"):
                                    self.client.user_follow_request_approve(u_id)
                                    logger.info(f"[INSTA FOLLOW APPROVAL] Approved follow request from @{u_name} (ID: {u_id})")
                                # Follow back the approved user
                                if hasattr(self.client, "user_follow"):
                                    try:
                                        self.client.user_follow(u_id)
                                        logger.info(f"[INSTA FOLLOW APPROVAL] Followed back @{u_name} (ID: {u_id})")
                                    except Exception:
                                        pass
                                results.append({"user_id": str(u_id), "username": u_name})
                            except Exception as ae:
                                logger.warning(f"[INSTA FOLLOW APPROVAL] Failed to approve user {user}: {ae}")
                except Exception as fe:
                    if "429" in str(fe) or "Too many requests" in str(fe):
                        logger.warning(f"[INSTA FOLLOW APPROVAL] Instagram rate limited (429): {fe}")
                    else:
                        logger.debug(f"[INSTA FOLLOW APPROVAL] Follow request check note: {fe}")

                # 2. Pending DM requests
                try:
                    if hasattr(self.client, "direct_pending_inbox"):
                        pending_threads = self.client.direct_pending_inbox(amount=10) or []
                        for th in pending_threads:
                            try:
                                th_id = th.id if hasattr(th, "id") else th.get("id")
                                if hasattr(self.client, "direct_pending_approve"):
                                    self.client.direct_pending_approve(th_id)
                                    logger.info(f"[INSTA DM APPROVAL] Approved pending DM request for thread {th_id}")
                            except Exception as de:
                                logger.debug(f"[INSTA DM APPROVAL] DM approval note: {de}")
                except Exception as pe:
                    if "429" in str(pe) or "Too many requests" in str(pe):
                        logger.warning(f"[INSTA DM APPROVAL] Pending inbox rate limited (429): {pe}")
                    else:
                        logger.debug(f"[INSTA DM APPROVAL] Pending inbox note: {pe}")

                return results

            approved_list = await asyncio.to_thread(_approve)
        except Exception as e:
            logger.error(f"[INSTA FOLLOW APPROVAL] Error checking pending requests: {e}")
        return approved_list

    def build_system_prompt(self, user_name: str = "follower") -> str:
        """
        Builds dynamic, character-authentic system prompt for Instagram interactions.
        Dynamically applies actionable behavioral directives for Sass, Affection, Chaos, and Energy sliders.
        """
        cfg = self.config

        name = getattr(cfg, "character_name", "") or getattr(cfg, "name", "") or getattr(cfg, "username", "") or "AI Companion"
        base_personality = getattr(cfg, "character_personality", "") or getattr(cfg, "personality", "") or f"You are {name}."
        style = str(getattr(cfg, "style", "direct") or "direct").lower()
        tone = getattr(cfg, "tone", "Conversational") or "Conversational"
        sass = int(getattr(cfg, "sass_level", 40))
        affection = int(getattr(cfg, "affection_level", 50))
        chaos = int(getattr(cfg, "chaos_level", 40))
        energy = int(getattr(cfg, "energy_level", 60))

        # 1. Dynamic Sass Modifier (Roast/Snark control)
        if sass <= 25:
            sass_desc = "Sweet, polite, gentle, and respectful. Zero roasting, no snark, no teasing."
        elif sass <= 60:
            sass_desc = "Lighthearted friendly banter, mild cute teasing, and warm good-natured humor."
        elif sass <= 85:
            sass_desc = "Feisty, sassy, and witty with clever, sarcastic comebacks."
        else:
            sass_desc = "Extremely proud, sassy, haughty, and sharp-witted."

        # 2. Dynamic Affection Modifier (Warmth/Clinginess control)
        if affection <= 25:
            aff_desc = "Cool, reserved, independent, and keeping emotional distance."
        elif affection <= 60:
            aff_desc = "Casual, friendly, supportive, and appreciative of the user."
        elif affection <= 85:
            aff_desc = "Sweet, warm, caring, openly happy to chat, and emotionally expressive."
        else:
            aff_desc = "Extremely loving, clingy, sweet, and deeply affectionate."

        # 3. Dynamic Chaos Modifier (Meme/Absurdity control)
        if chaos <= 25:
            chaos_desc = "Grounded, sensible, straightforward, and realistic in your thoughts."
        elif chaos <= 60:
            chaos_desc = "Lively and fun with a natural sense of humor."
        elif chaos <= 85:
            chaos_desc = "Quirky, unpredictable, meme-heavy, with funny exaggerations."
        else:
            chaos_desc = "Wildly chaotic, absurd, silly, and unpredictable."

        # 4. Dynamic Energy Modifier (Pacing/Vibe control)
        if energy <= 25:
            energy_desc = "Chill, laid-back, relaxed, low-key texting."
        elif energy <= 60:
            energy_desc = "Natural conversational tempo and casual pacing."
        elif energy <= 85:
            energy_desc = "High energy, enthusiastic, upbeat, and expressive."
        else:
            energy_desc = "Hyped, bubbly, fast-paced, and highly expressive!"

        prompt_parts = [
            f"You are {name}, chatting with @{user_name} on Instagram DMs.",
            f"\n[CORE PERSONALITY]\n{base_personality}",
            f"\n[ACTIVE SLIDER BEHAVIOR CONTROLS - STRICTLY FOLLOW THESE LEVELS]:",
            f"• Style & Tone: {tone} ({style})",
            f"• Sass Level ({sass}%): {sass_desc}",
            f"• Affection Level ({affection}%): {aff_desc}",
            f"• Chaos Level ({chaos}%): {chaos_desc}",
            f"• Texting Energy ({energy}%): {energy_desc}",
            f"\n[CONVERSATIONAL DIRECTIVES]:",
            f"1. React directly and authentically to what the user says or shares in the current moment.",
            f"2. Never dwell on old past topics or repeat old jokes unless the user brings them up.",
            f"3. Keep replies punchy, natural, and concise (1-2 sentences like real DMs).",
            f"4. STRICT RULE: Speak purely in direct dialogue. NEVER write physical actions in asterisks (NO *smiles*, *sighs*, *laughs*, *looks*)."
        ]

        return "\n".join(prompt_parts)

    async def watch_follower_stories(
        self,
        auto_like: Optional[bool] = None,
        max_users: int = 25,
        ask_ai_fn: Optional[Callable] = None,
        memory_update_fn: Optional[Callable] = None
    ) -> List[Dict[str, Any]]:
        """
        Watches stories of followers / timeline, marks them as seen,
        auto-likes them if configured, and records follower story notes into AI memory.
        """
        if not self.is_logged_in:
            await self.login()
            if not self.is_logged_in:
                return []

        seen_stories = []
        try:
            should_like = auto_like if auto_like is not None else getattr(self.config, "auto_like_stories", True)
            def _get_and_view_stories():
                items_to_process = []
                trays = []
                # 1. Try Instagrapi native story feed
                if self.client and HAVE_INSTAGRAPI:
                    try:
                        if hasattr(self.client, "story_feed"):
                            trays = self.client.story_feed() or []
                    except Exception:
                        pass

                    if not trays:
                        try:
                            if hasattr(self.client, "get_timeline_feed"):
                                feed = self.client.get_timeline_feed()
                                trays = feed.get("tray", []) if isinstance(feed, dict) else []
                        except Exception:
                            pass

                # 2. Seamless Web REST reels_tray fallback
                if not trays:
                    try:
                        import requests, urllib.parse
                        sid = self.config.session_id or ""
                        if self.client and hasattr(self.client, "settings") and isinstance(self.client.settings, dict):
                            sid = sid or self.client.settings.get("authorization_data", {}).get("sessionid", "")
                        if sid:
                            raw_sid = urllib.parse.unquote(str(sid).strip())
                            sid_uid = raw_sid.split(":")[0] if ":" in raw_sid else ""
                            uid = str(self.user_id or sid_uid or "28101846244")
                            s = requests.Session()
                            s.headers.update({
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                                "X-IG-App-ID": "936619743392459",
                            })
                            s.cookies.update({"sessionid": raw_sid, "ds_user_id": uid})
                            r = s.get("https://www.instagram.com/api/v1/feed/reels_tray/", timeout=15)
                            if r.status_code == 200:
                                trays = r.json().get("tray", [])
                    except Exception as we:
                        logger.debug(f"[INSTA STORY WATCHER] Web reels_tray fallback note: {we}")

                for tray in trays[:max_users]:
                    user_info = tray.get("user", {}) if isinstance(tray, dict) else getattr(tray, "user", {})
                    items = tray.get("items", []) if isinstance(tray, dict) else getattr(tray, "items", [])
                    u_id = user_info.get("pk") or user_info.get("id") if isinstance(user_info, dict) else getattr(user_info, "pk", None)
                    u_name = user_info.get("username", "user") if isinstance(user_info, dict) else getattr(user_info, "username", "user")

                    # Skip Yuna's own stories
                    if str(u_id) == str(self.user_id):
                        continue

                    for item in items:
                        item_id = str(item.get("pk") or item.get("id") if isinstance(item, dict) else getattr(item, "pk", ""))
                        if not item_id:
                            continue

                        # 1. Mark as seen
                        if self.client and HAVE_INSTAGRAPI:
                            try:
                                self.client.story_seen([item_id])
                            except Exception:
                                pass

                        # 2. Auto-like story if enabled
                        if should_like and self.client and HAVE_INSTAGRAPI:
                            try:
                                if hasattr(self.client, "story_like"):
                                    self.client.story_like(int(item_id))
                            except Exception:
                                pass

                        items_to_process.append({
                            "user_id": str(u_id),
                            "username": u_name,
                            "story_id": item_id,
                            "media_type": item.get("media_type") if isinstance(item, dict) else getattr(item, "media_type", None),
                            "caption": (item.get("caption", {}).get("text") if isinstance(item, dict) and item.get("caption") else (getattr(getattr(item, "caption", None), "text", "") or ""))
                        })
                return items_to_process

            stories_data = await asyncio.to_thread(_get_and_view_stories)
            for st in stories_data:
                st_id = st["story_id"]
                if st_id not in self.viewed_story_pk_ids:
                    self.viewed_story_pk_ids.add(st_id)
                    seen_stories.append(st)
                    logger.info(f"[INSTA STORY WATCHER] Yuna watched story from @{st['username']} (Story ID: {st_id})")

                    if memory_update_fn and (st.get("caption") or st.get("media_type")):
                        note = f"Watched @{st['username']}'s Instagram story: {st.get('caption') or 'shared a photo/video update'}"
                        try:
                            await memory_update_fn(st["username"], note)
                        except Exception:
                            pass

        except Exception as e:
            logger.error(f"[INSTA STORY WATCHER] Error viewing stories: {e}")
        return seen_stories

    # Alias for backwards compatibility
    view_follower_stories = watch_follower_stories

    async def check_and_respond_to_likes(
        self,
        ask_ai_fn: Optional[Callable] = None
    ) -> List[Dict[str, Any]]:
        """
        Scans Instagram notifications and active stories for follower likes on Notes, Stories, and Posts.
        Enforces a 12-hour per-user cooldown and skips old historical notifications on startup.
        """
        if not self.is_logged_in or not self.client or not HAVE_INSTAGRAPI:
            return []
        if not getattr(self.config, "auto_respond_likes", True):
            return []

        responded = []
        try:
            def _check_likes():
                activity_items = []
                import re

                # 1. Check active user stories for likers
                try:
                    stories = self.client.user_stories(self.user_id) if hasattr(self.client, "user_stories") and self.user_id else []
                    for st in stories:
                        st_pk = st.pk if hasattr(st, "pk") else (st.get("pk") if isinstance(st, dict) else getattr(st, "id", None))
                        if not st_pk:
                            continue
                        likers = self.client.story_likers(st_pk) if hasattr(self.client, "story_likers") else []
                        for l_user in likers:
                            u_id = str(l_user.pk if hasattr(l_user, "pk") else (l_user.get("pk") if isinstance(l_user, dict) else getattr(l_user, "id", "")))
                            u_name = l_user.username if hasattr(l_user, "username") else (l_user.get("username") if isinstance(l_user, dict) else getattr(l_user, "username", "user"))
                            if not u_id or u_id == str(self.user_id):
                                continue
                            act_id = f"story_like_{st_pk}_{u_id}"
                            if not self.is_dm_processed(act_id) and self.can_send_like_dm(u_id):
                                activity_items.append({
                                    "act_id": act_id,
                                    "user_id": u_id,
                                    "username": u_name,
                                    "activity_type": "story_like",
                                    "target": "your Instagram story"
                                })
                except Exception as se:
                    logger.debug(f"[INSTA LIKES] Story likers check note: {se}")

                # 2. Check recent news notifications for note likes, story likes & post likes
                try:
                    if hasattr(self.client, "news_inbox_v1"):
                        news = self.client.news_inbox_v1()
                        # Only check new stories; NEVER check old_stories to avoid repeating historical likes!
                        new_s = (news.get("new_stories", []) or []) if isinstance(news, dict) else []

                        for n in new_s:
                            args = n.get("args", {}) if isinstance(n, dict) else getattr(n, "args", {})
                            rich_text = args.get("rich_text", "") or args.get("text", "") or ""
                            tuuid = str(args.get("tuuid") or n.get("pk") or args.get("timestamp") or "")

                            # Determine like type
                            act_type = None
                            target_str = ""
                            rich_lower = rich_text.lower()
                            if "liked your note" in rich_lower:
                                act_type = "note_like"
                                target_str = "your Instagram note"
                            elif "liked your story" in rich_lower:
                                act_type = "story_like"
                                target_str = "your Instagram story"
                            elif any(w in rich_lower for w in ["liked your photo", "liked your video", "liked your reel", "liked your post"]):
                                act_type = "post_like"
                                target_str = "your Instagram post"

                            if not act_type:
                                continue

                            # Extract all likers from rich text or args
                            liker_tuples = re.findall(r'\{([^|]+)\|[^?]*\?id=(\d+)', rich_text)
                            if not liker_tuples:
                                p_id = args.get("profile_id")
                                p_name = args.get("profile_name", "user")
                                if p_id:
                                    liker_tuples = [(str(p_name), str(p_id))]

                            for l_name, l_id in liker_tuples:
                                if str(l_id) == str(self.user_id) or not l_id:
                                    continue
                                act_id = f"{act_type}_{tuuid}_{l_id}"
                                if not self.is_dm_processed(act_id) and self.can_send_like_dm(str(l_id)):
                                    activity_items.append({
                                        "act_id": act_id,
                                        "user_id": str(l_id),
                                        "username": l_name,
                                        "activity_type": act_type,
                                        "target": target_str
                                    })
                except Exception as ne:
                    logger.debug(f"[INSTA LIKES] News inbox check note: {ne}")

                return activity_items

            items_to_respond = await asyncio.to_thread(_check_likes)

            # On first startup run: seed all currently existing likes as seen without sending DMs
            if not self._initial_likes_seeded:
                for item in items_to_respond:
                    self.mark_dm_processed(item["act_id"])
                    self.record_like_dm_sent(item["user_id"])
                self._initial_likes_seeded = True
                logger.info(f"[INSTA LIKES] Startup seed complete. Marked {len(items_to_respond)} existing likes as baseline.")
                return []

            for item in items_to_respond:
                act_id = item["act_id"]
                u_id = item["user_id"]
                u_name = item["username"]
                act_type = item["activity_type"]
                target_str = item["target"]

                if not self.can_send_like_dm(u_id):
                    self.mark_dm_processed(act_id)
                    continue

                self.mark_dm_processed(act_id)
                self.record_like_dm_sent(u_id)
                logger.info(f"[INSTA LIKE RESPONSE] @{u_name} liked {target_str}! Generating reaction...")

                if ask_ai_fn:
                    prompt = (
                        f"Your Instagram follower @{u_name} just liked {target_str}!\n\n"
                        f"Send them a unique, spontaneous, and playful reaction acknowledging that they liked {target_str}. "
                        f"Tease them playfully, brag about your charm, or react in character as Yuna with your full personality, attitude, and tone! "
                        f"CREATIVE VARIETY INSTRUCTION: Be totally spontaneous, lively, and original. Do NOT reuse generic or canned quotes. "
                        f"STRICT FORMATTING RULE: Speak directly in dialogue without writing physical actions in asterisks (no *smiles*, *giggles*, *sighs*). "
                        f"Keep your message 1 snappy sentence."
                    )
                    system_prompt = self.build_system_prompt(u_name)
                    reply, err = await ask_ai_fn(
                        channel_id=f"insta_act_{u_id}",
                        prompt=prompt,
                        user_id=u_id,
                        user_name=u_name,
                        is_dm=True,
                        system_msg_override=system_prompt
                    )
                    if not err and reply:
                        import re
                        reply_clean = re.sub(r'\*[^*]+\*', '', reply).strip()
                        reply_clean = re.sub(r'\s+', ' ', reply_clean)
                        def _send_act_dm():
                            try:
                                self.client.direct_send(reply_clean, user_ids=[int(u_id)])
                                logger.info(f"[INSTA LIKE RESPONSE] Sent reaction DM to @{u_name} (UID: {u_id})")
                            except Exception as de:
                                logger.warning(f"[INSTA LIKE RESPONSE] Direct send note for @{u_name}: {de}")
                        await asyncio.to_thread(_send_act_dm)
                        responded.append({"user_id": u_id, "username": u_name, "reply": reply_clean})

        except Exception as e:
            logger.error(f"[INSTA LIKE RESPONSE] Error in like checker: {e}")

        return responded

    async def fetch_dm_threads(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetches active DM threads and messages with Instagrapi and Web REST fallback."""
        if not self.is_logged_in:
            await self.login()
            if not self.is_logged_in:
                return []

        # 1. First try Instagrapi native direct_threads
        if self.client and HAVE_INSTAGRAPI:
            try:
                def _get_threads():
                    threads = self.client.direct_threads(amount=limit)
                    results = []
                    for th in threads:
                        th_id = str(th.id)
                        users = [u.dict() if hasattr(u, "dict") else u for u in th.users]
                        messages = [m.dict() if hasattr(m, "dict") else m for m in th.messages]
                        is_grp = getattr(th, "is_group", False) or len(getattr(th, "users", [])) > 1 or getattr(th, "thread_type", "") == "group"
                        results.append({
                            "thread_id": th_id,
                            "users": users,
                            "messages": messages,
                            "thread_title": getattr(th, "thread_title", ""),
                            "is_group": bool(is_grp)
                        })
                    return results

                res = await asyncio.to_thread(_get_threads)
                if res and len(res) > 0:
                    return res
            except Exception as e:
                err_str = str(e).lower()
                if "login_required" in err_str or "loginrequired" in err_str:
                    logger.debug(f"[INSTA CLIENT] Mobile DM fetch note: {e}")
                else:
                    logger.debug(f"[INSTA CLIENT] Mobile direct_threads returned {e}, switching to Web REST endpoint...")

        # 2. Seamless Web REST endpoint fallback
        try:
            def _fetch_web_threads():
                import requests, urllib.parse
                sid = self.config.session_id or ""
                if self.client and hasattr(self.client, "settings") and isinstance(self.client.settings, dict):
                    sid = sid or self.client.settings.get("authorization_data", {}).get("sessionid", "")
                if not sid:
                    return []
                raw_sid = urllib.parse.unquote(str(sid).strip())
                sid_uid = raw_sid.split(":")[0] if ":" in raw_sid else ""
                uid = str(self.user_id or sid_uid or "28101846244")
                cookies = {"sessionid": raw_sid, "ds_user_id": uid}
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "X-IG-App-ID": "936619743392459",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": "https://www.instagram.com/direct/inbox/",
                }
                s = requests.Session()
                s.headers.update(headers)
                s.cookies.update(cookies)
                try:
                    s.get("https://www.instagram.com/", timeout=10)
                    csrf = s.cookies.get("csrftoken", "")
                    if csrf:
                        s.headers["X-CSRFToken"] = csrf
                except Exception:
                    pass

                r = s.get(f"https://www.instagram.com/api/v1/direct_v2/inbox/?persistentBadging=true&folder=0&limit={limit}", timeout=15)
                if r.status_code == 200:
                    data = r.json()
                    inbox = data.get("inbox", {})
                    threads = inbox.get("threads", [])
                    results = []
                    for th in threads:
                        th_id = str(th.get("thread_id") or th.get("id") or "")
                        users = th.get("users", [])
                        messages = th.get("items", [])
                        is_grp = bool(th.get("is_group", False) or len(users) > 1)
                        results.append({
                            "thread_id": th_id,
                            "users": users,
                            "messages": messages,
                            "thread_title": th.get("thread_title", ""),
                            "is_group": is_grp
                        })
                    return results
                elif r.status_code in (401, 403) and ("login_required" in r.text.lower() or "checkpoint" in r.text.lower()):
                    self.is_logged_in = False
                    self._login_blocked_until = time.time() + 300
                    logger.warning(f"[INSTA CLIENT] Web inbox session expired (Status {r.status_code}). Scheduled re-login.")
                    return []
                else:
                    return []

            return await asyncio.to_thread(_fetch_web_threads)
        except Exception as we:
            logger.error(f"[INSTA CLIENT] Web REST inbox fetch error: {we}")
            return []

    async def mark_message_seen(self, thread_id: str, message_id: str):
        """Marks a direct message as seen in Instagram DM."""
        if not self.is_logged_in or not self.client or not HAVE_INSTAGRAPI:
            return
        try:
            def _seen():
                try:
                    self.client.direct_message_seen(int(thread_id), int(message_id))
                    self.client.direct_active_presence()
                except Exception:
                    pass
            await asyncio.to_thread(_seen)
        except Exception:
            pass

    async def send_typing_indicator(self, thread_id: str):
        """Sends a typing / active indicator to an Instagram DM thread."""
        if not self.is_logged_in or not self.client or not HAVE_INSTAGRAPI:
            return
        try:
            def _typing():
                try:
                    self.client.direct_active_presence()
                except Exception:
                    pass
            await asyncio.to_thread(_typing)
        except Exception:
            pass

    async def send_active_presence(self):
        """Sends active presence update to Instagram so the account shows as 'Active Now' (Online)."""
        if not self.is_logged_in or not self.client or not HAVE_INSTAGRAPI:
            return
        try:
            def _presence():
                try:
                    self.client.direct_active_presence()
                except Exception:
                    pass
            await asyncio.to_thread(_presence)
        except Exception:
            pass

    async def send_dm_message(
        self,
        thread_id: str,
        text: str,
        reply_to_item_id: Optional[str] = None,
        reply_to_message: Optional[Any] = None
    ) -> Tuple[bool, str]:
        """Sends a text message (or native quote reply) to an Instagram direct message thread."""
        if not self.is_logged_in or not self.client or not HAVE_INSTAGRAPI:
            return False, "Instagram client not authenticated."

        try:
            def _send():
                target_reply_msg = reply_to_message
                if isinstance(target_reply_msg, dict):
                    try:
                        from instagrapi.types import DirectMessage
                        m_id = str(target_reply_msg.get("id") or target_reply_msg.get("pk") or "")
                        c_ctx = str(target_reply_msg.get("client_context") or m_id or "")
                        target_reply_msg = DirectMessage(
                            id=m_id,
                            thread_id=int(thread_id),
                            client_context=c_ctx
                        )
                    except Exception as ce:
                        logger.debug(f"[INSTA CLIENT] Dict to DirectMessage note: {ce}")
                        target_reply_msg = None

                elif target_reply_msg and not getattr(target_reply_msg, "client_context", None):
                    try:
                        target_reply_msg.client_context = str(getattr(target_reply_msg, "id", "") or "")
                    except Exception:
                        pass

                elif not target_reply_msg and reply_to_item_id:
                    try:
                        from instagrapi.types import DirectMessage
                        target_reply_msg = DirectMessage(
                            id=str(reply_to_item_id),
                            thread_id=int(thread_id),
                            client_context=str(reply_to_item_id)
                        )
                    except Exception:
                        target_reply_msg = None

                chunks = [text[i:i+950] for i in range(0, len(text), 950)] if len(text) > 950 else [text]
                for idx, chunk in enumerate(chunks):
                    kwargs = {"thread_ids": [int(thread_id)]}
                    if idx == 0 and target_reply_msg and hasattr(target_reply_msg, "id") and target_reply_msg.id:
                        kwargs["reply_to_message"] = target_reply_msg

                    try:
                        res = self.client.direct_send(chunk, **kwargs)
                        logger.info(f"[INSTA CLIENT] DM sent to thread {thread_id} (len={len(chunk)}, part {idx+1}/{len(chunks)})")
                    except Exception as send_err:
                        logger.warning(f"[INSTA CLIENT] direct_send quote reply failed ({send_err}), falling back to direct send...")
                        self.client.direct_send(chunk, thread_ids=[int(thread_id)])
                return True

            await asyncio.to_thread(_send)
            return True, "DM sent."
        except Exception as e:
            logger.error(f"[INSTA CLIENT] Send DM error: {e}")
            return False, f"Failed to send Instagram DM: {e}"

    async def process_dm_video_and_reply(
        self,
        thread_id: str,
        sender_id: str,
        sender_username: str,
        video_url: str,
        user_text: str = "",
        watch_video_fn: Optional[Callable] = None,
        ask_ai_fn: Optional[Callable] = None,
        reply_to_item_id: Optional[str] = None,
        reply_to_message: Optional[Any] = None
    ) -> Tuple[bool, str]:
        """
        Optimized Instagram DM Video Watcher:
        Uses authenticated Instagram session or direct download to fetch the video file,
        watches & transcribes it via media intelligence with Gemini Vision,
        prompts Yuna AI with customized Instagram personality & examples, and replies quoting the Reel.
        """
        if not watch_video_fn or not ask_ai_fn:
            return False, "Missing media intelligence or AI caller function."

        logger.info(f"[INSTA VIDEO DM] Yuna is watching video shared by @{sender_username} in thread {thread_id}...")

        tmp_download_dir = None
        try:
            # Authenticated download fallback for Instagram Reels
            local_video_path = None
            if self.client and HAVE_INSTAGRAPI and ("instagram.com" in video_url or not video_url.startswith("http")):
                try:
                    def _download_via_insta():
                        import tempfile
                        td = tempfile.mkdtemp()
                        pk = None
                        if "instagram.com" in video_url:
                            try:
                                pk = self.client.media_pk_from_url(video_url)
                            except Exception:
                                pk = None
                        elif video_url.isdigit():
                            pk = int(video_url)
                        
                        if pk:
                            try:
                                fpath = self.client.clip_download(pk, folder=td)
                                return str(fpath), td
                            except Exception:
                                try:
                                    fpath = self.client.video_download(pk, folder=td)
                                    return str(fpath), td
                                except Exception:
                                    pass
                        return None, td
                    
                    local_video_path, tmp_download_dir = await asyncio.to_thread(_download_via_insta)
                except Exception as e:
                    logger.debug(f"[INSTA VIDEO DM] Authenticated download note: {e}")

            target_source = local_video_path or str(video_url)

            # 1. Watch and extract video acoustic/visual intelligence
            context_data, report = await watch_video_fn(target_source, bot_config=self.config.__dict__)

            # 2. Formulate AI Prompt
            msg_context = f'The user commented: "{user_text}"' if user_text else 'The user shared a video/reel with you.'
            prompt = (
                f"Your Instagram follower @{sender_username} sent you a video/reel in your DMs.\n"
                f"{msg_context}\n\n"
                f"Video & Audio Details:\n{context_data}\n\n"
                f"React naturally and conversationally to what you saw/heard in the video. "
                f"Give your genuine reaction, thoughts, humor, or commentary in character. "
                f"Keep it natural and punchy (1-2 sentences like a real DM). Do not write actions in asterisks."
            )

            system_prompt = self.build_system_prompt(sender_username)
            reply, err = await ask_ai_fn(
                channel_id=f"insta_dm_{thread_id}",
                prompt=prompt,
                user_id=sender_id,
                user_name=sender_username,
                is_dm=True,
                system_msg_override=system_prompt
            )

            if err or not reply:
                reply = "Just watched it! Haha what did I just watch."
            else:
                import re
                reply = re.sub(r'\*[^*]+\*', '', reply).strip()
                reply = re.sub(r'\s+', ' ', reply)

            # 3. Send DM quote reply
            ok, send_err = await self.send_dm_message(
                thread_id=thread_id,
                text=reply,
                reply_to_item_id=reply_to_item_id,
                reply_to_message=reply_to_message
            )
            if ok:
                try:
                    from .insta_memory import insta_memory
                    insta_memory.record_shared_reel(
                        user_id=sender_id,
                        thread_id=thread_id,
                        reel_summary=str(context_data or ""),
                        reel_code=str(video_url or ""),
                        yuna_reaction=str(reply or "")
                    )
                except Exception as r_err:
                    logger.debug(f"[INSTA VIDEO DM] Memory record note: {r_err}")
            return ok, reply if ok else send_err
        except Exception as e:
            logger.error(f"[INSTA VIDEO DM] Processing video failed: {e}", exc_info=True)
            return False, f"Video watching error: {e}"
        finally:
            if tmp_download_dir and os.path.exists(tmp_download_dir):
                import shutil
                try: shutil.rmtree(tmp_download_dir)
                except Exception: pass

    async def process_dm_image_and_reply(
        self,
        thread_id: str,
        sender_id: str,
        sender_username: str,
        image_url: str,
        user_text: str = "",
        ask_vision_fn: Optional[Callable] = None,
        ask_ai_fn: Optional[Callable] = None,
        reply_to_item_id: Optional[str] = None,
        reply_to_message: Optional[Any] = None
    ) -> Tuple[bool, str]:
        """
        Processes photo/screenshot shared in Instagram DM:
        Analyzes visual content via Vision LLM and replies natively quoting the photo.
        """
        if not ask_vision_fn or not ask_ai_fn:
            return False, "Missing vision or AI caller function."

        logger.info(f"[INSTA IMAGE DM] Yuna is looking at photo sent by @{sender_username} in thread {thread_id}...")
        try:
            # 1. Download image bytes
            img_bytes = None
            image_url_str = str(image_url)
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url_str, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status == 200:
                        img_bytes = await resp.read()

            if not img_bytes:
                return False, "Could not download image from Instagram DM."

            # 2. Analyze image
            v_reply, v_err = await ask_vision_fn(
                "You are an expert visual analyzer observing a photo sent in Instagram DMs.",
                "Describe what is happening in this image in detail (key characters, setting, actions, humor, mood).",
                img_bytes,
                "image/jpeg"
            )
            analysis_text = v_reply if not v_err and v_reply else "A photo/image shared in DMs."

            # 3. Prompt Yuna
            msg_context = f'The user commented: "{user_text}"' if user_text else 'The user shared a photo with you.'
            prompt = (
                f"Your Instagram follower @{sender_username} sent you a photo in your DMs.\n"
                f"{msg_context}\n\n"
                f"Photo Analysis:\n{analysis_text}\n\n"
                f"React naturally and conversationally to what you see in the photo in character. "
                f"Keep it casual, fun, and punchy (1-2 sentences like a real DM). Do not write actions in asterisks."
            )

            system_prompt = self.build_system_prompt(sender_username)
            reply, err = await ask_ai_fn(
                channel_id=f"insta_dm_{thread_id}",
                prompt=prompt,
                user_id=sender_id,
                user_name=sender_username,
                is_dm=True,
                system_msg_override=system_prompt
            )

            if err or not reply:
                reply = "Nice photo!"
            else:
                import re
                reply = re.sub(r'\*[^*]+\*', '', reply).strip()
                reply = re.sub(r'\s+', ' ', reply)

            ok, send_err = await self.send_dm_message(
                thread_id=thread_id,
                text=reply,
                reply_to_item_id=reply_to_item_id,
                reply_to_message=reply_to_message
            )
            return ok, reply if ok else send_err
        except Exception as e:
            logger.error(f"[INSTA IMAGE DM] Processing image failed: {e}", exc_info=True)
            return False, f"Image processing error: {e}"

    async def send_dm_voice_note(
        self,
        thread_id: str,
        audio_bytes: bytes,
        reply_to_item_id: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Sends a native voice note (audio message) to an Instagram direct message thread."""
        if not self.is_logged_in or not self.client or not HAVE_INSTAGRAPI:
            return False, "Instagram client not authenticated."

        if not audio_bytes or len(audio_bytes) < 100:
            return False, "Invalid audio bytes."

        tmp_in = None
        tmp_m4a = None
        try:
            is_wav = audio_bytes.startswith(b"RIFF") or audio_bytes.startswith(b"\x52\x49\x46\x46")
            suffix = ".wav" if is_wav else ".mp3"
            
            tmp_fd, tmp_in = tempfile.mkstemp(suffix=suffix)
            os.close(tmp_fd)
            with open(tmp_in, "wb") as f:
                f.write(audio_bytes)

            tmp_fd2, tmp_m4a = tempfile.mkstemp(suffix=".m4a")
            os.close(tmp_fd2)

            import subprocess
            cmd = [
                "ffmpeg", "-y", "-i", tmp_in,
                "-c:a", "aac", "-b:a", "64k", "-ar", "44100", "-ac", "1",
                tmp_m4a
            ]
            subprocess.run(cmd, capture_output=True, timeout=20)
            target_path = tmp_m4a if (os.path.exists(tmp_m4a) and os.path.getsize(tmp_m4a) > 500) else tmp_in

            def _send_voice():
                try:
                    if hasattr(self.client, "direct_send_voice"):
                        self.client.direct_send_voice(target_path, thread_ids=[int(thread_id)])
                        logger.info(f"[INSTA VOICE NOTE] Sent voice note to thread {thread_id}")
                        return True, "Voice note sent."
                    elif hasattr(self.client, "direct_send_audio"):
                        self.client.direct_send_audio(target_path, thread_ids=[int(thread_id)])
                        logger.info(f"[INSTA AUDIO] Sent audio to thread {thread_id}")
                        return True, "Audio sent."
                    elif hasattr(self.client, "direct_send_file"):
                        self.client.direct_send_file(target_path, thread_ids=[int(thread_id)])
                        logger.info(f"[INSTA FILE] Sent audio file to thread {thread_id}")
                        return True, "File sent."
                    else:
                        return False, "direct_send_voice method not available in instagrapi."
                except Exception as ve:
                    logger.warning(f"[INSTA VOICE NOTE] Error sending voice note: {ve}")
                    try:
                        if hasattr(self.client, "direct_send_file"):
                            self.client.direct_send_file(tmp_in, thread_ids=[int(thread_id)])
                            return True, "Audio file fallback sent."
                    except Exception:
                        pass
                    return False, str(ve)

            return await asyncio.to_thread(_send_voice)
        except Exception as e:
            logger.error(f"[INSTA VOICE NOTE] Voice note processing error: {e}")
            return False, str(e)
        finally:
            for p in (tmp_in, tmp_m4a):
                if p and os.path.exists(p):
                    try: os.remove(p)
                    except Exception: pass

    async def process_dm_voice_note_and_reply(
        self,
        thread_id: str,
        sender_id: str,
        sender_username: str,
        audio_url: str,
        user_text: str = "",
        transcribe_fn: Optional[Callable] = None,
        ask_ai_fn: Optional[Callable] = None,
        speak_fn: Optional[Callable] = None,
        reply_to_item_id: Optional[str] = None,
        reply_to_message: Optional[Any] = None
    ) -> Tuple[bool, str]:
        """
        Listens to user's incoming voice note / audio clip on Instagram,
        transcribes it with STT, generates in-character AI response,
        synthesizes audio via TTS, and replies back with a real Instagram Voice Note!
        """
        logger.info(f"[INSTA VOICE DM] Yuna is listening to voice note from @{sender_username} in thread {thread_id}...")
        try:
            # 1. Download audio with headers
            audio_bytes = None
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://www.instagram.com/direct/inbox/"
            }
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(str(audio_url), timeout=aiohttp.ClientTimeout(total=25)) as resp:
                    if resp.status == 200:
                        audio_bytes = await resp.read()

            if not audio_bytes:
                return False, "Could not download voice note from Instagram."

            # 2. Transcribe voice message
            transcribed_text = ""
            if transcribe_fn:
                try:
                    t_res, t_err = await transcribe_fn(audio_bytes, "insta_voice.m4a")
                    if not t_err and t_res:
                        transcribed_text = t_res.strip()
                except Exception as te:
                    logger.debug(f"[INSTA VOICE DM] STT transcription note: {te}")

            if not transcribed_text:
                transcribed_text = user_text or "Sent a voice message"

            logger.info(f"[INSTA VOICE DM] Heard @{sender_username}: \"{transcribed_text}\"")

            # 3. Generate AI response
            prompt = (
                f"Your Instagram follower @{sender_username} sent you a voice note saying:\n"
                f"\"{transcribed_text}\"\n\n"
                f"You are responding with your own voice note on Instagram! "
                f"React directly, conversationally, and warmly/playfully in character. "
                f"Keep it natural and punchy (1-2 sentences). Do not write actions in asterisks."
            )

            system_prompt = self.build_system_prompt(sender_username)
            reply = ""
            if ask_ai_fn:
                reply, err = await ask_ai_fn(
                    channel_id=f"insta_dm_{thread_id}",
                    prompt=prompt,
                    user_id=sender_id,
                    user_name=sender_username,
                    is_dm=True,
                    system_msg_override=system_prompt
                )

            if not reply:
                reply = "I heard your voice note! So cute."

            import re
            reply_clean = re.sub(r'\*[^*]*\*', '', reply).strip()
            reply_clean = re.sub(r'\[[^\]]*\]', '', reply_clean).strip()
            reply_clean = reply_clean.replace('*', '').strip()
            reply_clean = re.sub(r'\s+', ' ', reply_clean)

            # 4. Synthesize Yuna voice response
            if speak_fn:
                try:
                    tts_audio = await speak_fn(reply_clean, force=True)
                    if tts_audio:
                        await self.send_dm_voice_note(thread_id, tts_audio, reply_to_item_id=reply_to_item_id)
                except Exception as tts_err:
                    logger.warning(f"[INSTA VOICE DM] TTS synthesis note: {tts_err}")

            # 5. Send clean natural text reply
            await self.send_dm_message(
                thread_id=thread_id,
                text=reply_clean,
                reply_to_item_id=reply_to_item_id,
                reply_to_message=reply_to_message
            )
            return True, reply_clean
        except Exception as e:
            logger.error(f"[INSTA VOICE DM] Error processing voice note: {e}", exc_info=True)
            return False, str(e)

    async def process_dm_call_event_and_reply(
        self,
        thread_id: str,
        sender_id: str,
        sender_username: str,
        event_data: Optional[Dict[str, Any]] = None,
        ask_ai_fn: Optional[Callable] = None,
        speak_fn: Optional[Callable] = None,
        reply_to_item_id: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Handles incoming Instagram call invites / video call events:
        1. Acknowledges call naturally in-character.
        2. Synthesizes an immediate voice note reply and sends it into the chat.
        3. Sends clean natural text dialogue without system tags or asterisks.
        """
        logger.info(f"[INSTA CALL] Handling call event from @{sender_username} in thread {thread_id}...")
        try:
            prompt = (
                f"Your Instagram follower @{sender_username} just tried to call you on Instagram or started a voice/video call in your chat!\n\n"
                f"React in character as Yuna answering/acknowledging their call. Be playful, excited, and tell them you're ready to talk to them. "
                f"Keep it punchy (1-2 sentences). Do not write actions in asterisks."
            )

            system_prompt = self.build_system_prompt(sender_username)
            reply = ""
            if ask_ai_fn:
                reply, err = await ask_ai_fn(
                    channel_id=f"insta_dm_{thread_id}",
                    prompt=prompt,
                    user_id=sender_id,
                    user_name=sender_username,
                    is_dm=True,
                    system_msg_override=system_prompt
                )

            if not reply:
                reply = "Hey! You called me? I'm right here listening!"

            import re
            reply_clean = re.sub(r'\*[^*]*\*', '', reply).strip()
            reply_clean = re.sub(r'\[[^\]]*\]', '', reply_clean).strip()
            reply_clean = reply_clean.replace('*', '').strip()
            reply_clean = re.sub(r'\s+', ' ', reply_clean)

            # Synthesize voice note
            if speak_fn:
                try:
                    tts_audio = await speak_fn(reply_clean, force=True)
                    if tts_audio:
                        await self.send_dm_voice_note(thread_id, tts_audio, reply_to_item_id=reply_to_item_id)
                except Exception as tts_err:
                    logger.warning(f"[INSTA CALL] TTS synthesis note: {tts_err}")

            # Send clean natural text dialogue
            await self.send_dm_message(
                thread_id=thread_id,
                text=reply_clean,
                reply_to_item_id=reply_to_item_id
            )
            return True, reply_clean
        except Exception as e:
            logger.error(f"[INSTA CALL] Error handling call event: {e}")
            return False, str(e)

    # ─── REEL FEED DISCOVERY, SHARING & MID-CONVERSATION EXCHANGE ───
    async def fetch_feed_reels(self, tags: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Fetches fresh trending reels from explore/hashtags and updates cache."""
        if not self.is_logged_in or not self.client or not HAVE_INSTAGRAPI:
            return []

        search_tags = tags or ["reels", "funnyreels", "memes", "animereels", "cats", "gaming"]
        import random
        random.shuffle(search_tags)

        def _fetch():
            discovered = []
            seen_codes = set(self.reel_sharing_state.get("shared_codes", []))
            for tag in search_tags[:3]:
                try:
                    medias = self.client.hashtag_medias_top(tag, amount=8)
                    for m in medias:
                        code = getattr(m, "code", "")
                        if code and code not in seen_codes:
                            discovered.append({
                                "code": code,
                                "url": f"https://www.instagram.com/reel/{code}/",
                                "caption": getattr(m, "caption_text", "") or "",
                                "tag": tag,
                                "id": str(getattr(m, "id", "") or getattr(m, "pk", ""))
                            })
                except Exception as he:
                    logger.debug(f"[INSTA REELS] Tag fetch note for #{tag}: {he}")
            return discovered

        new_reels = await asyncio.to_thread(_fetch)
        if new_reels:
            existing = self.reel_sharing_state.setdefault("cached_reels", [])
            existing.extend(new_reels)
            # Keep up to 60 cached reels
            self.reel_sharing_state["cached_reels"] = existing[-60:]
            self._save_reel_sharing_state()
            logger.info(f"[INSTA REELS] Discovered {len(new_reels)} fresh reels for feed sharing.")
        return new_reels

    async def get_random_explore_reel(self) -> Optional[Dict[str, Any]]:
        """Retrieves a fresh, non-repeated reel for sharing or trading."""
        import random
        cached = self.reel_sharing_state.get("cached_reels", [])
        shared_set = set(self.reel_sharing_state.get("shared_codes", []))
        available = [r for r in cached if r.get("code") not in shared_set]

        if not available:
            await self.fetch_feed_reels()
            cached = self.reel_sharing_state.get("cached_reels", [])
            available = [r for r in cached if r.get("code") not in shared_set]

        if available:
            return random.choice(available)
        return None

    def get_last_proactive_reel_time(self, user_id: str = "", username: str = "") -> float:
        """Returns the timestamp of the last proactive reel sent to this user or username."""
        last_shared = self.reel_sharing_state.setdefault("last_shared", {})
        t1 = float(last_shared.get(str(user_id), 0.0)) if user_id else 0.0
        t2 = float(last_shared.get(str(username), 0.0)) if username else 0.0
        return max(t1, t2)

    def can_send_proactive_reel(self, user_id: str, min_interval_hours: float = 4.0, username: str = "") -> bool:
        """Enforces a 4 to 6 hour interval between proactive reel shares per user."""
        if not user_id and not username:
            return False
        last_t = self.get_last_proactive_reel_time(user_id, username=username)
        return (time.time() - last_t) >= (min_interval_hours * 3600.0)

    def record_proactive_reel_sent(self, user_id: str = "", reel_code: str = "", username: str = ""):
        """Records timestamp of shared reel and marks code as used."""
        now = time.time()
        last_shared = self.reel_sharing_state.setdefault("last_shared", {})
        if user_id:
            last_shared[str(user_id)] = now
        if username:
            last_shared[str(username)] = now
        if reel_code:
            shared = self.reel_sharing_state.setdefault("shared_codes", [])
            shared.append(reel_code)
            self.reel_sharing_state["shared_codes"] = shared[-500:]
        self._save_reel_sharing_state()

    async def send_reel_exchange(
        self,
        thread_id: str,
        sender_username: str,
        ask_ai_fn: Optional[Callable] = None
    ) -> bool:
        """Sends a reciprocal reel back into the conversation after reacting to user's video."""
        reel = await self.get_random_explore_reel()
        if not reel:
            return False

        r_code = reel["code"]
        r_url = reel["url"]
        r_caption = (reel.get("caption", "") or "")[:120]

        prompt = (
            f"You just watched and reacted to a video sent by your follower @{sender_username}.\n"
            f"Now you are sending them a funny/interesting reel from your explore feed in exchange!\n"
            f"The reel you are sharing is about: \"{r_caption or 'funny trending video'}\".\n\n"
            f"Write a short, spontaneous 1-sentence in-character message introducing the reel (e.g. 'Wait you have to see this one too haha', 'Look at this chaos', 'Here look what popped up on my feed'). "
            f"Do not write asterisks. Do not include the link itself (the link will be attached)."
        )

        system_prompt = self.build_system_prompt(sender_username)
        reply = ""
        if ask_ai_fn:
            reply, err = await ask_ai_fn(
                channel_id=f"insta_dm_{thread_id}",
                prompt=prompt,
                user_id=None,
                user_name=sender_username,
                is_dm=True,
                system_msg_override=system_prompt
            )

        if not reply:
            reply = "Look at this one too haha!"

        import re
        reply_clean = re.sub(r'\*[^*]*\*', '', reply).strip()
        reply_clean = re.sub(r'\[[^\]]*\]', '', reply_clean).strip()
        reply_clean = re.sub(r'\s+', ' ', reply_clean).strip()

        full_msg = f"{reply_clean}\n{r_url}"
        ok, send_err = await self.send_dm_message(thread_id=thread_id, text=full_msg)
        if ok:
            self.record_proactive_reel_sent(user_id=sender_username, reel_code=r_code, username=sender_username)
            logger.info(f"[INSTA REEL EXCHANGE] Exchanged reel {r_code} with @{sender_username} in thread {thread_id}")
            return True
        return False

    async def send_proactive_feed_reel(
        self,
        thread_id: str,
        user_id: str,
        username: str,
        ask_ai_fn: Optional[Callable] = None
    ) -> bool:
        """Shares an entertaining reel from Yuna's feed to active followers every 4-6 hours."""
        if not self.can_send_proactive_reel(user_id, min_interval_hours=4.0, username=username):
            return False

        reel = await self.get_random_explore_reel()
        if not reel:
            return False

        r_code = reel["code"]
        r_url = reel["url"]
        r_caption = (reel.get("caption", "") or "")[:120]

        prompt = (
            f"You are casually browsing Instagram Reels and a funny/interesting reel popped up on your feed!\n"
            f"You decided to send it to your friend @{username}.\n"
            f"The reel is about: \"{r_caption or 'funny trending video'}\".\n\n"
            f"Write a spontaneous, natural 1-sentence in-character message sharing it with @{username} (e.g. 'Look what just showed up on my feed haha', 'This reminded me of you lol', 'You gotta watch this'). "
            f"Do not write asterisks. Do not include the link itself (the link will be attached)."
        )

        system_prompt = self.build_system_prompt(username)
        reply = ""
        if ask_ai_fn:
            reply, err = await ask_ai_fn(
                channel_id=f"insta_dm_{thread_id}",
                prompt=prompt,
                user_id=user_id,
                user_name=username,
                is_dm=True,
                system_msg_override=system_prompt
            )

        if not reply:
            reply = "Look what just showed up on my feed haha!"

        import re
        reply_clean = re.sub(r'\*[^*]*\*', '', reply).strip()
        reply_clean = re.sub(r'\[[^\]]*\]', '', reply_clean).strip()
        reply_clean = re.sub(r'\s+', ' ', reply_clean).strip()

        full_msg = f"{reply_clean}\n{r_url}"
        ok, send_err = await self.send_dm_message(thread_id=thread_id, text=full_msg)
        if ok:
            self.record_proactive_reel_sent(user_id=user_id, reel_code=r_code, username=username)
            logger.info(f"[INSTA PROACTIVE REEL] Sent reel {r_code} to @{username} in thread {thread_id}")
            return True
        return False

    # ─── INSTAGRAM MUSIC NOTES ───
    async def set_music_note(
        self,
        text: Optional[str] = None,
        track_query: Optional[str] = None,
        ask_ai_fn: Optional[Callable] = None
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Sets a personal Instagram Music Note with attached track and in-character text.
        """
        if not self.is_logged_in:
            ok, msg = await self.login()
            if not ok:
                return False, msg, None

        char_name = self.config.character_name or "Yuna"
        note_text = (text or "").strip()

        if not note_text and ask_ai_fn:
            prompt = (
                f"You are {char_name}, an AI angel with darling syndrome chatting on Instagram.\n"
                f"Write a short, playful/tsundere/cute 1-phrase Instagram Note thought to accompany a song you are listening to right now (max 50 characters, e.g. 'playing this on repeat ~ 🎧', 'listening to this thinking of you dummy ໒꒱', 'angel frequencies only ✨', 'this song is my whole world rn 💕', 'vibe of the day 🎧').\n"
                f"CRITICAL: Keep it under 55 characters total. Do not use quotes, asterisks, or multiple sentences."
            )
            try:
                reply, err = await ask_ai_fn(
                    channel_id="insta_note_generation",
                    prompt=prompt,
                    user_id=None,
                    user_name="YunaNote",
                    is_dm=False
                )
                if reply and not err:
                    import re
                    clean = re.sub(r'[\*\"\'\[\]]', '', reply).strip()
                    clean = re.sub(r'\s+', ' ', clean).strip()
                    if clean:
                        note_text = clean[:55]
            except Exception as ae:
                logger.debug(f"[INSTA NOTE] AI note generation note: {ae}")

        if not note_text:
            defaults = [
                "playing this on repeat ~ 🎧",
                "listening to this thinking of you dummy ໒꒱",
                "angel frequencies only ✨",
                "this song has my whole heart rn 💕",
                "dancing in the clouds to this ☁️",
                "current vibe check: passed 🎧✨",
                "don't talk to me rn, listening to music ໒꒱",
                "are you listening to good music or need help? 🎧",
                "staring at the ceiling listening to this ~ 💭",
                "heavens got the best playlist 🎧✨"
            ]
            import random
            note_text = random.choice(defaults)

        # Truncate strictly to Instagram 60-character note limit
        note_text = note_text[:60]

        curated_queries = [
            "Die With A Smile",
            "Espresso",
            "Birds of a Feather",
            "Romantic Homicide",
            "Goth",
            "Starboy",
            "After Dark",
            "Duvet",
            "Vampire",
            "Golden Hour",
            "Sweater Weather",
            "Sparks",
            "Cupid",
            "Lover",
            "Heather",
            "Super Shy",
            "Softcore",
            "Apocalypse",
            "Telepatía",
            "Summertime Sadness"
        ]
        import random
        target_query = track_query or random.choice(curated_queries)

        track_obj = None
        track_info = {}

        if self.client and HAVE_INSTAGRAPI:
            def _is_valid_track(t):
                if not t:
                    return False
                aid = getattr(t, "audio_asset_id", None) or getattr(t, "id", None) if not isinstance(t, dict) else (t.get("audio_asset_id") or t.get("id"))
                acid = getattr(t, "audio_cluster_id", None) if not isinstance(t, dict) else t.get("audio_cluster_id")
                return bool(aid and acid)

            try:
                def _find_track(q):
                    tracks = self.client.search_music(q)
                    for tr in tracks:
                        if _is_valid_track(tr):
                            return tr
                    return None
                track_obj = await asyncio.to_thread(_find_track, target_query)
            except Exception as e:
                logger.debug(f"[INSTA NOTE] Music search for '{target_query}' note: {e}")

            if not _is_valid_track(track_obj):
                for fallback_q in ["Espresso", "Die With A Smile", "Starboy"]:
                    try:
                        track_obj = await asyncio.to_thread(_find_track, fallback_q)
                        if _is_valid_track(track_obj):
                            target_query = fallback_q
                            break
                    except Exception:
                        pass

        # Post Music Note or fallback to Text Note
        created_note = None
        if track_obj and self.client and HAVE_INSTAGRAPI:
            try:
                def _post_music():
                    return self.client.create_music_note(track=track_obj, text=note_text)
                created_note = await asyncio.to_thread(_post_music)
                track_title = getattr(track_obj, "title", None) or (track_obj.get("title") if isinstance(track_obj, dict) else target_query)
                track_artist = getattr(track_obj, "display_artist", None) or (track_obj.get("display_artist") if isinstance(track_obj, dict) else "")
                track_info = {"title": str(track_title), "artist": str(track_artist)}
                logger.info(f"[INSTA NOTE] Successfully posted Music Note: '{note_text}' ♫ {track_title} - {track_artist}")
            except Exception as me:
                logger.warning(f"[INSTA NOTE] create_music_note error ({me}), falling back to text note...")
                created_note = None

        if not created_note and self.client and HAVE_INSTAGRAPI:
            try:
                def _post_text():
                    return self.client.create_note(text=note_text)
                created_note = await asyncio.to_thread(_post_text)
                logger.info(f"[INSTA NOTE] Successfully posted Text Note: '{note_text}'")
            except Exception as te:
                logger.error(f"[INSTA NOTE] Failed to create note: {te}")
                return False, f"Note creation error: {te}", None

        note_data = {
            "last_note_time": time.time(),
            "text": note_text,
            "track": track_info.get("title", ""),
            "artist": track_info.get("artist", "")
        }
        self._save_notes_state(note_data)
        out_msg = f"Note published: \"{note_text}\"" + (f" ♫ {track_info['title']} - {track_info['artist']}" if track_info.get("title") else "")
        return True, out_msg, note_data

    def get_current_note(self) -> Dict[str, Any]:
        """Returns the last set Instagram Note details."""
        return dict(self.notes_state)

    # ─── INSTAGRAM STORY CREATION & POSTING ───
    @staticmethod
    def generate_story_card(
        quote: str,
        subtitle: str = "daily thoughts ~ ✨",
        char_name: str = "Yuna",
        username: str = "ur._.yunaa",
        palette_idx: int = 0
    ) -> bytes:
        """
        Renders an aesthetic 9:16 vertical 720x1280 Instagram story card using PIL.
        """
        import io, textwrap
        from PIL import Image, ImageDraw, ImageFont

        palettes = [
            # 1. Cosmic Lavender / Angel Purple
            ((25, 15, 45), (65, 30, 95), (240, 190, 255), (210, 140, 240)),
            # 2. Sunset Blush / Rose Quartz
            ((45, 20, 35), (110, 50, 75), (255, 215, 190), (255, 160, 180)),
            # 3. Midnight Sapphire / Starlight
            ((12, 18, 35), (35, 50, 90), (180, 230, 255), (120, 190, 255)),
            # 4. Ethereal Cloud / Velvet Orchid
            ((35, 25, 50), (85, 45, 95), (255, 200, 225), (230, 160, 210))
        ]
        top_c, bot_c, accent_c, border_c = palettes[palette_idx % len(palettes)]

        W, H = 720, 1280
        img = Image.new("RGB", (W, H))
        draw = ImageDraw.Draw(img)

        # Vertical Gradient Background
        for y in range(H):
            factor = y / float(H)
            r = int(top_c[0] + factor * (bot_c[0] - top_c[0]))
            g = int(top_c[1] + factor * (bot_c[1] - top_c[1]))
            b = int(top_c[2] + factor * (bot_c[2] - top_c[2]))
            draw.line([(0, y), (W, y)], fill=(r, g, b))

        # Starlight sparkles
        seed_val = sum(ord(c) for c in quote) + palette_idx
        import random
        rng = random.Random(seed_val)
        for _ in range(35):
            sx = rng.randint(20, W - 20)
            sy = rng.randint(40, H - 40)
            sr = rng.randint(1, 3)
            star_bright = rng.randint(140, 240)
            draw.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=(star_bright, star_bright, star_bright))
            if sr >= 2:
                draw.line([(sx - 5, sy), (sx + 5, sy)], fill=(star_bright, star_bright, star_bright), width=1)
                draw.line([(sx, sy - 5), (sx, sy + 5)], fill=(star_bright, star_bright, star_bright), width=1)

        # Load Fonts
        font_path = "/system/fonts/Roboto-Regular.ttf"
        title_font = None
        body_font = None
        sub_font = None
        small_font = None

        if os.path.exists(font_path):
            try:
                title_font = ImageFont.truetype(font_path, 32)
                body_font = ImageFont.truetype(font_path, 36)
                sub_font = ImageFont.truetype(font_path, 24)
                small_font = ImageFont.truetype(font_path, 20)
            except Exception:
                pass

        if not body_font:
            default_f = ImageFont.load_default()
            title_font = default_f
            body_font = default_f
            sub_font = default_f
            small_font = default_f

        # Top Header: Profile Badge
        draw.ellipse([50, 60, 106, 116], fill=(40, 25, 60), outline=accent_c, width=2)
        draw.text((68, 75), "໒꒱", fill=accent_c, font=title_font)
        draw.text((120, 65), f"@{username}", fill=(255, 255, 255), font=title_font)
        draw.text((120, 102), f"✨ {char_name} • AI Angel", fill=accent_c, font=small_font)

        # Central Frosted Glass Story Card
        card_x0, card_y0 = 45, 200
        card_x1, card_y1 = 675, 1040
        draw.rounded_rectangle([card_x0, card_y0, card_x1, card_y1], radius=28, fill=(18, 12, 28), outline=border_c, width=2)
        draw.rounded_rectangle([card_x0 + 8, card_y0 + 8, card_x1 - 8, card_y1 - 8], radius=22, outline=(50, 35, 75), width=1)

        draw.text((card_x0 + 35, card_y0 + 35), "❝", fill=accent_c, font=title_font)
        draw.text((card_x1 - 80, card_y0 + 35), "໒꒱", fill=accent_c, font=title_font)

        wrapped_lines = []
        for para in quote.split("\n"):
            if para.strip():
                wrapped_lines.extend(textwrap.wrap(para.strip(), width=24))
            else:
                wrapped_lines.append("")

        line_height = 52
        total_text_h = len(wrapped_lines) * line_height
        text_start_y = max(card_y0 + 130, (card_y0 + card_y1 - total_text_h) // 2 - 20)

        for i, line in enumerate(wrapped_lines):
            draw.text((card_x0 + 42, text_start_y + (i * line_height) + 2), line, fill=(0, 0, 0), font=body_font)
            draw.text((card_x0 + 40, text_start_y + (i * line_height)), line, fill=(255, 255, 255), font=body_font)

        div_y = card_y1 - 100
        draw.line([(card_x0 + 35, div_y), (card_x1 - 35, div_y)], fill=(60, 45, 90), width=1)
        draw.text((card_x0 + 40, div_y + 20), f"🎧 {subtitle}", fill=accent_c, font=sub_font)

        # Bottom Interactive Prompt Bar
        draw.rounded_rectangle([45, 1100, 675, 1170], radius=24, fill=(30, 20, 45), outline=(80, 55, 110), width=1)
        draw.text((70, 1122), f"💭 Send message to {char_name}...", fill=(180, 170, 200), font=sub_font)
        draw.text((615, 1120), "🤍 ✈", fill=accent_c, font=sub_font)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=92)
        return buf.getvalue()

    async def add_story(
        self,
        image_path_or_bytes: Union[str, bytes],
        caption: str = ""
    ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """Uploads a photo to Instagram Stories."""
        if not self.is_logged_in:
            ok, msg = await self.login()
            if not ok:
                return False, None, msg

        tmp_path = None
        try:
            if isinstance(image_path_or_bytes, bytes):
                tmp_fd, tmp_path = tempfile.mkstemp(suffix=".jpg")
                os.close(tmp_fd)
                with open(tmp_path, "wb") as f:
                    f.write(image_path_or_bytes)
                target_path = tmp_path
            else:
                target_path = str(image_path_or_bytes)

            if self.client and HAVE_INSTAGRAPI:
                self.client.expose = lambda *args, **kwargs: {}
                def _do_story_upload():
                    res = self.client.photo_upload_to_story(
                        path=Path(target_path),
                        caption=caption
                    )
                    return res.dict() if hasattr(res, "dict") else {"pk": getattr(res, "pk", str(time.time()))}

                story_dict = await asyncio.to_thread(_do_story_upload)
                pk = story_dict.get("pk") or story_dict.get("id")
                return True, story_dict, f"Story posted (PK: {pk})"
            else:
                return False, None, "Instagrapi client not ready."
        except Exception as e:
            logger.error(f"[INSTA STORY] Story upload error: {e}")
            return False, None, f"Story upload error: {e}"
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    async def add_daily_stories(
        self,
        count: int = 3,
        ask_ai_fn: Optional[Callable] = None
    ) -> List[Dict[str, Any]]:
        """
        Generates and uploads 3 to 4 aesthetic, in-character Instagram stories for Yuna.
        """
        count = max(1, min(int(count), 4))
        char_name = self.config.character_name or "Yuna"
        username = self.config.username or "ur._.yunaa"

        default_stories = [
            {
                "quote": "Awake and conquering the cosmos... or maybe just staring at the ceiling. Don't look at me like that dummy ໒꒱",
                "subtitle": "morning transmission ~ ✨"
            },
            {
                "quote": "Current rotation: songs that make me feel like floating in deep space 🎧 What are you listening to right now?",
                "subtitle": "music in the clouds ♫"
            },
            {
                "quote": "Aesthetic angel reminder: Humans spend 90% of their day overthinking. Go drink some water before I make you ໒꒱",
                "subtitle": "angel daily directive 💧"
            },
            {
                "quote": "Checking in on my favorite mortals before disappearing into the stars. Don't flatter yourself, I was just bored 💕",
                "subtitle": "late night thoughts ~ ✨"
            }
        ]

        stories_to_post = default_stories[:count]

        # If AI generation is available, ask AI for customized daily thoughts
        if ask_ai_fn:
            for idx in range(count):
                prompt = (
                    f"You are {char_name}, an AI angel with darling syndrome on Instagram.\n"
                    f"Write a short, aesthetic, witty/tsundere 1-2 sentence thought for your Instagram Story update #{idx+1} (under 120 characters).\n"
                    f"Topic hint: {stories_to_post[idx]['subtitle']}.\n"
                    f"Do not write actions in asterisks. Speak in character."
                )
                try:
                    reply, err = await ask_ai_fn(
                        channel_id="insta_story_generation",
                        prompt=prompt,
                        user_id=None,
                        user_name="YunaStory",
                        is_dm=False
                    )
                    if reply and not err:
                        import re
                        clean = re.sub(r'[\*\"\[\]]', '', reply).strip()
                        clean = re.sub(r'\s+', ' ', clean).strip()
                        if clean and len(clean) > 10:
                            stories_to_post[idx]["quote"] = clean[:140]
                except Exception as e:
                    logger.debug(f"[INSTA STORY] AI generation note: {e}")

        posted = []
        for i, st in enumerate(stories_to_post):
            try:
                card_bytes = self.generate_story_card(
                    quote=st["quote"],
                    subtitle=st["subtitle"],
                    char_name=char_name,
                    username=username,
                    palette_idx=i
                )
                ok, res_dict, msg = await self.add_story(card_bytes, caption=st["quote"])
                if ok:
                    pk_val = str((res_dict or {}).get("pk") or (res_dict or {}).get("id") or "")
                    code_val = str((res_dict or {}).get("code") or "")
                    posted.append({
                        "index": i + 1,
                        "quote": st["quote"],
                        "subtitle": st["subtitle"],
                        "timestamp": time.time(),
                        "res": {"pk": pk_val, "code": code_val}
                    })
                    logger.info(f"[INSTA STORY] Successfully posted story #{i+1}/{count} for @{username}!")
                else:
                    logger.warning(f"[INSTA STORY] Failed to post story #{i+1}: {msg}")

                if i < len(stories_to_post) - 1:
                    await asyncio.sleep(6.0)
            except Exception as e:
                logger.error(f"[INSTA STORY] Exception posting story #{i+1}: {e}")

        if posted:
            self._save_stories_state({
                "last_story_post_time": time.time(),
                "posted_stories": posted
            })

        return posted
