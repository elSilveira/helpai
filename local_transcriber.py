"""
Local real-time transcription using faster-whisper (CTranslate2).

Runs Whisper locally on the CPU — no API calls needed for transcription.
The model is downloaded once from Hugging Face on first use.
"""

import logging
import threading
from typing import Any

import numpy as np

from config import LOCAL_WHISPER_MODEL, LOCAL_WHISPER_DEVICE, LOCAL_WHISPER_COMPUTE
from transcript_filters import is_hallucination, is_low_quality_segment, normalize_transcript_text

try:
    from faster_whisper import WhisperModel as _FasterWhisperModel
except ImportError as exc:
    _FasterWhisperModel = None
    _FASTER_WHISPER_IMPORT_ERROR = exc
else:
    _FASTER_WHISPER_IMPORT_ERROR = None

logger = logging.getLogger(__name__)

_model: Any = None
_model_lock = threading.Lock()
_transcribe_lock = threading.Lock()
_MIN_AUDIO_RMS = 0.005
_MIN_AUDIO_PEAK = 0.02


def _get_model():
    """Lazy-load the local Whisper model (thread-safe, singleton)."""
    global _model
    if _FasterWhisperModel is None:
        raise RuntimeError(
            "faster-whisper is not installed. Install the local STT dependencies "
            "or switch STT_PROVIDER to 'xai'."
        ) from _FASTER_WHISPER_IMPORT_ERROR
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        logger.info(
            "Loading local Whisper model '%s' (device=%s, compute=%s)…",
            LOCAL_WHISPER_MODEL, LOCAL_WHISPER_DEVICE, LOCAL_WHISPER_COMPUTE,
        )
        _model = _FasterWhisperModel(
            LOCAL_WHISPER_MODEL,
            device=LOCAL_WHISPER_DEVICE,
            compute_type=LOCAL_WHISPER_COMPUTE,
        )
        logger.info("Local Whisper model loaded.")
    return _model


def is_model_cached() -> bool:
    """Return True if the Whisper model files are already on disk (no download needed)."""
    try:
        from huggingface_hub import try_to_load_from_cache
        sentinel = try_to_load_from_cache(
            f"Systran/faster-whisper-{LOCAL_WHISPER_MODEL}", "config.json"
        )
        return sentinel is not None and sentinel is not getattr(sentinel, "_CACHED_NO_EXIST", object())
    except Exception:
        return False


def preload_model() -> None:
    """Pre-warm the Whisper model so the first transcription has no cold-start delay."""
    _get_model()


def transcribe_local(audio: np.ndarray, sample_rate: int = 16000, language: str = "en", fast: bool = False) -> str:
    """Transcribe a numpy audio array using the local Whisper model.

    Args:
        audio: float32 numpy array of audio samples (mono, 16kHz expected).
        sample_rate: Sample rate of the audio.
        language: BCP-47 language code passed to Whisper (e.g. 'en', 'es').  Use
            empty string or None to enable Whisper's own language auto-detection.
        fast: When True, use beam_size=1 for lower latency (live draft mode).
            When False (default), use beam_size=3 for higher accuracy (commits).

    Returns:
        Transcribed text, or empty string if silence/hallucination.
    """
    if audio.ndim > 1:
        audio = audio.mean(axis=1)  # stereo → mono
    if audio.dtype != np.float32:
        if audio.dtype == np.int16:
            audio = audio.astype(np.float32) / 32768.0
        else:
            audio = audio.astype(np.float32)

    # Skip near-silent audio
    rms = np.sqrt(np.mean(audio ** 2))
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if rms < _MIN_AUDIO_RMS and peak < _MIN_AUDIO_PEAK:
        return ""

    _lang = (language or "").strip() or None  # None → Whisper auto-detect

    # Hotwords are English tech terms; only inject when transcribing English.
    _hotwords = (
        "TypeScript JavaScript React Python API GraphQL REST Docker "
        "Kubernetes AWS database SQL Node.js Git CI/CD deployment "
        "microservices frontend backend endpoint component"
    ) if (_lang is None or _lang.startswith("en")) else None

    model = _get_model()
    with _transcribe_lock:
        # On GPU, always use full quality — it's fast enough for real-time.
        # On CPU, drafts use beam_size=1 for speed; commits use beam_size=3.
        if LOCAL_WHISPER_DEVICE == "cuda":
            _beam = 3
        else:
            _beam = 1 if fast else 3
        transcribe_kwargs = dict(
            beam_size=_beam,
            language=_lang,
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
            log_prob_threshold=-1.0,
            compression_ratio_threshold=1.8,
            repetition_penalty=1.5,
            no_repeat_ngram_size=3,
            hallucination_silence_threshold=1.0,
            vad_filter=True,
            vad_parameters=dict(
                min_silence_duration_ms=300,
                speech_pad_ms=250,
            ),
        )
        if _hotwords:
            transcribe_kwargs["hotwords"] = _hotwords
        segments, info = model.transcribe(audio, **transcribe_kwargs)

        # Consume the generator inside the lock — segments is lazy and does
        # GPU work during iteration, so it must stay serialized.
        parts = []
        for seg in segments:
            text = seg.text.strip()
            if not text:
                continue
            if is_hallucination(text):
                logger.debug("Filtered hallucination: '%s'", text)
                continue
            if is_low_quality_segment(seg):
                logger.debug("Filtered low-quality (logprob=%.2f, no_speech=%.2f): '%s'",
                             seg.avg_logprob, seg.no_speech_prob, text)
                continue
            parts.append(text)

    return normalize_transcript_text(" ".join(parts))
