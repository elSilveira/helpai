"""
User-editable settings persistence.

Stores settings as a JSON file next to the executable / script.
Falls back to defaults from config.py when the file does not exist.
"""

import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# In a PyInstaller bundle, __file__ points to _MEIPASS (temp dir).
# Use the exe's directory so settings persist across restarts.
if getattr(sys, "frozen", False):
    _base_dir = Path(sys.executable).parent
else:
    _base_dir = Path(__file__).parent

SETTINGS_FILE = _base_dir / "settings.json"

# Keys that can be customised by the user
DEFAULTS = {
    "HOTKEY_AUDIO_ANALYSIS": "ctrl+d",
    "HOTKEY_SCREENSHOT_FEEDBACK": "ctrl+e",
    "HOTKEY_QUICK_INPUT": "ctrl+shift+enter",
    "AUDIO_CAPTURE_ENABLED": True,
    "SCREENSHOT_FEEDBACK_ENABLED": True,
    "INSIGHT_OVERLAY_OPACITY": 0.88,
    "AUDIO_CHUNK_DURATION": 30,
    "AUDIO_RING_BUFFER_SECONDS": 120,
    "OPENAI_API_KEY": "",
    "OPENAI_MODEL": "gpt-4o",
    "AUDIO_SOURCE": "other",
    "AUDIO_INPUT_DEVICE_ID": "",
    "AUDIO_OUTPUT_DEVICE_ID": "",
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
