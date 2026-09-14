"""
YouTube Source Plugin.
Extracts YouTube metadata, transcripts, audio streams, and video frames.
"""
import re
import os
import io
import time
import json
import asyncio
import tempfile
import subprocess
from typing import List, Tuple, Optional, Dict, Any
import aiohttp

from ..core.base_source import BaseMediaSource
from ..core.registry import register_source
from ..types import MediaMetadata, TranscriptSegment
from ..config import MAX_VIDEO_DURATION_SECONDS

@register_source(priority=100)
class YouTubeSource(BaseMediaSource):
    YT_REGEX = re.compile(
        r'(?:https?:\/\/)?(?:www\.|m\.)?(?:youtube\.com\/(?:watch\?v=|embed\/|v\/|shorts\/|live\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})',
        re.IGNORECASE
    )

    def match(self, url_or_path: str) -> bool:
        if not url_or_path:
            return False
        return bool(self.YT_REGEX.search(url_or_path.strip()))

    def extract_id(self, url_or_path: str) -> str:
        m = self.YT_REGEX.search(url_or_path.strip())
        return m.group(1) if m else url_or_path.strip()

    async def extract_metadata(self, url_or_path: str) -> MediaMetadata:
        vid = self.extract_id(url_or_path)
        canonical_url = f"https://www.youtube.com/watch?v={vid}"

        # 1. Try oEmbed for instantaneous lightweight metadata
        title = "YouTube Video"
        author = "YouTube Creator"
        thumb = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
        desc = ""
        duration = 0.0
        tags = []

        try:
            oembed_url = f"https://www.youtube.com/oembed?url={canonical_url}&format=json"
            async with aiohttp.ClientSession() as session:
                async with session.get(oembed_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        title = data.get("title") or title
                        author = data.get("author_name") or author
                        thumb = data.get("thumbnail_url") or thumb
        except Exception:
            pass

        # 2. Try yt-dlp for rich metadata & exact duration
        try:
            cmd = [
                "yt-dlp", "--dump-json", "--skip-download",
                "--no-warnings", "--quiet", canonical_url
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=12)
            if stdout:
                info = json.loads(stdout.decode("utf-8", errors="ignore"))
                title = info.get("title") or title
                author = info.get("uploader") or info.get("artist") or author
                duration = float(info.get("duration") or 0.0)
                desc = info.get("description") or ""
                tags = info.get("tags") or []
                if info.get("thumbnail"):
                    thumb = info.get("thumbnail")
        except Exception:
            pass

        return MediaMetadata(
            url_or_path=canonical_url,
            platform="youtube",
            media_type="video",
            title=title,
            author=author,
            duration_sec=duration,
            thumbnail_url=thumb,
            description=desc[:1000],
            tags=tags[:15],
            extracted_at=time.time(),
            extra={"video_id": vid}
        )

    async def fetch_transcript(self, url_or_path: str, metadata: MediaMetadata) -> List[TranscriptSegment]:
        vid = metadata.extra.get("video_id") or self.extract_id(url_or_path)
        segments: List[TranscriptSegment] = []

        # Tier 1: youtube_transcript_api (direct instant fetch)
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            api = YouTubeTranscriptApi()
            tlist = api.list(vid)
            # Find first usable transcript (prefer English/manual, else auto-generated)
            best_tr = None
            for tr in tlist:
                if tr.language_code.startswith("en") and not tr.is_generated:
                    best_tr = tr
                    break
            if not best_tr:
                for tr in tlist:
                    if tr.language_code.startswith("en"):
                        best_tr = tr
                        break
            if not best_tr:
                for tr in tlist:
                    best_tr = tr
                    break

            if best_tr:
                fetched = best_tr.fetch()
                snippets = getattr(fetched, "snippets", None) or fetched
                for s in snippets:
                    start = float(getattr(s, "start", 0.0))
                    dur = float(getattr(s, "duration", 0.0))
                    txt = str(getattr(s, "text", "")).strip()
                    if txt:
                        if start > MAX_VIDEO_DURATION_SECONDS:
                            break
                        segments.append(TranscriptSegment(
                            start_sec=start,
                            end_sec=start + dur,
                            text=txt
                        ))
                if segments:
                    return segments
        except Exception as e:
            print(f"[YOUTUBE TRANSCRIPT API NOTICE] {e}")

        # Tier 2: yt-dlp auto subtitle & manual subtitle VTT dump
        try:
            import glob
            tmp_dir = tempfile.mkdtemp()
            cmd = [
                "yt-dlp",
                "--write-auto-sub", "--write-sub",
                "--sub-lang", "en.*,.*",
                "--sub-format", "vtt",
                "--skip-download",
                "-o", os.path.join(tmp_dir, "%(id)s.%(ext)s"),
                f"https://www.youtube.com/watch?v={vid}"
            ]
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            await asyncio.wait_for(proc.wait(), timeout=12)

            vtt_files = glob.glob(os.path.join(tmp_dir, "*.vtt"))
            if vtt_files:
                with open(vtt_files[0], "r", encoding="utf-8", errors="ignore") as vf:
                    vtt_text = vf.read()
                
                # Parse VTT subtitle blocks
                block_pattern = re.compile(
                    r'(?:(\d{2}):)?(\d{2}):(\d{2})\.(\d{3})\s*-->\s*(?:(\d{2}):)?(\d{2}):(\d{2})\.(\d{3})[^\n]*\n(.*?)(?=\n\s*(?:(?:\d{2}:)?\d{2}:\d{2}\.\d{3}|\Z))',
                    re.DOTALL
                )
                seen_texts = set()
                for m in block_pattern.finditer(vtt_text):
                    h1 = int(m.group(1)[:-1]) if m.group(1) else 0
                    m1 = int(m.group(2))
                    s1 = int(m.group(3))
                    ms1 = int(m.group(4))
                    start_sec = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000.0

                    h2 = int(m.group(5)[:-1]) if m.group(5) else 0
                    m2 = int(m.group(6))
                    s2 = int(m.group(7))
                    ms2 = int(m.group(8))
                    end_sec = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000.0

                    if start_sec > MAX_VIDEO_DURATION_SECONDS:
                        break

                    raw_text = m.group(9)
                    cleaned = re.sub(r'<[^>]+>', '', raw_text)
                    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

                    if cleaned and cleaned not in seen_texts and len(cleaned) > 1:
                        seen_texts.add(cleaned)
                        segments.append(TranscriptSegment(
                            start_sec=start_sec,
                            end_sec=end_sec,
                            text=cleaned
                        ))
                
                import shutil
                shutil.rmtree(tmp_dir, ignore_errors=True)
                if segments:
                    return segments
        except Exception as ve:
            print(f"[YOUTUBE VTT FALLBACK NOTICE] {ve}")

        return segments

    async def extract_audio_pcm16(self, url_or_path: str, metadata: MediaMetadata, max_duration_sec: int = MAX_VIDEO_DURATION_SECONDS) -> Tuple[Optional[bytes], int]:
        vid = metadata.extra.get("video_id") or self.extract_id(url_or_path)
        canonical_url = f"https://www.youtube.com/watch?v={vid}"
        tmp_wav = tempfile.mktemp(suffix=".wav")

        try:
            # yt-dlp piped into ffmpeg for fast streaming download limited to max_duration_sec
            cap_duration = min(max_duration_sec, MAX_VIDEO_DURATION_SECONDS)
            cmd = [
                "yt-dlp",
                "-f", "bestaudio/best",
                "--no-warnings", "--quiet",
                "-o", "-",
                canonical_url
            ]
            ytdl_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-i", "pipe:0",
                "-t", str(cap_duration),
                "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                tmp_wav
            ]
            ff_proc = subprocess.Popen(ffmpeg_cmd, stdin=ytdl_proc.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            ytdl_proc.stdout.close()
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, ff_proc.wait)

            if os.path.exists(tmp_wav) and os.path.getsize(tmp_wav) > 1024:
                with open(tmp_wav, "rb") as f:
                    data = f.read()
                return data, 16000
        except Exception as e:
            print(f"[YOUTUBE AUDIO EXTRACTION NOTICE] {e}")
        finally:
            if os.path.exists(tmp_wav):
                try: os.remove(tmp_wav)
                except: pass

        return None, 16000

    async def extract_keyframe_images(self, url_or_path: str, metadata: MediaMetadata, timestamps: List[float]) -> List[Tuple[float, bytes]]:
        if not timestamps:
            return []

        vid = metadata.extra.get("video_id") or self.extract_id(url_or_path)
        canonical_url = f"https://www.youtube.com/watch?v={vid}"
        frames: List[Tuple[float, bytes]] = []

        try:
            # Get video direct streaming URL
            cmd = ["yt-dlp", "-g", "-f", "best[height<=480]/bestvideo[height<=480]/best", canonical_url]
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
            stream_url = stdout.decode().strip().splitlines()[0] if stdout else None

            if not stream_url:
                return []

            tmp_dir = tempfile.mkdtemp()
            try:
                for ts in timestamps:
                    if ts > MAX_VIDEO_DURATION_SECONDS:
                        continue
                    out_jpg = os.path.join(tmp_dir, f"frame_{int(ts*100):06d}.jpg")
                    ff_cmd = [
                        "ffmpeg", "-y",
                        "-ss", str(ts),
                        "-i", stream_url,
                        "-frames:v", "1",
                        "-q:v", "3",
                        "-vf", "scale=480:-1",
                        out_jpg
                    ]
                    p = await asyncio.create_subprocess_exec(*ff_cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                    await asyncio.wait_for(p.wait(), timeout=10)
                    if os.path.exists(out_jpg) and os.path.getsize(out_jpg) > 500:
                        with open(out_jpg, "rb") as f:
                            frames.append((ts, f.read()))
            finally:
                import shutil
                try: shutil.rmtree(tmp_dir)
                except: pass
        except Exception as e:
            print(f"[YOUTUBE FRAME EXTRACTION NOTICE] {e}")

        return frames
