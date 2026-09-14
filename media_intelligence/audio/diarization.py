"""
Speaker Diarization and Turn Tracking.
Clusters speech turns and identifies speaker transitions using acoustic pitch/timbre & pause points.
"""
from typing import List, Dict, Any, Optional
from ..types import TranscriptSegment

class SpeakerDiarizer:

    @classmethod
    def diarize_transcript(cls, segments: List[TranscriptSegment], metric_chunks: List[Dict[str, Any]]) -> List[TranscriptSegment]:
        if not segments:
            return []

        # Correlate transcript start times with acoustic pitch & spectral centroid
        metric_lookup = {round(m["timestamp_sec"]): m for m in metric_chunks}
        
        current_speaker_idx = 1
        last_pitch = 0.0
        last_centroid = 0.0
        last_end = 0.0

        for seg in segments:
            m = metric_lookup.get(round(seg.start_sec))
            pitch = m["pitch"] if m else 0.0
            centroid = m["centroid"] if m else 0.0

            # Speaker transition heuristic:
            # 1. Noticeable pause (> 1.2s) + significant pitch/centroid shift
            # 2. Dramatic pitch octave change (> 45Hz)
            pause = seg.start_sec - last_end
            if last_pitch > 0 and pitch > 0:
                pitch_diff = abs(pitch - last_pitch)
                if (pause > 1.2 and pitch_diff > 35.0) or pitch_diff > 60.0:
                    current_speaker_idx = 2 if current_speaker_idx == 1 else 1

            seg.speaker_id = f"Speaker {current_speaker_idx}"
            if pitch > 0: last_pitch = pitch
            if centroid > 0: last_centroid = centroid
            last_end = seg.end_sec

        return segments
