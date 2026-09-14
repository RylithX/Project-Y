"""
Dynamic Scene Detector and Keyframe Selector.
Triggered by volume changes, acoustic spikes (laughter, screams, music drops), and visual transitions
to capture the most informative video moments with minimal API cost.
"""
from typing import List, Dict, Any, Set
from ..types import AudioEvent
from ..config import MAX_KEYFRAMES, MIN_SCENE_INTERVAL_SECONDS, MAX_VIDEO_DURATION_SECONDS

class DynamicSceneDetector:

    @classmethod
    def select_salient_timestamps(
        cls,
        duration_sec: float,
        audio_events: List[AudioEvent],
        metric_chunks: List[Dict[str, Any]],
        max_keyframes: int = MAX_KEYFRAMES
    ) -> List[float]:
        """
        Selects optimal keyframe timestamps based on:
        1. Major acoustic surges & events (screams, laughter, applause, music changes, volume spikes)
        2. Content distribution across the active video duration (capped at 12 minutes).
        """
        eff_duration = min(duration_sec if duration_sec > 0 else 60.0, MAX_VIDEO_DURATION_SECONDS)
        selected_times: Set[float] = set()

        # 1. Opening establishing keyframe (at 2-4 seconds)
        selected_times.add(min(3.0, eff_duration * 0.1))

        # 2. Add timestamps from high-intensity acoustic events
        sorted_events = sorted(audio_events, key=lambda e: e.intensity, reverse=True)
        for ev in sorted_events:
            if len(selected_times) >= max_keyframes:
                break
            if ev.start_sec > MAX_VIDEO_DURATION_SECONDS:
                continue
            # Avoid picking times too close to existing keyframes
            t = round(ev.start_sec + 0.5, 1)
            if not any(abs(t - existing) < MIN_SCENE_INTERVAL_SECONDS for existing in selected_times):
                selected_times.add(t)

        # 3. If under max_keyframes, distribute uniformly across the duration
        if len(selected_times) < max_keyframes and eff_duration > 10.0:
            step = eff_duration / (max_keyframes - len(selected_times) + 1)
            for i in range(1, max_keyframes):
                if len(selected_times) >= max_keyframes:
                    break
                candidate = round(step * i, 1)
                if not any(abs(candidate - existing) < MIN_SCENE_INTERVAL_SECONDS for existing in selected_times):
                    selected_times.add(candidate)

        sorted_final = sorted(list(selected_times))
        return sorted_final[:max_keyframes]
