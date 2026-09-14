"""
voice_dsp.py - Real-Time Acoustic & Tone Intelligence for Discord Voice Calls
-----------------------------------------------------------------------------
Uses NumPy hardware-accelerated DSP (FFT, autocorrelation, spectral centroid,
zero-crossing rate, energy onset envelope, and harmonicity analysis) to give
the bot acoustic perception during voice calls:

1. Differentiate vocal tone (whisper, excitement, laughing, shouting, calm, questioning).
2. Detect musical instruments (acoustic guitar chords, piano/synth, solo melodies).
3. Distinguish singing and background music from spoken dialogue.
4. Filter out transient noise (keyboard clicks, mic taps, breath pops) before STT.
5. Provide contextual perception prompts to the AI so it reacts naturally in character.
"""

import math
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple

try:
    import numpy as np
    HAVE_NUMPY = True
except ImportError:
    np = None
    HAVE_NUMPY = False


@dataclass
class CallAcousticProfile:
    duration_sec: float = 0.0
    rms_db: float = -100.0
    peak_rms_db: float = -100.0
    zcr: float = 0.0
    centroid_hz: float = 0.0
    mean_pitch_hz: float = 0.0
    pitch_range_hz: float = 0.0
    pitch_contour: str = "none"         # "rising", "falling", "monotone", "expressive", "steady", "none"
    pitch_stability: float = 0.0        # 0.0 to 1.0 (high for instruments/sustained notes)
    harmonicity: float = 0.0            # 0.0 to 1.0 (autocorrelation harmonic peak strength)
    onsets: int = 0
    tempo_bpm: Optional[float] = None
    is_noise_only: bool = False         # Click, pop, breath, or ambient silence
    is_whisper: bool = False            # Soft breathy speech
    is_shout: bool = False              # High-energy vocal spike
    is_laughter: bool = False           # Laughing / giggling energy bursts
    is_sigh: bool = False               # Audible heavy sigh / deep breath
    is_sad_or_crying: bool = False      # Subdued / sad / vulnerable vocal tone
    is_questioning: bool = False        # Inquisitive / curious rising pitch
    is_excited: bool = False            # High-energy animated vocal expression
    is_musical: bool = False            # Instrument, singing, or music track
    musical_type: Optional[str] = None  # "guitar", "piano_or_synth", "singing", "music_track"
    musical_desc: str = ""
    background_noise: str = "quiet"     # "quiet", "music", "keyboard_clicks", "voices_chatter", "ambient_room"
    noise_desc: str = ""                # Environmental background description
    vocal_action: Optional[str] = None  # Specific vocal action description
    tone: str = "Natural conversational tone"

    def get_prompt_context(self, caller_name: str = "User") -> str:
        """Formats comprehensive acoustic and environmental perception cues to augment the AI prompt."""
        details = [f"Vocal Tone & Emotion: {self.tone}"]
        if self.vocal_action:
            details.append(f"Vocal Action: {caller_name} {self.vocal_action}")
        if self.noise_desc:
            details.append(f"Caller's Background Ambiance: {self.noise_desc}")
            
        directive = "You are currently in an active live Discord voice call with them and can hear both their voice and room. "
        if self.is_laughter:
            directive += f"{caller_name} is laughing / giggling. React warmly and playfully to their laughter!"
        elif self.is_whisper:
            directive += f"{caller_name} is whispering softly. Whisper back or playfully ask what the secret is!"
        elif self.is_sigh:
            directive += f"{caller_name} just let out a heavy sigh. Ask what's on their mind or comfort/tease them!"
        elif self.is_shout:
            directive += f"{caller_name} spoke with loud intensity / excitement. Match their energy or react with surprise!"
        elif self.is_sad_or_crying:
            directive += f"{caller_name} sounds sad, vulnerable, or subdued. Show gentle empathy and care in your character!"
        elif self.is_musical:
            directive += f"{caller_name} played/sang music ({self.musical_desc}). React to their music!"
        elif self.background_noise == "music":
            directive += "There is music playing in their background. You can hear the tune/rhythm in their room!"
        elif self.background_noise == "voices_chatter":
            directive += "There are background voices or TV in their room. You can hear their background ambiance!"
        elif self.background_noise == "keyboard_clicks":
            directive += "You can hear keyboard typing or mouse clicking in their room."
        else:
            directive += f"React naturally to their emotional tone ({self.tone})!"

        return f"[(Acoustic & Environmental Perception:\n• " + "\n• ".join(details) + f"\n• Directive: {directive})]"


