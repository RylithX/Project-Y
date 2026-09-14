"""
Central Social Manager Orchestrator.
Coordinates:
- X (Twitter) Posting, Mention Replying, DM Replying
- Instagram Photo/Video/Reel Posting, Story Viewing, Follow Request Auto-Approval, DM Video Watching
- Photon (https://photon.codes/) Multi-Channel Gateway
- Burst Video / Multi-Media Queue Processing
- Persona-driven Multimodal Analysis & Auto-Captioning
"""

import asyncio
import io
import logging
import os
import time
from typing import Optional, Dict, Any, List, Tuple, Callable, Union

from .config import load_social_config, XConfig, InstagramConfig, PhotonConfig, MediaQueueConfig
from .x_client import XClient
from .insta_client import InstagramClient
from .photon_client import PhotonClient
from .media_queue import SocialMediaQueue, QueuedVideoItem, UserMediaBatch, global_media_queue
from .vision_analyzer import SocialContentAnalyzer
from .insta_memory import insta_memory

logger = logging.getLogger("Social.Manager")

def _clean_social_reply(text: str) -> str:
    """Cleans roleplay narration actions while preserving rich dialogue, paragraphs, and lists."""
    if not text:
        return ""
    import re
    cleaned = text
    cleaned = re.sub(r'[ \t]+', ' ', cleaned)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
    return cleaned

