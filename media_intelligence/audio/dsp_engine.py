"""
Acoustic DSP Engine (NumPy hardware accelerated with Pure-Python fallback).
Computes RMS volume, ZCR, spectral centroid, dominant pitch, and onset envelope.
"""
import io
import math
import array
from typing import List, Tuple, Dict, Any, Optional

try:
    import numpy as np
    HAVE_NUMPY = True
except ImportError:
    np = None
    HAVE_NUMPY = False

class AudioMetrics:
    """Computes acoustic features locally without any API cost."""

    @staticmethod
    def parse_wav_pcm16(wav_bytes: bytes) -> Tuple[Any, int]:
        """Parses a standard 16-bit PCM WAV byte stream into normalized float samples and sample rate."""
        if len(wav_bytes) < 44:
            return (np.array([], dtype=np.float32) if HAVE_NUMPY else []), 16000
        
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
            
        if HAVE_NUMPY and np is not None:
            samples = np.frombuffer(data_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            return samples, sample_rate
        else:
            arr = array.array('h')
            safe_len = len(data_bytes) - (len(data_bytes) % 2)
            arr.frombytes(data_bytes[:safe_len])
            return [x / 32768.0 for x in arr], sample_rate

    @staticmethod
    def compute_rms_db(samples) -> float:
        """Computes Root Mean Square volume in decibels."""
        if len(samples) == 0:
            return -100.0
        
        if HAVE_NUMPY and np is not None and isinstance(samples, np.ndarray):
            rms = float(np.sqrt(np.mean(samples ** 2) + 1e-12))
            return 20.0 * math.log10(rms)
        else:
            mean_sq = sum(x * x for x in samples) / len(samples)
            rms = math.sqrt(mean_sq + 1e-12)
            return 20.0 * math.log10(rms)

    @staticmethod
    def compute_zcr(samples) -> float:
        """Computes Zero Crossing Rate (0.0 to 1.0)."""
        if len(samples) < 2:
            return 0.0
        
        if HAVE_NUMPY and np is not None and isinstance(samples, np.ndarray):
            zero_crossings = np.sum(np.abs(np.diff(np.sign(samples))) > 0)
            return float(zero_crossings / len(samples))
        else:
            zc = sum(1 for i in range(len(samples)-1) if (samples[i] >= 0 > samples[i+1]) or (samples[i] < 0 <= samples[i+1]))
            return float(zc / len(samples))

    @staticmethod
    def compute_spectral_centroid(samples, sample_rate: int = 16000) -> float:
        """Computes Spectral Centroid (brightness in Hz)."""
        if len(samples) < 128:
            return 0.0
        
        if HAVE_NUMPY and np is not None and isinstance(samples, np.ndarray):
            window = np.hanning(len(samples))
            spectrum = np.abs(np.fft.rfft(samples * window))
            freqs = np.fft.rfftfreq(len(samples), 1.0 / sample_rate)
            sum_spec = np.sum(spectrum)
            if sum_spec < 1e-9:
                return 0.0
            return float(np.sum(freqs * spectrum) / sum_spec)
        else:
            N = min(256, len(samples))
            sub = samples[:N]
            num, den = 0.0, 0.0
            for k in range(1, N // 2):
                freq = k * sample_rate / N
                re = sum(sub[n] * math.cos(2 * math.pi * k * n / N) for n in range(N))
                im = sum(sub[n] * math.sin(2 * math.pi * k * n / N) for n in range(N))
                mag = math.sqrt(re * re + im * im)
                num += freq * mag
                den += mag
            return float(num / den) if den > 1e-9 else 0.0

    @staticmethod
    def compute_dominant_pitch(samples, sample_rate: int = 16000) -> float:
        """Computes Dominant Pitch in Hz via autocorrelation."""
        if len(samples) < 512:
            return 0.0
        
        min_lag = int(sample_rate / 600)  # Max pitch ~600Hz
        max_lag = int(sample_rate / 50)   # Min pitch ~50Hz
        if max_lag >= len(samples):
            max_lag = len(samples) - 1
        if min_lag >= max_lag:
            return 0.0

        if HAVE_NUMPY and np is not None and isinstance(samples, np.ndarray):
            n = len(samples)
            f_samples = np.fft.fft(samples, n * 2)
            r = np.fft.ifft(f_samples * np.conj(f_samples)).real[:n]
            if r[0] < 1e-9:
                return 0.0
            r_norm = r / r[0]
            segment = r_norm[min_lag:max_lag]
            if len(segment) == 0:
                return 0.0
            peak_idx = int(np.argmax(segment)) + min_lag
            if r_norm[peak_idx] > 0.25:
                return float(sample_rate / peak_idx)
            return 0.0
        else:
            best_lag = 0
            max_corr = -1.0
            r0 = sum(x * x for x in samples[:512]) + 1e-12
            for lag in range(min_lag, max_lag, 2):
                corr = sum(samples[i] * samples[i + lag] for i in range(0, min(512, len(samples) - lag), 2))
                norm_corr = corr / r0
                if norm_corr > max_corr:
                    max_corr = norm_corr
                    best_lag = lag
            if max_corr > 0.25 and best_lag > 0:
                return float(sample_rate / best_lag)
            return 0.0

    @staticmethod
    def compute_onset_strength(samples, sample_rate: int = 16000) -> float:
        """Computes energy transient onset strength (percussive transients)."""
        if len(samples) < 512:
            return 0.0
        
        frame_size = 512
        hop_size = 256
        num_frames = (len(samples) - frame_size) // hop_size
        if num_frames < 2:
            return 0.0
        
        energies = []
        for i in range(num_frames):
            start = i * hop_size
            frame = samples[start : start + frame_size]
            if HAVE_NUMPY and np is not None and isinstance(samples, np.ndarray):
                energies.append(float(np.sum(frame ** 2)))
            else:
                energies.append(sum(x * x for x in frame))
        
        diffs = [max(0.0, energies[i+1] - energies[i]) for i in range(len(energies)-1)]
        return float(max(diffs) if diffs else 0.0)

class AudioDSPEngine:
    """Processes long continuous audio streams into 2-5 second analysis chunks with metrics."""

    @classmethod
    def analyze_audio_track(cls, wav_bytes: bytes, chunk_duration_sec: float = 3.0) -> List[Dict[str, Any]]:
        samples, sr = AudioMetrics.parse_wav_pcm16(wav_bytes)
        if len(samples) == 0:
            return []

        chunk_len = int(chunk_duration_sec * sr)
        total_samples = len(samples)
        chunks = []

        for start_idx in range(0, total_samples, chunk_len):
            end_idx = min(total_samples, start_idx + chunk_len)
            sub_samples = samples[start_idx:end_idx]
            if len(sub_samples) < sr * 0.5:
                continue # Skip tiny trailing fragment

            ts = start_idx / sr
            rms_db = AudioMetrics.compute_rms_db(sub_samples)
            zcr = AudioMetrics.compute_zcr(sub_samples)
            centroid = AudioMetrics.compute_spectral_centroid(sub_samples, sr)
            pitch = AudioMetrics.compute_dominant_pitch(sub_samples, sr)
            onset = AudioMetrics.compute_onset_strength(sub_samples, sr)

            chunks.append({
                "timestamp_sec": round(ts, 2),
                "duration_sec": round(len(sub_samples) / sr, 2),
                "rms_db": round(rms_db, 1),
                "zcr": round(zcr, 3),
                "centroid": round(centroid, 1),
                "pitch": round(pitch, 1),
                "onset": round(onset, 2)
            })

        return chunks
