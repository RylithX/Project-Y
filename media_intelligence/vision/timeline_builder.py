"""
Unified Timeline Builder and Content Classifier.
Merges dialogue, acoustic events, visual keyframes, and scene segments into a coherent chronological timeline.
"""
from typing import List, Dict, Any, Tuple
from ..types import (
    MediaMetadata,
    TranscriptSegment,
    AudioEvent,
    VisionEvent,
    SceneSegment
)

class TimelineBuilder:

    @classmethod
    def build_chronological_timeline(
        cls,
        metadata: MediaMetadata,
        transcript: List[TranscriptSegment],
        audio_events: List[AudioEvent],
        vision_events: List[VisionEvent]
    ) -> Tuple[List[str], List[SceneSegment], List[str], float]:
        """
        Builds a chronological narrative timeline, scene segments, content tags, and overall confidence.
        """
        timeline_items = []

        # 1. Add visual scene events
        for v in vision_events:
            ts_str = f"[{int(v.timestamp_sec // 60):02d}:{int(v.timestamp_sec % 60):02d}]"
            timeline_items.append((v.timestamp_sec, f"{ts_str} (VISUAL SCENE {v.scene_idx}) {v.description}"))

        # 2. Add notable acoustic events
        for a in audio_events:
            if a.event_type == "silence":
                continue # Skip silence clutter in timeline
            ts_str = f"[{int(a.start_sec // 60):02d}:{int(a.start_sec % 60):02d}]"
            ev_label = a.event_type.upper().replace("_", " ")
            timeline_items.append((a.start_sec, f"{ts_str} (AUDIO: {ev_label}) {a.description}"))

        # 3. Add dialogue / speech segments (sample if many)
        step = max(1, len(transcript) // 15)
        for i in range(0, len(transcript), step):
            t = transcript[i]
            ts_str = f"[{int(t.start_sec // 60):02d}:{int(t.start_sec % 60):02d}]"
            spk = f"{t.speaker_id}: " if t.speaker_id else ""
            timeline_items.append((t.start_sec, f'{ts_str} (SPEECH) {spk}"{t.text}"'))

        # Sort all events chronologically
        timeline_items.sort(key=lambda x: x[0])
        chronological_timeline = [item[1] for item in timeline_items]

        # Build Scene Segments
        scenes: List[SceneSegment] = []
        if vision_events:
            for i, v in enumerate(vision_events):
                start = v.timestamp_sec
                end = vision_events[i+1].timestamp_sec if i + 1 < len(vision_events) else metadata.duration_sec
                scenes.append(SceneSegment(
                    scene_idx=v.scene_idx,
                    start_sec=start,
                    end_sec=max(start, end),
                    visual_summary=v.description,
                    keyframe_timestamp_sec=v.timestamp_sec
                ))

        # Content classification
        tags = cls._classify_content(metadata, transcript, audio_events)
        confidence = 0.90 if transcript and vision_events else (0.80 if transcript or vision_events else 0.65)

        return chronological_timeline, scenes, tags, confidence

    @classmethod
    def _classify_content(cls, metadata: MediaMetadata, transcript: List[TranscriptSegment], audio_events: List[AudioEvent]) -> List[str]:
        tags = set(metadata.tags)
        full_text = (metadata.title + " " + metadata.description + " " + " ".join(t.text for t in transcript[:20])).lower()

        if any(w in full_text for w in ["game", "gameplay", "minecraft", "fortnite", "roblox", "pokemon", "fps"]):
            tags.add("gaming")
        if any(w in full_text for w in ["how to", "tutorial", "guide", "explained", "learn", "review"]):
            tags.add("educational / tutorial")
        if any(w in full_text for w in ["music", "song", "lyrics", "cover", "remix", "beat", "official video"]):
            tags.add("music")
        if any(w in full_text for w in ["funny", "laugh", "meme", "comedy", "prank", "lol"]):
            tags.add("comedy / entertainment")
        if any(w in full_text for w in ["news", "update", "report", "announcement"]):
            tags.add("news / informative")

        # Acoustic cues
        if any(a.event_type == "laughter" for a in audio_events):
            tags.add("humorous / comedic moments")
        if any(a.event_type in ("scream", "volume_spike") for a in audio_events):
            tags.add("high energy / intense action")
        if any(a.event_type == "music_transition" for a in audio_events):
            tags.add("soundtrack-driven")

        return sorted(list(tags))[:8]
