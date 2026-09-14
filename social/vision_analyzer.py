"""
Vision & Multimodal Content Analyzer for Social Media Posts.
Analyzes screenshots, images, and videos, then prompts Yuna AI to craft
an authentic, in-character caption for X (Twitter) or Instagram.
"""

import asyncio
import io
import logging
import os
import time
from typing import Optional, Dict, Any, Tuple, List
from pathlib import Path

logger = logging.getLogger("Social.VisionAnalyzer")

class SocialContentAnalyzer:
    """
    Analyzes visual media (screenshots, photos, clips, videos)
    and generates character-authentic captions for social media posting.
    """

    def __init__(self, bot_config: Optional[Dict[str, Any]] = None):
        self.config = bot_config or {}

    async def analyze_and_caption(
        self,
        media_bytes: Optional[bytes] = None,
        media_path: Optional[str] = None,
        media_url: Optional[str] = None,
        media_type: str = "image", # "image" or "video"
        platform: str = "x", # "x" or "instagram"
        user_prompt: str = "",
        ask_ai_fn: Optional[Any] = None,
        ask_vision_fn: Optional[Any] = None,
        media_analyzer_fn: Optional[Any] = None
    ) -> Tuple[str, str, Optional[Dict[str, Any]]]:
        """
        Analyzes the media and produces: (caption, analysis_summary, metadata)
        """
        analysis_summary = ""
        metadata: Dict[str, Any] = {
            "platform": platform,
            "media_type": media_type,
            "timestamp": time.time()
        }

        # 1. Analyze Video Content
        if media_type == "video":
            if media_analyzer_fn and (media_url or media_path):
                try:
                    target = media_url or media_path
                    context_data, report = await media_analyzer_fn(target, bot_config=self.config)
                    analysis_summary = context_data
                    metadata["report"] = report
                except Exception as e:
                    logger.warning(f"[VISION ANALYZER] Video analysis fallback: {e}")
                    analysis_summary = f"Video content from {media_url or media_path}"
            else:
                analysis_summary = f"A video clip shared by user: {user_prompt or 'New video post'}"

        # 2. Analyze Image / Screenshot Content
        elif media_type == "image":
            if ask_vision_fn and media_bytes:
                try:
                    vision_prompt = (
                        "Analyze this screenshot/image in detail. "
                        "Describe what is visibly happening, key characters, text, UI elements, gameplay, "
                        "aesthetic mood, and funny/interesting details."
                    )
                    v_reply, v_err = await ask_vision_fn(
                        "You are an expert visual analyzer observing an image.",
                        vision_prompt,
                        media_bytes,
                        "image/jpeg"
                    )
                    if not v_err and v_reply:
                        analysis_summary = v_reply
                    else:
                        analysis_summary = f"Screenshot / image showing interesting visual content."
                except Exception as e:
                    logger.warning(f"[VISION ANALYZER] Image vision analysis error: {e}")
                    analysis_summary = "An aesthetic screenshot/image."
            else:
                analysis_summary = f"Image shared: {user_prompt or 'Screenshot/Photo'}"

        # 3. Generate Social Media Caption in Bot's Persona
        character_name = self.config.get("name") or self.config.get("character_name") or "AI Companion"
        personality = self.config.get("personality") or f"You are {character_name}."
        
        char_limit = 270 if platform.lower() == "x" else 2000
        platform_name = "X (Twitter)" if platform.lower() == "x" else "Instagram"

        caption_generation_prompt = (
            f"=== TASK: WRITE A {platform_name.upper()} POST CAPTION ===\n"
            f"You are {character_name}. You are posting a new {media_type} to your official {platform_name} account!\n\n"
            f"--- OBSERVED VISUAL CONTENT & SCENE ANALYSIS ---\n"
            f"{analysis_summary}\n\n"
        )
        if user_prompt:
            caption_generation_prompt += f"--- USER NOTE / EXTRA CONTEXT ---\n\"{user_prompt}\"\n\n"

        caption_generation_prompt += (
            f"--- CAPTION REQUIREMENTS ---\n"
            f"1. Write an authentic, charismatic post caption in YOUR TRUE PERSONALITY ({character_name}'s authentic style, tone, and vibe).\n"
            f"2. CRITICAL RULE: NO ROLEPLAYING AND NO ACTIONS. NEVER use asterisks `*...*` and NEVER write roleplay actions (e.g. NO `*smiles*`, `*giggles*`, `*sighs*`, `*winks*`). Talk directly and naturally like a real person posting online.\n"
            f"3. Keep it SHORT and snappy (1-2 short sentences maximum, under {char_limit} characters).\n"
            f"4. Add 1-2 natural emojis or aesthetic hashtags if fitting.\n"
            f"5. IMPORTANT: Output ONLY the final caption text ready to be posted directly. Do not include quotes around the entire caption or meta explanations."
        )

        caption = ""
        if ask_ai_fn:
            try:
                reply, err = await ask_ai_fn(
                    channel_id="social_caption_generator",
                    prompt=caption_generation_prompt,
                    system_msg_override=personality
                )
                if not err and reply:
                    caption = reply.strip().strip('"').strip("'")
            except Exception as e:
                logger.error(f"[VISION ANALYZER] Caption generation error: {e}")

        if not caption:
            # Fallback default caption
            if platform.lower() == "x":
                caption = f"Look at this! ✨ What do you think? #Yuna"
            else:
                caption = f"Just sharing this with you all~ 💕 Hope you love it as much as I do! ✨ #Yuna"

        return caption, analysis_summary, metadata
