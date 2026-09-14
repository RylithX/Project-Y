"""
Data structures and schema definitions for the Media Intelligence System.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime

@dataclass
class MediaMetadata:
    url_or_path: str
    platform: str                    # 'youtube', 'instagram', 'tiktok', 'twitter', 'reddit', 'twitch', 'direct', 'web', etc.
    media_type: str                  # 'video', 'audio', 'article', 'web_page', 'image'
    title: str = "Media Content"
    author: str = "Unknown"
    duration_sec: float = 0.0
    is_live: bool = False
    thumbnail_url: Optional[str] = None
    description: str = ""
    tags: List[str] = field(default_factory=list)
    view_count: Optional[int] = None
    upload_date: Optional[str] = None
    extracted_at: float = 0.0
    extra: Dict[str, Any] = field(default_factory=dict)

@dataclass
class TranscriptSegment:
    start_sec: float
    end_sec: float
    text: str
    speaker_id: Optional[str] = None
    confidence: float = 1.0
    is_synthesized: bool = False

@dataclass
class AudioEvent:
    event_type: str                  # 'laughter', 'scream', 'applause', 'cheering', 'silence', 'music_transition', 'volume_spike', 'speech'
    start_sec: float
    end_sec: float
    confidence: float = 0.85
    intensity: float = 0.5           # 0.0 - 1.0 scale
    description: str = ""
    metrics: Dict[str, float] = field(default_factory=dict) # rms_db, zcr, centroid, pitch, onset

@dataclass
class VisionEvent:
    timestamp_sec: float
    scene_idx: int
    description: str
    objects: List[str] = field(default_factory=list)
    people_count: int = 0
    actions: List[str] = field(default_factory=list)
    ocr_text: List[str] = field(default_factory=list)
    change_score: float = 0.0
    confidence: float = 0.85
    keyframe_b64: Optional[str] = None

@dataclass
class SceneSegment:
    scene_idx: int
    start_sec: float
    end_sec: float
    visual_summary: str = ""
    dialogue_summary: str = ""
    dominant_audio_events: List[str] = field(default_factory=list)
    keyframe_timestamp_sec: float = 0.0

@dataclass
class WebPageContent:
    url: str
    title: str
    domain: str
    author: Optional[str] = None
    published_date: Optional[str] = None
    description: str = ""
    markdown_content: str = ""
    main_text: str = ""
    headings: List[str] = field(default_factory=list)
    links: List[Dict[str, str]] = field(default_factory=list)
    images: List[Dict[str, str]] = field(default_factory=list)
    opengraph: Dict[str, str] = field(default_factory=dict)
    word_count: int = 0
    fetched_at: float = 0.0

@dataclass
class MediaIntelligenceReport:
    metadata: MediaMetadata
    summary: str = ""
    full_transcript_text: str = ""
    transcript_segments: List[TranscriptSegment] = field(default_factory=list)
    audio_events: List[AudioEvent] = field(default_factory=list)
    vision_events: List[VisionEvent] = field(default_factory=list)
    scenes: List[SceneSegment] = field(default_factory=list)
    chronological_timeline: List[str] = field(default_factory=list)
    content_classification: List[str] = field(default_factory=list) # e.g. ['gaming', 'tutorial', 'high_energy']
    overall_confidence: float = 0.9
    raw_acoustic_summary: Dict[str, Any] = field(default_factory=dict)
    execution_time_sec: float = 0.0
    was_cached: bool = False
