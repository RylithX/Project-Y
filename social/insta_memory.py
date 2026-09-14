"""
Instagram Profile & Persistent Memory Manager with Deep Discord Cross-Platform Sync.
Maintains dedicated Instagram user profiles in data/insta_profiles.json without mixing
Discord IDs and Instagram PKs, while enabling seamless cross-platform memory synchronization.
"""

import os
import json
import time
import re
import difflib
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger("SocialInstagramMemory")

INSTA_PROFILES_PATH = Path("/storage/emulated/0/discord-bot/data/insta_profiles.json")
DISCORD_PROFILES_PATH = Path("/storage/emulated/0/discord-bot/user_profiles.json")


class InstagramMemoryManager:
    """Manages Instagram user profiles, memories, and Discord identity matching."""

    def __init__(self):
        self.profiles: Dict[str, Dict[str, Any]] = {}
        self._load_profiles()

    def _load_profiles(self):
        """Loads Instagram user profiles from disk."""
        if INSTA_PROFILES_PATH.exists():
            try:
                with open(INSTA_PROFILES_PATH, "r", encoding="utf-8") as f:
                    self.profiles = json.load(f)
                logger.info(f"[INSTA MEMORY] Loaded {len(self.profiles)} Instagram user profiles from disk.")
            except Exception as e:
                logger.error(f"[INSTA MEMORY] Error loading {INSTA_PROFILES_PATH}: {e}")
                self.profiles = {}
        else:
            self.profiles = {}

    def _save_profiles(self):
        """Persists Instagram user profiles to disk."""
        try:
            INSTA_PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(INSTA_PROFILES_PATH, "w", encoding="utf-8") as f:
                json.dump(self.profiles, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[INSTA MEMORY] Error saving {INSTA_PROFILES_PATH}: {e}")

    def get_profile(self, user_id: str, username: str = "", full_name: str = "") -> Dict[str, Any]:
        """Gets or initializes profile for an Instagram user, updating username/full_name if provided."""
        uid = str(user_id)
        if uid not in self.profiles:
            self.profiles[uid] = {
                "user_id": uid,
                "username": username or "",
                "full_name": full_name or "",
                "biography": "",
                "profile_pic_url": "",
                "follower_count": 0,
                "following_count": 0,
                "last_scanned": 0,
                "last_active": time.time(),
                "last_user_message_time": 0.0,
                "recent_posts": [],
                "linked_discord_id": None,
                "link_confirmation_asked": False,
                "facts": [],
                "sentences": [],
                "interaction_count": 0,
                "notes": []
            }
            self._save_profiles()
        else:
            updated = False
            if username and not self.profiles[uid].get("username"):
                self.profiles[uid]["username"] = username
                updated = True
            if full_name and not self.profiles[uid].get("full_name"):
                self.profiles[uid]["full_name"] = full_name
                updated = True
            if updated:
                self._save_profiles()
        return self.profiles[uid]

    def register_user(self, user_id: str, username: str = "", full_name: str = "") -> Dict[str, Any]:
        """Explicitly registers an Instagram user in persistent memory with handle and full name."""
        uid = str(user_id)
        p = self.get_profile(uid, username=username, full_name=full_name)
        updated = False
        if username and p.get("username") != username:
            p["username"] = username
            updated = True
        if full_name and p.get("full_name") != full_name:
            p["full_name"] = full_name
            updated = True
        now = time.time()
        p["last_active"] = now
        p["last_user_message_time"] = now
        p["interaction_count"] = p.get("interaction_count", 0) + 1
        self._save_profiles()
        return p

    def record_user_message(self, user_id: str, username: str = "", timestamp: Optional[float] = None):
        """Records timestamp when a user sent a message/response in DM."""
        uid = str(user_id)
        p = self.get_profile(uid, username=username)
        t = timestamp if timestamp is not None else time.time()
        p["last_user_message_time"] = t
        p["last_active"] = t
        self._save_profiles()

    def get_last_user_message_time(self, user_id: str) -> float:
        """Returns the timestamp of the last message sent by this user."""
        uid = str(user_id)
        p = self.profiles.get(uid)
        if not p:
            return 0.0
        return float(p.get("last_user_message_time") or 0.0)

    def _get_discord_profiles(self) -> Dict[str, Any]:
        """Loads current Discord user profiles."""
        if DISCORD_PROFILES_PATH.exists():
            try:
                with open(DISCORD_PROFILES_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def match_discord_identity(self, insta_uid: str, insta_username: str, insta_full_name: str = "") -> Tuple[Optional[str], Optional[str], bool]:
        """
        Compares Instagram user info with Discord user profiles.
        Returns: (matched_discord_id, matched_discord_name, is_exact_match)
        """
        p = self.get_profile(insta_uid)
        d_profiles = self._get_discord_profiles()

        # If already linked, return link directly
        if p.get("linked_discord_id") and p["linked_discord_id"] in d_profiles:
            d_user = d_profiles[p["linked_discord_id"]]
            return p["linked_discord_id"], d_user.get("name") or d_user.get("global_name", "friend"), True

        if not d_profiles:
            return None, None, False

        i_uname_clean = (insta_username or "").lower().strip()
        i_fname_clean = (insta_full_name or "").lower().strip()
        i_uname_simple = re.sub(r'[^a-zA-Z0-9]', '', i_uname_clean)
        i_fname_simple = re.sub(r'[^a-zA-Z0-9]', '', i_fname_clean)

        best_fuzzy_id = None
        best_fuzzy_name = None
        best_fuzzy_ratio = 0.0

        for d_id, d_data in d_profiles.items():
            d_name = (d_data.get("name") or "").lower().strip()
            d_gname = (d_data.get("global_name") or "").lower().strip()
            d_name_simple = re.sub(r'[^a-zA-Z0-9]', '', d_name)
            d_gname_simple = re.sub(r'[^a-zA-Z0-9]', '', d_gname)

            # Special known mappings & exact anagrams (e.g. ryl1th <-> xht1lyr / Ryl)
            is_match = False
            if i_uname_simple in ("ryl1th", "ryl", "rylith", "ryliee") and (d_name_simple in ("xht1lyr", "ryl", "ryl1th") or d_gname_simple in ("ryl", "ryl1th")):
                is_match = True
            elif i_fname_simple and "ryl1th" in i_fname_simple and (d_name_simple in ("xht1lyr", "ryl") or d_gname_simple in ("ryl", "ryl1th")):
                is_match = True
            elif i_uname_simple and (i_uname_simple == d_name_simple or i_uname_simple == d_gname_simple):
                is_match = True
            elif i_fname_simple and (i_fname_simple == d_name_simple or i_fname_simple == d_gname_simple):
                is_match = True

            if is_match:
                p["linked_discord_id"] = str(d_id)
                self._save_profiles()
                logger.info(f"[INSTA MEMORY] Exact match linked Instagram user @{insta_username} to Discord user {d_name} ({d_id})")
                return str(d_id), d_data.get("global_name") or d_data.get("name"), True

            # Fuzzy match
            for d_str in [d_name_simple, d_gname_simple]:
                if not d_str or not i_uname_simple:
                    continue
                ratio = difflib.SequenceMatcher(None, i_uname_simple, d_str).ratio()
                if (i_uname_simple in d_str or d_str in i_uname_simple) and len(i_uname_simple) >= 3:
                    ratio = max(ratio, 0.85)
                if ratio > best_fuzzy_ratio:
                    best_fuzzy_ratio = ratio
                    best_fuzzy_id = str(d_id)
                    best_fuzzy_name = d_data.get("global_name") or d_data.get("name")

        if best_fuzzy_ratio >= 0.70:
            return best_fuzzy_id, best_fuzzy_name, False

        return None, None, False

    def check_user_confirmation(self, user_id: str, user_message: str) -> bool:
        """
        Detects if user confirms their Discord identity in conversation.
        e.g. 'yes', 'yeah that's me', 'yep', 'i am', 'my discord is ryl1th'.
        """
        uid = str(user_id)
        p = self.get_profile(uid)
        if p.get("linked_discord_id"):
            return True

        msg_clean = user_message.lower().strip()
        # Direct mention of Discord name
        d_profiles = self._get_discord_profiles()
        for d_id, d_data in d_profiles.items():
            d_name = (d_data.get("name") or "").lower().strip()
            d_gname = (d_data.get("global_name") or "").lower().strip()
            if (d_name and d_name in msg_clean) or (d_gname and len(d_gname) >= 3 and d_gname in msg_clean):
                p["linked_discord_id"] = str(d_id)
                self._save_profiles()
                logger.info(f"[INSTA MEMORY] User confirmed identity as Discord user {d_name} ({d_id})")
                return True

        # Affirmation after asking
        if p.get("link_confirmation_asked"):
            affirmation_patterns = [
                r"\byes\b", r"\byeah\b", r"\byep\b", r"\byup\b", r"\bmhm\b",
                r"\bthat'?s me\b", r"\bi am\b", r"\bcorrect\b", r"\bindeed\b",
                r"\bi'?m ryl\b", r"\bi'?m ryl1th\b", r"\bit'?s me\b"
            ]
            if any(re.search(pat, msg_clean) for pat in affirmation_patterns):
                # Lock in best fuzzy match
                d_id, d_name, _ = self.match_discord_identity(uid, p.get("username", ""), p.get("full_name", ""))
                if d_id:
                    p["linked_discord_id"] = str(d_id)
                    self._save_profiles()
                    logger.info(f"[INSTA MEMORY] User confirmed fuzzy identity as {d_name} ({d_id})")
                    return True

        return False

    async def scan_user_profile_if_needed(self, client: Any, user_id: str, username: str = "") -> Dict[str, Any]:
        """
        Scans Instagram user profile on message receipt if never scanned OR if idle > 2 hours (7200s).
        Fetches PFP, Bio, and up to 3 recent post captions if idle > 2 hours.
        """
        uid = str(user_id)
        p = self.get_profile(uid)
        now = time.time()
        time_since_active = now - p.get("last_active", 0)

        p["last_active"] = now
        p["interaction_count"] = p.get("interaction_count", 0) + 1

        should_scan = (p.get("last_scanned", 0) == 0) or (time_since_active > 7200)

        if should_scan and client:
            try:
                def _do_insta_scan():
                    info = None
                    try:
                        info = client.user_info(int(uid))
                    except Exception:
                        if username:
                            info = client.user_info_by_username(username)

                    posts_data = []
                    if time_since_active > 7200:
                        try:
                            medias = client.user_medias(int(uid), amount=3)
                            for m in medias:
                                cap = (getattr(m, "caption_text", "") or "")[:150]
                                if cap:
                                    posts_data.append({
                                        "caption": cap,
                                        "media_type": getattr(m, "media_type", 1)
                                    })
                        except Exception as pe:
                            logger.debug(f"[INSTA MEMORY] Post scan note: {pe}")

                    return info, posts_data

                import asyncio
                u_info, posts = await asyncio.to_thread(_do_insta_scan)

                if u_info:
                    p["username"] = getattr(u_info, "username", "") or username
                    p["full_name"] = getattr(u_info, "full_name", "") or ""
                    p["biography"] = getattr(u_info, "biography", "") or ""
                    p["follower_count"] = getattr(u_info, "follower_count", 0) or 0
                    p["following_count"] = getattr(u_info, "following_count", 0) or 0
                    p["profile_pic_url"] = str(getattr(u_info, "profile_pic_url_hd", "") or getattr(u_info, "profile_pic_url", "") or "")
                    if posts:
                        p["recent_posts"] = posts
                    p["last_scanned"] = now
                    logger.info(f"[INSTA MEMORY] Scanned profile for @{p['username']} ({uid})")

            except Exception as e:
                logger.warning(f"[INSTA MEMORY] Could not scan Instagram profile for {uid}: {e}")

        # Check Discord identity matching
        self.match_discord_identity(uid, p.get("username") or username, p.get("full_name", ""))
        self._save_profiles()
        return p

    def add_fact(self, user_id: str, fact: str):
        """Adds a remembered fact for an Instagram user."""
        uid = str(user_id)
        p = self.get_profile(uid)
        fact_clean = fact.strip()
        if fact_clean and fact_clean not in p["facts"]:
            p["facts"].append(fact_clean)
            if len(p["facts"]) > 50:
                p["facts"].pop(0)
            self._save_profiles()

    def add_sentence(self, user_id: str, sentence: str):
        """Adds a quote said by the Instagram user."""
        uid = str(user_id)
        p = self.get_profile(uid)
        s_clean = sentence.strip()
        if s_clean and s_clean not in p["sentences"]:
            p["sentences"].append(s_clean)
            if len(p["sentences"]) > 30:
                p["sentences"].pop(0)
            self._save_profiles()

    def build_memory_prompt_context(self, user_id: str, sender_username: str, current_prompt: str = "") -> str:
        """
        Builds rich structured memory context for LLM prompt,
        including Instagram profile details, recent posts, remembered facts,
        and deeply synced Discord memories across all bot memories.
        """
        uid = str(user_id)
        p = self.get_profile(uid)
        lines = []

        lines.append(f"[USER CONTEXT: INSTAGRAM FOLLOWER]")
        lines.append(f"Handle: @{p.get('username') or sender_username}")
        if p.get("full_name"):
            lines.append(f"Name / Display Name: {p['full_name']}")
        if p.get("biography"):
            lines.append(f"Bio: \"{p['biography']}\"")
        if p.get("recent_posts"):
            post_summaries = [f"• {post.get('caption')}" for post in p["recent_posts"] if post.get("caption")]
            if post_summaries:
                lines.append(f"Recent Instagram Posts: " + " | ".join(post_summaries[:3]))

        # Instagram facts
        if p.get("facts"):
            lines.append(f"Instagram memories: " + " ; ".join(p["facts"][-5:]))

        # Linked Discord Memory Sync
        d_id, d_name, is_exact = self.match_discord_identity(uid, p.get("username") or sender_username, p.get("full_name", ""))
        if is_exact and d_id:
            d_profiles = self._get_discord_profiles()
            d_data = d_profiles.get(d_id, {})
            
            # Aggregate ALL bot memories for Yuna from Discord profile
            all_facts = []
            all_sentences = []
            bot_mems = d_data.get("bot_memories", {})
            for b_id, b_mem in bot_mems.items():
                all_facts.extend(b_mem.get("facts", []))
                all_sentences.extend(b_mem.get("sentences", []))
            
            all_facts.extend(d_data.get("facts", []))
            all_sentences.extend(d_data.get("sentences", []))

            # Deduplicate preserving order
            # ONLY inject deep past quotes/facts if the user is asking about memories or who they are
            is_asking_memory = any(q in current_prompt.lower() for q in ["remember", "know about me", "who am i", "what do you know", "memories", "tell me about us", "who are you to me", "do you know me"])
            
            if is_asking_memory:
                lines.append(f"\n[CROSS-PLATFORM IDENTITY: THIS IS {d_name} FROM DISCORD!]")
                lines.append(f"You know this user deeply from Discord ({len(unique_facts)} facts on record).")
                if unique_facts:
                    lines.append(f"Key facts you remember about {d_name}:")
                    for f in unique_facts[-8:]:
                        lines.append(f"  • {f}")
                if unique_sentences:
                    lines.append(f"Things {d_name} has said in the past:")
                    for s in unique_sentences[-4:]:
                        lines.append(f"  • \"{s}\"")
            else:
                # Normal casual DM: keep it light and present-focused, do not rehash old topics
                lines.append(f"[NOTE: This follower is {d_name} from Discord. Chat naturally in the present moment without forcing old topics unless they bring them up.]")

        elif not is_exact and d_id and not p.get("link_confirmation_asked"):
            lines.append(f"\n[POSSIBLE DISCORD FRIEND: {d_name}]")
            lines.append(f"Their Instagram name '@{sender_username}' strongly resembles {d_name} from Discord.")
            lines.append(f"Casually ask them in your own style: \"Wait, are you {d_name} from Discord? ✨\"")
            p["link_confirmation_asked"] = True
            self._save_profiles()

        return "\n".join(lines)

    # ─── REEL & VIDEO WATCHING MEMORY & CALLOUT TRACKER ───
    def record_shared_reel(self, user_id: str, thread_id: str, reel_summary: str, reel_code: str = "", yuna_reaction: str = ""):
        """Records a watched reel/video context for conversational follow-ups and silence call-outs."""
        uid = str(user_id)
        p = self.get_profile(uid)
        p["last_shared_reel"] = {
            "summary": reel_summary or "",
            "code": reel_code or "",
            "timestamp": time.time(),
            "thread_id": str(thread_id),
            "yuna_reaction": yuna_reaction or "",
            "user_reacted": False,
            "called_out": False
        }
        self._save_profiles()

    def get_unresponded_reel(self, user_id: str, max_age_hours: float = 6.0) -> Optional[Dict[str, Any]]:
        """Returns active reel context if the follower is replying after Yuna watched their reel."""
        uid = str(user_id)
        p = self.profiles.get(uid)
        if not p:
            return None
        reel_info = p.get("last_shared_reel")
        if not reel_info or not isinstance(reel_info, dict):
            return None
        if reel_info.get("user_reacted"):
            return None
        t = reel_info.get("timestamp", 0)
        if (time.time() - t) <= (max_age_hours * 3600.0):
            return reel_info
        return None

    def mark_reel_reacted(self, user_id: str):
        """Marks that the follower responded back to Yuna about the shared reel."""
        uid = str(user_id)
        p = self.profiles.get(uid)
        if p and isinstance(p.get("last_shared_reel"), dict):
            p["last_shared_reel"]["user_reacted"] = True
            self._save_profiles()

    def mark_reel_called_out(self, user_id: str):
        """Marks that Yuna has called out the follower for ignoring her reel reaction."""
        uid = str(user_id)
        p = self.profiles.get(uid)
        if p and isinstance(p.get("last_shared_reel"), dict):
            p["last_shared_reel"]["called_out"] = True
            self._save_profiles()

    def get_pending_callout_reels(self, min_silence_seconds: float = 900.0, max_silence_seconds: float = 43200.0) -> List[Dict[str, Any]]:
        """Finds reels where Yuna reacted, but follower gave no response after min_silence_seconds."""
        now = time.time()
        pending = []
        for uid, p in self.profiles.items():
            reel_info = p.get("last_shared_reel")
            if not reel_info or not isinstance(reel_info, dict):
                continue
            if reel_info.get("user_reacted") or reel_info.get("called_out"):
                continue
            t = reel_info.get("timestamp", 0)
            silence = now - t
            if min_silence_seconds <= silence <= max_silence_seconds:
                pending.append({
                    "user_id": uid,
                    "username": p.get("username") or f"user_{uid}",
                    "thread_id": reel_info.get("thread_id") or "",
                    "summary": reel_info.get("summary") or "",
                    "yuna_reaction": reel_info.get("yuna_reaction") or "",
                    "code": reel_info.get("code") or ""
                })
        return pending


# Global singleton instance
insta_memory = InstagramMemoryManager()
