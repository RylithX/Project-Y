# -*- coding: utf-8 -*-
"""
doodle_engine.py - AI Doodling on Command & Doodle-Along Engine
Allows Discord bot personas and the web dashboard to actually draw, doodle on command,
and collaboratively doodle along with users on drawings/sketches.
"""

import io
import os
import math
import random
import re
import urllib.parse
import aiohttp
import asyncio
from typing import Optional, Tuple, Dict, Any, List
from PIL import Image, ImageDraw, ImageFont, ImageFilter


def is_doodle_request(text: str) -> Tuple[bool, str, str]:
    """
    Detects if a user message is asking the AI to draw or doodle along.
    Returns: (is_request, mode, subject)
    Modes: "along", "draw", "none"
    """
    if not text:
        return False, "none", ""
    t = text.strip().lower()

    # Commands
    if t.startswith(("!doodlealong", "!drawwithme", "!doodletogether", "!co-doodle", "/doodlealong")):
        parts = text.strip().split(None, 1)
        sub = parts[1].strip() if len(parts) > 1 else ""
        return True, "along", sub

    if t.startswith(("!doodle", "!draw", "!sketch", "!paint", "!scribble", "/doodle", "/draw")):
        parts = text.strip().split(None, 1)
        sub = parts[1].strip() if len(parts) > 1 else "cute cat"
        return True, "draw", sub

    # Doodle along conversational triggers
    doodle_along_patterns = [
        r"(?:doodle|draw|sketch)\s+along(?:\s+with\s+me)?(?:\s*[:,\-]?\s*(.*))?",
        r"(?:let'?s|wanna|can we)\s+(?:doodle|draw|sketch)\s+together(?:\s*[:,\-]?\s*(.*))?",
        r"add\s+(?:something|a doodle|to this|to my drawing)(?:\s*[:,\-]?\s*(.*))?",
        r"doodle\s+on\s+this(?:\s*[:,\-]?\s*(.*))?",
        r"finish\s+my\s+(?:drawing|doodle|sketch)(?:\s*[:,\-]?\s*(.*))?",
    ]
    for pat in doodle_along_patterns:
        m = re.search(pat, t)
        if m:
            sub = m.group(1).strip() if m.lastindex and m.group(1) else ""
            return True, "along", sub

    # Draw on command conversational triggers
    draw_patterns = [
        r"(?:can you|could you|please|will you)?\s*(?:draw|doodle|sketch|paint)\s+(?:me\s+)?(?:a|an|some)?\s*(.+)",
        r"(?:make|create)\s+(?:a|an)\s+(?:doodle|drawing|sketch)\s+of\s+(.+)",
        r"i want you to (?:draw|doodle|sketch)\s+(.+)",
    ]
    for pat in draw_patterns:
        m = re.search(pat, t)
        if m:
            sub = m.group(1).strip()
            if not any(sub.startswith(fp) for fp in ["conclusion", "conclusions", "a card", "the line", "near", "attention"]):
                return True, "draw", sub

    return False, "none", ""


