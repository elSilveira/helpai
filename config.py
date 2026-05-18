"""
HelpAI — Internal QA & Training Overlay Tool
Configuration parameters (SCREAMING_SNAKE_CASE convention).

Values marked "user-overridable" are loaded from settings.json when
the launcher / settings UI has saved them.  Everything else is fixed.
"""

import os

from helpai_version import __version__ as APP_VERSION
from settings import load as _load_settings

_user = _load_settings()

# ─── General ────────────────────────────────────────────────────────────────
APP_NAME = "HelpAI"

# ─── OpenAI / LLM ──────────────────────────────────────────────────────────
LLM_TEXT_PROVIDER = (_user.get("LLM_TEXT_PROVIDER") or os.environ.get("LLM_TEXT_PROVIDER", "openai")).strip().lower()
LLM_IMAGE_PROVIDER = (_user.get("LLM_IMAGE_PROVIDER") or os.environ.get("LLM_IMAGE_PROVIDER", "openai")).strip().lower()
OPENAI_API_KEY = _user.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
OPENAI_TEXT_MODEL = _user.get("OPENAI_TEXT_MODEL") or os.environ.get("OPENAI_TEXT_MODEL", "gpt-4o")
OPENAI_IMAGE_MODEL = _user.get("OPENAI_IMAGE_MODEL") or os.environ.get("OPENAI_IMAGE_MODEL", "gpt-4o")
CODEX_MODEL = _user.get("CODEX_MODEL") or os.environ.get("CODEX_MODEL", "")
OLLAMA_BASE_URL = (_user.get("OLLAMA_BASE_URL") or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
OLLAMA_TEXT_MODEL = _user.get("OLLAMA_TEXT_MODEL") or os.environ.get("OLLAMA_TEXT_MODEL", "qwen3:8b")
OLLAMA_IMAGE_MODEL = _user.get("OLLAMA_IMAGE_MODEL") or os.environ.get("OLLAMA_IMAGE_MODEL", "gemma3:12b")
KILL_OLLAMA_ON_EXIT = _user.get("KILL_OLLAMA_ON_EXIT", False)

# ─── Speech-to-Text ────────────────────────────────────────────────────────
XAI_API_KEY = _user.get("XAI_API_KEY") or os.environ.get("XAI_API_KEY", "")
STT_PROVIDER = (_user.get("STT_PROVIDER") or os.environ.get("STT_PROVIDER", "auto")).strip().lower()
XAI_STT_ENDPOINT = os.environ.get("XAI_STT_ENDPOINT", "https://api.x.ai/v1/stt")
STT_LANGUAGE = _user.get("STT_LANGUAGE", "en")
XAI_STT_LANGUAGE = _user.get("XAI_STT_LANGUAGE", "en")
XAI_STT_FORMAT_TEXT = _user.get("XAI_STT_FORMAT_TEXT", True)
XAI_STT_TIMEOUT_SECONDS = int(_user.get("XAI_STT_TIMEOUT_SECONDS", 30))

# ─── Audio Capture ──────────────────────────────────────────────────────────
AUDIO_CAPTURE_ENABLED = _user.get("AUDIO_CAPTURE_ENABLED", True)
AUDIO_SAMPLE_RATE = 16_000          # Hz – current STT backends are tuned for 16 kHz input
AUDIO_CHANNELS = 1
AUDIO_CHUNK_DURATION = _user.get("AUDIO_CHUNK_DURATION", 30)
AUDIO_RING_BUFFER_SECONDS = _user.get("AUDIO_RING_BUFFER_SECONDS", 120)  # continuous buffer length
AUDIO_DTYPE = "int16"
TRANSCRIPTION_INTERVAL = _user.get("TRANSCRIPTION_INTERVAL", 3)  # seconds between background transcriptions
AUDIO_SOURCE = _user.get("AUDIO_SOURCE", "other")  # "other" | "me" | "both"
AUDIO_INPUT_DEVICE_ID = _user.get("AUDIO_INPUT_DEVICE_ID", "")
AUDIO_OUTPUT_DEVICE_ID = _user.get("AUDIO_OUTPUT_DEVICE_ID", "")

# ─── Local Whisper (faster-whisper) ─────────────────────────────────────────
LOCAL_WHISPER_MODEL = _user.get("LOCAL_WHISPER_MODEL", "large-v3-turbo")  # tiny.en / base.en / small.en / medium.en / large-v3-turbo
LOCAL_WHISPER_DEVICE = _user.get("LOCAL_WHISPER_DEVICE", "auto")  # "auto" / "cpu" / "cuda"

def _resolve_whisper_device(device: str) -> tuple[str, str]:
    """Resolve device and compute type. 'auto' prefers CUDA when available."""
    resolved_device = "cpu"
    resolved_compute = "int8"

    if device in ("auto", "cuda"):
        try:
            import ctranslate2
            if ctranslate2.get_cuda_device_count() > 0:
                resolved_device = "cuda"
                resolved_compute = "float16"
        except Exception:
            if device == "cuda":
                import logging
                logging.getLogger(__name__).warning(
                    "CUDA requested but not available — falling back to CPU."
                )

    # When using CUDA, ensure the pip-installed NVIDIA DLLs are discoverable.
    if resolved_device == "cuda":
        _add_nvidia_dll_paths()

    return resolved_device, resolved_compute


def _add_nvidia_dll_paths() -> None:
    """Add pip-installed NVIDIA library directories to the DLL search path."""
    import glob
    import os
    import sys

    site_packages = [p for p in sys.path if "site-packages" in p]
    for sp in site_packages:
        nvidia_dir = os.path.join(sp, "nvidia")
        if not os.path.isdir(nvidia_dir):
            continue
        bin_dirs = glob.glob(os.path.join(nvidia_dir, "*", "bin"))
        for bin_dir in bin_dirs:
            if bin_dir not in os.environ.get("PATH", ""):
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
                # Also use os.add_dll_directory on Python 3.8+ Windows
                try:
                    os.add_dll_directory(bin_dir)
                except (OSError, AttributeError):
                    pass
        break  # only need the first site-packages

LOCAL_WHISPER_DEVICE, LOCAL_WHISPER_COMPUTE = _resolve_whisper_device(LOCAL_WHISPER_DEVICE)

# ─── Screenshot / Visual Feedback ──────────────────────────────────────────
SCREENSHOT_FEEDBACK_ENABLED = _user.get("SCREENSHOT_FEEDBACK_ENABLED", True)
STEALTH_MODE = _user.get("STEALTH_MODE", True)

# ─── Overlay UI ─────────────────────────────────────────────────────────────
INSIGHT_OVERLAY_OPACITY = _user.get("INSIGHT_OVERLAY_OPACITY", 0.88)
OVERLAY_BG_COLOR = "#1e1e2e"
OVERLAY_FG_COLOR = "#cdd6f4"
OVERLAY_ACCENT_COLOR = "#89b4fa"
OVERLAY_FONT_FAMILY = "Segoe UI"
OVERLAY_FONT_SIZE = 11
OVERLAY_WIDTH = 580
OVERLAY_HEIGHT = 480
OVERLAY_PADDING = 14
OVERLAY_POSITION_X = 60             # px from right edge of primary monitor
OVERLAY_POSITION_Y = 60             # px from top edge

# ─── Hotkeys (user-overridable) ────────────────────────────────────────────
HOTKEY_AUDIO_ANALYSIS = _user.get("HOTKEY_AUDIO_ANALYSIS", "ctrl+shift+d")
HOTKEY_SCREENSHOT_FEEDBACK = _user.get("HOTKEY_SCREENSHOT_FEEDBACK", "ctrl+shift+e")
HOTKEY_QUICK_INPUT = _user.get("HOTKEY_QUICK_INPUT", "ctrl+shift+enter")
HOTKEY_SHOW_CONVERSATION = _user.get("HOTKEY_SHOW_CONVERSATION", "ctrl+shift+s")
HOTKEY_CLEAR_CONTEXT = _user.get("HOTKEY_CLEAR_CONTEXT", "ctrl+shift+x")

# ─── Visibility Control ────────────────────────────────────────────────────
# Windows Display Affinity flag to exclude window from capture APIs.
# WDA_EXCLUDEFROMCAPTURE (0x00000011) — supported on Windows 10 2004+.
WDA_EXCLUDEFROMCAPTURE = 0x00000011