class CallAcousticAnalyzer:
    """Analyzes raw PCM or WAV audio bytes and generates CallAcousticProfile."""

    @classmethod
    def pcm_to_samples_16k(cls, pcm_bytes: bytes, channels: int = 2, sample_rate: int = 48000) -> Optional[Any]:
        """Fast NumPy vector decimation of raw s16le PCM to normalized 16kHz mono float32."""
        if not HAVE_NUMPY or np is None or len(pcm_bytes) < 32:
            return None
        try:
            raw = np.frombuffer(pcm_bytes, dtype=np.int16)
            if channels == 2:
                # Average stereo channels to mono
                usable_len = (len(raw) // 2) * 2
                mono = raw[:usable_len].reshape(-1, 2).mean(axis=1).astype(np.float32) / 32768.0
            else:
                mono = raw.astype(np.float32) / 32768.0

            # Downsample to 16kHz
            if sample_rate == 48000:
                return mono[::3]
            elif sample_rate == 16000:
                return mono
            else:
                step = max(1, int(round(sample_rate / 16000)))
                return mono[::step]
        except Exception:
            return None

    @classmethod
    def wav_to_samples_16k(cls, wav_bytes: bytes) -> Tuple[Optional[Any], int]:
        """Extracts normalized float32 samples from standard PCM16 WAV."""
        if not HAVE_NUMPY or np is None or len(wav_bytes) < 44:
            return None, 16000
        try:
            pos = 12
            sample_rate = 16000
            data_bytes = b""
            if wav_bytes[:4] == b'RIFF' and wav_bytes[8:12] == b'WAVE':
                while pos < len(wav_bytes) - 8:
                    chunk_id = wav_bytes[pos:pos+4]
                    chunk_size = int.from_bytes(wav_bytes[pos+4:pos+8], byteorder='little')
                    pos += 8
                    if chunk_id == b'fmt ':
                        sample_rate = int.from_bytes(wav_bytes[pos+4:pos+8], byteorder='little')
                    elif chunk_id == b'data':
                        data_bytes = wav_bytes[pos:pos+chunk_size]
                        break
                    pos += chunk_size
            if not data_bytes:
                data_bytes = wav_bytes[44:]
            samples = np.frombuffer(data_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            return samples, sample_rate
        except Exception:
            return None, 16000

    @classmethod
    def analyze_pcm(cls, pcm_bytes: bytes, channels: int = 2, sample_rate: int = 48000) -> CallAcousticProfile:
        samples = cls.pcm_to_samples_16k(pcm_bytes, channels=channels, sample_rate=sample_rate)
        if samples is None or len(samples) == 0:
            return CallAcousticProfile(is_noise_only=True)
        return cls.analyze_samples(samples, sr=16000)

    @classmethod
    def analyze_wav(cls, wav_bytes: bytes) -> CallAcousticProfile:
        samples, sr = cls.wav_to_samples_16k(wav_bytes)
        if samples is None or len(samples) == 0:
            return CallAcousticProfile(is_noise_only=True)
        return cls.analyze_samples(samples, sr=sr)

    @classmethod
    def analyze_samples(cls, samples: Any, sr: int = 16000) -> CallAcousticProfile:
        if not HAVE_NUMPY or np is None or len(samples) < int(sr * 0.2):
            return CallAcousticProfile(is_noise_only=True)

        dur = float(len(samples) / sr)
        rms = float(20.0 * math.log10(float(np.sqrt(np.mean(samples ** 2) + 1e-12))))
        zcr = float(np.sum(np.abs(np.diff(np.sign(samples))) > 0) / len(samples))

        # Spectral Centroid & Flatness
        win = np.hanning(len(samples))
        spec = np.abs(np.fft.rfft(samples * win))
        freqs = np.fft.rfftfreq(len(samples), 1.0 / sr)
        spec_sum = float(np.sum(spec) + 1e-9)
        centroid = float(np.sum(freqs * spec) / spec_sum)

        # Spectral Flatness (Wiener entropy)
        pos_spec = spec[spec > 1e-6]
        flatness = float(np.exp(np.mean(np.log(pos_spec))) / (np.mean(pos_spec) + 1e-9)) if len(pos_spec) > 0 else 1.0

        # Frame-by-frame analysis (160ms frames, 80ms hop)
        frame_len = int(0.16 * sr)
        hop_len = int(0.08 * sr)
        pitches: List[float] = []
        harmonics: List[float] = []
        frame_rms: List[float] = []
        frame_zcr: List[float] = []

        min_lag = int(sr / 650)  # max pitch ~650Hz
        max_lag = int(sr / 65)   # min pitch ~65Hz

        for st in range(0, len(samples) - frame_len + 1, hop_len):
            chunk = samples[st:st + frame_len]
            f_rms = float(20.0 * math.log10(float(np.sqrt(np.mean(chunk ** 2) + 1e-12))))
            frame_rms.append(f_rms)
            f_zcr = float(np.sum(np.abs(np.diff(np.sign(chunk))) > 0) / len(chunk))
            frame_zcr.append(f_zcr)

            n = len(chunk)
            f_chunk = np.fft.fft(chunk, n * 2)
            r = np.fft.ifft(f_chunk * np.conj(f_chunk)).real[:n]
            r_norm = r / (r[0] + 1e-12)

            if max_lag < len(r_norm) and min_lag < max_lag:
                seg = r_norm[min_lag:max_lag]
                p_idx = int(np.argmax(seg)) + min_lag
                h_val = float(r_norm[p_idx])
                harmonics.append(h_val)
                # Voice/instrument pitch condition
                if h_val > 0.35 and f_rms > -44.0:
                    pitches.append(float(sr / p_idx))
                else:
                    pitches.append(0.0)
            else:
                harmonics.append(0.0)
                pitches.append(0.0)

        voiced_pitches = [p for p in pitches if p > 0.0]
        mean_pitch = float(np.mean(voiced_pitches)) if voiced_pitches else 0.0
        pitch_range = float(np.max(voiced_pitches) - np.min(voiced_pitches)) if len(voiced_pitches) > 1 else 0.0
        avg_harm = float(np.mean(harmonics)) if harmonics else 0.0
        peak_rms = float(np.max(frame_rms)) if frame_rms else rms
        zcr_var = float(np.std(frame_zcr)) if frame_zcr else 0.0

        # Pitch & harmonic stability (fraction of consecutive voiced frames with steady pitch or harmonic octave/fifth transitions)
        stable_count = 0
        voiced_transitions = 0
        for i in range(len(pitches) - 1):
            p1, p2 = pitches[i], pitches[i+1]
            if p1 > 0.0 and p2 > 0.0:
                voiced_transitions += 1
                if abs(p1 - p2) < 7.0:
                    stable_count += 1
                else:
                    ratio = max(p1, p2) / (min(p1, p2) + 1e-6)
                    # Check musical harmonic intervals (octave ~2.0, fifth ~1.5, fourth ~1.33, double octave ~4.0)
                    if any(abs(ratio - target) < 0.26 for target in (2.0, 1.5, 1.33, 3.0, 4.0)):
                        stable_count += 1
        pitch_stability = (stable_count / voiced_transitions) if voiced_transitions > 0 else 0.0

        # Pitch contour
        contour = "none"
        if len(voiced_pitches) >= 4:
            q_len = max(1, len(voiced_pitches) // 4)
            first_q = float(np.mean(voiced_pitches[:q_len]))
            last_q = float(np.mean(voiced_pitches[-q_len:]))
            if last_q > first_q * 1.15:
                contour = "rising"
            elif first_q > last_q * 1.15:
                contour = "falling"
            elif pitch_range < 25.0:
                contour = "monotone"
            else:
                contour = "expressive"

        # Energy onsets & rhythmic transients
        onsets = 0
        onset_times = []
        for i in range(len(frame_rms) - 1):
            if (frame_rms[i+1] - frame_rms[i]) > 8.0 and frame_rms[i+1] > -36.0:
                onsets += 1
                onset_times.append(i * 0.08)

        # Estimate rhythm / BPM if recurring beats
        tempo_bpm = None
        if len(onset_times) >= 4:
            diffs = [onset_times[j+1] - onset_times[j] for j in range(len(onset_times)-1)]
            avg_diff = float(np.mean(diffs))
            if 0.35 <= avg_diff <= 1.0:
                tempo_bpm = round(60.0 / avg_diff, 1)

        # -------------------------------------------------------------
        # CLASSIFICATION LOGIC
        # -------------------------------------------------------------
        # 1. Transient click / tap / keyboard noise (impulsive non-speech)
        is_noise = False
        if dur < 0.20 and avg_harm < 0.20 and onsets <= 1:
            is_noise = True
        elif rms < -54.0 and not voiced_pitches:
            is_noise = True  # Ambient silence
        elif dur < 0.30 and rms < -30.0 and zcr > 0.45 and avg_harm < 0.12:
            is_noise = True  # Short keyclick / desk tap

        # 2. Background Noise Classification
        is_bg_music = bool((tempo_bpm and 65.0 <= tempo_bpm <= 185.0 and avg_harm > 0.28) or (pitch_stability > 0.58 and avg_harm > 0.40 and not voiced_pitches))
        is_keyboard = bool(zcr > 0.25 and centroid > 1900.0 and avg_harm < 0.25 and onsets >= 2)
        is_bg_voices = bool(onsets >= 3 and 0.14 < avg_harm < 0.45 and pitch_stability < 0.35 and len(voiced_pitches) > 2)
        is_ambient_noise = bool((flatness > 0.16 or centroid > 2300.0) and avg_harm < 0.25 and rms > -42.0)

        background_noise = "quiet"
        noise_desc = ""
        if is_bg_music:
            background_noise = "music"
            noise_desc = f"Background music or rhythm track playing (~{tempo_bpm:.0f} BPM)" if tempo_bpm else "Background music playing"
        elif is_keyboard:
            background_noise = "keyboard_clicks"
            noise_desc = "Keyboard typing, mouse clicking, or desk tapping sounds"
        elif is_bg_voices:
            background_noise = "voices_chatter"
            noise_desc = "Secondary voices, TV audio, or background conversation"
        elif is_ambient_noise:
            background_noise = "ambient_room"
            noise_desc = "Audible room noise (fan, airflow, or background hum)"

        # 3. Whisper (soft amplitude, breathy unvoiced tract, high ZCR)
        is_whisper = bool(
            (zcr > 0.13 and avg_harm < 0.32 and len(voiced_pitches) < len(pitches) * 0.40 and rms < -22.0 and dur >= 0.35)
            or (rms < -30.0 and zcr > 0.11 and dur >= 0.3)
        ) and not is_noise

        # 4. Shout / High-Energy Vocal Spike
        is_shout = bool(
            (peak_rms > -15.5 and (centroid > 1800.0 or peak_rms > -11.0))
            or (rms > -18.0 and (mean_pitch > 220.0 or centroid > 2000.0))
        ) and not is_whisper

        # 5. Laughter (rapid rhythmic energy bursts with vocal modulation)
        is_laughter = bool(
            (onsets >= 2 and zcr > 0.08 and pitch_stability < 0.65 and len(voiced_pitches) > 0 and rms > -36.0)
            or (len(frame_rms) >= 4 and any((frame_rms[i+1] - frame_rms[i]) > 4.5 for i in range(len(frame_rms)-1)) and zcr > 0.09 and rms > -36.0)
        ) and not is_whisper and not is_shout

        # 6. Sigh / Yawning (gradual exhale, energy slopes down, breathy)
        is_sigh = False
        if dur >= 0.6 and len(frame_rms) >= 4 and not is_laughter and not is_whisper and not is_shout:
            q = max(1, len(frame_rms) // 3)
            start_rms = float(np.mean(frame_rms[:q]))
            end_rms = float(np.mean(frame_rms[-q:]))
            if (start_rms - end_rms) > 5.0 and zcr > 0.08 and len(voiced_pitches) < len(pitches) * 0.35:
                is_sigh = True

        # 7. Musical Instruments / Singing
        is_musical = False
        musical_type = None
        musical_desc = ""

        # Solo Instrument: high pitch stability, high harmonicity across frames, low ZCR variance (no consonants)
        if pitch_stability > 0.65 and avg_harm > 0.55 and len(voiced_pitches) >= 4 and not is_whisper and zcr_var < 0.08:
            is_musical = True
            if 75.0 <= mean_pitch <= 360.0:
                musical_type = "guitar"
                musical_desc = "acoustic guitar chords or melody"
            elif 360.0 < mean_pitch <= 900.0:
                musical_type = "piano_or_synth"
                musical_desc = "piano or melodic instrument notes"
            else:
                musical_type = "solo_instrument"
                musical_desc = f"melodic instrument sound (Pitch: ~{mean_pitch:.0f}Hz)"

        # Singing: sustained vocal pitch on vowels, high harmonicity, human register
        elif len(voiced_pitches) > len(pitches) * 0.60 and avg_harm > 0.60 and 110.0 <= mean_pitch <= 520.0 and not is_shout and zcr_var < 0.09:
            is_musical = True
            musical_type = "singing"
            musical_desc = f"singing or vocal melody (Vocal tone: ~{mean_pitch:.0f}Hz)"

        # 8. Emotion: Sadness / Crying
        is_sad_or_crying = bool(
            contour == "falling" and rms < -25.0 and centroid < 1600.0 and
            pitch_range < 35.0 and not is_whisper and not is_sigh and dur >= 0.8
        )

        # 9. Emotion: Questioning / Curious
        is_questioning = False
        if len(voiced_pitches) >= 4 and not is_shout and not is_laughter and not is_whisper:
            tail_len = max(1, len(voiced_pitches) // 3)
            mid_pitch = float(np.mean(voiced_pitches[:-tail_len])) if len(voiced_pitches) > tail_len else mean_pitch
            tail_pitch = float(np.mean(voiced_pitches[-tail_len:]))
            if tail_pitch > mid_pitch * 1.10:
                is_questioning = True

        # 10. Emotion: Excited / Animated
        is_excited = bool(
            (pitch_range > 55.0 or (mean_pitch > 190.0 and rms > -24.0)) and
            centroid > 1600.0 and not is_shout and not is_whisper and not is_sad_or_crying
        )

        # Tone and vocal action synthesis
        vocal_action = None
        if is_whisper:
            tone = "Whispering softly (intimate, quiet, secret tone)"
            vocal_action = "whispered softly"
        elif is_shout:
            tone = "Shouting / high-energy exclamation (loud, intense, surprised)"
            vocal_action = "spoke with loud intensity / shouted"
        elif is_laughter:
            tone = "Laughing / playful giggling (amused, cheerful)"
            vocal_action = "laughed / chuckled"
        elif is_sigh:
            tone = "Heavy audible sigh (weary, relieved, or wistful)"
            vocal_action = "sighed heavily into the mic"
        elif is_sad_or_crying:
            tone = "Subdued, sad, or emotional voice (vulnerable, gentle)"
            vocal_action = "spoke with a sad, subdued tone"
        elif is_musical:
            tone = f"Musical performance ({musical_desc})"
            vocal_action = f"played or sang {musical_desc}"
        elif is_questioning:
            tone = "Curious / questioning / surprised (rising inflection)"
            vocal_action = "asked with a curious rising inflection"
        elif is_excited:
            tone = "Excited, lively, and enthusiastic (animated vocal energy)"
            vocal_action = "spoke with excited, lively energy"
        elif 0 < mean_pitch < 125.0 and rms < -22.0:
            tone = "Deep, relaxed, and calm conversational voice"
            vocal_action = "spoke in a calm, relaxed voice"
        else:
            tone = "Natural conversational tone"

        return CallAcousticProfile(
            duration_sec=round(dur, 2),
            rms_db=round(rms, 1),
            peak_rms_db=round(peak_rms, 1),
            zcr=round(zcr, 3),
            centroid_hz=round(centroid, 1),
            mean_pitch_hz=round(mean_pitch, 1),
            pitch_range_hz=round(pitch_range, 1),
            pitch_contour=contour,
            pitch_stability=round(pitch_stability, 2),
            harmonicity=round(avg_harm, 2),
            onsets=onsets,
            tempo_bpm=tempo_bpm,
            is_noise_only=is_noise,
            is_whisper=is_whisper,
            is_shout=is_shout,
            is_laughter=is_laughter,
            is_sigh=is_sigh,
            is_sad_or_crying=is_sad_or_crying,
            is_questioning=is_questioning,
            is_excited=is_excited,
            is_musical=is_musical,
            musical_type=musical_type,
            musical_desc=musical_desc,
            background_noise=background_noise,
            noise_desc=noise_desc,
            vocal_action=vocal_action,
            tone=tone
        )
