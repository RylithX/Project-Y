"""
Abstract Base Class for Media Sources.
"""
from abc import ABC, abstractmethod
from typing import List, Tuple, Optional, Any
from ..types import MediaMetadata, TranscriptSegment
from ..config import MAX_VIDEO_DURATION_SECONDS

class BaseMediaSource(ABC):
    """
    Plug-in interface for universal media ingestion.
    Each source provides extraction of metadata, audio slices, video frames, and subtitles.
    """
    
    @abstractmethod
    def match(self, url_or_path: str) -> bool:
        """Returns True if this source plugin can handle the given URL or path."""
        pass

    @abstractmethod
    async def extract_metadata(self, url_or_path: str) -> MediaMetadata:
        """Extracts title, duration, author, platform, tags, and description."""
        pass

    async def fetch_transcript(self, url_or_path: str, metadata: MediaMetadata) -> List[TranscriptSegment]:
        """Optionally fetches native platform subtitles/transcripts if available."""
        return []

    async def extract_audio_pcm16(self, url_or_path: str, metadata: MediaMetadata, max_duration_sec: int = MAX_VIDEO_DURATION_SECONDS) -> Tuple[Optional[bytes], int]:
        """Extracts 16kHz PCM16 single-channel WAV audio bytes."""
        return None, 16000

    async def extract_keyframe_images(self, url_or_path: str, metadata: MediaMetadata, timestamps: List[float]) -> List[Tuple[float, bytes]]:
        """Extracts JPEG frames at specific timestamps."""
        return []
