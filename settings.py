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
    "HOTKEY_ANALYZE_SCREENSHOTS": "ctrl+shift+a",
    "HOTKEY_QUICK_INPUT": "ctrl+shift+enter",
    "HOTKEY_NOTES": "ctrl+shift+n",
    "HOTKEY_SHOW_CONVERSATION": "ctrl+shift+s",
    "HOTKEY_CLEAR_CONTEXT": "ctrl+shift+x",
    "AUDIO_CAPTURE_ENABLED": True,
    "SCREENSHOT_FEEDBACK_ENABLED": True,
    "STEALTH_MODE": True,
    "INSIGHT_OVERLAY_OPACITY": 0.88,
    "AUDIO_CHUNK_DURATION": 30,
    "AUDIO_RING_BUFFER_SECONDS": 120,
    "TRANSCRIPTION_INTERVAL": 3,
    "LLM_TEXT_PROVIDER": "openai",
    "LLM_IMAGE_PROVIDER": "openai",
    "OPENAI_API_KEY": "",
    "OPENAI_TEXT_MODEL": "gpt-4o",
    "OPENAI_IMAGE_MODEL": "gpt-4o",
    "CODEX_MODEL": "",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_TEXT_MODEL": "qwen3:8b",
    "OLLAMA_IMAGE_MODEL": "gemma3:12b",
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
    "KILL_OLLAMA_ON_EXIT": False,
    "RESPONSE_PROFILE": "software_engineer",
    "CURRICULUM_TEXT": "",
    "CURRICULUM_SOURCE": "",
    "MEETING_SUBJECTS": [],
    "ACTIVE_MEETING_SUBJECT": "",
    "MEETING_SUBJECT_ENABLED": False,
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
            # Migrate legacy single-model keys → split text/image keys
            # Migrate legacy single-provider key → split text/image providers
            if "LLM_PROVIDER" in saved:
                saved.setdefault("LLM_TEXT_PROVIDER", saved["LLM_PROVIDER"])
                saved.setdefault("LLM_IMAGE_PROVIDER", saved["LLM_PROVIDER"])
                del saved["LLM_PROVIDER"]
            if "OPENAI_MODEL" in saved:
                saved.setdefault("OPENAI_TEXT_MODEL", saved["OPENAI_MODEL"])
                saved.setdefault("OPENAI_IMAGE_MODEL", saved["OPENAI_MODEL"])
                del saved["OPENAI_MODEL"]
            if "OLLAMA_MODEL" in saved:
                saved.setdefault("OLLAMA_TEXT_MODEL", saved["OLLAMA_MODEL"])
                # Only default image model to old value if it was vision-capable
                _VISION_MODELS = {"gemma3:12b", "gemma4:e2b", "gemma4:e4b",
                                  "gemma4:26b", "gemma4:31b", "llama4:scout"}
                if saved["OLLAMA_MODEL"] in _VISION_MODELS:
                    saved.setdefault("OLLAMA_IMAGE_MODEL", saved["OLLAMA_MODEL"])
                del saved["OLLAMA_MODEL"]
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
