"""
HelpAI launcher — the single entry point for the desktop shortcut.

Shows the Settings UI first.  When the user clicks "Save & Launch",
it starts the main overlay.
"""

import sys
from pathlib import Path

# Ensure project directory is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from settings_ui import SettingsWindow


RUNTIME_MODULES_TO_REIMPORT = (
    "config",
    "audio_capture",
    "analyzer",
    "local_transcriber",
    "overlay",
    "screenshot",
    "speech_to_text",
    "main",
)


def _discard_runtime_modules() -> None:
    """Clear modules that snapshot settings at import time before launching."""
    for module_name in RUNTIME_MODULES_TO_REIMPORT:
        sys.modules.pop(module_name, None)


def launch_main():
    """Import and run main after the settings window closes."""
    _discard_runtime_modules()
    from main import main
    main()


def main() -> None:
    win = SettingsWindow(on_save_and_launch=launch_main)
    win.run()


if __name__ == "__main__":
    main()