def _procedural_fallback_doodle(subject: str, bot_name: str = "Bot") -> bytes:
    """Procedurally renders a charming hand-drawn line-art doodle using Pillow as fallback."""
    width, height = 600, 600
    img = Image.new("RGBA", (width, height), (252, 250, 245, 255))
    draw = ImageDraw.Draw(img)

    for y in range(40, height, 30):
        draw.line([(0, y), (width, y)], fill=(235, 240, 248, 255), width=1)
    draw.line([(60, 0), (60, height)], fill=(255, 220, 225, 255), width=2)

    ink = (35, 40, 50, 255)
    accent = random.choice([
        (255, 107, 107, 255), (78, 205, 196, 255),
        (254, 202, 87, 255), (84, 160, 255, 255), (255, 159, 243, 255)
    ])

    cx, cy = 320, 280
    r = 90
    points = []
    for angle in range(0, 360, 15):
        rad = angle * 3.14159 / 180
        wobble = random.randint(-3, 3)
        px = cx + int((r + wobble) * 0.9 * math.cos(rad))
        py = cy + int((r + wobble) * math.sin(rad))
        points.append((px, py))
    points.append(points[0])
    draw.line(points, fill=ink, width=4)

    draw.line([(cx - 65, cy - 65), (cx - 85, cy - 120), (cx - 35, cy - 80)], fill=ink, width=4)
    draw.line([(cx + 65, cy - 65), (cx + 85, cy - 120), (cx + 35, cy - 80)], fill=ink, width=4)

    draw.ellipse([(cx - 40, cy - 20), (cx - 25, cy)], fill=ink)
    draw.ellipse([(cx + 25, cy - 20), (cx + 40, cy)], fill=ink)
    draw.ellipse([(cx - 36, cy - 17), (cx - 30, cy - 11)], fill=(255, 255, 255, 255))
    draw.ellipse([(cx + 29, cy - 17), (cx + 35, cy - 11)], fill=(255, 255, 255, 255))

    draw.ellipse([(cx - 60, cy + 10), (cx - 35, cy + 25)], fill=(accent[0], accent[1], accent[2], 120))
    draw.ellipse([(cx + 35, cy + 10), (cx + 60, cy + 25)], fill=(accent[0], accent[1], accent[2], 120))

    draw.polygon([(cx - 6, cy + 10), (cx + 6, cy + 10), (cx, cy + 16)], fill=ink)
    draw.arc([(cx - 25, cy + 12), (cx, cy + 32)], start=0, end=180, fill=ink, width=3)
    draw.arc([(cx, cy + 12), (cx + 25, cy + 32)], start=0, end=180, fill=ink, width=3)

    draw.line([(cx - 85, cy + 5), (cx - 50, cy + 10)], fill=ink, width=2)
    draw.line([(cx - 90, cy + 25), (cx - 52, cy + 22)], fill=ink, width=2)
    draw.line([(cx + 50, cy + 10), (cx + 85, cy + 5)], fill=ink, width=2)
    draw.line([(cx + 52, cy + 22), (cx + 90, cy + 25)], fill=ink, width=2)

    draw.arc([(cx - 50, cy + 70), (cx - 15, cy + 105)], start=180, end=360, fill=ink, width=4)
    draw.arc([(cx + 15, cy + 70), (cx + 50, cy + 105)], start=180, end=360, fill=ink, width=4)

    def draw_sparkle(x, y, sz, col):
        draw.line([(x - sz, y), (x + sz, y)], fill=col, width=3)
        draw.line([(x, y - sz), (x, y + sz)], fill=col, width=3)
        draw.line([(x - sz // 2, y - sz // 2), (x + sz // 2, y + sz // 2)], fill=col, width=2)
        draw.line([(x - sz // 2, y + sz // 2), (x + sz // 2, y - sz // 2)], fill=col, width=2)

    draw_sparkle(160, 150, 16, accent)
    draw_sparkle(480, 180, 20, accent)
    draw_sparkle(130, 420, 14, ink)
    draw_sparkle(500, 390, 16, ink)

    draw.rounded_rectangle([(180, 430), (460, 480)], radius=15, outline=ink, width=3, fill=(255, 255, 255, 240))
    draw.polygon([(260, 430), (280, 410), (300, 430)], fill=(255, 255, 255, 240), outline=ink)

    clean_sub = (subject[:30] + "...") if len(subject) > 30 else subject
    caption_text = f"Doodle: {clean_sub}"
    sig_text = f"Doodled by {bot_name} <3"

    try:
        font = ImageFont.load_default()
        draw.text((200, 445), caption_text, fill=ink, font=font)
        draw.text((70, 540), sig_text, fill=(130, 130, 150, 255), font=font)
    except Exception:
        pass

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


async def generate_doodle(
    prompt: str,
    bot_name: str = "Yuna",
    bot_personality: str = "",
    style: str = "doodle"
) -> Tuple[Optional[bytes], str]:
    """
    Generates an actual hand-drawn doodle / sketch based on the user prompt.
    Uses high-speed Pollinations doodle synthesis, with procedural PIL fallback.
    Returns: (image_bytes, commentary)
    """
    clean_prompt = prompt.strip()
    if not clean_prompt:
        clean_prompt = "cute cat taking a nap"

    commentaries = [
        f"*flips open sketchbook and scribbles furiously* Finished! Here is my doodle of **{clean_prompt}**! What do you think?",
        f"*taps pen on chin, smiles brightly* Tadaa! Doodled **{clean_prompt}** just for you! 🎨✨",
        f"*doodles with intense focus and giggles* Look at this! My fresh sketch of **{clean_prompt}**!",
        f"*proudly shows off the canvas* Here you go! One custom doodle of **{clean_prompt}**!",
    ]
    if "law" in bot_name.lower() or "death note" in bot_personality.lower():
        commentaries = [
            f"*sketches methodically in notebook* Finished the deduction sketch of **{clean_prompt}**.",
            f"Here is the doodle of **{clean_prompt}**. Exactly 97.4% precision on the ink lines.",
            f"*spins pen* A quick doodle of **{clean_prompt}**. Not bad for a quick sketch."
        ]

    commentary = random.choice(commentaries)

    doodle_style_prompt = (
        f"cute minimalist hand-drawn doodle sketch, black ink line art on clean white notebook paper, "
        f"charming playful sketchbook doodle of {clean_prompt}, clean lines, whimsical, high quality illustration"
    )
    encoded = urllib.parse.quote(doodle_style_prompt)
    seed = random.randint(1, 999999)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=640&height=640&nologo=true&seed={seed}"

    try:
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    if len(data) > 2000:
                        try:
                            img = Image.open(io.BytesIO(data)).convert("RGBA")
                            draw = ImageDraw.Draw(img)
                            sig = f"✎ {bot_name} doodle"
                            draw.text((15, img.height - 25), sig, fill=(120, 120, 130, 200))
                            out = io.BytesIO()
                            img.convert("RGB").save(out, format="PNG")
                            return out.getvalue(), commentary
                        except Exception:
                            return data, commentary
    except Exception as e:
        print(f"[DOODLE ENGINE] Online doodle generator failed: {e}. Falling back to procedural sketch.")

    fallback_bytes = _procedural_fallback_doodle(clean_prompt, bot_name)
    return fallback_bytes, commentary


async def doodle_along(
    base_image_bytes: bytes,
    user_prompt: str = "",
    bot_name: str = "Yuna",
    bot_personality: str = "",
    vision_analyzer_coro = None
) -> Tuple[bytes, str]:
    """
    Collaborative Doodle Along:
    Takes an image (user drawing / sketch), analyzes it, and actually doodles along with it:
    adds complementary doodle elements, stickers, companion doodles, speech bubbles, and signature.
    Returns: (composited_image_bytes, in_character_dialogue)
    """
    try:
        base_img = Image.open(io.BytesIO(base_image_bytes)).convert("RGBA")
    except Exception:
        fallback, com = await generate_doodle(user_prompt or "collaborative sketch", bot_name, bot_personality)
        return fallback, com

    max_dim = 1024
    if base_img.width > max_dim or base_img.height > max_dim:
        base_img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
    elif base_img.width < 300 or base_img.height < 300:
        base_img = base_img.resize((600, 600), Image.Resampling.BICUBIC)

    w, h = base_img.width, base_img.height

    if vision_analyzer_coro:
        try:
            detected_desc = await vision_analyzer_coro(base_image_bytes, user_prompt)
        except Exception as ve:
            print(f"[DOODLE ALONG] Vision analysis note: {ve}")

    complement_subjects = [
        "cute little mascot cheering", "happy sleeping kitty", "smiling star wearing sunglasses",
        "cute baby dragon with wings", "tiny ghost with party hat", "cute blushing hamster"
    ]
    if user_prompt:
        comp_subject = f"cute mini companion doodle to {user_prompt}"
    else:
        comp_subject = random.choice(complement_subjects)

    sticker_bytes, _ = await generate_doodle(comp_subject, bot_name, bot_personality)

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    if sticker_bytes:
        try:
            sticker_img = Image.open(io.BytesIO(sticker_bytes)).convert("RGBA")
            st_w = int(w * 0.32)
            st_h = int(st_w * (sticker_img.height / sticker_img.width))
            sticker_img = sticker_img.resize((st_w, st_h), Image.Resampling.LANCZOS)

            frame = Image.new("RGBA", (st_w + 16, st_h + 36), (255, 255, 255, 240))
            fdraw = ImageDraw.Draw(frame)
            fdraw.rectangle([(0, 0), (st_w + 15, st_h + 35)], outline=(40, 40, 50, 200), width=3)
            frame.paste(sticker_img, (8, 8), sticker_img)
            fdraw.text((12, st_h + 12), f"✎ {bot_name} add!", fill=(40, 40, 50, 255))

            pos_x = w - frame.width - 20
            pos_y = h - frame.height - 20
            base_img.paste(frame, (pos_x, pos_y), frame)
        except Exception as e:
            print(f"[DOODLE ALONG] Sticker composite note: {e}")

    accent_colors = [(255, 107, 107, 240), (254, 202, 87, 240), (78, 205, 196, 240), (255, 159, 243, 240)]

    def draw_doodle_star(cx, cy, r, col):
        draw.line([(cx - r, cy), (cx + r, cy)], fill=col, width=3)
        draw.line([(cx, cy - r), (cx, cy + r)], fill=col, width=3)
        draw.line([(cx - r * 0.5, cy - r * 0.5), (cx + r * 0.5, cy + r * 0.5)], fill=col, width=2)
        draw.line([(cx - r * 0.5, cy + r * 0.5), (cx + r * 0.5, cy - r * 0.5)], fill=col, width=2)

    def draw_doodle_heart(cx, cy, sz, col):
        draw.polygon([
            (cx, cy + sz), (cx - sz, cy), (cx - sz // 2, cy - sz),
            (cx, cy - sz // 2), (cx + sz // 2, cy - sz), (cx + sz, cy)
        ], fill=col)

    draw_doodle_star(40, 40, 16, random.choice(accent_colors))
    draw_doodle_star(w - 50, 45, 18, random.choice(accent_colors))
    draw_doodle_heart(70, h - 60, 12, (255, 90, 120, 220))
    draw_doodle_star(w // 2, 30, 14, (254, 202, 87, 220))

    stamp_text = f"★ Doodled Together with {bot_name} ★"
    try:
        draw.rectangle([(0, 0), (w, 32)], fill=(20, 20, 30, 140))
        draw.text((20, 8), stamp_text, fill=(255, 255, 255, 240))
    except Exception:
        pass

    result_img = Image.alpha_composite(base_img, overlay).convert("RGB")
    buf = io.BytesIO()
    result_img.save(buf, format="PNG")
    output_bytes = buf.getvalue()

    add_lines = [
        f"*gasps excitedly and grabs pen* I love your drawing so much! Look, I doodled along with you! I added a little companion friend, sparkle stars, and my seal of approval! 🎨💖 What should we add next?",
        f"*smiles warmly and doodles right alongside you* That sketch of yours was super inspiring! I jumped in and doodled a friend to keep yours company! We make an awesome art duo! ✨",
        f"*adds strokes with careful enthusiasm* Here we go! I doodled right along with your piece! Look at our joint masterpiece! 🖌️💫",
    ]
    if "law" in bot_name.lower():
        add_lines = [
            f"*examines your sketch and picks up pen* A solid foundation. I have added complementary markings, annotations, and a secondary figure to balance the composition. Our collaborative piece is complete.",
            f"I have added to your doodle as requested. The visual synergy is now optimal."
        ]

    dialogue = random.choice(add_lines)
    return output_bytes, dialogue


VECTOR_DOODLE_REGISTRY: Dict[str, Dict[str, Any]] = {
    "cat": {
        "word": "Cat",
        "hint": "A furry domestic pet with whiskers that meows!",
        "strokes": [
            {"color": "#111111", "size": 6, "points": [{"x": 0.35, "y": 0.45}, {"x": 0.40, "y": 0.38}, {"x": 0.50, "y": 0.36}, {"x": 0.60, "y": 0.38}, {"x": 0.65, "y": 0.45}, {"x": 0.67, "y": 0.55}, {"x": 0.63, "y": 0.65}, {"x": 0.50, "y": 0.68}, {"x": 0.37, "y": 0.65}, {"x": 0.33, "y": 0.55}, {"x": 0.35, "y": 0.45}]},
            {"color": "#111111", "size": 6, "points": [{"x": 0.37, "y": 0.40}, {"x": 0.33, "y": 0.25}, {"x": 0.45, "y": 0.36}]},
            {"color": "#111111", "size": 6, "points": [{"x": 0.55, "y": 0.36}, {"x": 0.67, "y": 0.25}, {"x": 0.63, "y": 0.40}]},
            {"color": "#111111", "size": 8, "points": [{"x": 0.43, "y": 0.48}, {"x": 0.43, "y": 0.49}]},
            {"color": "#111111", "size": 8, "points": [{"x": 0.57, "y": 0.48}, {"x": 0.57, "y": 0.49}]},
            {"color": "#e85d5d", "size": 5, "points": [{"x": 0.48, "y": 0.55}, {"x": 0.52, "y": 0.55}, {"x": 0.50, "y": 0.58}]},
            {"color": "#111111", "size": 4, "points": [{"x": 0.50, "y": 0.58}, {"x": 0.45, "y": 0.62}]},
            {"color": "#111111", "size": 4, "points": [{"x": 0.50, "y": 0.58}, {"x": 0.55, "y": 0.62}]},
            {"color": "#111111", "size": 3, "points": [{"x": 0.30, "y": 0.53}, {"x": 0.42, "y": 0.54}]},
            {"color": "#111111", "size": 3, "points": [{"x": 0.28, "y": 0.60}, {"x": 0.42, "y": 0.57}]},
            {"color": "#111111", "size": 3, "points": [{"x": 0.58, "y": 0.54}, {"x": 0.70, "y": 0.53}]},
            {"color": "#111111", "size": 3, "points": [{"x": 0.58, "y": 0.57}, {"x": 0.72, "y": 0.60}]}
        ]
    },
    "pikachu": {
        "word": "Pikachu",
        "hint": "An iconic yellow electric mouse with red cheeks!",
        "strokes": [
            {"color": "#feca57", "size": 8, "points": [{"x": 0.38, "y": 0.42}, {"x": 0.50, "y": 0.38}, {"x": 0.62, "y": 0.42}, {"x": 0.66, "y": 0.56}, {"x": 0.60, "y": 0.68}, {"x": 0.40, "y": 0.68}, {"x": 0.34, "y": 0.56}, {"x": 0.38, "y": 0.42}]},
            {"color": "#feca57", "size": 7, "points": [{"x": 0.40, "y": 0.40}, {"x": 0.26, "y": 0.22}, {"x": 0.46, "y": 0.38}]},
            {"color": "#111111", "size": 6, "points": [{"x": 0.26, "y": 0.22}, {"x": 0.32, "y": 0.27}]},
            {"color": "#feca57", "size": 7, "points": [{"x": 0.54, "y": 0.38}, {"x": 0.74, "y": 0.22}, {"x": 0.60, "y": 0.40}]},
            {"color": "#111111", "size": 6, "points": [{"x": 0.74, "y": 0.22}, {"x": 0.68, "y": 0.27}]},
            {"color": "#e85d5d", "size": 10, "points": [{"x": 0.38, "y": 0.58}, {"x": 0.38, "y": 0.59}]},
            {"color": "#e85d5d", "size": 10, "points": [{"x": 0.62, "y": 0.58}, {"x": 0.62, "y": 0.59}]},
            {"color": "#111111", "size": 7, "points": [{"x": 0.44, "y": 0.50}, {"x": 0.44, "y": 0.51}]},
            {"color": "#111111", "size": 7, "points": [{"x": 0.56, "y": 0.50}, {"x": 0.56, "y": 0.51}]},
            {"color": "#111111", "size": 4, "points": [{"x": 0.48, "y": 0.59}, {"x": 0.50, "y": 0.61}, {"x": 0.52, "y": 0.59}]}
        ]
    },
    "dragon": {
        "word": "Dragon",
        "hint": "A mythical fire-breathing reptile with wings!",
        "strokes": [
            {"color": "#10ac84", "size": 7, "points": [{"x": 0.40, "y": 0.40}, {"x": 0.52, "y": 0.35}, {"x": 0.60, "y": 0.42}, {"x": 0.55, "y": 0.55}, {"x": 0.42, "y": 0.52}, {"x": 0.40, "y": 0.40}]},
            {"color": "#ff9f43", "size": 6, "points": [{"x": 0.46, "y": 0.36}, {"x": 0.42, "y": 0.25}]},
            {"color": "#ff9f43", "size": 6, "points": [{"x": 0.54, "y": 0.36}, {"x": 0.58, "y": 0.25}]},
            {"color": "#10ac84", "size": 8, "points": [{"x": 0.48, "y": 0.55}, {"x": 0.46, "y": 0.75}, {"x": 0.56, "y": 0.75}]},
            {"color": "#54a0ff", "size": 5, "points": [{"x": 0.42, "y": 0.58}, {"x": 0.25, "y": 0.45}, {"x": 0.28, "y": 0.62}, {"x": 0.43, "y": 0.65}]},
            {"color": "#54a0ff", "size": 5, "points": [{"x": 0.56, "y": 0.58}, {"x": 0.73, "y": 0.45}, {"x": 0.70, "y": 0.62}, {"x": 0.55, "y": 0.65}]},
            {"color": "#ee5253", "size": 6, "points": [{"x": 0.60, "y": 0.45}, {"x": 0.72, "y": 0.42}, {"x": 0.78, "y": 0.48}, {"x": 0.68, "y": 0.50}]}
        ]
    }
}


def get_vector_doodle_blueprint(prompt: str) -> Dict[str, Any]:
    """Retrieves or generates a vector stroke blueprint for real-time canvas animation in Web Studio."""
    clean = prompt.lower().strip()
    for key, bp in VECTOR_DOODLE_REGISTRY.items():
        if key in clean or bp["word"].lower() in clean:
            return bp

    word = prompt.strip().capitalize()
    return {
        "word": word,
        "hint": f"A creative doodle of {word}!",
        "strokes": [
            {"color": "#111111", "size": 6, "points": [{"x": 0.35, "y": 0.40}, {"x": 0.50, "y": 0.32}, {"x": 0.65, "y": 0.40}, {"x": 0.65, "y": 0.65}, {"x": 0.50, "y": 0.72}, {"x": 0.35, "y": 0.65}, {"x": 0.35, "y": 0.40}]},
            {"color": "#54a0ff", "size": 5, "points": [{"x": 0.42, "y": 0.48}, {"x": 0.46, "y": 0.48}]},
            {"color": "#54a0ff", "size": 5, "points": [{"x": 0.54, "y": 0.48}, {"x": 0.58, "y": 0.48}]},
            {"color": "#e85d5d", "size": 4, "points": [{"x": 0.46, "y": 0.58}, {"x": 0.50, "y": 0.62}, {"x": 0.54, "y": 0.58}]},
            {"color": "#feca57", "size": 4, "points": [{"x": 0.28, "y": 0.30}, {"x": 0.32, "y": 0.30}]},
            {"color": "#feca57", "size": 4, "points": [{"x": 0.30, "y": 0.28}, {"x": 0.30, "y": 0.32}]},
            {"color": "#ff9f43", "size": 4, "points": [{"x": 0.68, "y": 0.30}, {"x": 0.72, "y": 0.30}]},
            {"color": "#ff9f43", "size": 4, "points": [{"x": 0.70, "y": 0.28}, {"x": 0.70, "y": 0.32}]}
        ]
    }
