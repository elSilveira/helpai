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
OPENAI_API_KEY = _user.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = _user.get("OPENAI_MODEL") or os.environ.get("OPENAI_MODEL", "gpt-4o")

# ─── Speech-to-Text ────────────────────────────────────────────────────────
XAI_API_KEY = _user.get("XAI_API_KEY") or os.environ.get("XAI_API_KEY", "")
STT_PROVIDER = (_user.get("STT_PROVIDER") or os.environ.get("STT_PROVIDER", "auto")).strip().lower()
XAI_STT_ENDPOINT = os.environ.get("XAI_STT_ENDPOINT", "https://api.x.ai/v1/stt")
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
LOCAL_WHISPER_MODEL = _user.get("LOCAL_WHISPER_MODEL", "small.en")  # tiny.en / base.en / small.en / medium.en
LOCAL_WHISPER_DEVICE = "cpu"       # "cpu" or "cuda"
LOCAL_WHISPER_COMPUTE = "int8"     # int8 is fastest on CPU

# ─── Screenshot / Visual Feedback ──────────────────────────────────────────
SCREENSHOT_FEEDBACK_ENABLED = _user.get("SCREENSHOT_FEEDBACK_ENABLED", True)

# ─── Overlay UI ─────────────────────────────────────────────────────────────
INSIGHT_OVERLAY_OPACITY = _user.get("INSIGHT_OVERLAY_OPACITY", 0.88)
OVERLAY_BG_COLOR = "#1e1e2e"
OVERLAY_FG_COLOR = "#cdd6f4"
OVERLAY_ACCENT_COLOR = "#89b4fa"
OVERLAY_FONT_FAMILY = "Segoe UI"
OVERLAY_FONT_SIZE = 11
OVERLAY_WIDTH = 520
OVERLAY_HEIGHT = 420
OVERLAY_PADDING = 14
OVERLAY_POSITION_X = 60             # px from right edge of primary monitor
OVERLAY_POSITION_Y = 60             # px from top edge

# ─── Hotkeys (user-overridable) ────────────────────────────────────────────
HOTKEY_AUDIO_ANALYSIS = _user.get("HOTKEY_AUDIO_ANALYSIS", "ctrl+d")
HOTKEY_SCREENSHOT_FEEDBACK = _user.get("HOTKEY_SCREENSHOT_FEEDBACK", "ctrl+e")
HOTKEY_QUICK_INPUT = _user.get("HOTKEY_QUICK_INPUT", "ctrl+shift+enter")
HOTKEY_SHOW_CONVERSATION = _user.get("HOTKEY_SHOW_CONVERSATION", "ctrl+s")

# ─── Visibility Control ────────────────────────────────────────────────────
# Windows Display Affinity flag to exclude window from capture APIs.
# WDA_EXCLUDEFROMCAPTURE (0x00000011) — supported on Windows 10 2004+.
WDA_EXCLUDEFROMCAPTURE = 0x00000011
