"""
Direct Media Source Plugin.
Handles direct video and audio URLs (.mp4, .webm, .mov, .mkv, .mp3, .wav, etc.) and local files.
"""
import os
import re
import time
import asyncio
import tempfile
import subprocess
from pathlib import Path
from typing import List, Tuple, Optional
import aiohttp

from ..core.base_source import BaseMediaSource
from ..core.registry import register_source
from ..types import MediaMetadata, TranscriptSegment
from ..config import MAX_VIDEO_DURATION_SECONDS

@register_source(priority=80)
class DirectMediaSource(BaseMediaSource):
    MEDIA_EXTENSIONS = {
        '.mp4', '.webm', '.mov', '.avi', '.mkv', '.m4v', '.3gp', '.flv',
        '.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac', '.opus', '.wma'
    }

    def match(self, url_or_path: str) -> bool:
        if not url_or_path:
            return False
        clean = url_or_path.split('?')[0].split('#')[0].lower().strip()
        ext = os.path.splitext(clean)[1]
        return ext in self.MEDIA_EXTENSIONS or os.path.isfile(url_or_path)

    async def _get_duration(self, file_path: str) -> float:
        try:
            cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path]
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            if stdout:
                return float(stdout.decode().strip())
        except Exception:
            pass
        return 0.0

    async def extract_metadata(self, url_or_path: str) -> MediaMetadata:
        is_local = os.path.isfile(url_or_path)
        name = Path(url_or_path).name.split('?')[0]
        ext = Path(name).suffix.lower()
        media_type = "audio" if ext in ('.mp3', '.wav', '.ogg', '.m4a', '.flac', '.opus') else "video"

        duration = 0.0
        if is_local:
            duration = await self._get_duration(url_or_path)

        return MediaMetadata(
            url_or_path=url_or_path,
            platform="direct_media",
            media_type=media_type,
            title=name,
            author="Direct Source",
            duration_sec=duration,
            extracted_at=time.time(),
            extra={"is_local": is_local}
        )

    async def _download_to_temp_if_needed(self, url_or_path: str) -> Tuple[str, bool]:
        if os.path.isfile(url_or_path):
            return url_or_path, False
        ext = Path(url_or_path.split('?')[0]).suffix or ".mp4"
        tmp_fd, tmp_file = tempfile.mkstemp(suffix=ext)
        os.close(tmp_fd)

        async with aiohttp.ClientSession() as session:
            async with session.get(url_or_path, timeout=aiohttp.ClientTimeout(total=90)) as resp:
                if resp.status != 200:
                    try: os.remove(tmp_file)
                    except: pass
                    return "", False
                with open(tmp_file, "wb") as f:
                    async for chunk in resp.content.iter_chunked(65536):
                        f.write(chunk)
        return tmp_file, True

    async def extract_audio_pcm16(self, url_or_path: str, metadata: MediaMetadata, max_duration_sec: int = MAX_VIDEO_DURATION_SECONDS) -> Tuple[Optional[bytes], int]:
        file_path, is_temp = await self._download_to_temp_if_needed(url_or_path)
        if not file_path:
            return None, 16000

        tmp_wav = tempfile.mktemp(suffix=".wav")
        try:
            cap_duration = min(max_duration_sec, MAX_VIDEO_DURATION_SECONDS)
            cmd = [
                "ffmpeg", "-y",
                "-i", file_path,
                "-t", str(cap_duration),
                "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                tmp_wav
            ]
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            await asyncio.wait_for(proc.wait(), timeout=30)

            if os.path.exists(tmp_wav) and os.path.getsize(tmp_wav) > 1024:
                with open(tmp_wav, "rb") as f:
                    data = f.read()
                return data, 16000
        except Exception:
            pass
        finally:
            if is_temp and os.path.exists(file_path):
                try: os.remove(file_path)
                except: pass
            if os.path.exists(tmp_wav):
                try: os.remove(tmp_wav)
                except: pass

        return None, 16000

    async def extract_keyframe_images(self, url_or_path: str, metadata: MediaMetadata, timestamps: List[float]) -> List[Tuple[float, bytes]]:
        if not timestamps or metadata.media_type == "audio":
            return []
        file_path, is_temp = await self._download_to_temp_if_needed(url_or_path)
        if not file_path:
            return []

        frames: List[Tuple[float, bytes]] = []
        tmp_dir = tempfile.mkdtemp()
        try:
            for ts in timestamps:
                if ts > MAX_VIDEO_DURATION_SECONDS:
                    continue
                out_jpg = os.path.join(tmp_dir, f"frame_{int(ts*100):06d}.jpg")
                ff_cmd = [
                    "ffmpeg", "-y", "-ss", str(ts),
                    "-i", file_path,
                    "-frames:v", "1", "-q:v", "3",
                    "-vf", "scale=480:-1", out_jpg
                ]
                p = await asyncio.create_subprocess_exec(*ff_cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                await asyncio.wait_for(p.wait(), timeout=10)
                if os.path.exists(out_jpg) and os.path.getsize(out_jpg) > 500:
                    with open(out_jpg, "rb") as f:
                        frames.append((ts, f.read()))
        finally:
            if is_temp and os.path.exists(file_path):
                try: os.remove(file_path)
                except: pass
            import shutil
            try: shutil.rmtree(tmp_dir)
            except: pass

        return frames
