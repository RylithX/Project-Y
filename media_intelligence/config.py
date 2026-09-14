"""
Configuration settings for the Media Intelligence System.
"""
import os
from dataclasses import dataclass

# Maximum video duration to process: 12 minutes (720 seconds) as per requirement
MAX_VIDEO_DURATION_SECONDS = int(os.getenv("MEDIA_MAX_VIDEO_DURATION", 720)) # 12 minutes
MAX_VIDEO_FILE_SIZE_MB = int(os.getenv("MEDIA_MAX_VIDEO_SIZE_MB", 150))
MAX_AUDIO_FILE_SIZE_MB = int(os.getenv("MEDIA_MAX_AUDIO_SIZE_MB", 50))

# Audio DSP Parameters
AUDIO_SAMPLE_RATE = 16000
AUDIO_FRAME_SIZE = 512
AUDIO_HOP_SIZE = 256
VOLUME_SPIKE_DB_THRESHOLD = 9.0  # dB above local moving average
SILENCE_DB_THRESHOLD = -45.0     # dB RMS below which audio is classified as silence

# Scene & Vision Sampling Parameters
MAX_KEYFRAMES = 8                # Maximum keyframes sent to vision models
MIN_SCENE_INTERVAL_SECONDS = 4.0 # Minimum seconds between keyframes
SCENE_DIFF_THRESHOLD = 0.04      # Mean normalized pixel/histogram difference for visual cut

# Cache & Storage
CACHE_EXPIRY_SECONDS = 86400     # 24 hours
CACHE_DIR = os.getenv("MEDIA_CACHE_DIR", os.path.join(os.path.dirname(__file__), "..", "data", "media_cache"))

@dataclass
class MediaConfig:
    max_video_duration: int = MAX_VIDEO_DURATION_SECONDS
    max_video_size_mb: int = MAX_VIDEO_FILE_SIZE_MB
    max_keyframes: int = MAX_KEYFRAMES
    scene_diff_threshold: float = SCENE_DIFF_THRESHOLD
    volume_spike_threshold_db: float = VOLUME_SPIKE_DB_THRESHOLD
    enable_vision: bool = True
    enable_audio_dsp: bool = True
    enable_stt: bool = True
    enable_diarization: bool = True
    enable_cache: bool = True
    gemini_key: str = ""
    groq_key: str = ""
    openrouter_key: str = ""
    cache_dir: str = CACHE_DIR
