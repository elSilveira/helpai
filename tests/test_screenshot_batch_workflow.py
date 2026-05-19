import unittest
from pathlib import Path


class ScreenshotBatchWorkflowTests(unittest.TestCase):
    def test_toolbar_exposes_save_and_analyze_screenshot_actions(self):
        root = Path(__file__).resolve().parents[1]
        overlay_source = (root / "overlay.py").read_text(encoding="utf-8")

        self.assertIn("on_screenshot", overlay_source)
        self.assertIn("on_analyze_screenshots", overlay_source)
        self.assertIn("Save Screenshot", overlay_source)
        self.assertIn("Analyze Screenshots", overlay_source)

    def test_toolbar_icon_buttons_use_fixed_centered_geometry(self):
        root = Path(__file__).resolve().parents[1]
        overlay_source = (root / "overlay.py").read_text(encoding="utf-8")

        self.assertIn("width=4", overlay_source)
        self.assertIn("height=1", overlay_source)
        self.assertIn("anchor=tk.CENTER", overlay_source)
        self.assertIn("pady=0", overlay_source)

    def test_screenshot_hotkey_saves_without_analyzing_and_analyze_action_sends_batch(self):
        root = Path(__file__).resolve().parents[1]
        main_source = (root / "main.py").read_text(encoding="utf-8")

        self.assertIn("_screenshot_batch.save(png)", main_source)
        self.assertIn("def _action_save_screenshot", main_source)
        self.assertIn("def _action_analyze_saved_screenshots", main_source)
        self.assertIn("analyze_screenshots(", main_source)
        self.assertIn("app.on_analyze_screenshots = on_analyze_screenshots_hotkey", main_source)
        self.assertIn("keyboard.add_hotkey(HOTKEY_SCREENSHOT_FEEDBACK, on_screenshot_hotkey", main_source)
        self.assertIn("keyboard.add_hotkey(HOTKEY_ANALYZE_SCREENSHOTS, on_analyze_screenshots_hotkey", main_source)
        self.assertNotIn("target=_action_screenshot_feedback", main_source)

    def test_clear_context_clears_saved_screenshot_batch(self):
        root = Path(__file__).resolve().parents[1]
        main_source = (root / "main.py").read_text(encoding="utf-8")

        self.assertIn("_screenshot_batch.clear()", main_source)

    def test_analyze_screenshots_hotkey_is_configured_and_visible_in_settings(self):
        root = Path(__file__).resolve().parents[1]
        settings_source = (root / "settings.py").read_text(encoding="utf-8")
        config_source = (root / "config.py").read_text(encoding="utf-8")
        ui_source = (root / "settings_ui.py").read_text(encoding="utf-8")

        self.assertIn("HOTKEY_ANALYZE_SCREENSHOTS", settings_source)
        self.assertIn('"HOTKEY_ANALYZE_SCREENSHOTS": "ctrl+shift+a"', settings_source)
        self.assertIn("HOTKEY_ANALYZE_SCREENSHOTS", config_source)
        self.assertIn("Save Screenshot", ui_source)
        self.assertIn("Analyze Saved Screenshots", ui_source)


if __name__ == "__main__":
    unittest.main()
