"""
Photon / Spectrum (https://photon.codes/) Multi-Channel Gateway Connector.
Enables Yuna to bridge with Photon's unified agent infrastructure across
iMessage, WhatsApp, Telegram, X, Instagram, Discord, and Slack.
"""

import asyncio
import json
import logging
import os
import time
from typing import Optional, Dict, Any, List, Tuple, Callable
import aiohttp

from .config import PhotonConfig

logger = logging.getLogger("Social.PhotonClient")

class PhotonClient:
    """
    Client for Photon Spectrum (photon.codes) Multi-Channel Messaging Infrastructure.
    """

    def __init__(self, config: PhotonConfig):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self._running = False
        self._poll_task: Optional[asyncio.Task] = None

    def is_configured(self) -> bool:
        return bool(self.config.enabled and (self.config.api_key or self.config.gateway_url))

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            headers = {
                "User-Agent": "Yuna-Photon-Bridge/1.0",
                "Content-Type": "application/json"
            }
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"
                headers["X-Photon-API-Key"] = self.config.api_key
            self.session = aiohttp.ClientSession(headers=headers)
        return self.session

    async def close(self):
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        if self.session and not self.session.closed:
            await self.session.close()

    async def send_message(
        self,
        channel: str, # "x", "instagram", "imessage", "whatsapp", "slack", "discord"
        recipient_id: str,
        text: str,
        media_urls: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """
        Sends an outgoing message through Photon's unified multi-channel dispatch API.
        """
        endpoint = f"{self.config.endpoint.rstrip('/')}/messages/send"
        if self.config.gateway_url:
            endpoint = f"{self.config.gateway_url.rstrip('/')}/v1/messages/send"

        payload = {
            "channel": channel,
            "recipient_id": recipient_id,
            "text": text,
            "media_urls": media_urls or [],
            "metadata": metadata or {},
            "timestamp": time.time()
        }

        try:
            session = await self._get_session()
            async with session.post(endpoint, json=payload, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                data = await resp.json()
                if resp.status in (200, 201, 202):
                    return True, data, "Message dispatched via Photon Spectrum."
                err_msg = data.get("error") or data.get("message") or f"HTTP {resp.status}"
                return False, data, f"Photon send failed: {err_msg}"
        except Exception as e:
            return False, None, f"Photon client exception: {e}"

    async def handle_webhook_event(
        self,
        event_data: Dict[str, Any],
        ask_ai_fn: Callable,
        watch_video_fn: Optional[Callable] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Processes an incoming multi-channel event received from Photon webhooks.
        """
        channel = event_data.get("channel", "unknown")
        sender_id = event_data.get("sender_id", "user")
        sender_name = event_data.get("sender_name", sender_id)
        text = event_data.get("text", "")
        media_items = event_data.get("media", [])

        logger.info(f"[PHOTON WEBHOOK] Incoming message from {channel} user @{sender_name}: {text[:60]}")

        # Check for media / videos in incoming Photon message
        extra_context = ""
        if media_items and watch_video_fn:
            for item in media_items:
                m_type = item.get("type", "")
                m_url = item.get("url", "")
                if m_type == "video" and m_url:
                    try:
                        v_context, _ = await watch_video_fn(m_url)
                        extra_context += f"\n\n[Observed Attached Video ({m_url})]:\n{v_context}"
                    except Exception as ve:
                        logger.warning(f"[PHOTON] Video analysis failed: {ve}")

        prompt = f"Message received from {channel.upper()} by {sender_name}: \"{text}\""
        if extra_context:
            prompt += extra_context

        reply, err = await ask_ai_fn(
            channel_id=f"photon_{channel}_{sender_id}",
            prompt=prompt,
            user_id=sender_id,
            user_name=sender_name,
            is_dm=True
        )

        if not err and reply:
            await self.send_message(
                channel=channel,
                recipient_id=sender_id,
                text=reply
            )
            return {"status": "replied", "reply": reply}
        return {"status": "error", "error": err}
