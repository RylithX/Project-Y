"""
Comprehensive X (Twitter) Client and Integration Engine.
Supports:
- Posting Tweets (text, images, multi-images, chunked video uploads)
- Commenting / Replying to Tweets and Mentions
- Replying to Direct Messages (DMs)
- Stream/Polling Mention Timelines and DMs with AI Character Generation
- OAuth 1.0a / OAuth 2.0 / API v2 Native + Tweepy Compatibility
"""

import asyncio
import base64
import hashlib
import hmac
import io
import json
import logging
import os
import secrets
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple, Union

import aiohttp

from .config import XConfig

logger = logging.getLogger("Social.XClient")

try:
    import tweepy
    HAVE_TWEEPY = True
except ImportError:
    tweepy = None
    HAVE_TWEEPY = False

class XClient:
    """
    Full-featured X (Twitter) API v2 and v1.1 Media Client.
    """

    def __init__(self, config: XConfig):
        self.config = config
        self.last_mention_id: Optional[str] = None
        self.last_dm_id: Optional[str] = None
        self.authenticated_user_id: Optional[str] = None
        self.authenticated_username: Optional[str] = None
        self._tweepy_client = None
        self._tweepy_api = None
        self._init_tweepy()

    def _init_tweepy(self):
        """Initializes tweepy client if credentials and library exist."""
        if not HAVE_TWEEPY:
            return
        try:
            if self.config.bearer_token or (self.config.api_key and self.config.access_token):
                self._tweepy_client = tweepy.Client(
                    bearer_token=self.config.bearer_token or None,
                    consumer_key=self.config.api_key or None,
                    consumer_secret=self.config.api_secret or None,
                    access_token=self.config.access_token or None,
                    access_token_secret=self.config.access_token_secret or None,
                    wait_on_rate_limit=True
                )
            if self.config.api_key and self.config.api_secret and self.config.access_token and self.config.access_token_secret:
                auth = tweepy.OAuth1UserHandler(
                    self.config.api_key,
                    self.config.api_secret,
                    self.config.access_token,
                    self.config.access_token_secret
                )
                self._tweepy_api = tweepy.API(auth)
                logger.info("[X CLIENT] Tweepy v1.1 and v2 API handlers initialized.")
        except Exception as e:
            logger.warning(f"[X CLIENT] Tweepy init exception (falling back to native REST): {e}")

    def is_configured(self) -> bool:
        """Returns True if essential credentials are provided."""
        has_v1_keys = bool(self.config.api_key and self.config.api_secret and self.config.access_token and self.config.access_token_secret)
        has_v2_keys = bool(self.config.bearer_token or has_v1_keys)
        return has_v2_keys

    def _generate_oauth1_header(self, method: str, url: str, extra_params: Optional[Dict[str, str]] = None) -> str:
        """Generates standard OAuth 1.0a HMAC-SHA1 authorization header for pure REST requests."""
        if not (self.config.api_key and self.config.api_secret and self.config.access_token and self.config.access_token_secret):
            return ""

        oauth_params = {
            "oauth_consumer_key": self.config.api_key,
            "oauth_nonce": secrets.token_hex(16),
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": str(int(time.time())),
            "oauth_token": self.config.access_token,
            "oauth_version": "1.0"
        }

        all_params = {}
        all_params.update(oauth_params)
        if extra_params:
            all_params.update(extra_params)

        # Normalize parameters
        sorted_keys = sorted(all_params.keys())
        param_str = "&".join([f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(str(all_params[k]), safe='')}" for k in sorted_keys])

        base_url = url.split("?")[0]
        base_string = f"{method.upper()}&{urllib.parse.quote(base_url, safe='')}&{urllib.parse.quote(param_str, safe='')}"

        signing_key = f"{urllib.parse.quote(self.config.api_secret, safe='')}&{urllib.parse.quote(self.config.access_token_secret, safe='')}"
        hashed = hmac.new(signing_key.encode("utf-8"), base_string.encode("utf-8"), hashlib.sha1)
        signature = base64.b64encode(hashed.digest()).decode("utf-8")

        oauth_params["oauth_signature"] = signature
        header_parts = [f'{urllib.parse.quote(k, safe="")}="{urllib.parse.quote(v, safe="")}"' for k, v in sorted(oauth_params.items())]
        return "OAuth " + ", ".join(header_parts)

    async def verify_credentials(self) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """Verifies authentication with X and fetches authenticated user details."""
        if not self.is_configured():
            return False, None, "X API credentials are not configured in settings."

        # 1. Try Tweepy v2
        if self._tweepy_client and self.config.api_key and self.config.access_token:
            try:
                me_resp = await asyncio.to_thread(self._tweepy_client.get_me, user_auth=True)
                if me_resp and me_resp.data:
                    self.authenticated_user_id = str(me_resp.data.id)
                    self.authenticated_username = str(me_resp.data.username)
                    return True, {"id": self.authenticated_user_id, "username": self.authenticated_username, "name": me_resp.data.name}, "OK"
            except Exception as e:
                logger.warning(f"[X CLIENT] Tweepy get_me failed: {e}")

        # 2. Native REST API v2
        url = "https://api.twitter.com/2/users/me"
        headers = {}
        auth_header = self._generate_oauth1_header("GET", url)
        if auth_header:
            headers["Authorization"] = auth_header
        elif self.config.bearer_token:
            headers["Authorization"] = f"Bearer {self.config.bearer_token}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    data = await resp.json()
                    if resp.status in (200, 201) and "data" in data:
                        u_data = data["data"]
                        self.authenticated_user_id = str(u_data.get("id"))
                        self.authenticated_username = str(u_data.get("username"))
                        return True, u_data, "OK"
                    else:
                        err_msg = data.get("detail") or data.get("title") or str(data)
                        return False, None, f"HTTP {resp.status}: {err_msg}"
        except Exception as e:
            return False, None, f"Network/Auth error: {e}"

    async def upload_media(self, media_bytes: bytes, filename: str, mime_type: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
        """
        Uploads image or video to X via v1.1 Media Upload endpoint.
        Returns (media_id_str, error_message).
        """
        # 1. Try Tweepy API v1.1 media_upload
        if self._tweepy_api:
            try:
                def _do_upload():
                    tmp_file = io.BytesIO(media_bytes)
                    tmp_file.name = filename
                    media = self._tweepy_api.media_upload(filename=filename, file=tmp_file)
                    return media.media_id_string
                media_id = await asyncio.to_thread(_do_upload)
                return media_id, None
            except Exception as e:
                logger.warning(f"[X CLIENT] Tweepy media upload failed, using native REST: {e}")

        # 2. Native REST Upload (Chunked INIT / APPEND / FINALIZE)
        upload_url = "https://upload.twitter.com/1.1/media/upload.json"
        total_bytes = len(media_bytes)
        
        # Determine media category and mime
        ext = Path(filename).suffix.lower()
        if not mime_type:
            if ext in (".mp4", ".mov", ".mkv", ".webm"):
                mime_type = "video/mp4"
            elif ext == ".gif":
                mime_type = "image/gif"
            elif ext == ".png":
                mime_type = "image/png"
            else:
                mime_type = "image/jpeg"

        is_video = mime_type.startswith("video/")
        media_category = "tweet_video" if is_video else ("tweet_gif" if mime_type == "image/gif" else "tweet_image")

        try:
            async with aiohttp.ClientSession() as session:
                # Step 1: INIT
                init_params = {
                    "command": "INIT",
                    "total_bytes": str(total_bytes),
                    "media_type": mime_type,
                    "media_category": media_category
                }
                init_auth = self._generate_oauth1_header("POST", upload_url, init_params)
                headers = {"Authorization": init_auth}
                
                async with session.post(upload_url, data=init_params, headers=headers) as init_resp:
                    init_data = await init_resp.json()
                    if init_resp.status not in (200, 201, 202) or "media_id_string" not in init_data:
                        return None, f"Media INIT failed: {init_data}"
                    media_id = init_data["media_id_string"]

                # Step 2: APPEND chunks (4MB chunks)
                chunk_size = 4 * 1024 * 1024
                segment_id = 0
                for offset in range(0, total_bytes, chunk_size):
                    chunk = media_bytes[offset:offset + chunk_size]
                    form = aiohttp.FormData()
                    form.add_field("command", "APPEND")
                    form.add_field("media_id", media_id)
                    form.add_field("segment_index", str(segment_id))
                    form.add_field("media", chunk, filename="blob", content_type="application/octet-stream")

                    append_auth = self._generate_oauth1_header("POST", upload_url)
                    headers = {"Authorization": append_auth}
                    async with session.post(upload_url, data=form, headers=headers) as app_resp:
                        if app_resp.status not in (200, 201, 202, 204):
                            app_err = await app_resp.text()
                            return None, f"Media APPEND chunk {segment_id} failed: {app_err}"
                    segment_id += 1

                # Step 3: FINALIZE
                fin_params = {"command": "FINALIZE", "media_id": media_id}
                fin_auth = self._generate_oauth1_header("POST", upload_url, fin_params)
                headers = {"Authorization": fin_auth}
                async with session.post(upload_url, data=fin_params, headers=headers) as fin_resp:
                    fin_data = await fin_resp.json()
                    if fin_resp.status not in (200, 201, 202):
                        return None, f"Media FINALIZE failed: {fin_data}"

                # Step 4: Check async processing info (for videos)
                processing_info = fin_data.get("processing_info")
                while processing_info:
                    state = processing_info.get("state")
                    if state == "succeeded":
                        break
                    elif state == "failed":
                        err_info = processing_info.get("error", {})
                        return None, f"Video processing failed: {err_info.get('message')}"
                    
                    check_after_secs = processing_info.get("check_after_secs", 2)
                    await asyncio.sleep(check_after_secs)

                    status_params = {"command": "STATUS", "media_id": media_id}
                    status_auth = self._generate_oauth1_header("GET", upload_url, status_params)
                    async with session.get(upload_url, params=status_params, headers={"Authorization": status_auth}) as st_resp:
                        st_data = await st_resp.json()
                        processing_info = st_data.get("processing_info")

                return media_id, None
        except Exception as e:
            return None, f"Media upload exception: {e}"

    async def post_tweet(
        self,
        text: str,
        media_ids: Optional[List[str]] = None,
        in_reply_to_tweet_id: Optional[str] = None,
        quote_tweet_id: Optional[str] = None
    ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """
        Posts a Tweet / Reply / Quote Tweet using Twitter API v2.
        Returns: (success, tweet_data, message_or_url)
        """
        # 1. Try Tweepy v2 Client
        if self._tweepy_client:
            try:
                def _do_post():
                    kwargs = {"text": text}
                    if media_ids:
                        kwargs["media_ids"] = media_ids
                    if in_reply_to_tweet_id:
                        kwargs["in_reply_to_tweet_id"] = in_reply_to_tweet_id
                    if quote_tweet_id:
                        kwargs["quote_tweet_id"] = quote_tweet_id
                    return self._tweepy_client.create_tweet(**kwargs)

                resp = await asyncio.to_thread(_do_post)
                if resp and resp.data:
                    t_id = resp.data.get("id") or resp.data["id"]
                    t_url = f"https://x.com/i/status/{t_id}"
                    return True, {"id": t_id, "text": text, "url": t_url}, t_url
            except Exception as e:
                logger.warning(f"[X CLIENT] Tweepy create_tweet failed, using native REST: {e}")

        # 2. Native REST API v2
        url = "https://api.twitter.com/2/tweets"
        payload: Dict[str, Any] = {"text": text}
        if media_ids:
            payload["media"] = {"media_ids": media_ids}
        if in_reply_to_tweet_id:
            payload["reply"] = {"in_reply_to_tweet_id": in_reply_to_tweet_id}
        if quote_tweet_id:
            payload["quote_tweet_id"] = quote_tweet_id

        headers = {"Content-Type": "application/json"}
        auth_header = self._generate_oauth1_header("POST", url)
        if auth_header:
            headers["Authorization"] = auth_header
        elif self.config.bearer_token:
            headers["Authorization"] = f"Bearer {self.config.bearer_token}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    data = await resp.json()
                    if resp.status in (200, 201) and "data" in data:
                        t_id = data["data"]["id"]
                        t_url = f"https://x.com/i/status/{t_id}"
                        return True, {"id": t_id, "text": text, "url": t_url}, t_url
                    else:
                        err_msg = data.get("detail") or data.get("title") or str(data)
                        return False, None, f"Tweet failed (HTTP {resp.status}): {err_msg}"
        except Exception as e:
            return False, None, f"Tweet post error: {e}"

    async def reply_to_tweet(self, tweet_id: str, text: str, media_ids: Optional[List[str]] = None) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """Replies to a tweet."""
        return await self.post_tweet(text=text, media_ids=media_ids, in_reply_to_tweet_id=tweet_id)

    async def like_tweet(self, tweet_id: str) -> bool:
        """Likes a tweet."""
        if not self.authenticated_user_id:
            await self.verify_credentials()
        if not self.authenticated_user_id:
            return False

        if self._tweepy_client and self.config.api_key and self.config.access_token:
            try:
                await asyncio.to_thread(self._tweepy_client.like, tweet_id, user_auth=True)
                return True
            except Exception:
                pass

        url = f"https://api.twitter.com/2/users/{self.authenticated_user_id}/likes"
        auth = self._generate_oauth1_header("POST", url)
        headers = {"Authorization": auth, "Content-Type": "application/json"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json={"tweet_id": tweet_id}, headers=headers) as resp:
                    return resp.status in (200, 201)
        except Exception:
            return False

    async def fetch_mentions(self, max_results: int = 10) -> List[Dict[str, Any]]:
        """Fetches recent mentions directed at the authenticated user."""
        if not self.authenticated_user_id:
            await self.verify_credentials()
        if not self.authenticated_user_id:
            return []

        # 1. Tweepy
        if self._tweepy_client and self.config.api_key and self.config.access_token:
            try:
                def _get_mentions():
                    kwargs = {
                        "id": self.authenticated_user_id,
                        "max_results": max_results,
                        "tweet_fields": ["created_at", "author_id", "conversation_id", "in_reply_to_user_id", "text"],
                        "expansions": ["author_id"]
                    }
                    if self.last_mention_id:
                        kwargs["since_id"] = self.last_mention_id
                    return self._tweepy_client.get_users_mentions(**kwargs)

                resp = await asyncio.to_thread(_get_mentions)
                if resp and resp.data:
                    mentions = []
                    users_by_id = {u.id: u for u in (resp.includes.get("users", []) if resp.includes else [])}
                    for t in resp.data:
                        author = users_by_id.get(t.author_id)
                        mentions.append({
                            "id": str(t.id),
                            "text": t.text,
                            "author_id": str(t.author_id),
                            "author_name": author.name if author else "",
                            "author_username": author.username if author else "",
                            "created_at": str(t.created_at)
                        })
                    return mentions
            except Exception as e:
                logger.warning(f"[X CLIENT] Tweepy fetch mentions failed: {e}")

        # 2. Native REST
        url = f"https://api.twitter.com/2/users/{self.authenticated_user_id}/mentions"
        params = {
            "max_results": str(max_results),
            "tweet.fields": "created_at,author_id,conversation_id,text",
            "expansions": "author_id"
        }
        if self.last_mention_id:
            params["since_id"] = self.last_mention_id

        headers = {}
        if self.config.bearer_token:
            headers["Authorization"] = f"Bearer {self.config.bearer_token}"
        else:
            headers["Authorization"] = self._generate_oauth1_header("GET", url, params)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        tweets = data.get("data", [])
                        users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}
                        result = []
                        for t in tweets:
                            author = users.get(t.get("author_id"), {})
                            result.append({
                                "id": str(t["id"]),
                                "text": t["text"],
                                "author_id": str(t.get("author_id")),
                                "author_name": author.get("name", ""),
                                "author_username": author.get("username", ""),
                                "created_at": t.get("created_at")
                            })
                        return result
        except Exception as e:
            logger.error(f"[X CLIENT] Fetch mentions error: {e}")
        return []

    async def send_dm(self, recipient_id: str, text: str) -> Tuple[bool, str]:
        """Sends a Direct Message (DM) to a user via API v2 DM events."""
        if self._tweepy_client and self.config.api_key and self.config.access_token:
            try:
                def _do_send_dm():
                    return self._tweepy_client.create_direct_message(
                        participant_id=recipient_id,
                        text=text
                    )
                resp = await asyncio.to_thread(_do_send_dm)
                return True, "DM sent."
            except Exception as e:
                logger.warning(f"[X CLIENT] Tweepy create_direct_message failed: {e}")

        # Native REST API v2 Direct Messages
        url = "https://api.twitter.com/2/dm_conversations/with_participant/messages"
        payload = {
            "participant_id": recipient_id,
            "message": {"text": text}
        }
        auth = self._generate_oauth1_header("POST", url)
        headers = {"Authorization": auth, "Content-Type": "application/json"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status in (200, 201):
                        return True, "DM sent successfully."
                    err = await resp.text()
                    return False, f"HTTP {resp.status}: {err}"
        except Exception as e:
            return False, f"DM send exception: {e}"

    async def fetch_direct_messages(self, max_results: int = 10) -> List[Dict[str, Any]]:
        """Fetches incoming direct message events."""
        if self._tweepy_client and self.config.api_key and self.config.access_token:
            try:
                def _get_dms():
                    return self._tweepy_client.get_direct_message_events(
                        max_results=max_results,
                        dm_event_fields=["id", "text", "sender_id", "created_at"],
                        expansions=["sender_id"]
                    )
                resp = await asyncio.to_thread(_get_dms)
                if resp and resp.data:
                    dms = []
                    users_by_id = {u.id: u for u in (resp.includes.get("users", []) if resp.includes else [])}
                    for event in resp.data:
                        if str(event.sender_id) != self.authenticated_user_id:
                            sender = users_by_id.get(event.sender_id)
                            dms.append({
                                "id": str(event.id),
                                "text": event.text,
                                "sender_id": str(event.sender_id),
                                "sender_username": sender.username if sender else "",
                                "sender_name": sender.name if sender else "",
                                "created_at": str(event.created_at)
                            })
                    return dms
            except Exception as e:
                logger.warning(f"[X CLIENT] Tweepy fetch DMs failed: {e}")

        # Native REST API v2 DM Events
        url = "https://api.twitter.com/2/dm_events"
        params = {"max_results": str(max_results), "dm_event.fields": "id,text,sender_id,created_at"}
        auth = self._generate_oauth1_header("GET", url, params)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers={"Authorization": auth}) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        events = data.get("data", [])
                        return [
                            {
                                "id": str(ev["id"]),
                                "text": ev.get("text", ""),
                                "sender_id": str(ev.get("sender_id")),
                                "created_at": ev.get("created_at")
                            }
                            for ev in events
                            if str(ev.get("sender_id")) != self.authenticated_user_id
                        ]
        except Exception as e:
            logger.error(f"[X CLIENT] Fetch DMs error: {e}")
        return []
