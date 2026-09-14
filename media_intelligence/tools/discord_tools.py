"""
Discord Bot Tools and High-Level Integration Interface.
Provides video watching (YouTube, Insta, TikTok, Twitter/X, Reddit, direct), web browsing, and search tools.
"""
import re
from typing import Optional, Dict, Any, Tuple, List
from ..config import MediaConfig, MAX_VIDEO_DURATION_SECONDS
from ..pipeline.analyzer import UniversalMediaAnalyzer
from ..pipeline.web_browser import UniversalWebBrowser

# Regex to detect media and web URLs
VIDEO_URL_REGEX = re.compile(
    r'(?:https?:\/\/)?(?:www\.|m\.)?(?:youtube\.com\/(?:watch\?v=|embed\/|v\/|shorts\/|live\/)|youtu\.be\/)[a-zA-Z0-9_-]{11}|'
    r'(?:https?:\/\/)?(?:www\.)?(?:instagram\.com\/(?:p|reel|tv)\/[a-zA-Z0-9_-]+|'
    r'tiktok\.com\/@?[a-zA-Z0-9_.-]+\/video\/\d+|vm\.tiktok\.com\/[a-zA-Z0-9_-]+|'
    r'(?:twitter\.com|x\.com)\/[a-zA-Z0-9_]+\/status\/\d+|'
    r'reddit\.com\/r\/[a-zA-Z0-9_]+\/comments\/[a-zA-Z0-9_]+|v\.redd\.it\/[a-zA-Z0-9]+|'
    r'twitch\.tv\/(?:videos\/\d+|[a-zA-Z0-9_]+\/clip\/[a-zA-Z0-9_-]+)|\S+\.(?:mp4|webm|mov|mkv|avi|m4v)(?:\?\S*)?)',
    re.IGNORECASE
)

GENERIC_WEB_URL_REGEX = re.compile(
    r'https?:\/\/[^\s<>"]+',
    re.IGNORECASE
)

async def watch_video_tool(url: str, user_prompt: str = "", bot_config: Optional[Dict[str, Any]] = None) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Watches and analyzes any video link (YouTube, Instagram, TikTok, Twitter/X, direct video) up to 12 minutes.
    Extracts acoustic events (laughter, screams, music), speech dialogue, and key visual moments.
    Returns character-ready synthesis and structured report data.
    """
    import os
    bot_cfg = bot_config or {}
    config = MediaConfig(
        max_video_duration=MAX_VIDEO_DURATION_SECONDS, # Strict 12-minute cap
        gemini_key=bot_cfg.get("gemini_key") or os.getenv("GEMINI_KEY", ""),
        groq_key=bot_cfg.get("groq_key") or os.getenv("GROQ_KEY", ""),
        openrouter_key=bot_cfg.get("openrouter_key") or os.getenv("OPENROUTER_KEY", "")
    )

    analyzer = UniversalMediaAnalyzer(config)
    try:
        report = await analyzer.analyze(url, max_duration_sec=MAX_VIDEO_DURATION_SECONDS)

        # Comprehensive timeline & full dialogue transcripts (up to 20,000 chars)
        timeline_snippet = "\n".join(report.chronological_timeline[:35]) if report.chronological_timeline else "Normal video playback."
        transcript_snippet = report.full_transcript_text[:20000] if report.full_transcript_text else "No spoken dialogue transcribed."
        
        # Only include acoustic events if genuine non-ambient events occurred
        high_conf_events = [e for e in report.audio_events if e.event_type not in ["silence"] and e.confidence >= 0.85]
        if high_conf_events:
            events_str = "\n".join([f"- [{int(e.start_sec//60):02d}:{int(e.start_sec%60):02d}] {e.description}" for e in high_conf_events[:8]])
            acoustic_section = f"--- NOTABLE AUDIO EVENTS (CONFIRMED) ---\n{events_str}\n\n"
        else:
            acoustic_section = "--- NOTABLE AUDIO EVENTS ---\nNo unusual audio spikes, screaming, or sudden sound effects (normal audio).\n\n"

        context_for_ai = (
            f"=== WATCHED VIDEO: \"{report.metadata.title}\" ({report.metadata.platform.upper()}) ===\n"
            f"URL: {url}\n"
            f"Creator/Author: {report.metadata.author}\n"
            f"Duration: {int(report.metadata.duration_sec // 60)}m {int(report.metadata.duration_sec % 60):02d}s (Limit: 12m)\n"
            f"Tags/Vibe: {', '.join(report.content_classification)}\n\n"
            f"--- CHRONOLOGICAL SCENE & AUDIO TIMELINE ---\n{timeline_snippet}\n\n"
            f"{acoustic_section}"
            f"--- FULL SPOKEN DIALOGUE & SONG LYRICS / TRANSCRIPT ---\n{transcript_snippet}\n\n"
            f"[CRITICAL VIDEO & AUDIO INSTRUCTION]: You have the FULL dialogue transcript, lyrics, and scene timeline above. "
            f"Speak specifically about what was heard, sung, spoken, and seen across the whole video in your personality reply!"
        )
        return context_for_ai, report.__dict__
    except Exception as e:
        return f"Could not watch video: {e}", None

async def browse_web_tool(url: str, user_prompt: str = "") -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Visits a webpage, reads its full text, headings, and OpenGraph metadata, and formats it for character response.
    """
    browser = UniversalWebBrowser()
    try:
        page = await browser.browse(url)
        # Retain full comprehensive article text (up to 30,000 chars)
        full_content = page.markdown_content if page.markdown_content else page.main_text
        if len(full_content) > 30000:
            full_content = full_content[:30000] + "\n\n... [Article continues]"

        context = (
            f"=== VISITED WEBPAGE: \"{page.title}\" ({page.domain}) ===\n"
            f"URL: {page.url}\n"
            f"Author/Source: {page.author}\n\n"
            f"--- FULL ARTICLE BODY & HEADINGS ---\n"
            f"{full_content}\n"
        )
        return context, page.__dict__
    except Exception as e:
        return f"Could not browse web page: {e}", None

async def search_web_tool(query: str, max_results: int = 4) -> Tuple[str, List[Dict[str, str]]]:
    """
    Searches the web and returns concise results with snippets.
    """
    browser = UniversalWebBrowser()
    results, err = await browser.search(query, max_results=max_results)
    if err or not results:
        return f"Web search failed: {err or 'No results found'}", []

    lines = [f"=== WEB SEARCH RESULTS FOR \"{query}\" ==="]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. [{r['title']}]({r['url']})\n   {r['snippet']}")
    return "\n\n".join(lines), results

def detect_and_handle_media_urls(text: str) -> Optional[Tuple[str, str]]:
    """
    Detects if a user message contains a video or web URL.
    Returns ('video', url) or ('web', url) or None.
    """
    if not text:
        return None

    # 1. Check video URL
    v_match = VIDEO_URL_REGEX.search(text)
    if v_match:
        return "video", v_match.group(0).strip()

    # 2. Check general web URL
    w_match = GENERIC_WEB_URL_REGEX.search(text)
    if w_match:
        return "web", w_match.group(0).strip()

    return None
