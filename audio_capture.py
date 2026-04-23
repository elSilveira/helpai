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
import re
import threading
import time
import warnings
import wave
from collections import Counter, deque

import numpy as np
import soundcard as sc
from soundcard.mediafoundation import SoundcardRuntimeWarning

# Suppress the specific soundcard overrun warning after startup so the terminal
# stays readable. The actual mitigation is handled below by reducing recorder
# blocking time and avoiding unnecessary background work.
warnings.filterwarnings(
    "ignore",
    message=r"data discontinuity in recording",
    category=SoundcardRuntimeWarning,
    module=r"soundcard\.mediafoundation",
)

from config import (
    AUDIO_CHANNELS,
    AUDIO_INPUT_DEVICE_ID,
    AUDIO_OUTPUT_DEVICE_ID,
    AUDIO_RING_BUFFER_SECONDS,
    AUDIO_SAMPLE_RATE,
    AUDIO_SOURCE,
    LOCAL_WHISPER_DEVICE,
    TRANSCRIPTION_INTERVAL,
)

logger = logging.getLogger(__name__)

# Each chunk recorded per iteration (seconds). Smaller chunks reduce the chance
# of WASAPI buffer overruns when local transcription briefly spikes CPU usage.
_CHUNK_SEC = 0.25
_PRE_ROLL_SEC = 0.75
_SEAL_OVERLAP_SEC = 2.0   # tail of sealed utterance kept as lead-in for next window
_MAX_UTTERANCE_SEC = max(30, min(AUDIO_RING_BUFFER_SECONDS, 60))
_MIN_TRANSCRIBE_SEC = 0.35
_MIN_TRANSCRIBE_RMS = 0.005
_VOICE_ACTIVITY_RMS = 0.004
_VOICE_ACTIVITY_PEAK = 0.02
_SILENCE_COMMIT_SEC = 1.8
_PUNCTUATION_COMMIT_SEC = 0.8
# Auto-seal long utterances at short natural pauses to keep Whisper fast
# and avoid ever-growing windows.  Once the utterance exceeds
# _AUTO_SEAL_AFTER_SEC, any silence >= _AUTO_SEAL_SILENCE_SEC triggers a seal.
_AUTO_SEAL_AFTER_SEC = 12.0
_AUTO_SEAL_SILENCE_SEC = 0.45
# Versioned pipeline: force-split continuous speech so Whisper always processes
# bounded audio.  The front is committed; the tail stays as overlap context.
_VERSION_AFTER_SEC = 10.0
_VERSION_OVERLAP_SEC = 2.5
_LEVEL_SMOOTHING = 0.35
_LEVEL_DECAY_PER_SEC = 0.85
_METER_RMS_CEILING = 0.05
_METER_PEAK_CEILING = 0.25


def _chunk_energy(data: np.ndarray | None) -> tuple[float, float]:
    """Return RMS/peak values for one audio chunk or frame window."""
    if data is None or data.size == 0:
        return 0.0, 0.0
    audio = data.astype(np.float32)
    rms = float(np.sqrt(np.mean(audio ** 2)))
    peak = float(np.max(np.abs(audio)))
    return rms, peak


def _has_voice_signal(rms: float, peak: float) -> bool:
    """Return True when chunk energy looks like speech or a leading consonant."""
    return rms >= _VOICE_ACTIVITY_RMS or peak >= _VOICE_ACTIVITY_PEAK


def _meter_level(rms: float, peak: float) -> float:
    """Map chunk energy into a 0..1 UI level meter."""
    if rms <= 0.0 and peak <= 0.0:
        return 0.0
    rms_ratio = min(1.0, rms / _METER_RMS_CEILING)
    peak_ratio = min(1.0, peak / _METER_PEAK_CEILING)
    return float(max(rms_ratio ** 0.5, peak_ratio * 0.7))


