"""
Universal Media Intelligence Analyzer Pipeline.
Coordinates source detection, metadata extraction, acoustic DSP & event detection,
transcription & diarization, dynamic keyframe vision, and timeline synthesis.
"""
import time
import asyncio
from typing import Optional, Dict, Any, List

from ..config import (
    MAX_VIDEO_DURATION_SECONDS,
    MediaConfig
)
from ..types import (
    MediaMetadata,
    TranscriptSegment,
    AudioEvent,
    VisionEvent,
    SceneSegment,
    MediaIntelligenceReport
)
from ..core.registry import SourcePluginRegistry
from ..cache import MediaCache
from ..audio.dsp_engine import AudioDSPEngine
from ..audio.acoustic_events import AcousticEventDetector
from ..audio.stt import MultiProviderSTT
from ..audio.diarization import SpeakerDiarizer
from ..vision.scene_detector import DynamicSceneDetector
from ..vision.visual_extractor import VisualExtractor
from ..vision.timeline_builder import TimelineBuilder

class UniversalMediaAnalyzer:

    def __init__(self, config: Optional[MediaConfig] = None):
        self.config = config or MediaConfig()
        self.cache = MediaCache(self.config.cache_dir)
        self.stt = MultiProviderSTT(
            groq_key=self.config.groq_key,
            gemini_key=self.config.gemini_key,
            openrouter_key=self.config.openrouter_key
        )
        self.vision = VisualExtractor(
            gemini_key=self.config.gemini_key,
            openrouter_key=self.config.openrouter_key
        )

    async def analyze(self, url_or_path: str, max_duration_sec: int = MAX_VIDEO_DURATION_SECONDS) -> MediaIntelligenceReport:
        start_time = time.time()
        url = url_or_path.strip()

        # Enforce maximum duration limit: 12 minutes (720 seconds)
        effective_max_duration = min(max_duration_sec, self.config.max_video_duration)

        # 1. Check cache
        if self.config.enable_cache:
            cached = self.cache.get(url)
            if cached:
                try:
                    meta_dict = cached.get("metadata", {})
                    meta = MediaMetadata(**meta_dict)
                    rep = MediaIntelligenceReport(
                        metadata=meta,
                        summary=cached.get("summary", ""),
                        full_transcript_text=cached.get("full_transcript_text", ""),
                        chronological_timeline=cached.get("chronological_timeline", []),
                        content_classification=cached.get("content_classification", []),
                        overall_confidence=cached.get("overall_confidence", 0.9),
                        execution_time_sec=round(time.time() - start_time, 2),
                        was_cached=True
                    )
                    return rep
                except Exception:
                    pass

        # 2. Find matching source plugin
        source = SourcePluginRegistry.find_source(url)
        if not source:
            raise ValueError(f"No media loader plugin found for source: {url}")

        # 3. Extract metadata
        metadata = await source.extract_metadata(url)

        # 4. Fetch native transcript or extract audio for STT & Acoustic DSP
        transcript_segments: List[TranscriptSegment] = []
        try:
            transcript_segments = await source.fetch_transcript(url, metadata)
        except Exception:
            pass

        audio_bytes, sr = None, 16000
        metric_chunks: List[Dict[str, Any]] = []
        audio_events: List[AudioEvent] = []

        if self.config.enable_audio_dsp or (self.config.enable_stt and not transcript_segments):
            try:
                audio_bytes, sr = await source.extract_audio_pcm16(url, metadata, max_duration_sec=effective_max_duration)
            except Exception:
                pass

        if audio_bytes:
            # Run local DSP metrics
            metric_chunks = AudioDSPEngine.analyze_audio_track(audio_bytes, chunk_duration_sec=3.0)
            # Detect acoustic events (laughter, screams, applause, music changes, volume spikes)
            audio_events = AcousticEventDetector.detect_events(metric_chunks)

            # If no native transcript, run fast STT
            if self.config.enable_stt and not transcript_segments:
                stt_text, _ = await self.stt.transcribe(audio_bytes)
                if stt_text:
                    transcript_segments.append(TranscriptSegment(
                        start_sec=0.0,
                        end_sec=min(metadata.duration_sec or 60.0, effective_max_duration),
                        text=stt_text,
                        is_synthesized=True
                    ))

        # 5. Diarization
        if self.config.enable_diarization and transcript_segments and metric_chunks:
            transcript_segments = SpeakerDiarizer.diarize_transcript(transcript_segments, metric_chunks)

        # 6. Dynamic Keyframe Selection & Vision Analysis
        vision_events: List[VisionEvent] = []
        if self.config.enable_vision and metadata.media_type == "video":
            salient_timestamps = DynamicSceneDetector.select_salient_timestamps(
                duration_sec=metadata.duration_sec,
                audio_events=audio_events,
                metric_chunks=metric_chunks,
                max_keyframes=self.config.max_keyframes
            )
            if salient_timestamps:
                keyframe_imgs = await source.extract_keyframe_images(url, metadata, salient_timestamps)
                if keyframe_imgs:
                    vision_events = await self.vision.analyze_keyframes(keyframe_imgs)

        # 7. Timeline Synthesis
        timeline, scenes, tags, confidence = TimelineBuilder.build_chronological_timeline(
            metadata, transcript_segments, audio_events, vision_events
        )

        full_transcript_str = "\n".join([f"[{int(t.start_sec//60):02d}:{int(t.start_sec%60):02d}] {t.speaker_id + ': ' if t.speaker_id else ''}{t.text}" for t in transcript_segments])

        # Summary generation
        summary = f"**{metadata.title}** ({metadata.platform.capitalize()} • {int(metadata.duration_sec//60)}m {int(metadata.duration_sec%60):02d}s)\n"
        if metadata.author:
            summary += f"By: {metadata.author}\n"
        if tags:
            summary += f"Classification: {', '.join(tags)}\n"

        rep = MediaIntelligenceReport(
            metadata=metadata,
            summary=summary,
            full_transcript_text=full_transcript_str,
            transcript_segments=transcript_segments,
            audio_events=audio_events,
            vision_events=vision_events,
            scenes=scenes,
            chronological_timeline=timeline,
            content_classification=tags,
            overall_confidence=confidence,
            execution_time_sec=round(time.time() - start_time, 2),
            was_cached=False
        )

        # Cache report
        if self.config.enable_cache:
            try:
                self.cache.set(url, {
                    "metadata": metadata.__dict__,
                    "summary": summary,
                    "full_transcript_text": full_transcript_str,
                    "chronological_timeline": timeline,
                    "content_classification": tags,
                    "overall_confidence": confidence
                })
            except Exception:
                pass

        return rep

async def analyze_media_url(url: str, config: Optional[MediaConfig] = None) -> MediaIntelligenceReport:
    analyzer = UniversalMediaAnalyzer(config)
    return await analyzer.analyze(url)
