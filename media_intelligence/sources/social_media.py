"""
Social Media Source Plugin (Instagram, TikTok, Twitter/X, Reddit, Twitch).
"""
import re
import os
import json
import time
import asyncio
import tempfile
import subprocess
from typing import List, Tuple, Optional
import aiohttp

from ..core.base_source import BaseMediaSource
from ..core.registry import register_source
from ..types import MediaMetadata, TranscriptSegment
from ..config import MAX_VIDEO_DURATION_SECONDS

@register_source(priority=90)
class SocialMediaSource(BaseMediaSource):
    SOCIAL_REGEX = re.compile(
        r'(?:instagram\.com\/(?:p|reel|tv)\/[a-zA-Z0-9_-]+|'
        r'tiktok\.com\/@?[a-zA-Z0-9_.-]+\/video\/\d+|vm\.tiktok\.com\/[a-zA-Z0-9_-]+|'
        r'(?:twitter\.com|x\.com)\/[a-zA-Z0-9_]+\/status\/\d+|'
        r'reddit\.com\/r\/[a-zA-Z0-9_]+\/comments\/[a-zA-Z0-9_]+|v\.redd\.it\/[a-zA-Z0-9]+|'
        r'twitch\.tv\/(?:videos\/\d+|[a-zA-Z0-9_]+\/clip\/[a-zA-Z0-9_-]+)|clips\.twitch\.tv\/[a-zA-Z0-9_-]+)',
        re.IGNORECASE
    )

    def match(self, url_or_path: str) -> bool:
        if not url_or_path:
            return False
        return bool(self.SOCIAL_REGEX.search(url_or_path.strip()))

    def _detect_platform(self, url: str) -> str:
        u = url.lower()
        if "instagram.com" in u: return "instagram"
        if "tiktok.com" in u: return "tiktok"
        if "twitter.com" in u or "x.com" in u: return "twitter"
        if "reddit.com" in u or "v.redd.it" in u: return "reddit"
        if "twitch.tv" in u: return "twitch"
        return "social_media"

    def _get_cookie_args(self) -> List[str]:
        for cpath in ["cookies.txt", "instagram_cookies.txt", "/storage/emulated/0/discord-bot/cookies.txt"]:
            if os.path.exists(cpath):
                return ["--cookies", cpath]
        return []

    async def extract_metadata(self, url_or_path: str) -> MediaMetadata:
        url = url_or_path.strip()
        platform = self._detect_platform(url)
        title = f"{platform.capitalize()} Media"
        author = f"{platform.capitalize()} Creator"
        desc = ""
        duration = 0.0
        thumb = None

        # 1. Specialized Twitter/X API (Instant metadata & tweet text)
        if platform == "twitter":
            try:
                # e.g. twitter.com/user/status/1234567890
                tw_match = re.search(r'(?:twitter\.com|x\.com)\/([^\/]+)\/status\/(\d+)', url, re.IGNORECASE)
                if tw_match:
                    user_handle = tw_match.group(1)
                    status_id = tw_match.group(2)
                    api_url = f"https://api.vxtwitter.com/{user_handle}/status/{status_id}"
                    async with aiohttp.ClientSession() as session:
                        async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                            if resp.status == 200:
                                tw_data = await resp.json()
                                author = tw_data.get("user_name") or tw_data.get("user_screen_name") or user_handle
                                tweet_text = tw_data.get("text", "")
                                title = f"Post by @{user_handle}"
                                desc = tweet_text
                                if tw_data.get("media_extended") and len(tw_data["media_extended"]) > 0:
                                    thumb = tw_data["media_extended"][0].get("thumbnail_url") or tw_data["media_extended"][0].get("url")
                                return MediaMetadata(
                                    url_or_path=url,
                                    platform="twitter",
                                    media_type="post",
                                    title=title,
                                    author=author,
                                    duration_sec=0.0,
                                    thumbnail_url=thumb,
                                    description=desc,
                                    extracted_at=time.time(),
                                    extra={"tweet_id": status_id, "user": user_handle}
                                )
            except Exception as e:
                print(f"[TWITTER API NOTICE] {e}")

        # 2. Specialized Instagram extractor
        if platform == "instagram":
            insta_match = re.search(r'instagram\.com\/(?:([a-zA-Z0-9_.-]+)\/)?(?:reel|p|tv)\/([a-zA-Z0-9_-]+)', url, re.IGNORECASE)
            username = insta_match.group(1) if (insta_match and insta_match.group(1) not in ["p", "reel", "tv", None]) else "Instagram Creator"
            shortcode = insta_match.group(2) if insta_match else "post"
            title = f"Instagram Reel / Post ({shortcode})"
            author = username if username != "Instagram Creator" else "@" + username
            desc = f"Instagram Reel post ({url}) by {author}"

        # 3. Try yt-dlp for rich metadata & audio streams
        try:
            cmd = ["yt-dlp", "--dump-json", "--skip-download", "--no-warnings", "--quiet"] + self._get_cookie_args() + [url]
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            if stdout:
                info = json.loads(stdout.decode("utf-8", errors="ignore"))
                title = info.get("title") or title
                author = info.get("uploader") or info.get("creator") or author
                duration = float(info.get("duration") or 0.0)
                desc = info.get("description") or desc
                thumb = info.get("thumbnail") or thumb
        except Exception:
            pass

        return MediaMetadata(
            url_or_path=url,
            platform=platform,
            media_type="video",
            title=title,
            author=author,
            duration_sec=duration,
            thumbnail_url=thumb,
            description=desc[:2000],
            extracted_at=time.time()
        )

    async def _resolve_local_video(self, url_or_path: str, tmp_dir: str) -> Optional[str]:
        """Resolves a URL or path to a local playable video file or stream URL."""
        if os.path.isfile(url_or_path):
            return url_or_path
        
        url = url_or_path.strip()
        # 1. Try yt-dlp to get direct stream URL
        try:
            cmd = ["yt-dlp", "-g", "-f", "best[height<=480]/bestvideo[height<=480]/best"] + self._get_cookie_args() + [url]
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            if stdout:
                s_url = stdout.decode().strip().splitlines()[0]
                if s_url and s_url.startswith("http"):
                    return s_url
        except Exception:
            pass

        # 2. Try direct download via yt-dlp
        temp_vid = os.path.join(tmp_dir, "video_source.mp4")
        try:
            dl_cmd = ["yt-dlp", "-f", "best[height<=480]/best", "-o", temp_vid] + self._get_cookie_args() + [url]
            dl_proc = await asyncio.create_subprocess_exec(*dl_cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            await asyncio.wait_for(dl_proc.wait(), timeout=25)
            if os.path.exists(temp_vid) and os.path.getsize(temp_vid) > 1024:
                return temp_vid
        except Exception:
            pass

        # 3. Direct HTTP download via aiohttp if it's a CDN or direct video URL
        if url.startswith("http"):
            try:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                async with aiohttp.ClientSession(headers=headers) as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                        if resp.status == 200:
                            with open(temp_vid, "wb") as f:
                                async for chunk in resp.content.iter_chunked(65536):
                                    f.write(chunk)
                            if os.path.exists(temp_vid) and os.path.getsize(temp_vid) > 1024:
                                return temp_vid
            except Exception:
                pass

        return None

    async def extract_audio_pcm16(self, url_or_path: str, metadata: MediaMetadata, max_duration_sec: int = MAX_VIDEO_DURATION_SECONDS) -> Tuple[Optional[bytes], int]:
        url = url_or_path.strip()
        tmp_dir = tempfile.mkdtemp()
        tmp_wav = os.path.join(tmp_dir, "audio.wav")
        try:
            cap_duration = min(max_duration_sec, MAX_VIDEO_DURATION_SECONDS)
            video_target = await self._resolve_local_video(url, tmp_dir)
            
            if video_target:
                ffmpeg_cmd = [
                    "ffmpeg", "-y",
                    "-i", video_target,
                    "-t", str(cap_duration),
                    "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                    tmp_wav
                ]
                proc = await asyncio.create_subprocess_exec(*ffmpeg_cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                await asyncio.wait_for(proc.wait(), timeout=20)
                if os.path.exists(tmp_wav) and os.path.getsize(tmp_wav) > 1024:
                    with open(tmp_wav, "rb") as f:
                        return f.read(), 16000

            # Fallback: Pipe yt-dlp to ffmpeg
            try:
                cmd = ["yt-dlp", "-f", "bestaudio/best", "--no-warnings", "--quiet", "-o", "-", url]
                ytdl_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                ffmpeg_cmd = ["ffmpeg", "-y", "-i", "pipe:0", "-t", str(cap_duration), "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", tmp_wav]
                ff_proc = subprocess.Popen(ffmpeg_cmd, stdin=ytdl_proc.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                ytdl_proc.stdout.close()
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, ff_proc.wait)
                if os.path.exists(tmp_wav) and os.path.getsize(tmp_wav) > 1024:
                    with open(tmp_wav, "rb") as f:
                        return f.read(), 16000
            except Exception:
                pass
        except Exception:
            pass
        finally:
            import shutil
            try: shutil.rmtree(tmp_dir)
            except: pass

        return None, 16000

    async def extract_keyframe_images(self, url_or_path: str, metadata: MediaMetadata, timestamps: List[float]) -> List[Tuple[float, bytes]]:
        if not timestamps:
            return []
        url = url_or_path.strip()
        frames: List[Tuple[float, bytes]] = []
        tmp_dir = tempfile.mkdtemp()

        try:
            target_source = await self._resolve_local_video(url, tmp_dir)
            if not target_source:
                return []

            for ts in timestamps:
                if ts > MAX_VIDEO_DURATION_SECONDS:
                    continue
                out_jpg = os.path.join(tmp_dir, f"frame_{int(ts*100):06d}.jpg")
                ff_cmd = [
                    "ffmpeg", "-y", "-ss", str(ts),
                    "-i", target_source,
                    "-frames:v", "1", "-q:v", "2",
                    "-vf", "scale=640:-1", out_jpg
                ]
                p = await asyncio.create_subprocess_exec(*ff_cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                await asyncio.wait_for(p.wait(), timeout=10)
                if os.path.exists(out_jpg) and os.path.getsize(out_jpg) > 500:
                    with open(out_jpg, "rb") as f:
                        frames.append((ts, f.read()))
        except Exception:
            pass
        finally:
            import shutil
            try: shutil.rmtree(tmp_dir)
            except: pass

        return frames
