"""
Speech-to-text backend selection and xAI integration.

The rest of the application should call this module instead of talking directly
to a specific STT engine.
"""

import io
import json
import logging
import uuid
import wave
from urllib import error, request

import numpy as np

import settings as _settings_store
from config import (
    STT_PROVIDER,
    XAI_API_KEY,
    XAI_STT_ENDPOINT,
    XAI_STT_FORMAT_TEXT,
    XAI_STT_TIMEOUT_SECONDS,
)
from local_transcriber import transcribe_local
from transcript_filters import filter_transcript_text

logger = logging.getLogger(__name__)

_SUPPORTED_PROVIDERS = {"auto", "local", "xai"}
_MIN_TRANSCRIBE_RMS = 0.005
_MIN_TRANSCRIBE_PEAK = 0.02


def _active_language() -> str:
    """Return the current transcription language, read fresh from settings on each call.

    Reading from settings.get() (not the module-level config constant) ensures that
    a language change saved through the settings UI takes effect on the next
    transcription without requiring an application restart.
    """
    lang = (_settings_store.get("STT_LANGUAGE") or "").strip()
    return lang if lang else "en"


def _normalize_provider_name(provider: str | None) -> str:
    normalized = (provider or "auto").strip().lower()
    if normalized in _SUPPORTED_PROVIDERS:
        return normalized
    logger.warning("Unknown STT provider '%s'; falling back to auto.", provider)
    return "auto"


def get_active_stt_provider(provider: str | None = None) -> str:
    """Resolve the active STT backend after applying auto-selection rules."""
    selected = _normalize_provider_name(provider or STT_PROVIDER)
    if selected == "auto":
        return "xai" if XAI_API_KEY else "local"
    return selected


def describe_active_stt_provider(provider: str | None = None) -> str:
    """Return a user-facing description of the active STT backend."""
    active = get_active_stt_provider(provider)
    if active == "xai":
        return "xAI Speech-to-Text"
    return "Local faster-whisper"


def _normalize_audio_array(audio: np.ndarray) -> np.ndarray:
    normalized = audio
    if normalized.ndim > 1:
        normalized = normalized.mean(axis=1)
    if normalized.dtype != np.float32:
        if normalized.dtype == np.int16:
            normalized = normalized.astype(np.float32) / 32768.0
        else:
            normalized = normalized.astype(np.float32)
    return np.clip(normalized, -1.0, 1.0)


def _audio_has_speech(audio: np.ndarray) -> bool:
    if audio.size == 0:
        return False
    rms = float(np.sqrt(np.mean(audio ** 2)))
    peak = float(np.max(np.abs(audio)))
    return rms >= _MIN_TRANSCRIBE_RMS or peak >= _MIN_TRANSCRIBE_PEAK


def _audio_array_to_wav_bytes(audio: np.ndarray, sample_rate: int) -> bytes:
    pcm_audio = (_normalize_audio_array(audio) * 32767).clip(-32768, 32767).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_audio.tobytes())
    return buffer.getvalue()


def _wav_bytes_to_audio_array(wav_bytes: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        raw_frames = wav_file.readframes(wav_file.getnframes())

    if sample_width != 2:
        raise ValueError(f"Unsupported WAV sample width: {sample_width * 8} bits")

    audio = np.frombuffer(raw_frames, dtype=np.int16)
    if channels > 1:
        audio = audio.reshape(-1, channels)
    return audio.astype(np.float32) / 32768.0, sample_rate


def _build_xai_request_body(wav_bytes: bytes, language: str) -> tuple[bytes, str]:
    boundary = f"----HelpAIBoundary{uuid.uuid4().hex}"
    body = io.BytesIO()

    def write_text_field(name: str, value: str) -> None:
        body.write(f"--{boundary}\r\n".encode("utf-8"))
        body.write(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        body.write(value.encode("utf-8"))
        body.write(b"\r\n")

    lang = language.strip()
    if lang:
        if XAI_STT_FORMAT_TEXT:
            write_text_field("format", "true")
        write_text_field("language", lang)

    body.write(f"--{boundary}\r\n".encode("utf-8"))
    body.write(b'Content-Disposition: form-data; name="file"; filename="recording.wav"\r\n')
    body.write(b"Content-Type: audio/wav\r\n\r\n")
    body.write(wav_bytes)
    body.write(b"\r\n")
    body.write(f"--{boundary}--\r\n".encode("utf-8"))
    return body.getvalue(), boundary


def _transcribe_with_xai(wav_bytes: bytes, language: str = "en") -> str:
    if not XAI_API_KEY:
        raise RuntimeError(
            "XAI_API_KEY is not configured. Set it in settings or the environment before "
            "using the xAI STT backend."
        )

    body, boundary = _build_xai_request_body(wav_bytes, language)
    request_object = request.Request(XAI_STT_ENDPOINT, data=body, method="POST")
    request_object.add_header("Authorization", f"Bearer {XAI_API_KEY}")
    request_object.add_header("Accept", "application/json")
    request_object.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")

    try:
        with request.urlopen(request_object, timeout=XAI_STT_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace").strip()
        reason = details or exc.reason
        raise RuntimeError(f"xAI STT request failed ({exc.code}): {reason}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"xAI STT request failed: {exc.reason}") from exc

    transcript = filter_transcript_text(str(payload.get("text", "")))
    logger.info(
        "xAI transcription complete (%d chars, duration=%ss).",
        len(transcript),
        payload.get("duration", "?"),
    )
    return transcript


def _use_local_fallback_on_error(provider: str | None) -> bool:
    return _normalize_provider_name(provider or STT_PROVIDER) == "auto"


def transcribe_audio_array(audio: np.ndarray, sample_rate: int = 16000, provider: str | None = None) -> str:
    """Transcribe an in-memory audio buffer with the configured STT backend."""
    normalized_audio = _normalize_audio_array(audio)
    if not _audio_has_speech(normalized_audio):
        return ""

    lang = _active_language()
    active_provider = get_active_stt_provider(provider)
    if active_provider == "local":
        return transcribe_local(normalized_audio, sample_rate, language=lang)

    try:
        return _transcribe_with_xai(_audio_array_to_wav_bytes(normalized_audio, sample_rate), language=lang)
    except Exception:
        if not _use_local_fallback_on_error(provider):
            raise
        logger.exception("xAI STT failed; falling back to local faster-whisper.")
        return transcribe_local(normalized_audio, sample_rate, language=lang)


def transcribe_wav_bytes(wav_bytes: bytes, provider: str | None = None) -> str:
    """Transcribe a WAV payload with the configured STT backend."""
    lang = _active_language()
    active_provider = get_active_stt_provider(provider)
    if active_provider == "xai":
        try:
            return _transcribe_with_xai(wav_bytes, language=lang)
        except Exception:
            if not _use_local_fallback_on_error(provider):
                raise
            logger.exception("xAI STT failed; falling back to local faster-whisper.")

    audio, sample_rate = _wav_bytes_to_audio_array(wav_bytes)
    return transcribe_audio_array(audio, sample_rate=sample_rate, provider="local")