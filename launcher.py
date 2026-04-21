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


def launch_main():
    """Import and run main after the settings window closes."""
    from main import main
    main()


if __name__ == "__main__":
    win = SettingsWindow(on_save_and_launch=launch_main)
    win.run()
