import unittest
from pathlib import Path


class NotesOverlayTests(unittest.TestCase):
    def test_notes_overlay_is_separate_from_quick_input_and_has_shortcut(self):
        root = Path(__file__).resolve().parents[1]
        settings_source = (root / "settings.py").read_text(encoding="utf-8")
        config_source = (root / "config.py").read_text(encoding="utf-8")
        ui_source = (root / "settings_ui.py").read_text(encoding="utf-8")
        main_source = (root / "main.py").read_text(encoding="utf-8")
        overlay_source = (root / "overlay.py").read_text(encoding="utf-8")

        self.assertIn("HOTKEY_NOTES", settings_source)
        self.assertIn('"HOTKEY_NOTES": "ctrl+shift+n"', settings_source)
        self.assertIn("HOTKEY_NOTES", config_source)
        self.assertIn("Take Notes", ui_source)
        self.assertIn("keyboard.add_hotkey(HOTKEY_NOTES", main_source)
        self.assertIn("def on_notes_hotkey", main_source)

        self.assertIn("def open_notes", overlay_source)
        self.assertIn("_notes_win", overlay_source)
        self.assertIn("Take Notes", overlay_source)
        self.assertIn("w, h = self._px(820), self._px(520)", overlay_source)
        self.assertIn("bar_w = self._px(720)", overlay_source)
        self.assertIn("input_btn.bind(\"<Button-1>\", lambda _: self.open_quick_input())", overlay_source)
        self.assertIn("notes_btn.bind(\"<Button-1>\", lambda _: self.open_notes())", overlay_source)


if __name__ == "__main__":
    unittest.main()
