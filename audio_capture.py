"""
Audio capture module.

Continuously records two streams in ring-buffers:
  • INPUT  — microphone (your voice)
  • OUTPUT — system / loopback audio (meeting participants)

Uses the ``soundcard`` library which provides native WASAPI loopback
support on Windows.  When the user presses the hotkey the buffers are
flushed, converted to WAV, and sent for analysis.
"""

import io
import logging
import threading
import warnings

# Suppress noisy soundcard discontinuity warnings (caused by CPU-heavy transcription)
warnings.filterwarnings("ignore", message="data discontinuity")
import wave
from collections import Counter, deque

import numpy as np
import soundcard as sc

from config import (
    AUDIO_CHANNELS,
    AUDIO_INPUT_DEVICE_ID,
    AUDIO_OUTPUT_DEVICE_ID,
    AUDIO_RING_BUFFER_SECONDS,
    AUDIO_SAMPLE_RATE,
    AUDIO_SOURCE,
    TRANSCRIPTION_INTERVAL,
)

logger = logging.getLogger(__name__)

# Each chunk recorded per iteration (seconds)
_CHUNK_SEC = 1
_REALTIME_WINDOW_SEC = max(5, TRANSCRIPTION_INTERVAL + 2)
_MIN_TRANSCRIBE_SEC = 1.0
_MIN_TRANSCRIBE_RMS = 0.01


def _build_device_choices(devices, default_device, default_label: str) -> list[tuple[str, str]]:
    """Build user-facing device choices as (label, id) tuples."""
    choices: list[tuple[str, str]] = []
    if default_device is not None:
        choices.append((f"{default_label}: {default_device.name}", ""))
    else:
        choices.append((default_label, ""))

    name_counts = Counter(device.name for device in devices)
    for device in devices:
        label = device.name
        if name_counts[device.name] > 1:
            label = f"{device.name} [{device.id[-8:]}]"
        choices.append((label, device.id))
    return choices


def list_microphone_choices() -> list[tuple[str, str]]:
    """Return selectable microphone choices for settings UIs."""
    try:
        microphones = list(sc.all_microphones())
        default_mic = sc.default_microphone()
        return _build_device_choices(microphones, default_mic, "System default mic")
    except Exception:
        logger.exception("Failed to enumerate microphones.")
        return [("System default mic", "")]


def list_speaker_choices() -> list[tuple[str, str]]:
    """Return selectable speaker/loopback choices for settings UIs."""
    try:
        speakers = list(sc.all_speakers())
        default_speaker = sc.default_speaker()
        return _build_device_choices(speakers, default_speaker, "System default output")
    except Exception:
        logger.exception("Failed to enumerate speakers.")
        return [("System default output", "")]


def _find_device_by_id(devices, device_id: str):
    for device in devices:
        if device.id == device_id:
            return device
    return None


def get_selected_microphone(device_id: str | None = None):
    """Resolve the configured microphone, falling back to the system default."""
    try:
        if device_id:
            microphones = list(sc.all_microphones())
            microphone = _find_device_by_id(microphones, device_id)
            if microphone is not None:
                return microphone
            logger.warning("Configured microphone device was not found. Falling back to the system default.")
        return sc.default_microphone()
    except Exception:
        logger.exception("Failed to resolve microphone device.")
        return None


def get_selected_speaker(device_id: str | None = None):
    """Resolve the configured speaker, falling back to the system default."""
    try:
        if device_id:
            speakers = list(sc.all_speakers())
            speaker = _find_device_by_id(speakers, device_id)
            if speaker is not None:
                return speaker
            logger.warning("Configured output device was not found. Falling back to the system default.")
        return sc.default_speaker()
    except Exception:
        logger.exception("Failed to resolve output device.")
        return None


