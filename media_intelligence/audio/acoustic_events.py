"""
Acoustic Event Intelligence & Classification.
Detects laughter, screams, applause, cheering, silence, music transitions, rhythm, and emotion.
"""
from typing import List, Dict, Any, Optional
from ..types import AudioEvent

class AcousticEventDetector:
    """Analyzes continuous DSP metric frames to identify notable acoustic and emotional events."""

    @classmethod
    def detect_events(cls, metric_chunks: List[Dict[str, Any]]) -> List[AudioEvent]:
        if not metric_chunks:
            return []

        events: List[AudioEvent] = []
        all_rms = [c["rms_db"] for c in metric_chunks if c["rms_db"] > -80.0]
        avg_rms = sum(all_rms) / len(all_rms) if all_rms else -40.0

        last_music_centroid = 0.0

        for i, c in enumerate(metric_chunks):
            ts = c["timestamp_sec"]
            dur = c["duration_sec"]
            rms = c["rms_db"]
            zcr = c["zcr"]
            centroid = c["centroid"]
            pitch = c["pitch"]
            onset = c["onset"]

            # 1. SILENCE (sustained low amplitude)
            if rms < -50.0 and zcr < 0.03:
                events.append(AudioEvent(
                    event_type="silence",
                    start_sec=ts,
                    end_sec=ts + dur,
                    confidence=0.95,
                    intensity=0.1,
                    description="Quiet pause or ambient silence",
                    metrics=c
                ))
                continue

            # 2. SCREAM / EXTREME VOCAL SPIKE (High amplitude scream well above speech level)
            if rms > (avg_rms + 22.0) and rms > -6.0 and (centroid > 3200.0 and pitch > 420.0):
                events.append(AudioEvent(
                    event_type="scream",
                    start_sec=ts,
                    end_sec=ts + dur,
                    confidence=0.90,
                    intensity=min(1.0, (rms + 20.0) / 20.0),
                    description="Loud scream or intense shout",
                    metrics=c
                ))
                continue

            # 3. APPLAUSE / CROWD CHEER (High ZCR and sustained energy)
            if zcr > 0.40 and 2500.0 < centroid < 6500.0 and rms > -24.0 and onset > 40.0:
                events.append(AudioEvent(
                    event_type="applause",
                    start_sec=ts,
                    end_sec=ts + dur,
                    confidence=0.88,
                    intensity=0.8,
                    description="Applause, clapping, or cheering crowd",
                    metrics=c
                ))
                continue

            # 4. MUSIC TRANSITION / HEAVY BEAT DROP
            if centroid > 1800.0 and onset > 50.0 and rms > -18.0:
                if last_music_centroid > 0:
                    shift = abs(centroid - last_music_centroid) / last_music_centroid
                    if shift > 1.2:
                        events.append(AudioEvent(
                            event_type="music_transition",
                            start_sec=ts,
                            end_sec=ts + dur,
                            confidence=0.85,
                            intensity=0.8,
                            description="Prominent music beat drop or soundtrack shift",
                            metrics=c
                        ))
                last_music_centroid = centroid

            # 5. SUDDEN EXPLOSION / LOUD TRANSIENT IMPACT
            if rms > (avg_rms + 24.0) and onset > 90.0 and rms > -6.0:
                events.append(AudioEvent(
                    event_type="volume_spike",
                    start_sec=ts,
                    end_sec=ts + dur,
                    confidence=0.90,
                    intensity=0.9,
                    description="Sudden loud audio impact or explosive sound effect",
                    metrics=c
                ))

        return events

    @classmethod
    def get_cadence_emotion_summary(cls, chunk: Dict[str, Any]) -> str:
        pitch = chunk.get("pitch", 0.0)
        rms = chunk.get("rms_db", -40.0)
        zcr = chunk.get("zcr", 0.1)

        p_tag = "high" if pitch > 220.0 else ("low" if 0 < pitch < 120.0 else "neutral")
        v_tag = "whisper" if rms < -32.0 else ("raised/loud" if rms > -14.0 else "normal")
        c_tag = "fast" if zcr > 0.2 else ("slow" if zcr < 0.08 else "steady")

        return f"Pitch: {p_tag}, Volume: {v_tag}, Rhythm: {c_tag}"
