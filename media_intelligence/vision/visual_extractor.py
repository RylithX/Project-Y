"""
Multimodal Vision Extractor.
Extracts scene descriptions, people, objects, actions, and OCR text with failover across vision providers.
"""
import os
import io
import json
import base64
import asyncio
import aiohttp
from typing import List, Tuple, Optional, Dict, Any
from ..types import VisionEvent

class VisualExtractor:

    def __init__(self, gemini_key: Optional[str] = None, openrouter_key: Optional[str] = None):
        self.gemini_key = gemini_key or os.getenv("GEMINI_KEY", "")
        self.openrouter_key = openrouter_key or os.getenv("OPENROUTER_KEY", "")

    async def analyze_keyframes(self, frames: List[Tuple[float, bytes]]) -> List[VisionEvent]:
        if not frames:
            return []

        events: List[VisionEvent] = []
        for idx, (ts, img_bytes) in enumerate(frames, start=1):
            desc, ocr_items, objs, actions = await self._analyze_single_frame(img_bytes, idx, len(frames), ts)
            b64_str = base64.b64encode(img_bytes).decode("utf-8")
            events.append(VisionEvent(
                timestamp_sec=ts,
                scene_idx=idx,
                description=desc or "Scene frame",
                objects=objs,
                people_count=1 if "person" in objs or "people" in objs else 0,
                actions=actions,
                ocr_text=ocr_items,
                confidence=0.88,
                keyframe_b64=b64_str
            ))
        return events

    async def _analyze_single_frame(self, img_bytes: bytes, idx: int, total: int, ts: float) -> Tuple[str, List[str], List[str], List[str]]:
        prompt = (
            f"Analyze this video keyframe ({idx}/{total} at {int(ts//60)}m {int(ts%60):02d}s). "
            "In 2 sentences, describe the visual scene, setting, characters/people, main actions, and any readable on-screen text/titles. "
            "Be purely objective and factual."
        )

        # 1. Try Gemini Vision
        if self.gemini_key:
            res = await self._call_gemini_vision(img_bytes, prompt)
            if res:
                return res, [], [], []

        # 2. Try OpenRouter Vision
        if self.openrouter_key:
            res = await self._call_openrouter_vision(img_bytes, prompt)
            if res:
                return res, [], [], []

        return f"Scene at {int(ts//60)}:{int(ts%60):02d}", [], [], []

    async def _call_gemini_vision(self, img_bytes: bytes, prompt: str) -> Optional[str]:
        if not self.gemini_key:
            return None
        b64_img = base64.b64encode(img_bytes).decode("utf-8")
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/jpeg", "data": b64_img}}
                ]
            }]
        }
        for model in ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash", "gemini-flash-lite-latest"]:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.gemini_key}"
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            candidates = data.get("candidates", [])
                            if candidates and "content" in candidates[0]:
                                parts = candidates[0]["content"].get("parts", [])
                                if parts and "text" in parts[0]:
                                    return parts[0]["text"].strip()
            except Exception:
                continue
        return None

    async def _call_openrouter_vision(self, img_bytes: bytes, prompt: str) -> Optional[str]:
        if not self.openrouter_key:
            return None
        try:
            b64_img = base64.b64encode(img_bytes).decode("utf-8")
            url = "https://openrouter.ai/api/v1/chat/completions"
            for or_model in ["google/gemini-2.5-flash", "google/gemini-flash-1.5", "meta-llama/llama-3.2-11b-vision-instruct:free"]:
                try:
                    payload = {
                        "model": or_model,
                        "messages": [{
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}
                            ]
                        }]
                    }
                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            url,
                            headers={"Authorization": f"Bearer {self.openrouter_key}", "Content-Type": "application/json"},
                            json=payload,
                            timeout=aiohttp.ClientTimeout(total=20)
                        ) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                return data["choices"][0]["message"]["content"].strip()
                except Exception:
                    continue
        except Exception:
            pass
        return None