def _is_transcribable(frames: np.ndarray | None, sample_rate: int) -> bool:
    """Return True when a frame window is large and loud enough to transcribe."""
    if frames is None or frames.shape[0] <= sample_rate * _MIN_TRANSCRIBE_SEC:
        return False
    rms = float(np.sqrt(np.mean(frames.astype(np.float32) ** 2)))
    return rms > _MIN_TRANSCRIBE_RMS


def _extract_incremental_text(previous: str, current: str) -> str:
    """Return only the new suffix from an overlapping rolling-window transcript."""
    import re

    prev_words = previous.split()
    curr_words = current.split()
    if not curr_words:
        return ""
    if previous.strip().lower() == current.strip().lower():
        return ""

    def normalize(word: str) -> str:
        return re.sub(r"^\W+|\W+$", "", word).lower()

    prev_keys = [normalize(word) for word in prev_words]
    curr_keys = [normalize(word) for word in curr_words]

    max_overlap = min(len(prev_keys), len(curr_keys))
    for overlap in range(max_overlap, 0, -1):
        if prev_keys[-overlap:] == curr_keys[:overlap]:
            return " ".join(curr_words[overlap:]).strip()

    return current.strip()


def _to_wav(frames: np.ndarray, sample_rate: int, channels: int) -> bytes:
    """Convert a float32/int16 numpy array to WAV bytes."""
    if frames.dtype == np.float32:
        frames = (frames * 32767).clip(-32768, 32767).astype(np.int16)
    elif frames.dtype != np.int16:
        frames = frames.astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(frames.tobytes())
    return buf.getvalue()


class _RingBuffer:
    """Thread-safe ring buffer that keeps the last *max_seconds* of audio."""

    def __init__(self, max_seconds: int, sample_rate: int, channels: int):
        self._max_frames = max_seconds * sample_rate
        self._sr = sample_rate
        self._ch = channels
        self._lock = threading.Lock()
        self._chunks: deque[np.ndarray] = deque()
        self._total_frames = 0

    def append(self, data: np.ndarray) -> None:
        n = data.shape[0]
        with self._lock:
            self._chunks.append(data)
            self._total_frames += n
            while self._total_frames > self._max_frames and self._chunks:
                removed = self._chunks.popleft()
                self._total_frames -= removed.shape[0]

    def flush(self) -> np.ndarray | None:
        """Return all buffered audio and clear the buffer."""
        with self._lock:
            if not self._chunks:
                return None
            result = np.concatenate(list(self._chunks), axis=0)
            self._chunks.clear()
            self._total_frames = 0
        return result

    def snapshot_recent(self, seconds: float) -> np.ndarray | None:
        """Return the most recent audio window without clearing the buffer."""
        max_frames = int(seconds * self._sr)
        with self._lock:
            if not self._chunks:
                return None
            target_frames = min(max_frames, self._total_frames)
            recent_chunks: list[np.ndarray] = []
            collected = 0
            for chunk in reversed(self._chunks):
                recent_chunks.append(chunk)
                collected += chunk.shape[0]
                if collected >= target_frames:
                    break

        if not recent_chunks:
            return None

        result = np.concatenate(list(reversed(recent_chunks)), axis=0)
        if result.shape[0] > target_frames:
            result = result[-target_frames:]
        return result

    @property
    def duration(self) -> float:
        return self._total_frames / self._sr