def _has_voice_activity(data: np.ndarray | None) -> bool:
    """Return True when a freshly recorded chunk contains speech-like energy."""
    rms, peak = _chunk_energy(data)
    return _has_voice_signal(rms, peak)


def _join_transcript_text(existing: str, addition: str) -> str:
    """Append transcript text while preserving punctuation spacing."""
    left = existing.strip()
    right = addition.strip()
    if not left:
        return right
    if not right:
        return left
    if right[0] in ",.!?;:)]}" or left.endswith(("(", "[", "{", '"', "'")):
        return left + right
    return f"{left} {right}"


def _ends_sentence(text: str) -> bool:
    """Return True when text looks like a completed sentence/utterance."""
    stripped = text.strip()
    if not stripped:
        return False
    return stripped.endswith((".", "!", "?", "…", ".\"", "!\"", "?\"", ".'", "!'", "?'", ")", "]"))


def _append_committed_text(existing: str, addition: str) -> str:
    """Append a completed utterance as its own logical transcript line."""
    segment = addition.strip()
    if not segment:
        return existing
    if not existing:
        return segment
    return f"{existing}\n{segment}"


def _compose_transcript(committed: str, draft: str) -> str:
    """Return the user-visible transcript including any in-progress draft."""
    committed = committed.strip()
    draft = draft.strip()
    if committed and draft:
        return f"{committed}\n{draft}"
    return committed or draft


class _CommittedSegment:
    """One committed utterance with a fast (instant) and optional clean (backup) transcription."""
    __slots__ = (
        "fast_text", "clean_text", "audio", "sample_rate", "_backup_submitted",
    )

    def __init__(self, fast_text: str, audio: np.ndarray | None = None, sample_rate: int = 16000):
        self.fast_text = fast_text
        self.clean_text: str | None = None
        self.audio = audio.copy() if audio is not None else None
        self.sample_rate = sample_rate
        self._backup_submitted = False

    @property
    def text(self) -> str:
        return self.clean_text if self.clean_text is not None else self.fast_text


def _rebuild_from_segments(segments: list[_CommittedSegment]) -> str:
    """Join committed segments into a single transcript string."""
    parts = [seg.text for seg in segments if seg.text]
    return "\n".join(parts)


def _stabilize_draft_text(previous: str, candidate: str) -> str:
    """Avoid obvious regressions when live utterance transcription fluctuates."""
    prev = previous.strip()
    current = candidate.strip()
    if not current:
        return prev
    if not prev:
        return current

    def normalize(text: str) -> str:
        cleaned = re.sub(r"[^\w]+", " ", text)
        return re.sub(r"\s+", " ", cleaned).strip().lower()

    prev_key = normalize(prev)
    current_key = normalize(current)
    if not prev_key:
        return current
    if prev_key == current_key:
        return current
    if current_key.startswith(prev_key) or prev_key in current_key:
        return current
    if prev_key.startswith(current_key) or current_key in prev_key:
        return prev
    return current


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
    return _is_transcribable_window(frames, sample_rate, allow_short=False)


