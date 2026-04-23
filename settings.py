"""
User-editable settings persistence.

Stores settings next to the executable for frozen builds, keeps repo-local
settings during development, and uses %APPDATA%\\HelpAI for pip-installed copies.
"""

import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _is_installed_copy(base_dir: Path) -> bool:
    return any(part.lower() in {"site-packages", "dist-packages"} for part in base_dir.parts)


def _resolve_base_dir() -> Path:
    override = os.environ.get("HELPAI_SETTINGS_DIR", "").strip()
    if override:
        return Path(override).expanduser()

    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent

    module_dir = Path(__file__).resolve().parent
    if _is_installed_copy(module_dir):
        appdata = os.environ.get("APPDATA", "").strip()
        if appdata:
            return Path(appdata) / "HelpAI"
        return Path.home() / ".helpai"

    return module_dir


_base_dir = _resolve_base_dir()

SETTINGS_FILE = _base_dir / "settings.json"

# Keys that can be customised by the user
DEFAULTS = {
    "HOTKEY_AUDIO_ANALYSIS": "ctrl+shift+d",
    "HOTKEY_SCREENSHOT_FEEDBACK": "ctrl+shift+e",
    "HOTKEY_QUICK_INPUT": "ctrl+shift+enter",
    "HOTKEY_SHOW_CONVERSATION": "ctrl+shift+s",
    "AUDIO_CAPTURE_ENABLED": True,
    "SCREENSHOT_FEEDBACK_ENABLED": True,
    "INSIGHT_OVERLAY_OPACITY": 0.88,
    "AUDIO_CHUNK_DURATION": 30,
    "AUDIO_RING_BUFFER_SECONDS": 120,
    "TRANSCRIPTION_INTERVAL": 3,
    "OPENAI_API_KEY": "",
    "OPENAI_MODEL": "gpt-4o",
    "STT_PROVIDER": "auto",
    "XAI_API_KEY": "",
    "STT_LANGUAGE": "en",
    "XAI_STT_LANGUAGE": "en",
    "XAI_STT_FORMAT_TEXT": True,
    "XAI_STT_TIMEOUT_SECONDS": 30,
    "AUDIO_SOURCE": "other",
    "AUDIO_INPUT_DEVICE_ID": "",
    "AUDIO_OUTPUT_DEVICE_ID": "",
    "LOCAL_WHISPER_MODEL": "large-v3-turbo",
    "LOCAL_WHISPER_DEVICE": "auto",
}

_cache: dict | None = None


def load() -> dict:
    """Load settings from disk, merged with defaults."""
    global _cache
    settings = dict(DEFAULTS)
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            settings.update(saved)
            logger.info("Settings loaded from %s", SETTINGS_FILE)
        except Exception:
            logger.exception("Failed to read settings file; using defaults.")
    _cache = settings
    return settings


def save(settings: dict) -> None:
    """Persist settings to disk."""
    global _cache
    # Only save keys that differ from hard defaults or are user-editable
    to_save = {k: v for k, v in settings.items() if k in DEFAULTS}
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(to_save, f, indent=2)
    _cache = dict(DEFAULTS)
    _cache.update(to_save)
    logger.info("Settings saved to %s", SETTINGS_FILE)


def get(key: str):
    """Get a single setting value (loads from disk on first call)."""
    if _cache is None:
        load()
    return _cache.get(key, DEFAULTS.get(key))