class ContinuousCapture:
    """Continuously captures mic input and system loopback into ring buffers.
    Optionally runs real-time background transcription."""

    def __init__(
        self,
        sample_rate: int = AUDIO_SAMPLE_RATE,
        channels: int = AUDIO_CHANNELS,
        ring_seconds: int = AUDIO_RING_BUFFER_SECONDS,
        transcribe_fn=None,
        on_transcript=None,
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.ring_seconds = ring_seconds

        self._input_buf = _RingBuffer(ring_seconds, sample_rate, channels)
        self._output_buf = _RingBuffer(ring_seconds, sample_rate, channels)

        # Real-time transcription support
        self._transcribe_fn = transcribe_fn  # callable(wav_bytes) -> str
        self._on_transcript = on_transcript  # callable(input_text, output_text)
        self._input_live_buf = _RingBuffer(_REALTIME_WINDOW_SEC, sample_rate, channels)
        self._output_live_buf = _RingBuffer(_REALTIME_WINDOW_SEC, sample_rate, channels)
        self._last_input_window_text = ""
        self._last_output_window_text = ""
        self._transcript_input = ""
        self._transcript_output = ""
        self._transcript_lock = threading.Lock()

        self._running = False
        self._mic_thread: threading.Thread | None = None
        self._loopback_thread: threading.Thread | None = None
        self._transcription_thread: threading.Thread | None = None

    # ── lifecycle ───────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True

        self._mic_thread = threading.Thread(
            target=self._record_mic, daemon=True, name="mic-capture"
        )
        self._loopback_thread = threading.Thread(
            target=self._record_loopback, daemon=True, name="loopback-capture"
        )
        self._mic_thread.start()
        self._loopback_thread.start()

        if self._transcribe_fn:
            self._transcription_thread = threading.Thread(
                target=self._transcription_loop, daemon=True, name="transcription"
            )
            self._transcription_thread.start()
            logger.info("Real-time transcription enabled (interval=%ds).", TRANSCRIPTION_INTERVAL)

        logger.info(
            "Continuous capture started (ring=%ds, sr=%d).",
            self.ring_seconds, self.sample_rate,
        )

    def stop(self) -> None:
        self._running = False
        for t in (self._mic_thread, self._loopback_thread, self._transcription_thread):
            if t and t.is_alive():
                t.join(timeout=3)
        logger.info("Continuous capture stopped.")

    @property
    def is_running(self) -> bool:
        return self._running

    # ── flush (called on hotkey) ────────────────────────────────────────

    def flush_input(self) -> bytes | None:
        """Return mic (your voice) audio as WAV bytes and clear buffer."""
        frames = self._input_buf.flush()
        if frames is None or len(frames) == 0:
            return None
        return _to_wav(frames, self.sample_rate, self.channels)

    def flush_output(self) -> bytes | None:
        """Return loopback (meeting) audio as WAV bytes and clear buffer."""
        frames = self._output_buf.flush()
        if frames is None or len(frames) == 0:
            return None
        return _to_wav(frames, self.sample_rate, self.channels)

    def flush_both(self) -> tuple[bytes | None, bytes | None]:
        """Convenience: flush mic and loopback at once."""
        return self.flush_input(), self.flush_output()

    # ── recording loops ─────────────────────────────────────────────────

    def _record_mic(self) -> None:
        """Continuously record from the selected microphone."""
        try:
            mic = get_selected_microphone(AUDIO_INPUT_DEVICE_ID)
            if mic is None:
                logger.warning("No microphone device available — your audio will not be recorded.")
                return
            logger.info("Mic device: %s", mic.name)
            chunk_frames = int(self.sample_rate * _CHUNK_SEC)
            with mic.recorder(
                samplerate=self.sample_rate, channels=self.channels
            ) as rec:
                while self._running:
                    data = rec.record(numframes=chunk_frames)
                    self._input_buf.append(data)
                    if self._transcribe_fn:
                        self._input_live_buf.append(data.copy())
        except Exception:
            logger.exception("Microphone capture failed.")

    def _record_loopback(self) -> None:
        """Continuously record system audio via WASAPI loopback."""
        try:
            speaker = get_selected_speaker(AUDIO_OUTPUT_DEVICE_ID)
            if speaker is None:
                logger.warning("No output device available — meeting audio will not be recorded.")
                return
            loopback = sc.get_microphone(
                speaker.id, include_loopback=True
            )
            logger.info("Loopback device: %s", loopback.name)
            chunk_frames = int(self.sample_rate * _CHUNK_SEC)
            with loopback.recorder(
                samplerate=self.sample_rate, channels=self.channels
            ) as rec:
                while self._running:
                    data = rec.record(numframes=chunk_frames)
                    self._output_buf.append(data)
                    if self._transcribe_fn:
                        self._output_live_buf.append(data.copy())
        except Exception:
            logger.exception(
                "Loopback capture failed — system audio will not be recorded. "
                "Ensure a speaker/headphone output device is active."
            )

    # ── status helpers ──────────────────────────────────────────────────

    @property
    def input_seconds(self) -> float:
        return self._input_buf.duration

    @property
    def output_seconds(self) -> float:
        return self._output_buf.duration

    # ── real-time transcription ─────────────────────────────────────────

    def _transcription_loop(self) -> None:
        """Periodically transcribe recent rolling windows in the background."""
        import time
        from concurrent.futures import ThreadPoolExecutor

        executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="whisper")

        while self._running:
            time.sleep(TRANSCRIPTION_INTERVAL)
            if not self._running:
                break

            # Read the most recent rolling windows so transcription never builds backlog.
            if AUDIO_SOURCE in ("me", "both"):
                input_frames = self._input_live_buf.snapshot_recent(_REALTIME_WINDOW_SEC)
            else:
                input_frames = None
                self._last_input_window_text = ""

            if AUDIO_SOURCE in ("other", "both"):
                output_frames = self._output_live_buf.snapshot_recent(_REALTIME_WINDOW_SEC)
            else:
                output_frames = None
                self._last_output_window_text = ""

            if not _is_transcribable(input_frames, self.sample_rate):
                input_frames = None
                self._last_input_window_text = ""

            if not _is_transcribable(output_frames, self.sample_rate):
                output_frames = None
                self._last_output_window_text = ""

            if input_frames is None and output_frames is None:
                continue

            # Transcribe both streams in parallel
            def _do_input(f=input_frames):
                if f is None:
                    return ""
                try:
                    return self._transcribe_fn(f, self.sample_rate)
                except Exception:
                    logger.exception("Background mic transcription failed.")
                    return ""

            def _do_output(f=output_frames):
                if f is None:
                    return ""
                try:
                    return self._transcribe_fn(f, self.sample_rate)
                except Exception:
                    logger.exception("Background loopback transcription failed.")
                    return ""

            fut_input = executor.submit(_do_input)
            fut_output = executor.submit(_do_output)

            new_input = fut_input.result()
            new_output = fut_output.result()
            append_input = _extract_incremental_text(self._last_input_window_text, new_input)
            append_output = _extract_incremental_text(self._last_output_window_text, new_output)
            self._last_input_window_text = new_input or ""
            self._last_output_window_text = new_output or ""

            if append_input or append_output:
                with self._transcript_lock:
                    if append_input:
                        self._transcript_input += append_input + "\n"
                    if append_output:
                        self._transcript_output += append_output + "\n"

                if self._on_transcript:
                    with self._transcript_lock:
                        self._on_transcript(
                            self._transcript_input,
                            self._transcript_output,
                        )

        executor.shutdown(wait=False)

    def get_transcript(self) -> tuple[str, str]:
        """Return accumulated transcript (input, output) without clearing."""
        with self._transcript_lock:
            return self._transcript_input, self._transcript_output

    def clear_transcript(self) -> tuple[str, str]:
        """Return and clear accumulated transcript."""
        with self._transcript_lock:
            result = (self._transcript_input, self._transcript_output)
            self._transcript_input = ""
            self._transcript_output = ""
        return result


def check_audio_available() -> bool:
    """Return True if the required audio device(s) are available."""
    try:
        has_input = get_selected_microphone(AUDIO_INPUT_DEVICE_ID) is not None
        has_output = get_selected_speaker(AUDIO_OUTPUT_DEVICE_ID) is not None
        if AUDIO_SOURCE == "me":
            return has_input
        if AUDIO_SOURCE == "other":
            return has_output
        return has_input or has_output
    except Exception:
        return False