class SocialManager:
    """
    Unified manager for all external social media channels and queue processing.
    """

    def __init__(
        self,
        bot_config: Optional[Dict[str, Any]] = None,
        ask_ai_fn: Optional[Callable] = None,
        ask_vision_fn: Optional[Callable] = None,
        watch_video_fn: Optional[Callable] = None,
        memory_update_fn: Optional[Callable] = None,
        speak_fn: Optional[Callable] = None,
        transcribe_fn: Optional[Callable] = None
    ):
        self.bot_config = bot_config or {}
        self.ask_ai_fn = ask_ai_fn
        self.ask_vision_fn = ask_vision_fn
        self.watch_video_fn = watch_video_fn
        self.memory_update_fn = memory_update_fn
        self.speak_fn = speak_fn
        self.transcribe_fn = transcribe_fn

        social_cfgs = load_social_config(self.bot_config)
        self.x_cfg: XConfig = social_cfgs["x"]
        self.insta_cfg: InstagramConfig = social_cfgs["instagram"]
        self.photon_cfg: PhotonConfig = social_cfgs["photon"]
        self.queue_cfg: MediaQueueConfig = social_cfgs["queue"]

        self.x_client = XClient(self.x_cfg)
        self.insta_client = InstagramClient(self.insta_cfg)
        self.photon_client = PhotonClient(self.photon_cfg)
        self.vision_analyzer = SocialContentAnalyzer(self.bot_config)
        self.media_queue = global_media_queue

        self._running = False
        self._x_poll_task: Optional[asyncio.Task] = None
        self._insta_poll_task: Optional[asyncio.Task] = None
        self._insta_dm_task: Optional[asyncio.Task] = None
        self._insta_reel_task: Optional[asyncio.Task] = None
        self._insta_follow_task: Optional[asyncio.Task] = None
        self._insta_story_task: Optional[asyncio.Task] = None
        self._insta_activity_task: Optional[asyncio.Task] = None
        self._insta_note_task: Optional[asyncio.Task] = None
        self._insta_story_poster_task: Optional[asyncio.Task] = None

        # Hook media queue processor
        self.media_queue.set_processor(self._process_media_batch)

    def update_config(self, new_config: Dict[str, Any]):
        """Refreshes configuration dynamically and applies it live to workers."""
        old_insta_session = getattr(self.insta_cfg, "session_id", "")
        old_insta_enabled = getattr(self.insta_cfg, "enabled", False)

        self.bot_config = new_config
        social_cfgs = load_social_config(new_config)
        self.x_cfg = social_cfgs["x"]
        self.insta_cfg = social_cfgs["instagram"]
        self.photon_cfg = social_cfgs["photon"]
        self.queue_cfg = social_cfgs["queue"]

        self.x_client.config = self.x_cfg
        self.x_client._init_tweepy()
        self.insta_client.config = self.insta_cfg
        self.photon_client.config = self.photon_cfg
        self.vision_analyzer.config = self.bot_config

        session_changed = (self.insta_cfg.session_id and self.insta_cfg.session_id != old_insta_session)
        user_changed = (self.insta_cfg.username and self.insta_cfg.username != getattr(self.insta_client, "username", None))
        if session_changed or user_changed:
            self.insta_client.is_logged_in = False
            self.insta_client.client = None
            self.insta_client.user_id = None
            self.insta_client.username = self.insta_cfg.username
            self.insta_client._load_processed_dms()

        logger.info(f"[SOCIAL MANAGER] Updated configs dynamically. Instagram: enabled={self.insta_cfg.enabled}, username={self.insta_cfg.username}, persona={self.insta_cfg.character_name}")

        # If running, dynamically adjust background tasks
        if self._running:
            if self.insta_cfg.enabled and self.insta_client.is_configured():
                dm_task = getattr(self, "_insta_dm_task", None)
                if not old_insta_enabled or session_changed or user_changed or dm_task is None or dm_task.done():
                    asyncio.create_task(self._start_insta_workers(relogin=session_changed or user_changed))
            elif not self.insta_cfg.enabled:
                self._stop_insta_workers()

    update_configs = update_config

    async def _start_insta_workers(self, relogin: bool = False):
        """Starts or restarts Instagram background workers."""
        try:
            self._stop_insta_workers()
            if relogin or not self.insta_client.is_logged_in:
                await self.insta_client.login()
            if not self.insta_client.is_logged_in:
                logger.warning("[SOCIAL MANAGER] Instagram login failed or not ready; workers not started.")
                return

            self._insta_dm_task = asyncio.create_task(self._insta_dm_worker())
            self._insta_reel_task = asyncio.create_task(self._insta_reel_feed_worker())
            if self.insta_cfg.auto_approve_follow_requests:
                self._insta_follow_task = asyncio.create_task(self._insta_follow_worker())
            if self.insta_cfg.watch_follower_stories:
                self._insta_story_task = asyncio.create_task(self._insta_story_worker())
            if getattr(self.insta_cfg, "auto_respond_likes", True):
                self._insta_activity_task = asyncio.create_task(self._insta_activity_worker())
            if getattr(self.insta_cfg, "auto_music_notes", True):
                self._insta_note_task = asyncio.create_task(self._insta_note_worker())
            if getattr(self.insta_cfg, "auto_post_stories", True):
                self._insta_story_poster_task = asyncio.create_task(self._insta_story_poster_worker())
            logger.info("[SOCIAL MANAGER] Instagram background workers started successfully.")
        except Exception as e:
            logger.error(f"[SOCIAL MANAGER] Error starting Instagram workers: {e}")

    def _stop_insta_workers(self):
        """Safely stops active Instagram workers."""
        for attr in [
            "_insta_dm_task", "_insta_reel_task", "_insta_follow_task",
            "_insta_story_task", "_insta_activity_task",
            "_insta_note_task", "_insta_story_poster_task"
        ]:
            task = getattr(self, attr, None)
            if task and not task.done():
                task.cancel()
            setattr(self, attr, None)

    async def start(self):
        """Starts background workers for X, Instagram, and Media Queue."""
        if self._running:
            return
        self._running = True

        await self.media_queue.start()

        # 1. Start X Polling if enabled
        if self.x_cfg.enabled and self.x_client.is_configured():
            self._x_poll_task = asyncio.create_task(self._x_polling_worker())
            logger.info("[SOCIAL MANAGER] X (Twitter) background poller started.")

        # 2. Start Instagram Worker if enabled
        if self.insta_cfg.enabled and self.insta_client.is_configured():
            asyncio.create_task(self._start_insta_workers(relogin=False))

    async def stop(self):
        """Stops background workers."""
        self._running = False
        await self.media_queue.stop()
        if self._x_poll_task:
            self._x_poll_task.cancel()
        if getattr(self, "_insta_dm_task", None):
            self._insta_dm_task.cancel()
        if getattr(self, "_insta_follow_task", None):
            self._insta_follow_task.cancel()
        if getattr(self, "_insta_story_task", None):
            self._insta_story_task.cancel()
        if getattr(self, "_insta_activity_task", None):
            self._insta_activity_task.cancel()
        await self.photon_client.close()

    # ─── DISCORD TRIGGER: POST TO X WITH AUTO-ANALYSIS & CAPTION ───
    async def post_to_x_with_analysis(
        self,
        media_bytes: Optional[bytes] = None,
        media_filename: str = "media.jpg",
        media_path: Optional[str] = None,
        media_url: Optional[str] = None,
        user_prompt: str = ""
    ) -> Tuple[bool, str, str, Optional[str]]:
        """
        Analyzes screenshot/video, generates Yuna's caption, and posts to X.
        Returns: (success, generated_caption, analysis_summary, tweet_url)
        """
        is_video = media_filename.lower().endswith((".mp4", ".mov", ".mkv", ".webm", ".avi")) or (media_url and any(media_url.lower().endswith(ext) for ext in [".mp4", ".mov"]))
        media_type = "video" if is_video else "image"

        # 1. Vision & Multimodal Analysis + Caption Generation
        caption, analysis, meta = await self.vision_analyzer.analyze_and_caption(
            media_bytes=media_bytes,
            media_path=media_path,
            media_url=media_url,
            media_type=media_type,
            platform="x",
            user_prompt=user_prompt,
            ask_ai_fn=self.ask_ai_fn,
            ask_vision_fn=self.ask_vision_fn,
            media_analyzer_fn=self.watch_video_fn
        )

        # 2. Upload media if provided
        media_ids = []
        if media_bytes:
            m_id, err = await self.x_client.upload_media(media_bytes, media_filename)
            if m_id:
                media_ids.append(m_id)
            elif err:
                logger.warning(f"[SOCIAL MANAGER] X Media upload failed ({err}), posting text-only.")
        elif media_path and os.path.exists(media_path):
            with open(media_path, "rb") as f:
                b = f.read()
            m_id, err = await self.x_client.upload_media(b, Path(media_path).name)
            if m_id:
                media_ids.append(m_id)

        # 3. Post Tweet
        ok, tweet_data, msg_or_url = await self.x_client.post_tweet(text=caption, media_ids=media_ids if media_ids else None)
        return ok, caption, analysis, (msg_or_url if ok else None)

    # ─── DISCORD TRIGGER: POST TO INSTAGRAM WITH AUTO-ANALYSIS & CAPTION ───
    async def post_to_insta_with_analysis(
        self,
        media_bytes: Optional[bytes] = None,
        media_filename: str = "media.jpg",
        media_path: Optional[str] = None,
        media_url: Optional[str] = None,
        user_prompt: str = ""
    ) -> Tuple[bool, str, str, Optional[str]]:
        """
        Analyzes screenshot/video, generates Yuna's caption, and posts to Instagram.
        Returns: (success, generated_caption, analysis_summary, post_url)
        """
        is_video = media_filename.lower().endswith((".mp4", ".mov", ".mkv", ".webm", ".avi")) or (media_url and any(media_url.lower().endswith(ext) for ext in [".mp4", ".mov"]))
        media_type = "video" if is_video else "image"

        # 1. Vision & Multimodal Analysis + Caption Generation
        caption, analysis, meta = await self.vision_analyzer.analyze_and_caption(
            media_bytes=media_bytes,
            media_path=media_path,
            media_url=media_url,
            media_type=media_type,
            platform="instagram",
            user_prompt=user_prompt,
            ask_ai_fn=self.ask_ai_fn,
            ask_vision_fn=self.ask_vision_fn,
            media_analyzer_fn=self.watch_video_fn
        )

        # 2. Post to Instagram
        if is_video:
            target_file = media_path
            tmp_created = False
            if not target_file and media_bytes:
                import tempfile
                tmp_fd, target_file = tempfile.mkstemp(suffix=Path(media_filename).suffix or ".mp4")
                os.close(tmp_fd)
                with open(target_file, "wb") as f:
                    f.write(media_bytes)
                tmp_created = True
            
            if target_file:
                ok, p_data, p_url = await self.insta_client.post_video(target_file, caption=caption, is_reel=True)
                if tmp_created and os.path.exists(target_file):
                    try:
                        os.remove(target_file)
                    except Exception:
                        pass
                return ok, caption, analysis, (p_url if ok else None)
            else:
                return False, caption, analysis, None
        else:
            payload = media_bytes if media_bytes else media_path
            if not payload:
                return False, caption, analysis, "No image payload provided."
            ok, p_data, p_url = await self.insta_client.post_photo(payload, caption=caption)
            return ok, caption, analysis, (p_url if ok else None)

    # ─── MEDIA QUEUE BATCH PROCESSOR ───
    async def _process_media_batch(self, batch: UserMediaBatch):
        """
        Processes queued videos sequentially when a user sends multiple videos at once.
        Synthesizes a cohesive analysis across all videos.
        """
        count = len(batch.items)
        first_item = batch.items[0]
        logger.info(f"[SOCIAL MANAGER] Processing batch of {count} videos for {batch.batch_key}...")

        all_video_contexts = []
        for i, item in enumerate(batch.items, 1):
            target = item.url_or_path
            if self.watch_video_fn:
                try:
                    c_data, rep = await self.watch_video_fn(target, bot_config=self.bot_config)
                    all_video_contexts.append(f"=== [VIDEO {i}/{count}] Source: {item.url_or_path} ===\n{c_data}")
                except Exception as ve:
                    all_video_contexts.append(f"=== [VIDEO {i}/{count}] Source: {item.url_or_path} ===\nCould not watch: {ve}")
            else:
                all_video_contexts.append(f"=== [VIDEO {i}/{count}] ===\nVideo link: {item.url_or_path}")

        combined_context = "\n\n".join(all_video_contexts)
        prompt = (
            f"The user ({first_item.user_name}) shared {count} videos at once:\n\n"
            f"{combined_context}\n\n"
            f"User's accompanying note: \"{first_item.message_context or 'Check out these videos!'}\"\n\n"
            f"React to what you watched in 1-2 short, punchy sentences in character. "
            f"STRICT RULES: DO NOT roleplay. DO NOT write actions in asterisks like *smiles* or *laughs*. Keep it concise and natural."
        )

        if self.ask_ai_fn:
            reply, err = await self.ask_ai_fn(
                channel_id=first_item.channel_id,
                prompt=prompt,
                user_id=first_item.user_id,
                user_name=first_item.user_name,
                is_dm=(first_item.source_platform in ("instagram", "x"))
            )
            if not err and reply:
                reply = _clean_social_reply(reply)
                # Deliver response to the appropriate platform
                if first_item.source_platform == "instagram":
                    await self.insta_client.send_dm_message(first_item.channel_id, reply)
                elif first_item.source_platform == "x":
                    await self.x_client.send_dm(first_item.user_id, reply)
                elif first_item.raw_attachment and hasattr(first_item.raw_attachment, "reply_callback"):
                    try:
                        await first_item.raw_attachment.reply_callback(reply)
                    except Exception:
                        pass

    # ─── X BACKGROUND POLLING WORKER ───
    async def _x_polling_worker(self):
        """Polls X for mentions and DMs, then replies as Yuna."""
        while self._running:
            try:
                # 1. Handle Mentions
                if self.x_cfg.auto_reply_mentions:
                    mentions = await self.x_client.fetch_mentions(max_results=10)
                    for m in mentions:
                        m_id = m["id"]
                        if self.x_client.last_mention_id and int(m_id) <= int(self.x_client.last_mention_id):
                            continue
                        self.x_client.last_mention_id = m_id
                        
                        # Like mention if enabled
                        if self.x_cfg.auto_like_mentions:
                            await self.x_client.like_tweet(m_id)

                        # Generate AI response
                        if self.ask_ai_fn:
                            x_name = getattr(self.x_cfg, "character_name", "") or getattr(self.x_cfg, "name", "") or "your persona"
                            prompt = (
                                f"User @{m.get('author_username', 'someone')} mentioned you on X (Twitter): \"{m['text']}\"\n\n"
                                f"Reply concisely in character as {x_name}. STRICT RULES: DO NOT roleplay. DO NOT write actions in asterisks (no *smiles*, *laughs*, etc.). "
                                f"Keep your tweet short (1-2 sentences), snappy, and natural."
                            )
                            reply, err = await self.ask_ai_fn(
                                channel_id=f"x_mention_{m_id}",
                                prompt=prompt,
                                user_id=m.get("author_id"),
                                user_name=m.get("author_username")
                            )
                            if not err and reply:
                                reply_clean = _clean_social_reply(reply)
                                tweet_text = reply_clean[:275] if len(reply_clean) > 275 else reply_clean
                                await self.x_client.reply_to_tweet(m_id, tweet_text)
                                logger.info(f"[X POLLE] Replied to mention {m_id} from @{m.get('author_username')}")

                # 2. Handle DMs
                if self.x_cfg.auto_reply_dms:
                    dms = await self.x_client.fetch_direct_messages(max_results=10)
                    for dm in dms:
                        dm_id = dm["id"]
                        if self.x_client.last_dm_id and int(dm_id) <= int(self.x_client.last_dm_id):
                            continue
                        self.x_client.last_dm_id = dm_id

                        if self.ask_ai_fn:
                            x_name = getattr(self.x_cfg, "character_name", "") or getattr(self.x_cfg, "name", "") or "your persona"
                            prompt = (
                                f"User sent you a Direct Message (DM) on X: \"{dm['text']}\"\n\n"
                                f"Reply concisely in character as {x_name}. STRICT RULES: DO NOT roleplay. DO NOT write actions in asterisks (no *smiles*, *sighs*, etc.). "
                                f"Keep your reply short (1-2 sentences), punchy, and direct."
                            )
                            reply, err = await self.ask_ai_fn(
                                channel_id=f"x_dm_{dm.get('sender_id')}",
                                prompt=prompt,
                                user_id=dm.get("sender_id"),
                                is_dm=True
                            )
                            if not err and reply:
                                reply_clean = _clean_social_reply(reply)
                                await self.x_client.send_dm(dm["sender_id"], reply_clean)
                                logger.info(f"[X POLLE] Replied to DM {dm_id}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[X WORKER] Error in polling loop: {e}")

            await asyncio.sleep(max(10, self.x_cfg.poll_interval_seconds))

    @staticmethod
    def _parse_msg_timestamp(msg: Any) -> float:
        """Safely parses UNIX timestamp in seconds from any message representation."""
        if not msg:
            return 0.0
        raw = msg.get("timestamp") if isinstance(msg, dict) else getattr(msg, "timestamp", None)
        if raw is None:
            return 0.0
        import datetime
        if isinstance(raw, datetime.datetime):
            return raw.timestamp()
        if isinstance(raw, (int, float)):
            return float(raw) / 1e6 if raw > 1e11 else float(raw)
        try:
            val = float(raw)
            return val / 1e6 if val > 1e11 else val
        except Exception:
            return 0.0

    @staticmethod
    def _extract_msg_sender_id(msg: Any) -> str:
        """Safely extracts sender ID from any message representation."""
        if not msg:
            return ""
        if isinstance(msg, dict):
            return str(msg.get("user_id") or msg.get("sender_id") or msg.get("user", {}).get("pk") or "")
        return str(getattr(msg, "user_id", "") or getattr(msg, "sender_id", ""))

    def _extract_media_from_msg(self, msg: Any) -> Tuple[Optional[str], Optional[str], Optional[str], bool, Optional[str]]:
        """
        Extracts (video_url, image_url, audio_url, is_call_event, media_type_label) from an Instagram DM message
        across Instagrapi model objects and nested Web REST dictionaries.
        """
        video_url = None
        image_url = None
        audio_url = None
        is_call_event = False
        label = None

        m_dict = msg if isinstance(msg, dict) else (msg.dict() if hasattr(msg, "dict") else getattr(msg, "__dict__", {}))
        item_type = str(m_dict.get("item_type") or getattr(msg, "item_type", "") or "").lower()

        # 0. Voice Note / Audio Clip
        v_med = m_dict.get("voice_media") or getattr(msg, "voice_media", None) or m_dict.get("audio") or getattr(msg, "audio", None) or m_dict.get("direct_audio") or getattr(msg, "direct_audio", None)
        if not v_med and (item_type in ("voice_media", "audio", "direct_audio") or (isinstance(m_dict.get("media"), dict) and m_dict.get("media", {}).get("media_type") == 11)):
            v_med = m_dict.get("media") or m_dict.get("visual_media")

        if v_med or item_type in ("voice_media", "audio", "direct_audio"):
            vm_dict = v_med if isinstance(v_med, dict) else (v_med.dict() if hasattr(v_med, "dict") else getattr(v_med, "__dict__", {}))
            if isinstance(vm_dict.get("voice_media"), dict):
                vm_dict = vm_dict["voice_media"]

            media_sub = vm_dict.get("media", {}) if isinstance(vm_dict.get("media"), dict) else (m_dict.get("media", {}) if isinstance(m_dict.get("media"), dict) else {})
            audio_sub = media_sub.get("audio", {}) if isinstance(media_sub.get("audio"), dict) else (vm_dict.get("audio", {}) if isinstance(vm_dict.get("audio"), dict) else {})

            if isinstance(audio_sub, dict):
                audio_url = audio_sub.get("audio_src") or audio_sub.get("url")
            if not audio_url and isinstance(media_sub, dict):
                audio_url = media_sub.get("audio_src") or media_sub.get("url")
            if not audio_url and isinstance(vm_dict, dict):
                audio_url = vm_dict.get("audio_src") or vm_dict.get("url")
            if audio_url:
                label = "Voice Note"

        # 0.5. Video Call / Audio Call Event (Only if not a Voice Note)
        call_evt = m_dict.get("video_call_event") or getattr(msg, "video_call_event", None)
        if not audio_url and (call_evt or item_type in ("video_call_event", "call_event", "action_log")):
            if call_evt or any(k in item_type for k in ["call", "video_call", "audio_call"]):
                is_call_event = True
                label = "Call Event"

        # 1. Clip / Reel (Handles nested {"clip": {"clip": {...}}} from Web REST inbox)
        clip = m_dict.get("clip") or getattr(msg, "clip", None)
        if clip and not audio_url:
            c_dict = clip if isinstance(clip, dict) else (clip.dict() if hasattr(clip, "dict") else getattr(clip, "__dict__", {}))
            if isinstance(c_dict.get("clip"), dict):
                c_dict = c_dict["clip"]

            video_url = c_dict.get("video_url") or getattr(clip, "video_url", None)
            if not video_url:
                v_vers = c_dict.get("video_versions") or getattr(clip, "video_versions", None) or []
                if v_vers and len(v_vers) > 0:
                    video_url = v_vers[0].get("url") if isinstance(v_vers[0], dict) else getattr(v_vers[0], "url", None)

            code = c_dict.get("code") or getattr(clip, "code", None)
            if not video_url and code:
                video_url = f"https://www.instagram.com/reel/{code}/"

            image_url = c_dict.get("thumbnail_url") or getattr(clip, "thumbnail_url", None)
            if not image_url and c_dict.get("image_versions2"):
                cands = c_dict.get("image_versions2", {}).get("candidates", [])
                if cands and len(cands) > 0:
                    image_url = cands[0].get("url")
            label = "Reel"

        # 2. Media Share (Post / Carousel / Shared Reel)
        m_share = m_dict.get("media_share") or getattr(msg, "media_share", None)
        if not video_url and not audio_url and m_share:
            ms_dict = m_share if isinstance(m_share, dict) else (m_share.dict() if hasattr(m_share, "dict") else getattr(m_share, "__dict__", {}))
            if isinstance(ms_dict.get("media_share"), dict):
                ms_dict = ms_dict["media_share"]
            elif isinstance(ms_dict.get("media"), dict):
                ms_dict = ms_dict["media"]

            video_url = ms_dict.get("video_url") or getattr(m_share, "video_url", None)
            if not video_url:
                v_vers = ms_dict.get("video_versions") or getattr(m_share, "video_versions", None) or []
                if v_vers and len(v_vers) > 0:
                    video_url = v_vers[0].get("url") if isinstance(v_vers[0], dict) else getattr(v_vers[0], "url", None)

            code = ms_dict.get("code") or getattr(m_share, "code", None)
            m_type = ms_dict.get("media_type") or getattr(m_share, "media_type", 1)
            if not video_url and code and m_type == 2:
                video_url = f"https://www.instagram.com/reel/{code}/"

            if not image_url and ms_dict.get("image_versions2"):
                cands = ms_dict.get("image_versions2", {}).get("candidates", [])
                if cands and len(cands) > 0:
                    image_url = cands[0].get("url")

            if not image_url:
                image_url = ms_dict.get("thumbnail_url") or getattr(m_share, "thumbnail_url", None)
            label = label or ("Reel" if m_type == 2 or video_url else "Shared Post")

        # 3. Direct Media / Visual Media (Disappearing or permanent photo/video)
        d_med = m_dict.get("media") or getattr(msg, "media", None) or m_dict.get("visual_media") or getattr(msg, "visual_media", None)
        if d_med and not audio_url and not video_url:
            dm_dict = d_med if isinstance(d_med, dict) else (d_med.dict() if hasattr(d_med, "dict") else getattr(d_med, "__dict__", {}))
            if isinstance(dm_dict.get("media"), dict):
                dm_dict = dm_dict["media"]

            video_url = video_url or dm_dict.get("video_url") or getattr(d_med, "video_url", None)
            if not video_url and (dm_dict.get("video_versions") or getattr(d_med, "video_versions", None)):
                v_vers = dm_dict.get("video_versions") or getattr(d_med, "video_versions", [])
                if v_vers and len(v_vers) > 0:
                    video_url = v_vers[0].get("url") if isinstance(v_vers[0], dict) else getattr(v_vers[0], "url", None)

            image_url = image_url or dm_dict.get("thumbnail_url") or getattr(d_med, "thumbnail_url", None)
            if not image_url and (dm_dict.get("image_versions2") or getattr(d_med, "image_versions2", None)):
                cands = (dm_dict.get("image_versions2") or getattr(d_med, "image_versions2", {})).get("candidates", [])
                if cands and len(cands) > 0:
                    image_url = cands[0].get("url")
            label = label or ("Video" if video_url else "Photo")

        # 4. XMA Share (External clips, IGTV, Reels, Threads)
        xma = m_dict.get("xma_share") or getattr(msg, "xma_share", None)
        if xma and not audio_url and not video_url:
            x_dict = xma if isinstance(xma, dict) else (xma.dict() if hasattr(xma, "dict") else getattr(xma, "__dict__", {}))
            video_url = video_url or x_dict.get("video_url") or getattr(xma, "video_url", None)
            image_url = image_url or x_dict.get("preview_url") or getattr(xma, "preview_url", None)
            label = label or "Clip"

        # 5. Animated Media (GIFs, Giphy stickers)
        anim = m_dict.get("animated_media") or getattr(msg, "animated_media", None)
        if anim and not audio_url and not video_url and not image_url:
            a_dict = anim if isinstance(anim, dict) else (anim.dict() if hasattr(anim, "dict") else getattr(anim, "__dict__", {}))
            images = a_dict.get("images") or getattr(anim, "images", {})
            if isinstance(images, dict):
                fh = images.get("fixed_height") or images.get("original") or {}
                image_url = image_url or (fh.get("url") if isinstance(fh, dict) else getattr(fh, "url", None))
            label = label or "GIF/Sticker"

        # 6. Direct Link
        link = m_dict.get("link") or getattr(msg, "link", None)
        if link and not video_url and not image_url and not audio_url:
            l_dict = link if isinstance(link, dict) else (link.dict() if hasattr(link, "dict") else getattr(link, "__dict__", {}))
            link_text = l_dict.get("text") or getattr(link, "text", "") or ""
            if link_text and ("instagram.com" in link_text or "youtube.com" in link_text or "tiktok.com" in link_text):
                video_url = link_text
                label = "Link"

        return video_url, image_url, audio_url, is_call_event, label

    # ─── INSTAGRAM DEDICATED FAST DM POLLING WORKER ───
    async def _insta_dm_worker(self):
        """
        High-frequency poller for Instagram DMs with:
        1. Smart Restart Reconciliation: Scans 10 previous messages to detect missed user messages vs already-responded threads.
        2. Debounce Message Batching: Combines multiple messages sent < 3s apart into a single contextual prompt.
        3. Burst Energy Matching: Matches multi-message rapid texting with sequential short messages (< 5).
        """
        reconciled = False
        dm_debounce_buffer: Dict[str, List[Dict[str, Any]]] = {}
        dm_last_recv_time: Dict[str, float] = {}
        in_memory_ingested_ids = set()
        last_presence_time = 0.0

        while self._running:
            try:
                if not self.insta_client.is_logged_in:
                    await self.insta_client.login()
                    if not self.insta_client.is_logged_in:
                        await asyncio.sleep(10)
                        continue

                # Push presence update to Instagram so the account stays 'Active Now' (Online)
                now = time.time()
                if now - last_presence_time > 20:
                    await self.insta_client.send_active_presence()
                    last_presence_time = now

                threads = await self.insta_client.fetch_dm_threads(limit=10)

                # 1. SMART RESTART RECONCILIATION
                if not reconciled:
                    for th_init in threads:
                        messages = th_init.get("messages", [])
                        if not messages:
                            continue
                        
                        msgs_sorted = sorted(
                            messages,
                            key=lambda m: self._parse_msg_timestamp(m)
                        )
                        last_10 = msgs_sorted[-10:]
                        
                        # Find index of latest message sent by Yuna
                        last_yuna_idx = -1
                        for idx, m in enumerate(last_10):
                            sender = self._extract_msg_sender_id(m)
                            if sender == str(self.insta_client.user_id):
                                last_yuna_idx = idx

                        if last_yuna_idx >= 0:
                            # Yuna responded up to last_yuna_idx. Mark messages up to that point as processed.
                            for m in last_10[:last_yuna_idx + 1]:
                                m_id = str(m.get("id") or m.get("pk") or "") if isinstance(m, dict) else str(getattr(m, "id", "") or getattr(m, "pk", ""))
                                if m_id:
                                    self.insta_client.processed_dm_item_ids.add(m_id)

                    self.insta_client._save_processed_dms()
                    reconciled = True
                    logger.info(f"[INSTA DM WORKER] Startup reconciliation complete. Tracking {len(self.insta_client.processed_dm_item_ids)} processed IDs.")

                # 2. INGESTION INTO DEBOUNCE BUFFER
                now = time.time()
                for th in threads:
                    th_id = str(th["thread_id"])
                    messages = th.get("messages", [])
                    if not messages:
                        continue

                    # Map and ensure profiles exist for users in this thread
                    thread_users = th.get("users", [])
                    thread_user_map = {}
                    for u in thread_users:
                        u_dict = u if isinstance(u, dict) else (u.dict() if hasattr(u, "dict") else getattr(u, "__dict__", {}))
                        u_pk = str(u_dict.get("pk") or u_dict.get("id") or "")
                        u_name = u_dict.get("username") or ""
                        u_fname = u_dict.get("full_name") or ""
                        if u_pk:
                            thread_user_map[u_pk] = {
                                "username": u_name,
                                "full_name": u_fname
                            }
                            # Auto-discover participant profiles in persistent memory without false activity counts
                            insta_memory.get_profile(u_pk, username=u_name, full_name=u_fname)

                    messages_sorted = sorted(
                        messages,
                        key=lambda m: self._parse_msg_timestamp(m)
                    )

                    for msg in messages_sorted:
                        msg_id = str(msg.get("item_id") or msg.get("id") or msg.get("pk") or msg.get("message_id") or "") if isinstance(msg, dict) else str(getattr(msg, "item_id", "") or getattr(msg, "id", "") or getattr(msg, "pk", "") or getattr(msg, "message_id", ""))
                        sender_id = str(msg.get("user_id", "")) if isinstance(msg, dict) else str(getattr(msg, "user_id", ""))

                        if not msg_id or sender_id == str(self.insta_client.user_id) or self.insta_client.is_dm_processed(msg_id) or msg_id in in_memory_ingested_ids:
                            continue

                        in_memory_ingested_ids.add(msg_id)

                        # Resolve individual author username
                        author_info = thread_user_map.get(sender_id, {})
                        author_username = author_info.get("username") or ""
                        if not author_username:
                            p_mem = insta_memory.get_profile(sender_id)
                            author_username = p_mem.get("username") or f"user_{sender_id}"

                        # Attach thread context info and accurate sender info
                        msg_entry = msg if isinstance(msg, dict) else msg.__dict__
                        msg_entry["_sender_id"] = sender_id
                        msg_entry["_sender_username"] = author_username
                        msg_entry["_sender_fullname"] = author_info.get("full_name", "")
                        msg_entry["_thread_title"] = th.get("thread_title") or f"chat_{th_id}"
                        msg_entry["_thread_id"] = th_id
                        msg_entry["_is_group"] = bool(th.get("is_group", False))
                        msg_entry["_thread_users"] = thread_users

                        dm_debounce_buffer.setdefault(th_id, []).append(msg_entry)
                        dm_last_recv_time[th_id] = now

                # 3. PROCESS READY DEBOUNCED BATCHES
                for th_id in list(dm_debounce_buffer.keys()):
                    queued_msgs = dm_debounce_buffer.get(th_id, [])
                    if not queued_msgs:
                        continue

                    last_time = dm_last_recv_time.get(th_id, 0)
                    # Debounce: If user sent a message < 2.5s ago and buffer has < 4 items, wait for follow-up
                    if (now - last_time < 2.5) and len(queued_msgs) < 4:
                        continue

                    # Buffer is ready! Pop the batch
                    batch = dm_debounce_buffer.pop(th_id, [])
                    if not batch:
                        continue

                    # Mark batch items processed
                    for m_item in batch:
                        m_id = str(m_item.get("id") or m_item.get("pk") or "")
                        if m_id:
                            self.insta_client.mark_dm_processed(m_id)
                            logger.debug(f"[INSTA DM WORKER] Mark processed: {m_id}")

                    latest_msg = batch[-1]
                    latest_msg_id = str(latest_msg.get("id") or latest_msg.get("pk") or "")
                    sender_id = str(latest_msg.get("_sender_id") or latest_msg.get("user_id", ""))
                    sender_username = latest_msg.get("_sender_username") or f"user_{sender_id}"
                    sender_fullname = latest_msg.get("_sender_fullname", "")
                    is_group_chat = bool(latest_msg.get("_is_group", False))
                    group_title = latest_msg.get("_thread_title", "Group Chat")

                    # Extract all user texts in the batch with speaker attribution
                    user_texts_clean = []
                    formatted_transcript_lines = []
                    for m in batch:
                        m_author = m.get("_sender_username") or f"user_{m.get('_sender_id', '')}"
                        t = ((m.get("text") if isinstance(m, dict) else getattr(m, "text", "")) or "").strip()
                        if t and t != "None":
                            user_texts_clean.append(t)
                            formatted_transcript_lines.append(f"@{m_author}: \"{t}\"")

                    combined_text = " ".join(user_texts_clean)

                    # In Group Chat (GC), only respond if addressed by name, pronoun triggers, or replied to
                    if is_group_chat:
                        import re
                        c_name = (self.insta_cfg.character_name or "Yuna").lower()
                        u_name = (self.insta_cfg.username or "ur._.yunaa").lower()
                        name_pattern = rf'\b({re.escape(c_name)}|{re.escape(u_name)}|yuna|yunaa|brili|brilliance|she|her|hers|herself)\b|@{re.escape(u_name)}'
                        trigger_match = bool(re.search(name_pattern, combined_text, re.IGNORECASE))

                        is_reply_to_bot = False
                        for m in batch:
                            rep_msg = getattr(m, "reply_to_message", None) if not isinstance(m, dict) else m.get("reply_to_message")
                            if rep_msg:
                                rep_sender = str(getattr(rep_msg, "user_id", None) or (rep_msg.get("user_id") if isinstance(rep_msg, dict) else ""))
                                if rep_sender == str(self.insta_client.user_id):
                                    is_reply_to_bot = True
                                    break

                        if not trigger_match and not is_reply_to_bot:
                            logger.debug(f"[INSTA GC] In group chat '{group_title}', message from @{sender_username} did not mention bot. Ignoring.")
                            continue

                    # Mark seen and start typing indicator
                    await self.insta_client.mark_message_seen(th_id, latest_msg_id)
                    await self.insta_client.send_typing_indicator(th_id)

                    # Ensure sender is registered in memory and scan profile
                    insta_memory.register_user(sender_id, username=sender_username, full_name=sender_fullname)
                    for ut in user_texts_clean:
                        insta_memory.check_user_confirmation(sender_id, ut)
                        insta_memory.add_sentence(sender_id, ut)

                    await insta_memory.scan_user_profile_if_needed(self.insta_client.client, sender_id, sender_username)
                    mem_context = insta_memory.build_memory_prompt_context(sender_id, sender_username, combined_text)

                    # Check if any media, voice notes, or call events were sent in this batch
                    found_video_url = None
                    found_image_url = None
                    found_audio_url = None
                    found_call_event = False
                    media_label = None

                    for m in batch:
                        v_url, i_url, a_url, is_call, lbl = self._extract_media_from_msg(m)
                        if is_call:
                            found_call_event = True
                            media_label = lbl
                        if a_url and not found_audio_url:
                            found_audio_url = a_url
                            media_label = lbl
                        if v_url and not found_video_url:
                            found_video_url = v_url
                            media_label = lbl
                        if i_url and not found_image_url:
                            found_image_url = i_url
                            media_label = lbl

                    # Check text triggers for call requests e.g. "call me", "can we call", "let's voice call"
                    import re
                    is_call_text_request = bool(re.search(
                        r'\b(call me|can we call|let\'s call|lets call|start a call|voice call|video call|jump on a call|pick up the call|answer the call)\b',
                        combined_text,
                        re.IGNORECASE
                    ))

                    # 0. Instagram Call Event / Call Trigger in Batch
                    if found_call_event or is_call_text_request:
                        await self.insta_client.process_dm_call_event_and_reply(
                            thread_id=th_id,
                            sender_id=sender_id,
                            sender_username=sender_username,
                            ask_ai_fn=self.ask_ai_fn,
                            speak_fn=self.speak_fn,
                            reply_to_item_id=latest_msg_id
                        )
                        continue

                    # 0.5. Voice Note / Audio Clip in Batch
                    if found_audio_url:
                        combined_user_text = " \n".join(user_texts_clean) if user_texts_clean else ""
                        await self.insta_client.process_dm_voice_note_and_reply(
                            thread_id=th_id,
                            sender_id=sender_id,
                            sender_username=sender_username,
                            audio_url=str(found_audio_url),
                            user_text=combined_user_text,
                            transcribe_fn=self.transcribe_fn,
                            ask_ai_fn=self.ask_ai_fn,
                            speak_fn=self.speak_fn,
                            reply_to_item_id=latest_msg_id,
                            reply_to_message=latest_msg
                        )
                        continue

                    # A. Video / Reel / Clip in Batch
                    if found_video_url:
                        combined_user_text = " \n".join(user_texts_clean) if user_texts_clean else ""
                        v_ok, v_reply = await self.insta_client.process_dm_video_and_reply(
                            thread_id=th_id,
                            sender_id=sender_id,
                            sender_username=sender_username,
                            video_url=str(found_video_url),
                            user_text=combined_user_text,
                            watch_video_fn=self.watch_video_fn,
                            ask_ai_fn=self.ask_ai_fn,
                            reply_to_item_id=latest_msg_id,
                            reply_to_message=latest_msg
                        )
                        # Mid-conversation Reel Exchange: send a reel back in exchange!
                        if v_ok:
                            await asyncio.sleep(3.5)
                            await self.insta_client.send_reel_exchange(
                                thread_id=th_id,
                                sender_username=sender_username,
                                ask_ai_fn=self.ask_ai_fn
                            )
                        continue

                    # B. Photo / Image / Sticker / GIF in Batch
                    if found_image_url:
                        combined_user_text = " \n".join(user_texts_clean) if user_texts_clean else ""
                        await self.insta_client.process_dm_image_and_reply(
                            thread_id=th_id,
                            sender_id=sender_id,
                            sender_username=sender_username,
                            image_url=str(found_image_url),
                            user_text=combined_user_text,
                            ask_vision_fn=self.ask_vision_fn,
                            ask_ai_fn=self.ask_ai_fn,
                            reply_to_item_id=latest_msg_id,
                            reply_to_message=latest_msg
                        )
                        continue

                    # C. Text DM / Group Chat Message
                    if self.ask_ai_fn:
                        d_id, d_name, _ = insta_memory.match_discord_identity(sender_id, sender_username)
                        target_user_id = d_id if d_id else sender_id
                        target_user_name = d_name if d_name else sender_username
                        unresponded_reel = insta_memory.get_unresponded_reel(sender_id)
                        if unresponded_reel:
                            insta_memory.mark_reel_reacted(sender_id)
                            r_summary = unresponded_reel.get("summary", "")[:250]
                            r_rxn = unresponded_reel.get("yuna_reaction", "")
                            msg_prompt = (
                                f"[FOLLOW-UP TO SHARED REEL/VIDEO]:\n"
                                f"You and @{sender_username} watched a reel earlier about: \"{r_summary}\"\n"
                                f"Your previous reaction was: \"{r_rxn}\"\n"
                                f"The follower is now replying to you with: \"{user_texts_clean[0] if user_texts_clean else 'Haha'}\"\n"
                                f"CRITICAL DIRECTIVE: Send a warm, positive, enthusiastic reply continuing the discussion on what you both saw in the reel!"
                            )
                            char_name = self.insta_cfg.character_name or "Yuna"
                            energy_instruction = (
                                f"Respond warmly, enthusiastically, and positively in character as {char_name} (1-2 sentences), connecting what they said back to the video!"
                            )
                        elif is_group_chat:
                            char_name = self.insta_cfg.character_name or "Yuna"
                            transcript_str = "\n".join(formatted_transcript_lines) if formatted_transcript_lines else f"@{sender_username}: \"{user_texts_clean[0] if user_texts_clean else 'Hello'}\""
                            msg_prompt = (
                                f"[INSTAGRAM GROUP CHAT: '{group_title}']\n"
                                f"Recent messages in group:\n{transcript_str}\n\n"
                                f"You are currently replying to @{sender_username} (Name: {sender_fullname or sender_username})."
                            )
                            energy_instruction = (
                                f"[GROUP CHAT DIRECTIVE: You are chatting in a group chat with multiple distinct individuals. "
                                f"CRITICAL: Address @{sender_username} by their actual handle/name and DO NOT confuse them with other group members or call everyone by the same name! "
                                f"Keep your response witty, lively, and in-character (1-2 sentences).]"
                            )
                        elif len(user_texts_clean) >= 2:
                            char_name = self.insta_cfg.character_name or "Yuna"
                            formatted_msgs = "\n".join([f"- \"{t}\"" for t in user_texts_clean])
                            msg_prompt = f"The user sent {len(user_texts_clean)} messages in rapid succession:\n{formatted_msgs}"
                            energy_instruction = (
                                "Respond cohesively in a single concise, natural in-character message addressing what the follower sent."
                            )
                        elif user_texts_clean:
                            char_name = self.insta_cfg.character_name or "Yuna"
                            msg_prompt = f"Message from follower @{sender_username}: \"{user_texts_clean[0]}\""
                            energy_instruction = (
                                "LENGTH GUIDELINE: If it's a quick casual remark, keep it natural and punchy (1-2 sentences). "
                                "If the user asks for details, memories, explanations, or stories, provide a rich, detailed, and expressive answer in character."
                            )
                        else:
                            char_name = self.insta_cfg.character_name or "Yuna"
                            msg_prompt = f"Follower @{sender_username} sent you a reaction/sticker in your Direct Messages (DMs)."
                            energy_instruction = f"Reply playfully and briefly in 1 snappy sentence in character as {char_name}."

                        prompt = (
                            f"{mem_context}\n\n"
                            f"{msg_prompt}\n\n"
                            f"Reply naturally and conversationally in character as {char_name}.\n"
                            f"{energy_instruction}\n"
                            f"STRICT RULE: Speak purely in direct dialogue without writing physical actions in asterisks (no *smiles*, *laughs*, *sighs*)."
                        )

                        system_override = self.insta_client.build_system_prompt(sender_username)
                        reply, err = await self.ask_ai_fn(
                            channel_id=f"insta_dm_{th_id}",
                            prompt=prompt,
                            user_id=target_user_id,
                            user_name=target_user_name,
                            is_dm=True,
                            system_msg_override=system_override
                        )

                        if not err and reply:
                            clean_text = reply.replace("||SPLIT||", " ")
                            reply_clean = _clean_social_reply(clean_text)
                            if reply_clean:
                                await self.insta_client.send_dm_message(
                                    thread_id=th_id,
                                    text=reply_clean,
                                    reply_to_item_id=latest_msg_id,
                                    reply_to_message=latest_msg
                                )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[INSTA DM WORKER] Error in DM polling: {e}")

            await asyncio.sleep(4.0)

    # ─── INSTAGRAM FOLLOW & PENDING REQUEST WORKER ───
    async def _insta_follow_worker(self):
        """Background worker for auto-approving follow requests and message requests."""
        while self._running:
            try:
                if self.insta_cfg.auto_approve_follow_requests and self.insta_client.is_logged_in:
                    await self.insta_client.auto_approve_follow_requests()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"[INSTA FOLLOW WORKER] Follow check note: {e}")

            await asyncio.sleep(45.0)

    # ─── INSTAGRAM STORY AUTO-VIEWER & FOLLOWER ACTIVITY WORKER ───
    async def _insta_story_worker(self):
        """Background worker for periodically viewing follower stories and leaving auto-likes."""
        while self._running:
            try:
                if self.insta_cfg.watch_follower_stories and self.insta_client.is_logged_in:
                    await self.insta_client.watch_follower_stories(
                        auto_like=self.insta_cfg.auto_like_stories,
                        ask_ai_fn=self.ask_ai_fn,
                        memory_update_fn=insta_memory.record_story_view
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"[INSTA STORY WORKER] Story check note: {e}")

            await asyncio.sleep(max(60, self.insta_cfg.story_check_interval_minutes * 60))

    # ─── INSTAGRAM NOTIFICATION & LIKE RESPONDER WORKER ───
    async def _insta_activity_worker(self):
        """Background worker for responding to user likes and calling out ignored reel reactions."""
        while self._running:
            try:
                if getattr(self.insta_cfg, "auto_respond_likes", True) and self.insta_client.is_logged_in:
                    await self.insta_client.check_and_respond_to_likes(ask_ai_fn=self.ask_ai_fn)

                # Check for followers who shared a reel, Yuna reacted, but they gave no response after 15+ minutes
                if self.insta_client.is_logged_in and self.ask_ai_fn:
                    pending = insta_memory.get_pending_callout_reels(min_silence_seconds=900.0, max_silence_seconds=43200.0)
                    for item in pending:
                        u_id = item["user_id"]
                        u_name = item["username"]
                        th_id = item["thread_id"]
                        summary = item["summary"]
                        yuna_rxn = item["yuna_reaction"]

                        insta_memory.mark_reel_called_out(u_id)
                        if not th_id:
                            continue

                        char_name = self.insta_cfg.character_name or "Yuna"
                        prompt = (
                            f"Your follower @{u_name} sent you a video/reel earlier about: \"{summary[:200]}\".\n"
                            f"You watched it and sent your reaction: \"{yuna_rxn}\", but they never said anything back and went silent!\n\n"
                            f"Call them out ONCE playfully, sassily, and in character as {char_name} (1 short sentence). "
                            f"Ask them why they dropped a reel and disappeared without telling you what they thought. "
                            f"Do not write actions in asterisks."
                        )
                        sys_prompt = self.insta_client.build_system_prompt(u_name)
                        reply, err = await self.ask_ai_fn(
                            channel_id=f"insta_dm_{th_id}",
                            prompt=prompt,
                            user_id=u_id,
                            user_name=u_name,
                            is_dm=True,
                            system_msg_override=sys_prompt
                        )
                        if not err and reply:
                            reply_clean = _clean_social_reply(reply)
                            if reply_clean:
                                logger.info(f"[INSTA REEL CALLOUT] Calling out @{u_name} for silence on shared reel in thread {th_id}...")
                                await self.insta_client.send_dm_message(thread_id=th_id, text=reply_clean)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"[INSTA ACTIVITY WORKER] Activity check note: {e}")

            await asyncio.sleep(25.0)

    # ─── INSTAGRAM PROACTIVE 4-6 HOUR REEL FEED SHARER ───
    async def _insta_reel_feed_worker(self):
        """Periodically shares entertaining reels from explore/feed to active DM conversations every 4-6 hours,
        preventing spamming if nobody has responded in the last 12 hours."""
        import random
        # Initial sleep of 90 seconds after boot
        await asyncio.sleep(90.0)
        while self._running:
            try:
                proactive_enabled = getattr(self.insta_cfg, "proactive_reels_enabled", True)
                silence_cutoff_hours = getattr(self.insta_cfg, "reel_silence_cutoff_hours", 12.0)
                max_silence_seconds = silence_cutoff_hours * 3600.0

                if proactive_enabled and self.insta_client.is_logged_in and self.ask_ai_fn:
                    threads = await self.insta_client.fetch_dm_threads(limit=10)
                    yuna_id = str(self.insta_client.user_id or "")

                    for th in threads:
                        th_id = str(th.get("thread_id", ""))
                        if not th_id or th.get("is_group"):
                            continue
                        users = th.get("users", [])
                        if not users:
                            continue
                        u = users[0]
                        u_dict = u if isinstance(u, dict) else (u.dict() if hasattr(u, "dict") else getattr(u, "__dict__", {}))
                        u_id = str(u_dict.get("pk") or u_dict.get("id") or "")
                        u_name = u_dict.get("username") or ""
                        if not u_id or not u_name or (yuna_id and u_id == yuna_id):
                            continue

                        messages = th.get("messages", [])
                        now = time.time()

                        # Determine latest message from follower vs Yuna
                        last_user_msg_time = 0.0
                        last_bot_msg_time = 0.0

                        sorted_msgs = sorted(
                            messages,
                            key=lambda m: self._parse_msg_timestamp(m)
                        )

                        for m in sorted_msgs:
                            sender = self._extract_msg_sender_id(m)
                            ts = self._parse_msg_timestamp(m)
                            if yuna_id and sender == yuna_id:
                                if ts > last_bot_msg_time:
                                    last_bot_msg_time = ts
                            elif sender:
                                if ts > last_user_msg_time:
                                    last_user_msg_time = ts

                        # Check memory for last user message time if not present in recent messages
                        p = insta_memory.profiles.get(str(u_id)) or {}
                        mem_user_time = float(p.get("last_user_message_time") or 0.0)
                        last_user_time = max(last_user_msg_time, mem_user_time)

                        # If user has never sent a message or responded, do not spam reels
                        if last_user_time <= 0:
                            logger.debug(f"[INSTA REEL FEED] Skipping @{u_name} ({u_id}): No message or response history from user.")
                            continue

                        # 12-Hour Silence Cutoff: Do not send reels if nobody responded in last 12 hours
                        silence_duration = now - last_user_time
                        if silence_duration > max_silence_seconds:
                            logger.info(
                                f"[INSTA REEL FEED] Skipping @{u_name} ({u_id}): Nobody responded in last {silence_cutoff_hours:.0f} hours "
                                f"(silence: {silence_duration/3600.0:.1f}h > {silence_cutoff_hours:.0f}h). Reel sharing paused."
                            )
                            continue

                        # Do not send another proactive reel if user has not responded back to the previous one
                        last_reel_time = self.insta_client.get_last_proactive_reel_time(u_id, username=u_name)
                        if last_reel_time > last_user_time:
                            logger.info(
                                f"[INSTA REEL FEED] Skipping @{u_name} ({u_id}): User has not responded since "
                                f"last proactive reel sent {(now - last_reel_time)/3600.0:.1f}h ago. Awaiting user response."
                            )
                            continue

                        # Check 4 to 6 hour randomized interval between reels
                        min_int = getattr(self.insta_cfg, "min_reel_interval_hours", 4.0)
                        max_int = getattr(self.insta_cfg, "max_reel_interval_hours", 6.0)
                        interval = random.uniform(min_int, max_int)
                        if self.insta_client.can_send_proactive_reel(u_id, min_interval_hours=interval, username=u_name):
                            logger.info(
                                f"[INSTA REEL FEED] Active conversation found for @{u_name} "
                                f"(user responded {silence_duration/3600.0:.1f}h ago). Sending proactive reel..."
                            )
                            await self.insta_client.send_proactive_feed_reel(
                                thread_id=th_id,
                                user_id=u_id,
                                username=u_name,
                                ask_ai_fn=self.ask_ai_fn
                            )
                            await asyncio.sleep(15.0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"[INSTA REEL FEED WORKER] Reel feed worker note: {e}")

            # Check every 25 minutes
            await asyncio.sleep(1500.0)

    # ─── INSTAGRAM MUSIC NOTE AUTO-UPDATER WORKER ───
    async def _insta_note_worker(self):
        """Background worker for automatically updating Instagram Music Notes every 12 to 24 hours."""
        await asyncio.sleep(60.0)
        while self._running:
            try:
                auto_notes = getattr(self.insta_cfg, "auto_music_notes", True)
                if auto_notes and self.insta_client.is_logged_in:
                    last_time = float(self.insta_client.notes_state.get("last_note_time", 0.0))
                    interval_hours = getattr(self.insta_cfg, "note_check_interval_hours", 12.0)
                    now = time.time()
                    elapsed = now - last_time

                    if elapsed >= (interval_hours * 3600.0):
                        logger.info(
                            f"[INSTA NOTE WORKER] Updating Instagram Music Note "
                            f"(elapsed: {elapsed/3600.0:.1f}h >= {interval_hours}h)..."
                        )
                        ok, msg, note_data = await self.insta_client.set_music_note(ask_ai_fn=self.ask_ai_fn)
                        if ok:
                            logger.info(f"[INSTA NOTE WORKER] {msg}")
                        else:
                            logger.warning(f"[INSTA NOTE WORKER] Could not update note: {msg}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"[INSTA NOTE WORKER] Note worker error: {e}")

            # Check every 30 minutes
            await asyncio.sleep(1800.0)

    # ─── INSTAGRAM DAILY STORY POSTER WORKER ───
    async def _insta_story_poster_worker(self):
        """Background worker for automatically posting 3-4 daily aesthetic stories every 24 hours."""
        await asyncio.sleep(120.0)
        while self._running:
            try:
                auto_stories = getattr(self.insta_cfg, "auto_post_stories", True)
                if auto_stories and self.insta_client.is_logged_in:
                    last_time = float(self.insta_client.stories_state.get("last_story_post_time", 0.0))
                    interval_hours = getattr(self.insta_cfg, "story_post_interval_hours", 24.0)
                    now = time.time()
                    elapsed = now - last_time

                    if elapsed >= (interval_hours * 3600.0):
                        count = getattr(self.insta_cfg, "stories_per_day", 3)
                        logger.info(
                            f"[INSTA STORY POSTER] Generating and posting {count} daily stories "
                            f"(elapsed: {elapsed/3600.0:.1f}h >= {interval_hours}h)..."
                        )
                        posted = await self.insta_client.add_daily_stories(count=count, ask_ai_fn=self.ask_ai_fn)
                        logger.info(f"[INSTA STORY POSTER] Published {len(posted)}/{count} stories successfully.")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"[INSTA STORY POSTER] Story poster error: {e}")

            # Check every 30 minutes
            await asyncio.sleep(1800.0)

