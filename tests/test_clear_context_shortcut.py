import unittest
from pathlib import Path


class ClearContextShortcutTests(unittest.TestCase):
    def test_clear_context_hotkey_is_configured_and_registered(self):
        root = Path(__file__).resolve().parents[1]
        settings_source = (root / "settings.py").read_text(encoding="utf-8")
        config_source = (root / "config.py").read_text(encoding="utf-8")
        ui_source = (root / "settings_ui.py").read_text(encoding="utf-8")
        main_source = (root / "main.py").read_text(encoding="utf-8")

        self.assertIn("HOTKEY_CLEAR_CONTEXT", settings_source)
        self.assertIn("HOTKEY_CLEAR_CONTEXT", config_source)
        self.assertIn("Clear Context", ui_source)
        self.assertIn("keyboard.add_hotkey(HOTKEY_CLEAR_CONTEXT", main_source)
        self.assertIn("_clear_context_memory", main_source)


if __name__ == "__main__":
    unittest.main()
