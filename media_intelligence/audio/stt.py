"""
Multi-Provider Speech-to-Text (STT) Engine with Failover.
Supports Groq Whisper-Large-v3-Turbo, Gemini Audio Multimodal, and OpenRouter Whisper.
"""
import os
import io
import re
import time
import json
import base64
import tempfile
import aiohttp
from typing import Optional, Tuple, List
from ..types import TranscriptSegment
from ..config import MAX_AUDIO_FILE_SIZE_MB


def fast_heuristic_speech_correct(text: str) -> str:
    """Instant zero-latency phonetic regex correction for well-known speech-to-text slips."""
    if not text:
        return text
    t = text
    # "my eyes heard" -> "my eyes hurt", "ear heard" -> "ear hurt", etc.
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


async def correct_speech_transcript(raw_text: str, groq_key: Optional[str] = None, gemini_key: Optional[str] = None) -> str:
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

    g_key = groq_key or os.getenv("GROQ_KEY", "")
    if g_key:
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

    gem_key = gemini_key or os.getenv("GEMINI_KEY", "")
    if gem_key:
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


class MultiProviderSTT:

    def __init__(self, groq_key: Optional[str] = None, gemini_key: Optional[str] = None, openrouter_key: Optional[str] = None):
        self.groq_key = groq_key or os.getenv("GROQ_KEY", "")
        self.gemini_key = gemini_key or os.getenv("GEMINI_KEY", "")
        self.openrouter_key = openrouter_key or os.getenv("OPENROUTER_KEY", "")

    async def transcribe(self, wav_bytes: bytes, filename: str = "speech.wav", model: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
        if not wav_bytes or len(wav_bytes) < 500:
            return "", None

        req_m = (model or "auto").strip().lower()
        raw_res = None

        # Prioritized list of candidates based on requested model
        if "large" in req_m and "turbo" not in req_m:
            candidates = [("groq", "whisper-large-v3"), ("groq", "whisper-large-v3-turbo"), ("gemini", "gemini-3.5-flash-lite")]
        elif "turbo" in req_m:
            candidates = [("groq", "whisper-large-v3-turbo"), ("groq", "whisper-large-v3"), ("gemini", "gemini-3.5-flash-lite")]
        elif "3.6" in req_m or "gemini-flash" in req_m:
            candidates = [("gemini", "gemini-3.6-flash"), ("gemini", "gemini-3.5-flash-lite"), ("groq", "whisper-large-v3-turbo")]
        elif "gemini" in req_m or "lite" in req_m:
            candidates = [("gemini", "gemini-3.5-flash-lite"), ("gemini", "gemini-3.6-flash"), ("groq", "whisper-large-v3-turbo")]
        else:
            # Auto cascade: Groq Turbo -> Groq Large -> Gemini Lite -> Gemini Flash
            candidates = [("groq", "whisper-large-v3-turbo"), ("groq", "whisper-large-v3"), ("gemini", "gemini-3.5-flash-lite"), ("gemini", "gemini-3.6-flash")]

        for prov, m_name in candidates:
            if raw_res:
                break
            if prov == "groq" and self.groq_key:
                res, err = await self._transcribe_groq(wav_bytes, filename, model_name=m_name)
                if not err and res:
                    raw_res = res
            elif prov == "gemini" and self.gemini_key:
                res, err = await self._transcribe_gemini(wav_bytes, model_name=m_name)
                if not err and res:
                    raw_res = res

        if not raw_res and self.openrouter_key:
            res, err = await self._transcribe_openrouter(wav_bytes, filename)
            if not err and res:
                raw_res = res

        if raw_res:
            corrected = await correct_speech_transcript(raw_res, groq_key=self.groq_key, gemini_key=self.gemini_key)
            if corrected and corrected != raw_res:
                print(f"[STT AI CORRECT] '{raw_res}' -> '{corrected}'")
                raw_res = corrected
            return raw_res, None

        return None, "All STT providers failed or no API keys configured."

    async def _transcribe_groq(self, wav_bytes: bytes, filename: str, model_name: str = "whisper-large-v3-turbo") -> Tuple[Optional[str], Optional[str]]:
        tmp_path = tempfile.mktemp(suffix=".wav")
        try:
            with open(tmp_path, "wb") as f:
                f.write(wav_bytes)

            async with aiohttp.ClientSession() as session:
                with open(tmp_path, "rb") as af:
                    data = aiohttp.FormData()
                    data.add_field("file", af, filename=filename, content_type="audio/wav")
                    data.add_field("model", model_name)
                    data.add_field("language", "en")  # Force Whisper to ONLY hear English
                    data.add_field("temperature", "0.0")
                    data.add_field("prompt", "Clear conversational English speech, standard vocabulary.")
                    data.add_field("response_format", "json")
                    async with session.post(
                        "https://api.groq.com/openai/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {self.groq_key}"},
                        data=data,
                        timeout=aiohttp.ClientTimeout(total=45)
                    ) as resp:
                        if resp.status == 200:
                            result = await resp.json()
                            return result.get("text", "").strip(), None
                        else:
                            txt = await resp.text()
                            return None, f"Groq STT ({model_name}) HTTP {resp.status}: {txt[:150]}"
        except Exception as e:
            return None, str(e)
        finally:
            if os.path.exists(tmp_path):
                try: os.remove(tmp_path)
                except: pass

    async def _transcribe_gemini(self, wav_bytes: bytes, model_name: str = "gemini-3.5-flash-lite") -> Tuple[Optional[str], Optional[str]]:
        try:
            b64_audio = base64.b64encode(wav_bytes).decode("utf-8")
            payload = {
                "contents": [{
                    "parts": [
                        {"text": "Transcribe this audio verbatim into English only. Never transcribe in non-English languages. Return only the spoken English dialogue."},
                        {"inline_data": {"mime_type": "audio/wav", "data": b64_audio}}
                    ]
                }]
            }
            async with aiohttp.ClientSession() as session:
                for target_m in [model_name, "gemini-3.5-flash-lite", "gemini-3.6-flash"]:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_m}:generateContent?key={self.gemini_key}"
                    async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=40)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                            if parts and parts[0].get("text"):
                                return parts[0]["text"].strip(), None
                return None, "Gemini STT models failed or returned empty"
        except Exception as e:
            return None, str(e)

    async def _transcribe_openrouter(self, wav_bytes: bytes, filename: str) -> Tuple[Optional[str], Optional[str]]:
        # OpenRouter fallback
        return None, "OpenRouter STT fallback unconfigured"
