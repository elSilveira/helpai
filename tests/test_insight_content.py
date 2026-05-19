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

    def test_moves_file_marker_with_code_block_to_code_panel(self):
        text = (
            "First explain the approach.\n\n"
            "#### File: app.py\n"
            "This code is in `app.py`.\n"
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
        self.assertEqual(
            content.code,
            "#### File: app.py\nThis code is in `app.py`.\n\nprint('hello')",
        )
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

    def test_prepares_current_and_three_prior_insight_history_blocks(self):
        blocks = overlay.prepare_insight_history(
            "current response",
            ["previous response 1", "previous response 2", "previous response 3", "previous response 4"],
        )

        self.assertEqual([block.text for block in blocks], [
            "current response",
            "previous response 1",
            "previous response 2",
            "previous response 3",
        ])
        self.assertEqual([block.label for block in blocks], ["Now", "Previous 1", "Previous 2", "Previous 3"])
        self.assertEqual([block.tag for block in blocks], [
            "insight_current",
            "insight_history_1",
            "insight_history_2",
            "insight_history_3",
        ])

    def test_overlay_exposes_clear_context_action_from_insight_panel(self):
        source = inspect.getsource(overlay.OverlayApp)

        self.assertIn("on_clear_context", source)
        self.assertIn("clear_insight_context", source)
        self.assertIn("Clear context", source)


if __name__ == "__main__":
    unittest.main()
