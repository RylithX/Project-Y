"""
Modular, Provider-Agnostic Media Intelligence System
=====================================================
A plug-in based architecture for universal media loading, acoustic DSP intelligence,
transcription & diarization, dynamic keyframe scene detection, timeline synthesis,
web browsing, and multi-modal content understanding.
"""

from .config import (
    MAX_VIDEO_DURATION_SECONDS,
    AUDIO_SAMPLE_RATE,
    MAX_KEYFRAMES,
    SCENE_DIFF_THRESHOLD,
    VOLUME_SPIKE_DB_THRESHOLD,
    CACHE_EXPIRY_SECONDS,
    MediaConfig
)
from .types import (
    MediaMetadata,
    TranscriptSegment,
    AudioEvent,
    VisionEvent,
    SceneSegment,
    MediaIntelligenceReport,
    WebPageContent
)
from .core.registry import (
    SourcePluginRegistry,
    STTProviderRegistry,
    register_source,
    register_stt_provider
)
from .core.base_source import BaseMediaSource
from .sources import (
    YouTubeSource,
    SocialMediaSource,
    DirectMediaSource,
    WebPageSource
)
from .audio.dsp_engine import AudioMetrics, AudioDSPEngine
from .audio.acoustic_events import AcousticEventDetector
from .audio.stt import MultiProviderSTT
from .audio.diarization import SpeakerDiarizer
from .vision.scene_detector import DynamicSceneDetector
from .vision.visual_extractor import VisualExtractor
from .vision.timeline_builder import TimelineBuilder
from .pipeline.analyzer import UniversalMediaAnalyzer, analyze_media_url
from .pipeline.web_browser import UniversalWebBrowser, browse_url, search_and_read
from .tools.discord_tools import (
    watch_video_tool,
    browse_web_tool,
    search_web_tool,
    detect_and_handle_media_urls
)

__all__ = [
    "MAX_VIDEO_DURATION_SECONDS",
    "AUDIO_SAMPLE_RATE",
    "MAX_KEYFRAMES",
    "SCENE_DIFF_THRESHOLD",
    "VOLUME_SPIKE_DB_THRESHOLD",
    "CACHE_EXPIRY_SECONDS",
    "MediaConfig",
    "MediaMetadata",
    "TranscriptSegment",
    "AudioEvent",
    "VisionEvent",
    "SceneSegment",
    "MediaIntelligenceReport",
    "WebPageContent",
    "SourcePluginRegistry",
    "STTProviderRegistry",
    "register_source",
    "register_stt_provider",
    "BaseMediaSource",
    "YouTubeSource",
    "SocialMediaSource",
    "DirectMediaSource",
    "WebPageSource",
    "AudioMetrics",
    "AudioDSPEngine",
    "AcousticEventDetector",
    "MultiProviderSTT",
    "SpeakerDiarizer",
    "DynamicSceneDetector",
    "VisualExtractor",
    "TimelineBuilder",
    "UniversalMediaAnalyzer",
    "analyze_media_url",
    "UniversalWebBrowser",
    "browse_url",
    "search_and_read",
    "watch_video_tool",
    "browse_web_tool",
    "search_web_tool",
    "detect_and_handle_media_urls"
]