def _is_transcribable_window(
    frames: np.ndarray | None,
    sample_rate: int,
    *,
    allow_short: bool,
) -> bool:
    """Return True when a live utterance window is worth sending to STT."""
    if frames is None:
        return False
    min_seconds = 0.2 if allow_short else _MIN_TRANSCRIBE_SEC
    if frames.shape[0] <= sample_rate * min_seconds:
        return False
    rms, peak = _chunk_energy(frames)
    if allow_short:
        return rms > _VOICE_ACTIVITY_RMS or peak > (_VOICE_ACTIVITY_PEAK * 0.7)
    return rms > _MIN_TRANSCRIBE_RMS or peak > _VOICE_ACTIVITY_PEAK


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

    def clear(self) -> None:
        """Clear the buffer without returning its contents."""
        with self._lock:
            self._chunks.clear()
            self._total_frames = 0

    def snapshot_all(self) -> np.ndarray | None:
        """Return all currently buffered audio without clearing the buffer."""
        with self._lock:
            if not self._chunks:
                return None
            return np.concatenate(list(self._chunks), axis=0)

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

    def split_front(self, seconds: float) -> np.ndarray | None:
        """Remove and return the first *seconds* of audio, keeping the rest."""
        target_frames = int(seconds * self._sr)
        with self._lock:
            if self._total_frames <= target_frames:
                return None
            front_chunks: list[np.ndarray] = []
            collected = 0
            while self._chunks and collected < target_frames:
                chunk = self._chunks.popleft()
                front_chunks.append(chunk)
                collected += chunk.shape[0]
                self._total_frames -= chunk.shape[0]
            if not front_chunks:
                return None
            result = np.concatenate(front_chunks, axis=0)
            if result.shape[0] > target_frames:
                excess = result[target_frames:]
                result = result[:target_frames]
                self._chunks.appendleft(excess)
                self._total_frames += excess.shape[0]
            return result

    @property
    def duration(self) -> float:
        return self._total_frames / self._sr


