import unittest
import inspect

import overlay


class InsightContentTests(unittest.TestCase):
    def test_splits_fenced_code_into_code_panel(self):
        text = (
            "First explain the approach.\n\n"
            "```python\n"
            "print('hello')\n"
            "```\n\n"
            "Then explain why this works."
        )

        content = overlay.split_insight_content(text)

        self.assertEqual(
            content.insights,
            "First explain the approach.\n\nThen explain why this works.",
        )
        self.assertEqual(content.code, "print('hello')")
        self.assertTrue(content.has_code)

    def test_overlay_uses_separate_code_panel_not_tabs(self):
        source = inspect.getsource(overlay.OverlayApp)

        self.assertIn("_ensure_code_panel", source)
        self.assertNotIn("_build_insight_tab", source)
        self.assertNotIn("_set_insight_tab", source)

    def test_keeps_plain_text_in_insights_when_no_code_exists(self):
        content = overlay.split_insight_content("No code needed here.")

        self.assertEqual(content.insights, "No code needed here.")
        self.assertEqual(content.code, "")
        self.assertFalse(content.has_code)


if __name__ == "__main__":
    unittest.main()
