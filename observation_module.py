"""
PROJECT J // Real-Time Audio/Visual Passive Observation Module
Fully compliant with IMPLEMENTATION ORDERS 1 through 13.
Zero-dependency architecture: works with pure Python standard library (math, struct, array)
and automatically uses NumPy/PIL if installed for hardware acceleration.
"""

import asyncio
import base64
import io
import json
import logging
import math
import os
import struct
import array
import subprocess
import time
from collections import deque
from datetime import datetime
from typing import Callable, Deque, Dict, List, Optional, Tuple, Any

# Optional accelerators
try:
    import numpy as np
    HAVE_NUMPY = True
except ImportError:
    np = None
    HAVE_NUMPY = False

try:
    from PIL import Image
    HAVE_PIL = True
except ImportError:
    Image = None
    HAVE_PIL = False

logger = logging.getLogger("ProjectJ.Observation")

class AudioMetrics:
    """Computes real-time acoustic features purely in local NumPy or built-in Python without API calls."""
    
    @staticmethod
    def parse_wav_pcm16(wav_bytes: bytes) -> Tuple[List[float], int]:
        """Parses a standard 16-bit PCM WAV byte stream into normalized float samples and sample rate."""
        if len(wav_bytes) < 44:
            return [], 16000
        
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
            # ensure even byte count
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
        """Computes zero-crossing rate."""
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
        """Computes spectral centroid in Hz."""
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
            # 256-point DFT weighted spectral centroid
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
        """Computes dominant pitch (Hz) via autocorrelation."""
        if len(samples) < 512:
            return 0.0
        
        min_lag = int(sample_rate / 600)
        max_lag = int(sample_rate / 50)
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
            peak_idx = np.argmax(segment) + min_lag
            if r_norm[peak_idx] > 0.25:
                return float(sample_rate / peak_idx)
            return 0.0
        else:
            # Subsampled autocorrelation
            best_lag = 0
            max_corr = -1.0
            r0 = sum(x * x for x in samples[:512]) + 1e-12
            step = 2
            for lag in range(min_lag, max_lag, step):
                corr = sum(samples[i] * samples[i + lag] for i in range(0, 512 - lag, 2))
                norm_corr = corr / r0
                if norm_corr > max_corr:
                    max_corr = norm_corr
                    best_lag = lag
            if max_corr > 0.25 and best_lag > 0:
                return float(sample_rate / best_lag)
            return 0.0

    @staticmethod
    def compute_onset_strength(samples, sample_rate: int = 16000) -> float:
        """Computes onset envelope energy transient strength."""
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


