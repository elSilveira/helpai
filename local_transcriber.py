"""
Local real-time transcription using faster-whisper (CTranslate2).

Runs Whisper locally on the CPU — no API calls needed for transcription.
The model is downloaded once from Hugging Face on first use.
"""

import io
import logging
import threading
import wave

import numpy as np
from faster_whisper import WhisperModel

from config import LOCAL_WHISPER_MODEL, LOCAL_WHISPER_DEVICE, LOCAL_WHISPER_COMPUTE

logger = logging.getLogger(__name__)

_model: WhisperModel | None = None
_model_lock = threading.Lock()


def _get_model() -> WhisperModel:
    """Lazy-load the local Whisper model (thread-safe, singleton)."""
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        logger.info(
            "Loading local Whisper model '%s' (device=%s, compute=%s)…",
            LOCAL_WHISPER_MODEL, LOCAL_WHISPER_DEVICE, LOCAL_WHISPER_COMPUTE,
        )
        _model = WhisperModel(
            LOCAL_WHISPER_MODEL,
            device=LOCAL_WHISPER_DEVICE,
            compute_type=LOCAL_WHISPER_COMPUTE,
        )
        logger.info("Local Whisper model loaded.")
    return _model


# Known Whisper silence hallucinations
_HALLUCINATION_EXACT: set[str] = {
    "thank you", "thank you.", "thanks.", "thanks",
    "thank you for watching", "thank you for watching.",
    "thanks for watching", "thanks for watching.",
    "like and subscribe", "please subscribe",
    "subscribe", "bye.", "bye", "you",
    "ご視聴ありがとうございました", "ご視聴ありがとうございました。",
    "谢谢观看", "谢谢观看。", "字幕由amara.org社区提供",
    "시청해주셔서 감사합니다", "시청해 주셔서 감사합니다",
    "grazie", "grazie.", "grazie per la visione",
    "gracias", "gracias.", "gracias por ver",
    "obrigado", "obrigado.", "obrigada.",
    "danke", "danke.", "danke fürs zuschauen",
    "merci", "merci.", "merci d'avoir regardé",
    "شكرا للمشاهدة",
    "!", ".", "...", "…", "♪", "♪♪", "♪♪♪",
    "music", "[music]", "(music)",
}

_TECHNICAL_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (r"\btype script\b", "TypeScript"),
    (r"\bthat to extend\b", "TypeScript"),
    (r"\bjava script\b", "JavaScript"),
    (r"\bgraph q l\b", "GraphQL"),
    (r"\bgraph ql\b", "GraphQL"),
    (r"\bnode js\b", "Node.js"),
)


def _is_hallucination(text: str) -> bool:
    """Return True if the text is a known Whisper hallucination."""
    import re
    t = text.strip()
    if not t:
        return True
    if t.lower() in {h.lower() for h in _HALLUCINATION_EXACT}:
        return True
    # Repeated words: "you you you you"
    if re.match(r'^(\w+)(\s+\1){2,}$', t, re.IGNORECASE):
        return True
    # Repeated phrases: "I don't know I don't know I don't know"
    words = t.split()
    if len(words) >= 6:
        for phrase_len in range(2, min(8, len(words) // 2 + 1)):
            phrase = ' '.join(words[:phrase_len]).lower()
            count = 0
            i = 0
            while i <= len(words) - phrase_len:
                chunk = ' '.join(words[i:i + phrase_len]).lower()
                if chunk == phrase:
                    count += 1
                    i += phrase_len
                else:
                    break
            if count >= 3 and count * phrase_len >= len(words) * 0.6:
                return True
    # Only punctuation / whitespace / music symbols
    stripped = re.sub(r'[\s.,!?;:\-–—…♪()[\]]+', '', t)
    if len(stripped) <= 2:
        return True
    return False


def _is_low_quality_segment(seg) -> bool:
    """Filter out low-confidence or suspiciously short segments."""
    text = seg.text.strip()
    words = text.split()
    # Very short fragments (1-2 words) need high confidence
    if len(words) <= 2 and seg.avg_logprob < -0.5:
        return True
    # Any segment with very low confidence
    if seg.avg_logprob < -0.8:
        return True
    # High no-speech probability on the segment
    if seg.no_speech_prob > 0.5:
        return True
    # Very short duration with few words — likely noise
    duration = seg.end - seg.start
    if duration < 0.5 and len(words) <= 2:
        return True
    return False


def _normalize_transcript_text(text: str) -> str:
    """Normalize common technical terms that Whisper often splits or mangles."""
    import re

    normalized = text
    for pattern, replacement in _TECHNICAL_REPLACEMENTS:
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def transcribe_local(audio: np.ndarray, sample_rate: int = 16000) -> str:
    """Transcribe a numpy audio array using the local Whisper model.

    Args:
        audio: float32 numpy array of audio samples (mono, 16kHz expected).
        sample_rate: Sample rate of the audio.

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
    if rms < 0.01:
        return ""

    model = _get_model()
    segments, info = model.transcribe(
        audio,
        beam_size=3,
        language="en",
        condition_on_previous_text=False,
        no_speech_threshold=0.6,
        log_prob_threshold=-1.0,
        compression_ratio_threshold=1.8,      # stricter than default 2.4 — catches hallucinated repetition
        repetition_penalty=1.5,               # penalize repeated tokens
        no_repeat_ngram_size=3,               # block repeated 3-grams
        hallucination_silence_threshold=1.0,  # skip segments in silence gaps >1s
        vad_filter=True,
        vad_parameters=dict(
            min_silence_duration_ms=300,
            speech_pad_ms=250,
        ),
        hotwords=(
            "TypeScript JavaScript React Python API GraphQL REST Docker "
            "Kubernetes AWS database SQL Node.js Git CI/CD deployment "
            "microservices frontend backend endpoint component"
        ),
    )

    parts = []
    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue
        if _is_hallucination(text):
            logger.debug("Filtered hallucination: '%s'", text)
            continue
        if _is_low_quality_segment(seg):
            logger.debug("Filtered low-quality (logprob=%.2f, no_speech=%.2f): '%s'",
                         seg.avg_logprob, seg.no_speech_prob, text)
            continue
        parts.append(text)

    return _normalize_transcript_text(" ".join(parts))