class _LiveStreamState:
    """Utterance-aware live stream state used for STT and audio meters."""

    def __init__(self, sample_rate: int, channels: int, fallback_name: str):
        self._fallback_name = fallback_name
        self._sr = sample_rate
        self._pre_roll = _RingBuffer(_PRE_ROLL_SEC, sample_rate, channels)
        self._utterance = _RingBuffer(_MAX_UTTERANCE_SEC, sample_rate, channels)
        self._lock = threading.Lock()
        now = time.monotonic()
        self._utterance_open = False
        self._last_voice_at = now
        self._last_level_at = now
        self._level = 0.0
        self._device_name = fallback_name

    def set_device_name(self, name: str) -> None:
        with self._lock:
            self._device_name = (name or self._fallback_name).strip() or self._fallback_name

    def record_chunk(self, data: np.ndarray) -> None:
        """Append one chunk, preserving short lead-in audio for new utterances."""
        now = time.monotonic()
        rms, peak = _chunk_energy(data)
        level = _meter_level(rms, peak)
        has_voice = _has_voice_signal(rms, peak)

        with self._lock:
            if has_voice and not self._utterance_open:
                # If the previous seal left an overlap tail in the buffer, use it
                # as the lead-in instead of clearing and re-adding only the pre-roll.
                # This ensures tail words cut by the VAD get a second chance.
                if self._utterance.duration == 0:
                    pre_roll = self._pre_roll.snapshot_recent(_PRE_ROLL_SEC)
                    if pre_roll is not None and pre_roll.size:
                        self._utterance.append(pre_roll)
                self._utterance_open = True

            self._pre_roll.append(data.copy())
            if has_voice:
                self._last_voice_at = now
            self._level = max(level, self._level + ((level - self._level) * _LEVEL_SMOOTHING))
            self._last_level_at = now
            if self._utterance_open:
                self._utterance.append(data.copy())

    def snapshot_live(self, now: float) -> tuple[np.ndarray | None, float, bool]:
        """Return the active utterance buffer without clearing it."""
        with self._lock:
            silence = max(0.0, now - self._last_voice_at)
            is_open = self._utterance_open
        if not is_open:
            return None, silence, False
        return self._utterance.snapshot_all(), silence, True

    def snapshot_recent_live(self, now: float, max_seconds: float) -> tuple[np.ndarray | None, float, bool]:
        """Return only the most recent *max_seconds* of the active utterance.

        Used for low-latency live draft updates — keeps Whisper processing time
        bounded regardless of utterance length.
        """
        with self._lock:
            silence = max(0.0, now - self._last_voice_at)
            is_open = self._utterance_open
        if not is_open:
            return None, silence, False
        return self._utterance.snapshot_recent(max_seconds), silence, True

    @property
    def utterance_duration(self) -> float:
        """Current utterance length in seconds (0 when closed)."""
        with self._lock:
            if not self._utterance_open:
                return 0.0
            return self._utterance.duration

    def force_version(self, keep_seconds: float) -> np.ndarray | None:
        """Split off the front of a long utterance for committed transcription.

        The utterance stays open with approximately *keep_seconds* of audio
        remaining as overlap context for the next transcription cycle.
        Returns the removed front portion, or None if not enough audio.
        """
        with self._lock:
            if not self._utterance_open:
                return None
            dur = self._utterance.duration
            split_sec = dur - keep_seconds
            if split_sec <= 0:
                return None
            return self._utterance.split_front(split_sec)

    def is_idle_ready(self, min_silence_sec: float) -> bool:
        """Return True when the utterance is open and silence threshold is reached.

        For long utterances (> _AUTO_SEAL_AFTER_SEC) a shorter silence threshold
        is used so they get segmented at natural pauses rather than growing
        indefinitely.
        """
        with self._lock:
            if not self._utterance_open:
                return False
            silence = max(0.0, time.monotonic() - self._last_voice_at)
            effective = (
                _AUTO_SEAL_SILENCE_SEC
                if self._utterance.duration > _AUTO_SEAL_AFTER_SEC
                else min_silence_sec
            )
            return silence >= effective

    def seal_if_idle(self, now: float, min_silence_sec: float) -> tuple[np.ndarray | None, float, bool]:
        """Close and return the current utterance once it has gone idle.

        Instead of fully clearing the buffer, the last _SEAL_OVERLAP_SEC seconds
        of audio are retained as the lead-in for the next utterance so that
        tail words clipped by the VAD can be re-transcribed with more context.

        For long utterances (> _AUTO_SEAL_AFTER_SEC) a shorter silence threshold
        is used so they get segmented at natural pauses.
        """
        with self._lock:
            silence = max(0.0, now - self._last_voice_at)
            if not self._utterance_open:
                return None, silence, False
            effective = (
                _AUTO_SEAL_SILENCE_SEC
                if self._utterance.duration > _AUTO_SEAL_AFTER_SEC
                else min_silence_sec
            )
            if silence < effective:
                return None, silence, False
            frames = self._utterance.snapshot_all()
            # Keep an overlap tail — do NOT fully clear the buffer.
            overlap_n = int(_SEAL_OVERLAP_SEC * self._sr)
            self._utterance.clear()
            if frames is not None and frames.shape[0] > overlap_n:
                self._utterance.append(frames[-overlap_n:])
            self._utterance_open = False
        return frames, silence, True

    def meter_snapshot(self) -> dict[str, float | str | bool]:
        """Return UI-friendly meter data for the current stream."""
        with self._lock:
            level = self._level
            last_level_at = self._last_level_at
            device_name = self._device_name
            active = self._utterance_open
        elapsed = time.monotonic() - last_level_at
        decayed_level = max(0.0, level - (elapsed * _LEVEL_DECAY_PER_SEC))
        return {
            "device_name": device_name,
            "level": min(1.0, decayed_level),
            "active": active,
        }


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
        self._transcribe_fn = transcribe_fn  # callable(audio_frames, sample_rate) -> str
        self._on_transcript = on_transcript  # callable(input_text, output_text)
        self._input_live_state = _LiveStreamState(sample_rate, channels, "Microphone")
        self._output_live_state = _LiveStreamState(sample_rate, channels, "System Audio")
        self._transcript_input = ""
        self._transcript_output = ""
        self._draft_input = ""
        self._draft_output = ""
        self._transcript_lock = threading.Lock()
        self._draft_input_started_at: float | None = None
        self._draft_output_started_at: float | None = None
        # Last committed utterance text per stream — used to deduplicate the
        # overlap tail that is re-transcribed at the start of each new window.
        self._last_committed_input = ""
        self._last_committed_output = ""
        # Segment-based committed storage for dual-quality (fast + clean) pipeline.
        self._segments_input: list[_CommittedSegment] = []
        self._segments_output: list[_CommittedSegment] = []
        self._backup_executor: "ThreadPoolExecutor | None" = None

        self._running = False
        self._mic_thread: threading.Thread | None = None
        self._loopback_thread: threading.Thread | None = None
        self._transcription_thread: threading.Thread | None = None
        self._capture_input = AUDIO_SOURCE in ("me", "both")
        self._capture_output = AUDIO_SOURCE in ("other", "both")
        # Event that fires immediately when silence crosses the commit threshold.
        # This lets the transcription loop wake up without waiting the full interval.
        self._transcription_trigger = threading.Event()

    # ── lifecycle ───────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True

        if self._capture_input:
            self._mic_thread = threading.Thread(
                target=self._record_mic, daemon=True, name="mic-capture"
            )
            self._mic_thread.start()

        if self._capture_output:
            self._loopback_thread = threading.Thread(
                target=self._record_loopback, daemon=True, name="loopback-capture"
            )
            self._loopback_thread.start()

        if self._transcribe_fn:
            self._transcription_thread = threading.Thread(
                target=self._transcription_loop, daemon=True, name="transcription"
            )
            self._transcription_thread.start()
            logger.info("Real-time transcription enabled (interval=%ds).", TRANSCRIPTION_INTERVAL)

        logger.info(
            "Continuous capture started (source=%s, ring=%ds, sr=%d, chunk=%.0fms).",
            AUDIO_SOURCE,
            self.ring_seconds,
            self.sample_rate,
            _CHUNK_SEC * 1000,
        )

    def stop(self) -> None:
        self._running = False
        self._transcription_trigger.set()  # unblock the loop if waiting
        for t in (self._mic_thread, self._loopback_thread, self._transcription_thread):
            if t and t.is_alive():
                t.join(timeout=3)
        if self._backup_executor is not None:
            self._backup_executor.shutdown(wait=False)
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
            if not self._capture_input:
                return
            mic = get_selected_microphone(AUDIO_INPUT_DEVICE_ID)
            if mic is None:
                logger.warning("No microphone device available — your audio will not be recorded.")
                return
            logger.info("Mic device: %s", mic.name)
            self._input_live_state.set_device_name(mic.name)
            chunk_frames = int(self.sample_rate * _CHUNK_SEC)
            with mic.recorder(
                samplerate=self.sample_rate, channels=self.channels
            ) as rec:
                while self._running:
                    data = rec.record(numframes=chunk_frames)
                    self._input_buf.append(data)
                    self._input_live_state.record_chunk(data)
                    if self._transcribe_fn and self._input_live_state.is_idle_ready(_SILENCE_COMMIT_SEC):
                        self._transcription_trigger.set()
        except Exception:
            logger.exception("Microphone capture failed.")

    def _record_loopback(self) -> None:
        """Continuously record system audio via WASAPI loopback."""
        try:
            if not self._capture_output:
                return
            speaker = get_selected_speaker(AUDIO_OUTPUT_DEVICE_ID)
            if speaker is None:
                logger.warning("No output device available — meeting audio will not be recorded.")
                return
            loopback = sc.get_microphone(
                speaker.id, include_loopback=True
            )
            logger.info("Loopback device: %s", loopback.name)
            self._output_live_state.set_device_name(speaker.name)
            chunk_frames = int(self.sample_rate * _CHUNK_SEC)
            with loopback.recorder(
                samplerate=self.sample_rate, channels=self.channels
            ) as rec:
                while self._running:
                    data = rec.record(numframes=chunk_frames)
                    self._output_buf.append(data)
                    self._output_live_state.record_chunk(data)
                    if self._transcribe_fn and self._output_live_state.is_idle_ready(_SILENCE_COMMIT_SEC):
                        self._transcription_trigger.set()
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

    def get_audio_levels(self) -> dict[str, dict[str, float | str | bool]]:
        """Return current audio meter data for the captured streams."""
        levels: dict[str, dict[str, float | str | bool]] = {}
        if self._capture_output:
            levels["output"] = self._output_live_state.meter_snapshot()
        if self._capture_input:
            levels["input"] = self._input_live_state.meter_snapshot()
        return levels

    # ── real-time transcription ─────────────────────────────────────────

    def _update_stream_transcript(
        self,
        stream: str,
        live_text: str,
        silence_seconds: float,
        now: float,
        *,
        force_commit: bool = False,
        audio_for_backup: np.ndarray | None = None,
    ) -> bool:
        """Update committed/draft transcript state for one audio stream."""
        if stream == "input":
            transcript_attr = "_transcript_input"
            draft_attr = "_draft_input"
            started_attr = "_draft_input_started_at"
            last_committed_attr = "_last_committed_input"
        else:
            transcript_attr = "_transcript_output"
            draft_attr = "_draft_output"
            started_attr = "_draft_output_started_at"
            last_committed_attr = "_last_committed_output"

        changed = False
        incoming = live_text.strip()

        with self._transcript_lock:
            draft = getattr(self, draft_attr)
            if incoming:
                updated_draft = incoming if force_commit else _stabilize_draft_text(draft, incoming)
                if updated_draft != draft:
                    setattr(self, draft_attr, updated_draft)
                    draft = updated_draft
                    changed = True
                if getattr(self, started_attr) is None:
                    setattr(self, started_attr, now)

            draft = getattr(self, draft_attr)
            if not draft:
                setattr(self, started_attr, None)
                return changed

            should_commit = force_commit or silence_seconds >= _SILENCE_COMMIT_SEC
            if not should_commit and silence_seconds >= _PUNCTUATION_COMMIT_SEC:
                should_commit = _ends_sentence(draft)

            if should_commit:
                transcript = getattr(self, transcript_attr)
                last_committed = getattr(self, last_committed_attr)
                # Strip any overlap already committed in the previous utterance
                # so words at the tail don't appear twice in the transcript.
                commit_text = (
                    _extract_incremental_text(last_committed, draft)
                    if last_committed else draft
                )
                if commit_text:
                    transcript = _append_committed_text(transcript, commit_text)
                    setattr(self, transcript_attr, transcript)
                    # Also store as a segment for backup pipeline.
                    seg_list = self._segments_input if stream == "input" else self._segments_output
                    seg = _CommittedSegment(commit_text, audio=audio_for_backup, sample_rate=self.sample_rate)
                    seg_list.append(seg)
                setattr(self, last_committed_attr, draft)
                setattr(self, draft_attr, "")
                setattr(self, started_attr, None)
                changed = True

        return changed

    def _current_transcripts(self) -> tuple[str, str]:
        """Return committed transcripts with any active in-progress drafts."""
        with self._transcript_lock:
            committed_in = _rebuild_from_segments(self._segments_input) if self._segments_input else self._transcript_input
            committed_out = _rebuild_from_segments(self._segments_output) if self._segments_output else self._transcript_output
            return (
                _compose_transcript(committed_in, self._draft_input),
                _compose_transcript(committed_out, self._draft_output),
            )

    def _submit_backup(self, segment: _CommittedSegment) -> None:
        """Submit a clean (beam_size=3) re-transcription of a committed segment."""
        if not self._transcribe_fn or segment.audio is None:
            return
        if self._backup_executor is None:
            from concurrent.futures import ThreadPoolExecutor
            self._backup_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="whisper-backup")
        self._backup_executor.submit(self._apply_backup, segment)

    def _apply_backup(self, segment: _CommittedSegment) -> None:
        """Re-transcribe with full quality and swap in the clean text."""
        try:
            try:
                clean = self._transcribe_fn(segment.audio, segment.sample_rate, fast=False)
            except TypeError:
                clean = self._transcribe_fn(segment.audio, segment.sample_rate)
            if not clean:
                return
            with self._transcript_lock:
                segment.clean_text = clean
                # Free the audio — no longer needed.
                segment.audio = None
                # Rebuild committed strings from segments so _compose_transcript
                # picks up the clean version.
                self._transcript_input = _rebuild_from_segments(self._segments_input)
                self._transcript_output = _rebuild_from_segments(self._segments_output)
            if self._on_transcript:
                input_text, output_text = self._current_transcripts()
                self._on_transcript(input_text, output_text)
        except Exception:
            logger.exception("Backup transcription failed.")

    def _has_active_utterance(self) -> bool:
        """Return True when at least one stream has an open utterance."""
        if AUDIO_SOURCE in ("me", "both") and self._input_live_state.utterance_duration > 0:
            return True
        if AUDIO_SOURCE in ("other", "both") and self._output_live_state.utterance_duration > 0:
            return True
        return False

    def _transcription_loop(self) -> None:
        """Continuously transcribe active utterances with minimal delay.

        When speech is active the loop runs as fast as Whisper can keep up —
        no fixed interval sleep.  A short minimum gap (_MIN_DRAFT_INTERVAL_SEC)
        prevents CPU spin when Whisper is very fast on tiny chunks.  When idle
        (no open utterance) the loop sleeps up to TRANSCRIPTION_INTERVAL or
        until the trigger event fires.

        Long utterances are handled by a versioned pipeline: once an utterance
        exceeds _VERSION_AFTER_SEC the front is split off and committed while a
        short overlap tail stays in the buffer.  Each Whisper call stays bounded
        (~10 s) regardless of how long someone speaks.
        """
        from concurrent.futures import ThreadPoolExecutor

        _MIN_DRAFT_INTERVAL_SEC = 0.3   # floor between back-to-back drafts

        executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="whisper")
        last_transcribe_at = 0.0

        while self._running:
            # When speech is active, only wait the minimum gap so drafts update
            # as fast as Whisper can process.  When idle, sleep the full interval
            # or until the trigger fires (silence-commit detected).
            if self._has_active_utterance():
                elapsed = time.monotonic() - last_transcribe_at
                gap = max(0, _MIN_DRAFT_INTERVAL_SEC - elapsed)
                if gap > 0:
                    self._transcription_trigger.wait(timeout=gap)
                    self._transcription_trigger.clear()
            else:
                self._transcription_trigger.wait(timeout=TRANSCRIPTION_INTERVAL)
                self._transcription_trigger.clear()

            if not self._running:
                break
            now = time.monotonic()

            stream_windows: dict[str, tuple[np.ndarray | None, float, bool]] = {}
            any_versioned = False

            if AUDIO_SOURCE in ("me", "both"):
                input_frames, input_silence, input_sealed = self._input_live_state.seal_if_idle(
                    now,
                    _SILENCE_COMMIT_SEC,
                )
                if input_sealed:
                    stream_windows["input"] = (input_frames, input_silence, True)
                elif self._input_live_state.utterance_duration > _VERSION_AFTER_SEC:
                    version_frames = self._input_live_state.force_version(_VERSION_OVERLAP_SEC)
                    if version_frames is not None:
                        stream_windows["input"] = (version_frames, 0.0, True)
                        any_versioned = True
                else:
                    input_frames, input_silence, input_open = self._input_live_state.snapshot_live(now)
                    if input_open:
                        stream_windows["input"] = (input_frames, input_silence, False)

            if AUDIO_SOURCE in ("other", "both"):
                output_frames, output_silence, output_sealed = self._output_live_state.seal_if_idle(
                    now,
                    _SILENCE_COMMIT_SEC,
                )
                if output_sealed:
                    stream_windows["output"] = (output_frames, output_silence, True)
                elif self._output_live_state.utterance_duration > _VERSION_AFTER_SEC:
                    version_frames = self._output_live_state.force_version(_VERSION_OVERLAP_SEC)
                    if version_frames is not None:
                        stream_windows["output"] = (version_frames, 0.0, True)
                        any_versioned = True
                else:
                    output_frames, output_silence, output_open = self._output_live_state.snapshot_live(now)
                    if output_open:
                        stream_windows["output"] = (output_frames, output_silence, False)

            if not stream_windows:
                continue

            def _do_transcribe(stream: str, frames: np.ndarray | None, fast: bool = False) -> str:
                if frames is None:
                    return ""
                try:
                    return self._transcribe_fn(frames, self.sample_rate, fast=fast)
                except TypeError:
                    return self._transcribe_fn(frames, self.sample_rate)
                except Exception:
                    logger.exception("Background %s transcription failed.", stream)
                    return ""

            futures = {}
            results: dict[str, str] = {}
            for stream, (frames, _silence, sealed) in stream_windows.items():
                if _is_transcribable_window(frames, self.sample_rate, allow_short=sealed):
                    # Drafts use fast mode (beam_size=1); sealed commits use
                    # full quality (beam_size=3) — backup will refine later.
                    futures[stream] = executor.submit(_do_transcribe, stream, frames, not sealed)
                else:
                    results[stream] = ""

            for stream, future in futures.items():
                results[stream] = future.result()
            last_transcribe_at = time.monotonic()

            # If Whisper took a while for a live draft and a seal is now ready,
            # discard the stale draft result and immediately process the seal.
            stale = False
            for stream, (frames, _silence, sealed) in stream_windows.items():
                if sealed:
                    continue
                state = self._input_live_state if stream == "input" else self._output_live_state
                if state.is_idle_ready(_SILENCE_COMMIT_SEC):
                    stale = True
                    break
            if stale:
                self._transcription_trigger.set()
                continue

            changed = False
            if "input" in stream_windows:
                _frames, input_silence, input_sealed = stream_windows["input"]
                changed = self._update_stream_transcript(
                    "input",
                    results.get("input", ""),
                    input_silence,
                    now,
                    force_commit=input_sealed,
                    audio_for_backup=_frames if input_sealed else None,
                ) or changed
            if "output" in stream_windows:
                _frames, output_silence, output_sealed = stream_windows["output"]
                changed = self._update_stream_transcript(
                    "output",
                    results.get("output", ""),
                    output_silence,
                    now,
                    force_commit=output_sealed,
                    audio_for_backup=_frames if output_sealed else None,
                ) or changed

            # Submit backup (clean/beam_size=3) for newly committed segments
            # that haven't been submitted yet.
            # On CUDA, skip backup entirely — full quality is already real-time.
            if LOCAL_WHISPER_DEVICE != "cuda":
                for seg_list in (self._segments_input, self._segments_output):
                    for seg in seg_list:
                        if not seg._backup_submitted and seg.audio is not None:
                            seg._backup_submitted = True
                            self._submit_backup(seg)

            if changed and self._on_transcript:
                input_text, output_text = self._current_transcripts()
                self._on_transcript(input_text, output_text)

        executor.shutdown(wait=False)

    def get_transcript(self) -> tuple[str, str]:
        """Return accumulated transcript (input, output) without clearing."""
        return self._current_transcripts()

    def clear_transcript(self) -> tuple[str, str]:
        """Return and clear accumulated transcript."""
        with self._transcript_lock:
            result = (
                _compose_transcript(
                    _rebuild_from_segments(self._segments_input) if self._segments_input else self._transcript_input,
                    self._draft_input,
                ),
                _compose_transcript(
                    _rebuild_from_segments(self._segments_output) if self._segments_output else self._transcript_output,
                    self._draft_output,
                ),
            )
            self._transcript_input = ""
            self._transcript_output = ""
            self._draft_input = ""
            self._draft_output = ""
            self._draft_input_started_at = None
            self._draft_output_started_at = None
            self._last_committed_input = ""
            self._last_committed_output = ""
            self._segments_input.clear()
            self._segments_output.clear()
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