class PassiveObservationModule:
    """
    Real-Time Audio/Visual Passive Observation Module
    Implements all 13 Implementation Orders with zero required dependencies.
    """

    def __init__(self, llm_dispatcher: Callable, config: dict, data_dir: str = "data"):
        self.llm_dispatcher = llm_dispatcher
        self.config = config
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        
        # State
        self.is_active = False
        self.session_start_time = 0.0
        self.reaction_threshold = self.config.get("observation_reaction_threshold", 0.95)
        self.session_logging_enabled = self.config.get("observation_session_logging", True)

        # Buffers
        self.frame_buffer: Deque[Tuple[float, str, bytes]] = deque(maxlen=60) # (timestamp, b64_jpg, raw_jpg_bytes)
        self.audio_buffer: Deque[Tuple[float, bytes, dict]] = deque(maxlen=6) # (timestamp, wav_bytes, metrics)
        self.memory_log: List[str] = []
        
        # Scene Differentiation
        self.last_analyzed_frame_bytes: Optional[bytes] = None
        self.pending_vision_queue: Deque[dict] = deque()

        # Rate Limiting & Counters
        self.last_vision_call_time = 0.0
        self.vision_calls_in_last_minute: List[float] = []
        self.stt_calls_in_last_minute: List[float] = []
        self.last_music_analysis_time = 0.0
        self.last_music_centroid = 0.0
        self.running_audio_rms_history: Deque[float] = deque(maxlen=12)

        # Background worker tasks
        self.workers: List[asyncio.Task] = []
        self.active_ffmpeg_processes: List[subprocess.Popen] = []
        
        # Callbacks
        self.on_status_change_callback: Optional[Callable[[str], asyncio.Future]] = None

    def set_status_callback(self, callback: Callable[[str], asyncio.Future]):
        self.on_status_change_callback = callback

    def _get_timestamp_str(self, elapsed_seconds: float) -> str:
        hours = int(elapsed_seconds // 3600)
        minutes = int((elapsed_seconds % 3600) // 60)
        seconds = int(elapsed_seconds % 60)
        return f"[{hours:02d}:{minutes:02d}:{seconds:02d}]"

    def _estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    # ─── 12. STARTUP AND SHUTDOWN ────────────────────────────────

    async def start_observation(self, video_source: Optional[str] = None) -> str:
        if self.is_active:
            return "Observation is already active."

        self.is_active = True
        self.session_start_time = time.time()
        self.frame_buffer.clear()
        self.audio_buffer.clear()
        self.memory_log.clear()
        self.pending_vision_queue.clear()
        self.last_analyzed_frame_bytes = None
        self.last_vision_call_time = 0.0
        self.vision_calls_in_last_minute.clear()
        self.stt_calls_in_last_minute.clear()
        self.last_music_analysis_time = 0.0
        self.last_music_centroid = 0.0
        self.running_audio_rms_history.clear()

        self.workers = [
            asyncio.create_task(self._vision_rate_limiter_loop()),
            asyncio.create_task(self._log_compression_monitor_loop())
        ]

        if video_source:
            self._start_ffmpeg_stream_ingestion(video_source)

        return "Observation active. I am watching and listening."

    async def stop_observation(self) -> str:
        if not self.is_active:
            return "Observation is not currently active."

        self.is_active = False
        
        for w in self.workers:
            w.cancel()
        self.workers.clear()

        for proc in self.active_ffmpeg_processes:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try: proc.kill()
                except: pass
        self.active_ffmpeg_processes.clear()

        if self.session_logging_enabled and self.memory_log:
            try:
                log_filename = f"observation_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                log_path = os.path.join(self.data_dir, log_filename)
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(self.memory_log))
                logger.info(f"Observation session saved to {log_path}")
            except Exception as e:
                logger.error(f"Failed to save observation log: {e}")

        self.frame_buffer.clear()
        self.audio_buffer.clear()

        return "Observation ended."

    # ─── 2 & 5. STREAM INGESTION (FFMPEG PIPES) ───────────────────

    def _start_ffmpeg_stream_ingestion(self, stream_url: str):
        try:
            video_cmd = [
                "ffmpeg", "-re", "-i", stream_url,
                "-vf", "fps=1,scale=320:-1",
                "-f", "image2pipe", "-vcodec", "mjpeg", "-q:v", "3",
                "-"
            ]
            video_proc = subprocess.Popen(video_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            self.active_ffmpeg_processes.append(video_proc)
            asyncio.create_task(self._read_video_pipe(video_proc))

            audio_cmd = [
                "ffmpeg", "-re", "-i", stream_url,
                "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                "-f", "s16le",
                "-"
            ]
            audio_proc = subprocess.Popen(audio_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            self.active_ffmpeg_processes.append(audio_proc)
            asyncio.create_task(self._read_audio_pipe(audio_proc))
        except Exception as e:
            logger.error(f"Failed to start ffmpeg ingestion: {e}")

    async def _read_video_pipe(self, proc: subprocess.Popen):
        buffer = bytearray()
        while self.is_active and proc.poll() is None:
            chunk = await asyncio.to_thread(proc.stdout.read, 4096)
            if not chunk:
                break
            buffer.extend(chunk)
            while True:
                soi = buffer.find(b'\xff\xd8')
                if soi == -1:
                    buffer.clear()
                    break
                eoi = buffer.find(b'\xff\xd9', soi + 2)
                if eoi == -1:
                    if soi > 0:
                        buffer = buffer[soi:]
                    break
                jpeg_bytes = bytes(buffer[soi : eoi + 2])
                buffer = buffer[eoi + 2:]
                await self.ingest_frame_bytes(jpeg_bytes)
            await asyncio.sleep(0.01)

    async def _read_audio_pipe(self, proc: subprocess.Popen):
        chunk_bytes_needed = 10 * 16000 * 2
        buffer = bytearray()
        while self.is_active and proc.poll() is None:
            chunk = await asyncio.to_thread(proc.stdout.read, 8192)
            if not chunk:
                break
            buffer.extend(chunk)
            while len(buffer) >= chunk_bytes_needed:
                pcm_data = bytes(buffer[:chunk_bytes_needed])
                buffer = buffer[chunk_bytes_needed:]
                wav_io = io.BytesIO()
                wav_io.write(b'RIFF')
                wav_io.write((36 + len(pcm_data)).to_bytes(4, 'little'))
                wav_io.write(b'WAVEfmt ')
                wav_io.write((16).to_bytes(4, 'little'))
                wav_io.write((1).to_bytes(2, 'little'))
                wav_io.write((1).to_bytes(2, 'little'))
                wav_io.write((16000).to_bytes(4, 'little'))
                wav_io.write((32000).to_bytes(4, 'little'))
                wav_io.write((2).to_bytes(2, 'little'))
                wav_io.write((16).to_bytes(2, 'little'))
                wav_io.write(b'data')
                wav_io.write(len(pcm_data).to_bytes(4, 'little'))
                wav_io.write(pcm_data)
                wav_bytes = wav_io.getvalue()
                await self.ingest_audio_chunk(wav_bytes)
            await asyncio.sleep(0.01)

    # ─── 2. VIDEO INGESTION & 3. SCENE DIFFERENTIATION ENGINE ────

    async def ingest_frame_bytes(self, jpeg_bytes: bytes):
        if not self.is_active:
            return

        ts = time.time()
        try:
            # Scaled to 320 width
            if HAVE_PIL and Image is not None:
                try:
                    pil_img = Image.open(io.BytesIO(jpeg_bytes)).convert("RGB")
                    if pil_img.width != 320:
                        w_percent = (320 / float(pil_img.width))
                        h_size = int((float(pil_img.height) * float(w_percent)))
                        pil_img = pil_img.resize((320, h_size), Image.Resampling.BILINEAR)
                        out_io = io.BytesIO()
                        pil_img.save(out_io, format="JPEG", quality=80)
                        jpeg_bytes = out_io.getvalue()
                except Exception:
                    pass
            
            b64_str = base64.b64encode(jpeg_bytes).decode("utf-8")
            self.frame_buffer.append((ts, b64_str, jpeg_bytes))

            if self.last_analyzed_frame_bytes is None:
                self.last_analyzed_frame_bytes = jpeg_bytes
                self._trigger_scene_change_window(ts, is_initial=True)
                return

            diff = self._compute_mean_pixel_diff(jpeg_bytes, self.last_analyzed_frame_bytes)
            
            if diff >= self.reaction_threshold:
                await self._trigger_catastrophic_breach("ALERT")

            if diff >= 0.04:
                self.last_analyzed_frame_bytes = jpeg_bytes
                self._trigger_scene_change_window(ts)
        except Exception as e:
            logger.error(f"Error in frame ingestion: {e}")

    def _compute_mean_pixel_diff(self, bytes1: bytes, bytes2: bytes) -> float:
        try:
            if HAVE_PIL and Image is not None:
                i1 = Image.open(io.BytesIO(bytes1)).resize((32, 32)).convert("L")
                i2 = Image.open(io.BytesIO(bytes2)).resize((32, 32)).convert("L")
                b1 = list(i1.getdata())
                b2 = list(i2.getdata())
                diff = sum(abs(x - y) for x, y in zip(b1, b2)) / (255.0 * len(b1))
                return float(diff)
            else:
                # Fast byte sampling comparison
                sample_len = min(len(bytes1), len(bytes2), 2048)
                if sample_len == 0:
                    return 0.0
                step = 4
                diff = sum(abs(bytes1[i] - bytes2[i]) for i in range(100, sample_len, step)) / (255.0 * (sample_len // step))
                return float(diff)
        except Exception:
            return 0.0

    def _trigger_scene_change_window(self, keyframe_ts: float, is_initial: bool = False):
        asyncio.create_task(self._collect_5_frame_window(keyframe_ts, is_initial))

    async def _collect_5_frame_window(self, keyframe_ts: float, is_initial: bool):
        await asyncio.sleep(2.1)
        
        frames_list = list(self.frame_buffer)
        if not frames_list:
            return

        key_idx = len(frames_list) - 1
        for i, (ts, _, _) in enumerate(frames_list):
            if abs(ts - keyframe_ts) < 0.5:
                key_idx = i
                break

        start_idx = max(0, key_idx - 2)
        end_idx = min(len(frames_list), key_idx + 3)
        window_frames = frames_list[start_idx:end_idx]
        
        b64_frames = [f[1] for f in window_frames]
        elapsed = keyframe_ts - self.session_start_time
        timestamp_label = self._get_timestamp_str(elapsed)

        self.pending_vision_queue.append({
            "timestamp_label": timestamp_label,
            "timestamp": keyframe_ts,
            "frames": b64_frames
        })

    # ─── 4 & 10 & 11. VISION ANALYSIS — RATE-LIMITED ─────────────

    async def _vision_rate_limiter_loop(self):
        backoff_delay = 1.0
        while self.is_active:
            try:
                now = time.time()
                self.vision_calls_in_last_minute = [t for t in self.vision_calls_in_last_minute if now - t < 60.0]

                if not self.pending_vision_queue:
                    await asyncio.sleep(0.5)
                    continue

                time_since_last = now - self.last_vision_call_time
                if time_since_last < 30.0 or len(self.vision_calls_in_last_minute) >= 2:
                    await asyncio.sleep(1.0)
                    continue

                batch_items = []
                while self.pending_vision_queue and len(batch_items) < 2:
                    batch_items.append(self.pending_vision_queue.popleft())

                all_b64_frames = []
                ts_label = batch_items[0]["timestamp_label"]
                for item in batch_items:
                    for f in item["frames"]:
                        if f not in all_b64_frames:
                            all_b64_frames.append(f)
                
                all_b64_frames = all_b64_frames[:10]
                vision_prompt = "Describe what visually changed in these frames in 2 sentences. No commentary, no reactions, no emotional language. Factual visual description only."

                success, desc = await self._execute_vision_with_failover(vision_prompt, all_b64_frames)
                
                if success and desc:
                    self.last_vision_call_time = time.time()
                    self.vision_calls_in_last_minute.append(self.last_vision_call_time)
                    backoff_delay = 1.0
                    
                    log_entry = f"{ts_label} VISUAL: {desc.strip()}"
                    self.memory_log.append(log_entry)
                    logger.info(f"[MEMORY LOG] {log_entry}")
                else:
                    logger.warning("[VISUAL] Vision service unavailable. Queuing observation.")
                    self.memory_log.append(f"{ts_label} VISUAL: Observation queued — vision service unavailable.")
                    await asyncio.sleep(min(60.0, backoff_delay * 2))
                    backoff_delay = min(60.0, backoff_delay * 2)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in vision rate limiter loop: {e}")
                await asyncio.sleep(2.0)

    async def _execute_vision_with_failover(self, prompt: str, b64_frames: List[str]) -> Tuple[bool, str]:
        providers = ["gemini", "openrouter", "groq"]
        for provider in providers:
            try:
                res, err = await self.llm_dispatcher(
                    call_type="vision",
                    provider=provider,
                    prompt=prompt,
                    images_b64=b64_frames
                )
                if not err and res and res.strip():
                    return True, res.strip()
            except Exception as e:
                logger.warning(f"Vision provider '{provider}' failed: {e}")
        return False, ""

    # ─── 5, 6, 7. AUDIO INGESTION & ROUTER ───────────────────────

    async def ingest_audio_chunk(self, wav_bytes: bytes):
        if not self.is_active:
            return

        ts = time.time()
        elapsed = ts - self.session_start_time
        ts_label = self._get_timestamp_str(elapsed)

        try:
            samples, sr = AudioMetrics.parse_wav_pcm16(wav_bytes)
            rms_db = AudioMetrics.compute_rms_db(samples)
            zcr = AudioMetrics.compute_zcr(samples)
            centroid = AudioMetrics.compute_spectral_centroid(samples, sr)
            pitch = AudioMetrics.compute_dominant_pitch(samples, sr)
            onset = AudioMetrics.compute_onset_strength(samples, sr)

            metrics = {
                "rms_db": rms_db,
                "zcr": zcr,
                "centroid": centroid,
                "pitch": pitch,
                "onset": onset
            }
            self.audio_buffer.append((ts, wav_bytes, metrics))

            avg_rms = sum(self.running_audio_rms_history) / len(self.running_audio_rms_history) if self.running_audio_rms_history else -60.0
            self.running_audio_rms_history.append(rms_db)

            if rms_db > -5.0 and onset > 50.0:
                await self._trigger_catastrophic_breach("LOUD")

            # 7a: SILENCE
            if rms_db < -40.0 and zcr < 0.05:
                self.memory_log.append(f"{ts_label} AUDIO: Quiet ambient tone. No significant sound.")
                return

            # 7d: SFX / EVENT
            if rms_db > (avg_rms + 12.0) or onset > 30.0:
                log_entry = f"{ts_label} AUDIO: Loud audio event detected."
                self.memory_log.append(log_entry)
                if self.frame_buffer:
                    last_frame_b64 = self.frame_buffer[-1][1]
                    logger.info(f"{ts_label} SFX Event captured.")

            # 7b: SPEECH
            if 0.03 <= zcr <= 0.35 and 300.0 <= centroid <= 4000.0 and rms_db >= -38.0:
                asyncio.create_task(self._process_speech_chunk(ts_label, wav_bytes, pitch, rms_db, zcr))
                return

            # 7c: MUSIC / SCORE
            if centroid > 800.0 and onset > 2.0 and rms_db >= -35.0:
                centroid_shift = abs(centroid - self.last_music_centroid) / max(self.last_music_centroid, 1.0)
                time_since_music = time.time() - self.last_music_analysis_time
                if (centroid_shift > 0.15 or self.last_music_centroid == 0.0) and time_since_music >= 90.0:
                    self.last_music_centroid = centroid
                    self.last_music_analysis_time = time.time()
                    asyncio.create_task(self._process_music_chunk(ts_label, wav_bytes))
                else:
                    self.memory_log.append(f"{ts_label} AUDIO: Background music continuing.")

        except Exception as e:
            logger.error(f"Error in audio processing router: {e}")

    async def _process_speech_chunk(self, ts_label: str, wav_bytes: bytes, pitch: float, rms_db: float, zcr: float):
        now = time.time()
        self.stt_calls_in_last_minute = [t for t in self.stt_calls_in_last_minute if now - t < 60.0]
        if len(self.stt_calls_in_last_minute) >= 6:
            logger.warning("STT rate limit (6/min) reached. Skipping transcription.")
            return
        
        self.stt_calls_in_last_minute.append(now)

        pitch_tag = "high" if pitch > 220.0 else ("low" if pitch > 0 and pitch < 120.0 else "mid")
        vol_tag = "whisper" if rms_db < -30.0 else ("raised" if rms_db > -14.0 else "normal")
        cadence_tag = "fast" if zcr > 0.2 else ("slow" if zcr < 0.08 else "steady")
        tone_str = f"Voice pitch: {pitch_tag}. Volume: {vol_tag}. Cadence: {cadence_tag}."

        transcription = await self._execute_stt_with_failover(wav_bytes)
        if transcription and transcription.strip():
            log_entry = f"{ts_label} AUDIO: Dialogue — \"{transcription.strip()}\" ({tone_str})"
            self.memory_log.append(log_entry)
            logger.info(f"[MEMORY LOG] {log_entry}")

    async def _execute_stt_with_failover(self, wav_bytes: bytes) -> Optional[str]:
        providers = ["groq", "gemini", "openrouter"]
        for p in providers:
            try:
                res, err = await self.llm_dispatcher(call_type="stt", provider=p, audio_bytes=wav_bytes)
                if not err and res and res.strip():
                    return res.strip()
            except Exception as e:
                logger.warning(f"STT provider '{p}' failed: {e}")
        return None

    async def _process_music_chunk(self, ts_label: str, wav_bytes: bytes):
        prompt = "Describe the music or background audio in 2 sentences. Genre, tempo, mood, instrumentation. No commentary."
        for p in ["gemini", "openrouter"]:
            try:
                res, err = await self.llm_dispatcher(call_type="audio_description", provider=p, audio_bytes=wav_bytes, prompt=prompt)
                if not err and res and res.strip():
                    log_entry = f"{ts_label} AUDIO: {res.strip()}"
                    self.memory_log.append(log_entry)
                    logger.info(f"[MEMORY LOG] {log_entry}")
                    return
            except Exception:
                continue

    # ─── 8. UNIFIED ROLLING MEMORY LOG & COMPRESSION ─────────────

    async def _log_compression_monitor_loop(self):
        while self.is_active:
            try:
                await asyncio.sleep(15.0)
                full_log_text = "\n".join(self.memory_log)
                token_count = self._estimate_tokens(full_log_text)
                
                if token_count > 4000 and len(self.memory_log) >= 10:
                    split_idx = len(self.memory_log) // 2
                    old_entries = self.memory_log[:split_idx]
                    recent_entries = self.memory_log[split_idx:]

                    compress_prompt = (
                        "You are an objective archival compression system. "
                        "Summarize the following chronological observation logs into a single concise paragraph beginning with 'Previously: '. "
                        "Preserve key facts, visual events, dialogue, and audio metrics factually in third person with no commentary:\n\n"
                        + "\n".join(old_entries)
                    )

                    res, err = await self.llm_dispatcher(call_type="text", provider="auto", prompt=compress_prompt)
                    if not err and res and res.strip():
                        summary_entry = res.strip()
                        if not summary_entry.startswith("Previously:"):
                            summary_entry = f"Previously: {summary_entry}"
                        self.memory_log = [summary_entry] + recent_entries
                        logger.info("Successfully compressed oldest 50% of observation memory log.")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in memory log compression monitor: {e}")

    # ─── 1. CORE BEHAVIOR CATASTROPHIC BREACH ─────────────────────

    async def _trigger_catastrophic_breach(self, alert_word: str):
        if self.on_status_change_callback:
            try:
                await self.on_status_change_callback(alert_word)
            except Exception as e:
                logger.error(f"Error emitting status change callback: {e}")

    # ─── 9. QUERY RESPONSE PROTOCOL & 13. NO PERSONA OUTPUT ───────

    async def answer_user_query(self, user_question: str) -> str:
        if not self.is_active:
            return "Observation session is not currently active."

        full_log_str = "\n".join(self.memory_log) if self.memory_log else "No observation entries logged yet."
        recent_frames = [f[1] for f in list(self.frame_buffer)[-5:]]
        
        system_instruction = (
            "You are an objective observation query engine. You answer queries strictly based on the provided Chronological Observation Memory Log and recent visual/audio buffers.\n"
            "STRICT RULES:\n"
            "1. Answer the user's question directly using ONLY the evidence present in the memory log and visual frames.\n"
            "2. Do not hallucinate, speculate, or mention events that were not logged.\n"
            "3. If the memory log does not contain the answer, state EXACTLY: 'I did not observe that in the session so far.'\n"
            "4. Do NOT use first-person meta-commentary about your own perception (never say 'I see', 'I hear', 'I am watching', 'As an AI').\n"
            "5. Do NOT ask follow-up questions. Do NOT volunteer opinions or suggestions. State the facts and stop."
        )

        user_content = (
            f"=== CHRONOLOGICAL OBSERVATION MEMORY LOG ===\n{full_log_str}\n\n"
            f"=== USER QUERY ===\n{user_question}"
        )

        res, err = await self.llm_dispatcher(
            call_type="vision_query",
            provider="auto",
            system_prompt=system_instruction,
            prompt=user_content,
            images_b64=recent_frames
        )

        if not err and res and res.strip():
            return res.strip()
        
        return "I did not observe that in the session so far."

    # ─── TELEMETRY & STATUS ──────────────────────────────────────

    def get_telemetry(self) -> dict:
        now = time.time()
        elapsed = now - self.session_start_time if self.is_active else 0.0
        return {
            "is_active": self.is_active,
            "session_elapsed_seconds": round(elapsed, 1),
            "session_time_str": self._get_timestamp_str(elapsed),
            "total_frames_in_buffer": len(self.frame_buffer),
            "total_audio_chunks_in_buffer": len(self.audio_buffer),
            "memory_log_entries_count": len(self.memory_log),
            "estimated_token_count": self._estimate_tokens("\n".join(self.memory_log)),
            "vision_calls_last_minute": len([t for t in self.vision_calls_in_last_minute if now - t < 60.0]),
            "stt_calls_last_minute": len([t for t in self.stt_calls_in_last_minute if now - t < 60.0]),
            "reaction_threshold": self.reaction_threshold,
            "latest_log_snippet": self.memory_log[-10:] if self.memory_log else []
        }
